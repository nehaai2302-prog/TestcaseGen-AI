"""Extract and check specification facts (quiet hours, DST day lengths).

Spec-agnostic: facts are parsed from requirement text patterns, not hardcoded
product IDs. Callers attach ``source_rule_id`` when indexing a project.
"""

from __future__ import annotations

import re
from typing import Any

_TIME = r"\d{1,2}:\d{2}"

_QUIET_WINDOW_RE = re.compile(
    r"quiet\s+hours?\b[^.\n]{0,80}?"
    r"(?:(?:are|is|=|:)\s*)?"
    r"(?:from\s+)?"
    rf"(?P<start>{_TIME})\s*(?:[-–]|to)\s*(?P<end>{_TIME})",
    re.IGNORECASE,
)

_QUIET_END_RE = re.compile(
    r"quiet\s+hours?\b[^.\n]{0,60}?"
    rf"(?:end(?:s|ing)?|until|through)\s+(?:at\s+)?(?P<end>{_TIME})",
    re.IGNORECASE,
)

_DST_SPRING_RE = re.compile(
    r"(?:spring[\s-]?forward|clocks?\s+(?:spring\s+)?forward|"
    r"dst\s+start|daylight\s+saving[s]?\s+(?:begins?|starts?))",
    re.IGNORECASE,
)
_DST_FALL_RE = re.compile(
    r"(?:fall[\s-]?back|autumn[\s-]?back|clocks?\s+fall\s+back|"
    r"dst\s+end|daylight\s+saving[s]?\s+(?:ends?|stops?))",
    re.IGNORECASE,
)

_HOUR_DAY_RE = re.compile(
    r"\b(?P<hours>23|25)[\s-]?hours?\s+days?\b|"
    r"\b(?:day|calendar\s+day)\s+(?:has|contains|is)\s+(?P<hours2>23|25)\s+hours?\b|"
    r"\b(?P<hours3>23|25)\s+hours?\s+(?:in\s+)?(?:the\s+)?(?:day|calendar\s+day)\b",
    re.IGNORECASE,
)

_INVENTED_EXAMPLE_RE = re.compile(
    r"\b(?:invented|hypothetical|made[\s-]?up|for\s+illustration)\b|"
    r"\b(?:example\s+only|not\s+from\s+(?:the\s+)?spec)\b",
    re.IGNORECASE,
)

# Config/settings tests intentionally set quiet hours to non-default values.
_QUIET_CONFIG_TITLE_RE = re.compile(
    r"\b(?:define|configure|set|change|update)\b.{0,40}\bquiet\s+hours\b",
    re.IGNORECASE,
)
_QUIET_CONFIG_ACTION_RE = re.compile(
    r"(?:"
    r"set\s+the\s+(?:start|end)\s+time\s+to|"
    r"(?:set|change|update)\s+(?:the\s+)?quiet\s+hours|"
    r"open\s+(?:the\s+)?(?:\w+\s+)?quiet\s+hours\s+settings|"
    r"save\s+(?:the\s+)?quiet\s+hours"
    r")",
    re.IGNORECASE,
)
_QUIET_CONFIG_SAVE_RE = re.compile(
    r"\b(?:saved?\s+successfully|are\s+saved|settings\s+page\s+shows|"
    r"quiet\s+hours\s+are\s+saved)\b",
    re.IGNORECASE,
)

_MARCH_RE = re.compile(r"\b(?:march|mar\.?)\b", re.IGNORECASE)
_NOV_RE = re.compile(r"\b(?:november|nov\.?)\b", re.IGNORECASE)


def _norm_time(raw: str) -> str:
    parts = raw.strip().split(":")
    if len(parts) != 2:
        return raw.strip()
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return raw.strip()
    return f"{h:02d}:{m:02d}"


def extract_spec_facts(text: str) -> list[dict[str, Any]]:
    """Parse quiet-hour windows and DST day-length facts from requirement text."""
    src = text or ""
    facts: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    def _add(fact: dict[str, Any]) -> None:
        key = (
            fact.get("type"),
            fact.get("start"),
            fact.get("end"),
            fact.get("transition"),
            fact.get("hours"),
        )
        if key in seen:
            return
        seen.add(key)
        facts.append(fact)

    for match in _QUIET_WINDOW_RE.finditer(src):
        _add(
            {
                "type": "quiet_hours_window",
                "start": _norm_time(match.group("start")),
                "end": _norm_time(match.group("end")),
            }
        )

    for match in _QUIET_END_RE.finditer(src):
        end = _norm_time(match.group("end"))
        # Prefer full windows when already found; still record end-only if new.
        if not any(
            f.get("type") == "quiet_hours_window" and f.get("end") == end for f in facts
        ):
            _add({"type": "quiet_hours_end", "end": end})

    # Pair DST transition phrases with nearby day-length claims (same sentence /
    # short window), and also accept explicit "spring-forward … 23-hour" prose.
    for match in _HOUR_DAY_RE.finditer(src):
        hours_raw = match.group("hours") or match.group("hours2") or match.group("hours3")
        if not hours_raw:
            continue
        hours = int(hours_raw)
        window = src[max(0, match.start() - 120) : min(len(src), match.end() + 120)]
        spring = bool(_DST_SPRING_RE.search(window) or _MARCH_RE.search(window))
        fall = bool(_DST_FALL_RE.search(window) or _NOV_RE.search(window))
        if spring and not fall:
            _add(
                {
                    "type": "dst_day_length",
                    "transition": "spring_forward",
                    "hours": hours,
                }
            )
        elif fall and not spring:
            _add(
                {
                    "type": "dst_day_length",
                    "transition": "fall_back",
                    "hours": hours,
                }
            )
        elif spring and fall:
            # Ambiguous window — skip rather than guess.
            continue

    # Spec may state both transitions without repeating "hour day" twice in one
    # match window; scan sentences that name a transition and an hour count.
    for sentence in re.split(r"[.\n;]+", src):
        s = sentence.strip()
        if not s:
            continue
        hour_m = _HOUR_DAY_RE.search(s)
        if not hour_m:
            continue
        hours_raw = hour_m.group("hours") or hour_m.group("hours2") or hour_m.group("hours3")
        if not hours_raw:
            continue
        hours = int(hours_raw)
        spring = bool(_DST_SPRING_RE.search(s) or _MARCH_RE.search(s))
        fall = bool(_DST_FALL_RE.search(s) or _NOV_RE.search(s))
        if spring and not fall:
            _add(
                {
                    "type": "dst_day_length",
                    "transition": "spring_forward",
                    "hours": hours,
                }
            )
        elif fall and not spring:
            _add(
                {
                    "type": "dst_day_length",
                    "transition": "fall_back",
                    "hours": hours,
                }
            )

    return facts


def build_project_spec_facts(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Index facts from all atomic rules with source_rule_id."""
    out: list[dict[str, Any]] = []
    for rule in rules:
        rid = str(rule.get("rule_id") or "").strip()
        text = " ".join(
            [
                str(rule.get("summary") or ""),
                str(rule.get("detail") or ""),
                str(rule.get("text") or ""),
            ]
        )
        for fact in extract_spec_facts(text):
            row = dict(fact)
            if rid:
                row["source_rule_id"] = rid
            out.append(row)
    return out


def _case_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    steps_text = "\n".join(str(s) for s in steps) if isinstance(steps, list) else str(steps)
    return "\n".join(
        [
            str(case.get("title") or ""),
            str(case.get("description") or ""),
            str(case.get("preconditions") or ""),
            steps_text,
            str(case.get("expected_result") or ""),
        ]
    )


def _case_quiet_windows(text: str) -> list[tuple[str, str]]:
    """Quiet-hour *definitions* asserted in the case (not schedule times).

    Skips phrases like ``outside quiet hours, 08:00-09:00`` where the times are
    the scheduled run window, not the quiet-hours configuration.
    """
    windows: list[tuple[str, str]] = []
    for match in _QUIET_WINDOW_RE.finditer(text):
        prefix = text[max(0, match.start() - 48) : match.start()]
        if re.search(
            r"\b(?:outside|during|within|after|before|except(?:\s+during)?)\s*$",
            prefix,
            re.IGNORECASE,
        ):
            continue
        windows.append((_norm_time(match.group("start")), _norm_time(match.group("end"))))
    return windows


def _case_quiet_ends(text: str) -> list[str]:
    ends = [_norm_time(m.group("end")) for m in _QUIET_END_RE.finditer(text)]
    for _start, end in _case_quiet_windows(text):
        ends.append(end)
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for e in ends:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out


def _case_dst_claims(text: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for match in _HOUR_DAY_RE.finditer(text):
        hours_raw = match.group("hours") or match.group("hours2") or match.group("hours3")
        if not hours_raw:
            continue
        hours = int(hours_raw)
        window = text[max(0, match.start() - 120) : min(len(text), match.end() + 120)]
        spring = bool(_DST_SPRING_RE.search(window) or _MARCH_RE.search(window))
        fall = bool(_DST_FALL_RE.search(window) or _NOV_RE.search(window))
        transition: str | None = None
        if spring and not fall:
            transition = "spring_forward"
        elif fall and not spring:
            transition = "fall_back"
        claims.append({"hours": hours, "transition": transition, "span": match.group(0)})
    return claims


def _is_invented_example(text: str) -> bool:
    return bool(_INVENTED_EXAMPLE_RE.search(text or ""))


def _steps_text(case: dict[str, Any]) -> str:
    steps = case.get("steps") or []
    if isinstance(steps, list):
        return "\n".join(str(s) for s in steps)
    return str(steps)


def is_quiet_hours_configuration_test(case: dict[str, Any]) -> bool:
    """True when the case is *setting* quiet hours, not asserting the default window.

    FR-style config cases (define/set midnight-crossing windows) must not be
    rejected just because the values differ from a documented default.
    """
    title = str(case.get("title") or "")
    description = str(case.get("description") or "")
    expected = str(case.get("expected_result") or "")
    steps = _steps_text(case)
    actions = f"{title}\n{description}\n{steps}"

    if _QUIET_CONFIG_TITLE_RE.search(title):
        return True
    if _QUIET_CONFIG_ACTION_RE.search(actions) and (
        _QUIET_CONFIG_SAVE_RE.search(expected) or _QUIET_CONFIG_ACTION_RE.search(steps)
    ):
        return True
    return False


def _quiet_hours_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        f
        for f in facts
        if f.get("type") in {"quiet_hours_window", "quiet_hours_end"}
    ]


def _dst_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [f for f in facts if f.get("type") == "dst_day_length"]


def _allowed_quiet_ends(facts: list[dict[str, Any]]) -> set[str]:
    ends: set[str] = set()
    for f in _quiet_hours_facts(facts):
        end = f.get("end")
        if end:
            ends.add(str(end))
    return ends


def _allowed_quiet_windows(facts: list[dict[str, Any]]) -> set[tuple[str, str]]:
    windows: set[tuple[str, str]] = set()
    for f in facts:
        if f.get("type") == "quiet_hours_window" and f.get("start") and f.get("end"):
            windows.add((str(f["start"]), str(f["end"])))
    return windows


def _dst_hours_for(facts: list[dict[str, Any]], transition: str) -> set[int]:
    return {
        int(f["hours"])
        for f in _dst_facts(facts)
        if f.get("transition") == transition and f.get("hours") is not None
    }


def spec_fact_violations(
    case: dict[str, Any],
    facts: list[dict[str, Any]],
) -> list[str]:
    """Return hard violations (empty if only invented-example warnings).

    Quiet hours: reject when a case *asserts* a window that conflicts with
    extracted defaults. Skip when the case is configuring/setting quiet hours
    to a custom value (valid settings test).

    DST: reject only when the specification states a day length for that
    transition and the case contradicts it. Do not reject calendar DST
    knowledge merely because the SRS never mentions day lengths.
    """
    text = _case_text(case)
    if not text.strip() or not facts:
        return []

    invented = _is_invented_example(text)
    issues: list[str] = []
    skip_quiet_window_check = is_quiet_hours_configuration_test(case)

    allowed_ends = _allowed_quiet_ends(facts)
    allowed_windows = _allowed_quiet_windows(facts)

    if not skip_quiet_window_check and (allowed_ends or allowed_windows):
        for start, end in _case_quiet_windows(text):
            if allowed_windows and (start, end) not in allowed_windows:
                msg = (
                    f"Quiet hours window {start}-{end} is not in the specification "
                    f"(known: {', '.join(f'{a}-{b}' for a, b in sorted(allowed_windows))})."
                )
                if not invented:
                    issues.append(msg)
            elif allowed_ends and end not in allowed_ends:
                known = ", ".join(sorted(allowed_ends))
                msg = (
                    f"Quiet hours end {end} conflicts with specification "
                    f"(known end(s): {known})."
                )
                if not invented:
                    issues.append(msg)

        if not _case_quiet_windows(text):
            for end in _case_quiet_ends(text):
                if allowed_ends and end not in allowed_ends:
                    known = ", ".join(sorted(allowed_ends))
                    msg = (
                        f"Quiet hours end {end} conflicts with specification "
                        f"(known end(s): {known})."
                    )
                    if not invented:
                        issues.append(msg)

    for claim in _case_dst_claims(text):
        hours = int(claim["hours"])
        transition = claim.get("transition")
        if transition:
            known_hours = _dst_hours_for(facts, transition)
            label = (
                "spring-forward" if transition == "spring_forward" else "fall-back"
            )
            # Only conflict-check when the SRS actually states this transition.
            if known_hours and hours not in known_hours:
                known = ", ".join(str(h) for h in sorted(known_hours))
                msg = (
                    f"Asserts a {hours}-hour day for {label}, but the specification "
                    f"states {known}-hour day(s) for that transition."
                )
                if not invented:
                    issues.append(msg)
        else:
            all_hours = {
                int(f["hours"])
                for f in _dst_facts(facts)
                if f.get("hours") is not None
            }
            if all_hours and hours not in all_hours:
                known = ", ".join(str(h) for h in sorted(all_hours))
                msg = (
                    f"Asserts a {hours}-hour day, which is not among DST day lengths "
                    f"in the specification ({known})."
                )
                if not invented:
                    issues.append(msg)

    # Deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            unique.append(issue)
    return unique


def spec_fact_warnings(
    case: dict[str, Any],
    facts: list[dict[str, Any]],
) -> list[str]:
    """Soft warnings for invented-example mismatches (do not reject the case)."""
    text = _case_text(case)
    if not _is_invented_example(text):
        return []
    # Re-run checks with invented flag off by temporarily stripping markers
    # is awkward; instead mirror violation messages with a warning prefix.
    stripped = dict(case)
    # Force invented path: call violations on a copy without the invented markers
    # by replacing markers so violations would fire, then re-label.
    plain = _INVENTED_EXAMPLE_RE.sub(" ", text)
    probe = {
        "title": plain,
        "description": "",
        "preconditions": "",
        "steps": [],
        "expected_result": "",
    }
    raw = spec_fact_violations(probe, facts)
    return [f"Invented example (warning): {m}" for m in raw]
