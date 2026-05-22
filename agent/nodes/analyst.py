"""Analyst agent / requirement normalizer."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agent.formatting import chunk_lines
from agent.llm import get_analyst_chat_model, get_model_name
from agent.models import AnalystResult
from agent.prompts import ANALYST_SYSTEM, ANALYST_USER, REQUIREMENT_CHUNKS_BLOCK
from agent.state import TestGenState


def _summary_from_text(text: str, requirement_id: str) -> str:
    cleaned = " ".join((text or "").split())
    if cleaned.lower().startswith(requirement_id.lower()):
        cleaned = cleaned[len(requirement_id) :].lstrip(" :.-")
    return cleaned[:220] or requirement_id


def _requirements_from_structured_chunks(
    chunks: list[dict[str, Any]],
    module_hint: str | None,
) -> list[dict[str, Any]]:
    if chunks and all(c.get("is_synthetic_requirement") for c in chunks):
        return []

    requirements: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        req_id = (chunk.get("requirement_id") or "").strip()
        if not req_id:
            continue
        text = chunk.get("chunk_text") or ""
        requirements.append(
            {
                "rule_id": req_id,
                "requirement_id": req_id,
                "summary": _summary_from_text(text, req_id),
                "detail": text,
                "source_requirement_chunk_ids": [str(chunk.get("id"))],
                "module": chunk.get("module") or module_hint,
                "screen": "General",
                "source": "document_requirement",
                "chunk_index": chunk.get("chunk_index", i),
            }
        )
    return requirements


def analyze_requirements(state: TestGenState) -> dict[str, Any]:
    chunks = state.get("requirement_chunks") or []
    if not chunks:
        return {
            "atomic_rules": [],
            "errors": (state.get("errors") or []) + ["No requirement chunks to analyze"],
            "current_step": "analyze_requirements",
        }

    structured = _requirements_from_structured_chunks(
        chunks, state.get("module_hint") or None
    )
    if structured:
        return {
            "atomic_rules": structured,
            "requirements": structured,
            "reasoning": (
                "Requirement IDs were detected in the document, so the Analyst "
                "preserved the source requirement IDs instead of inventing RULE labels."
            ),
            "current_step": "analyze_requirements",
            "model_name": get_model_name(),
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
    structured = llm.with_structured_output(AnalystResult)
    result: AnalystResult = structured.invoke(
        [SystemMessage(content=sys), HumanMessage(content=user)]
    )

    rules = [r.model_dump() for r in result.atomic_rules][:max_rules]
    for i, rule in enumerate(rules):
        if not rule.get("rule_id"):
            rule["rule_id"] = f"REQ-{i + 1:02d}"
        if str(rule.get("rule_id", "")).upper().startswith("RULE-"):
            rule["rule_id"] = f"REQ-{i + 1:02d}"
        rule["requirement_id"] = rule.get("requirement_id") or rule["rule_id"]
        if not (rule.get("screen") or "").strip():
            rule["screen"] = "General"

    return {
        "atomic_rules": rules,
        "requirements": rules,
        "reasoning": result.reasoning,
        "current_step": "analyze_requirements",
        "model_name": get_model_name(),
    }
