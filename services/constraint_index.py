"""Project-wide constraint index for cross-rule validation."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "price_threshold": ("threshold", "price threshold", "€/kwh", "$/kwh"),
    "the_price_threshold": ("threshold", "price threshold", "€/kwh", "$/kwh"),
    "runtime": ("runtime", "run duration", "cycle length"),
    "duration": ("runtime", "duration", "hours long"),
}

_PRICE_SIGNAL_RE = re.compile(
    r"\bprice\b|€\s*/\s*kwh|\$\s*/\s*kwh|€/kwh|\$/kwh|\bkwh\b",
    re.IGNORECASE,
)
_NON_PRICE_THRESHOLD_RE = re.compile(
    r"\b(?:availability|uptime|downtime|sla|compliant|compliance)\b|"
    r"\bminimum\s+threshold\b|"
    r"\d+(?:[.,]\d+)?\s*%",
    re.IGNORECASE,
)


def _field_tokens(field: str) -> list[str]:
    return [tok for tok in re.split(r"[_\s]+", field.lower()) if tok and tok not in {"the", "a", "an"}]


def _is_price_threshold_field(field: str) -> bool:
    f = (field or "").strip().lower()
    return f in {"price_threshold", "the_price_threshold"} or (
        f.endswith("_threshold") and "price" in f
    )


def _mentions_price_threshold(text: str) -> bool:
    """True only for price/energy threshold wording — not SLA 'minimum threshold'."""
    lowered = (text or "").lower()
    if "price threshold" in lowered:
        return True
    if "threshold mode" in lowered:
        return True
    if "threshold" not in lowered:
        # Energy unit alone is not enough to claim the field is under test.
        return False
    if _PRICE_SIGNAL_RE.search(lowered):
        return True
    # Bare "threshold" without price signals: allow only when not clearly SLA/%.
    if _NON_PRICE_THRESHOLD_RE.search(lowered):
        return False
    return True


def _constraint_key(constraint: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(sorted((k, str(v)) for k, v in constraint.items() if k != "source_rule_id"))


def build_project_constraint_index(
    rules: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group parsed constraints by field across all requirements."""
    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        rid = str(rule.get("rule_id") or "").strip()
        for constraint in rule.get("constraints") or []:
            field = str(constraint.get("field") or "value").strip() or "value"
            row = dict(constraint)
            if rid:
                row["source_rule_id"] = rid
            by_field[field].append(row)
    return dict(by_field)


def case_mentions_field(case_text: str, field: str) -> bool:
    """True when case text is exercising values for a shared constraint field."""
    lowered = (case_text or "").lower()
    if _is_price_threshold_field(field):
        return _mentions_price_threshold(case_text)

    tokens = _field_tokens(field)
    if tokens and any(tok in lowered for tok in tokens):
        return True
    aliases = _FIELD_ALIASES.get(field, ())
    if aliases and any(alias in lowered for alias in aliases):
        return True
    if field.endswith("_threshold") or field == "threshold":
        # Non-price thresholds: keep simple token match.
        return "threshold" in lowered
    return False


def _merge_applicable_constraints(
    text: str,
    *,
    linked_rule: dict[str, Any] | None,
    project_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Linked-rule constraints plus cross-rule constraints when text mentions the field."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    linked_id = str((linked_rule or {}).get("rule_id") or "").strip()

    for constraint in (linked_rule or {}).get("constraints") or []:
        key = _constraint_key(constraint)
        if key in seen:
            continue
        seen.add(key)
        row = dict(constraint)
        if linked_id and not row.get("source_rule_id"):
            row["source_rule_id"] = linked_id
        merged.append(row)

    for field, constraints in project_index.items():
        if not case_mentions_field(text, field):
            continue
        for constraint in constraints:
            source_id = str(constraint.get("source_rule_id") or "").strip()
            if source_id and source_id == linked_id:
                continue
            key = _constraint_key(constraint)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(constraint))

    return merged


def _rule_text(rule: dict[str, Any]) -> str:
    return "\n".join(
        [
            str(rule.get("summary") or ""),
            str(rule.get("detail") or ""),
        ]
    )


def constraints_for_rule(
    rule: dict[str, Any],
    *,
    project_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Constraints on this rule plus applicable cross-rule limits for generation prompts."""
    return _merge_applicable_constraints(
        _rule_text(rule),
        linked_rule=rule,
        project_index=project_index,
    )


def constraints_for_case(
    case: dict[str, Any],
    *,
    linked_rule: dict[str, Any] | None,
    project_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Linked-rule constraints plus applicable cross-rule constraints."""
    case_text = "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("preconditions") or ""),
            str(case.get("expected_result") or ""),
            *(
                [str(s) for s in case.get("steps") or []]
                if isinstance(case.get("steps"), list)
                else [str(case.get("steps") or "")]
            ),
        ]
    )
    return _merge_applicable_constraints(
        case_text,
        linked_rule=linked_rule,
        project_index=project_index,
    )


def _fmt_num(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:g}"


def format_constraint_line(constraint: dict[str, Any]) -> str:
    """Single human-readable constraint line for LLM prompts."""
    field = str(constraint.get("field") or "value")
    source = str(constraint.get("source_rule_id") or "").strip()
    prefix = f"{field} (from {source})" if source else field
    ctype = constraint.get("type")
    if ctype == "range":
        unit = str(constraint.get("unit") or "").strip()
        unit_s = f" {unit}" if unit else ""
        return (
            f"{prefix}: {_fmt_num(constraint['min'])}–{_fmt_num(constraint['max'])}{unit_s}"
        )
    if ctype == "increment":
        unit = str(constraint.get("unit") or "").strip()
        unit_s = f" {unit}" if unit else ""
        return f"{prefix}: increments of {_fmt_num(constraint['step'])}{unit_s}"
    if ctype == "enum":
        values = ", ".join(str(v) for v in constraint.get("values") or [])
        return f"{prefix}: one of: {values}"
    if ctype == "format":
        return f"{prefix}: format {constraint.get('pattern')}"
    if ctype == "int_range":
        unit = str(constraint.get("unit") or "").strip()
        unit_s = f" {unit}" if unit else ""
        return (
            f"{prefix}: {_fmt_num(constraint['min'])}–{_fmt_num(constraint['max'])}{unit_s}"
        )
    return prefix


def format_constraints_for_prompt(constraints: list[dict[str, Any]]) -> str:
    """Block of parsed limits to inject into generation prompts."""
    if not constraints:
        return ""
    lines = [f"- {format_constraint_line(c)}" for c in constraints]
    return (
        "Applicable constraints (use these exact limits in test data):\n"
        + "\n".join(lines)
    )
