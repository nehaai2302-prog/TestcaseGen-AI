"""Tests for specification-fact extraction and validation (quiet hours, DST)."""

from __future__ import annotations

from agent.nodes.validate_spec_facts import validate_spec_facts
from services.spec_facts import extract_spec_facts, spec_fact_violations


def test_extract_quiet_hours_window() -> None:
    text = "Appliances marked as noisy shall not run during quiet hours 22:00-07:00."
    facts = extract_spec_facts(text)
    assert any(
        f.get("type") == "quiet_hours_window"
        and f.get("start") == "22:00"
        and f.get("end") == "07:00"
        for f in facts
    )


def test_extract_dst_day_lengths() -> None:
    text = (
        "On the spring-forward day the calendar day has 23 hours. "
        "On the fall-back day the calendar day has 25 hours."
    )
    facts = extract_spec_facts(text)
    assert any(
        f.get("type") == "dst_day_length"
        and f.get("transition") == "spring_forward"
        and f.get("hours") == 23
        for f in facts
    )
    assert any(
        f.get("type") == "dst_day_length"
        and f.get("transition") == "fall_back"
        and f.get("hours") == 25
        for f in facts
    )


def test_reject_spring_forward_with_wrong_day_length() -> None:
    facts = extract_spec_facts(
        "On the spring-forward (March) transition the day has 23 hours. "
        "On fall-back the day has 25 hours."
    )
    case = {
        "title": "DST spring-forward scheduling",
        "description": "Verify scheduling on a 25-hour day in March spring-forward.",
        "preconditions": "DST spring-forward weekend in March.",
        "steps": ["Run overnight schedule across the spring-forward night."],
        "expected_result": "System treats the spring-forward calendar day as a 25-hour day.",
    }
    issues = spec_fact_violations(case, facts)
    assert issues
    assert any("25-hour" in i and "spring-forward" in i for i in issues)


def test_reject_quiet_hours_wrong_end() -> None:
    facts = extract_spec_facts(
        "Noisy appliances shall not be scheduled during quiet hours 22:00-07:00."
    )
    case = {
        "title": "Quiet hours end check",
        "description": "Quiet hours are 22:00-06:00.",
        "preconditions": "Quiet hours configured as 22:00-06:00.",
        "steps": ["Attempt to schedule a noisy appliance at 06:30."],
        "expected_result": "Schedule is allowed after quiet hours end at 06:00.",
    }
    issues = spec_fact_violations(case, facts)
    assert issues
    assert any("06:00" in i and "07:00" in i for i in issues)


def test_accept_matching_quiet_hours_and_dst() -> None:
    facts = extract_spec_facts(
        "Quiet hours 22:00-07:00. Spring-forward days are 23-hour days; "
        "fall-back days are 25-hour days."
    )
    case = {
        "title": "Correct quiet hours and DST",
        "description": "Quiet hours are 22:00-07:00.",
        "preconditions": "Spring-forward night; calendar day is a 23-hour day.",
        "steps": ["Schedule outside quiet hours after 07:00."],
        "expected_result": "Noisy appliance may run after quiet hours end at 07:00.",
    }
    assert spec_fact_violations(case, facts) == []


def test_accept_quiet_hours_configuration_with_custom_window() -> None:
    """Settings tests may set a midnight-crossing window that is not the default."""
    facts = extract_spec_facts(
        "Quiet hours default to 22:00-07:00. Users may configure start and end "
        "times in hh:00 format."
    )
    case = {
        "title": "Define quiet hours that cross midnight using hh:00 times",
        "description": "",
        "preconditions": (
            "Current quiet hours are at the default value 22:00–07:00 "
            "or another known value."
        ),
        "steps": [
            "Open the General quiet hours settings.",
            "Set the start time to 23:00 and the end time to 06:00 using hh:00 format.",
            "Save the quiet hours configuration.",
            "Reopen the settings to confirm the saved values.",
        ],
        "expected_result": (
            "The quiet hours are saved successfully as 23:00–06:00, and the "
            "settings page shows the updated start and end times exactly as entered."
        ),
    }
    assert spec_fact_violations(case, facts) == []


def test_still_reject_wrong_window_when_used_as_scheduling_fixture() -> None:
    facts = extract_spec_facts(
        "Noisy appliances shall not run during quiet hours 22:00-07:00."
    )
    case = {
        "title": "FR-11 Positive - noisy appliance scheduled outside quiet hours",
        "description": (
            "Quiet hours window when cheapest slot is inside quiet hours"
        ),
        "preconditions": (
            "Quiet hours are configured for 22:00-06:00. A noisy appliance is enabled."
        ),
        "steps": [
            "Trigger schedule generation.",
            "Verify the selected hour is outside the 22:00-06:00 quiet hours window.",
        ],
        "expected_result": "The system schedules the noisy appliance at 07:00.",
    }
    issues = spec_fact_violations(case, facts)
    assert issues
    assert any("22:00-06:00" in i for i in issues)


def test_accept_schedule_time_after_outside_quiet_hours_phrase() -> None:
    """08:00-09:00 after 'outside quiet hours' is a run slot, not a quiet window."""
    facts = extract_spec_facts(
        "Noisy appliances shall not run during quiet hours 22:00-07:00."
    )
    case = {
        "title": (
            "FR-11 Smoke Positive - Noisy appliance scheduled outside quiet hours "
            "despite cheaper quiet-hour slot"
        ),
        "description": "",
        "preconditions": (
            "Quiet hours are configured for 22:00-07:00. A noisy appliance is available "
            "to schedule. Price data for the next day is set so that 23:00-00:00 and "
            "00:00-01:00 are the cheapest hours, and 08:00-09:00 is the cheapest hour "
            "outside quiet hours."
        ),
        "steps": [
            "Mark the appliance as noisy.",
            "Trigger scheduling for the appliance using the available price optimization.",
            "Review the scheduled run time chosen by the system.",
        ],
        "expected_result": (
            "The appliance is scheduled for the cheapest available time outside quiet "
            "hours, 08:00-09:00, and is not scheduled during 22:00-07:00."
        ),
    }
    assert spec_fact_violations(case, facts) == []


def test_accept_dst_calendar_fact_when_srs_silent() -> None:
    """Do not reject real-world spring-forward length when the SRS never states DST."""
    facts = extract_spec_facts("Quiet hours 22:00-07:00.")
    case = {
        "title": "Manual Override schedules an event across a 23-hour daylight saving time day",
        "description": "",
        "preconditions": (
            "Use a known spring-forward date where the local day has 23 hours."
        ),
        "steps": [
            "Create a manual override starting at 01:30 on the spring-forward date.",
            "Save the manual override.",
        ],
        "expected_result": "The manual override saves successfully.",
    }
    assert spec_fact_violations(case, facts) == []


def test_invented_example_does_not_hard_reject() -> None:
    facts = extract_spec_facts("Quiet hours 22:00-07:00.")
    case = {
        "title": "Invented example only",
        "description": (
            "Hypothetical invented example (not from the spec): quiet hours 22:00-06:00."
        ),
        "preconditions": "",
        "steps": [],
        "expected_result": "Illustrative only.",
    }
    assert spec_fact_violations(case, facts) == []


def test_validate_spec_facts_node_rejects_bad_dst_case() -> None:
    state = {
        "atomic_rules": [
            {
                "rule_id": "NFR-DST",
                "summary": "DST day lengths",
                "detail": (
                    "On spring-forward the calendar day has 23 hours. "
                    "On fall-back the calendar day has 25 hours."
                ),
            }
        ],
        "generated_cases": [
            {
                "linked_requirement": "NFR-DST",
                "title": "Wrong spring length",
                "description": "March spring-forward is treated as a 25-hour day.",
                "preconditions": "Spring-forward in March.",
                "steps": ["Observe day length across transition."],
                "expected_result": "The day has 25 hours.",
            },
            {
                "linked_requirement": "NFR-DST",
                "title": "Correct fall-back",
                "description": "Fall-back produces a 25-hour day.",
                "preconditions": "Fall-back night.",
                "steps": ["Observe day length."],
                "expected_result": "The fall-back calendar day has 25 hours.",
            },
        ],
        "reasoning": "",
    }
    out = validate_spec_facts(state)
    assert out["spec_fact_stats"]["rejected_cases"] == 1
    assert out["spec_fact_stats"]["valid_cases"] == 1
    assert len(out["spec_fact_rejected_cases"]) == 1
    assert "25-hour" in " ".join(
        out["spec_fact_rejected_cases"][0].get("spec_fact_violations") or []
    )
