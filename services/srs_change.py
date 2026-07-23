"""Detect requirement-document changes across re-prepare of the same filename."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.supabase_repo import content_hash


def _hashes_by_requirement_id(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    """Map requirement_id → sorted content hashes (supports multi-chunk IDs)."""
    by_id: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        rid = str(row.get("requirement_id") or "").strip()
        if not rid:
            continue
        h = str(row.get("content_hash") or "").strip()
        if not h:
            h = content_hash(str(row.get("chunk_text") or ""))
        by_id[rid].append(h)
    return {rid: tuple(sorted(hashes)) for rid, hashes in by_id.items()}


def diff_requirement_documents(
    previous_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    *,
    document_name: str = "",
) -> dict[str, Any]:
    """Compare previous vs new requirement chunks for one document.

    Returns a report with changed / added / removed requirement IDs and
    ``replace_requirement_ids`` = changed + removed (cases to purge on generate).
    """
    prev = _hashes_by_requirement_id(previous_rows)
    nxt = _hashes_by_requirement_id(new_rows)
    prev_ids = set(prev)
    next_ids = set(nxt)

    added = sorted(next_ids - prev_ids)
    removed = sorted(prev_ids - next_ids)
    changed = sorted(
        rid for rid in (prev_ids & next_ids) if prev[rid] != nxt[rid]
    )
    unchanged = sorted(
        rid for rid in (prev_ids & next_ids) if prev[rid] == nxt[rid]
    )
    replace_ids = sorted(set(changed) | set(removed))

    return {
        "document_name": document_name,
        "had_previous": bool(previous_rows),
        "changed": changed,
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "replace_requirement_ids": replace_ids,
        "changed_count": len(changed),
        "added_count": len(added),
        "removed_count": len(removed),
        "unchanged_count": len(unchanged),
    }


def format_srs_change_caption(report: dict[str, Any] | None) -> str:
    """Short UI caption for prepare / generate."""
    if not report or not report.get("had_previous"):
        return ""
    parts: list[str] = []
    if report.get("changed_count"):
        parts.append(f"{report['changed_count']} changed")
    if report.get("added_count"):
        parts.append(f"{report['added_count']} added")
    if report.get("removed_count"):
        parts.append(f"{report['removed_count']} removed")
    if not parts:
        return (
            "Same document re-prepared — requirement text matches the previous version "
            "(no generated-case replace needed)."
        )
    replace_ids = report.get("replace_requirement_ids") or []
    id_preview = ", ".join(replace_ids[:8])
    if len(replace_ids) > 8:
        id_preview += "…"
    return (
        f"SRS update detected ({'; '.join(parts)}). "
        f"On generate, previously generated cases for "
        f"**{id_preview or 'changed/removed IDs'}** will be replaced."
    )
