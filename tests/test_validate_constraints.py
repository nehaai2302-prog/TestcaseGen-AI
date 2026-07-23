"""Tests for validating generated cases against parsed constraints."""

from __future__ import annotations

from agent.nodes.validate_constraints import validate_constraints


def test_validate_constraints_rejects_wrong_currency_and_range() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-9",
                "constraints": [
                    {
                        "field": "price_threshold",
                        "type": "range",
                        "min": 0.0,
                        "max": 1.0,
                        "unit": "€/kWh",
                    }
                ],
            }
        ],
        "generated_cases": [
            {
                "title": "Use threshold $50",
                "linked_requirement": "FR-9",
                "preconditions": "Set price threshold to $50.",
                "steps": ["Enter $50 as the threshold."],
                "expected_result": "Threshold is accepted.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["invalid_cases"] == 1
    assert len(out["generated_cases"]) == 0
    issues = out["invalid_cases"][0]["constraint_violations"]
    assert any("wrong currency" in issue for issue in issues)


def test_validate_constraints_rejects_invalid_increment() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-10",
                "constraints": [
                    {
                        "field": "price_threshold",
                        "type": "increment",
                        "step": 0.001,
                        "unit": "€/kWh",
                    }
                ],
            }
        ],
        "generated_cases": [
            {
                "title": "Set threshold 0.0025 €/kWh",
                "linked_requirement": "FR-10",
                "preconditions": "Use threshold 0.0025 €/kWh.",
                "steps": ["Enter 0.0025 €/kWh."],
                "expected_result": "Threshold saved.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["invalid_cases"] == 1
    assert any(
        "valid increment" in issue
        for issue in out["invalid_cases"][0]["constraint_violations"]
    )


def test_validate_constraints_passes_valid_case() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-11",
                "constraints": [
                    {
                        "field": "duration",
                        "type": "int_range",
                        "min": 1,
                        "max": 8,
                        "unit": "hours",
                    }
                ],
            }
        ],
        "generated_cases": [
            {
                "title": "Schedule 4-hour run",
                "linked_requirement": "FR-11",
                "preconditions": "A 4 hours run is allowed.",
                "steps": ["Select duration 4 hours."],
                "expected_result": "A 4 hours schedule is accepted.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert len(out["generated_cases"]) == 1
    assert out["invalid_cases"] == []


FR9_CONSTRAINTS = [
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


def test_cross_rule_fr7_case_rejects_dollar_threshold_from_fr9() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-7",
                "summary": "Threshold mode scheduling",
                "detail": "Run when spot price is below the user-defined price threshold.",
                "constraints": [],
            },
            {
                "rule_id": "FR-9",
                "summary": "Price threshold range",
                "detail": "Price threshold 0.000-1.000 €/kWh in increments of 0.001.",
                "constraints": FR9_CONSTRAINTS,
            },
        ],
        "generated_cases": [
            {
                "title": "Set threshold in threshold mode",
                "linked_requirement": "FR-7",
                "preconditions": "Appliance uses threshold mode.",
                "steps": ["Enter price threshold $50.", "Save settings."],
                "expected_result": "Threshold is rejected or not saved.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["invalid_cases"] == 1
    issues = out["invalid_cases"][0]["constraint_violations"]
    assert any("from FR-9" in issue for issue in issues)
    assert any("wrong currency" in issue or "violates range" in issue for issue in issues)


def test_cross_rule_fr7_case_accepts_valid_euro_threshold() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-7",
                "summary": "Threshold mode scheduling",
                "detail": "Run when spot price is below the user-defined price threshold.",
                "constraints": [],
            },
            {
                "rule_id": "FR-9",
                "summary": "Price threshold range",
                "constraints": FR9_CONSTRAINTS,
            },
        ],
        "generated_cases": [
            {
                "title": "Valid threshold for threshold mode",
                "linked_requirement": "FR-7",
                "preconditions": "Appliance uses threshold mode.",
                "steps": ["Enter price threshold 0.500 €/kWh.", "Save settings."],
                "expected_result": "Threshold 0.500 €/kWh is saved.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_cross_rule_does_not_apply_unrelated_runtime_constraints() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-6",
                "constraints": [
                    {
                        "field": "runtime",
                        "type": "int_range",
                        "min": 1,
                        "max": 8,
                        "unit": "hours",
                    }
                ],
            },
            {
                "rule_id": "FR-9",
                "constraints": FR9_CONSTRAINTS,
            },
        ],
        "generated_cases": [
            {
                "title": "Save valid threshold",
                "linked_requirement": "FR-9",
                "preconditions": "Enter threshold 0.250 €/kWh.",
                "steps": ["Save the price threshold."],
                "expected_result": "Threshold saved.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1


# --- Generic multi-spec fixtures (not EcoCharge) ---

CHECKOUT_DISCOUNT_LIMITS = [
    {
        "field": "coupon_discount",
        "type": "range",
        "min": 1.0,
        "max": 50.0,
        "unit": "%",
    },
]


def test_cross_rule_checkout_case_rejects_out_of_range_discount() -> None:
    """Checkout negative with 75% expects rejection — valid negative, not constraint-rejected."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-CHECKOUT-1",
                "summary": "Apply coupon at checkout",
                "detail": "The shopper may apply one coupon code during checkout.",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PAY-LIMITS",
                "summary": "Coupon discount bounds",
                "detail": "Coupon discount 1-50 percent.",
                "constraints": CHECKOUT_DISCOUNT_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Apply high coupon on checkout",
                "linked_requirement": "REQ-CHECKOUT-1",
                "test_type": "negative",
                "preconditions": "Cart total is 120 USD.",
                "steps": [
                    "Enter coupon code SAVEBIG with discount 75%.",
                    "Submit checkout.",
                ],
                "expected_result": "Discount is rejected because it exceeds the allowed maximum.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_positive_checkout_rejects_out_of_range_discount_on_save() -> None:
    """Positive-style case that saves 75% must still be constraint-rejected."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-CHECKOUT-1",
                "summary": "Apply coupon at checkout",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PAY-LIMITS",
                "summary": "Coupon discount bounds",
                "constraints": CHECKOUT_DISCOUNT_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Apply high coupon on checkout",
                "linked_requirement": "REQ-CHECKOUT-1",
                "test_type": "positive",
                "preconditions": "Cart total is 120 USD.",
                "steps": [
                    "Enter coupon code SAVEBIG with discount 75%.",
                    "Submit checkout.",
                ],
                "expected_result": "Checkout applies a 75% coupon discount.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["invalid_cases"] == 1
    issues = out["invalid_cases"][0]["constraint_violations"]
    assert any("from REQ-PAY-LIMITS" in issue for issue in issues)
    assert any("violates range" in issue for issue in issues)


def test_cross_rule_checkout_case_accepts_valid_discount() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-CHECKOUT-1",
                "summary": "Apply coupon at checkout",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PAY-LIMITS",
                "summary": "Coupon discount bounds",
                "constraints": CHECKOUT_DISCOUNT_LIMITS,
            },
        ],
        "generated_cases": [
            {
                "title": "Apply valid coupon",
                "linked_requirement": "REQ-CHECKOUT-1",
                "preconditions": "Cart total is 80 USD.",
                "steps": ["Enter coupon code SAVE10 with discount 10%.", "Submit checkout."],
                "expected_result": "Checkout total reflects a 10% coupon discount.",
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_constraint_passes_negative_entering_above_max_threshold() -> None:
    """Regression: 1.001 negatives that expect rejection must not be constraint-rejected."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": FR9_CONSTRAINTS,
            }
        ],
        "generated_cases": [
            {
                "title": "Reject price threshold above the maximum allowed value",
                "linked_requirement": "REQ-PRICE-LIMITS",
                "test_type": "negative",
                "steps": [
                    "Open Quiet Hours settings.",
                    "Enter a price threshold of 1.001 €/kWh.",
                    "Attempt to save the configuration.",
                ],
                "expected_result": (
                    "The system rejects 1.001 €/kWh and shows a validation error."
                ),
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_constraint_passes_positive_spot_price_display_rounding() -> None:
    """Regression: spot price 0.1234 display test is not threshold configuration."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-DISPLAY-1",
                "summary": "Display spot price rounded to 3 decimals",
                "constraints": [],
            },
            {
                "rule_id": "REQ-PRICE-LIMITS",
                "constraints": FR9_CONSTRAINTS,
            },
        ],
        "generated_cases": [
            {
                "title": "Display spot price rounded to 3 decimals for a mid-range value",
                "linked_requirement": "REQ-DISPLAY-1",
                "test_type": "positive",
                "preconditions": (
                    "A spot price value of 0.1234 €/kWh is available to be shown."
                ),
                "steps": [
                    "Open the Automatic Scheduling screen that shows the current spot price.",
                    "Locate the displayed spot price value.",
                    "Compare the displayed value against the underlying value 0.1234 €/kWh.",
                ],
                "expected_result": (
                    "The spot price is displayed as 0.123 €/kWh, rounded to 3 decimal places."
                ),
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_constraint_passes_availability_sla_not_price_threshold() -> None:
    """Regression: 99.5% availability must not be checked against €/kWh price_threshold."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "NFR-3",
                "summary": "Scheduling service monthly availability",
                "detail": "Monthly availability shall be at least 99.5%.",
                "constraints": [],
            },
            {
                "rule_id": "FR-9",
                "summary": "Price threshold range",
                "detail": "Price threshold 0.000-1.000 €/kWh.",
                "constraints": FR9_CONSTRAINTS,
            },
        ],
        "generated_cases": [
            {
                "title": "Verify scheduling service monthly availability meets 99.5% minimum",
                "linked_requirement": "NFR-3",
                "test_type": "positive",
                "preconditions": (
                    "A completed monthly availability report is available for the "
                    "scheduling service showing total scheduled uptime and downtime "
                    "for the month. Use a sample month with 30 days (43,200 minutes) "
                    "and recorded downtime of 216 minutes, which equals exactly 99.5% "
                    "availability."
                ),
                "steps": [
                    "Open the monthly availability report for the scheduling service.",
                    "Locate the total scheduled uptime and total downtime values.",
                    "Calculate or verify the reported availability percentage.",
                    "Compare the result against the 99.5% minimum requirement.",
                ],
                "expected_result": (
                    "The scheduling service is reported as compliant because the "
                    "monthly availability is exactly 99.5%, meeting the minimum threshold."
                ),
            }
        ],
    }
    out = validate_constraints(state)
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["invalid_cases"] == []


def test_validate_format_hh00_rejects_non_hour_times_without_crash() -> None:
    from agent.nodes.validate_constraints import _validate_format

    issues = _validate_format(
        "Set quiet hours from 22:30 to 07:15",
        {"type": "format", "field": "quiet_hours", "pattern": "hh:00"},
    )
    assert any("22:30" in i for i in issues)
    assert any("07:15" in i for i in issues)


def test_validate_constraints_keeps_already_persisted_despite_violations() -> None:
    """Regen must not drop saved cases when re-running constraint checks."""
    bad_case = {
        "title": "Use threshold $50",
        "linked_requirement": "FR-9",
        "preconditions": "Set price threshold to $50.",
        "steps": ["Enter $50 as the threshold."],
        "expected_result": "Threshold is accepted.",
    }
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-9",
                "constraints": [
                    {
                        "field": "price_threshold",
                        "type": "range",
                        "min": 0.0,
                        "max": 1.0,
                        "unit": "€/kWh",
                    }
                ],
            }
        ],
        "generated_cases": [
            {**bad_case, "title": "Saved bad case", "_already_persisted": True},
            {**bad_case, "title": "Fresh bad draft"},
        ],
        "reasoning": "",
    }
    out = validate_constraints(state)
    kept_titles = {c.get("title") for c in out["generated_cases"]}
    assert "Saved bad case" in kept_titles
    assert "Fresh bad draft" not in kept_titles
    assert out["constraint_stats"]["valid_cases"] == 1
    assert out["constraint_stats"]["invalid_cases"] == 1

