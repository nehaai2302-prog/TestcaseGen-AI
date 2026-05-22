"""Deterministic coverage checks against exhaustiveness quotas."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agent.exhaustiveness import DESTRUCTIVE_TYPES, POSITIVE_TYPES, quotas_for_level


def _rule_key(case: dict[str, Any]) -> str | None:
    lr = (case.get("linked_requirement") or "").strip()
    if lr:
        return lr
    return None


def count_by_rule_and_type(cases: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in cases:
        rid = _rule_key(c)
        if not rid:
            continue
        t = (c.get("test_type") or "positive").strip().lower()
        counts[rid][t] += 1
    return {k: dict(v) for k, v in counts.items()}


def compute_gaps(
    atomic_rules: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    level: str,
) -> list[dict[str, Any]]:
    """Return gaps: rule_id, test_type, needed, have."""
    quotas = quotas_for_level(level)
    counts = count_by_rule_and_type(cases)
    gaps: list[dict[str, Any]] = []

    for rule in atomic_rules:
        rid = rule.get("rule_id", "")
        if not rid:
            continue
        have = counts.get(rid, {})
        for test_type, required in quotas.items():
            if required <= 0:
                continue
            got = have.get(test_type, 0)
            if got < required:
                gaps.append(
                    {
                        "rule_id": rid,
                        "test_type": test_type,
                        "needed": required - got,
                        "required": required,
                        "have": got,
                    }
                )
    return gaps


def build_coverage_report(
    atomic_rules: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    level: str,
) -> dict[str, Any]:
    quotas = quotas_for_level(level)
    counts = count_by_rule_and_type(cases)
    gaps = compute_gaps(atomic_rules, cases, level)
    rules_ok = 0
    per_rule: list[dict[str, Any]] = []

    for rule in atomic_rules:
        rid = rule.get("rule_id", "")
        have = counts.get(rid, {})
        rule_gaps = [g for g in gaps if g["rule_id"] == rid]
        satisfied = len(rule_gaps) == 0
        if satisfied:
            rules_ok += 1
        per_rule.append(
            {
                "rule_id": rid,
                "summary": rule.get("summary", ""),
                "counts": {t: have.get(t, 0) for t in quotas},
                "required": quotas,
                "satisfied": satisfied,
            }
        )

    return {
        "level": level,
        "rule_count": len(atomic_rules),
        "rules_fully_covered": rules_ok,
        "total_cases": len(cases),
        "expected_cases": len(atomic_rules) * sum(quotas.values()) if atomic_rules else 0,
        "gap_count": len(gaps),
        "gaps": gaps,
        "per_rule": per_rule,
    }


def gaps_for_agent(
    gaps: list[dict[str, Any]],
    agent: str,
) -> list[dict[str, Any]]:
    """Filter gaps for happy_path (positive) or destructive (negative/boundary/edge)."""
    allowed = POSITIVE_TYPES if agent == "happy_path" else DESTRUCTIVE_TYPES
    return [g for g in gaps if g.get("test_type") in allowed]
