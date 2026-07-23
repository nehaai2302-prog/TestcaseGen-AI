"""Build and compile the LangGraph multi-agent test-generation workflow.

Flow (default):
    analyze_requirements -> retrieve_history_per_rule (scope-aware RAG)
        -> generate_cases -> validate_constraints -> validate_expectations
        -> validate_spec_facts -> oracle_validate
        -> enrich_rag_links -> review_coverage
        -> validate_dedup -> persist

Incomplete regen (button):
    generate_cases -> validate_constraints -> ... -> persist
    (reuses analysis/RAG from last_run; only fills coverage gaps)
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from langgraph.graph import END, StateGraph

from agent.nodes.analyst import analyze_requirements
from agent.nodes.coverage_reviewer import prepare_regeneration, review_coverage
from agent.nodes.enrich_rag import enrich_rag_links
from agent.nodes.generate_cases import generate_cases
from agent.nodes.oracle_validate import oracle_validate
from agent.nodes.persist import persist
from agent.nodes.retrieve_per_rule import retrieve_history_per_rule
from agent.nodes.validate_constraints import validate_constraints
from agent.nodes.validate_expectations import validate_expectations
from agent.nodes.validate_spec_facts import validate_spec_facts
from agent.nodes.validate import validate_dedup
from agent.state import TestGenState
from services.supabase_repo import SupabaseRepo

PIPELINE_STEP_LABELS: dict[str, str] = {
    "analyze_requirements": (
        "Detecting requirements and tagging scopes..."
    ),
    "retrieve_history_per_rule": (
        "Retrieving project history per requirement (scope-aware RAG)..."
    ),
    "generate_cases": (
        "Generating test cases per requirement from retrieved history "
        "(may take 30-60 seconds)..."
    ),
    "validate_constraints": (
        "Validating generated cases against parsed requirement constraints..."
    ),
    "validate_expectations": (
        "Checking negative cases do not reject constraint-valid values..."
    ),
    "validate_spec_facts": (
        "Checking quiet-hour times and DST day lengths against the specification..."
    ),
    "oracle_validate": (
        "Quality review: checking whether cases are clear and executable..."
    ),
    "enrich_rag_links": (
        "Linking generated tests to retrieved bugs & existing test cases..."
    ),
    "review_coverage": (
        "Coverage reviewer: verifying test counts per requirement and type..."
    ),
    "prepare_regeneration": (
        "Preparing a follow-up generation pass for coverage gaps..."
    ),
    "validate_dedup": (
        "Deduplicating this run (title, verbatim, cross-req scenarios, semantic, library)..."
    ),
    "persist": "Saving accepted test cases to the database...",
}

PIPELINE_STEP_COUNT = 11
REGEN_PIPELINE_STEP_COUNT = 9

PIPELINE_NEXT_STEP: dict[str, str] = {
    "analyze_requirements": "retrieve_history_per_rule",
    "retrieve_history_per_rule": "generate_cases",
    "generate_cases": "validate_constraints",
    "validate_constraints": "validate_expectations",
    "validate_expectations": "validate_spec_facts",
    "validate_spec_facts": "oracle_validate",
    "oracle_validate": "enrich_rag_links",
    "enrich_rag_links": "review_coverage",
    "review_coverage": "validate_dedup",
    "prepare_regeneration": "generate_cases",
    "validate_dedup": "persist",
}

LONG_STEP_HINTS: dict[str, str] = {
    "analyze_requirements": (
        "The Analyst LLM call is running - this step often takes 20-45s; the page is not frozen."
    ),
    "generate_cases": (
        "Generating many structured test cases - often the slowest step; please wait."
    ),
    "retrieve_history_per_rule": (
        "Embedding each requirement and querying pgvector - usually fast (a few seconds)."
    ),
}


def get_step_label(step: str) -> str:
    return PIPELINE_STEP_LABELS.get(step, step.replace("_", " ").title())


def get_step_hint(step: str) -> str:
    return LONG_STEP_HINTS.get(step, "Still working...")


def _route_after_coverage(state: TestGenState) -> str:
    if state.get("needs_regeneration"):
        return "prepare_regeneration"
    return "validate_dedup"


def _add_shared_nodes(g: StateGraph, repo: SupabaseRepo) -> None:
    g.add_node("generate_cases", generate_cases)
    g.add_node("validate_constraints", validate_constraints)
    g.add_node("validate_expectations", validate_expectations)
    g.add_node("validate_spec_facts", validate_spec_facts)
    g.add_node("oracle_validate", oracle_validate)
    g.add_node("enrich_rag_links", enrich_rag_links)
    g.add_node("review_coverage", review_coverage)
    g.add_node("prepare_regeneration", prepare_regeneration)
    g.add_node("validate_dedup", partial(validate_dedup, repo=repo))
    g.add_node("persist", partial(persist, repo=repo))


def _wire_from_generate(g: StateGraph) -> None:
    g.add_edge("generate_cases", "validate_constraints")
    g.add_edge("validate_constraints", "validate_expectations")
    g.add_edge("validate_expectations", "validate_spec_facts")
    g.add_edge("validate_spec_facts", "oracle_validate")
    g.add_edge("oracle_validate", "enrich_rag_links")
    g.add_edge("enrich_rag_links", "review_coverage")
    g.add_conditional_edges(
        "review_coverage",
        _route_after_coverage,
        {
            "prepare_regeneration": "prepare_regeneration",
            "validate_dedup": "validate_dedup",
        },
    )
    g.add_edge("prepare_regeneration", "generate_cases")
    g.add_edge("validate_dedup", "persist")
    g.add_edge("persist", END)


def build_graph(repo: SupabaseRepo):
    g = StateGraph(TestGenState)
    g.add_node("analyze_requirements", analyze_requirements)
    g.add_node(
        "retrieve_history_per_rule",
        partial(retrieve_history_per_rule, repo=repo),
    )
    _add_shared_nodes(g, repo)
    g.set_entry_point("analyze_requirements")
    g.add_edge("analyze_requirements", "retrieve_history_per_rule")
    g.add_edge("retrieve_history_per_rule", "generate_cases")
    _wire_from_generate(g)
    return g.compile()


def build_regen_graph(repo: SupabaseRepo):
    """Scoped regen: reuse last_run analysis/RAG; fill incomplete requirement quotas."""
    g = StateGraph(TestGenState)
    _add_shared_nodes(g, repo)
    g.set_entry_point("generate_cases")
    _wire_from_generate(g)
    return g.compile()


def run_generation(repo: SupabaseRepo, initial: TestGenState) -> TestGenState:
    """Run full graph and return final state (blocking, no progress callbacks)."""
    app = build_graph(repo)
    return app.invoke(initial)


def run_generation_stream(
    repo: SupabaseRepo,
    initial: TestGenState,
    on_step: Callable[[str, TestGenState, int], None] | None = None,
) -> TestGenState:
    """
    Run graph with stream_mode='values'; call on_step(current_step, state, step_index)
    after each node completes.
    """
    app = build_graph(repo)
    final: TestGenState = dict(initial)
    seen_steps: list[str] = []

    for state in app.stream(initial, stream_mode="values"):
        final = state
        step = state.get("current_step") or ""
        if step and step not in seen_steps:
            seen_steps.append(step)
            if on_step:
                on_step(step, state, len(seen_steps))

    return final


def run_regen_stream(
    repo: SupabaseRepo,
    initial: TestGenState,
    on_step: Callable[[str, TestGenState, int], None] | None = None,
) -> TestGenState:
    """Run incomplete-requirement regen graph (starts at generate_cases)."""
    app = build_regen_graph(repo)
    final: TestGenState = dict(initial)
    seen_steps: list[str] = []

    for state in app.stream(initial, stream_mode="values"):
        final = state
        step = state.get("current_step") or ""
        if step and step not in seen_steps:
            seen_steps.append(step)
            if on_step:
                on_step(step, state, len(seen_steps))

    return final
