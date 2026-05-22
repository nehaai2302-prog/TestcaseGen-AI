"""Destructive agent: negative, boundary, and edge test cases."""

from __future__ import annotations

import os
from typing import Any

from agent.coverage import gaps_for_agent
from agent.nodes._batch_generate import generate_destructive_batch
from agent.state import TestGenState


def _batch_size() -> int:
    return max(1, int(os.environ.get("GEN_RULE_BATCH_SIZE", "3")))


def run_destructive(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    if not rules:
        return {"destructive_cases": [], "current_step": "run_destructive"}

    gaps = gaps_for_agent(state.get("coverage_gaps") or [], "destructive")
    is_regen = bool(gaps) and int(state.get("review_round") or 0) > 0

    if is_regen:
        new_cases = generate_destructive_batch(rules, gaps, state)
        existing = list(state.get("destructive_cases") or [])
        return {
            "destructive_cases": existing + new_cases,
            "current_step": "run_destructive",
        }

    all_cases: list[dict[str, Any]] = []
    for i in range(0, len(rules), _batch_size()):
        batch = rules[i : i + _batch_size()]
        all_cases.extend(generate_destructive_batch(batch, None, state))

    return {
        "destructive_cases": all_cases,
        "current_step": "run_destructive",
    }
