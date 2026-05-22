"""RAG linkage stats and ID resolution for demo UI."""

from __future__ import annotations

import math
from typing import Any


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def build_history_lookup(
    bugs: list[dict[str, Any]],
    tcs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for b in bugs:
        lookup[f"bug:{b.get('id')}"] = {**b, "_kind": "bug"}
    for t in tcs:
        lookup[f"tc:{t.get('id')}"] = {**t, "_kind": "test_case"}
    return lookup


def resolve_supporting(
    case: dict[str, Any],
    bugs: list[dict[str, Any]],
    tcs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Human-readable list of linked history items for one case."""
    bug_map = {str(b.get("id")): b for b in bugs}
    tc_map = {str(t.get("id")): t for t in tcs}
    out: list[dict[str, Any]] = []
    for bid in case.get("supporting_bug_ids") or []:
        b = bug_map.get(str(bid))
        if b:
            out.append(
                {
                    "kind": "bug",
                    "id": str(bid),
                    "title": b.get("title"),
                    "similarity": b.get("similarity"),
                    "link_source": case.get("rag_link_source"),
                }
            )
    for tid in case.get("supporting_test_case_ids") or []:
        t = tc_map.get(str(tid))
        if t:
            out.append(
                {
                    "kind": "test_case",
                    "id": str(tid),
                    "title": t.get("title"),
                    "similarity": t.get("similarity"),
                    "link_source": case.get("rag_link_source"),
                }
            )
    return out


def compute_rag_stats(
    cases: list[dict[str, Any]],
    bugs: list[dict[str, Any]],
    tcs: list[dict[str, Any]],
) -> dict[str, Any]:
    with_links = 0
    llm_links = 0
    semantic_links = 0
    for c in cases:
        has = bool(c.get("supporting_bug_ids")) or bool(c.get("supporting_test_case_ids"))
        if has:
            with_links += 1
            src = c.get("rag_link_source") or "llm"
            if src == "semantic_fallback":
                semantic_links += 1
            else:
                llm_links += 1
    return {
        "retrieved_bug_count": len(bugs),
        "retrieved_tc_count": len(tcs),
        "total_cases": len(cases),
        "cases_with_history_links": with_links,
        "cases_llm_linked": llm_links,
        "cases_semantic_linked": semantic_links,
        "history_available": bool(bugs or tcs),
    }


def semantic_link_cases(
    cases: list[dict[str, Any]],
    bugs: list[dict[str, Any]],
    tcs: list[dict[str, Any]],
    *,
    case_vectors: list[list[float]],
    history_vectors: list[list[float]],
    history_meta: list[tuple[str, str]],
    min_similarity: float = 0.42,
) -> list[dict[str, Any]]:
    """
    Fill supporting_* on cases that have no history link when retrieval returned items.
    history_meta: (kind, id) parallel to history_vectors — kind is 'bug' or 'tc'.
    """
    if not history_vectors:
        return cases

    updated: list[dict[str, Any]] = []
    for case, cv in zip(cases, case_vectors):
        c = dict(case)
        has_link = bool(c.get("supporting_bug_ids")) or bool(c.get("supporting_test_case_ids"))
        if has_link:
            c.setdefault("rag_link_source", "llm")
            updated.append(c)
            continue

        best_sim = 0.0
        best_kind = ""
        best_id = ""
        for (kind, hid), hv in zip(history_meta, history_vectors):
            sim = _cosine(cv, hv)
            if sim > best_sim:
                best_sim = sim
                best_kind = kind
                best_id = hid

        if best_sim >= min_similarity and best_id:
            if best_kind == "bug":
                c["supporting_bug_ids"] = [best_id]
                c["supporting_test_case_ids"] = c.get("supporting_test_case_ids") or []
            else:
                c["supporting_test_case_ids"] = [best_id]
                c["supporting_bug_ids"] = c.get("supporting_bug_ids") or []
            c["rag_link_source"] = "semantic_fallback"
            c["rag_link_similarity"] = round(best_sim, 3)
            note = c.get("description") or ""
            prefix = f"[Grounded in project history — {best_kind} match, sim={best_sim:.2f}] "
            if prefix.strip() not in (note or ""):
                c["description"] = (prefix + note).strip() if note else prefix.strip()

        updated.append(c)
    return updated
