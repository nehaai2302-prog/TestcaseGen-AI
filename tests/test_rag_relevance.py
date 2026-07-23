"""Tests for RAG relevance guard (domain contamination filter)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agent.nodes.retrieve_per_rule import retrieve_history_per_rule
from agent.rag_relevance import (
    domain_mismatch,
    filter_relevant_items,
    is_relevant_item,
    requirement_corpus_tokens,
)


ENERGY_RULES = [
    {
        "rule_id": "FR-5",
        "summary": "Schedule appliance in cheapest contiguous price window",
        "detail": (
            "The system shall schedule noisy appliances outside quiet hours using "
            "hourly spot prices in €/kWh and the configured price threshold."
        ),
        "screen": "Scheduling",
        "module": "optimization",
        "status": "active",
    },
    {
        "rule_id": "FR-11",
        "summary": "Noisy appliances blocked during quiet hours",
        "detail": "Quiet hours 22:00-07:00; do not schedule washing machine during quiet hours.",
        "screen": "Scheduling",
        "status": "active",
    },
]


def test_drops_ecommerce_cart_history_for_energy_srs() -> None:
    req_tokens = requirement_corpus_tokens(ENERGY_RULES)
    cart_bug = {
        "id": "bug-cart",
        "title": "Cart total wrong after coupon",
        "description": (
            "Checkout cart shows incorrect USD currency and shipping lbs for wishlist SKU."
        ),
        "component": "checkout",
        "similarity": 0.55,
    }
    energy_bug = {
        "id": "bug-quiet",
        "title": "Noisy appliance scheduled inside quiet hours",
        "description": (
            "Washing machine was scheduled at 23:00 during quiet hours despite spot price."
        ),
        "component": "scheduling",
        "similarity": 0.62,
    }
    assert domain_mismatch(cart_bug, req_tokens)
    assert not domain_mismatch(energy_bug, req_tokens)

    kept, dropped = filter_relevant_items([cart_bug, energy_bug], req_tokens)
    kept_ids = {str(i["id"]) for i in kept}
    dropped_ids = {str(i["id"]) for i in dropped}
    assert "bug-quiet" in kept_ids
    assert "bug-cart" in dropped_ids


def test_drops_low_similarity_even_if_on_domain() -> None:
    req_tokens = requirement_corpus_tokens(ENERGY_RULES)
    weak = {
        "id": "bug-weak",
        "title": "Quiet hours scheduling edge",
        "description": "Appliance schedule near quiet hours boundary.",
        "similarity": 0.12,
    }
    assert not is_relevant_item(weak, req_tokens, min_similarity=0.28)


@patch(
    "agent.nodes.retrieve_per_rule.embed_texts",
    return_value=[[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]],
)
@patch("agent.nodes.retrieve_per_rule.get_embeddings_model")
def test_retrieve_filters_foreign_domain_from_prompts(
    _mock_model: MagicMock,
    _mock_embed: MagicMock,
) -> None:
    repo = MagicMock()
    repo.match_bug_reports.return_value = [
        {
            "id": "bug-cart",
            "title": "Cart coupon currency mismatch",
            "description": "Checkout cart applies GBP instead of USD for SKU refund.",
            "component": "checkout",
            "similarity": 0.5,
        },
        {
            "id": "bug-quiet",
            "title": "Quiet hours ignored for washing machine",
            "description": "Spot price scheduling ran during quiet hours.",
            "component": "scheduling",
            "similarity": 0.55,
        },
    ]
    repo.match_test_cases.return_value = []

    state = {
        "project_id": "project-aaa",
        "use_project_history": True,
        "atomic_rules": ENERGY_RULES,
    }
    result = retrieve_history_per_rule(state, repo)
    used_ids = {str(b["id"]) for b in result["retrieved_bugs"]}
    assert "bug-quiet" in used_ids
    assert "bug-cart" not in used_ids
    assert result["rag_stats"]["retrieved_bugs"] == 2
    assert result["rag_stats"]["used_bugs"] == 1
    assert result["rag_stats"]["dropped_bugs"] == 1
    assert "bug-cart" not in (result["atomic_rules"][0].get("retrieved_bug_ids") or [])


@patch("agent.nodes.retrieve_per_rule.embed_texts")
@patch("agent.nodes.retrieve_per_rule.get_embeddings_model")
def test_retrieve_skips_when_history_disabled(
    _mock_model: MagicMock,
    mock_embed: MagicMock,
) -> None:
    repo = MagicMock()
    state = {
        "project_id": "project-aaa",
        "use_project_history": False,
        "atomic_rules": ENERGY_RULES,
    }
    result = retrieve_history_per_rule(state, repo)
    repo.match_bug_reports.assert_not_called()
    repo.match_test_cases.assert_not_called()
    mock_embed.assert_not_called()
    assert result["retrieved_bugs"] == []
    assert result["rag_stats"]["use_project_history"] is False
    assert result["rag_stats"]["skip_reason"] == "use_project_history_disabled"
