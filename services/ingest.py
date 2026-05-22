"""High-level ingest: requirements file and CSV imports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from services.chunking import ParseQuality, assess_parse_quality, split_requirements
from services.document_parser import parse_uploaded_file
from services.embeddings import embed_texts, get_embeddings_model
from services.supabase_repo import SupabaseRepo, content_hash

ImportMode = Literal["flat", "grouped"]


@dataclass
class ParseResult:
    """Outcome of CSV analysis (no DB writes, no embeddings)."""

    entities: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    preview: list[dict[str, Any]] = field(default_factory=list)


BUG_GROUP_ALIASES = ("bug_id", "bugid", "bug_number", "bug_no", "id", "issue_id", "key", "defect_id")
BUG_NUMBER_ALIASES = BUG_GROUP_ALIASES
TC_GROUP_ALIASES = ("test_case_id", "testcaseid", "tc_id", "case_id", "testcase_id", "id")

# (score weight, column aliases) — used to guess bug vs test-case CSV from headers.
_BUG_KIND_MARKERS = (
    (3, ("bug_id", "bugid", "issue_id", "defect_id")),
    (2, ("steps_to_reproduce", "reproduction_steps")),
    (2, ("actual_result", "actual_behavior")),
    (1, ("status", "resolution")),
)
_TC_KIND_MARKERS = (
    (3, ("test_case_id", "testcaseid", "tc_id", "case_id")),
    (2, ("test_type",)),
    (2, ("steps", "test_steps")),
    (2, ("test_scenario", "test_case")),
    (1, ("preconditions",)),
)


def ingest_requirement_document(
    repo: SupabaseRepo,
    project_id: str,
    filename: str,
    file_bytes: bytes,
    module: str | None = None,
) -> tuple[list[dict[str, Any]], ParseQuality]:
    """Parse, split, embed, replace requirements; return rows and parse quality."""
    text = parse_uploaded_file(filename, file_bytes)
    requirements = split_requirements(text)
    if not requirements:
        raise ValueError("No text extracted from document")
    parse_quality = assess_parse_quality(requirements)

    repo.delete_requirements_for_document(project_id, filename)
    emb = get_embeddings_model()
    vectors = embed_texts(emb, [r.text for r in requirements])

    rows: list[dict[str, Any]] = []
    for i, (req, vec) in enumerate(zip(requirements, vectors)):
        rows.append(
            {
                "project_id": project_id,
                "document_name": filename,
                "chunk_index": i,
                "chunk_text": req.text,
                "requirement_id": req.requirement_id,
                "is_synthetic_requirement": req.is_synthetic,
                "module": module,
                "content_hash": content_hash(req.text),
                "embedding": vec,
            }
        )
    inserted = repo.insert_requirement_chunks(project_id, filename, rows)
    return inserted, parse_quality


def _normalize_header(name: str) -> str:
    s = str(name).strip().lstrip("\ufeff").strip()
    return s.lower().replace(" ", "_").replace("-", "_")


def _column_lookup(df: pd.DataFrame) -> dict[str, str]:
    """normalized_header -> original column name."""
    return {_normalize_header(c): c for c in df.columns}


def _pick_col(lookup: dict[str, str], *aliases: str) -> str | None:
    for a in aliases:
        key = _normalize_header(a)
        if key in lookup:
            return lookup[key]
    return None


def _find_col_by_substrings(
    lookup: dict[str, str],
    must_contain: tuple[str, ...],
    must_not_contain: tuple[str, ...] = (),
) -> str | None:
    """Fallback column match when exact aliases fail (e.g. 'Expected Results' -> expected_results)."""
    for norm, orig in lookup.items():
        if any(bad in norm for bad in must_not_contain):
            continue
        if all(token in norm for token in must_contain):
            return orig
    return None


def _resolve_bug_content_columns(lookup: dict[str, str]) -> dict[str, str | None]:
    """Resolve steps / expected / actual columns with aliases then fuzzy header match."""
    steps = _pick_col(
        lookup,
        "steps_to_reproduce",
        "step_to_reproduce",
        "reproduction_steps",
        "repro_steps",
        "steps",
        "step",
    )
    if not steps:
        steps = _find_col_by_substrings(
            lookup,
            ("reproduc",),
            ("expected", "actual", "reported", "priority", "severity", "status"),
        )
    if not steps:
        steps = _find_col_by_substrings(
            lookup,
            ("step",),
            ("expected", "actual", "reported", "priority", "severity", "status"),
        )

    expected = _pick_col(
        lookup,
        "expected_result",
        "expected_results",
        "expected",
        "expected_behavior",
    )
    if not expected:
        expected = _find_col_by_substrings(
            lookup, ("expected",), ("unexpected", "reported")
        )

    actual = _pick_col(
        lookup,
        "actual_result",
        "actual_results",
        "actual",
        "actual_behavior",
    )
    if not actual:
        actual = _find_col_by_substrings(
            lookup, ("actual",), ("reported",)
        )

    return {"steps": steps, "expected": expected, "actual": actual}


def detect_csv_kind(df: pd.DataFrame) -> Literal["bugs", "test_cases", "unknown"]:
    """
    Guess whether a CSV is a bug export or test-case export from column headers.
    Used to warn when the file is on the wrong Import tab.
    """
    lookup = _column_lookup(df)
    bug_score = 0
    tc_score = 0

    for weight, aliases in _BUG_KIND_MARKERS:
        if _pick_col(lookup, *aliases):
            bug_score += weight

    for weight, aliases in _TC_KIND_MARKERS:
        if _pick_col(lookup, *aliases):
            tc_score += weight

    # "step" alone is ambiguous; "steps_to_reproduce" is bug-specific.
    if _pick_col(lookup, "step", "step_description", "action") and not _pick_col(
        lookup, "steps_to_reproduce", "reproduction_steps"
    ):
        tc_score += 1

    if _pick_col(lookup, "expected_result", "expected") and _pick_col(
        lookup, "steps_to_reproduce", "reproduction_steps"
    ):
        bug_score += 1

    if bug_score >= 3 and bug_score > tc_score:
        return "bugs"
    if tc_score >= 3 and tc_score > bug_score:
        return "test_cases"
    return "unknown"


def _wrong_tab_error(found_columns: list[str], *, expected: Literal["bugs", "test_cases"]) -> str:
    if expected == "bugs":
        return (
            "This CSV looks like a **bug report** export "
            "(e.g. Bug_ID, Steps_to_Reproduce, Actual_Result, Status). "
            "Open the **Bug reports** tab on the Import page and analyze the file there.\n\n"
            f"Columns found: {found_columns}"
        )
    return (
        "This CSV looks like a **test case** export "
        "(e.g. test scenario, test steps, expected result). "
        "Open the **Test cases** tab on the Import page and analyze the file there.\n\n"
        f"Columns found: {found_columns}"
    )


def _cell_str(row: pd.Series, col: str | None) -> str:
    if col is None:
        return ""
    val = row[col]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _first_non_empty(values: list[str]) -> str:
    for v in values:
        if v:
            return v
    return ""


def _unique_non_empty(values: list[str]) -> set[str]:
    return {v for v in values if v}


def _parse_steps_cell(val: Any) -> list[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return []
    if s.startswith("["):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return [str(x) for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    if ";" in s:
        parts = [p.strip() for p in s.split(";") if p.strip()]
        return parts if parts else [s]
    if "\n" in s:
        parts = [p.strip() for p in s.split("\n") if p.strip()]
        return parts if parts else [s]
    return [s]


def _detect_group_column(
    lookup: dict[str, str],
    aliases: tuple[str, ...],
    override: str | None,
) -> str | None:
    if override and override != "(auto)":
        key = _normalize_header(override)
        return lookup.get(key)
    return _pick_col(lookup, *aliases)


def _should_use_grouped_mode(df: pd.DataFrame, group_col: str | None) -> bool:
    if not group_col or df.empty:
        return False
    ids = [_cell_str(row, group_col) for _, row in df.iterrows()]
    non_empty = [g for g in ids if g]
    if len(non_empty) < 2:
        return False
    return len(set(non_empty)) < len(non_empty)


def _iter_groups(
    df: pd.DataFrame,
    group_col: str,
) -> tuple[list[tuple[str, list[pd.Series]]], int]:
    """Preserve first-seen group order; return (groups, skipped_orphan_rows)."""
    buckets: dict[str, list[pd.Series]] = {}
    order: list[str] = []
    skipped = 0

    for _, row in df.iterrows():
        gid = _cell_str(row, group_col)
        if not gid:
            skipped += 1
            continue
        if gid not in buckets:
            buckets[gid] = []
            order.append(gid)
        buckets[gid].append(row)

    return [(gid, buckets[gid]) for gid in order], skipped


def _is_steps_placeholder(text: str) -> bool:
    t = text.strip().lower().rstrip(":").strip()
    return t in ("steps to reproduce", "reproduction steps", "steps", "")


def _format_bug_steps_section(rows: list[pd.Series], lookup: dict[str, str]) -> str:
    """Steps / expected / actual from dedicated columns (always merged into description)."""
    cols = _resolve_bug_content_columns(lookup)
    steps_c, exp_c, act_c = cols["steps"], cols["expected"], cols["actual"]
    if not any((steps_c, exp_c, act_c)):
        return ""

    entries: list[str] = []
    step_num = 0
    for row in rows:
        bits: list[str] = []
        if steps_c:
            steps = _cell_str(row, steps_c)
            if steps:
                bits.append(steps)
        if exp_c:
            exp = _cell_str(row, exp_c)
            if exp:
                bits.append(f"Expected: {exp}")
        if act_c:
            act = _cell_str(row, act_c)
            if act:
                bits.append(f"Actual: {act}")
        if not bits:
            continue
        step_num += 1
        block = "\n".join(bits)
        entries.append(f"{step_num}. {block}" if len(rows) > 1 else block)

    if not entries:
        return ""
    return "Steps to reproduce:\n" + "\n".join(entries)


def _bug_extra_metadata(
    row: pd.Series,
    lookup: dict[str, str],
    *,
    include_environment: bool = True,
) -> str:
    parts: list[str] = []
    cat_c = _pick_col(lookup, "category")
    cat = _cell_str(row, cat_c)
    if cat:
        parts.append(f"Category: {cat}")
    if include_environment:
        env_c = _pick_col(lookup, "environment", "env")
        env = _cell_str(row, env_c)
        if env:
            parts.append(f"Environment: {env}")
    return "\n\n".join(parts)


def _build_bug_description(
    rows: list[pd.Series],
    lookup: dict[str, str],
    desc_c: str | None,
) -> str:
    """
    Build description from optional description column plus steps/expected/actual columns.
    Step columns are always included when present (even if description column exists).
    """
    parts: list[str] = []

    if desc_c:
        base = _first_non_empty([_cell_str(r, desc_c) for r in rows])
        if base and not _is_steps_placeholder(base):
            parts.append(base)

    steps_block = _format_bug_steps_section(rows, lookup)
    if steps_block:
        parts.append(steps_block)

    if rows:
        meta = _bug_extra_metadata(
            rows[0], lookup, include_environment=bool(steps_block)
        )
        if meta:
            parts.append(meta)

    return "\n\n".join(parts) if parts else "(no description provided)"


def _bug_number_for_rows(
    rows: list[pd.Series],
    bug_num_c: str | None,
    group_id: str | None = None,
) -> str | None:
    if bug_num_c:
        num = _first_non_empty([_cell_str(r, bug_num_c) for r in rows])
        if num:
            return num
    return group_id


def _bug_title_for_rows(
    rows: list[pd.Series],
    group_id: str,
    title_c: str | None,
    bug_num_c: str | None,
) -> str:
    title = _first_non_empty([_cell_str(r, title_c) if title_c else "" for r in rows])
    if title:
        return title
    bid = _first_non_empty([_cell_str(r, bug_num_c) if bug_num_c else "" for r in rows])
    if bid:
        return f"Bug {bid}"
    return f"Bug {group_id}"


def _parse_bugs_flat(df: pd.DataFrame, lookup: dict[str, str]) -> ParseResult:
    title_c = _pick_col(lookup, "title", "subject", "bug_title", "summary", "name")
    bug_num_c = _pick_col(lookup, *BUG_NUMBER_ALIASES)
    desc_c = _pick_col(lookup, "description", "details", "bug_description")
    sev_c = _pick_col(lookup, "severity", "priority")
    comp_c = _pick_col(lookup, "component", "category", "environment")
    reso_c = _pick_col(lookup, "resolution", "status")

    entities: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    skipped = 0

    for _, row in df.iterrows():
        rows = [row]
        title = _cell_str(row, title_c) if title_c else ""
        bug_number = _bug_number_for_rows(rows, bug_num_c)
        if not title and bug_number:
            title = f"Bug {bug_number}"
        if not title:
            skipped += 1
            continue

        desc = _build_bug_description(rows, lookup, desc_c)
        sev = _cell_str(row, sev_c) if sev_c else ""
        comp = _cell_str(row, comp_c) if comp_c else ""
        reso = _cell_str(row, reso_c) if reso_c else ""

        entities.append(
            {
                "title": title,
                "bug_number": bug_number,
                "description": desc,
                "severity": sev or None,
                "component": comp or None,
                "resolution": reso or None,
            }
        )
        preview.append(
            {
                "bug_number": bug_number or "",
                "title": title,
                "description": desc[:200] + ("…" if len(desc) > 200 else ""),
                "severity": sev or "",
                "component": comp or "",
                "csv_rows": 1,
            }
        )

    return ParseResult(
        entities=entities,
        stats={
            "input_rows": len(df),
            "output_entities": len(entities),
            "skipped_rows": skipped,
            "mode": "flat",
            "group_column": None,
        },
        preview=preview,
    )


def _parse_bugs_grouped(
    df: pd.DataFrame,
    lookup: dict[str, str],
    group_col: str,
) -> ParseResult:
    title_c = _pick_col(lookup, "title", "subject", "bug_title", "summary", "name")
    bug_num_c = _pick_col(lookup, *BUG_NUMBER_ALIASES)
    desc_c = _pick_col(lookup, "description", "details", "bug_description")
    sev_c = _pick_col(lookup, "severity", "priority")
    comp_c = _pick_col(lookup, "component", "category", "environment")
    reso_c = _pick_col(lookup, "resolution", "status")

    groups, skipped = _iter_groups(df, group_col)
    entities: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    warnings: list[str] = []

    for group_id, rows in groups:
        title = _bug_title_for_rows(rows, group_id, title_c, bug_num_c)
        bug_number = _bug_number_for_rows(rows, bug_num_c, group_id)
        desc = _build_bug_description(rows, lookup, desc_c)

        sevs = _unique_non_empty([_cell_str(r, sev_c) if sev_c else "" for r in rows])
        comps = _unique_non_empty([_cell_str(r, comp_c) if comp_c else "" for r in rows])
        resos = _unique_non_empty([_cell_str(r, reso_c) if reso_c else "" for r in rows])

        if len(sevs) > 1:
            warnings.append(f"Bug {group_id}: conflicting severity values: {sevs}")
        if len(comps) > 1:
            warnings.append(f"Bug {group_id}: conflicting component values: {comps}")
        if len(resos) > 1:
            warnings.append(f"Bug {group_id}: conflicting resolution values: {resos}")

        titles_in_group = _unique_non_empty(
            [_cell_str(r, title_c) if title_c else "" for r in rows]
        )
        if len(titles_in_group) > 1:
            warnings.append(f"Bug {group_id}: multiple titles in group; using first non-empty.")

        sev = _first_non_empty([_cell_str(r, sev_c) if sev_c else "" for r in rows])
        comp = _first_non_empty([_cell_str(r, comp_c) if comp_c else "" for r in rows])
        reso = _first_non_empty([_cell_str(r, reso_c) if reso_c else "" for r in rows])

        entities.append(
            {
                "title": title,
                "bug_number": bug_number,
                "description": desc,
                "severity": sev or None,
                "component": comp or None,
                "resolution": reso or None,
            }
        )
        preview.append(
            {
                "bug_number": bug_number or "",
                "title": title,
                "description": desc[:200] + ("…" if len(desc) > 200 else ""),
                "severity": sev or "",
                "component": comp or "",
                "csv_rows": len(rows),
            }
        )

    return ParseResult(
        entities=entities,
        warnings=warnings,
        stats={
            "input_rows": len(df),
            "output_entities": len(entities),
            "skipped_rows": skipped,
            "mode": "grouped",
            "group_column": group_col,
        },
        preview=preview,
    )


def parse_bugs_csv(
    df: pd.DataFrame,
    group_column: str | None = None,
    force_grouped: bool = False,
) -> ParseResult:
    """
    Analyze bug CSV without DB writes.

    Flat: one row per bug. Grouped: rows sharing Bug_ID merge into one bug.
    """
    if df.empty:
        return ParseResult(
            entities=[],
            stats={"input_rows": 0, "output_entities": 0, "skipped_rows": 0, "mode": "flat"},
        )

    lookup = _column_lookup(df)
    if detect_csv_kind(df) == "test_cases":
        raise ValueError(_wrong_tab_error(list(df.columns), expected="test_cases"))
    title_c = _pick_col(lookup, "title", "subject", "bug_title", "summary", "name")
    bug_num_c = _pick_col(lookup, *BUG_NUMBER_ALIASES)
    if not title_c and not bug_num_c:
        raise ValueError(
            "Bug CSV must include a title column (Title, subject, summary, …) "
            "or a bug number column (Bug_ID, bug_number, issue_id, key). "
            f"Found columns: {list(df.columns)}"
        )

    gcol = _detect_group_column(lookup, BUG_GROUP_ALIASES, group_column)
    use_grouped = force_grouped or _should_use_grouped_mode(df, gcol)

    if use_grouped and gcol:
        result = _parse_bugs_grouped(df, lookup, gcol)
    else:
        result = _parse_bugs_flat(df, lookup)

    if not result.entities and len(df) > 0:
        raise ValueError(
            f"No bugs parsed from {len(df)} row(s). "
            "Check titles, Bug_ID values, or grouped row structure."
        )

    return result


def commit_bugs_csv(
    repo: SupabaseRepo,
    project_id: str,
    entities: list[dict[str, Any]],
) -> int:
    if not entities:
        return 0
    records = [{**e, "project_id": project_id} for e in entities]
    texts = [f"{r['title']}\n{r['description']}" for r in records]
    emb = get_embeddings_model()
    vectors = embed_texts(emb, texts)
    for r, vec in zip(records, vectors):
        r["embedding"] = vec
    repo.insert_bug_reports(records)
    return len(records)


def import_bugs_csv(
    repo: SupabaseRepo,
    project_id: str,
    df: pd.DataFrame,
    group_column: str | None = None,
    force_grouped: bool = False,
) -> int:
    """Parse, embed, and insert bugs (legacy one-step import)."""
    parsed = parse_bugs_csv(df, group_column=group_column, force_grouped=force_grouped)
    return commit_bugs_csv(repo, project_id, parsed.entities)


def _resolve_test_case_columns(lookup: dict[str, str]) -> dict[str, str | None]:
    """Map common test-case export headers to logical fields."""
    return {
        "title": _pick_col(
            lookup,
            "title",
            "test_scenario",
            "test_case",
            "testcase",
            "scenario",
            "name",
            "summary",
        ),
        "steps": _pick_col(
            lookup,
            "steps",
            "test_steps",
            "testcase_steps",
            "test_step",
            "step",
            "step_description",
            "action",
        ),
        "expected_result": _pick_col(
            lookup,
            "expected_result",
            "expected_results",
            "expected",
            "expected_outcome",
            "expected_behavior",
        ),
        "test_type": _pick_col(lookup, "test_type", "type", "tc_type"),
        "priority": _pick_col(lookup, "priority"),
        "testcase_id_csv": _pick_col(
            lookup,
            "testcase_id",
            "test_case_id",
            "testcase_number",
            "case_number",
            "tc_number",
        ),
        "description": _pick_col(lookup, "description"),
        "preconditions": _pick_col(lookup, "preconditions"),
        "module": _pick_col(lookup, "module"),
    }


def _parse_test_cases_flat(df: pd.DataFrame) -> ParseResult:
    lookup = _column_lookup(df)
    cols_map = _resolve_test_case_columns(lookup)

    missing_hints: list[str] = []
    if not cols_map["title"]:
        missing_hints.append(
            "a title or scenario column (e.g. Title, Test scenario, Test case)"
        )
    if not cols_map["steps"]:
        missing_hints.append("a steps column (e.g. Steps, Test steps)")
    if not cols_map["expected_result"]:
        missing_hints.append("expected result (e.g. Expected result)")

    if missing_hints:
        if detect_csv_kind(df) == "bugs":
            raise ValueError(_wrong_tab_error(list(df.columns), expected="bugs"))
        raise ValueError(
            "Test case CSV is missing required data: "
            + "; ".join(missing_hints)
            + ". Optional columns: **test type** (defaults to positive), **priority** "
            "(defaults to medium). "
            f"Found: {list(df.columns)}"
        )

    title_c = cols_map["title"]
    steps_c = cols_map["steps"]
    exp_c = cols_map["expected_result"]
    ttype_c = cols_map["test_type"]
    pri_c = cols_map["priority"]
    desc_c = cols_map["description"]
    pre_c = cols_map["preconditions"]
    mod_c = cols_map["module"]
    tc_id_c = cols_map["testcase_id_csv"]

    entities: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    skipped = 0

    assert title_c and steps_c and exp_c  # validated above

    for _, row in df.iterrows():
        title = _cell_str(row, title_c)
        if not title:
            skipped += 1
            continue
        steps = _parse_steps_cell(row[steps_c])
        if not steps:
            steps = ["Step 1: (not specified)"]
        exp = _cell_str(row, exp_c)
        ttype = _cell_str(row, ttype_c).lower() if ttype_c else ""
        if not ttype or ttype == "nan":
            ttype = "positive"
        pri = _cell_str(row, pri_c).lower() if pri_c else ""
        if not pri or pri == "nan":
            pri = "medium"
        desc = _cell_str(row, desc_c) if desc_c else ""
        pre = _cell_str(row, pre_c) if pre_c else ""
        mod = _cell_str(row, mod_c) if mod_c else ""
        tc_ext = _testcase_external_id_for_rows([row], tc_id_c)

        entities.append(
            _test_case_entity(tc_ext, title, desc, pre, steps, exp, ttype, pri, mod)
        )
        preview.append(
            _test_case_preview_row(tc_ext, title, steps, exp, ttype, pri, 1)
        )

    return ParseResult(
        entities=entities,
        stats={
            "input_rows": len(df),
            "output_entities": len(entities),
            "skipped_rows": skipped,
            "mode": "flat",
            "group_column": None,
        },
        preview=preview,
    )


def _testcase_external_id_for_rows(
    rows: list[pd.Series],
    tc_id_col: str | None,
    group_id: str | None = None,
) -> str | None:
    if tc_id_col:
        v = _first_non_empty([_cell_str(r, tc_id_col) for r in rows])
        if v:
            return v
    return group_id if group_id else None


def _test_case_entity(
    testcase_id: str | None,
    title: str,
    desc: str,
    pre: str,
    steps: list[str],
    exp: str,
    ttype: str,
    pri: str,
    mod: str,
) -> dict[str, Any]:
    return {
        "testcase_id": testcase_id,
        "title": title,
        "description": desc or None,
        "preconditions": pre or None,
        "steps": steps,
        "expected_result": exp,
        "test_type": ttype,
        "priority": pri,
        "module": mod or None,
        "source": "imported",
        "is_duplicate": False,
        "source_requirement_chunk_ids": [],
        "supporting_bug_ids": [],
        "supporting_test_case_ids": [],
    }


def _test_case_preview_row(
    testcase_id: str | None,
    title: str,
    steps: list[str],
    exp: str,
    ttype: str,
    pri: str,
    csv_rows: int,
    group_id: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "testcase_id": testcase_id or "",
        "title": title,
        "steps_count": len(steps),
        "expected_result": (exp[:120] + "…") if len(exp) > 120 else exp,
        "test_type": ttype,
        "priority": pri,
        "csv_rows": csv_rows,
    }
    if group_id:
        row["group_id"] = group_id
    return row


def _parse_test_cases_grouped(
    df: pd.DataFrame,
    lookup: dict[str, str],
    group_col: str,
) -> ParseResult:
    cols_map = _resolve_test_case_columns(lookup)
    title_c = cols_map["title"]
    steps_c = cols_map["steps"]
    exp_c = cols_map["expected_result"]
    ttype_c = cols_map["test_type"]
    pri_c = cols_map["priority"]
    desc_c = cols_map["description"]
    pre_c = cols_map["preconditions"]
    mod_c = cols_map["module"]
    tc_id_c = cols_map["testcase_id_csv"]

    if not steps_c:
        raise ValueError(
            "Grouped test case CSV needs a steps column "
            "(e.g. Steps, Test steps, step). "
            f"Found columns: {list(df.columns)}"
        )

    groups, skipped = _iter_groups(df, group_col)
    entities: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    warnings: list[str] = []

    for group_id, rows in groups:
        title = _first_non_empty([_cell_str(r, title_c) if title_c else "" for r in rows])
        if not title:
            title = f"Test case {group_id}"

        all_steps: list[str] = []
        for row in rows:
            all_steps.extend(_parse_steps_cell(row[steps_c]))
        if not all_steps:
            all_steps = ["Step 1: (not specified)"]

        exp = _first_non_empty([_cell_str(r, exp_c) if exp_c else "" for r in rows])
        ttype = _first_non_empty(
            [_cell_str(r, ttype_c).lower() if ttype_c else "" for r in rows]
        ) or "positive"
        pri = _first_non_empty(
            [_cell_str(r, pri_c).lower() if pri_c else "" for r in rows]
        ) or "medium"
        desc = _first_non_empty([_cell_str(r, desc_c) if desc_c else "" for r in rows])
        pre = _first_non_empty([_cell_str(r, pre_c) if pre_c else "" for r in rows])
        mod = _first_non_empty([_cell_str(r, mod_c) if mod_c else "" for r in rows])

        titles_in_group = _unique_non_empty(
            [_cell_str(r, title_c) if title_c else "" for r in rows]
        )
        if len(titles_in_group) > 1:
            warnings.append(
                f"Test case {group_id}: multiple titles in group; using first non-empty."
            )
        tt_set = _unique_non_empty(
            [_cell_str(r, ttype_c).lower() if ttype_c else "" for r in rows]
        )
        pr_set = _unique_non_empty(
            [_cell_str(r, pri_c).lower() if pri_c else "" for r in rows]
        )
        if len(tt_set) > 1:
            warnings.append(f"Test case {group_id}: conflicting test_type values: {tt_set}")
        if pri_c and len(pr_set) > 1:
            warnings.append(f"Test case {group_id}: conflicting priority values: {pr_set}")

        tc_ext = _testcase_external_id_for_rows(rows, tc_id_c, group_id)
        entities.append(
            _test_case_entity(tc_ext, title, desc, pre, all_steps, exp, ttype, pri, mod)
        )
        preview.append(
            _test_case_preview_row(
                tc_ext, title, all_steps, exp, ttype, pri, len(rows), group_id
            )
        )

    return ParseResult(
        entities=entities,
        warnings=warnings,
        stats={
            "input_rows": len(df),
            "output_entities": len(entities),
            "skipped_rows": skipped,
            "mode": "grouped",
            "group_column": group_col,
        },
        preview=preview,
    )


def parse_test_cases_csv(
    df: pd.DataFrame,
    group_column: str | None = None,
    force_grouped: bool = False,
) -> ParseResult:
    """Analyze test case CSV without DB writes."""
    if df.empty:
        return ParseResult(
            entities=[],
            stats={"input_rows": 0, "output_entities": 0, "skipped_rows": 0, "mode": "flat"},
        )

    lookup = _column_lookup(df)
    if detect_csv_kind(df) == "bugs":
        raise ValueError(_wrong_tab_error(list(df.columns), expected="bugs"))

    gcol = _detect_group_column(lookup, TC_GROUP_ALIASES, group_column)
    use_grouped = force_grouped or _should_use_grouped_mode(df, gcol)

    if use_grouped and gcol:
        result = _parse_test_cases_grouped(df, lookup, gcol)
    else:
        result = _parse_test_cases_flat(df)

    if not result.entities and len(df) > 0:
        raise ValueError(
            f"No test cases parsed from {len(df)} row(s). "
            "Check required columns or grouped structure."
        )

    total_steps = sum(len(e.get("steps") or []) for e in result.entities)
    result.stats["total_steps"] = total_steps
    return result


def commit_test_cases_csv(
    repo: SupabaseRepo,
    project_id: str,
    entities: list[dict[str, Any]],
) -> int:
    if not entities:
        return 0
    records = [{**e, "project_id": project_id} for e in entities]
    texts: list[str] = []
    for r in records:
        steps = r.get("steps") or []
        steps_blob = "\n".join(str(s) for s in steps)
        texts.append(
            f"{r['title']}\n{r.get('description') or ''}\n{steps_blob}\n{r.get('expected_result', '')}"
        )
    emb = get_embeddings_model()
    vectors = embed_texts(emb, texts)
    for r, vec in zip(records, vectors):
        r["embedding"] = vec
    repo.insert_test_cases(records)
    return len(records)


def import_test_cases_csv(
    repo: SupabaseRepo,
    project_id: str,
    df: pd.DataFrame,
    group_column: str | None = None,
    force_grouped: bool = False,
) -> int:
    """Parse, embed, and insert test cases (legacy one-step import)."""
    parsed = parse_test_cases_csv(df, group_column=group_column, force_grouped=force_grouped)
    return commit_test_cases_csv(repo, project_id, parsed.entities)
