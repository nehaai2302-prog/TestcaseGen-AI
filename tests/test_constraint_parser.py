"""Tests for constraint extraction helpers."""

from __future__ import annotations

from services.constraint_parser import extract_constraints


def test_extract_range_and_increment() -> None:
    text = "FR-9: price threshold 0.000–1.000 €/kWh, in increments of 0.001"
    constraints = extract_constraints(text)
    assert any(
        c.get("type") == "range"
        and c.get("field") == "price_threshold"
        and c.get("min") == 0.0
        and c.get("max") == 1.0
        and c.get("unit") == "€/kWh"
        for c in constraints
    )
    assert any(
        c.get("type") == "increment"
        and c.get("field") == "price_threshold"
        and c.get("step") == 0.001
        for c in constraints
    )


def test_extract_ecocharge_fr9_between_range_wording() -> None:
    text = (
        "The price threshold shall be a value between 0.000 and 1.000 €/kWh, "
        "configurable in increments of 0.001."
    )
    constraints = extract_constraints(text)
    assert any(
        c.get("type") == "range"
        and c.get("field") == "price_threshold"
        and c.get("min") == 0.0
        and c.get("max") == 1.0
        for c in constraints
    )


def test_extract_checkout_coupon_discount_range() -> None:
    """Generic payment spec wording — no EcoCharge IDs."""
    text = "Coupon discount 1-50 percent."
    constraints = extract_constraints(text)
    assert any(
        c.get("type") == "range"
        and c.get("field") == "coupon_discount"
        and c.get("min") == 1.0
        and c.get("max") == 50.0
        for c in constraints
    )


def test_extract_enum_format_and_int_range() -> None:
    text = (
        "Country code must be one of: LT, LV, EE, FI, SE4. "
        "Start time must be in hh:00 format. "
        "Duration 1–8 hours."
    )
    constraints = extract_constraints(text)
    assert any(
        c.get("type") == "enum" and c.get("values") == ["LT", "LV", "EE", "FI", "SE4"]
        for c in constraints
    )
    assert any(c.get("type") == "format" and c.get("pattern") == "hh:00" for c in constraints)
    assert any(
        c.get("type") == "int_range"
        and c.get("min") == 1
        and c.get("max") == 8
        for c in constraints
    )

