"""Per-rule pgvector retrieval using rule text + scope as the query.

Each atomic rule is embedded as
`"Scope: {scope}. Module: {module}. Requirement: {summary}. {detail}"` so the scope name
(a UI screen, service, endpoint, or functional area) participates in the semantic search.
A bug or test case mentioning the scope will surface for the rule even if its module is
different.
"""

from __future__ import annotations

import os
from typing import Any

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


def retrieve_history_per_rule(
    state: TestGenState, repo: SupabaseRepo
) -> dict[str, Any]:
    project_id = state["project_id"]
    rules = list(state.get("atomic_rules") or [])
    if not rules:
        return {
            "retrieved_bugs": [],
            "retrieved_tcs": [],
            "rule_retrievals": {},
            "current_step": "retrieve_history_per_rule",
        }

    threshold = float(os.environ.get("RETRIEVAL_MATCH_THRESHOLD", "0.15"))
    k = int(os.environ.get("RETRIEVAL_TOP_K_PER_RULE", "4"))

    queries = [_rule_query(r) for r in rules]
    emb = get_embeddings_model()
    qvecs = embed_texts(emb, queries)

    bugs_map: dict[str, dict[str, Any]] = {}
    tcs_map: dict[str, dict[str, Any]] = {}
    rule_retrievals: dict[str, dict[str, Any]] = {}
    updated_rules: list[dict[str, Any]] = []

    for rule, qv, qtext in zip(rules, qvecs, queries):
        rid = rule.get("rule_id", "")
        bugs = repo.match_bug_reports(project_id, qv, threshold, k)
        tcs = repo.match_test_cases(project_id, qv, threshold, k)
        bug_ids = [str(b.get("id")) for b in bugs if b.get("id")]
        tc_ids = [str(t.get("id")) for t in tcs if t.get("id")]

        _merge_top(bugs_map, bugs)
        _merge_top(tcs_map, tcs)

        rule_retrievals[rid] = {
            "query": qtext,
            "scope": (rule.get("screen") or "General"),
            "bug_ids": bug_ids,
            "tc_ids": tc_ids,
        }

        updated = dict(rule)
        updated["retrieval_query"] = qtext
        updated["retrieved_bug_ids"] = bug_ids
        updated["retrieved_tc_ids"] = tc_ids
        updated_rules.append(updated)

    bugs_list = sorted(
        bugs_map.values(),
        key=lambda b: float(b.get("similarity") or 0),
        reverse=True,
    )
    tcs_list = sorted(
        tcs_map.values(),
        key=lambda t: float(t.get("similarity") or 0),
        reverse=True,
    )

    summary = {
        "bug_count": len(bugs_list),
        "tc_count": len(tcs_list),
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
        "current_step": "retrieve_history_per_rule",
    }
