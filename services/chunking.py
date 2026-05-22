"""Split requirement text for embedding and generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass(frozen=True)
class RequirementSplit:
    requirement_id: str | None
    text: str
    is_synthetic: bool = False


# Prefix-style requirement IDs (FR-1.1:, US-103:, REQ-12., - **FR-2.2**:).
# Anchored to line start (with optional bullet/bold markers) and requires a `:`
# or `.` separator. Case-sensitive on purpose: lowercase English words like
# "of", "in", "as" must NOT match.
_PREFIX_REQUIREMENT_RE = re.compile(
    r"""
    (?m)                              # multiline so ^ means start of a line
    ^[ \t]*                           # optional leading indent
    (?:[-*\u2022]\s+)?                # optional bullet (-, *, or U+2022)
    \**                               # optional opening **bold**
    (?P<prefix>[A-Z]{2,10})           # UPPERCASE prefix only
    [ \t_-]{0,3}                      # short separator, never crosses newlines
    (?P<num>\d+(?:\.\d+)*)            # 1, 1.1, 2.3.4 ...
    \**                               # optional closing **bold**
    \s*[:.]                           # MUST be followed by : or .
    """,
    re.VERBOSE,
)

# Numeric-only requirement IDs (1.2.3:, 4.1:). Need a colon to avoid matching
# normal section headings like "2.1 Coupon Input and Submission" or "1. Intro".
_NUMERIC_HEADING_RE = re.compile(
    r"""
    (?m)
    ^[ \t]*
    (?:[-*\u2022]\s+)?
    (?P<num>\d+(?:\.\d+){1,})         # at least two dotted parts (1.2 minimum)
    \s*:                              # REQUIRE colon; period is too ambiguous
    """,
    re.VERBOSE,
)

# Trailing section-heading detector. Matches lines like "2.1 Coupon Input",
# "2. Functional Requirements (FR)" or "1. Introduction" - a leading section
# number followed by title text that does NOT end in sentence punctuation. We
# use the "no terminal . ! ? :" tail to avoid mistaking numbered list items
# ("1. Click Save.") for headings.
_SECTION_HEADING_TRAILER_RE = re.compile(
    r"""
    ^\s*
    \d+(?:\.\d+)*                     # leading section number
    \.?                               # optional dot after the number
    \s+                               # whitespace before the title
    \S.*?                             # title text
    [^.!?:\s]                         # title ends with non-punctuation
    \s*$
    """,
    re.VERBOSE,
)


def _strip_trailing_section_headings(block: str) -> str:
    """Remove trailing section-heading lines (and blank lines) from a body block.

    Requirements come from a single match anchored at the requirement ID. Any
    section heading that sits between this requirement and the next one is
    sliced into this requirement's tail by the split loop. Strip those so the
    requirement body only contains its own content.
    """
    lines = block.rstrip().split("\n")
    while lines:
        last = lines[-1].rstrip()
        if not last:
            lines.pop()
            continue
        if ":" in last:
            # A line with a colon is content (or a requirement we already
            # matched). Never strip.
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
    """Build a clean requirement ID from named groups.

    Using match.group(0) here would re-include the leading bullet (`-`, `*`,
    `\u2022`), any opening `**` bold markers, surrounding whitespace and the
    trailing `:`/`.` punctuation in the ID. We always reconstruct from the
    `prefix` and `num` groups so the ID is canonical (e.g. FR-1.1).
    """
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

    # Drop overlaps, preferring the match that appears first in the sorted order.
    unique: list[re.Match[str]] = []
    last_end = -1
    for match in matches:
        if match.start() < last_end:
            continue
        unique.append(match)
        last_end = match.end()
    return unique


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
    chunks = splitter.split_text(text)
    return [c.strip() for c in chunks if c.strip()]


def split_requirements(text: str) -> list[RequirementSplit]:
    """Split structured docs into one row per requirement ID.

    Supports IDs like FR-2.2, FR 2.2, US-103, REQ-12, custom prefixes, and numeric
    headings such as 1.2.3. If no IDs are found, falls back to character
    chunks with synthetic REQ-01, REQ-02, ... IDs.
    """
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
        # Body starts AFTER the matched ID prefix (and its trailing :/.) so the
        # bullet + ID + colon don't get duplicated into the requirement text.
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
