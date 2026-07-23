"""Tests for comparison substance validation (Phase 5.1c)."""

from __future__ import annotations

from agent.nodes.oracle_validate import oracle_validate
from agent.substance import comparison_substance_findings

ECOCHARGE_FR5 = {
    "rule_id": "FR-5",
    "summary": "Cheapest contiguous block",
    "detail": (
        "For each appliance in cheapest-hours mode, the system shall select the contiguous "
        "block of hours within the scheduling window whose total price is the lowest, where "
        "the block length equals the appliance runtime."
    ),
    "execution_profile": "comparison",
}


def test_substance_rejects_case_without_price_data() -> None:
    case = {
        "preconditions": "A scheduling window exists.",
        "steps": ["Given a 24-hour window", "Find block with lowest price"],
        "expected_result": "Block selected",
    }
    findings = comparison_substance_findings(ECOCHARGE_FR5, case)
    assert findings
    assert "candidate values" in findings[0].lower()


def test_substance_rejects_vague_expected_even_with_prices() -> None:
    case = {
        "preconditions": (
            "Hourly prices (€/kWh): 01:00=0.30, 02:00=0.25, 03:00=0.28, 04:00=0.22. "
            "Runtime is 2 hours."
        ),
        "steps": ["Run schedule optimization for the appliance."],
        "expected_result": "The system selects the cheapest contiguous block.",
    }
    findings = comparison_substance_findings(ECOCHARGE_FR5, case)
    assert findings
    assert "concrete verifiable outcome" in findings[0].lower()


def test_substance_accepts_concrete_comparison_case() -> None:
    case = {
        "preconditions": (
            "8-hour window with hourly spot prices (€/kWh): 01:00=0.30, 02:00=0.25, "
            "03:00=0.28, 04:00=0.22, 05:00=0.35, 06:00=0.20, 07:00=0.18, 08:00=0.24. "
            "Appliance runtime is 2 hours."
        ),
        "steps": ["Run schedule optimization for the appliance."],
        "expected_result": (
            "Appliance is scheduled for 06:00-08:00 (total 0.38 €/kWh), not 04:00-06:00 "
            "(total 0.42 €/kWh)."
        ),
    }
    assert comparison_substance_findings(ECOCHARGE_FR5, case) == []


def test_oracle_rejects_fr5_style_case_without_substance() -> None:
    state = {
        "atomic_rules": [ECOCHARGE_FR5],
        "generated_cases": [
            {
                "title": "Cheapest block selected",
                "linked_requirement": "FR-5",
                "preconditions": "Cheapest-hours mode is enabled.",
                "steps": [
                    "Configure a scheduling window.",
                    "Trigger schedule generation.",
                ],
                "expected_result": "The lowest total price block is selected.",
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["rejected_cases"] == 1


def test_oracle_rejects_fr5_when_execution_profile_mislabeled_general() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "FR-5",
                "detail": ECOCHARGE_FR5["detail"],
                "execution_profile": "general",
            }
        ],
        "generated_cases": [
            {
                "title": "Cheapest block selected",
                "linked_requirement": "FR-5",
                "test_type": "positive",
                "preconditions": (
                    "Hourly prices: 01:00=0.30, 02:00=0.25, 03:00=0.28, 04:00=0.22. "
                    "Runtime 2 hours."
                ),
                "steps": ["Generate schedule for the appliance."],
                "expected_result": (
                    "The system selects the contiguous block with the lowest total price."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["rejected_cases"] == 1


def test_oracle_accepts_fr5_style_case_with_named_block() -> None:
    state = {
        "atomic_rules": [ECOCHARGE_FR5],
        "generated_cases": [
            {
                "title": "Select cheapest 2-hour block",
                "linked_requirement": "FR-5",
                "preconditions": (
                    "Window 01:00-08:00 with prices: 0.30, 0.25, 0.28, 0.22, 0.35, 0.20, 0.18, 0.24 "
                    "€/kWh. Runtime 2 hours."
                ),
                "steps": ["Generate the daily schedule for the appliance."],
                "expected_result": "Schedule uses 06:00-08:00 (total 0.38 €/kWh).",
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1


def test_oracle_accepts_comparison_rejection_when_runtime_exceeds_window() -> None:
    state = {
        "atomic_rules": [ECOCHARGE_FR5],
        "generated_cases": [
            {
                "title": "Reject scheduling when runtime exceeds available contiguous hours",
                "linked_requirement": "FR-5",
                "test_type": "negative",
                "preconditions": (
                    "Appliance B uses cheapest-hours mode with runtime 5 hours. "
                    "The scheduling window has 4 consecutive hours with prices: "
                    "Hour 1=0.12, Hour 2=0.13, Hour 3=0.11, Hour 4=0.14."
                ),
                "steps": [
                    "Confirm cheapest-hours mode and runtime 5 hours.",
                    "Provide the 4-hour window with the listed prices.",
                    "Trigger schedule calculation.",
                ],
                "expected_result": (
                    "The system does not select any block and shows a clear message that "
                    "the 5-hour runtime cannot fit within the 4-hour scheduling window."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1


def test_substance_accepts_runtime_exceeds_window_without_dual_duration_in_expected() -> None:
    """Regression: 4h runtime vs 3 price slots — rejection need not repeat both durations."""
    case = {
        "test_type": "negative",
        "preconditions": (
            "Cheapest-hours mode with runtime 4 hours. Scheduling window has only 3 hourly "
            "prices: 18:00=0.100, 19:00=0.200, 20:00=0.150 €/kWh."
        ),
        "steps": [
            "Set runtime to 4 hours.",
            "Enter the 3 hourly prices from preconditions.",
            "Trigger schedule calculation.",
        ],
        "expected_result": (
            "The system does not select a block and shows a clear message that there are "
            "not enough contiguous hours in the scheduling window for the 4-hour runtime."
        ),
    }
    assert comparison_substance_findings(ECOCHARGE_FR5, case) == []


def test_oracle_accepts_fr11_quiet_hours_rejection_with_times() -> None:
    fr11 = {
        "rule_id": "FR-11",
        "summary": "Noisy appliances blocked during quiet hours",
        "detail": (
            "Appliances marked as noisy shall not be scheduled to run during quiet hours, "
            "even if the cheapest hours fall within them."
        ),
    }
    state = {
        "atomic_rules": [fr11],
        "generated_cases": [
            {
                "title": "Noise restriction blocks scheduling during quiet hours",
                "linked_requirement": "FR-11",
                "test_type": "negative",
                "preconditions": (
                    "Quiet hours are 22:00-06:00. Forecast: 22:00=0.02, 23:00=0.02, "
                    "00:00=0.02 €/kWh. Noisy appliance; no non-quiet hour matches."
                ),
                "steps": [
                    "Open scheduling for the noisy appliance.",
                    "Attempt auto-schedule with price optimization.",
                ],
                "expected_result": (
                    "The schedule is not created for any quiet-hour start time, and the system "
                    "shows a blocking message indicating the appliance cannot run during quiet "
                    "hours. Quiet hours take precedence over the cheapest prices."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1


def test_oracle_accepts_timezone_display_case() -> None:
    nfr4 = {
        "rule_id": "NFR-4",
        "summary": "Display times in local timezone",
        "detail": "All times shall be displayed in the user's local timezone.",
    }
    state = {
        "atomic_rules": [nfr4],
        "generated_cases": [
            {
                "title": "Reject display that keeps times in source timezone",
                "linked_requirement": "NFR-4",
                "test_type": "negative",
                "preconditions": (
                    "Device timezone is Europe/Helsinki. Source record timezone is one hour "
                    "behind local time."
                ),
                "steps": [
                    "Open the page that shows the time value.",
                    "Load the record in the different source timezone.",
                    "Compare displayed time to source and local timezone.",
                ],
                "expected_result": (
                    "The time is not shown in the source timezone; it is displayed in the "
                    "user's local timezone only."
                ),
            }
        ],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["valid_cases"] == 1
