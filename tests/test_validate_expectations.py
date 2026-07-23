"""Tests for negative/boundary expectation validation (5.2b)."""

from __future__ import annotations

from agent.nodes.validate_expectations import (
    expectation_violations,
    validate_expectations,
)

PRICE_LIMITS = [
    {
        "field": "price_threshold",
        "type": "range",
        "min": 0.0,
        "max": 1.0,
        "unit": "€/kWh",
    },
    {
        "field": "price_threshold",
        "type": "increment",
        "step": 0.001,
        "unit": "€/kWh",
    },
]


def test_rejects_negative_that_expects_rejection_of_valid_increment() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            }
        ],
        "generated_cases": [
            {
                "title": "Reject valid threshold step",
                "linked_requirement": "REQ-PRICE-LIMITS",
                "test_type": "negative",
                "preconditions": "User opens price threshold settings.",
                "steps": ["Enter price threshold 0.002 €/kWh.", "Save."],
                "expected_result": "Value is rejected as invalid.",
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["rejected_cases"] == 1
    assert len(out["generated_cases"]) == 0
    issues = out["expectation_rejected_cases"][0]["expectation_violations"]
    assert any("non-violation" in issue for issue in issues)


def test_passes_negative_that_expects_rejection_of_out_of_range_value() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            }
        ],
        "generated_cases": [
            {
                "title": "Reject above-max threshold",
                "linked_requirement": "REQ-PRICE-LIMITS",
                "test_type": "negative",
                "preconditions": "User opens price threshold settings.",
                "steps": ["Enter price threshold 1.001 €/kWh.", "Save."],
                "expected_result": "Value is rejected as invalid.",
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["valid_cases"] == 1
    assert out["expectation_rejected_cases"] == []


def test_skips_positive_cases_even_when_expectation_mentions_rejection() -> None:
    case = {
        "title": "Valid threshold saved",
        "linked_requirement": "REQ-PRICE-LIMITS",
        "test_type": "positive",
        "steps": ["Enter price threshold 0.500 €/kWh.", "Save."],
        "expected_result": "Invalid values are rejected; 0.500 €/kWh is saved.",
    }
    violations = expectation_violations(case, PRICE_LIMITS)
    assert violations == []


def test_cross_rule_negative_valid_value_flagged() -> None:
    """Threshold rule inherits limits from pricing rule — still checks expectations."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-THRESHOLD-1",
                "summary": "Threshold mode scheduling",
                "detail": "Run when spot price is below the user-defined price threshold.",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Reject valid threshold in threshold mode",
                "linked_requirement": "REQ-THRESHOLD-1",
                "test_type": "negative",
                "preconditions": "Appliance uses threshold mode.",
                "steps": ["Enter price threshold 0.002 €/kWh.", "Save settings."],
                "expected_result": "Threshold is rejected and not saved.",
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["rejected_cases"] == 1
    issues = out["expectation_rejected_cases"][0]["expectation_violations"]
    assert any("REQ-PRICE-LIMITS" in issue for issue in issues)


def test_generic_coupon_negative_with_valid_discount_rejected() -> None:
    limits = [
        {
            "field": "coupon_discount",
            "type": "range",
            "min": 1.0,
            "max": 50.0,
            "unit": "%",
        }
    ]
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-CHECKOUT-1",
                "summary": "Apply coupon at checkout",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PAY-LIMITS",
                "constraints": limits,
            },
        ],
        "generated_cases": [
            {
                "title": "Reject valid coupon percent",
                "linked_requirement": "REQ-CHECKOUT-1",
                "test_type": "negative",
                "steps": ["Enter coupon discount 10% at checkout.", "Submit."],
                "expected_result": "Discount is rejected as invalid.",
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["rejected_cases"] == 1


def test_skips_runtime_scheduling_case_that_only_cites_price_range_in_setup() -> None:
    """Regression: do not flag 0/1 from '0–1 €/kWh' when steps test runtime window fit."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-RUNTIME-1",
                "summary": "Cheapest-hours scheduling",
                "detail": "Select contiguous cheapest blocks within runtime.",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Do not select a block when runtime exceeds the scheduling window",
                "linked_requirement": "REQ-RUNTIME-1",
                "test_type": "negative",
                "preconditions": (
                    "Runtime is 7 hours. The scheduling window has 6 hourly prices "
                    "within the allowed 0–1 €/kWh range."
                ),
                "steps": [
                    "Set runtime to 7 hours.",
                    "Load a scheduling window containing only 6 hourly prices.",
                    "Trigger schedule calculation.",
                ],
                "expected_result": (
                    "The system does not select any schedule and shows a validation error."
                ),
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["valid_cases"] == 1
    assert out["expectation_rejected_cases"] == []


def test_passes_negative_entering_below_min_threshold() -> None:
    """Regression: -0.001 under test must not be confused with 0/0.001 in expected bounds text."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            }
        ],
        "generated_cases": [
            {
                "title": "Reject price threshold below the minimum",
                "linked_requirement": "REQ-PRICE-LIMITS",
                "test_type": "negative",
                "steps": [
                    "Open Quiet Hours settings.",
                    "In the price threshold field, enter -0.001 €/kWh.",
                    "Attempt to save.",
                ],
                "expected_result": (
                    "The system rejects -0.001 €/kWh and shows an error that the value "
                    "must be between 0.000 and 1.000 €/kWh."
                ),
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["valid_cases"] == 1
    assert out["expectation_rejected_cases"] == []


def test_boundary_manual_start_at_max_spot_price_not_flagged() -> None:
    """Regression: upper-boundary success ('not blocked') is not invalid negative expectation."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-CONTROL-1",
                "summary": "Manual start when spot price at boundary",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": PRICE_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Manual start remains available when spot price is 1.000 €/kWh",
                "linked_requirement": "REQ-CONTROL-1",
                "test_type": "boundary",
                "preconditions": (
                    "Appliance is stopped. Current spot price is 1.000 €/kWh."
                ),
                "steps": [
                    "Open the appliance detail view.",
                    "Set or confirm the spot price display/context to 1.000 €/kWh.",
                    "Click the manual Start control.",
                ],
                "expected_result": (
                    "The appliance starts successfully at exactly 1.000 €/kWh; "
                    "manual start is not blocked at the upper boundary price threshold."
                ),
            }
        ],
    }
    out = validate_expectations(state)
    assert out["expectation_stats"]["valid_cases"] == 1
    assert out["expectation_rejected_cases"] == []
