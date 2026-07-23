"""Tests for project-wide constraint indexing."""

from __future__ import annotations

from services.constraint_index import (
    build_project_constraint_index,
    case_mentions_field,
    constraints_for_case,
    constraints_for_rule,
    format_constraint_line,
    format_constraints_for_prompt,
)


def test_build_project_constraint_index_groups_by_field() -> None:
    rules = [
        {
            "rule_id": "FR-9",
            "constraints": [
                {"field": "price_threshold", "type": "range", "min": 0.0, "max": 1.0}
            ],
        }
    ]
    index = build_project_constraint_index(rules)
    assert len(index["price_threshold"]) == 1
    assert index["price_threshold"][0]["source_rule_id"] == "FR-9"


def test_constraints_for_case_includes_cross_rule_threshold() -> None:
    index = build_project_constraint_index(
        [
            {"rule_id": "FR-7", "constraints": []},
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
            },
        ]
    )
    case = {
        "title": "Threshold mode",
        "preconditions": "Set price threshold to 0.5 €/kWh.",
        "steps": ["Save threshold."],
        "expected_result": "Saved.",
    }
    constraints = constraints_for_case(
        case,
        linked_rule={"rule_id": "FR-7", "constraints": []},
        project_index=index,
    )
    assert len(constraints) == 1
    assert constraints[0]["source_rule_id"] == "FR-9"


def test_case_mentions_field_for_threshold_wording() -> None:
    assert case_mentions_field("Enter price threshold 0.5", "price_threshold")
    assert case_mentions_field("Enter $50 as the threshold.", "price_threshold")
    assert not case_mentions_field("Open the dashboard home page.", "price_threshold")
    assert not case_mentions_field(
        "Monthly availability meets the 99.5% minimum threshold.",
        "price_threshold",
    )


def test_constraints_for_case_skips_availability_minimum_threshold() -> None:
    """NFR-style availability % must not pull in FR-9 price_threshold limits."""
    index = build_project_constraint_index(
        [
            {"rule_id": "NFR-3", "constraints": []},
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
            },
        ]
    )
    case = {
        "title": "Verify scheduling service monthly availability meets 99.5% minimum",
        "preconditions": (
            "A completed monthly availability report shows downtime of 216 minutes, "
            "which equals exactly 99.5% availability."
        ),
        "steps": [
            "Open the monthly availability report.",
            "Compare the result against the 99.5% minimum requirement.",
        ],
        "expected_result": (
            "The scheduling service is reported as compliant because the monthly "
            "availability is exactly 99.5%, meeting the minimum threshold."
        ),
    }
    constraints = constraints_for_case(
        case,
        linked_rule={"rule_id": "NFR-3", "constraints": []},
        project_index=index,
    )
    assert constraints == []


def test_constraints_for_case_links_checkout_to_payment_discount_limits() -> None:
    """Generic e-commerce IDs: checkout case inherits payment discount constraints."""
    index = build_project_constraint_index(
        [
            {"rule_id": "REQ-CHECKOUT-1", "constraints": []},
            {
                "rule_id": "REQ-PAY-LIMITS",
                "constraints": [
                    {
                        "field": "coupon_discount",
                        "type": "range",
                        "min": 1.0,
                        "max": 50.0,
                        "unit": "%",
                    }
                ],
            },
        ]
    )
    case = {
        "title": "Apply coupon",
        "preconditions": "Shopper applies coupon discount 20% at checkout.",
        "steps": ["Submit order."],
        "expected_result": "Discount applied.",
    }
    constraints = constraints_for_case(
        case,
        linked_rule={"rule_id": "REQ-CHECKOUT-1", "constraints": []},
        project_index=index,
    )
    assert len(constraints) == 1
    assert constraints[0]["source_rule_id"] == "REQ-PAY-LIMITS"
    assert constraints[0]["field"] == "coupon_discount"


def test_constraints_for_rule_includes_linked_and_cross_rule() -> None:
    index = build_project_constraint_index(
        [
            {
                "rule_id": "REQ-THRESHOLD-1",
                "summary": "User sets price threshold for smart charging.",
                "constraints": [],
            },
            {
                "rule_id": "REQ-LIMITS-9",
                "constraints": [
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
                ],
            },
        ]
    )
    rule = {
        "rule_id": "REQ-THRESHOLD-1",
        "summary": "User sets price threshold for smart charging.",
        "detail": "System stores threshold for optimization.",
        "constraints": [],
    }
    constraints = constraints_for_rule(rule, project_index=index)
    assert len(constraints) == 2
    assert {c["source_rule_id"] for c in constraints} == {"REQ-LIMITS-9"}


def test_constraints_for_rule_skips_unrelated_cross_rule_fields() -> None:
    index = build_project_constraint_index(
        [
            {
                "rule_id": "REQ-DASH-1",
                "summary": "Open dashboard home page.",
                "constraints": [],
            },
            {
                "rule_id": "REQ-LIMITS-9",
                "constraints": [
                    {
                        "field": "price_threshold",
                        "type": "range",
                        "min": 0.0,
                        "max": 1.0,
                        "unit": "€/kWh",
                    }
                ],
            },
        ]
    )
    rule = {
        "rule_id": "REQ-DASH-1",
        "summary": "Open dashboard home page.",
        "detail": "",
        "constraints": [],
    }
    assert constraints_for_rule(rule, project_index=index) == []


def test_format_constraints_for_prompt() -> None:
    block = format_constraints_for_prompt(
        [
            {
                "field": "coupon_discount",
                "source_rule_id": "REQ-PAY-LIMITS",
                "type": "range",
                "min": 1.0,
                "max": 50.0,
                "unit": "%",
            }
        ]
    )
    assert "Applicable constraints" in block
    assert "coupon_discount (from REQ-PAY-LIMITS): 1–50 %" in block


def test_format_constraint_line_range_and_increment() -> None:
    range_line = format_constraint_line(
        {
            "field": "price_threshold",
            "source_rule_id": "REQ-LIMITS-9",
            "type": "range",
            "min": 0.0,
            "max": 1.0,
            "unit": "€/kWh",
        }
    )
    inc_line = format_constraint_line(
        {
            "field": "price_threshold",
            "source_rule_id": "REQ-LIMITS-9",
            "type": "increment",
            "step": 0.001,
            "unit": "€/kWh",
        }
    )
    assert "0–1 €/kWh" in range_line
    assert "increments of 0.001" in inc_line
