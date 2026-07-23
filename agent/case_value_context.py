"""Shared helpers for values under test in constraint and expectation validation."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from services.constraint_index import (
    _FIELD_ALIASES,
    _is_price_threshold_field,
    _mentions_price_threshold,
)

ENTRY_LINE_RE = re.compile(
    r"(?i)\b(enter|set|input|type|configure|provide|attempt)\b",
)

UNDER_TEST_NUM_RE = re.compile(
    r"(?P<sign>-)?\s*(?P<currency>[$€])?\s*(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>€\/kWh|\$\/kWh|USD|EUR|kWh|MB|GB|px|ms|s|hours?|minutes?|%)?",
    re.IGNORECASE,
)

_REJECTION_NEGATED_RE = re.compile(
    r"\b(?:"
    r"not|n't|never|without|no\s+longer|does\s+not|do\s+not|did\s+not|"
    r"is\s+not|are\s+not|was\s+not|were\s+not|must\s+not\s+be|"
    r"should\s+not\s+be|cannot\s+be|can\s+not\s+be"
    r")\s+(?:\w+\s+){0,3}?"
    r"(?:"
    r"reject(?:ed|ion|s)?|invalid(?:ated)?|blocked|denied|"
    r"fail(?:s|ed|ure)?|error(?:\s+message)?"
    r")\b",
    re.IGNORECASE,
)

REJECTION_EXPECTED_RE = re.compile(
    r"\b("
    r"reject(?:ed|ion|s)?|"
    r"invalid(?:ated)?|"
    r"not\s+(?:accepted|allowed|saved|permitted)|"
    r"denied|"
    r"blocked|"
    r"cannot\s+(?:be\s+)?(?:save|accept|enter)|"
    r"error(?:\s+message)?|"
    r"fail(?:s|ed|ure)?|"
    r"must\s+not\s+(?:accept|save|allow)"
    r")\b",
    re.IGNORECASE,
)

_SUCCESS_EXPECTED_RE = re.compile(
    r"\b("
    r"success(?:ful(?:ly)?)?|"
    r"accepted|allowed|saved|permitted|"
    r"starts?\s+successfully|"
    r"is\s+(?:applied|accepted|saved|allowed)|"
    r"remains?\s+available|"
    r"not\s+blocked"
    r")\b",
    re.IGNORECASE,
)

NEGATIVE_TEST_TYPES = frozenset({"negative", "boundary", "edge"})


def field_tokens(field: str) -> list[str]:
    return [tok for tok in re.split(r"[_\s]+", field.lower()) if tok]


def near_field(text: str, field: str, start: int) -> bool:
    tokens = field_tokens(field)
    if not tokens:
        return True
    window = text[max(0, start - 80) : min(len(text), start + 80)].lower()
    return any(tok in window for tok in tokens)


_REJECTION_SIGNAL_RE = re.compile(
    r"\b(?:reject(?:ed|ion|s)?|invalid(?:ated)?|denied|"
    r"error(?:\s+message)?|fail(?:s|ed|ure)?)\b",
    re.IGNORECASE,
)


def expects_rejection(expected_result: str) -> bool:
    text = expected_result or ""
    if not text.strip():
        return False
    if _REJECTION_NEGATED_RE.search(text):
        return False
    if _SUCCESS_EXPECTED_RE.search(text) and not _REJECTION_SIGNAL_RE.search(text):
        return False
    return bool(REJECTION_EXPECTED_RE.search(text))


def is_intentional_negative_constraint_test(case: dict[str, Any]) -> bool:
    test_type = str(case.get("test_type") or "").strip().lower()
    return test_type in NEGATIVE_TEST_TYPES and expects_rejection(
        str(case.get("expected_result") or "")
    )


def steps_lines(case: dict[str, Any]) -> list[str]:
    steps = case.get("steps") or []
    if isinstance(steps, list):
        return [str(step) for step in steps if str(step).strip()]
    text = str(steps).strip()
    return [text] if text else []


def line_mentions_field(line: str, field: str) -> bool:
    """Field must appear on the same line as the value being checked."""
    lowered = line.lower()
    normalized_field = field.replace("_", " ")
    if _is_price_threshold_field(field):
        return _mentions_price_threshold(line)
    if normalized_field in lowered or field.lower() in lowered:
        return True
    if field.endswith("_threshold") or field == "threshold":
        return "threshold" in lowered
    tokens = field_tokens(field)
    if tokens and any(tok in lowered for tok in tokens):
        return True
    aliases = _FIELD_ALIASES.get(field, ())
    unit_only_aliases = {"€/kwh", "$/kwh"}
    for alias in aliases:
        if alias not in lowered:
            continue
        if alias in unit_only_aliases:
            if tokens and any(tok in lowered for tok in tokens):
                return True
            continue
        return True
    return False


def unit_compatible_with_field(
    match: re.Match[str],
    field: str,
    constraints: list[dict[str, Any]],
) -> bool:
    """False when the parsed unit clearly conflicts with this field's constraint units."""
    parsed = (match.group("unit") or "").strip().lower()
    if not parsed:
        return True
    expected_units = {
        str(row.get("unit") or "").strip().lower()
        for row in field_constraints(constraints, field)
        if row.get("unit")
    }
    if not expected_units:
        return True
    # Percent values must not be checked against €/kWh (or similar) fields.
    if parsed in {"%", "percent", "percentage"}:
        if any("kwh" in u or u.startswith("€") or u.startswith("$") for u in expected_units):
            return False
        if any(u in {"%", "percent", "percentage"} for u in expected_units):
            return True
        return False
    for expected in expected_units:
        if expected in parsed or parsed in expected:
            return True
        if expected.startswith("€") and match.group("currency") == "€":
            return True
    return False


def unit_match_for_field(match: re.Match[str], field: str, constraints: list[dict[str, Any]]) -> bool:
    """True when a parsed unit on an entry line matches this field's constraints."""
    parsed = (match.group("unit") or "").strip().lower()
    if not parsed:
        return False
    if not unit_compatible_with_field(match, field, constraints):
        return False
    for row in field_constraints(constraints, field):
        expected = str(row.get("unit") or "").strip().lower()
        if not expected:
            continue
        if expected in parsed or parsed in expected:
            return True
        if expected.startswith("€") and match.group("currency") == "€":
            return True
    return False


def _parse_numeric_match(match: re.Match[str]) -> float:
    raw = match.group("num")
    value = float(raw.replace(",", "."))
    if match.group("sign") == "-":
        value = -value
    return value


def _is_spot_price_context(line: str) -> bool:
    lowered = line.lower()
    return "spot price" in lowered or (
        "display" in lowered and "threshold" not in lowered
    )


def values_under_test_by_field(
    case: dict[str, Any],
    constraints: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Numbers entered in steps for a constrained field."""
    fields = {str(c.get("field") or "value") for c in constraints}
    out: dict[str, list[float]] = defaultdict(list)
    seen: set[tuple[str, float]] = set()
    for line in steps_lines(case):
        if not ENTRY_LINE_RE.search(line):
            continue
        for match in UNDER_TEST_NUM_RE.finditer(line):
            value = _parse_numeric_match(match)
            for field in fields:
                if not unit_compatible_with_field(match, field, constraints):
                    continue
                on_field = line_mentions_field(line, field) and near_field(
                    line, field, match.start()
                )
                threshold_field = field in {
                    "price_threshold",
                    "the_price_threshold",
                } or field.endswith("_threshold")
                on_unit = unit_match_for_field(match, field, constraints)
                if threshold_field and not on_field:
                    if _is_spot_price_context(line):
                        continue
                    if not (ENTRY_LINE_RE.search(line) and on_unit):
                        continue
                elif not on_field and not (ENTRY_LINE_RE.search(line) and on_unit):
                    continue
                key = (field, value)
                if key in seen:
                    break
                seen.add(key)
                out[field].append(value)
                break
    return out


def accepted_outcome_values(
    case: dict[str, Any],
    field: str,
    constraints: list[dict[str, Any]] | None = None,
) -> list[float]:
    """Numeric outcomes in expected_result that should satisfy constraints (positive cases)."""
    expected = str(case.get("expected_result") or "")
    if not expected or expects_rejection(expected):
        return []
    if not line_mentions_field(expected, field):
        return []
    values: list[float] = []
    seen: set[float] = set()
    constraint_rows = constraints or []
    for match in UNDER_TEST_NUM_RE.finditer(expected):
        if constraint_rows and not unit_compatible_with_field(match, field, constraint_rows):
            continue
        if not near_field(expected, field, match.start()):
            continue
        value = _parse_numeric_match(match)
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def field_constraints(
    constraints: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    return [c for c in constraints if str(c.get("field") or "value") == field]


def value_violates_field_constraints(
    value: float,
    field: str,
    constraints: list[dict[str, Any]],
) -> bool:
    for row in field_constraints(constraints, field):
        ctype = row.get("type")
        if ctype == "range":
            if value < float(row["min"]) or value > float(row["max"]):
                return True
        elif ctype == "increment":
            step = float(row["step"])
            if step and not math.isclose(
                value / step,
                round(value / step),
                rel_tol=0,
                abs_tol=1e-6,
            ):
                return True
        elif ctype == "int_range":
            iv = int(value)
            if iv < int(row["min"]) or iv > int(row["max"]):
                return True
        elif ctype == "enum":
            allowed = {str(v).upper() for v in row.get("values") or []}
            token = str(value).upper()
            if allowed and token not in allowed:
                return True
    return False


def value_satisfies_field_constraints(
    value: float,
    field: str,
    constraints: list[dict[str, Any]],
) -> bool:
    if not field_constraints(constraints, field):
        return False
    return not value_violates_field_constraints(value, field, constraints)


def numeric_candidates_for_field(
    case: dict[str, Any],
    constraints: list[dict[str, Any]],
    field: str,
) -> list[float]:
    """Values that must satisfy numeric constraints — not intentional negative probes."""
    if is_intentional_negative_constraint_test(case):
        return []
    under_test = values_under_test_by_field(case, constraints)
    candidates = list(under_test.get(field, []))
    test_type = str(case.get("test_type") or "").strip().lower()
    if test_type == "positive":
        candidates.extend(accepted_outcome_values(case, field, constraints))
    deduped: list[float] = []
    seen: set[float] = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def entry_uses_wrong_currency(case: dict[str, Any], field: str, expected_unit: str) -> bool:
    if not expected_unit.startswith("€"):
        return False
    for line in steps_lines(case):
        if not ENTRY_LINE_RE.search(line):
            continue
        if not line_mentions_field(line, field):
            continue
        if "$" in line:
            return True
    return False
