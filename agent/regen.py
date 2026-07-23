"""Helpers for regenerating incomplete (partial / not covered) requirements."""

from __future__ import annotations

from typing import Any

from agent.coverage import compute_gaps
from agent.exhaustiveness import normalize_level
from agent.state import TestGenState

def incomplete_rule_ids(report: dict[str, Any] | None) -> list[str]:
    """Rule IDs that are partially covered or not covered (not blocked)."""
    ids: list[str] = []
    for row in (report or {}).get("per_rule") or []:
        status = row.get("coverage_status")
        if status in {"partially_covered", "not_covered"}:
            rid = str(row.get("rule_id") or "").strip()
            if rid:
                ids.append(rid)
    return ids


def gaps_for_incomplete_run(last_run: dict[str, Any]) -> list[dict[str, Any]]:
    """Prefer stored coverage_gaps; otherwise recompute from accepted cases."""
    if "coverage_gaps" in last_run:
        return list(last_run.get("coverage_gaps") or [])
    rules = list(last_run.get("atomic_rules") or [])
    cases = list(
        last_run.get("validated_cases")
        or last_run.get("generated_cases")
        or []
    )
    level = normalize_level(last_run.get("exhaustiveness_level"))
    return compute_gaps(rules, cases, level)


def can_regenerate_incomplete(last_run: dict[str, Any] | None) -> bool:
    if not last_run:
        return False
    report = last_run.get("coverage_report") or {}
    if incomplete_rule_ids(report):
        return True
    return bool(gaps_for_incomplete_run(last_run))


def build_regen_feedback(last_run: dict[str, Any]) -> dict[str, list[str]]:
    """Map rule_id → short rejection reasons from the previous run."""
    by_rule: dict[str, list[str]] = {}

    def _add(rid: str, note: str) -> None:
        rid = (rid or "").strip()
        note = (note or "").strip()
        if not rid or not note:
            return
        bucket = by_rule.setdefault(rid, [])
        if note not in bucket:
            bucket.append(note)

    for case in last_run.get("invalid_cases") or []:
        rid = str(case.get("linked_requirement") or "")
        for issue in case.get("constraint_violations") or []:
            _add(rid, f"Constraint: {issue}")

    for case in last_run.get("expectation_rejected_cases") or []:
        rid = str(case.get("linked_requirement") or "")
        for issue in case.get("expectation_violations") or []:
            _add(rid, f"Expectation: {issue}")

    for case in last_run.get("spec_fact_rejected_cases") or []:
        rid = str(case.get("linked_requirement") or "")
        for issue in case.get("spec_fact_violations") or []:
            _add(rid, f"Spec fact: {issue}")

    for case in last_run.get("oracle_rejected_cases") or []:
        rid = str(case.get("linked_requirement") or "")
        for issue in case.get("oracle_findings") or []:
            _add(rid, f"Quality: {issue}")

    return {rid: notes[:5] for rid, notes in by_rule.items()}


def format_regen_feedback_block(notes: list[str]) -> str:
    if not notes:
        return ""
    lines = ["Prior attempt feedback (do not repeat these mistakes):"]
    lines.extend(f"- {n}" for n in notes)
    return "\n".join(lines)


def prepare_incomplete_regen_state(last_run: dict[str, Any]) -> TestGenState:
    """Build a regen initial state: keep accepted cases, fill coverage gaps only."""
    gaps = gaps_for_incomplete_run(last_run)
    prior = list(
        last_run.get("validated_cases")
        or last_run.get("generated_cases")
        or []
    )
    tagged_prior: list[dict[str, Any]] = []
    for case in prior:
        row = dict(case)
        row["_already_persisted"] = True
        tagged_prior.append(row)

    feedback = build_regen_feedback(last_run)
    # Only keep feedback for rules we will regenerate
    gap_rules = {str(g.get("rule_id") or "") for g in gaps}
    feedback = {k: v for k, v in feedback.items() if k in gap_rules}

    review_round = max(1, int(last_run.get("review_round") or 0) + 1)

    state: TestGenState = {
        "project_id": str(last_run.get("project_id") or ""),
        "document_name": last_run.get("document_name") or "",
        "requirement_chunks": list(last_run.get("requirement_chunks") or []),
        "exhaustiveness_level": normalize_level(last_run.get("exhaustiveness_level")),
        "module_hint": last_run.get("module_hint"),
        "use_project_history": bool(last_run.get("use_project_history", True)),
        "atomic_rules": list(last_run.get("atomic_rules") or []),
        "contradictions": list(last_run.get("contradictions") or []),
        "clarifying_questions": list(last_run.get("clarifying_questions") or []),
        "retrieved_bugs": list(last_run.get("retrieved_bugs") or []),
        "retrieved_tcs": list(last_run.get("retrieved_tcs") or []),
        "retrieval_summary": dict(last_run.get("retrieval_summary") or {}),
        "rule_retrievals": dict(last_run.get("rule_retrievals") or {}),
        "rag_stats": dict(last_run.get("rag_stats") or {}),
        "generated_cases": tagged_prior,
        "coverage_gaps": gaps,
        "coverage_report": dict(last_run.get("coverage_report") or {}),
        "review_round": review_round,
        "agent_looped_back": True,
        "regen_mode": True,
        "regen_feedback": feedback,
        "retrieval_loops": int(last_run.get("retrieval_loops") or 0),
        "pending_queries": [],
        "errors": [],
        "invalid_cases": [],
        "expectation_rejected_cases": [],
        "spec_fact_rejected_cases": [],
        "oracle_rejected_cases": [],
        "duplicates": [],
    }
    return state


def incomplete_summary(last_run: dict[str, Any]) -> dict[str, Any]:
    """UI-friendly counts for the regenerate button."""
    report = last_run.get("coverage_report") or {}
    gaps = gaps_for_incomplete_run(last_run)
    rule_ids = sorted({str(g.get("rule_id") or "") for g in gaps if g.get("rule_id")})
    if not rule_ids:
        rule_ids = incomplete_rule_ids(report)
    return {
        "rule_ids": rule_ids,
        "rule_count": len(rule_ids),
        "gap_count": len(gaps),
        "partially_covered": int(report.get("rules_partially_covered") or 0),
        "not_covered": int(report.get("rules_not_covered") or 0),
        "blocked": int(report.get("blocked_rule_count") or 0),
    }
