"""Tests for cross-rule contradiction scanning."""

from __future__ import annotations

from agent.contradiction_scan import (
    scan_generated_case_contradictions,
    scan_spec_contradictions,
)
from agent.nodes.oracle_validate import oracle_validate


ECO_FR7 = {
    "rule_id": "FR-7",
    "summary": "Threshold mode run rule",
    "detail": (
        "In threshold mode, the appliance shall only run when the hourly spot price is "
        "below the configured price threshold."
    ),
}

ECO_FR8 = {
    "rule_id": "FR-8",
    "summary": "Skip cycle when no qualifying hour",
    "detail": (
        "If no hour in the scheduling window has a price at or below the threshold, "
        "the cycle shall be skipped for that day."
    ),
}

# Wording from ecocharge_srs.md release 1.0 (real acceptance fixture).
ECOCHARGE_SRS_FR7 = {
    "rule_id": "FR-7",
    "summary": "Threshold mode run rule",
    "detail": (
        "For each appliance in threshold mode, the system shall run the appliance only "
        "during hours whose spot price is strictly below the user-defined price threshold."
    ),
}

ECOCHARGE_SRS_FR8 = {
    "rule_id": "FR-8",
    "summary": "Skip cycle when no qualifying hour",
    "detail": (
        "If no hour within the scheduling window has a spot price at or below the "
        "threshold, the system shall skip the appliance's cycle for that day and notify "
        "the user."
    ),
}

ECOCHARGE_SRS_FR12 = {
    "rule_id": "FR-12",
    "summary": "Immediate schedule notification",
    "detail": (
        "The system shall send a push notification to the user immediately when a daily "
        "schedule is created, listing the selected hours and estimated cost for each "
        "appliance."
    ),
}

ECOCHARGE_SRS_FR13 = {
    "rule_id": "FR-13",
    "summary": "Quiet-hours notification queue",
    "detail": (
        "Push notifications shall not be delivered during quiet hours. Notifications "
        "generated during quiet hours shall be queued and delivered when quiet hours end."
    ),
}

USER_FR7_CASE = {
    "title": "Threshold mode excludes hours priced exactly at the threshold",
    "linked_requirement": "FR-7",
    "test_type": "negative",
    "preconditions": (
        'An appliance named "Washing Machine" exists and can be set to threshold mode. '
        "Configure the user-defined price threshold to 0.15 currency units/kWh. "
        "Prepare a spot price window with one hour priced exactly at 0.15 currency units/kWh."
    ),
    "steps": [
        "Set Washing Machine to threshold mode with the price threshold at 0.15 currency units/kWh.",
        "Trigger the appliance scheduling/run calculation for the hour priced at 0.15.",
        "Check whether the appliance is scheduled to run during that hour.",
    ],
    "expected_result": (
        "Washing Machine is not scheduled to run at 0.15 currency units/kWh because the "
        "requirement allows only hours strictly below the threshold."
    ),
}

USER_FR8_CASE = {
    "title": "Do not skip cycle when at least one scheduling-window hour is at or below threshold",
    "linked_requirement": "FR-8",
    "test_type": "negative",
    "preconditions": (
        "Scheduling feature is enabled. Appliance scheduling window is configured for a single day "
        "with these hourly spot prices: 01:00 = 0.32, 02:00 = 0.20, 03:00 = 0.25. "
        "Threshold is set to 0.20 for the appliance cycle. User has notification delivery enabled."
    ),
    "steps": [
        "Configure the appliance to run only within the 01:00–03:00 scheduling window.",
        "Set the price threshold to 0.20.",
        "Save the schedule and wait until the scheduled day completes.",
        "Check whether the appliance cycle started on the day.",
        "Check whether any skip notification was sent.",
    ],
    "expected_result": (
        "The appliance cycle is not skipped because 02:00 matches the threshold at 0.20, "
        "and no 'skipped for the day' notification is sent."
    ),
}


def test_scan_flags_ecocharge_fr7_fr8_spec_text() -> None:
    contradictions = scan_spec_contradictions([ECO_FR7, ECO_FR8])
    assert len(contradictions) == 1
    assert contradictions[0]["rule_id"] == "FR-7"
    assert contradictions[0]["related_rule_ids"] == ["FR-8"]


def test_scan_flags_ecocharge_srs_release_wording() -> None:
    """Regression: real SRS uses 'strictly below' + 'spot price at or below'."""
    contradictions = scan_spec_contradictions([ECOCHARGE_SRS_FR7, ECOCHARGE_SRS_FR8])
    assert len(contradictions) == 1
    assert contradictions[0]["related_rule_ids"] == ["FR-8"]


def test_scan_flags_ecocharge_fr12_fr13_notification_timing() -> None:
    contradictions = scan_spec_contradictions([ECOCHARGE_SRS_FR12, ECOCHARGE_SRS_FR13])
    assert len(contradictions) == 1
    assert contradictions[0]["rule_id"] == "FR-12"
    assert contradictions[0]["related_rule_ids"] == ["FR-13"]
    assert "notification timing" in contradictions[0]["issue"].lower()


def test_scan_flags_synthetic_immediate_vs_queued_notifications() -> None:
    immediate = {
        "rule_id": "REQ-N1",
        "detail": "The app shall send an alert at once when an order is placed.",
    }
    queued = {
        "rule_id": "REQ-N2",
        "detail": (
            "Alerts shall not be delivered during the night curfew period; "
            "they are queued until the curfew ends."
        ),
    }
    contradictions = scan_spec_contradictions([immediate, queued])
    assert len(contradictions) == 1
    assert "notification timing" in contradictions[0]["issue"].lower()


def test_scan_finds_both_threshold_and_notification_pairs() -> None:
    rules = [
        ECOCHARGE_SRS_FR7,
        ECOCHARGE_SRS_FR8,
        ECOCHARGE_SRS_FR12,
        ECOCHARGE_SRS_FR13,
    ]
    contradictions = scan_spec_contradictions(rules)
    pairs = {frozenset({c["rule_id"], *c["related_rule_ids"]}) for c in contradictions}
    assert frozenset({"FR-7", "FR-8"}) in pairs
    assert frozenset({"FR-12", "FR-13"}) in pairs
    assert len(contradictions) == 2


def test_scan_uses_ingested_chunks_when_analyst_summary_is_short() -> None:
    """Generic: scan ingested requirement text, not only LLM-paraphrased rule fields."""
    rules = [
        {
            "rule_id": "FR-7",
            "summary": "Threshold scheduling",
            "detail": "Run when price is below threshold.",
        },
        {
            "rule_id": "FR-8",
            "summary": "Skip cycle rule",
            "detail": "Skip when no qualifying hour.",
        },
    ]
    chunks = [
        {
            "id": "c7",
            "requirement_id": "FR-7",
            "chunk_text": ECO_FR7["detail"],
        },
        {
            "id": "c8",
            "requirement_id": "FR-8",
            "chunk_text": ECO_FR8["detail"],
        },
    ]
    assert scan_spec_contradictions(rules) == []
    contradictions = scan_spec_contradictions(rules, requirement_chunks=chunks)
    assert len(contradictions) == 1


def test_scan_flags_less_than_or_equal_wording() -> None:
    strict_rule = {
        "rule_id": "REQ-A",
        "summary": "Run below threshold",
        "detail": "The system shall run only when price is below the threshold.",
    }
    inclusive_rule = {
        "rule_id": "REQ-B",
        "summary": "Skip when none qualify",
        "detail": (
            "If no hour has a price less than or equal to the threshold, "
            "the cycle shall be skipped."
        ),
    }
    contradictions = scan_spec_contradictions([strict_rule, inclusive_rule])
    assert len(contradictions) == 1


def test_scan_flags_user_generated_fr7_fr8_cases() -> None:
    findings = scan_generated_case_contradictions([USER_FR7_CASE, USER_FR8_CASE])
    assert len(findings) == 1
    assert findings[0]["related_rule_ids"] == ["FR-8"]


def test_oracle_preserves_contradictions_when_no_cases_generated() -> None:
    chunks = [
        {"requirement_id": "FR-7", "chunk_text": ECO_FR7["detail"]},
        {"requirement_id": "FR-8", "chunk_text": ECO_FR8["detail"]},
    ]
    state = {
        "atomic_rules": [ECO_FR7, ECO_FR8],
        "requirement_chunks": chunks,
        "generated_cases": [],
    }
    out = oracle_validate(state)
    assert len(out["contradictions"]) >= 1
    assert out["atomic_rules"][0]["status"] == "requires_clarification"


def test_oracle_rejects_conflicting_fr7_fr8_cases() -> None:
    state = {
        "atomic_rules": [ECO_FR7, ECO_FR8],
        "generated_cases": [USER_FR7_CASE, USER_FR8_CASE],
    }
    out = oracle_validate(state)
    assert out["oracle_stats"]["rejected_cases"] == 2
    assert len(out["contradictions"]) >= 1
    assert out["generated_cases"] == []
