"""Tests for requirement ID splitting and parse-quality heuristics."""

from __future__ import annotations

import pytest

from services.chunking import (
    RequirementSplit,
    assess_parse_quality,
    split_requirements,
    structured_splits_low_confidence,
)

COUPON_DOC = """\
2.3 Coupon Business Rules & Validation
FR-2.4
The system shall trim leading and trailing whitespace from the coupon code before validation.
FR-2.5
Coupon codes shall be treated as case-insensitive during validation.
FR-2.6
The system shall prevent submission of empty coupon codes and display:
"Bitte geben Sie einen Gutscheincode ein."
FR-2.7
Only one coupon code may be applied per order unless explicitly configured for coupon stacking.
FR-99.9: sentinel.
"""


@pytest.mark.parametrize(
    "src,expected_id,expected_body_start",
    [
        (
            "\u2022 FR-1.1: The system shall validate coupon codes on submission.",
            "FR-1.1",
            "The system shall validate coupon codes on submission.",
        ),
        (
            "- FR-2.3: Inventory must be re-checked at checkout.",
            "FR-2.3",
            "Inventory must be re-checked at checkout.",
        ),
        (
            "**FR-3.5**: Refunds must be processed within 24 hours.",
            "FR-3.5",
            "Refunds must be processed within 24 hours.",
        ),
        (
            "FR 4.2: Search results must paginate at 20 items per page.",
            "FR-4.2",
            "Search results must paginate at 20 items per page.",
        ),
        (
            "BND-001: Character count = 10 \u2014 Accept input for validation.",
            "BND-001",
            "Character count = 10",
        ),
        (
            "1.2.3: Some numeric heading requirement.",
            "1.2.3",
            "Some numeric heading requirement.",
        ),
        (
            "US-103: As a buyer, I want to apply a coupon code.",
            "US-103",
            "As a buyer, I want to apply a coupon code.",
        ),
        (
            "REQ-12. Optional trailing period after ID.",
            "REQ-12",
            "Optional trailing period after ID.",
        ),
    ],
)
def test_split_requirements_common_forms(
    src: str, expected_id: str, expected_body_start: str
) -> None:
    doc = src + "\nFR-99.9: trailing sentinel.\n"
    splits = split_requirements(doc)
    assert splits, f"no splits for {src!r}"
    head = splits[0]
    assert head.requirement_id == expected_id
    assert head.text.splitlines()[0].strip().startswith(expected_body_start)


def test_coupon_doc_ids_on_separate_lines() -> None:
    splits = split_requirements(COUPON_DOC)
    by_id = {s.requirement_id: s for s in splits}
    assert by_id["FR-2.4"].text.startswith("The system shall trim")
    assert by_id["FR-2.5"].text.startswith("Coupon codes")
    assert by_id["FR-2.6"].text.startswith("The system shall prevent")
    assert by_id["FR-2.7"].text.startswith("Only one coupon")
    assert "FR-2-2" not in by_id
    assert not structured_splits_low_confidence(splits)
    assert assess_parse_quality(splits) == "ok"


PAYMENT_MODULE_DOC = """\
1. Core Payment Processing (Happy Path)
\u2022 FR-1.1: The system must integrate with a PCI-DSS compliant third-party payment gateway.
\u2022 FR-1.2: Upon clicking "Place Order," the system must issue a single tokenized payload.
\u2022 FR-1.3: On a successful transaction response, the system must clear the user's active cart session.
2. Dynamic Input Validation
\u2022 FR-2.1: The card input fields must validate string formats in real-time.
\u2022 FR-2.2: If a transaction fails due to banking constraints, the Payment Module must catch the gateway error code.
3. Cross-Module State Constraints
\u2022 FR-3.1 (Cart Interaction): The Payment Module must re-verify the active total price against the Database.
\u2022 FR-3.2 (Coupon Interaction): If a valid coupon code is applied or removed, the payment module's payload Amount must recalculate.
\u2022 FR-3.3 (Inventory Lock): If an item in the cart becomes "Out of Stock", the Place Order button must be disabled.
4. Non-Functional Requirements (NFRs)
\u2022 NFR-4.1 (Data Protection): The application must completely satisfy PCI-DSS requirements.
\u2022 NFR-4.2 (Idempotency): The Payment API endpoint must accept an Idempotency-Key header.
\u2022 NFR-4.3 (Latency): The UI transition must take less than 200ms.
FR-99.9: sentinel.
"""


def test_payment_module_doc_all_requirement_ids() -> None:
    splits = split_requirements(PAYMENT_MODULE_DOC)
    ids = [s.requirement_id for s in splits]
    expected = [
        "FR-1.1",
        "FR-1.2",
        "FR-1.3",
        "FR-2.1",
        "FR-2.2",
        "FR-3.1",
        "FR-3.2",
        "FR-3.3",
        "NFR-4.1",
        "NFR-4.2",
        "NFR-4.3",
    ]
    assert ids == expected, ids
    by_id = {s.requirement_id: s for s in splits}
    assert by_id["FR-3.1"].text.startswith("The Payment Module must re-verify")
    assert by_id["NFR-4.1"].text.startswith("The application must completely")
    assert assess_parse_quality(splits) == "ok"


@pytest.mark.parametrize(
    "src,expected_id,expected_body_start",
    [
        (
            "\u2022 FR-3.1 (Cart Interaction): The Payment Module must re-verify totals.",
            "FR-3.1",
            "The Payment Module must re-verify totals.",
        ),
        (
            "NFR-4.2 (Idempotency): The Payment API endpoint must accept a key.",
            "NFR-4.2",
            "The Payment API endpoint must accept a key.",
        ),
    ],
)
def test_parenthetical_label_before_colon(
    src: str, expected_id: str, expected_body_start: str
) -> None:
    doc = src + "\nFR-99.9: trailing sentinel.\n"
    head = split_requirements(doc)[0]
    assert head.requirement_id == expected_id
    assert head.text.splitlines()[0].strip().startswith(expected_body_start)


def test_truncated_ids_are_low_confidence() -> None:
    splits = [
        RequirementSplit(
            requirement_id="FR-2",
            text="4 The system shall trim whitespace.",
            is_synthetic=False,
        ),
        RequirementSplit(
            requirement_id="FR-2-2",
            text="5 Coupon codes shall be case-insensitive.",
            is_synthetic=False,
        ),
    ]
    assert structured_splits_low_confidence(splits)
    assert assess_parse_quality(splits) == "ambiguous"
