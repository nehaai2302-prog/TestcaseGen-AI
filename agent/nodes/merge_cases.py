"""Merge positive and destructive case lists into generated_cases."""

from __future__ import annotations

from typing import Any

from agent.state import TestGenState


def merge_cases(state: TestGenState) -> dict[str, Any]:
    positive = list(state.get("positive_cases") or [])
    destructive = list(state.get("destructive_cases") or [])
    merged = positive + destructive
    return {
        "generated_cases": merged,
        "current_step": "merge_cases",
    }
