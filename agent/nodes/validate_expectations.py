"""Reject negative cases that expect failure for constraint-valid values."""

from __future__ import annotations

from typing import Any

from agent.case_value_context import (
    expects_rejection,
    field_constraints,
    value_satisfies_field_constraints,
    values_under_test_by_field,
    NEGATIVE_TEST_TYPES,
)
from agent.state import TestGenState
from services.constraint_index import build_project_constraint_index, constraints_for_case


def expectation_violations(
    case: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> list[str]:
    """Flag negatives/boundaries that claim rejection for a constraint-valid value."""
    test_type = str(case.get("test_type") or "").strip().lower()
    if test_type not in NEGATIVE_TEST_TYPES:
        return []
    if not expects_rejection(str(case.get("expected_result") or "")):
        return []

    values_by_field = values_under_test_by_field(case, constraints)
    if not values_by_field:
        return []

    issues: list[str] = []
    for field, values in values_by_field.items():
        if not field_constraints(constraints, field):
            continue
        for value in values:
            if value_satisfies_field_constraints(value, field, constraints):
                source_ids = sorted(
                    {
                        str(c.get("source_rule_id"))
                        for c in field_constraints(constraints, field)
                        if c.get("source_rule_id")
                    }
                )
                source_hint = f" (from {', '.join(source_ids)})" if source_ids else ""
                issues.append(
                    f"{field}{source_hint}: negative tests rejection of {value:g}, "
                    "but that value satisfies parsed constraints (non-violation)."
                )
    return issues


def validate_expectations(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    generated = list(state.get("generated_cases") or [])
    if not generated:
        return {
            "generated_cases": [],
            "expectation_rejected_cases": [],
            "expectation_violations": [],
            "expectation_stats": {
                "input_cases": 0,
                "valid_cases": 0,
                "rejected_cases": 0,
            },
            "current_step": "validate_expectations",
        }

    rule_by_id = {str(r.get("rule_id")): r for r in rules if r.get("rule_id")}
    project_index = build_project_constraint_index(rules)
    valid_cases: list[dict[str, Any]] = []
    rejected_cases: list[dict[str, Any]] = []
    violations_summary: list[dict[str, Any]] = []

    for case in generated:
        rid = str(case.get("linked_requirement") or "")
        linked_rule = rule_by_id.get(rid) or {}
        constraints = constraints_for_case(
            case,
            linked_rule=linked_rule,
            project_index=project_index,
        )
        if not constraints:
            valid_cases.append(case)
            continue

        violations = expectation_violations(case, constraints)
        if violations:
            rejected = dict(case)
            rejected["expectation_violations"] = violations
            rejected_cases.append(rejected)
            violations_summary.append(
                {
                    "linked_requirement": rid,
                    "title": case.get("title"),
                    "violations": violations,
                }
            )
        else:
            valid_cases.append(case)

    stats = {
        "input_cases": len(generated),
        "valid_cases": len(valid_cases),
        "rejected_cases": len(rejected_cases),
    }

    reasoning = state.get("reasoning") or ""
    if rejected_cases:
        reasoning = (
            reasoning
            + "\nExpectation validation rejected "
            + f"{len(rejected_cases)} negative/boundary case(s) that test non-violations."
        ).strip()

    return {
        "generated_cases": valid_cases,
        "expectation_rejected_cases": rejected_cases,
        "expectation_violations": violations_summary,
        "expectation_stats": stats,
        "reasoning": reasoning,
        "current_step": "validate_expectations",
    }
