"""Reject vague or unexecutable generated cases using spec-agnostic QA checks."""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.ambiguity import contradiction_blocked_ids, mark_rule_statuses
from agent.contradiction_scan import (
    merge_contradictions,
    scan_generated_case_contradictions,
    scan_spec_contradictions,
)
from agent.execution_profile import normalize_execution_profile
from agent.substance import (
    comparison_substance_findings,
    is_timezone_display_case,
    rejection_outcome_is_concrete,
)
from agent.llm import get_analyst_chat_model
from agent.models import OracleVerdictBatch
from agent.prompts import ORACLE_CASE_BLOCK, ORACLE_SYSTEM, ORACLE_USER
from agent.state import TestGenState

_NUM_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_DURATION_NUM_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:-|)(?:hour|hours|minute|minutes|day|days|item|items)\b",
    re.IGNORECASE,
)


def _data_numbers(text: str) -> list[str]:
    duration_spans = [m.span() for m in _DURATION_NUM_RE.finditer(text)]
    nums: list[str] = []
    for match in _NUM_TOKEN_RE.finditer(text):
        start, end = match.span()
        if any(d_start <= start and end <= d_end for d_start, d_end in duration_spans):
            continue
        nums.append(match.group(0))
    return nums


def _literal_richness(text: str) -> dict[str, int]:
    nums = _data_numbers(text)
    times = _TIME_RE.findall(text)
    return {
        "num_count": len(nums),
        "distinct_nums": len(set(nums)),
        "time_count": len(times),
    }

_VAGUE_STEP_PHRASES = (
    "open the flow",
    "open the scheduling flow",
    "review the screen",
    "inspect the result",
    "submit using the available options",
    "use the available options",
    "verify the outcome",
    "check the result",
    "generate the schedule",
)

_ORACLE_BATCH_SIZE = 6


def _case_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_str = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("description") or ""),
            str(case.get("preconditions") or ""),
            steps_str,
            str(case.get("expected_result") or ""),
        ]
    )


def _has_sufficient_literals(profile: str, text: str) -> bool:
    richness = _literal_richness(text)
    if profile == "comparison":
        return richness["distinct_nums"] >= 2 or richness["num_count"] >= 3
    if profile == "scheduling":
        return richness["time_count"] >= 1 or richness["num_count"] >= 2
    return True


def _vague_step_findings(case: dict[str, Any]) -> list[str]:
    steps = case.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return ["Unexecutable - no steps provided for a manual test case."]

    joined = " ".join(str(step) for step in steps).lower()
    vague_hits = [phrase for phrase in _VAGUE_STEP_PHRASES if phrase in joined]
    if vague_hits and not _literal_richness(_case_text(case))["num_count"]:
        return [
            "Unexecutable - steps are too vague for a manual tester "
            f"(for example: {vague_hits[0]})."
        ]
    return []


def _profile_findings(requirement: dict[str, Any], case: dict[str, Any]) -> list[str]:
    text = _case_text(case)
    req_text = f"{requirement.get('summary') or ''} {requirement.get('detail') or ''}"
    profile = normalize_execution_profile(
        requirement.get("execution_profile"),
        req_text,
        requirement.get("constraints") or [],
    )

    if profile == "comparison":
        return comparison_substance_findings(requirement, case)
    if profile == "scheduling":
        if is_timezone_display_case(requirement, case):
            return []
        text = _case_text(case)
        expected = str(case.get("expected_result") or "")
        if _TIME_RE.search(text) or rejection_outcome_is_concrete(expected):
            return []
        if not _has_sufficient_literals(profile, text):
            return [
                "Unexecutable - scheduling case is missing concrete times or windows a tester can verify."
            ]
        return []
    return []


def _heuristic_findings(requirement: dict[str, Any], case: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    findings.extend(_vague_step_findings(case))
    findings.extend(_profile_findings(requirement, case))
    return findings


def _format_steps(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return "(none)"
    return "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))


def _build_oracle_blocks(
    cases: list[dict[str, Any]],
    rule_by_id: dict[str, dict[str, Any]],
) -> str:
    blocks: list[str] = []
    for case in cases:
        rid = str(case.get("linked_requirement") or "")
        requirement = rule_by_id.get(rid) or {}
        req_text = f"{requirement.get('summary') or ''} {requirement.get('detail') or ''}"
        profile = normalize_execution_profile(
            requirement.get("execution_profile"),
            req_text,
            requirement.get("constraints") or [],
        )
        blocks.append(
            ORACLE_CASE_BLOCK.format(
                case_title=str(case.get("title") or "(untitled)"),
                rule_id=rid or "(unknown)",
                execution_profile=profile,
                requirement_summary=requirement.get("summary") or "(none)",
                requirement_detail=requirement.get("detail") or "(none)",
                preconditions=case.get("preconditions") or "(none)",
                steps=_format_steps(case),
                expected_result=case.get("expected_result") or "(none)",
            )
        )
    return "\n\n".join(blocks)


def _llm_oracle_findings(
    cases: list[dict[str, Any]],
    rule_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    if not cases:
        return {}

    llm = get_analyst_chat_model()
    structured = llm.with_structured_output(OracleVerdictBatch)
    findings_by_title: dict[str, list[str]] = {}

    for start in range(0, len(cases), _ORACLE_BATCH_SIZE):
        batch = cases[start : start + _ORACLE_BATCH_SIZE]
        user = ORACLE_USER.format(case_blocks=_build_oracle_blocks(batch, rule_by_id))
        raw = structured.invoke(
            [SystemMessage(content=ORACLE_SYSTEM), HumanMessage(content=user)]
        )
        result = OracleVerdictBatch.model_validate(raw)
        for verdict in result.verdicts:
            if verdict.executable or not verdict.issues:
                continue
            title = verdict.case_title.strip()
            findings_by_title[title] = list(verdict.issues)

    return findings_by_title


def _oracle_use_llm() -> bool:
    return os.environ.get("ORACLE_USE_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}


def oracle_validate(state: TestGenState) -> dict[str, Any]:
    cases = list(state.get("generated_cases") or [])
    rules = list(state.get("atomic_rules") or [])
    chunks = list(state.get("requirement_chunks") or [])
    spec_contradictions = scan_spec_contradictions(rules, requirement_chunks=chunks)
    contradictions = merge_contradictions(
        list(state.get("contradictions") or []),
        spec_contradictions,
    )
    marked_rules = mark_rule_statuses(rules, contradictions)

    if not cases:
        return {
            "generated_cases": [],
            "oracle_rejected_cases": [],
            "oracle_findings": [],
            "oracle_stats": {"input_cases": 0, "valid_cases": 0, "rejected_cases": 0},
            "contradictions": contradictions,
            "atomic_rules": marked_rules,
            "current_step": "oracle_validate",
        }

    rule_by_id = {str(r.get("rule_id")): r for r in rules if r.get("rule_id")}
    case_contradictions = scan_generated_case_contradictions(cases)
    contradictions = merge_contradictions(
        contradictions,
        case_contradictions,
    )
    blocked_rule_ids = contradiction_blocked_ids(contradictions)
    marked_rules = mark_rule_statuses(rules, contradictions)
    conflicting_titles: set[str] = set()
    for row in case_contradictions:
        for title in row.get("case_titles") or []:
            if title:
                conflicting_titles.add(str(title))

    heuristic_rejections: dict[int, list[str]] = {}
    heuristic_valid: list[tuple[int, dict[str, Any]]] = []

    for idx, case in enumerate(cases):
        if case.get("_already_persisted"):
            continue
        rid = str(case.get("linked_requirement") or "")
        requirement = rule_by_id.get(rid) or {}
        findings = _heuristic_findings(requirement, case)
        title = str(case.get("title") or "")
        if rid in blocked_rule_ids:
            findings.append(
                "Blocked requirement — specification contradiction requires clarification before testing."
            )
        elif title in conflicting_titles:
            findings.append(
                "Contradictory boundary testcase — conflicts with another requirement at price == threshold."
            )
        if findings:
            heuristic_rejections[idx] = findings
        else:
            heuristic_valid.append((idx, case))

    llm_rejections: dict[str, list[str]] = {}
    if _oracle_use_llm():
        llm_cases = [case for _, case in heuristic_valid]
        llm_rejections = _llm_oracle_findings(llm_cases, rule_by_id)

    valid_cases: list[dict[str, Any]] = []
    rejected_cases: list[dict[str, Any]] = []
    findings_summary: list[dict[str, Any]] = []

    for idx, case in enumerate(cases):
        if case.get("_already_persisted"):
            valid_cases.append(case)
            continue
        title = str(case.get("title") or "")
        findings = list(heuristic_rejections.get(idx) or [])
        if not findings and title in llm_rejections:
            findings = list(llm_rejections[title])

        if findings:
            row = dict(case)
            row["oracle_findings"] = findings
            rejected_cases.append(row)
            findings_summary.append(
                {
                    "linked_requirement": case.get("linked_requirement"),
                    "title": title,
                    "findings": findings,
                }
            )
        else:
            valid_cases.append(case)

    stats = {
        "input_cases": len(cases),
        "valid_cases": len(valid_cases),
        "rejected_cases": len(rejected_cases),
        "llm_enabled": _oracle_use_llm(),
        "case_contradictions": len(case_contradictions),
    }

    reasoning = state.get("reasoning") or ""
    if case_contradictions:
        reasoning = (
            reasoning
            + "\nQuality review detected "
            + f"{len(case_contradictions)} cross-requirement boundary contradiction(s) in generated cases."
        ).strip()
    if rejected_cases:
        reasoning = (
            reasoning
            + "\nQuality review flagged "
            + f"{len(rejected_cases)} case(s) as vague or unexecutable."
        ).strip()

    return {
        "generated_cases": valid_cases,
        "oracle_rejected_cases": rejected_cases,
        "oracle_findings": findings_summary,
        "oracle_stats": stats,
        "contradictions": contradictions,
        "atomic_rules": marked_rules,
        "reasoning": reasoning,
        "current_step": "oracle_validate",
    }
