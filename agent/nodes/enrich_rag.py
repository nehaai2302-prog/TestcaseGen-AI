"""Semantic fallback links from retrieved history when the LLM omitted supporting_* IDs.

Uses each rule's own retrieved pool (set by `retrieve_history_per_rule`) rather than the
global pool. Falls back to the global pool only for cases that have no `linked_requirement`.
"""

from __future__ import annotations

import math
import os
from typing import Any

from agent.rag_display import compute_rag_stats, semantic_link_cases
from agent.state import TestGenState
from services.embeddings import embed_texts, get_embeddings_model


def _case_blob(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_str = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return (
        f"{case.get('title', '')}\n{case.get('description') or ''}\n"
        f"{steps_str}\n{case.get('expected_result', '')}"
    )


def _history_blob(item: dict[str, Any]) -> str:
    return f"{item.get('title', '')}\n{item.get('description') or ''}"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _attach_link(case: dict[str, Any], kind: str, hid: str, sim: float) -> dict[str, Any]:
    c = dict(case)
    if kind == "bug":
        c["supporting_bug_ids"] = [hid]
        c["supporting_test_case_ids"] = c.get("supporting_test_case_ids") or []
    else:
        c["supporting_test_case_ids"] = [hid]
        c["supporting_bug_ids"] = c.get("supporting_bug_ids") or []
    c["rag_link_source"] = "semantic_fallback"
    c["rag_link_similarity"] = round(sim, 3)
    note = c.get("description") or ""
    prefix = f"[Grounded in project history - {kind} match, sim={sim:.2f}] "
    if prefix.strip() not in (note or ""):
        c["description"] = (prefix + note).strip() if note else prefix.strip()
    return c


_RETRIEVAL_STAT_KEYS = (
    "use_project_history",
    "skip_reason",
    "retrieved_bugs",
    "retrieved_tcs",
    "used_bugs",
    "used_tcs",
    "dropped_bugs",
    "dropped_tcs",
)


def _merge_rag_stats(
    prior: dict[str, Any] | None,
    link_stats: dict[str, Any],
) -> dict[str, Any]:
    """Keep retrieve_* counters from retrieval; add/overwrite link-quality fields."""
    merged = dict(link_stats)
    for key in _RETRIEVAL_STAT_KEYS:
        if prior and key in prior:
            merged[key] = prior[key]
    return merged


def enrich_rag_links(state: TestGenState) -> dict[str, Any]:
    cases = list(state.get("generated_cases") or [])
    bugs = list(state.get("retrieved_bugs") or [])
    tcs = list(state.get("retrieved_tcs") or [])
    rules = list(state.get("atomic_rules") or [])
    prior_stats = dict(state.get("rag_stats") or {})

    if not cases or (not bugs and not tcs):
        stats = _merge_rag_stats(prior_stats, compute_rag_stats(cases, bugs, tcs))
        return {
            "generated_cases": cases,
            "rag_stats": stats,
            "current_step": "enrich_rag_links",
        }

    unlinked_idx = [
        i
        for i, c in enumerate(cases)
        if not (c.get("supporting_bug_ids") or c.get("supporting_test_case_ids"))
    ]
    if not unlinked_idx:
        stats = _merge_rag_stats(prior_stats, compute_rag_stats(cases, bugs, tcs))
        return {
            "generated_cases": cases,
            "rag_stats": stats,
            "current_step": "enrich_rag_links",
        }

    min_sim = float(os.environ.get("RAG_LINK_MIN_SIMILARITY", "0.55"))
    emb = get_embeddings_model()
    bugs_by_id = {str(b.get("id")): b for b in bugs}
    tcs_by_id = {str(t.get("id")): t for t in tcs}
    rules_by_id = {r.get("rule_id"): r for r in rules if r.get("rule_id")}
    enriched = list(cases)

    # Group unlinked cases by their linked rule. Per-rule fallback is preferred
    # because the candidate pool is the rule's own screen-aware retrieval.
    per_rule: dict[str, list[int]] = {}
    no_rule_idx: list[int] = []
    for i in unlinked_idx:
        rid = (cases[i].get("linked_requirement") or "").strip()
        if rid and rid in rules_by_id:
            per_rule.setdefault(rid, []).append(i)
        else:
            no_rule_idx.append(i)

    for rid, idxs in per_rule.items():
        rule = rules_by_id[rid]
        bug_ids = [bid for bid in (rule.get("retrieved_bug_ids") or []) if bid in bugs_by_id]
        tc_ids = [tid for tid in (rule.get("retrieved_tc_ids") or []) if tid in tcs_by_id]
        pool_meta: list[tuple[str, str]] = [("bug", bid) for bid in bug_ids] + [
            ("tc", tid) for tid in tc_ids
        ]
        if not pool_meta:
            continue

        case_texts = [_case_blob(enriched[i]) for i in idxs]
        pool_texts = [
            _history_blob(bugs_by_id[hid] if kind == "bug" else tcs_by_id[hid])
            for kind, hid in pool_meta
        ]
        vectors = embed_texts(emb, case_texts + pool_texts)
        case_vecs = vectors[: len(case_texts)]
        pool_vecs = vectors[len(case_texts) :]

        for case_idx, cv in zip(idxs, case_vecs):
            best_sim = 0.0
            best_kind = ""
            best_id = ""
            for (kind, hid), hv in zip(pool_meta, pool_vecs):
                sim = _cosine(cv, hv)
                if sim > best_sim:
                    best_sim = sim
                    best_kind = kind
                    best_id = hid
            if best_sim >= min_sim and best_id:
                enriched[case_idx] = _attach_link(
                    enriched[case_idx], best_kind, best_id, best_sim
                )

    if no_rule_idx:
        # Global-pool fallback for any case without a rule link.
        global_cases = [enriched[i] for i in no_rule_idx]
        case_texts = [_case_blob(c) for c in global_cases]
        history_meta: list[tuple[str, str]] = []
        history_texts: list[str] = []
        for b in bugs:
            history_meta.append(("bug", str(b.get("id", ""))))
            history_texts.append(_history_blob(b))
        for t in tcs:
            history_meta.append(("tc", str(t.get("id", ""))))
            history_texts.append(_history_blob(t))
        if history_meta:
            vectors = embed_texts(emb, case_texts + history_texts)
            case_vecs = vectors[: len(case_texts)]
            hv_list = vectors[len(case_texts) :]
            patched = semantic_link_cases(
                global_cases,
                bugs,
                tcs,
                case_vectors=case_vecs,
                history_vectors=hv_list,
                history_meta=history_meta,
                min_similarity=min_sim,
            )
            for idx, p in zip(no_rule_idx, patched):
                enriched[idx] = p

    stats = _merge_rag_stats(prior_stats, compute_rag_stats(enriched, bugs, tcs))
    return {
        "generated_cases": enriched,
        "positive_cases": [c for c in enriched if c.get("test_type") == "positive"],
        "destructive_cases": [
            c for c in enriched if c.get("test_type") in ("negative", "boundary", "edge")
        ],
        "rag_stats": stats,
        "current_step": "enrich_rag_links",
    }
