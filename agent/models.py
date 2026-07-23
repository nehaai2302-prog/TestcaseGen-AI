"""Shared Pydantic models for the multi-agent generation pipeline."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AtomicRule(BaseModel):
    # Kept as rule_id for compatibility with older graph code. In the new
    # requirement-first flow this is the source requirement ID (FR-2.2, US-103,
    # REQ-01, etc.), not an invented RULE-XX label.
    rule_id: str
    requirement_id: str | None = None
    summary: str
    detail: str = ""
    source_requirement_chunk_ids: list[str] = Field(default_factory=list)
    module: str | None = None
    # Shared-context bucket used to group rules for screen/scope-aware RAG.
    # May hold: a UI screen ("Checkout"), a service/endpoint ("OrderService",
    # "POST /api/payments"), a functional area ("AuthN", "Audit"), or "General".
    screen: str | None = None
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    # How manual testers must exercise this rule: config forms, comparisons, schedules, or general.
    execution_profile: str = "general"


class RequirementContradiction(BaseModel):
    rule_id: str
    issue: str
    related_rule_ids: list[str] = Field(default_factory=list)


class ClarifyingQuestion(BaseModel):
    rule_ids: list[str] = Field(default_factory=list)
    question: str
    why_it_matters: str = ""


class AnalystResult(BaseModel):
    reasoning: str = ""
    atomic_rules: list[AtomicRule] = Field(default_factory=list)
    contradictions: list[RequirementContradiction] = Field(default_factory=list)
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


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


class TestCasesBatch(BaseModel):
    test_cases: list[TestCaseGen] = Field(default_factory=list)


class OracleCaseVerdict(BaseModel):
    case_title: str
    executable: bool = True
    issues: list[str] = Field(default_factory=list)


class OracleVerdictBatch(BaseModel):
    verdicts: list[OracleCaseVerdict] = Field(default_factory=list)
