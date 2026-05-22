"""Build and compile the LangGraph multi-agent test-generation workflow.

Flow (default):
    analyze_requirements -> retrieve_history_per_rule (scope-aware RAG)
        -> generate_cases -> enrich_rag_links -> review_coverage
        -> validate_dedup -> persist
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from langgraph.graph import END, StateGraph

from agent.nodes.analyst import analyze_requirements
from agent.nodes.coverage_reviewer import prepare_regeneration, review_coverage
from agent.nodes.enrich_rag import enrich_rag_links
from agent.nodes.generate_cases import generate_cases
from agent.nodes.persist import persist
from agent.nodes.retrieve_per_rule import retrieve_history_per_rule
from agent.nodes.validate import validate_dedup
from agent.state import TestGenState
from services.supabase_repo import SupabaseRepo

# Human-readable labels for Streamlit progress (match node / current_step names).
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
        "Checking for duplicates against the test case library..."
    ),
    "persist": "Saving accepted test cases to the database...",
}

# Typical path without regen (MAX_COVERAGE_REVIEW_ROUNDS=0).
PIPELINE_STEP_COUNT = 7

# After each node finishes, the next node begins (used for live "in progress" UI).
PIPELINE_NEXT_STEP: dict[str, str] = {
    "analyze_requirements": "retrieve_history_per_rule",
    "retrieve_history_per_rule": "generate_cases",
    "generate_cases": "enrich_rag_links",
    "enrich_rag_links": "review_coverage",
    "review_coverage": "validate_dedup",
    "prepare_regeneration": "generate_cases",
    "validate_dedup": "persist",
}

# Extra hints while a long LLM step is running (Streamlit elapsed timer).
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


def build_graph(repo: SupabaseRepo):
    g = StateGraph(TestGenState)
    g.add_node("analyze_requirements", analyze_requirements)
    g.add_node(
        "retrieve_history_per_rule",
        partial(retrieve_history_per_rule, repo=repo),
    )
    g.add_node("generate_cases", generate_cases)
    g.add_node("enrich_rag_links", enrich_rag_links)
    g.add_node("review_coverage", review_coverage)
    g.add_node("prepare_regeneration", prepare_regeneration)
    g.add_node("validate_dedup", partial(validate_dedup, repo=repo))
    g.add_node("persist", partial(persist, repo=repo))

    g.set_entry_point("analyze_requirements")
    g.add_edge("analyze_requirements", "retrieve_history_per_rule")
    g.add_edge("retrieve_history_per_rule", "generate_cases")
    g.add_edge("generate_cases", "enrich_rag_links")
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
