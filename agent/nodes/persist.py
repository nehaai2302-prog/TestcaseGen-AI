"""Persist generated test cases and generation history."""

from __future__ import annotations

import uuid
import re
from typing import Any

from agent.state import TestGenState
from services.embeddings import embed_texts, get_embeddings_model
from services.supabase_repo import SupabaseRepo


def _uuid_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        try:
            out.append(str(uuid.UUID(str(v))))
        except (ValueError, TypeError):
            continue
    return out


_TYPE_CODES = {
    "positive": "POS",
    "negative": "NEG",
    "boundary": "BND",
    "edge": "EDGE",
}


def _safe_requirement_id(requirement_id: str) -> str:
    safe = re.sub(r"\s+", "-", requirement_id.strip())
    safe = re.sub(r'[\\/:*?"<>|]+', "-", safe)
    return safe.strip("-") or "REQ"


def _type_code(test_type: str | None) -> str:
    return _TYPE_CODES.get((test_type or "positive").strip().lower(), "TC")


def _existing_case_counters(
    repo: SupabaseRepo,
    project_id: str,
) -> dict[tuple[str, str], int]:
    counters: dict[tuple[str, str], int] = {}
    for row in repo.list_test_cases(project_id, limit=5000):
        req_id = (row.get("linked_requirement") or "").strip()
        tcid = (row.get("testcase_id") or "").strip()
        test_type = (row.get("test_type") or "").strip().lower()
        if not req_id or not tcid:
            continue
        code = _type_code(test_type)
        safe_req = _safe_requirement_id(req_id)
        prefix = f"TC_{safe_req}_{code}_"
        if not tcid.startswith(prefix):
            continue
        suffix = tcid.removeprefix(prefix)
        if not suffix.isdigit():
            continue
        key = (req_id, code)
        counters[key] = max(counters.get(key, 0), int(suffix))
    return counters


def _assign_testcase_ids(
    cases: list[dict[str, Any]],
    counters: dict[tuple[str, str], int],
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for case in cases:
        c = dict(case)
        if c.get("testcase_id"):
            updated.append(c)
            continue
        req_id = (c.get("linked_requirement") or "REQ").strip()
        code = _type_code(c.get("test_type"))
        key = (req_id, code)
        counters[key] = counters.get(key, 0) + 1
        c["testcase_id"] = f"TC_{_safe_requirement_id(req_id)}_{code}_{counters[key]:02d}"
        updated.append(c)
    return updated


def persist(state: TestGenState, repo: SupabaseRepo) -> dict[str, Any]:
    project_id = state["project_id"]
    doc_name = state.get("document_name") or ""
    counters = _existing_case_counters(repo, project_id)
    all_validated = list(state.get("validated_cases") or [])
    # Regen: only insert newly accepted cases (already-persisted keep their IDs).
    to_insert = [
        c for c in all_validated if not c.get("_already_persisted")
    ] if state.get("regen_mode") else all_validated
    validated = _assign_testcase_ids(to_insert, counters)
    # Preserve prior cases in state for UI; assign IDs only to new ones above.
    if state.get("regen_mode"):
        prior = [c for c in all_validated if c.get("_already_persisted")]
        validated_for_state = prior + validated
    else:
        validated_for_state = validated
    dups = _assign_testcase_ids(list(state.get("duplicates") or []), counters)

    emb_model = get_embeddings_model()
    texts: list[str] = []
    rows: list[dict[str, Any]] = []
    for case in validated:
        steps = case.get("steps") or []
        if isinstance(steps, list):
            steps_str = "\n".join(str(s) for s in steps)
        else:
            steps_str = str(steps)
        blob = f"{case.get('title','')}\n{case.get('description') or ''}\n{steps_str}\n{case.get('expected_result','')}"
        texts.append(blob)
        row = {
            "project_id": project_id,
            "testcase_id": case.get("testcase_id"),
            "title": case.get("title"),
            "description": case.get("description"),
            "preconditions": case.get("preconditions"),
            "steps": steps if isinstance(steps, list) else [str(steps)],
            "expected_result": case.get("expected_result"),
            "test_type": case.get("test_type") or "positive",
            "priority": case.get("priority") or "medium",
            "module": case.get("module"),
            "linked_requirement": case.get("linked_requirement"),
            "source": "generated",
            "is_duplicate": False,
            "source_requirement_chunk_ids": _uuid_list(case.get("source_requirement_chunk_ids")),
            "supporting_bug_ids": _uuid_list(case.get("supporting_bug_ids")),
            "supporting_test_case_ids": _uuid_list(case.get("supporting_test_case_ids")),
        }
        rows.append(row)

    if texts:
        vectors = embed_texts(emb_model, texts)
        for r, v in zip(rows, vectors):
            r["embedding"] = v
        repo.insert_test_cases(rows)

    dup_rows: list[dict[str, Any]] = []
    dup_texts: list[str] = []
    for case in dups:
        steps = case.get("steps") or []
        if isinstance(steps, list):
            steps_str = "\n".join(str(s) for s in steps)
        else:
            steps_str = str(steps)
        blob = f"{case.get('title','')}\n{steps_str}"
        dup_texts.append(blob)
        dup_rows.append(
            {
                "project_id": project_id,
                "testcase_id": case.get("testcase_id"),
                "title": case.get("title"),
                "description": case.get("description"),
                "preconditions": case.get("preconditions"),
                "steps": steps if isinstance(steps, list) else [str(steps)],
                "expected_result": case.get("expected_result"),
                "test_type": case.get("test_type") or "positive",
                "priority": case.get("priority") or "medium",
                "module": case.get("module"),
                "linked_requirement": case.get("linked_requirement"),
                "source": "generated",
                "is_duplicate": True,
                "similar_to_title": case.get("similar_to_title"),
                "source_requirement_chunk_ids": _uuid_list(case.get("source_requirement_chunk_ids")),
                "supporting_bug_ids": _uuid_list(case.get("supporting_bug_ids")),
                "supporting_test_case_ids": _uuid_list(case.get("supporting_test_case_ids")),
            }
        )
    if dup_texts:
        vectors = embed_texts(emb_model, dup_texts)
        for r, v in zip(dup_rows, vectors):
            r["embedding"] = v
        repo.insert_test_cases(dup_rows)

    rag = state.get("rag_stats") or {}
    model_note = state.get("model_name") or ""
    dedup_stats = state.get("batch_dedup_stats") or {}
    if dedup_stats:
        model_note = (
            f"{model_note}; dedup_kept={dedup_stats.get('kept', 0)}"
            f"; batch_title={dedup_stats.get('removed_title', 0)}"
            f"; batch_verbatim={dedup_stats.get('removed_verbatim', 0)}"
            f"; batch_cross_req={dedup_stats.get('removed_cross_req', 0)}"
            f"; batch_semantic={dedup_stats.get('removed_semantic', 0)}"
            f"; library={dedup_stats.get('removed_library', 0)}"
        ).strip("; ")
    if rag.get("history_available"):
        model_note = (
            f"{model_note}; RAG linked {rag.get('cases_with_history_links', 0)}/"
            f"{rag.get('total_cases', 0)}"
        ).strip("; ")

    repo.insert_generation_history(
        {
            "project_id": project_id,
            "requirement_doc": doc_name,
            "test_cases_generated": len(validated) + len(dups),
            "duplicates_found": len(dups),
            "agent_looped_back": bool(state.get("agent_looped_back")),
            "model_name": model_note or None,
        }
    )

    return {
        "validated_cases": validated_for_state,
        "duplicates": dups,
        "current_step": "persist",
    }
