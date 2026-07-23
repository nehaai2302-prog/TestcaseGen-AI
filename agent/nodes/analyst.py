"""Analyst agent / requirement normalizer."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.ambiguity import mark_rule_statuses, summarize_contradictions
from agent.clarifying_questions import build_clarifying_questions
from agent.contradiction_scan import merge_contradictions, scan_spec_contradictions
from agent.formatting import chunk_lines
from agent.llm import get_analyst_chat_model, get_analyst_model_name
from agent.models import AnalystResult
from agent.prompts import ANALYST_SYSTEM, ANALYST_USER, REQUIREMENT_CHUNKS_BLOCK
from agent.state import TestGenState
from agent.execution_profile import infer_execution_profile, normalize_execution_profile
from services.chunking import RequirementSplit, structured_splits_low_confidence
from services.constraint_parser import extract_constraints

_SYNTHETIC_REQ_RE = re.compile(r"^REQ-\d{2}$", re.IGNORECASE)


def _parent_id_for_rule(
    rule: dict[str, Any],
    chunk_by_id: dict[str, dict[str, Any]],
    synthetic_chunk_ids: set[str],
) -> str:
    """Resolve the display parent ID used when suffixing duplicate rule_ids."""
    rid = (rule.get("rule_id") or "").strip()
    for cid in rule.get("source_requirement_chunk_ids") or []:
        chunk = chunk_by_id.get(str(cid))
        if not chunk:
            continue
        chunk_rid = (chunk.get("requirement_id") or "").strip()
        if chunk_rid:
            return chunk_rid
    if rid in synthetic_chunk_ids or _SYNTHETIC_REQ_RE.match(rid):
        return rid
    return rid


def ensure_unique_rule_ids(
    rules: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Assign unique rule_id per capability when the LLM reused the same ID."""
    if not rules:
        return rules

    chunk_by_id = {str(c.get("id")): c for c in chunks if c.get("id")}
    synthetic_chunk_ids = {
        (c.get("requirement_id") or "").strip()
        for c in chunks
        if c.get("is_synthetic_requirement") and (c.get("requirement_id") or "").strip()
    }

    id_counts: dict[str, int] = defaultdict(int)
    for rule in rules:
        rid = (rule.get("rule_id") or "").strip()
        if rid:
            id_counts[rid] += 1

    duplicates = {rid for rid, count in id_counts.items() if count > 1}
    if not duplicates:
        return rules

    per_parent: dict[str, int] = defaultdict(int)
    out: list[dict[str, Any]] = []
    for rule in rules:
        row = dict(rule)
        rid = (row.get("rule_id") or "").strip()
        if rid not in duplicates:
            out.append(row)
            continue

        parent = _parent_id_for_rule(row, chunk_by_id, synthetic_chunk_ids)
        per_parent[parent] += 1
        new_id = f"{parent}-{per_parent[parent]}"
        row["rule_id"] = new_id
        row["requirement_id"] = new_id
        out.append(row)

    return out


def _summary_from_text(text: str, requirement_id: str) -> str:
    cleaned = " ".join((text or "").split())
    if cleaned.lower().startswith(requirement_id.lower()):
        cleaned = cleaned[len(requirement_id) :].lstrip(" :.-")
    return cleaned[:220] or requirement_id


def _chunks_as_splits(chunks: list[dict[str, Any]]) -> list[RequirementSplit]:
    return [
        RequirementSplit(
            requirement_id=(c.get("requirement_id") or "").strip() or None,
            text=c.get("chunk_text") or "",
            is_synthetic=bool(c.get("is_synthetic_requirement")),
        )
        for c in chunks
    ]


def _requirements_from_structured_chunks(
    chunks: list[dict[str, Any]],
    module_hint: str | None,
) -> list[dict[str, Any]]:
    if chunks and all(c.get("is_synthetic_requirement") for c in chunks):
        return []
    if structured_splits_low_confidence(_chunks_as_splits(chunks)):
        return []

    requirements: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        req_id = (chunk.get("requirement_id") or "").strip()
        if not req_id:
            continue
        text = chunk.get("chunk_text") or ""
        constraints = extract_constraints(text)
        requirements.append(
            {
                "rule_id": req_id,
                "requirement_id": req_id,
                "summary": _summary_from_text(text, req_id),
                "detail": text,
                "source_requirement_chunk_ids": [str(chunk.get("id"))],
                "module": chunk.get("module") or module_hint,
                "screen": "General",
                "constraints": constraints,
                "execution_profile": infer_execution_profile(text, constraints),
                "source": "document_requirement",
                "status": "active",
                "chunk_index": chunk.get("chunk_index", i),
            }
        )
    return requirements


def analyze_requirements(state: TestGenState) -> dict[str, Any]:
    chunks = state.get("requirement_chunks") or []
    if not chunks:
        return {
            "atomic_rules": [],
            "contradictions": [],
            "clarifying_questions": [],
            "errors": (state.get("errors") or []) + ["No requirement chunks to analyze"],
            "current_step": "analyze_requirements",
        }

    structured = _requirements_from_structured_chunks(
        chunks, state.get("module_hint") or None
    )
    if structured:
        contradictions = scan_spec_contradictions(structured, requirement_chunks=chunks)
        structured = mark_rule_statuses(structured, contradictions)
        clarifying = build_clarifying_questions(structured, contradictions)
        reasoning = (
            "Structured requirement IDs were detected with high confidence; "
            "source IDs were preserved without an LLM pass."
        )
        contradiction_note = summarize_contradictions(contradictions)
        if contradiction_note:
            reasoning = (
                f"Analyst flagged {len(contradictions)} contradiction(s) requiring clarification "
                f"before generation: {contradiction_note}. "
                + reasoning
            ).strip()
        if clarifying:
            reasoning = (
                reasoning
                + f" Open questions for the spec author: {len(clarifying)}."
            ).strip()
        return {
            "atomic_rules": structured,
            "requirements": structured,
            "contradictions": contradictions,
            "clarifying_questions": clarifying,
            "reasoning": reasoning,
            "current_step": "analyze_requirements",
            "model_name": get_analyst_model_name(),
        }

    max_rules = int(os.environ.get("ANALYST_MAX_RULES", "20"))
    chunks_block = REQUIREMENT_CHUNKS_BLOCK.format(chunk_lines=chunk_lines(chunks))
    user = ANALYST_USER.format(
        module_hint=state.get("module_hint") or "(none)",
        chunks_block=chunks_block,
        max_rules=max_rules,
    )
    sys = ANALYST_SYSTEM.format(max_rules=max_rules)

    llm = get_analyst_chat_model()
    structured_llm = llm.with_structured_output(AnalystResult)
    result: AnalystResult = structured_llm.invoke(
        [SystemMessage(content=sys), HumanMessage(content=user)]
    )

    rules = [r.model_dump() for r in result.atomic_rules][:max_rules]
    contradictions = [c.model_dump() for c in result.contradictions]
    llm_questions = [q.model_dump() for q in result.clarifying_questions]
    for i, rule in enumerate(rules):
        if not rule.get("rule_id"):
            rule["rule_id"] = f"REQ-{i + 1:02d}"
        if str(rule.get("rule_id", "")).upper().startswith("RULE-"):
            rule["rule_id"] = f"REQ-{i + 1:02d}"
        rule["requirement_id"] = rule.get("requirement_id") or rule["rule_id"]
        if not (rule.get("screen") or "").strip():
            rule["screen"] = "General"
        if not rule.get("constraints"):
            rule["constraints"] = extract_constraints(rule.get("detail") or rule.get("summary") or "")
        rule_text = f"{rule.get('summary') or ''} {rule.get('detail') or ''}"
        rule["execution_profile"] = normalize_execution_profile(
            rule.get("execution_profile"),
            rule_text,
            rule.get("constraints") or [],
        )

    rules = ensure_unique_rule_ids(rules, chunks)
    rules = mark_rule_statuses(rules, contradictions)
    llm_contradictions = scan_spec_contradictions(rules, requirement_chunks=chunks)
    contradictions = merge_contradictions(contradictions, llm_contradictions)
    rules = mark_rule_statuses(rules, contradictions)
    clarifying = build_clarifying_questions(
        rules,
        contradictions,
        llm_questions=llm_questions,
    )

    reasoning = result.reasoning or ""
    contradiction_note = summarize_contradictions(contradictions)
    if contradiction_note:
        reasoning = (
            f"Analyst flagged {len(contradictions)} contradiction(s) requiring clarification "
            f"before generation: {contradiction_note}. "
            + reasoning
        ).strip()
    if clarifying:
        reasoning = (
            reasoning
            + f" Open questions for the spec author: {len(clarifying)}."
        ).strip()
    if not all(c.get("is_synthetic_requirement") for c in chunks):
        reasoning = (
            "Automatic ID detection looked ambiguous; the Analyst LLM re-read the "
            "document chunks to preserve or repair requirement IDs. "
            + reasoning
        )

    return {
        "atomic_rules": rules,
        "requirements": rules,
        "contradictions": contradictions,
        "clarifying_questions": clarifying,
        "reasoning": reasoning,
        "current_step": "analyze_requirements",
        "model_name": get_analyst_model_name(),
    }
