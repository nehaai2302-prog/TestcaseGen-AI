"""Tests for contradiction blocking helpers."""

from __future__ import annotations

from agent.ambiguity import (
    STATUS_REQUIRES_CLARIFICATION,
    contradiction_blocked_ids,
    generatable_rules,
    mark_rule_statuses,
)
from agent.coverage import build_coverage_report, compute_gaps


def test_contradiction_blocks_both_related_rules() -> None:
    contradictions = [
        {
            "rule_id": "FR-7",
            "issue": "Contradicts FR-8 at threshold",
            "related_rule_ids": ["FR-8"],
        }
    ]
    assert contradiction_blocked_ids(contradictions) == {"FR-7", "FR-8"}


def test_mark_rule_statuses_sets_blocked() -> None:
    rules = [
        {"rule_id": "FR-7", "summary": "A"},
        {"rule_id": "FR-8", "summary": "B"},
        {"rule_id": "FR-9", "summary": "C"},
    ]
    contradictions = [
        {"rule_id": "FR-7", "related_rule_ids": ["FR-8"], "issue": "conflict"}
    ]
    marked = mark_rule_statuses(rules, contradictions)
    statuses = {r["rule_id"]: r["status"] for r in marked}
    assert statuses["FR-7"] == STATUS_REQUIRES_CLARIFICATION
    assert statuses["FR-8"] == STATUS_REQUIRES_CLARIFICATION
    assert statuses["FR-9"] == "active"
    assert len(generatable_rules(marked)) == 1


def test_coverage_skips_blocked_rules() -> None:
    rules = [
        {"rule_id": "FR-7", "status": STATUS_REQUIRES_CLARIFICATION},
        {"rule_id": "FR-9", "status": "active"},
    ]
    gaps = compute_gaps(rules, [], "standard")
    assert all(g["rule_id"] == "FR-9" for g in gaps)
    assert not any(g["rule_id"] == "FR-7" for g in gaps)
    report = build_coverage_report(rules, [], "standard")
    assert report["blocked_rule_count"] == 1
    assert report["generatable_rule_count"] == 1
    assert report["rules_not_covered"] == 1
    assert report["rules_partially_covered"] == 0
    assert report["rules_fully_covered"] == 0


def test_coverage_fully_partial_and_not_covered() -> None:
    rules = [
        {"rule_id": "REQ-A", "status": "active"},
        {"rule_id": "REQ-B", "status": "active"},
        {"rule_id": "REQ-C", "status": "active"},
        {"rule_id": "REQ-D", "status": STATUS_REQUIRES_CLARIFICATION},
    ]
    # smoke: 1 positive + 1 negative per rule
    cases = [
        {"linked_requirement": "REQ-A", "test_type": "positive"},
        {"linked_requirement": "REQ-A", "test_type": "negative"},
        {"linked_requirement": "REQ-B", "test_type": "positive"},
    ]
    report = build_coverage_report(rules, cases, "smoke")
    assert report["rules_fully_covered"] == 1
    assert report["rules_partially_covered"] == 1
    assert report["rules_not_covered"] == 1
    assert report["blocked_rule_count"] == 1
    by_id = {row["rule_id"]: row["coverage_status"] for row in report["per_rule"]}
    assert by_id["REQ-A"] == "fully_covered"
    assert by_id["REQ-B"] == "partially_covered"
    assert by_id["REQ-C"] == "not_covered"
    assert by_id["REQ-D"] == "blocked"
