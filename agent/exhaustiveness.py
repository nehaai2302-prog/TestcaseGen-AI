"""Exhaustiveness profiles: per-rule test quotas by QA level."""

from __future__ import annotations

from typing import Any

ExhaustivenessLevel = str  # smoke | standard | exhaustive

EXHAUSTIVENESS_PROFILES: dict[str, dict[str, Any]] = {
    "smoke": {
        "label": "Level 1 — Smoke testing",
        "description": "1 positive + 1 negative per requirement",
        "quotas": {"positive": 1, "negative": 1, "boundary": 0, "edge": 0},
    },
    "standard": {
        "label": "Level 2 — Standard regression",
        "description": "2 positive + 3 negative + 1 boundary per requirement",
        "quotas": {"positive": 2, "negative": 3, "boundary": 1, "edge": 0},
    },
    "exhaustive": {
        "label": "Level 3 — Thorough (full coverage)",
        "description": "3 positive + 5 negative + 2 boundary + 2 edge per requirement",
        "quotas": {"positive": 3, "negative": 5, "boundary": 2, "edge": 2},
    },
}

DEFAULT_LEVEL: ExhaustivenessLevel = "standard"

POSITIVE_TYPES = frozenset({"positive"})
DESTRUCTIVE_TYPES = frozenset({"negative", "boundary", "edge"})


def normalize_level(level: str | None) -> ExhaustivenessLevel:
    key = (level or DEFAULT_LEVEL).strip().lower()
    if key not in EXHAUSTIVENESS_PROFILES:
        return DEFAULT_LEVEL
    return key


def get_profile(level: str | None) -> dict[str, Any]:
    return EXHAUSTIVENESS_PROFILES[normalize_level(level)]


def quotas_for_level(level: str | None) -> dict[str, int]:
    return dict(get_profile(level)["quotas"])


def cases_per_rule(level: str | None) -> int:
    return sum(quotas_for_level(level).values())


def estimate_total_cases(level: str | None, rule_count: int) -> int:
    if rule_count <= 0:
        return 0
    return rule_count * cases_per_rule(level)


def level_options() -> list[tuple[str, str]]:
    """Streamlit selectbox options: (label, value)."""
    return [
        (p["label"], key) for key, p in EXHAUSTIVENESS_PROFILES.items()
    ]
