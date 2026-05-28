"""Shared helpers for project name and module filter labels in Streamlit pages."""

from __future__ import annotations

import re
from typing import Any

# Leading list markers the LLM often embeds (UI/export add their own index).
_STEP_LEADING_NUM = re.compile(
    r"^\s*(?:"
    r"\(\d+\)\s*"
    r"|\d+[\.\)]\s*"
    r"|(?:step\s*)?\d+\s*:\s*"
    r")",
    re.IGNORECASE,
)

MODULE_ALL = "(All modules)"
MODULE_NONE = "(No module)"
MODULE_NONE_SENTINEL = "__none__"


def active_project_name(projects: list[dict[str, Any]], project_id: str) -> str:
    for p in projects:
        if str(p.get("id")) == str(project_id):
            return str(p.get("name") or "Unnamed project")
    return "Unknown project"


def module_filter_options(rows: list[dict[str, Any]]) -> list[str]:
    """Build selectbox options from test case rows (must include 'module' key)."""
    names: set[str] = set()
    has_empty = False
    for row in rows:
        mod = (row.get("module") or "").strip()
        if mod:
            names.add(mod)
        else:
            has_empty = True
    opts = [MODULE_ALL, *sorted(names, key=str.lower)]
    if has_empty:
        opts.append(MODULE_NONE)
    return opts


def resolve_module_filter(label: str) -> str | None:
    """Map UI label to traceability filter: None = all, sentinel = no module, else module name."""
    if label == MODULE_ALL:
        return None
    if label == MODULE_NONE:
        return MODULE_NONE_SENTINEL
    return label


def module_label_for_filter(module_filter: str | None) -> str:
    if module_filter is None:
        return MODULE_ALL
    if module_filter == MODULE_NONE_SENTINEL:
        return MODULE_NONE
    return module_filter


def normalize_test_steps(steps: object) -> list[str]:
    """Coerce DB/LLM steps to a list of non-empty strings."""
    if steps is None:
        return []
    if isinstance(steps, list):
        return [str(s) for s in steps if str(s).strip()]
    text = str(steps).strip()
    return [text] if text else []


def strip_step_number_prefix(step: str) -> str:
    """Remove embedded step numbers (e.g. '1. Click…' -> 'Click…')."""
    text = str(step or "").strip()
    while text:
        match = _STEP_LEADING_NUM.match(text)
        if not match:
            break
        text = text[match.end() :].lstrip()
    return text


def clean_test_steps(steps: object) -> list[str]:
    """Steps ready for display/export numbering (no duplicate 1.1. prefixes)."""
    return [
        strip_step_number_prefix(s)
        for s in normalize_test_steps(steps)
        if strip_step_number_prefix(s)
    ]


def format_numbered_steps_text(steps: object) -> str:
    """Single block of 1. … 2. … lines for CSV/XLSX export."""
    cleaned = clean_test_steps(steps)
    return "\n".join(f"{i}. {s}" for i, s in enumerate(cleaned, start=1))


def test_cases_breakdown_help(trace: dict[str, Any]) -> str:
    """Hover help text for Test cases metric (generated / imported / unlinked)."""
    parts = [
        f"{trace.get('generated', 0)} generated",
        f"{trace.get('imported', 0)} imported",
    ]
    unlinked = trace.get("unlinked", 0)
    if unlinked:
        parts.append(f"{unlinked} unlinked")
    return "Breakdown: " + " · ".join(parts)
