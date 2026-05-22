"""Library test case list + semantic / keyword search."""

from __future__ import annotations

import os
from typing import Any, Literal

from services.embeddings import embed_query, get_embeddings_model
from services.supabase_repo import SupabaseRepo

SearchMode = Literal["semantic", "keyword", "none"] | None


def _apply_row_filters(
    rows: list[dict[str, Any]],
    test_type: str,
    priority: str,
    source: str,
) -> list[dict[str, Any]]:
    out = rows
    if test_type and test_type != "(any)":
        out = [r for r in out if (r.get("test_type") or "").lower() == test_type.lower()]
    if priority and priority != "(any)":
        out = [r for r in out if (r.get("priority") or "").lower() == priority.lower()]
    if source and source != "(any)":
        out = [r for r in out if (r.get("source") or "").lower() == source.lower()]
    return out


def _keyword_match(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = query.lower()
    matched: list[dict[str, Any]] = []
    for row in rows:
        parts = [
            str(row.get("title") or ""),
            str(row.get("description") or ""),
            str(row.get("testcase_id") or ""),
            str(row.get("linked_requirement") or ""),
            str(row.get("module") or ""),
            str(row.get("preconditions") or ""),
            str(row.get("expected_result") or ""),
        ]
        steps = row.get("steps") or []
        if isinstance(steps, list):
            parts.extend(str(s) for s in steps)
        elif steps:
            parts.append(str(steps))
        if needle in "\n".join(parts).lower():
            matched.append(row)
    return matched


def library_test_case_rows(
    repo: SupabaseRepo,
    project_id: str,
    query: str,
    *,
    test_type: str = "(any)",
    priority: str = "(any)",
    source: str = "(any)",
) -> tuple[list[dict[str, Any]], SearchMode]:
    """Return filtered rows and how they were matched (None = browse, no search query)."""
    if not query.strip():
        rows = repo.list_test_cases(
            project_id,
            test_type=None if test_type == "(any)" else test_type,
            priority=None if priority == "(any)" else priority,
            source=None if source == "(any)" else source,
            limit=300,
        )
        return rows, None

    q = query.strip()
    threshold = float(
        os.environ.get(
            "LIBRARY_SEARCH_THRESHOLD",
            os.environ.get("RETRIEVAL_MATCH_THRESHOLD", "0.1"),
        )
    )
    match_count = int(os.environ.get("LIBRARY_SEARCH_MATCH_COUNT", "50"))

    pool = repo.list_test_cases(project_id, limit=500)
    emb = get_embeddings_model()
    vec = embed_query(emb, q)

    hits: list[dict[str, Any]] = []
    try:
        hits = repo.match_test_cases(
            project_id,
            vec,
            match_threshold=threshold,
            match_count=match_count,
        )
    except Exception:
        hits = []

    hit_ids = {str(h["id"]) for h in hits}
    sim_map = {str(h["id"]): float(h.get("similarity", 0)) for h in hits}
    vector_rows: list[dict[str, Any]] = []
    for row in pool:
        rid = str(row["id"])
        if rid in hit_ids:
            copy = dict(row)
            copy["_similarity"] = sim_map.get(rid, 0.0)
            vector_rows.append(copy)
    vector_rows.sort(key=lambda r: float(r.get("_similarity") or 0), reverse=True)

    if vector_rows:
        filtered = _apply_row_filters(vector_rows, test_type, priority, source)
        return filtered, "semantic"

    keyword_rows = _keyword_match(pool, q)
    for row in keyword_rows:
        row.pop("_similarity", None)
    if keyword_rows:
        filtered = _apply_row_filters(keyword_rows, test_type, priority, source)
        return filtered, "keyword"

    return [], "none"
