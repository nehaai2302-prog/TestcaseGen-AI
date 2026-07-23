"""Validate generated cases against parsed requirement constraints."""

from __future__ import annotations

import math
import re
from typing import Any

from agent.case_value_context import (
    entry_uses_wrong_currency,
    is_intentional_negative_constraint_test,
    numeric_candidates_for_field,
)
from agent.state import TestGenState
from services.constraint_index import build_project_constraint_index, constraints_for_case

_NUM_RE = re.compile(
    r"(?P<currency>[$€])?\s*(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>€\/kWh|\$\/kWh|USD|EUR|kWh|MB|GB|px|ms|s|hours?|minutes?|%)?",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _case_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_text = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("description") or ""),
            str(case.get("preconditions") or ""),
            steps_text,
            str(case.get("expected_result") or ""),
        ]
    )


def field_tokens(field: str) -> list[str]:
    return [tok for tok in re.split(r"[_\s]+", field.lower()) if tok]


def near_field(text: str, field: str, start: int) -> bool:
    tokens = field_tokens(field)
    if not tokens:
        return True
    window = text[max(0, start - 80) : min(len(text), start + 80)].lower()
    return any(tok in window for tok in tokens)


def _num_matches(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _NUM_RE.finditer(text):
        raw = m.group("num")
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            continue
        out.append(
            {
                "value": value,
                "currency": m.group("currency") or "",
                "unit": (m.group("unit") or "").strip(),
                "start": m.start(),
                "end": m.end(),
            }
        )
    return out


def _violations_for_numeric_value(value: float, c: dict[str, Any]) -> list[str]:
    field = str(c.get("field") or "value")
    ctype = c.get("type")
    unit = str(c.get("unit") or "")
    if ctype == "range":
        min_v = float(c.get("min"))
        max_v = float(c.get("max"))
        if value < min_v or value > max_v:
            return [f"{field}: value {value} violates range {min_v}-{max_v}{unit}"]
    elif ctype == "increment":
        step = float(c.get("step"))
        if step and not math.isclose(
            value / step,
            round(value / step),
            rel_tol=0,
            abs_tol=1e-6,
        ):
            return [f"{field}: value {value} is not a valid increment of {step}"]
    elif ctype == "int_range":
        iv = int(value)
        min_v = int(c.get("min"))
        max_v = int(c.get("max"))
        if iv < min_v or iv > max_v:
            return [f"{field}: value {iv} violates integer range {min_v}-{max_v}"]
    return []


def _validate_enum(case_text: str, c: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    values = [str(v) for v in c.get("values") or []]
    if not values:
        return violations
    field = str(c.get("field") or "value")
    upper_tokens = re.findall(r"\b[A-Z0-9_-]{2,10}\b", case_text)
    allowed = {v.upper() for v in values}
    for token in upper_tokens:
        if token in allowed:
            continue
        if near_field(case_text, field, case_text.find(token)):
            violations.append(f"{field}: value {token} is not in allowed set {values}")
    return violations


def _validate_format(case_text: str, c: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    pattern = str(c.get("pattern") or "")
    field = str(c.get("field") or "value")
    if pattern == "hh:00":
        for match in _TIME_RE.findall(case_text):
            if not match.endswith(":00"):
                violations.append(
                    f"{field}: time {match} does not match {pattern} format"
                )
    return violations


def _constraint_violations(case: dict[str, Any], constraints: list[dict[str, Any]]) -> list[str]:
    text = _case_text(case)
    intentional_negative = is_intentional_negative_constraint_test(case)
    all_violations: list[str] = []
    seen: set[str] = set()

    for c in constraints:
        source = str(c.get("source_rule_id") or "").strip()
        field_name = str(c.get("field") or "value")
        prefix = field_name if not source else f"{field_name} (from {source})"
        ctype = c.get("type")
        raw: list[str] = []

        if ctype in ("range", "increment", "int_range"):
            if not intentional_negative:
                for value in numeric_candidates_for_field(case, constraints, field_name):
                    raw.extend(_violations_for_numeric_value(value, c))
            if ctype == "range" and not intentional_negative:
                unit = str(c.get("unit") or "")
                if entry_uses_wrong_currency(case, field_name, unit):
                    raw.append(f"{field_name}: wrong currency ($) for expected {unit}")
        elif ctype == "enum":
            raw = _validate_enum(text, c)
        elif ctype == "format":
            raw = _validate_format(text, c)

        for issue in raw:
            if issue.startswith(f"{field_name}:"):
                formatted = issue.replace(f"{field_name}:", f"{prefix}:", 1)
            else:
                formatted = f"{prefix}: {issue}"
            if formatted in seen:
                continue
            seen.add(formatted)
            all_violations.append(formatted)

    return all_violations


def validate_constraints(state: TestGenState) -> dict[str, Any]:
    rules = list(state.get("atomic_rules") or [])
    generated = list(state.get("generated_cases") or [])
    if not generated:
        return {
            "generated_cases": [],
            "invalid_cases": [],
            "constraint_violations": [],
            "constraint_stats": {"input_cases": 0, "valid_cases": 0, "invalid_cases": 0},
            "current_step": "validate_constraints",
        }

    rule_by_id = {str(r.get("rule_id")): r for r in rules if r.get("rule_id")}
    project_index = build_project_constraint_index(rules)
    valid_cases: list[dict[str, Any]] = []
    invalid_cases: list[dict[str, Any]] = []
    violations_summary: list[dict[str, Any]] = []

    for case in generated:
        # Regen / fill-gaps: keep already-saved cases as-is (same as dedup).
        if case.get("_already_persisted"):
            valid_cases.append(case)
            continue
        rid = str(case.get("linked_requirement") or "")
        linked_rule = rule_by_id.get(rid) or {}
        constraints = constraints_for_case(
            case,
            linked_rule=linked_rule,
            project_index=project_index,
        )
        if not constraints:
            valid_cases.append(case)
            continue
        violations = _constraint_violations(case, constraints)
        if violations:
            invalid = dict(case)
            invalid["constraint_violations"] = violations
            invalid_cases.append(invalid)
            violations_summary.append(
                {
                    "linked_requirement": rid,
                    "title": case.get("title"),
                    "violations": violations,
                }
            )
        else:
            valid_cases.append(case)

    stats = {
        "input_cases": len(generated),
        "valid_cases": len(valid_cases),
        "invalid_cases": len(invalid_cases),
    }

    reasoning = state.get("reasoning") or ""
    if invalid_cases:
        reasoning = (
            reasoning
            + "\nConstraint validation rejected "
            + f"{len(invalid_cases)} case(s) before coverage/dedup."
        ).strip()

    return {
        "generated_cases": valid_cases,
        "invalid_cases": invalid_cases,
        "constraint_violations": violations_summary,
        "constraint_stats": stats,
        "reasoning": reasoning,
        "current_step": "validate_constraints",
    }
