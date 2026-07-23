"""Tests for spec-agnostic oracle validation."""

from __future__ import annotations

from agent.nodes.oracle_validate import oracle_validate


def _fr9_rule() -> dict:
    return {
        "rule_id": "FR-9",
        "summary": "Price threshold range and increment",
        "detail": "Price threshold must be 0.000-1.000 €/kWh in increments of 0.001.",
        "execution_profile": "config",
        "constraints": [
            {"type": "range", "min": 0.0, "max": 1.0, "unit": "€/kWh"},
            {"type": "increment", "step": 0.001, "unit": "€/kWh"},
        ],
    }


def test_oracle_accepts_config_case_even_when_ui_mentions_quiet_hours() -> None:
    state = {
        "atomic_rules": [_fr9_rule()],
        "generated_cases": [
            {
                "title": "Save valid price threshold on Quiet Hours settings",
                "linked_requirement": "FR-9",
                "preconditions": "User is on Quiet Hours settings.",
                "steps": [
                    "Enter price threshold 0.500 €/kWh.",
                    "Save the settings.",
                ],
                "expected_result": "Threshold 0.500 €/kWh is accepted and saved.",
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1
    assert out["oracle_rejected_cases"] == []


def test_oracle_accepts_coupon_length_cases_even_if_labeled_comparison() -> None:
    """Length-limit requirements must not get comparison substance rules."""
    state = {
        "atomic_rules": [
            {
                "rule_id": "REQ-COUPON-1",
                "summary": "Coupon input maximum length",
                "detail": (
                    "The coupon input field shall accept a maximum of 10 characters. "
                    "Longer values must be blocked."
                ),
                "execution_profile": "comparison",
            }
        ],
        "generated_cases": [
            {
                "title": "Coupon input accepts exactly 10 characters",
                "linked_requirement": "REQ-COUPON-1",
                "test_type": "positive",
                "preconditions": "Open the coupon entry UI where the input field is available.",
                "steps": [
                    "Click the coupon input field.",
                    "Enter the 10-character value 'ABCDEFGHIJ'.",
                    "Move focus away from the field or attempt to submit the form.",
                ],
                "expected_result": (
                    "The full 10-character value remains in the input field and is "
                    "accepted without validation error."
                ),
            },
            {
                "title": "Coupon input blocks entry longer than 10 characters",
                "linked_requirement": "REQ-COUPON-1",
                "test_type": "negative",
                "preconditions": "Open the coupon entry UI where the input field is available.",
                "steps": [
                    "Click the coupon input field.",
                    "Enter the 11-character value 'ABCDEFGHIJK'.",
                    "Attempt to save or submit the form.",
                ],
                "expected_result": (
                    "The input field does not retain more than 10 characters; the 11th "
                    "character is prevented or removed."
                ),
            },
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 2
    assert out["oracle_rejected_cases"] == []


def test_oracle_rejects_scheduling_case_without_times() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-11",
                "summary": "Noisy appliance outside quiet hours",
                "detail": "Noisy appliance shall not run during quiet hours.",
                "execution_profile": "scheduling",
            }
        ],
        "generated_cases": [
            {
                "title": "Noisy appliance outside quiet hours",
                "linked_requirement": "FR-11",
                "preconditions": "Quiet hours are configured.",
                "steps": [
                    "Mark the appliance as noisy.",
                    "Trigger schedule generation for the appliance.",
                ],
                "expected_result": "The appliance is not scheduled during quiet hours.",
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["rejected_cases"] == 1
    assert "scheduling case is missing concrete times" in (
        out["oracle_rejected_cases"][0]["oracle_findings"][0].lower()
    )


def test_oracle_accepts_scheduling_case_with_different_time_slots() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-11",
                "summary": "Noisy appliance outside quiet hours",
                "detail": "Quiet hours 22:00-06:00; schedule outside quiet hours when needed.",
                "execution_profile": "scheduling",
            }
        ],
        "generated_cases": [
            {
                "title": "Noisy appliance scheduled outside quiet hours",
                "linked_requirement": "FR-11",
                "preconditions": (
                    "Quiet hours are 22:00-06:00. Cheapest slot is 23:00-01:00 at 0.08 €/kWh. "
                    "Next cheapest non-quiet slot is 06:00-08:00 at 0.12 €/kWh."
                ),
                "steps": [
                    "Mark the appliance as noisy.",
                    "Run scheduling with the provided price windows.",
                ],
                "expected_result": (
                    "The appliance is scheduled at 06:00-08:00 and is not scheduled at 23:00-01:00."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1
    assert out["oracle_rejected_cases"] == []


def test_oracle_accepts_manual_stop_case_without_time_windows() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-16",
                "summary": "Manual stop when appliance not running",
                "detail": (
                    "Manual stop shall be disabled when the appliance is not running. "
                    "An attempted stop must not cancel today's schedule."
                ),
                "execution_profile": "general",
            }
        ],
        "generated_cases": [
            {
                "title": "Do not allow manual stop when the appliance is not running",
                "linked_requirement": "FR-16",
                "preconditions": (
                    "An appliance exists with no active running state and may still have "
                    "scheduled hours later today."
                ),
                "steps": [
                    "Open the appliance control view for the idle appliance.",
                    "Attempt to use the manual stop control.",
                    "Observe the appliance status and today's schedule after the action.",
                ],
                "expected_result": (
                    "The appliance is not stopped because it is not running; no running session "
                    "is interrupted and no current-day schedule is canceled by the attempted stop."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1
    assert out["oracle_rejected_cases"] == []
