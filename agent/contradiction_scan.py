"""Lightweight cross-rule contradiction scan (spec-agnostic heuristics)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_THRESHOLD = re.compile(r"\bthreshold\b", re.IGNORECASE)
# Optional adjectives between determiner and "price threshold" (e.g. "user-defined price threshold").
_THRESHOLD_PHRASE = (
    r"(?:the\s+)?(?:\w+(?:\s+\w+)*\s+)?(?:price\s+)?threshold"
)
_STRICT_BELOW_THRESHOLD = re.compile(
    r"(?:<\s*" + _THRESHOLD_PHRASE + r"|"
    r"(?:less|lower)\s+than\s+" + _THRESHOLD_PHRASE + r"|"
    r"(?:under|below)\s+" + _THRESHOLD_PHRASE + r"|"
    r"\bstrictly\s+below\b|"
    r"only\s+(?:when\s+)?(?:the\s+)?(?:hourly\s+)?(?:spot\s+)?price\s+is\s+below|"
    r"price\s+(?:is\s+)?below\s+" + _THRESHOLD_PHRASE + r")",
    re.IGNORECASE,
)
_INCLUSIVE_AT_OR_BELOW_THRESHOLD = re.compile(
    r"(?:at or below|equal to or below|not above|≤|<=)\s+"
    r"(?:the\s+)?(?:\w+(?:\s+\w+)*\s+)?(?:price\s+)?threshold|"
    r"(?:at or below|equal to or below)\s+(?:the\s+)?threshold|"
    r"(?:less|lower)\s+than\s+or\s+equal\s+to\s+" + _THRESHOLD_PHRASE + r"|"
    r"no\s+hour\b.*?"
    r"(?:at or below|equal to or below|not above|less than or equal to)\s+"
    r"(?:the\s+)?(?:\w+(?:\s+)?)*threshold|"
    r"no\s+hour(?:s)?\s+(?:in\s+.+?\s+)?(?:has|have|with)\s+"
    r"(?:a\s+)?(?:\w+\s+)*price\s+"
    r"(?:at or below|equal to or below|not above|less than or equal to)\s+"
    r"(?:the\s+)?threshold|"
    r"matches?\s+the\s+threshold|"
    r"priced\s+exactly\s+at",
    re.IGNORECASE,
)
_RUNTIME_BEHAVIOR = re.compile(
    r"(?:shall|must)(?:\s+[\w-]+){0,6}\s+(?:run|schedule|start)|"
    r"(?:run|schedule|start)\s+when|"
    r"\bthreshold\s+mode\b|"
    r"\bskip(?:ped)?\b|"
    r"\bshall\s+not\s+run\b|"
    r"\bmust\s+not\s+run\b|"
    r"\bdo\s+not\s+run\b|"
    r"\bnot\s+run\b|"
    r"\bno\s+hour",
    re.IGNORECASE,
)

_NOTIFICATION = re.compile(
    r"\b(?:push\s+)?notifications?\b|\bnotify(?:ing|ication)?\s+the\s+user\b|\balerts?\b",
    re.IGNORECASE,
)
_IMMEDIATE_NOTIFICATION = re.compile(
    r"\b(?:immediately|at once|right away|without delay)\b|"
    r"\b(?:send|deliver)\b[^.]{0,80}\b(?:immediately|at once)\b|"
    r"\b(?:immediately|at once)\b[^.]{0,80}\b(?:when|upon)\b",
    re.IGNORECASE,
)
_DEFERRED_NOTIFICATION = re.compile(
    r"\b(?:queued?|defer(?:red)?|held|suppress(?:ed)?)\b|"
    r"\bshall\s+not\s+be\s+delivered\b|"
    r"\bnot\s+be\s+delivered\s+during\b|"
    r"\bnot\s+delivered\s+during\b|"
    r"\bdelivered?\s+when\b[^.]{0,60}\b(?:end|over)\b|"
    r"\bqueue\b[^.]{0,40}\b(?:until|when)\b",
    re.IGNORECASE,
)
_QUIET_OR_RESTRICTED_WINDOW = re.compile(
    r"\bquiet\s+hours?\b|"
    r"\bdo[- ]not[- ]disturb\b|"
    r"\brestricted\s+(?:hours?|period|window)\b|"
    r"\bnight\s+(?:hours?|period|curfew)\b|"
    r"\bsilent\s+hours?\b",
    re.IGNORECASE,
)
_SCHEDULE_OR_EVENT_TRIGGER = re.compile(
    r"\b(?:daily\s+)?schedule\s+is\s+created\b|"
    r"\bwhen\s+(?:a\s+)?(?:daily\s+)?schedule\b|"
    r"\bupon\s+schedule\s+(?:creation|generation)\b|"
    r"\bwhen\s+.{0,40}\b(?:created|generated|computed)\b",
    re.IGNORECASE,
)

# Generated-case signals for the same boundary disagreement.
_CASE_EQUALITY_AT_THRESHOLD = re.compile(
    r"(?:exactly\s+at|priced\s+exactly\s+at|equal\s+to\s+the\s+threshold|"
    r"matches?\s+the\s+threshold|at\s+or\s+below\s+the\s+threshold|"
    r"hour(?:s)?\s+priced\s+exactly\s+at)",
    re.IGNORECASE,
)
_CASE_STRICT_EQUALITY_OUTCOME = re.compile(
    r"(?:strictly\s+below|only\s+hours?\s+strictly\s+below|"
    r"not\s+scheduled\s+to\s+run|is\s+not\s+scheduled\s+to\s+run|"
    r"shall\s+not\s+run|must\s+not\s+run)",
    re.IGNORECASE,
)
_CASE_INCLUSIVE_EQUALITY_OUTCOME = re.compile(
    r"(?:not\s+skipped|is\s+not\s+skipped|cycle\s+is\s+not\s+skipped|"
    r"matches?\s+the\s+threshold|at\s+or\s+below\s+the\s+threshold)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class NotificationSemantics:
    mentions_notification: bool
    immediate_delivery: bool
    deferred_or_restricted: bool
    mentions_quiet_window: bool
    mentions_schedule_trigger: bool


@dataclass(frozen=True)
class ThresholdSemantics:
    mentions_threshold: bool
    strict_below: bool
    inclusive_at_or_below: bool
    runtime_behavior: bool


def _chunk_indexes(
    requirement_chunks: list[dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_req_id: dict[str, dict[str, Any]] = {}
    for chunk in requirement_chunks or []:
        cid = str(chunk.get("id") or "").strip()
        if cid:
            by_id[cid] = chunk
        req_id = str(chunk.get("requirement_id") or "").strip()
        if req_id:
            by_req_id[req_id] = chunk
    return by_id, by_req_id


def _rule_text(
    rule: dict[str, Any],
    *,
    chunk_by_id: dict[str, dict[str, Any]] | None = None,
    chunk_by_req_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Combine analyst fields with ingested requirement chunk text when available."""
    parts: list[str] = [
        str(rule.get("summary") or ""),
        str(rule.get("detail") or ""),
    ]
    for cid in rule.get("source_requirement_chunk_ids") or []:
        chunk = (chunk_by_id or {}).get(str(cid))
        if chunk:
            parts.append(str(chunk.get("chunk_text") or ""))
    rid = str(rule.get("rule_id") or "").strip()
    if rid and chunk_by_req_id and rid in chunk_by_req_id:
        parts.append(str(chunk_by_req_id[rid].get("chunk_text") or ""))
    return " ".join(part.strip() for part in parts if part and part.strip())


def _case_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_str = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("description") or ""),
            str(case.get("preconditions") or ""),
            steps_str,
            str(case.get("expected_result") or ""),
        ]
    )


def classify_notification_semantics(text: str) -> NotificationSemantics:
    return NotificationSemantics(
        mentions_notification=bool(_NOTIFICATION.search(text)),
        immediate_delivery=bool(_IMMEDIATE_NOTIFICATION.search(text)),
        deferred_or_restricted=bool(_DEFERRED_NOTIFICATION.search(text)),
        mentions_quiet_window=bool(_QUIET_OR_RESTRICTED_WINDOW.search(text)),
        mentions_schedule_trigger=bool(_SCHEDULE_OR_EVENT_TRIGGER.search(text)),
    )


def classify_threshold_semantics(text: str) -> ThresholdSemantics:
    return ThresholdSemantics(
        mentions_threshold=bool(_THRESHOLD.search(text)),
        strict_below=bool(_STRICT_BELOW_THRESHOLD.search(text)),
        inclusive_at_or_below=bool(_INCLUSIVE_AT_OR_BELOW_THRESHOLD.search(text)),
        runtime_behavior=bool(_RUNTIME_BEHAVIOR.search(text)),
    )


def _notification_timing_issue(
    sem_a: NotificationSemantics,
    sem_b: NotificationSemantics,
) -> str | None:
    if not sem_a.mentions_notification or not sem_b.mentions_notification:
        return None

    a_immediate = sem_a.immediate_delivery and not sem_a.deferred_or_restricted
    b_immediate = sem_b.immediate_delivery and not sem_b.deferred_or_restricted
    a_deferred = sem_a.deferred_or_restricted and not sem_a.immediate_delivery
    b_deferred = sem_b.deferred_or_restricted and not sem_b.immediate_delivery

    if not ((a_immediate and b_deferred) or (b_immediate and a_deferred)):
        return None

    shares_context = (
        sem_a.mentions_quiet_window
        or sem_b.mentions_quiet_window
        or sem_a.mentions_schedule_trigger
        or sem_b.mentions_schedule_trigger
    )
    if not shares_context:
        return None

    return (
        "Ambiguous notification timing: one rule requires immediate delivery while "
        "another defers or suppresses delivery during a restricted time window."
    )


def _notification_timing_conflict(text_a: str, text_b: str) -> str | None:
    return _notification_timing_issue(
        classify_notification_semantics(text_a),
        classify_notification_semantics(text_b),
    )


def _threshold_boundary_issue(sem_a: ThresholdSemantics, sem_b: ThresholdSemantics) -> str | None:
    if not sem_a.mentions_threshold or not sem_b.mentions_threshold:
        return None
    if not sem_a.runtime_behavior or not sem_b.runtime_behavior:
        return None

    a_strict = sem_a.strict_below and not sem_a.inclusive_at_or_below
    b_strict = sem_b.strict_below and not sem_b.inclusive_at_or_below
    a_inclusive = sem_a.inclusive_at_or_below
    b_inclusive = sem_b.inclusive_at_or_below

    if (a_strict and b_inclusive) or (b_strict and a_inclusive):
        return (
            "Ambiguous at price == threshold: one rule uses strict less-than while "
            "another treats threshold as qualifying (at or below)."
        )
    return None


def _threshold_boundary_conflict(text_a: str, text_b: str) -> str | None:
    return _threshold_boundary_issue(
        classify_threshold_semantics(text_a),
        classify_threshold_semantics(text_b),
    )


def _contradiction_row(id_a: str, id_b: str, issue: str) -> dict[str, Any]:
    return {
        "rule_id": id_a,
        "related_rule_ids": [id_b],
        "issue": f"{issue} Compare {id_a} with {id_b}.",
    }


def _spec_pair_conflict(text_a: str, text_b: str) -> str | None:
    return _threshold_boundary_conflict(text_a, text_b) or _notification_timing_conflict(
        text_a, text_b
    )


def scan_spec_contradictions(
    rules: list[dict[str, Any]],
    *,
    requirement_chunks: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Detect pairwise specification conflicts without an LLM pass."""
    contradictions: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()
    chunk_by_id, chunk_by_req_id = _chunk_indexes(requirement_chunks)

    for i, rule_a in enumerate(rules):
        id_a = (rule_a.get("rule_id") or "").strip()
        if not id_a:
            continue
        text_a = _rule_text(rule_a, chunk_by_id=chunk_by_id, chunk_by_req_id=chunk_by_req_id)
        for rule_b in rules[i + 1 :]:
            id_b = (rule_b.get("rule_id") or "").strip()
            if not id_b:
                continue
            pair = frozenset({id_a, id_b})
            if pair in seen:
                continue

            issue = _spec_pair_conflict(
                text_a,
                _rule_text(rule_b, chunk_by_id=chunk_by_id, chunk_by_req_id=chunk_by_req_id),
            )
            if not issue:
                continue

            seen.add(pair)
            contradictions.append(_contradiction_row(id_a, id_b, issue))

    return contradictions


def scan_generated_case_contradictions(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect cross-requirement testcase conflicts at price == threshold."""
    findings: list[dict[str, Any]] = []
    seen: set[frozenset[str]] = set()

    boundary_cases: list[dict[str, Any]] = []
    for case in cases:
        blob = _case_text(case)
        if not _CASE_EQUALITY_AT_THRESHOLD.search(blob):
            continue
        rid = str(case.get("linked_requirement") or "").strip()
        if not rid:
            continue
        strict_outcome = bool(_CASE_STRICT_EQUALITY_OUTCOME.search(blob))
        inclusive_outcome = bool(_CASE_INCLUSIVE_EQUALITY_OUTCOME.search(blob))
        if not strict_outcome and not inclusive_outcome:
            continue
        boundary_cases.append(
            {
                "case": case,
                "rule_id": rid,
                "title": str(case.get("title") or ""),
                "strict_outcome": strict_outcome,
                "inclusive_outcome": inclusive_outcome and not strict_outcome,
            }
        )

    for i, row_a in enumerate(boundary_cases):
        for row_b in boundary_cases[i + 1 :]:
            if row_a["rule_id"] == row_b["rule_id"]:
                continue
            if not (
                (row_a["strict_outcome"] and row_b["inclusive_outcome"])
                or (row_b["strict_outcome"] and row_a["inclusive_outcome"])
            ):
                continue

            pair = frozenset({row_a["rule_id"], row_b["rule_id"]})
            if pair in seen:
                continue
            seen.add(pair)

            issue = (
                "Contradictory boundary tests at price == threshold: "
                f"{row_a['rule_id']} expects strict below-threshold behavior while "
                f"{row_b['rule_id']} treats threshold equality as qualifying (or vice versa)."
            )
            findings.append(
                {
                    "rule_id": row_a["rule_id"],
                    "related_rule_ids": [row_b["rule_id"]],
                    "issue": issue,
                    "case_titles": [row_a["title"], row_b["title"]],
                }
            )

    return findings


def merge_contradictions(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[frozenset[str], dict[str, Any]] = {}
    for group in groups:
        for row in group:
            rid = (row.get("rule_id") or "").strip()
            related = [str(r).strip() for r in row.get("related_rule_ids") or [] if str(r).strip()]
            if not rid:
                continue
            key = frozenset({rid, *related})
            merged.setdefault(key, row)
    return list(merged.values())
