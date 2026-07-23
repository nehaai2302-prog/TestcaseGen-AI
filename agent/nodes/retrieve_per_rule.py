"""Per-rule pgvector retrieval using rule text + scope as the query.

Each atomic rule is embedded as
`"Scope: {scope}. Module: {module}. Requirement: {summary}. {detail}"` so the scope name
(a UI screen, service, endpoint, or functional area) participates in the semantic search.
A bug or test case mentioning the scope will surface for the rule even if its module is
different.

After raw retrieval, a relevance guard drops low-similarity and foreign-domain items
so off-topic project history (e.g. e-commerce imports in an energy SRS project) does
not pollute generation prompts.
"""

from __future__ import annotations

import os
from typing import Any

from agent.ambiguity import generatable_rules
from agent.rag_relevance import (
    filter_relevant_items,
    requirement_corpus_tokens,
)
from agent.state import TestGenState
from services.embeddings import embed_texts, get_embeddings_model
from services.supabase_repo import SupabaseRepo


def _rule_query(rule: dict[str, Any]) -> str:
    scope = (rule.get("screen") or "").strip() or "General"
    module = (rule.get("module") or "").strip()
    summary = (rule.get("summary") or "").strip()
    detail = (rule.get("detail") or "").strip()
    parts: list[str] = []
    # Skip the noisy "Scope: General." prefix - it adds no signal when no real scope exists.
    if scope and scope.lower() != "general":
        parts.append(f"Scope: {scope}.")
    if module:
        parts.append(f"Module: {module}.")
    if summary:
        parts.append(f"Requirement: {summary}.")
    if detail:
        parts.append(detail)
    return " ".join(parts).strip()


def _merge_top(
    existing: dict[str, dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> None:
    """Keep the highest similarity per id."""
    for item in incoming:
        key = str(item.get("id"))
        if not key:
            continue
        sim_new = float(item.get("similarity") or 0)
        cur = existing.get(key)
        if cur is None or sim_new > float(cur.get("similarity") or 0):
            existing[key] = item


def _empty_retrieval(all_rules: list[dict[str, Any]], *, reason: str) -> dict[str, Any]:
    return {
        "atomic_rules": all_rules,
        "requirements": all_rules,
        "retrieved_bugs": [],
        "retrieved_tcs": [],
        "rule_retrievals": {},
        "retrieval_summary": {
            "bug_count": 0,
            "tc_count": 0,
            "bugs": [],
            "test_cases": [],
            "use_project_history": False,
            "skip_reason": reason,
        },
        "rag_stats": {
            "use_project_history": False,
            "retrieved_bugs": 0,
            "retrieved_tcs": 0,
            "used_bugs": 0,
            "used_tcs": 0,
            "dropped_bugs": 0,
            "dropped_tcs": 0,
            "skip_reason": reason,
        },
        "current_step": "retrieve_history_per_rule",
    }


def retrieve_history_per_rule(
    state: TestGenState, repo: SupabaseRepo
) -> dict[str, Any]:
    project_id = state["project_id"]
    all_rules = list(state.get("atomic_rules") or [])
    use_history = state.get("use_project_history", True)
    if use_history is False:
        return _empty_retrieval(all_rules, reason="use_project_history_disabled")

    rules = generatable_rules(all_rules)
    if not all_rules:
        return {
            "retrieved_bugs": [],
            "retrieved_tcs": [],
            "rule_retrievals": {},
            "rag_stats": {
                "use_project_history": True,
                "retrieved_bugs": 0,
                "retrieved_tcs": 0,
                "used_bugs": 0,
                "used_tcs": 0,
                "dropped_bugs": 0,
                "dropped_tcs": 0,
            },
            "current_step": "retrieve_history_per_rule",
        }
    if not rules:
        return {
            "atomic_rules": all_rules,
            "requirements": all_rules,
            "retrieved_bugs": [],
            "retrieved_tcs": [],
            "rule_retrievals": {},
            "retrieval_summary": {
                "bug_count": 0,
                "tc_count": 0,
                "bugs": [],
                "test_cases": [],
            },
            "rag_stats": {
                "use_project_history": True,
                "retrieved_bugs": 0,
                "retrieved_tcs": 0,
                "used_bugs": 0,
                "used_tcs": 0,
                "dropped_bugs": 0,
                "dropped_tcs": 0,
            },
            "current_step": "retrieve_history_per_rule",
        }

    threshold = float(os.environ.get("RETRIEVAL_MATCH_THRESHOLD", "0.15"))
    k = int(os.environ.get("RETRIEVAL_TOP_K_PER_RULE", "4"))
    req_tokens = requirement_corpus_tokens(all_rules)

    queries = [_rule_query(r) for r in rules]
    emb = get_embeddings_model()
    qvecs = embed_texts(emb, queries)

    raw_bugs_map: dict[str, dict[str, Any]] = {}
    raw_tcs_map: dict[str, dict[str, Any]] = {}
    used_bugs_map: dict[str, dict[str, Any]] = {}
    used_tcs_map: dict[str, dict[str, Any]] = {}
    rule_retrievals: dict[str, dict[str, Any]] = {}
    enriched_by_id: dict[str, dict[str, Any]] = {}
    dropped_bug_ids: set[str] = set()
    dropped_tc_ids: set[str] = set()

    for rule, qv, qtext in zip(rules, qvecs, queries):
        rid = rule.get("rule_id", "")
        raw_bugs = repo.match_bug_reports(project_id, qv, threshold, k)
        raw_tcs = repo.match_test_cases(project_id, qv, threshold, k)

        kept_bugs, dropped_bugs = filter_relevant_items(raw_bugs, req_tokens)
        kept_tcs, dropped_tcs = filter_relevant_items(raw_tcs, req_tokens)

        bug_ids = [str(b.get("id")) for b in kept_bugs if b.get("id")]
        tc_ids = [str(t.get("id")) for t in kept_tcs if t.get("id")]
        raw_bug_ids = [str(b.get("id")) for b in raw_bugs if b.get("id")]
        raw_tc_ids = [str(t.get("id")) for t in raw_tcs if t.get("id")]

        _merge_top(raw_bugs_map, raw_bugs)
        _merge_top(raw_tcs_map, raw_tcs)
        _merge_top(used_bugs_map, kept_bugs)
        _merge_top(used_tcs_map, kept_tcs)
        dropped_bug_ids.update(str(b.get("id")) for b in dropped_bugs if b.get("id"))
        dropped_tc_ids.update(str(t.get("id")) for t in dropped_tcs if t.get("id"))

        rule_retrievals[rid] = {
            "query": qtext,
            "scope": (rule.get("screen") or "General"),
            "bug_ids": bug_ids,
            "tc_ids": tc_ids,
            "raw_bug_ids": raw_bug_ids,
            "raw_tc_ids": raw_tc_ids,
            "dropped_bug_ids": [str(b.get("id")) for b in dropped_bugs if b.get("id")],
            "dropped_tc_ids": [str(t.get("id")) for t in dropped_tcs if t.get("id")],
        }

        updated = dict(rule)
        updated["retrieval_query"] = qtext
        updated["retrieved_bug_ids"] = bug_ids
        updated["retrieved_tc_ids"] = tc_ids
        updated["raw_retrieved_bug_ids"] = raw_bug_ids
        updated["raw_retrieved_tc_ids"] = raw_tc_ids
        enriched_by_id[rid] = updated

    updated_rules = [enriched_by_id.get(r.get("rule_id", ""), dict(r)) for r in all_rules]

    bugs_list = sorted(
        used_bugs_map.values(),
        key=lambda b: float(b.get("similarity") or 0),
        reverse=True,
    )
    tcs_list = sorted(
        used_tcs_map.values(),
        key=lambda t: float(t.get("similarity") or 0),
        reverse=True,
    )

    rag_stats = {
        "use_project_history": True,
        "retrieved_bugs": len(raw_bugs_map),
        "retrieved_tcs": len(raw_tcs_map),
        "used_bugs": len(used_bugs_map),
        "used_tcs": len(used_tcs_map),
        "dropped_bugs": len(dropped_bug_ids),
        "dropped_tcs": len(dropped_tc_ids),
    }

    summary = {
        "bug_count": len(bugs_list),
        "tc_count": len(tcs_list),
        "retrieved_bug_count": rag_stats["retrieved_bugs"],
        "retrieved_tc_count": rag_stats["retrieved_tcs"],
        "used_bug_count": rag_stats["used_bugs"],
        "used_tc_count": rag_stats["used_tcs"],
        "dropped_bug_count": rag_stats["dropped_bugs"],
        "dropped_tc_count": rag_stats["dropped_tcs"],
        "use_project_history": True,
        "bugs": [
            {
                "id": str(b.get("id")),
                "title": b.get("title"),
                "similarity": b.get("similarity"),
            }
            for b in bugs_list[:15]
        ],
        "test_cases": [
            {
                "id": str(t.get("id")),
                "title": t.get("title"),
                "similarity": t.get("similarity"),
            }
            for t in tcs_list[:15]
        ],
    }

    return {
        "atomic_rules": updated_rules,
        "requirements": updated_rules,
        "retrieved_bugs": bugs_list,
        "retrieved_tcs": tcs_list,
        "retrieval_summary": summary,
        "rule_retrievals": rule_retrievals,
        "rag_stats": rag_stats,
        "current_step": "retrieve_history_per_rule",
    }
