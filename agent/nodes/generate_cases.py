"""Combined test generation (all types in one LLM call per requirement), parallelized."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from agent.nodes._batch_generate import generate_combined_batch
from agent.ambiguity import generatable_rules, mark_rule_statuses
from agent.contradiction_scan import merge_contradictions, scan_spec_contradictions
from agent.state import TestGenState


def _rules_for_generation(
    state: TestGenState,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    all_rules = list(state.get("atomic_rules") or [])
    chunks = list(state.get("requirement_chunks") or [])
    contradictions = merge_contradictions(
        list(state.get("contradictions") or []),
        scan_spec_contradictions(all_rules, requirement_chunks=chunks),
    )
    marked_rules = mark_rule_statuses(all_rules, contradictions)
    return generatable_rules(marked_rules), contradictions, marked_rules


def _batch_size() -> int:
    return max(1, int(os.environ.get("GEN_RULE_BATCH_SIZE", "8")))


def _max_workers() -> int:
    return max(1, int(os.environ.get("GEN_PARALLEL_WORKERS", "3")))


def _run_batches_parallel(
    batches: list[list[dict[str, Any]]],
    state: TestGenState,
    gaps: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if len(batches) <= 1:
        if not batches:
            return []
        return generate_combined_batch(batches[0], state, gaps)

    all_cases: list[dict[str, Any]] = []
    workers = min(_max_workers(), len(batches))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(generate_combined_batch, batch, dict(state), gaps): i
            for i, batch in enumerate(batches)
        }
        for fut in as_completed(futures):
            all_cases.extend(fut.result())
    return all_cases


def generate_cases(state: TestGenState) -> dict[str, Any]:
    rules, contradictions, marked_rules = _rules_for_generation(state)
    if not rules:
        return {
            "positive_cases": [],
            "destructive_cases": [],
            "generated_cases": [],
            "contradictions": contradictions,
            "atomic_rules": marked_rules,
            "current_step": "generate_cases",
        }

    gaps = list(state.get("coverage_gaps") or [])
    is_regen = bool(gaps) and int(state.get("review_round") or 0) > 0

    if is_regen:
        gap_rules = {g["rule_id"] for g in gaps}
        target_rules = [r for r in rules if r.get("rule_id") in gap_rules]
        new_cases = _run_batches_parallel([[r] for r in target_rules], state, gaps)
        existing = list(state.get("generated_cases") or [])
        merged = existing + new_cases
        return {
            "generated_cases": merged,
            "positive_cases": [c for c in merged if c.get("test_type") == "positive"],
            "destructive_cases": [
                c for c in merged if c.get("test_type") in ("negative", "boundary", "edge")
            ],
            "contradictions": contradictions,
            "atomic_rules": marked_rules,
            "current_step": "generate_cases",
        }

    # Generate each requirement in its own LLM call. This is intentionally more
    # constrained than batching many requirements together: each output case must
    # map clearly to exactly one source requirement ID.
    batches = [[r] for r in rules]
    all_cases = _run_batches_parallel(batches, state, None)
    return {
        "generated_cases": all_cases,
        "positive_cases": [c for c in all_cases if c.get("test_type") == "positive"],
        "destructive_cases": [
            c for c in all_cases if c.get("test_type") in ("negative", "boundary", "edge")
        ],
        "contradictions": contradictions,
        "atomic_rules": marked_rules,
        "current_step": "generate_cases",
    }
