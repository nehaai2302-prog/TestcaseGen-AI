"""Reject cases that assert times or DST day lengths conflicting with the spec."""

from __future__ import annotations

from typing import Any

from agent.state import TestGenState
from services.spec_facts import (
    build_project_spec_facts,
    extract_spec_facts,
    spec_fact_violations,
    spec_fact_warnings,
)


def _rule_text(rule: dict[str, Any]) -> str:
    return " ".join(
        [
            str(rule.get("summary") or ""),
            str(rule.get("detail") or ""),
            str(rule.get("text") or ""),
        ]
    )


def facts_for_case(
    case: dict[str, Any],
    *,
    linked_rule: dict[str, Any],
    project_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prefer linked-rule facts, then fall back to the full project index."""
    local = extract_spec_facts(_rule_text(linked_rule))
    rid = str(linked_rule.get("rule_id") or case.get("linked_requirement") or "")
    tagged_local = []
    for fact in local:
        row = dict(fact)
        if rid:
            row["source_rule_id"] = rid
        tagged_local.append(row)
    if tagged_local:
        # Still include project DST / quiet-hour facts from other rules so
        # cross-rule windows (e.g. quiet hours defined once) are visible.
        merged = list(tagged_local)
        seen = {
            (
                f.get("type"),
                f.get("start"),
                f.get("end"),
                f.get("transition"),
                f.get("hours"),
            )
            for f in merged
        }
        for fact in project_facts:
            key = (
                fact.get("type"),
                fact.get("start"),
                fact.get("end"),
                fact.get("transition"),
                fact.get("hours"),
            )
            if key not in seen:
                seen.add(key)
                merged.append(fact)
        return merged
    return list(project_facts)


def validate_spec_facts(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    generated = list(state.get("generated_cases") or [])
    if not generated:
        return {
            "generated_cases": [],
            "spec_fact_rejected_cases": [],
            "spec_fact_violations": [],
            "spec_fact_stats": {
                "input_cases": 0,
                "valid_cases": 0,
                "rejected_cases": 0,
            },
            "current_step": "validate_spec_facts",
        }

    rule_by_id = {str(r.get("rule_id")): r for r in rules if r.get("rule_id")}
    project_facts = build_project_spec_facts(rules)
    valid_cases: list[dict[str, Any]] = []
    rejected_cases: list[dict[str, Any]] = []
    violations_summary: list[dict[str, Any]] = []

    for case in generated:
        rid = str(case.get("linked_requirement") or "")
        linked_rule = rule_by_id.get(rid) or {}
        facts = facts_for_case(
            case,
            linked_rule=linked_rule,
            project_facts=project_facts,
        )
        if not facts:
            valid_cases.append(case)
            continue

        violations = spec_fact_violations(case, facts)
        warnings = spec_fact_warnings(case, facts)
        if violations:
            rejected = dict(case)
            rejected["spec_fact_violations"] = violations
            if warnings:
                rejected["spec_fact_warnings"] = warnings
            rejected_cases.append(rejected)
            violations_summary.append(
                {
                    "linked_requirement": rid,
                    "title": case.get("title"),
                    "violations": violations,
                }
            )
        else:
            kept = dict(case)
            if warnings:
                kept["spec_fact_warnings"] = warnings
            valid_cases.append(kept)

    stats = {
        "input_cases": len(generated),
        "valid_cases": len(valid_cases),
        "rejected_cases": len(rejected_cases),
    }

    reasoning = state.get("reasoning") or ""
    if rejected_cases:
        reasoning = (
            reasoning
            + "\nSpec-fact validation rejected "
            + f"{len(rejected_cases)} case(s) with times or DST day lengths "
            + "not matching the specification."
        ).strip()

    return {
        "generated_cases": valid_cases,
        "spec_fact_rejected_cases": rejected_cases,
        "spec_fact_violations": violations_summary,
        "spec_fact_stats": stats,
        "reasoning": reasoning,
        "current_step": "validate_spec_facts",
    }
