"""Tests that per-rule RAG retrieval is scoped to the active project."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.retrieve_per_rule import retrieve_history_per_rule


@patch("agent.nodes.retrieve_per_rule.embed_texts", return_value=[[0.1, 0.2, 0.3]])
@patch("agent.nodes.retrieve_per_rule.get_embeddings_model")
def test_retrieve_passes_project_id_to_match_rpcs(
    _mock_model: MagicMock,
    _mock_embed: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_bug_reports.return_value = [
        {"id": "bug-1", "title": "Payment failure", "similarity": 0.5}
    ]
    repo.match_test_cases.return_value = []

    state = {
        "project_id": "project-aaa",
        "atomic_rules": [
            {
                "rule_id": "FR-1",
                "summary": "Checkout payment",
                "detail": "Pay with card",
                "screen": "Checkout",
                "status": "active",
            }
        ],
    }

    result = retrieve_history_per_rule(state, repo)

    repo.match_bug_reports.assert_called_once()
    bug_args = repo.match_bug_reports.call_args[0]
    assert bug_args[0] == "project-aaa"

    repo.match_test_cases.assert_called_once()
    tc_args = repo.match_test_cases.call_args[0]
    assert tc_args[0] == "project-aaa"

    assert result["retrieved_bugs"][0]["id"] == "bug-1"


@patch("agent.nodes.retrieve_per_rule.embed_texts", return_value=[[0.1, 0.2, 0.3]])
@patch("agent.nodes.retrieve_per_rule.get_embeddings_model")
def test_retrieve_skips_blocked_rules(
    _mock_model: MagicMock,
    _mock_embed: MagicMock,
) -> None:
    repo = MagicMock()
    state = {
        "project_id": "project-aaa",
        "atomic_rules": [
            {
                "rule_id": "FR-7",
                "summary": "Blocked",
                "status": "requires_clarification",
            },
            {
                "rule_id": "FR-9",
                "summary": "Active rule",
                "detail": "detail",
                "screen": "General",
                "status": "active",
            },
        ],
    }

    retrieve_history_per_rule(state, repo)

    assert repo.match_bug_reports.call_count == 1
    assert repo.match_test_cases.call_count == 1
