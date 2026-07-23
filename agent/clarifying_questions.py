"""Build clarifying questions for the spec author (distinct from hard contradictions).

Questions may reference blocked contradiction pairs (so the author knows what to
resolve) or underspecified but still-generatable requirements.
"""

from __future__ import annotations

import re
from typing import Any

from agent.execution_profile import normalize_execution_profile

_VAGUE_PHRASE_RE = re.compile(
    r"\b(?:"
    r"as\s+appropriate|as\s+needed|if\s+applicable|where\s+applicable|"
    r"reasonable|sufficient|etc\.?|and\s+so\s+on|"
    r"tbd|tbc|to\s+be\s+defined|to\s+be\s+confirmed|to\s+be\s+decided|"
    r"unspecified|not\s+specified|left\s+undefined"
    r")\b",
    re.IGNORECASE,
)

_TIE_BREAK_RE = re.compile(
    r"\b(?:tie[\s-]?break|equal(?:ly)?\s+(?:cheap|priced|low)|"
    r"same\s+price|identical\s+(?:cost|price)|when\s+(?:tied|equal))\b",
    re.IGNORECASE,
)

_TIMEZONE_RE = re.compile(
    r"\b(?:timezone|time\s*zone|UTC|local\s+time|user'?s\s+local)\b",
    re.IGNORECASE,
)

_TIME_LITERAL_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

_EQUALITY_BOUNDARY_RE = re.compile(
    r"(?:"
    # Clear inequality phrasing (with or without an immediate number)
    r"\b(?:strictly\s+)?(?:less\s+than|greater\s+than|"
    r"at\s+or\s+below|at\s+or\s+above|"
    r"less\s+than\s+or\s+equal|greater\s+than\s+or\s+equal)\b|"
    # below/above as threshold language ("below the threshold")
    r"\b(?:strictly\s+)?(?:below|above)\b|"
    # under/over only when followed by an amount — avoids "precedence over",
    # "under standard load", etc.
    r"\b(?:strictly\s+)?(?:under|over)\s+[€$]?\d"
    r")",
    re.IGNORECASE,
)


def _rule_text(rule: dict[str, Any]) -> str:
    return " ".join(
        [
            str(rule.get("summary") or ""),
            str(rule.get("detail") or ""),
            str(rule.get("text") or ""),
        ]
    ).strip()


def _qid(rule_ids: list[str], question: str) -> str:
    ids = ",".join(sorted({r for r in rule_ids if r}))
    return f"{ids}|{question.strip().lower()[:120]}"


def questions_from_contradictions(
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn hard contradictions into author-facing open questions."""
    out: list[dict[str, Any]] = []
    for row in contradictions:
        rid = str(row.get("rule_id") or "").strip()
        related = [
            str(r).strip()
            for r in (row.get("related_rule_ids") or [])
            if str(r).strip()
        ]
        issue = (row.get("issue") or "").strip() or "Conflicting requirements"
        rule_ids = [rid] if rid else []
        rule_ids.extend(r for r in related if r not in rule_ids)
        if not rule_ids:
            continue
        out.append(
            {
                "rule_ids": rule_ids,
                "question": (
                    f"Which interpretation should apply for {', '.join(rule_ids)}? "
                    f"{issue}"
                ),
                "why_it_matters": (
                    "These requirements are blocked from generation until the conflict "
                    "is resolved; otherwise QA cannot know which behavior to assert."
                ),
                "source": "contradiction",
            }
        )
    return out


def questions_from_underspecification(
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Heuristics for underspecified but non-contradictory requirements."""
    out: list[dict[str, Any]] = []
    for rule in rules:
        rid = str(rule.get("rule_id") or "").strip()
        if not rid:
            continue
        if rule.get("status") == "requires_clarification":
            # Covered by contradiction-derived questions when applicable.
            continue
        text = _rule_text(rule)
        if not text:
            continue
        profile = normalize_execution_profile(
            rule.get("execution_profile"),
            text,
            rule.get("constraints") or [],
        )

        if _VAGUE_PHRASE_RE.search(text):
            out.append(
                {
                    "rule_ids": [rid],
                    "question": (
                        f"For {rid}, what concrete acceptance criteria replace vague "
                        "wording (e.g. 'as needed', 'reasonable', 'TBD')?"
                    ),
                    "why_it_matters": (
                        "Vague criteria produce weak or untestable cases; the author "
                        "should name measurable limits or expected outcomes."
                    ),
                    "source": "underspecification",
                }
            )

        if profile == "comparison" and not _TIE_BREAK_RE.search(text):
            out.append(
                {
                    "rule_ids": [rid],
                    "question": (
                        f"For {rid}, what should happen when two candidates tie "
                        "(same price/score)?"
                    ),
                    "why_it_matters": (
                        "Without a tie-break rule, comparison tests must guess which "
                        "winner is correct."
                    ),
                    "source": "underspecification",
                }
            )

        if (
            _TIME_LITERAL_RE.search(text)
            and not _TIMEZONE_RE.search(text)
            and profile in {"scheduling", "config", "general"}
        ):
            # Only ask once-ish when times are operational (quiet hours etc.)
            if re.search(r"\b(?:quiet\s+hours?|schedule|window|local)\b", text, re.I):
                out.append(
                    {
                        "rule_ids": [rid],
                        "question": (
                            f"For {rid}, which timezone do the stated clock times use "
                            "(UTC, device local, user preference)?"
                        ),
                        "why_it_matters": (
                            "Ambiguous timebases cause false fails around DST and "
                            "cross-region testing."
                        ),
                        "source": "underspecification",
                    }
                )

        if (
            profile in {"config", "comparison", "scheduling"}
            and _EQUALITY_BOUNDARY_RE.search(text)
            and not re.search(
                r"\b(?:equal(?:s|ity)?|exactly\s+at|==|at\s+the\s+threshold)\b",
                text,
                re.I,
            )
        ):
            out.append(
                {
                    "rule_ids": [rid],
                    "question": (
                        f"For {rid}, what is the expected behavior exactly at the "
                        "boundary value (equality)?"
                    ),
                    "why_it_matters": (
                        "Boundary equality is a common source of conflicting tests when "
                        "the SRS only states strict inequalities."
                    ),
                    "source": "underspecification",
                }
            )

    return out


def merge_clarifying_questions(
    *groups: list[dict[str, Any]],
    max_questions: int = 24,
) -> list[dict[str, Any]]:
    """Deduplicate by rule_ids + question text; preserve first-seen order."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for group in groups:
        for row in group:
            question = str(row.get("question") or "").strip()
            rule_ids = [
                str(r).strip()
                for r in (row.get("rule_ids") or [])
                if str(r).strip()
            ]
            if not question or not rule_ids:
                continue
            key = _qid(rule_ids, question)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "rule_ids": rule_ids,
                    "question": question,
                    "why_it_matters": str(row.get("why_it_matters") or "").strip(),
                    "source": str(row.get("source") or "analyst").strip() or "analyst",
                }
            )
            if len(out) >= max_questions:
                return out
    return out


def build_clarifying_questions(
    rules: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    *,
    llm_questions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Combine contradiction, underspecification, and optional LLM questions."""
    return merge_clarifying_questions(
        questions_from_contradictions(contradictions),
        list(llm_questions or []),
        questions_from_underspecification(rules),
    )
