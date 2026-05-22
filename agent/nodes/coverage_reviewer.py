"""Coverage reviewer: deterministic gap detection + optional regen signal."""

from __future__ import annotations

import os
from typing import Any

from agent.coverage import build_coverage_report, compute_gaps
from agent.exhaustiveness import normalize_level
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

    reasoning_parts = [
        state.get("reasoning") or "",
        f"Coverage review (round {review_round}): "
        f"{report['rules_fully_covered']}/{report['rule_count']} requirements fully covered, "
        f"{report['total_cases']} cases, {report['gap_count']} gaps.",
    ]
    if gaps:
        sample = ", ".join(
            f"{g['rule_id']}/{g['test_type']} need {g['needed']}" for g in gaps[:8]
        )
        if len(gaps) > 8:
            sample += f" … (+{len(gaps) - 8} more)"
        reasoning_parts.append(f"Gaps: {sample}.")

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
    return {
        "review_round": int(state.get("review_round") or 0) + 1,
        "agent_looped_back": True,
        "current_step": "prepare_regeneration",
    }
