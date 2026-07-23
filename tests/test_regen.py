"""Tests for incomplete-requirement regeneration helpers."""

from __future__ import annotations

from agent.regen import (
    build_regen_feedback,
    can_regenerate_incomplete,
    incomplete_rule_ids,
    incomplete_summary,
    prepare_incomplete_regen_state,
)


def test_incomplete_rule_ids_from_report() -> None:
    report = {
        "per_rule": [
            {"rule_id": "REQ-A", "coverage_status": "fully_covered"},
            {"rule_id": "REQ-B", "coverage_status": "partially_covered"},
            {"rule_id": "REQ-C", "coverage_status": "not_covered"},
            {"rule_id": "REQ-D", "coverage_status": "blocked"},
        ]
    }
    assert incomplete_rule_ids(report) == ["REQ-B", "REQ-C"]


def test_build_regen_feedback_collects_rejection_notes() -> None:
    last_run = {
        "invalid_cases": [
            {
                "linked_requirement": "REQ-B",
                "constraint_violations": ["price_threshold: wrong currency ($)"],
            }
        ],
        "oracle_rejected_cases": [
            {
                "linked_requirement": "REQ-C",
                "oracle_findings": ["Unexecutable - missing concrete data."],
            }
        ],
        "expectation_rejected_cases": [],
        "spec_fact_rejected_cases": [
            {
                "linked_requirement": "REQ-B",
                "spec_fact_violations": [
                    "Quiet hours end 06:00 conflicts with specification (known end(s): 07:00)."
                ],
            }
        ],
    }
    feedback = build_regen_feedback(last_run)
    assert "REQ-B" in feedback
    assert any("Constraint" in n for n in feedback["REQ-B"])
    assert any("Spec fact" in n for n in feedback["REQ-B"])
    assert "REQ-C" in feedback
    assert any("Quality" in n for n in feedback["REQ-C"])


def test_prepare_incomplete_regen_state_targets_gaps_only() -> None:
    last_run = {
        "project_id": "proj-1",
        "document_name": "spec.txt",
        "exhaustiveness_level": "smoke",
        "atomic_rules": [
            {"rule_id": "REQ-A", "status": "active"},
            {"rule_id": "REQ-B", "status": "active"},
        ],
        "validated_cases": [
            {
                "title": "A positive",
                "linked_requirement": "REQ-A",
                "test_type": "positive",
                "testcase_id": "TC_REQ-A_POS_01",
            },
            {
                "title": "A negative",
                "linked_requirement": "REQ-A",
                "test_type": "negative",
                "testcase_id": "TC_REQ-A_NEG_01",
            },
            {
                "title": "B positive only",
                "linked_requirement": "REQ-B",
                "test_type": "positive",
                "testcase_id": "TC_REQ-B_POS_01",
            },
        ],
        "coverage_gaps": [
            {
                "rule_id": "REQ-B",
                "test_type": "negative",
                "needed": 1,
                "required": 1,
                "have": 0,
            }
        ],
        "coverage_report": {
            "rules_partially_covered": 1,
            "rules_not_covered": 0,
            "per_rule": [
                {"rule_id": "REQ-A", "coverage_status": "fully_covered"},
                {"rule_id": "REQ-B", "coverage_status": "partially_covered"},
            ],
        },
        "invalid_cases": [
            {
                "linked_requirement": "REQ-B",
                "constraint_violations": ["coupon_discount: value 75 violates range"],
            }
        ],
        "requirement_chunks": [{"id": "c1"}],
        "retrieved_bugs": [],
        "retrieved_tcs": [],
    }
    assert can_regenerate_incomplete(last_run)
    summary = incomplete_summary(last_run)
    assert summary["rule_count"] == 1
    assert summary["rule_ids"] == ["REQ-B"]

    state = prepare_incomplete_regen_state(last_run)
    assert state["regen_mode"] is True
    assert state["review_round"] >= 1
    assert state["coverage_gaps"][0]["rule_id"] == "REQ-B"
    assert all(c.get("_already_persisted") for c in state["generated_cases"])
    assert "REQ-B" in (state.get("regen_feedback") or {})
    assert "REQ-A" not in (state.get("regen_feedback") or {})


def test_can_regenerate_incomplete_false_when_fully_covered() -> None:
    last_run = {
        "atomic_rules": [{"rule_id": "REQ-A", "status": "active"}],
        "coverage_gaps": [],
        "coverage_report": {
            "per_rule": [{"rule_id": "REQ-A", "coverage_status": "fully_covered"}],
            "rules_partially_covered": 0,
            "rules_not_covered": 0,
        },
        "validated_cases": [
            {"linked_requirement": "REQ-A", "test_type": "positive"},
            {"linked_requirement": "REQ-A", "test_type": "negative"},
        ],
    }
    assert not can_regenerate_incomplete(last_run)
