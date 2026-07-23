"""Tests for constraint-aware generation prompt blocks."""

from __future__ import annotations

from agent.nodes._batch_generate import _rule_block
from services.constraint_index import build_project_constraint_index


def test_rule_block_includes_applicable_constraints() -> None:
    rules = [
        {
            "rule_id": "REQ-CHECKOUT-1",
            "summary": "Apply coupon discount at checkout.",
            "detail": "Shopper enters coupon discount before payment.",
            "screen": "Checkout",
            "constraints": [],
            "source_requirement_chunk_ids": ["chunk-1"],
        },
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
    project_index = build_project_constraint_index(rules)
    block = _rule_block(
        rules[0],
        {"positive": 1, "negative": 1},
        {},
        {},
        project_index,
    )
    assert "Applicable constraints" in block
    assert "coupon_discount (from REQ-PAY-LIMITS): 1–50 %" in block


def test_rule_block_omits_constraints_when_none_apply() -> None:
    rules = [
        {
            "rule_id": "REQ-DASH-1",
            "summary": "Open dashboard home page.",
            "detail": "",
            "screen": "Dashboard",
            "constraints": [],
            "source_requirement_chunk_ids": [],
        }
    ]
    project_index = build_project_constraint_index(rules)
    block = _rule_block(rules[0], {"positive": 1}, {}, {}, project_index)
    assert "Applicable constraints" not in block
