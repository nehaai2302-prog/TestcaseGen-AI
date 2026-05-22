"""Split requirement text for embedding and generation."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from langchain_text_splitters import RecursiveCharacterTextSplitter

ParseQuality = Literal["ok", "ambiguous", "synthetic", "empty"]


@dataclass(frozen=True)
class RequirementSplit:
    requirement_id: str | None
    text: str
    is_synthetic: bool = False


# Prefix IDs: FR-2.4:, FR-3.1 (Cart Interaction):, NFR-4.1 (Data Protection):, etc.
_PREFIX_REQUIREMENT_RE = re.compile(
    r"""
    (?m)
    ^[ \t]*
    ((?:[-*\u2022]\s+)|)
    \**
    (?P<prefix>[A-Z]{2,10})
    [ \t_-]{0,3}
    (?P<num>\d+(?:\.\d+)*)
    \**
    (?:
        \s*(?:\([^)]*\))?
        \s*:
      | \.(?!\d)
      | (?=\s*$)
    )
    """,
    re.VERBOSE,
)

_NUMERIC_HEADING_RE = re.compile(
    r"""
    (?m)
    ^[ \t]*
    (?:[-*\u2022]\s+)?
    (?P<num>\d+(?:\.\d+){1,})
    \s*:
    """,
    re.VERBOSE,
)

_SECTION_HEADING_TRAILER_RE = re.compile(
    r"""
    ^\s*
    \d+(?:\.\d+)*
    \.?
    \s+
    \S.*?
    [^.!?:\s]
    \s*$
    """,
    re.VERBOSE,
)

_DEDUP_ID_SUFFIX_RE = re.compile(r"^[A-Z]{2,10}-\d+-\d+$")
_SHORT_PREFIX_ID_RE = re.compile(r"^[A-Z]{2,10}-\d+$")


def _strip_trailing_section_headings(block: str) -> str:
    lines = block.rstrip().split("\n")
    while lines:
        last = lines[-1].rstrip()
        if not last:
            lines.pop()
            continue
        if ":" in last:
            break
        if _SECTION_HEADING_TRAILER_RE.match(last):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


def _normalize_requirement_id(raw: str) -> str:
    value = re.sub(r"\s+", "-", raw.strip())
    value = re.sub(r'[\\/:*?"<>|]+', "-", value)
    return value.strip("-")


def _requirement_id_from_match(match: re.Match[str]) -> str:
    groups = match.groupdict()
    prefix = (groups.get("prefix") or "").upper()
    num = groups.get("num") or ""
    if prefix:
        return _normalize_requirement_id(f"{prefix}-{num}")
    return _normalize_requirement_id(num)


def _iter_requirement_matches(text: str) -> list[re.Match[str]]:
    matches = list(_PREFIX_REQUIREMENT_RE.finditer(text))
    matches.extend(_NUMERIC_HEADING_RE.finditer(text))
    matches.sort(key=lambda m: m.start())

    unique: list[re.Match[str]] = []
    last_end = -1
    for match in matches:
        if match.start() < last_end:
            continue
        unique.append(match)
        last_end = match.end()
    return unique


def structured_splits_low_confidence(splits: list[RequirementSplit]) -> bool:
    """True when regex splits look unreliable; Analyst LLM should re-parse."""
    if not splits or all(s.is_synthetic for s in splits):
        return False

    ids = [s.requirement_id for s in splits if s.requirement_id]
    if not ids:
        return True

    if sum(1 for rid in ids if _DEDUP_ID_SUFFIX_RE.match(rid or "")) >= 2:
        return True

    for split in splits:
        rid = split.requirement_id or ""
        if _SHORT_PREFIX_ID_RE.match(rid):
            first_line = (split.text or "").splitlines()[0].strip()
            if re.match(r"^\d+\b", first_line):
                return True

    if any(n >= 3 for n in Counter(ids).values()):
        return True

    return False


def assess_parse_quality(splits: list[RequirementSplit]) -> ParseQuality:
    if not splits:
        return "empty"
    if all(s.is_synthetic for s in splits):
        return "synthetic"
    if structured_splits_low_confidence(splits):
        return "ambiguous"
    return "ok"


def split_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [c.strip() for c in splitter.split_text(text) if c.strip()]


def split_requirements(text: str) -> list[RequirementSplit]:
    """Split structured docs into one row per requirement ID."""
    cleaned = text.strip()
    if not cleaned:
        return []

    matches = _iter_requirement_matches(cleaned)
    if not matches:
        return [
            RequirementSplit(
                requirement_id=f"REQ-{i + 1:02d}",
                text=chunk,
                is_synthetic=True,
            )
            for i, chunk in enumerate(split_text(cleaned))
        ]

    splits: list[RequirementSplit] = []
    seen: dict[str, int] = {}
    for idx, match in enumerate(matches):
        body_start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        body = cleaned[body_start:end].strip()

        req_id = _requirement_id_from_match(match)
        count = seen.get(req_id, 0) + 1
        seen[req_id] = count
        if count > 1:
            req_id = f"{req_id}-{count}"

        trimmed = _strip_trailing_section_headings(body)
        if not trimmed:
            continue

        splits.append(
            RequirementSplit(
                requirement_id=req_id,
                text=trimmed,
                is_synthetic=False,
            )
        )

    return splits
