"""CSV import for historical bugs and test cases."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from services.bootstrap import get_repo
from services.openai_errors import (
    friendly_openai_error,
    remember_openai_probe_failure,
    resolve_openai_banner_message,
)
from services.ingest import (
    ParseResult,
    commit_bugs_csv,
    commit_test_cases_csv,
    detect_csv_kind,
    parse_bugs_csv,
    parse_test_cases_csv,
)
from services.supabase_auth import require_auth
from theme import apply_theme, render_back_to_home_link

apply_theme()
require_auth()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "templates"


@dataclass(frozen=True)
class _CsvTemplate:
    filename: str
    heading: str
    description: str
    button_label: str


_BUG_TEMPLATES = (
    _CsvTemplate(
        filename="bugs_flat_template.csv",
        heading="One row per bug",
        description=(
            "Each bug appears on a single row with title, steps, severity, and status in that row. "
            "Use this layout when your spreadsheet or export already has one line per issue."
        ),
        button_label="Download: one row per bug",
    ),
    _CsvTemplate(
        filename="bugs_grouped_template.csv",
        heading="Multiple rows per bug",
        description=(
            "The same **Bug_ID** is repeated on several rows; put one reproduction step on each row. "
            "Use this when steps are split across lines (for example, 200 rows importing as 50 bugs)."
        ),
        button_label="Download: multiple rows per bug",
    ),
)

_TEST_CASE_TEMPLATES = (
    _CsvTemplate(
        filename="test_cases_flat_template.csv",
        heading="One row per test case",
        description=(
            "Each test case is a single row. Common headers like **Test scenario**, **Test steps**, "
            "and **Expected result** are recognized automatically. Put multiple steps in one cell "
            "separated by semicolons or new lines. **Priority** is optional (defaults to medium)."
        ),
        button_label="Download: one row per test case",
    ),
    _CsvTemplate(
        filename="test_cases_grouped_template.csv",
        heading="Multiple rows per test case",
        description=(
            "The same **TestCaseID** is repeated on several rows with one step per row. "
            "Metadata such as title can sit on the first row only. Priority is optional."
        ),
        button_label="Download: multiple rows per test case",
    ),
)


def _file_fingerprint(name: str, data: bytes) -> str:
    return hashlib.sha256(name.encode() + data).hexdigest()[:16]


def _read_uploaded_csv(uploaded_file) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(uploaded_file.getvalue()), encoding="utf-8-sig")


def _render_stats(parsed: ParseResult, entity_label: str) -> None:
    s = parsed.stats
    mode = s.get("mode", "flat")
    inp = s.get("input_rows", 0)
    out = s.get("output_entities", 0)
    skipped = s.get("skipped_rows", 0)

    if mode == "grouped" and inp > out:
        st.info(
            f"Ready to import **{out} {entity_label}** — merged **{inp} CSV rows** "
            f"that share the same ID (e.g. Bug_ID or TestCaseID)."
        )
    else:
        st.info(
            f"Ready to import **{out} {entity_label}** "
            f"({'one per CSV row' if inp == out else f'from {inp} CSV rows'})."
        )

    if skipped:
        st.warning(f"Skipped **{skipped}** row(s) with no group id / title.")

    if entity_label == "test cases" and "total_steps" in s:
        st.caption(f"Total steps across all test cases: **{s['total_steps']}**.")

    if parsed.warnings:
        with st.expander(f"Warnings ({len(parsed.warnings)})", expanded=False):
            for w in parsed.warnings:
                st.markdown(f"- {w}")


def _render_preview(parsed: ParseResult) -> None:
    if parsed.preview:
        st.dataframe(pd.DataFrame(parsed.preview), use_container_width=True, hide_index=True)


def _render_template_section(templates: tuple[_CsvTemplate, ...], key_prefix: str) -> None:
    if not TEMPLATES_DIR.is_dir():
        return
    available = [t for t in templates if (TEMPLATES_DIR / t.filename).is_file()]
    if not available:
        return

    with st.expander("Optional: example CSV templates", expanded=False):
        st.markdown(
            "Only needed if you are creating a file from scratch. "
            "If you already have an export from Jira, TestRail, or Excel, upload it directly above."
        )
        for i, tpl in enumerate(available):
            path = TEMPLATES_DIR / tpl.filename
            st.markdown(f"**{tpl.heading}**")
            st.markdown(tpl.description)
            _, btn_col, _ = st.columns([1, 2, 2])
            with btn_col:
                st.download_button(
                    label=tpl.button_label,
                    data=path.read_bytes(),
                    file_name=tpl.filename,
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                    key=f"dl_tpl_{key_prefix}_{tpl.filename}",
                )
            if i < len(available) - 1:
                st.divider()


def _import_tab(
    *,
    tab_key: str,
    entity_label: str,
    uploader_label: str,
    parse_fn,
    commit_fn,
    repo,
    project_id: str,
) -> None:
    parse_key = f"{tab_key}_parse"
    fp_key = f"{tab_key}_fingerprint"

    uploaded = st.file_uploader(uploader_label, type=["csv"], key=f"{tab_key}_csv")
    if uploaded is None:
        st.session_state.pop(parse_key, None)
        st.session_state.pop(fp_key, None)
        return

    fp = _file_fingerprint(uploaded.name, uploaded.getvalue())
    if st.session_state.get(fp_key) != fp:
        st.session_state.pop(parse_key, None)
        st.session_state[fp_key] = fp

    df = _read_uploaded_csv(uploaded)
    kind = detect_csv_kind(df)
    if tab_key == "bugs" and kind == "test_cases":
        st.warning(
            "This file looks like a **test case** CSV. "
            "Use the **Test cases** tab unless you meant to import bugs."
        )
    elif tab_key == "tcs" and kind == "bugs":
        st.error(
            "This file looks like a **bug report** CSV (Bug_ID, Steps_to_Reproduce, …). "
            "Switch to the **Bug reports** tab to import it."
        )

    col_a, col_b = st.columns(2)
    with col_a:
        analyze = st.button("🔍 Analyze CSV", key=f"{tab_key}_analyze", type="primary")
    with col_b:
        clear = st.button("🧹 Clear analysis", key=f"{tab_key}_clear")

    if clear:
        st.session_state.pop(parse_key, None)
        st.rerun()

    if analyze:
        try:
            parsed = parse_fn(df)
            st.session_state[parse_key] = parsed
        except ValueError as e:
            st.error(str(e))
            st.session_state.pop(parse_key, None)

    parsed: ParseResult | None = st.session_state.get(parse_key)
    if not parsed:
        st.caption("Upload a CSV and click **Analyze CSV** to preview before importing.")
        return

    _render_stats(parsed, entity_label)
    _render_preview(parsed)

    if st.button(f"✅ Confirm import {len(parsed.entities)} {entity_label}", key=f"{tab_key}_commit"):
        if banner_msg := resolve_openai_banner_message():
            st.error(banner_msg)
            return
        try:
            with st.spinner("Embedding and inserting…"):
                n = commit_fn(repo, project_id, parsed.entities)
        except Exception as exc:
            msg = friendly_openai_error(exc)
            if msg:
                remember_openai_probe_failure(exc)
                st.error(msg)
                return
            raise
        st.success(f"Imported {n} {entity_label}.")
        st.session_state.pop(parse_key, None)
        st.session_state.pop(fp_key, None)


render_back_to_home_link()
st.title("📥 Import data")
st.caption(
    "Have old bugs or tests? Import them optionally — they're used as background "
    "context when you generate."
)

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

pid = st.session_state.get("project_id")
if not pid:
    st.warning("Select a project from the home page first.")
    st.stop()

st.markdown(
    """
Import historical **bugs** and **test cases** from CSV.

1. Choose the correct tab (**Bug reports** or **Test cases**).
2. Upload your file and click **Analyze CSV** to preview what will be imported.
3. Click **Confirm import** when the preview looks right.

If your export has several rows per bug or test case (same **Bug_ID** or **TestCaseID**),
those rows are merged automatically. Example CSV layouts are available in each tab below.
"""
)

tab1, tab2 = st.tabs(["Bug reports", "Test cases"])

with tab1:
    st.markdown(
        """
Typical columns: **Title**, **Bug_ID**, **Steps_to_Reproduce**, **Severity**, **Status**.
Multiple rows with the same Bug_ID are combined into one bug.
        """
    )
    _render_template_section(_BUG_TEMPLATES, "bugs")
    _import_tab(
        tab_key="bugs",
        entity_label="bugs",
        uploader_label="Bugs CSV",
        parse_fn=parse_bugs_csv,
        commit_fn=commit_bugs_csv,
        repo=repo,
        project_id=pid,
    )

with tab2:
    st.markdown(
        """
Typical columns: **Test scenario** (or title), **Test steps**, **Expected result**, **Test type**.
Optional: **Test case ID** / **TestCase_ID** / **testcase_number** (stored in the library for search). That same ID column can group multiple step rows into one case. **Priority** defaults to **medium** if omitted.
        """
    )
    _render_template_section(_TEST_CASE_TEMPLATES, "tcs")
    _import_tab(
        tab_key="tcs",
        entity_label="test cases",
        uploader_label="Test cases CSV",
        parse_fn=parse_test_cases_csv,
        commit_fn=commit_test_cases_csv,
        repo=repo,
        project_id=pid,
    )
