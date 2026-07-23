"""Tests for clarifying-question generation (Phase 5.3a)."""

from __future__ import annotations

from agent.clarifying_questions import (
    build_clarifying_questions,
    questions_from_contradictions,
    questions_from_underspecification,
)
from agent.models import AnalystResult, ClarifyingQuestion


def test_clarifying_question_model_roundtrip() -> None:
    q = ClarifyingQuestion(
        rule_ids=["FR-5"],
        question="What happens on a price tie?",
        why_it_matters="Needed for a deterministic expected result.",
    )
    result = AnalystResult(clarifying_questions=[q])
    dumped = result.model_dump()
    assert dumped["clarifying_questions"][0]["rule_ids"] == ["FR-5"]


def test_questions_from_contradictions() -> None:
    contradictions = [
        {
            "rule_id": "FR-7",
            "issue": "Contradicts FR-8 at price == threshold",
            "related_rule_ids": ["FR-8"],
        }
    ]
    qs = questions_from_contradictions(contradictions)
    assert len(qs) == 1
    assert set(qs[0]["rule_ids"]) == {"FR-7", "FR-8"}
    assert "FR-7" in qs[0]["question"]
    assert qs[0]["source"] == "contradiction"


def test_comparison_tie_break_question() -> None:
    rules = [
        {
            "rule_id": "FR-5",
            "summary": "Select cheapest contiguous block",
            "detail": "Select the cheapest 2-hour block from the available window.",
            "execution_profile": "comparison",
            "status": "active",
        }
    ]
    qs = questions_from_underspecification(rules)
    assert any("tie" in q["question"].lower() for q in qs)


def test_vague_wording_question() -> None:
    rules = [
        {
            "rule_id": "REQ-1",
            "summary": "Notify as needed",
            "detail": "The system shall notify the user as appropriate when scheduling fails.",
            "status": "active",
        }
    ]
    qs = questions_from_underspecification(rules)
    assert any("vague" in q["question"].lower() or "as needed" in q["question"].lower() for q in qs)


def test_build_merges_and_dedupes() -> None:
    rules = [
        {
            "rule_id": "FR-5",
            "summary": "Select cheapest block",
            "detail": "Select the cheapest contiguous block.",
            "execution_profile": "comparison",
            "status": "active",
        }
    ]
    contradictions = [
        {
            "rule_id": "FR-7",
            "issue": "Conflicts with FR-8",
            "related_rule_ids": ["FR-8"],
        }
    ]
    llm_qs = [
        {
            "rule_ids": ["FR-5"],
            "question": "What happens when two blocks have the same total?",
            "why_it_matters": "Tie-break required.",
            "source": "analyst",
        }
    ]
    out = build_clarifying_questions(rules, contradictions, llm_questions=llm_qs)
    assert any(q["source"] == "contradiction" for q in out)
    assert any("FR-5" in q["rule_ids"] for q in out)
    # Dedup should not explode
    assert len(out) <= 24


def test_precedence_over_does_not_trigger_boundary_equality() -> None:
    """'precedence over' must not be treated as a numeric inequality."""
    rules = [
        {
            "rule_id": "FR-11",
            "summary": "Quiet hours for noisy appliances",
            "detail": (
                'Appliances marked as "noisy" shall not be scheduled to run during '
                "quiet hours, even if the cheapest hours fall within them. "
                "Quiet hours take precedence over price optimization."
            ),
            "execution_profile": "scheduling",
            "status": "active",
        }
    ]
    qs = questions_from_underspecification(rules)
    assert not any("boundary value" in q["question"].lower() for q in qs)


def test_strictly_below_threshold_asks_boundary_equality() -> None:
    rules = [
        {
            "rule_id": "FR-7",
            "summary": "Threshold mode",
            "detail": (
                "Run the appliance only during hours whose spot price is "
                "strictly below the user-defined price threshold."
            ),
            "execution_profile": "config",
            "status": "active",
        }
    ]
    qs = questions_from_underspecification(rules)
    assert any("boundary value" in q["question"].lower() for q in qs)