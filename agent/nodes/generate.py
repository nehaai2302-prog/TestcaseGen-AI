"""LLM structured generation with optional loop-back signal."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from agent.prompts import CONTEXT_BLOCK, GENERATE_SYSTEM, GENERATE_USER, REQUIREMENT_CHUNKS_BLOCK
from agent.state import TestGenState


class TestCaseGen(BaseModel):
    title: str
    description: str | None = None
    preconditions: str | None = None
    steps: list[str] = Field(default_factory=list)
    expected_result: str = ""
    test_type: str = "positive"
    priority: str = "medium"
    module: str | None = None
    linked_requirement: str | None = None
    source_requirement_chunk_ids: list[str] = Field(default_factory=list)
    supporting_bug_ids: list[str] = Field(default_factory=list)
    supporting_test_case_ids: list[str] = Field(default_factory=list)


class GenerateResult(BaseModel):
    needs_more_context: bool = False
    retrieval_queries: list[str] = Field(default_factory=list)
    reasoning: str = ""
    test_cases: list[TestCaseGen] = Field(default_factory=list)


def _chunk_lines(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for c in chunks:
        cid = str(c.get("id", ""))
        idx = c.get("chunk_index", 0)
        text = (c.get("chunk_text") or "").replace("\n", " ")[:800]
        lines.append(f"- id={cid} chunk_index={idx} :: {text}")
    return "\n".join(lines)


def _bug_lines(bugs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for b in bugs:
        bid = str(b.get("id", ""))
        title = b.get("title", "")
        desc = (b.get("description") or "")[:400]
        lines.append(f"- bug_id={bid} :: {title} — {desc}")
    return "\n".join(lines) if lines else "- (none retrieved)"


def _tc_lines(tcs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for t in tcs:
        tid = str(t.get("id", ""))
        title = t.get("title", "")
        desc = (t.get("description") or "")[:300]
        lines.append(f"- tc_id={tid} :: {title} — {desc}")
    return "\n".join(lines) if lines else "- (none retrieved)"


def generate_tests(state: TestGenState) -> dict[str, Any]:
    model_name = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.2)
    structured = llm.with_structured_output(GenerateResult)

    chunks = state.get("requirement_chunks") or []
    test_types = ", ".join(state.get("test_types") or ["positive", "negative", "edge"])
    sys = GENERATE_SYSTEM.format(test_types=test_types)
    chunks_block = REQUIREMENT_CHUNKS_BLOCK.format(chunk_lines=_chunk_lines(chunks))
    ctx = CONTEXT_BLOCK.format(
        tc_lines=_tc_lines(state.get("retrieved_tcs") or []),
        bug_lines=_bug_lines(state.get("retrieved_bugs") or []),
    )
    user = GENERATE_USER.format(
        module_hint=state.get("module_hint") or "(none)",
        chunks_block=chunks_block,
        context_block=ctx,
    )

    result: GenerateResult = structured.invoke(
        [SystemMessage(content=sys), HumanMessage(content=user)]
    )

    cases: list[dict[str, Any]] = []
    for tc in result.test_cases:
        d = tc.model_dump()
        d["source"] = "generated"
        d["is_duplicate"] = False
        cases.append(d)

    return {
        "generated_cases": cases,
        "needs_more_context": result.needs_more_context,
        "retrieval_queries": result.retrieval_queries or [],
        "reasoning": result.reasoning,
        "current_step": "generate_tests",
        "model_name": model_name,
    }
