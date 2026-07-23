"""Tests for SRS change detection (Phase 5.3c)."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.srs_change import (
    diff_requirement_documents,
    format_srs_change_caption,
)
from services.supabase_repo import content_hash


def _row(rid: str, text: str) -> dict:
    return {
        "requirement_id": rid,
        "chunk_text": text,
        "content_hash": content_hash(text),
    }


def test_diff_first_upload_has_no_replace_ids() -> None:
    report = diff_requirement_documents(
        [],
        [_row("FR-1", "A"), _row("FR-2", "B")],
        document_name="srs.txt",
    )
    assert report["had_previous"] is False
    assert report["added"] == ["FR-1", "FR-2"]
    assert report["replace_requirement_ids"] == []


def test_diff_detects_changed_added_removed() -> None:
    previous = [_row("FR-1", "old text"), _row("FR-2", "same"), _row("FR-3", "gone")]
    new = [_row("FR-1", "new text"), _row("FR-2", "same"), _row("FR-4", "brand new")]
    report = diff_requirement_documents(previous, new, document_name="srs.txt")
    assert report["had_previous"] is True
    assert report["changed"] == ["FR-1"]
    assert report["unchanged"] == ["FR-2"]
    assert report["removed"] == ["FR-3"]
    assert report["added"] == ["FR-4"]
    assert report["replace_requirement_ids"] == ["FR-1", "FR-3"]


def test_diff_identical_reprepare_needs_no_replace() -> None:
    rows = [_row("FR-1", "text a"), _row("FR-2", "text b")]
    report = diff_requirement_documents(rows, rows, document_name="srs.txt")
    assert report["replace_requirement_ids"] == []
    assert report["unchanged_count"] == 2
    caption = format_srs_change_caption(report)
    assert "no generated-case replace" in caption.lower()


def test_format_caption_lists_replace_targets() -> None:
    report = {
        "had_previous": True,
        "changed_count": 1,
        "added_count": 0,
        "removed_count": 1,
        "replace_requirement_ids": ["FR-1", "FR-3"],
    }
    caption = format_srs_change_caption(report)
    assert "1 changed" in caption
    assert "1 removed" in caption
    assert "FR-1" in caption
    assert "replaced" in caption.lower()


def test_delete_generated_test_cases_for_requirements_filters_source() -> None:
    repo = MagicMock()
    repo._client = MagicMock()
    chain = repo._client.table.return_value.delete.return_value.eq.return_value.eq.return_value.in_
    chain.return_value.execute.return_value.data = [{"id": "1"}, {"id": "2"}]

    # Bind real method
    from services.supabase_repo import SupabaseRepo

    deleted = SupabaseRepo.delete_generated_test_cases_for_requirements(
        repo, "proj-1", ["FR-1", "FR-3", ""]
    )
    assert deleted == 2
    repo._client.table.assert_called_with("test_cases")
