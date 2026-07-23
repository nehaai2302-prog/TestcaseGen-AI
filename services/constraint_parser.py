"""Parse simple structured constraints from requirement text."""

from __future__ import annotations

import re
from typing import Any

_NUM = r"\d+(?:[.,]\d+)?"
_UNIT_RE = r"(?:€\/kWh|\$\/kWh|€|USD|EUR|kWh|MB|GB|px|ms|s|minutes?|hours?)"
_RANGE_RE = re.compile(
    rf"(?P<label>[A-Za-z][A-Za-z0-9_ /-]{{1,40}}?)\s+(?P<min>{_NUM})\s*[–-]\s*(?P<max>{_NUM})(?:\s*(?P<unit>{_UNIT_RE}))?",
    re.IGNORECASE,
)
_BETWEEN_RANGE_RE = re.compile(
    rf"(?P<label>[A-Za-z][A-Za-z0-9_ /-]+)\s+shall\s+be\s+(?:a\s+)?value\s+between\s+"
    rf"(?P<min>{_NUM})\s+and\s+(?P<max>{_NUM})(?:\s*(?P<unit>{_UNIT_RE}))?",
    re.IGNORECASE,
)
_INCREMENT_RE = re.compile(
    rf"(?:for\s+(?P<label1>[A-Za-z][A-Za-z0-9_ /-]{{1,40}}?)\s*,?\s*)?(?:in\s+)?increments?\s+of\s+(?P<step>{_NUM})(?:\s*(?P<unit>{_UNIT_RE}))?",
    re.IGNORECASE,
)
_ENUM_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9_ /-]{1,40}?)\s+(?:must\s+be\s+)?one\s+of:\s*(?P<values>[A-Za-z0-9_-]+(?:\s*,\s*[A-Za-z0-9_-]+)+)",
    re.IGNORECASE,
)
_FORMAT_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9_ /-]{1,40}?)\s+(?:must\s+be\s+in|shall\s+use|uses)\s+(?P<pattern>[A-Za-z0-9:._-]+)\s+format",
    re.IGNORECASE,
)
_INT_RANGE_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9_ /-]{1,40}?)\s+(?P<min>\d+)\s*[–-]\s*(?P<max>\d+)\s*(?P<unit>hours?|items?|minutes?|days?)",
    re.IGNORECASE,
)


def _to_float(text: str) -> float:
    return float(text.replace(",", "."))


def _clean_label(label: str | None) -> str:
    text = (label or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if text.startswith("the_"):
        text = text[4:]
    return text or "value"


def extract_constraints(text: str) -> list[dict[str, Any]]:
    constraints: list[dict[str, Any]] = []
    last_field = "value"
    src = text or ""

    for match in _RANGE_RE.finditer(src):
        field = _clean_label(match.group("label"))
        last_field = field
        min_v = _to_float(match.group("min"))
        max_v = _to_float(match.group("max"))
        if match.group("min").isdigit() and match.group("max").isdigit() and match.group("unit"):
            unit = str(match.group("unit") or "")
            if unit.lower().startswith(("hour", "item", "minute", "day")):
                constraints.append(
                    {
                        "field": field,
                        "type": "int_range",
                        "min": int(min_v),
                        "max": int(max_v),
                        "unit": unit,
                    }
                )
                continue
        constraints.append(
            {
                "field": field,
                "type": "range",
                "min": min_v,
                "max": max_v,
                "unit": (match.group("unit") or "").strip() or None,
            }
        )

    for match in _BETWEEN_RANGE_RE.finditer(src):
        field = _clean_label(match.group("label"))
        last_field = field
        constraints.append(
            {
                "field": field,
                "type": "range",
                "min": _to_float(match.group("min")),
                "max": _to_float(match.group("max")),
                "unit": (match.group("unit") or "").strip() or None,
            }
        )

    for match in _INT_RANGE_RE.finditer(src):
        field = _clean_label(match.group("label"))
        constraints.append(
            {
                "field": field,
                "type": "int_range",
                "min": int(match.group("min")),
                "max": int(match.group("max")),
                "unit": (match.group("unit") or "").strip(),
            }
        )

    for match in _INCREMENT_RE.finditer(src):
        field = _clean_label(match.group("label1")) if match.group("label1") else last_field
        constraints.append(
            {
                "field": field,
                "type": "increment",
                "step": _to_float(match.group("step")),
                "unit": (match.group("unit") or "").strip() or None,
            }
        )

    for match in _ENUM_RE.finditer(src):
        field = _clean_label(match.group("label"))
        values = [v.strip() for v in match.group("values").split(",") if v.strip()]
        constraints.append(
            {
                "field": field,
                "type": "enum",
                "values": values,
            }
        )

    for match in _FORMAT_RE.finditer(src):
        field = _clean_label(match.group("label"))
        constraints.append(
            {
                "field": field,
                "type": "format",
                "pattern": match.group("pattern").strip(),
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in constraints:
        key = tuple(sorted((k, str(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped

