"""Infer how a requirement should be executed in manual tests (spec-agnostic)."""

from __future__ import annotations

import re
from typing import Any

EXECUTION_PROFILES = ("general", "config", "comparison", "scheduling")

# UI/state-guard rules may mention "schedule" but do not verify time placement.
_CONTROL_GUARD_PATTERNS = (
    r"\bmanual\s+stop\b",
    r"\bnot\s+running\b",
    r"\bwhen\s+(?:the\s+)?appliance\s+is\s+not\s+running\b",
    r"\bwhile\s+(?:the\s+)?appliance\s+is\s+(?:idle|off|stopped)\b",
    r"\bdisabled\s+when\b",
    r"\bwhen\s+not\s+running\b",
)

_DISPLAY_LOCALIZATION_PATTERNS = (
    r"\btimezone\b",
    r"\blocal\s+timezone\b",
    r"\btimes?\s+shall\s+be\s+displayed\b",
    r"\bdisplayed?\s+in\b.*\b(?:local|timezone)\b",
)

_QUIET_HOURS_RESTRICTION_PATTERNS = (
    r"\bquiet\s+hours?\b",
)

_QUIET_HOURS_GUARDRAIL_PATTERNS = (
    r"\b(?:shall|must)\s+not\s+(?:be\s+)?(?:scheduled|run)\b",
    r"\bnot\s+(?:be\s+)?(?:scheduled|run)\s+during\b",
    r"\bquiet\s+hours?\s+take\s+precedence\b",
    r"\bprecedence\s+over\b",
)

_SCHEDULING_PATTERNS = (
    r"\b\d{1,2}:\d{2}\b",
    r"\btime\s+window",
    r"\btime\s+slot",
    r"\brun\s+during\b",
    r"\bnot\s+run\s+during\b",
    r"\bquiet\s+hours?\b",
    r"\boutside\s+(?:the\s+)?(?:configured\s+)?(?:hours?|window|period)\b",
    r"\bwithin\s+(?:the\s+)?(?:configured\s+)?(?:hours?|window|period)\b",
    r"\b(?:start|end)\s+time\b",
    r"\bschedule(?:d)?\s+(?:at|for|during|outside|within)\b",
    r"\b(?:hour|minute)\s+block\b",
    r"\b\d+\s*-?\s*hour\s+(?:block|window)\b",
)

_COMPARISON_PATTERNS = (
    r"\bcheapest\b",
    r"\blowest\b",
    r"\bhighest\b",
    r"\bbest\b",
    r"\boptimal\b",
    r"\bcompare\b",
    r"\bselect(?:ing)?\s+the\b",
    r"\bnext\s+(?:available|cheapest|best|lowest|highest)\b",
    r"\blowest\s+price\b",
    r"\bhighest\s+priority\b",
    r"\bmost\s+recent\b",
    r"\bleast\s+expensive\b",
    # "minimum/maximum" alone are too broad (max length, min availability).
    # Require selection/optimization context.
    r"\b(?:minimum|maximum)\s+(?:total|cost|price|score|priority|value)\b",
    r"\b(?:choose|pick|prefer|select)\b.{0,40}\b(?:minimum|maximum)\b",
)

_LENGTH_INPUT_CONFIG_PATTERNS = (
    r"\b(?:max(?:imum)?|min(?:imum)?)\s+(?:length|characters?|chars?)\b",
    r"\b(?:length|characters?|chars?)\s+(?:limit|must|shall|of|is)\b",
    r"\b\d+\s*(?:-|\u2013|to)?\s*(?:character|characters|chars?)\b",
    r"\bcharacter\s+(?:limit|length|count)\b",
    r"\binput\s+(?:field|length|validation)\b",
    r"\baccept(?:s|ed)?\s+exactly\s+\d+\b",
    r"\blonger\s+than\s+\d+\s*(?:character|characters|chars?)\b",
)

_CONFIG_PATTERNS = (
    r"\bconfigure\b",
    r"\bconfiguration\b",
    r"\bsettings?\b",
    r"\bthreshold\b",
    r"\bparameter\b",
    r"\bvalid(?:ate|ation)\b",
    r"\bmust\s+be\s+(?:in|between)\b",
    r"\bincrements?\s+of\b",
    r"\bone\s+of:\b",
) + _LENGTH_INPUT_CONFIG_PATTERNS


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _is_quiet_hours_guardrail(text: str) -> bool:
    if not _matches_any(text, _QUIET_HOURS_RESTRICTION_PATTERNS):
        return False
    return _matches_any(text, _QUIET_HOURS_GUARDRAIL_PATTERNS)


def _is_length_or_input_config(text: str) -> bool:
    return _matches_any(text, _LENGTH_INPUT_CONFIG_PATTERNS)


def infer_execution_profile(
    text: str,
    constraints: list[dict[str, Any]] | None = None,
) -> str:
    """Classify how testers must exercise this requirement."""
    src = (text or "").strip()
    if not src:
        return "general"

    if _matches_any(src, _CONTROL_GUARD_PATTERNS):
        return "general"

    if _matches_any(src, _DISPLAY_LOCALIZATION_PATTERNS):
        return "general"

    if _is_quiet_hours_guardrail(src):
        return "scheduling"

    # Input length / character limits are config validation, not multi-candidate comparison.
    if _is_length_or_input_config(src):
        return "config"

    if _matches_any(src, _COMPARISON_PATTERNS):
        return "comparison"

    if _matches_any(src, _SCHEDULING_PATTERNS):
        return "scheduling"

    has_constraints = bool(constraints)
    if has_constraints or _matches_any(src, _CONFIG_PATTERNS):
        return "config"
    return "general"


def normalize_execution_profile(value: str | None, fallback_text: str = "", constraints: list[dict[str, Any]] | None = None) -> str:
    """Use stored profile when sensible; otherwise infer from requirement text."""
    inferred = infer_execution_profile(fallback_text, constraints)
    profile = (value or "").strip().lower()
    if profile not in EXECUTION_PROFILES:
        return inferred
    # A vague LLM label must not bypass stronger text-based inference (e.g. FR-5 → comparison).
    if profile == "general" and inferred != "general":
        return inferred
    if profile == "scheduling" and inferred == "comparison":
        return inferred
    # LLM sometimes labels length limits as comparison because of "maximum".
    if profile == "comparison" and inferred == "config" and _is_length_or_input_config(
        fallback_text
    ):
        return "config"
    return profile
