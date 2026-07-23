"""Tests for cross-requirement scenario dedup (shared error / failure paths)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.cross_req_dedup import (
    cross_requirement_scenario_dedup,
    extract_error_codes,
)
from agent.nodes.validate import validate_dedup


def test_extract_error_codes_normalizes_variants() -> None:
    assert extract_error_codes("Shows E-102 and ERR_102") == {"E-102"}
    assert extract_error_codes("error code ERROR-55") == {"E-55"}


def test_cross_req_dedup_shared_error_code() -> None:
    cases = [
        {
            "title": "FR-6 window too short shows E-102",
            "linked_requirement": "FR-6",
            "test_type": "negative",
            "steps": ["Attempt schedule with 5h runtime in 4h window."],
            "expected_result": "System shows error E-102 and does not schedule.",
        },
        {
            "title": "FR-5 NEG_02 runtime cannot fit",
            "linked_requirement": "FR-5",
            "test_type": "negative",
            "steps": ["Provide a 5-hour runtime in a 4-hour window."],
            "expected_result": "Schedule fails with E-102 because runtime cannot fit.",
        },
    ]
    kept, dups = cross_requirement_scenario_dedup(cases)
    assert len(kept) == 1
    assert kept[0]["linked_requirement"] == "FR-6"
    assert len(dups) == 1
    assert dups[0]["linked_requirement"] == "FR-5"
    assert dups[0]["duplicate_reason"] == "cross_requirement_scenario_duplicate"
    assert dups[0]["similar_to_requirement"] == "FR-6"
    assert "E-102" in str(dups[0].get("scenario_match") or "")


def test_cross_req_dedup_keeps_same_requirement_error_twice() -> None:
    """Same requirement may mention E-102 twice — not a cross-req duplicate."""
    cases = [
        {
            "title": "Neg A",
            "linked_requirement": "FR-6",
            "test_type": "negative",
            "expected_result": "Error E-102 for window A.",
            "steps": ["a"],
        },
        {
            "title": "Neg B",
            "linked_requirement": "FR-6",
            "test_type": "negative",
            "expected_result": "Error E-102 for window B.",
            "steps": ["b"],
        },
    ]
    kept, dups = cross_requirement_scenario_dedup(cases)
    assert len(kept) == 2
    assert dups == []


def test_cross_req_dedup_identical_specific_failure_expected() -> None:
    expected = (
        "The 5-hour runtime cannot fit within the 4-hour scheduling window "
        "and no schedule is created."
    )
    cases = [
        {
            "title": "FR-6 cannot fit",
            "linked_requirement": "FR-6",
            "test_type": "negative",
            "steps": ["Try schedule."],
            "expected_result": expected,
        },
        {
            "title": "FR-5 cannot fit duplicate",
            "linked_requirement": "FR-5",
            "test_type": "negative",
            "steps": ["Try schedule again."],
            "expected_result": expected,
        },
    ]
    kept, dups = cross_requirement_scenario_dedup(cases)
    assert len(kept) == 1
    assert len(dups) == 1
    assert "identical failure" in str(dups[0].get("scenario_match") or "")


def test_cross_req_dedup_ignores_generic_rejection() -> None:
    cases = [
        {
            "title": "Reject bad coupon",
            "linked_requirement": "REQ-A",
            "test_type": "negative",
            "steps": ["Enter bad code."],
            "expected_result": "The input is rejected with an error message.",
        },
        {
            "title": "Reject bad threshold",
            "linked_requirement": "REQ-B",
            "test_type": "negative",
            "steps": ["Enter bad threshold."],
            "expected_result": "The input is rejected with an error message.",
        },
    ]
    kept, dups = cross_requirement_scenario_dedup(cases)
    assert len(kept) == 2
    assert dups == []


@patch("agent.nodes.validate.embed_texts", return_value=[[0.1], [0.9]])
@patch("agent.nodes.validate.get_embeddings_model")
def test_validate_dedup_reports_cross_req_stat(
    _mock_model: MagicMock,
    _mock_embed: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_test_cases.return_value = []
    state = {
        "project_id": "p1",
        "generated_cases": [
            {
                "title": "FR-6 E-102",
                "linked_requirement": "FR-6",
                "test_type": "negative",
                "steps": ["Step one"],
                "expected_result": "Shows E-102.",
            },
            {
                "title": "FR-5 E-102 again",
                "linked_requirement": "FR-5",
                "test_type": "negative",
                "steps": ["Step two"],
                "expected_result": "Also shows E-102.",
            },
        ],
    }
    out = validate_dedup(state, repo)
    assert out["batch_dedup_stats"]["removed_cross_req"] == 1
    assert len(out["validated_cases"]) == 1
    assert out["duplicates"][0]["duplicate_reason"] == (
        "cross_requirement_scenario_duplicate"
    )
