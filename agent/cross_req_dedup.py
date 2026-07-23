"""Cross-requirement scenario dedup (shared error codes / failure modes).

Scoped semantic dedup stays within one requirement. This module catches the
case where two different requirements generate the same error-path scenario
(e.g. FR-5 NEG and FR-6 both asserting E-102).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_ERROR_CODE_RE = re.compile(
    r"\b(?:E|ERR|ERROR)[-_]?\d{2,5}\b",
    re.IGNORECASE,
)

_SPECIFIC_FAILURE_RE = re.compile(
    r"\b(?:"
    r"cannot\s+fit|can't\s+fit|does\s+not\s+fit|"
    r"not\s+enough\s+(?:contiguous\s+)?(?:hours?|runtime|window)|"
    r"insufficient\s+(?:hours?|runtime|window|space)|"
    r"runtime\s+exceeds|window\s+too\s+short|"
    r"blocking\s+message|validation\s+message"
    r")\b",
    re.IGNORECASE,
)


def _norm_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _case_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_str = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("preconditions") or ""),
            steps_str,
            str(case.get("expected_result") or ""),
        ]
    )


def extract_error_codes(text: str) -> set[str]:
    """Normalize codes like e-102 / ERR_102 → E-102."""
    out: set[str] = set()
    for match in _ERROR_CODE_RE.finditer(text or ""):
        raw = match.group(0).upper().replace("_", "-")
        letters = re.match(r"[A-Z]+", raw)
        digits = re.search(r"\d+", raw)
        if not digits:
            continue
        prefix = (letters.group(0) if letters else "E")
        if prefix.startswith("ERROR") or prefix.startswith("ERR"):
            prefix = "E"
        elif len(prefix) > 1 and prefix != "E":
            prefix = prefix[0]
        out.add(f"{prefix}-{digits.group(0)}")
    return out


def scenario_keys(case: dict[str, Any]) -> list[tuple[str, str]]:
    """Keys that identify a shared failure scenario across requirements.

    Returns zero or more keys:
    - ('error_code', 'E-102')
    - ('expected_failure', '<hash>') when expected_result is a concrete shared
      failure path (negatives only; avoids generic 'rejected' collisions).
    """
    text = _case_text(case)
    keys: list[tuple[str, str]] = []
    for code in sorted(extract_error_codes(text)):
        keys.append(("error_code", code))

    ttype = str(case.get("test_type") or "positive").strip().lower()
    expected = _norm_text(str(case.get("expected_result") or ""))
    if (
        ttype in {"negative", "boundary", "edge"}
        and expected
        and len(expected) >= 40
        and _SPECIFIC_FAILURE_RE.search(expected)
    ):
        digest = hashlib.sha256(expected.encode()).hexdigest()[:16]
        keys.append(("expected_failure", digest))

    return keys


def cross_requirement_scenario_dedup(
    cases: list[dict[str, Any]],
    *,
    seed_cases: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep first case per shared scenario key; flag later ones from other reqs.

    ``seed_cases`` (e.g. already-accepted regen priors) populate the seen map
    but are not returned in ``kept``.
    """
    kept: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    # key → (keeper_title, keeper_requirement)
    seen: dict[tuple[str, str], tuple[str, str]] = {}

    for case in seed_cases or []:
        rid = str(case.get("linked_requirement") or "").strip()
        title = str(case.get("title") or "")
        for key in scenario_keys(case):
            if key not in seen:
                seen[key] = (title, rid)

    for case in cases:
        rid = str(case.get("linked_requirement") or "").strip()
        title = str(case.get("title") or "")
        keys = scenario_keys(case)
        matched: tuple[str, str] | None = None
        matched_key: tuple[str, str] | None = None

        for key in keys:
            prior = seen.get(key)
            if not prior:
                continue
            prior_title, prior_rid = prior
            if prior_rid and rid and prior_rid != rid:
                matched = (prior_title, prior_rid)
                matched_key = key
                break

        if matched and matched_key:
            kind, value = matched_key
            if kind == "error_code":
                detail = f"shared error code {value}"
            else:
                detail = "identical failure expected result"
            duplicates.append(
                {
                    **case,
                    "is_duplicate": True,
                    "duplicate_reason": "cross_requirement_scenario_duplicate",
                    "similar_to_title": matched[0],
                    "similar_to_requirement": matched[1],
                    "scenario_match": detail,
                }
            )
            continue

        for key in keys:
            if key not in seen:
                seen[key] = (title, rid)
        kept.append(case)

    return kept, duplicates
