"""Filter retrieved project history for relevance to the current requirements.

Spec-agnostic: uses similarity scores plus token overlap against the requirement
corpus. Items that introduce many foreign domain terms (e.g. cart/currency when
the SRS is about energy scheduling) are dropped before they reach the LLM.
"""

from __future__ import annotations

import os
import re
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "when",
        "while",
        "of",
        "to",
        "for",
        "in",
        "on",
        "at",
        "by",
        "from",
        "with",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "can",
        "could",
        "may",
        "might",
        "must",
        "not",
        "no",
        "yes",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "into",
        "over",
        "under",
        "about",
        "after",
        "before",
        "between",
        "during",
        "each",
        "all",
        "any",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "than",
        "too",
        "very",
        "just",
        "also",
        "only",
        "same",
        "so",
        "up",
        "out",
        "off",
        "own",
        "user",
        "system",
        "shall",
        "must",
        "test",
        "case",
        "bug",
        "report",
        "verify",
        "ensure",
        "using",
        "use",
        "via",
        "per",
        "new",
        "one",
        "two",
        "set",
        "get",
        "open",
        "save",
        "click",
        "page",
        "screen",
        "field",
        "value",
        "data",
        "time",
        "date",
        "day",
        "hour",
        "hours",
        "minute",
        "minutes",
    }
)

# Tokens that strongly signal retail/commerce domain contamination when absent
# from the requirement corpus. Kept short and generic — not product-specific.
_FOREIGN_DOMAIN_HINTS = frozenset(
    {
        "cart",
        "checkout",
        "coupon",
        "sku",
        "wishlist",
        "shipping",
        "freight",
        "invoice",
        "refund",
        "loyalty",
        "marketplace",
        "storefront",
        "ecommerce",
        "e-commerce",
        "lbs",
        "kg",
        "currency",
        "usd",
        "gbp",
        "paypal",
        "stripe",
        "vat",
        "taxid",
        "basket",
        "merchandise",
        "sku",
    }
)


def tokenize(text: str) -> set[str]:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text or "")}
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def requirement_corpus_tokens(rules: list[dict[str, Any]]) -> set[str]:
    parts: list[str] = []
    for rule in rules:
        parts.append(str(rule.get("summary") or ""))
        parts.append(str(rule.get("detail") or ""))
        parts.append(str(rule.get("text") or ""))
        parts.append(str(rule.get("screen") or ""))
        parts.append(str(rule.get("module") or ""))
    return tokenize(" ".join(parts))


def item_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("description") or ""),
            str(item.get("component") or ""),
            str(item.get("expected_result") or ""),
            str(item.get("preconditions") or ""),
        ]
    )


def relevance_min_similarity() -> float:
    return float(os.environ.get("RAG_RELEVANCE_MIN_SIMILARITY", "0.28"))


def max_foreign_ratio() -> float:
    return float(os.environ.get("RAG_MAX_FOREIGN_TOKEN_RATIO", "0.45"))


def domain_mismatch(
    item: dict[str, Any],
    req_tokens: set[str],
) -> bool:
    """True when the item looks like a foreign domain relative to requirements."""
    tokens = tokenize(item_text(item))
    if not tokens:
        return False

    foreign = tokens - req_tokens
    if not foreign:
        return False

    ratio = len(foreign) / max(len(tokens), 1)
    foreign_hints = foreign & _FOREIGN_DOMAIN_HINTS
    # Strong signal: commerce/retail hints absent from the SRS vocabulary.
    if foreign_hints and not (foreign_hints & req_tokens):
        return True
    # Soft signal: mostly OOV content words vs the requirement corpus.
    if ratio >= max_foreign_ratio() and len(foreign) >= 3:
        return True
    return False


def is_relevant_item(
    item: dict[str, Any],
    req_tokens: set[str],
    *,
    min_similarity: float | None = None,
) -> bool:
    sim = float(item.get("similarity") or 0.0)
    floor = relevance_min_similarity() if min_similarity is None else min_similarity
    if sim < floor:
        return False
    if domain_mismatch(item, req_tokens):
        return False
    return True


def filter_relevant_items(
    items: list[dict[str, Any]],
    req_tokens: set[str],
    *,
    min_similarity: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split items into (kept/used, dropped)."""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for item in items:
        if is_relevant_item(item, req_tokens, min_similarity=min_similarity):
            kept.append(item)
        else:
            dropped.append(item)
    return kept, dropped


def filter_rule_history(
    *,
    bugs: list[dict[str, Any]],
    tcs: list[dict[str, Any]],
    req_tokens: set[str],
    min_similarity: float | None = None,
) -> dict[str, Any]:
    """Filter per-rule bug/TC lists; return kept lists + drop stats."""
    kept_bugs, dropped_bugs = filter_relevant_items(
        bugs, req_tokens, min_similarity=min_similarity
    )
    kept_tcs, dropped_tcs = filter_relevant_items(
        tcs, req_tokens, min_similarity=min_similarity
    )
    return {
        "bugs": kept_bugs,
        "tcs": kept_tcs,
        "dropped_bugs": dropped_bugs,
        "dropped_tcs": dropped_tcs,
        "retrieved_bug_count": len(bugs),
        "retrieved_tc_count": len(tcs),
        "used_bug_count": len(kept_bugs),
        "used_tc_count": len(kept_tcs),
    }
