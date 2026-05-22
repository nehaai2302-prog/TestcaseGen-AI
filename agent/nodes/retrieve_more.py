"""LangGraph node: queue follow-up retrieval queries."""

from __future__ import annotations

from typing import Any

from agent.state import TestGenState


def retrieve_more(state: TestGenState) -> dict[str, Any]:
    loops = int(state.get("retrieval_loops") or 0) + 1
    queries = list(state.get("retrieval_queries") or [])
    return {
        "retrieval_loops": loops,
        "pending_queries": queries,
        "current_step": "retrieve_more",
        "agent_looped_back": True,
    }
