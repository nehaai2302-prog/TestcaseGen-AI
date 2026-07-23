"""Tests for batch semantic deduplication."""

from __future__ import annotations

from agent.nodes.validate import batch_semantic_dedup, cosine_similarity


def test_cosine_similarity_identical_vectors() -> None:
    vec = [1.0, 0.0, 0.0]
    assert cosine_similarity(vec, vec) == 1.0


def test_batch_semantic_dedup_keeps_one_per_cluster() -> None:
    cases = [
        {"title": "Login with valid credentials"},
        {"title": "Sign in using correct email and password"},
        {"title": "Upload profile photo under 5MB"},
    ]
    vectors = [
        [1.0, 0.0, 0.0],
        [0.99, 0.01, 0.0],
        [0.0, 1.0, 0.0],
    ]
    kept, dups = batch_semantic_dedup(cases, vectors, threshold=0.75)
    assert len(kept) == 2
    assert len(dups) == 1
    assert dups[0]["duplicate_reason"] == "batch_semantic_duplicate"
    assert dups[0]["similar_to_title"] == cases[0]["title"]


def test_six_cases_three_semantic_variants() -> None:
    vectors = [
        [1.0, 0.0, 0.0],
        [0.99, 0.01, 0.0],
        [0.98, 0.02, 0.0],
        [0.0, 1.0, 0.0],
        [0.01, 0.99, 0.0],
        [0.02, 0.98, 0.0],
        [0.0, 0.0, 1.0],
        [0.0, 0.01, 0.99],
        [0.0, 0.02, 0.98],
    ]
    cases = [{"title": f"Case {i}"} for i in range(9)]
    kept, dups = batch_semantic_dedup(cases, vectors, threshold=0.75)
    assert len(kept) == 3
    assert len(dups) == 6
