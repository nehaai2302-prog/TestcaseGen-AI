"""Tests for Analyst rule_id de-duplication (Option B)."""

from __future__ import annotations

from agent.nodes.analyst import ensure_unique_rule_ids


def _chunk(
    cid: str,
    requirement_id: str,
    *,
    synthetic: bool = True,
) -> dict:
    return {
        "id": cid,
        "requirement_id": requirement_id,
        "chunk_text": f"Body for {requirement_id}",
        "is_synthetic_requirement": synthetic,
    }


def test_no_change_when_rule_ids_already_unique() -> None:
    chunks = [_chunk("a", "REQ-01"), _chunk("b", "REQ-02")]
    rules = [
        {"rule_id": "REQ-01-1", "source_requirement_chunk_ids": ["a"]},
        {"rule_id": "REQ-02-1", "source_requirement_chunk_ids": ["b"]},
    ]
    out = ensure_unique_rule_ids(rules, chunks)
    assert [r["rule_id"] for r in out] == ["REQ-01-1", "REQ-02-1"]


def test_synthetic_duplicate_req_ids_get_suffixes() -> None:
    chunks = [_chunk("a", "REQ-01"), _chunk("b", "REQ-02")]
    rules = [
        {
            "rule_id": "REQ-01",
            "requirement_id": "REQ-01",
            "source_requirement_chunk_ids": ["a"],
        },
        {
            "rule_id": "REQ-01",
            "requirement_id": "REQ-01",
            "source_requirement_chunk_ids": ["a"],
        },
        {
            "rule_id": "REQ-01",
            "requirement_id": "REQ-01",
            "source_requirement_chunk_ids": ["a"],
        },
        {
            "rule_id": "REQ-02",
            "requirement_id": "REQ-02",
            "source_requirement_chunk_ids": ["b"],
        },
        {
            "rule_id": "REQ-02",
            "requirement_id": "REQ-02",
            "source_requirement_chunk_ids": ["b"],
        },
        {
            "rule_id": "REQ-02",
            "requirement_id": "REQ-02",
            "source_requirement_chunk_ids": ["b"],
        },
    ]
    out = ensure_unique_rule_ids(rules, chunks)
    assert [r["rule_id"] for r in out] == [
        "REQ-01-1",
        "REQ-01-2",
        "REQ-01-3",
        "REQ-02-1",
        "REQ-02-2",
        "REQ-02-3",
    ]
    assert len({r["rule_id"] for r in out}) == 6


def test_document_native_single_id_unchanged() -> None:
    chunks = [
        _chunk("x", "FR-3.1", synthetic=False),
    ]
    rules = [
        {
            "rule_id": "FR-3.1",
            "requirement_id": "FR-3.1",
            "source_requirement_chunk_ids": ["x"],
        },
    ]
    out = ensure_unique_rule_ids(rules, chunks)
    assert out[0]["rule_id"] == "FR-3.1"


def test_document_native_duplicate_gets_suffix() -> None:
    chunks = [_chunk("x", "FR-2.4", synthetic=False)]
    rules = [
        {
            "rule_id": "FR-2.4",
            "source_requirement_chunk_ids": ["x"],
        },
        {
            "rule_id": "FR-2.4",
            "source_requirement_chunk_ids": ["x"],
        },
    ]
    out = ensure_unique_rule_ids(rules, chunks)
    assert [r["rule_id"] for r in out] == ["FR-2.4-1", "FR-2.4-2"]
