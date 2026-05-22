"""Shared helpers for project name and module filter labels in Streamlit pages."""

from __future__ import annotations

from typing import Any

MODULE_ALL = "(All modules)"
MODULE_NONE = "(No module)"
MODULE_NONE_SENTINEL = "__none__"


def active_project_name(projects: list[dict[str, Any]], project_id: str) -> str:
    for p in projects:
        if p.get("id") == project_id:
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
