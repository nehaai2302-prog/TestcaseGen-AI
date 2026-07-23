"""Contradiction detection helpers for the Analyst and coverage reviewer."""

from __future__ import annotations

from typing import Any

STATUS_ACTIVE = "active"
STATUS_REQUIRES_CLARIFICATION = "requires_clarification"


def contradiction_blocked_ids(contradictions: list[dict[str, Any]]) -> set[str]:
    """Collect every rule_id that must not be generated until clarified."""
    blocked: set[str] = set()
    for row in contradictions:
        rid = (row.get("rule_id") or "").strip()
        if rid:
            blocked.add(rid)
        related = row.get("related_rule_id") or row.get("contradicts_rule_id")
        if related:
            blocked.add(str(related).strip())
        for rel in row.get("related_rule_ids") or []:
            text = str(rel).strip()
            if text:
                blocked.add(text)
    return blocked


def mark_rule_statuses(
    rules: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocked = contradiction_blocked_ids(contradictions)
    marked: list[dict[str, Any]] = []
    for rule in rules:
        row = dict(rule)
        rid = (row.get("rule_id") or "").strip()
        if rid in blocked:
            row["status"] = STATUS_REQUIRES_CLARIFICATION
        else:
            row["status"] = row.get("status") or STATUS_ACTIVE
        marked.append(row)
    return marked


def generatable_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rules if r.get("status") != STATUS_REQUIRES_CLARIFICATION]


def summarize_contradictions(contradictions: list[dict[str, Any]]) -> str:
    if not contradictions:
        return ""
    lines: list[str] = []
    for row in contradictions:
        rid = row.get("rule_id") or "?"
        issue = (row.get("issue") or "").strip() or "Contradiction detected"
        lines.append(f"{rid}: {issue}")
    return "; ".join(lines)
