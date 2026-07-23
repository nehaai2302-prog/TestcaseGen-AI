"""Coverage reviewer: deterministic gap detection + optional regen signal."""

from __future__ import annotations

import os
from typing import Any

from agent.coverage import build_coverage_report, compute_gaps
from agent.exhaustiveness import normalize_level
from agent.ambiguity import STATUS_REQUIRES_CLARIFICATION
from agent.state import TestGenState


def _max_review_rounds() -> int:
    return max(0, int(os.environ.get("MAX_COVERAGE_REVIEW_ROUNDS", "0")))


def review_coverage(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    cases = list(state.get("generated_cases") or [])
    level = normalize_level(state.get("exhaustiveness_level"))
    review_round = int(state.get("review_round") or 0)

    gaps = compute_gaps(rules, cases, level)
    report = build_coverage_report(rules, cases, level)
    blocked = int(report.get("blocked_rule_count") or 0)

    reasoning_parts = [
        state.get("reasoning") or "",
        f"Coverage review (round {review_round}): "
        f"{report['rules_fully_covered']}/{report['rule_count']} fully covered, "
        f"{report.get('rules_partially_covered', 0)} partially covered, "
        f"{report.get('rules_not_covered', 0)} not covered "
        f"({report.get('generatable_rule_count', report['rule_count'])} generatable, "
        f"{blocked} blocked), "
        f"{report['total_cases']} cases.",
    ]
    if blocked:
        reasoning_parts.append(
            f"{blocked} requirement(s) blocked with status '{STATUS_REQUIRES_CLARIFICATION}' "
            "due to specification contradictions."
        )
    if gaps:
        sample = ", ".join(
            f"{g['rule_id']}/{g['test_type']} need {g['needed']}" for g in gaps[:8]
        )
        if len(gaps) > 8:
            sample += f" … (+{len(gaps) - 8} more)"
        reasoning_parts.append(f"Incomplete quotas: {sample}.")

    needs_regen = bool(gaps) and review_round < _max_review_rounds()

    return {
        "coverage_gaps": gaps,
        "coverage_report": report,
        "coverage_satisfied": not bool(gaps),
        "needs_regeneration": needs_regen,
        "reasoning": "\n".join(p for p in reasoning_parts if p).strip(),
        "current_step": "review_coverage",
    }


def prepare_regeneration(state: TestGenState) -> dict[str, Any]:
    """Increment review round before looping back to generators."""
    from agent.regen import build_regen_feedback

    feedback = build_regen_feedback(state)
    gap_rules = {
        str(g.get("rule_id") or "")
        for g in (state.get("coverage_gaps") or [])
        if g.get("rule_id")
    }
    if gap_rules:
        feedback = {k: v for k, v in feedback.items() if k in gap_rules}
    return {
        "review_round": int(state.get("review_round") or 0) + 1,
        "agent_looped_back": True,
        "regen_feedback": feedback,
        "current_step": "prepare_regeneration",
    }
