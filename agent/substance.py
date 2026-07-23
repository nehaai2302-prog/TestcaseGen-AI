"""Substance checks for generated test cases (spec-agnostic)."""

from __future__ import annotations

import os
import re
from typing import Any

_NUM_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?")
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
_TIME_RANGE_RE = re.compile(
    r"\b\d{1,2}:\d{2}\s*(?:-|–|to)\s*\d{1,2}:\d{2}\b",
    re.IGNORECASE,
)
_DURATION_NUM_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:-|)(?:hour|hours|minute|minutes|day|days|item|items)\b",
    re.IGNORECASE,
)
_DURATION_VALUE_RE = re.compile(
    r"\b(\d+)\s*-?\s*(?:hour|hours)\b",
    re.IGNORECASE,
)

_REJECTION_OUTCOME = re.compile(
    r"\b(?:reject(?:ed|ion)?|error(?:\s+message)?|invalid|cannot fit|can't fit|"
    r"does not select|do not select|not created|not scheduled|blocking message|"
    r"validation message|shall not run|cannot run|does not fit|no block)\b",
    re.IGNORECASE,
)

_TIMEZONE_LITERAL = re.compile(
    r"\btimezone\b|(?:Europe|America|Asia|Pacific)/[A-Za-z_]+|\bUTC\b",
    re.IGNORECASE,
)

_VAGUE_EXPECTED_PHRASES = (
    "block selected",
    "lowest total",
    "cheapest block",
    "cheapest hours",
    "cheapest contiguous",
    "lowest price",
    "optimal block",
    "optimal hours",
    "best block",
    "selects the lowest",
    "selects the cheapest",
    "chooses the lowest",
    "chooses the cheapest",
    "picks the lowest",
    "schedules during the cheapest",
    "lowest-cost block",
    "minimum total",
    "winning block",
    "winning hour",
)


def _data_numbers(text: str, *, include_durations: bool = False) -> list[str]:
    duration_spans = [m.span() for m in _DURATION_NUM_RE.finditer(text)]
    nums: list[str] = []
    for match in _NUM_TOKEN_RE.finditer(text):
        start, end = match.span()
        if not include_durations and any(
            d_start <= start and end <= d_end for d_start, d_end in duration_spans
        ):
            continue
        nums.append(match.group(0))
    return nums


def _literal_richness(text: str, *, include_durations: bool = False) -> dict[str, int]:
    nums = _data_numbers(text, include_durations=include_durations)
    times = _TIME_RE.findall(text)
    return {
        "num_count": len(nums),
        "distinct_nums": len(set(nums)),
        "time_count": len(times),
    }


def _is_negative_case(case: dict[str, Any]) -> bool:
    ttype = str(case.get("test_type") or "positive").strip().lower()
    return ttype in {"negative", "boundary", "edge"}


def rejection_outcome_is_concrete(expected: str) -> bool:
    """True when a negative/rejection expected result is specific enough to verify."""
    blob = (expected or "").strip()
    if not blob or not _REJECTION_OUTCOME.search(blob):
        return False

    if _TIME_RANGE_RE.search(blob) or _TIME_RE.search(blob):
        return True

    duration_values = {m.group(1) for m in _DURATION_VALUE_RE.finditer(blob)}
    if len(duration_values) >= 2:
        return True

    richness = _literal_richness(blob, include_durations=True)
    if richness["distinct_nums"] >= 2:
        return True

    if re.search(
        r"\b(?:error(?:\s+message)?|validation message|blocking message|clear message|"
        r"cannot fit|can't fit|not enough|insufficient|"
        r"do not fit|does not fit|E-\d+)\b",
        blob,
        re.IGNORECASE,
    ):
        return True

    if re.search(
        r"\b(?:not enough|insufficient|cannot fit|can't fit|do not fit|does not fit)\b"
        r".*\b(?:contiguous|hours?|runtime|window|block)\b",
        blob,
        re.IGNORECASE,
    ):
        return True

    return False


def is_timezone_display_case(requirement: dict[str, Any], case: dict[str, Any]) -> bool:
    req_text = f"{requirement.get('summary') or ''} {requirement.get('detail') or ''}"
    case_text = "\n".join(
        [
            req_text,
            str(case.get("preconditions") or ""),
            str(case.get("expected_result") or ""),
        ]
    )
    return bool(_TIMEZONE_LITERAL.search(case_text)) and bool(
        re.search(r"\bdisplay(?:ed)?\b|\blocal(?:ized|isation|ization)?\b", case_text, re.I)
    )


def _case_input_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_str = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("preconditions") or ""),
            steps_str,
        ]
    )


def _comparison_min_distinct_candidates(requirement_text: str) -> int:
    """Infer how many distinct candidate values a comparison case should include."""
    default = max(2, int(os.environ.get("SUBSTANCE_COMPARISON_MIN_DISTINCT", "3")))
    text = (requirement_text or "").lower()
    hourly_floor = max(3, int(os.environ.get("SUBSTANCE_COMPARISON_HOURLY_MIN", "4")))

    if re.search(r"\bhourly\b", text) and re.search(
        r"\b(?:block|runtime|contiguous|window)\b", text
    ):
        return hourly_floor

    runtime_match = re.search(r"\b(\d+)\s*-?\s*hour", text)
    if runtime_match:
        return max(default, int(runtime_match.group(1)) + 1)

    if re.search(r"\b(?:block|contiguous|window|candidate|option)\b", text):
        return default

    return default


def _positive_selection_outcome_is_concrete(expected: str) -> bool:
    """Positive comparison cases must name hours, a range, or multiple comparable values."""
    blob = (expected or "").strip()
    if not blob:
        return False

    if _TIME_RANGE_RE.search(blob) or _TIME_RE.search(blob):
        return True

    richness = _literal_richness(blob, include_durations=True)
    if richness["distinct_nums"] >= 2:
        return True

    lowered = blob.lower()
    if any(phrase in lowered for phrase in _VAGUE_EXPECTED_PHRASES):
        return False
    if re.search(
        r"\b(?:cheapest|lowest|optimal|best)\b.*\b(?:block|hours?|window|slot)\b",
        lowered,
    ):
        return False

    return False


def _expected_outcome_is_concrete(
    expected: str,
    requirement_text: str,
    *,
    strict_positive_selection: bool = False,
) -> bool:
    """True when expected result gives a tester something specific to verify."""
    if strict_positive_selection:
        return _positive_selection_outcome_is_concrete(expected)

    if rejection_outcome_is_concrete(expected):
        return True

    blob = (expected or "").strip()
    if not blob:
        return False

    if _TIME_RANGE_RE.search(blob) or _TIME_RE.search(blob):
        return True

    richness = _literal_richness(blob)
    if richness["distinct_nums"] >= 2:
        return True
    if richness["num_count"] >= 1 and richness["time_count"] >= 1:
        return True

    lowered = blob.lower()
    if any(phrase in lowered for phrase in _VAGUE_EXPECTED_PHRASES):
        return False

    if richness["num_count"] >= 1 and re.search(
        r"\b(?:total|cost|sum|block|hours?|runs? at|scheduled at)\b", lowered
    ):
        return True

    req_words = {
        w
        for w in re.findall(r"[a-z]{4,}", (requirement_text or "").lower())
        if w not in {"shall", "system", "appliance", "within", "where", "each"}
    }
    exp_words = set(re.findall(r"[a-z]{4,}", lowered))
    if exp_words and exp_words.issubset(req_words) and richness["num_count"] == 0:
        return False

    return richness["num_count"] >= 1 and len(blob) >= 40


def comparison_substance_findings(
    requirement: dict[str, Any],
    case: dict[str, Any],
) -> list[str]:
    """Reject comparison-profile cases without verifiable candidate data and outcomes."""
    req_text = f"{requirement.get('summary') or ''} {requirement.get('detail') or ''}"
    input_text = _case_input_text(case)
    expected = str(case.get("expected_result") or "")
    negative = _is_negative_case(case)

    if negative and rejection_outcome_is_concrete(expected):
        input_richness = _literal_richness(input_text)
        if input_richness["distinct_nums"] >= 2 or input_richness["time_count"] >= 1:
            return []
        return [
            "Unexecutable - comparison/selection case is missing concrete candidate values "
            "(need at least 2 distinct values or explicit times in preconditions or steps)."
        ]

    min_distinct = _comparison_min_distinct_candidates(req_text)
    input_richness = _literal_richness(input_text)
    if (
        input_richness["distinct_nums"] < min_distinct
        and input_richness["num_count"] < min_distinct
    ):
        return [
            "Unexecutable - comparison/selection case is missing concrete candidate values "
            f"(need at least {min_distinct} distinct values in preconditions or steps)."
        ]

    if not _expected_outcome_is_concrete(
        expected,
        req_text,
        strict_positive_selection=not negative,
    ):
        return [
            "Unexecutable - expected result does not name a concrete verifiable outcome "
            "(for example specific hours, a block range, or compared totals)."
        ]

    return []
