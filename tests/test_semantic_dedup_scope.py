"""Tests for semantic batch dedup scoping rules.

The key behavioral requirement:
- Semantic batch dedup should never compare cases with different `test_type`.
- Semantic batch dedup should only compare within the same `linked_requirement`.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.validate import validate_dedup


def _embed_side_effect(_model: object, texts: list[str]) -> list[list[float]]:
    # Return identical vectors for every blob so semantic similarity is always high.
    return [[1.0, 0.0] for _ in texts]


@patch("agent.nodes.validate.get_embeddings_model", return_value=MagicMock())
@patch("agent.nodes.validate.embed_texts", side_effect=_embed_side_effect)
def test_semantic_dedup_does_not_compare_positive_vs_negative(
    _embed: MagicMock,
    _model: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_test_cases.return_value = []

    state = {
        "project_id": "project-1",
        "exhaustiveness_level": "smoke",
        "generated_cases": [
            {
                "title": "Positive A",
                "linked_requirement": "FR-1",
                "test_type": "positive",
                "steps": ["do it"],
                "expected_result": "ok",
                "supporting_bug_ids": [],
                "supporting_test_case_ids": [],
                "source_requirement_chunk_ids": [],
            },
            {
                "title": "Negative B",
                "linked_requirement": "FR-1",
                "test_type": "negative",
                "steps": ["do it"],
                "expected_result": "error",
                "supporting_bug_ids": [],
                "supporting_test_case_ids": [],
                "source_requirement_chunk_ids": [],
            },
        ],
    }

    out = validate_dedup(state, repo)
    assert out["batch_dedup_stats"]["removed_semantic"] == 0
    assert len(out["duplicates"]) == 0
    assert len(out["validated_cases"]) == 2


@patch("agent.nodes.validate.get_embeddings_model", return_value=MagicMock())
@patch("agent.nodes.validate.embed_texts", side_effect=_embed_side_effect)
def test_semantic_dedup_scoped_to_same_req_and_type(
    _embed: MagicMock,
    _model: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_test_cases.return_value = []

    state = {
        "project_id": "project-1",
        "exhaustiveness_level": "standard",
        "generated_cases": [
            {
                "title": "Positive A1",
                "linked_requirement": "FR-1",
                "test_type": "positive",
                "steps": ["do it"],
                "expected_result": "ok",
                "supporting_bug_ids": [],
                "supporting_test_case_ids": [],
                "source_requirement_chunk_ids": [],
            },
            {
                "title": "Positive A2",
                "linked_requirement": "FR-1",
                "test_type": "positive",
                "steps": ["do it"],
                "expected_result": "ok",
                "supporting_bug_ids": [],
                "supporting_test_case_ids": [],
                "source_requirement_chunk_ids": [],
            },
        ],
    }

    out = validate_dedup(state, repo)
    assert out["batch_dedup_stats"]["removed_verbatim"] == 1
    assert out["batch_dedup_stats"]["removed_semantic"] == 0
    assert len(out["duplicates"]) == 1
    assert out["duplicates"][0]["duplicate_reason"] == "batch_verbatim_duplicate"
    assert len(out["validated_cases"]) == 1


@patch("agent.nodes.validate.get_embeddings_model", return_value=MagicMock())
@patch("agent.nodes.validate.embed_texts", side_effect=_embed_side_effect)
def test_verbatim_dedup_across_different_requirements(
    _embed: MagicMock,
    _model: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_test_cases.return_value = []

    shared_steps = ["Configure prices 0.10, 0.20, 0.15.", "Run optimizer."]
    shared_expected = "Schedule uses 02:00-03:00."

    state = {
        "project_id": "project-1",
        "generated_cases": [
            {
                "title": "FR-5 cheapest block",
                "linked_requirement": "FR-5",
                "test_type": "positive",
                "steps": shared_steps,
                "expected_result": shared_expected,
            },
            {
                "title": "Different title same body",
                "linked_requirement": "FR-6",
                "test_type": "negative",
                "steps": shared_steps,
                "expected_result": shared_expected,
            },
        ],
    }

    out = validate_dedup(state, repo)
    assert out["batch_dedup_stats"]["removed_verbatim"] == 1
    assert len(out["validated_cases"]) == 1

