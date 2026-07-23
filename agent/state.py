"""Typed state for LangGraph test generation pipeline."""

from __future__ import annotations

from typing import Any, TypedDict


class TestGenState(TypedDict, total=False):
    project_id: str
    document_name: str
    requirement_chunks: list[dict[str, Any]]
    exhaustiveness_level: str  # smoke | standard | exhaustive
    module_hint: str | None

    # Legacy (optional); profile quotas drive types now
    test_types: list[str]

    retrieved_bugs: list[dict[str, Any]]
    retrieved_tcs: list[dict[str, Any]]
    retrieval_summary: dict[str, Any]
    rule_retrievals: dict[str, Any]

    rag_stats: dict[str, Any]
    use_project_history: bool

    pending_queries: list[str]
    retrieval_loops: int

    # Requirements (legacy key name kept for graph compatibility)
    atomic_rules: list[dict[str, Any]]
    requirements: list[dict[str, Any]]

    # Generators
    positive_cases: list[dict[str, Any]]
    destructive_cases: list[dict[str, Any]]
    generated_cases: list[dict[str, Any]]

    # Coverage reviewer
    coverage_gaps: list[dict[str, Any]]
    coverage_report: dict[str, Any]
    coverage_satisfied: bool
    needs_regeneration: bool
    review_round: int

    validated_cases: list[dict[str, Any]]
    duplicates: list[dict[str, Any]]
    batch_dedup_stats: dict[str, Any]
    invalid_cases: list[dict[str, Any]]
    constraint_violations: list[dict[str, Any]]
    constraint_stats: dict[str, Any]
    expectation_rejected_cases: list[dict[str, Any]]
    expectation_violations: list[dict[str, Any]]
    expectation_stats: dict[str, Any]
    spec_fact_rejected_cases: list[dict[str, Any]]
    spec_fact_violations: list[dict[str, Any]]
    spec_fact_stats: dict[str, Any]
    oracle_rejected_cases: list[dict[str, Any]]
    oracle_findings: list[dict[str, Any]]
    oracle_stats: dict[str, Any]

    # Incomplete-requirement regeneration (button / coverage loop)
    regen_mode: bool
    regen_feedback: dict[str, list[str]]

    contradictions: list[dict[str, Any]]
    clarifying_questions: list[dict[str, Any]]
    srs_replace_requirement_ids: list[str]

    needs_more_context: bool
    retrieval_queries: list[str]
    reasoning: str

    current_step: str
    errors: list[str]

    agent_looped_back: bool
    model_name: str
