"""Happy-path agent: positive test cases per atomic rule."""

from __future__ import annotations

import os
from typing import Any

from agent.coverage import gaps_for_agent
from agent.nodes._batch_generate import generate_happy_batch
from agent.state import TestGenState


def _batch_size() -> int:
    return max(1, int(os.environ.get("GEN_RULE_BATCH_SIZE", "3")))


def run_happy_path(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    if not rules:
        return {"positive_cases": [], "current_step": "run_happy_path"}

    gaps = gaps_for_agent(state.get("coverage_gaps") or [], "happy_path")
    is_regen = bool(gaps) and int(state.get("review_round") or 0) > 0

    if is_regen:
        new_cases = generate_happy_batch(rules, gaps, state)
        existing = list(state.get("positive_cases") or [])
        return {
            "positive_cases": existing + new_cases,
            "current_step": "run_happy_path",
        }

    all_cases: list[dict[str, Any]] = []
    for i in range(0, len(rules), _batch_size()):
        batch = rules[i : i + _batch_size()]
        all_cases.extend(generate_happy_batch(batch, None, state))

    return {
        "positive_cases": all_cases,
        "current_step": "run_happy_path",
    }
