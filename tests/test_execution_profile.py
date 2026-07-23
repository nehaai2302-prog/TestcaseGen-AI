"""Tests for spec-agnostic execution profile inference."""

from __future__ import annotations

from agent.execution_profile import infer_execution_profile, normalize_execution_profile


def test_infer_config_profile_for_threshold_range() -> None:
    text = "Price threshold must be between 0.000 and 1.000 €/kWh in increments of 0.001."
    constraints = [
        {"type": "range", "min": 0.0, "max": 1.0, "unit": "€/kWh"},
        {"type": "increment", "step": 0.001, "unit": "€/kWh"},
    ]
    assert infer_execution_profile(text, constraints) == "config"


def test_infer_scheduling_profile_for_runtime_windows() -> None:
    text = "Noisy appliances shall not run during quiet hours 22:00-06:00."
    assert infer_execution_profile(text) == "scheduling"


def test_fr11_stays_scheduling_even_when_cheapest_is_mentioned() -> None:
    text = (
        "Appliances marked as noisy shall not be scheduled to run during quiet hours, "
        "even if the cheapest hours fall within them. Quiet hours take precedence over "
        "price optimization."
    )
    assert infer_execution_profile(text) == "scheduling"


def test_nfr4_timezone_display_is_general() -> None:
    text = "All times shall be displayed in the user's local timezone."
    assert infer_execution_profile(text) == "general"


def test_manual_stop_rule_stays_general_even_with_schedule_mention() -> None:
    text = (
        "Manual stop shall be disabled when the appliance is not running. "
        "An attempted stop must not cancel today's schedule."
    )
    assert infer_execution_profile(text) == "general"


def test_normalize_general_label_does_not_override_comparison_inference() -> None:
    text = "Select the cheapest contiguous block within the scheduling window."
    assert normalize_execution_profile("general", text) == "comparison"


def test_infer_comparison_profile_for_selection_rules() -> None:
    text = "Select the cheapest 2-hour block from the available 8-hour window."
    assert infer_execution_profile(text) == "comparison"


def test_coupon_max_characters_is_config_not_comparison() -> None:
    """Bare 'maximum' must not force comparison — length limits are config."""
    text = (
        "The coupon input field shall accept a maximum of 10 characters. "
        "Values longer than 10 characters must be blocked."
    )
    assert infer_execution_profile(text) == "config"
    assert normalize_execution_profile("comparison", text) == "config"


def test_minimum_availability_is_not_comparison() -> None:
    text = "Scheduling service monthly availability shall meet a 99.5% minimum."
    assert infer_execution_profile(text) != "comparison"


def test_normalize_execution_profile_uses_llm_value_when_valid() -> None:
    assert normalize_execution_profile("config", "select cheapest slot") == "config"
