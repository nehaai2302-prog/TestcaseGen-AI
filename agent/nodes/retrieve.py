"""Retrieve similar bugs and test cases using pgvector RPC."""

from __future__ import annotations

import os
from typing import Any

from agent.state import TestGenState
from services.embeddings import embed_query, get_embeddings_model
from services.supabase_repo import SupabaseRepo


def retrieve_history(state: TestGenState, repo: SupabaseRepo) -> dict[str, Any]:
    project_id = state["project_id"]
    emb_model = get_embeddings_model()
    threshold = float(os.environ.get("RETRIEVAL_MATCH_THRESHOLD", "0.15"))
    k = int(os.environ.get("RETRIEVAL_TOP_K", "12"))

    bugs_map: dict[str, dict[str, Any]] = {
        str(b["id"]): b for b in state.get("retrieved_bugs") or []
    }
    tcs_map: dict[str, dict[str, Any]] = {
        str(t["id"]): t for t in state.get("retrieved_tcs") or []
    }

    pending = list(state.get("pending_queries") or [])
    chunks = state.get("requirement_chunks") or []

    query_texts: list[str] = []
    if pending:
        query_texts.extend(pending)
    else:
        joined = "\n\n".join(c.get("chunk_text", "") for c in chunks).strip()
        if not joined:
            return {
                "retrieved_bugs": [],
                "retrieved_tcs": [],
                "pending_queries": [],
                "current_step": "retrieve_history",
                "errors": (state.get("errors") or [])
                + ["No requirement text to retrieve against"],
            }
        query_texts.append(joined[:12000])

    for text in query_texts:
        qe = embed_query(emb_model, text)
        bugs = repo.match_bug_reports(project_id, qe, threshold, k)
        tcs = repo.match_test_cases(project_id, qe, threshold, k)
        for b in bugs:
            bugs_map[str(b["id"])] = b
        for t in tcs:
            tcs_map[str(t["id"])] = t

    bugs_list = list(bugs_map.values())
    tcs_list = list(tcs_map.values())
    bugs_list.sort(key=lambda b: float(b.get("similarity") or 0), reverse=True)
    tcs_list.sort(key=lambda t: float(t.get("similarity") or 0), reverse=True)

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
        "retrieved_bugs": bugs_list,
        "retrieved_tcs": tcs_list,
        "retrieval_summary": summary,
        "pending_queries": [],
        "current_step": "retrieve_history",
    }
