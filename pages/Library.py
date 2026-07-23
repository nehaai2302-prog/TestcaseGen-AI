"""Semantic search and filters over saved test cases."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
from services.export import test_cases_to_dataframe, to_csv_bytes, to_excel_bytes
from services.library_search import library_test_case_rows
from services.openai_errors import friendly_openai_error, remember_openai_probe_failure
from services.project_ui import MODULE_NONE_SENTINEL, active_project_name
from services.supabase_auth import require_auth
from theme import (
    apply_theme,
    render_active_project_banner,
    render_back_to_home_link,
    render_library_case_detail,
    render_library_requirement_preview,
    scroll_to_anchor,
)

apply_theme()
require_auth()
render_back_to_home_link()

st.title("📚 Test case library")

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

pid = st.session_state.get("project_id")
if not pid:
    st.warning("Select a project from the home page first.")
    st.stop()

projects = repo.list_projects()
render_active_project_banner(active_project_name(projects, pid))

if "lib_selected_case_id" not in st.session_state:
    st.session_state.lib_selected_case_id = None
if "lib_prev_selected_case_id" not in st.session_state:
    st.session_state.lib_prev_selected_case_id = None

_REQ_ALL = "(all requirements)"
_REQ_UNLINKED = "(no linked requirement)"

# Apply filter reset before any widget with key="library_req_filter" is created.
if st.session_state.pop("lib_clear_filters_pending", False):
    st.query_params.clear()
    st.session_state.pop("library_linked_requirement", None)
    st.session_state.pop("library_module_filter", None)
    st.session_state["library_req_filter"] = _REQ_ALL
    st.session_state.lib_selected_case_id = None
    st.session_state.lib_prev_selected_case_id = None

_unlinked_qp = st.query_params.get("unlinked")
if isinstance(_unlinked_qp, list):
    _unlinked_qp = _unlinked_qp[0] if _unlinked_qp else None
_filter_unlinked_only = _unlinked_qp in ("1", "true", "yes")

_req_qp = st.query_params.get("linked_requirement")
if isinstance(_req_qp, list):
    _req_qp = _req_qp[0] if _req_qp else None
_default_req = (st.session_state.get("library_linked_requirement") or _req_qp or "").strip()
if _req_qp and not _filter_unlinked_only:
    st.session_state["library_linked_requirement"] = _req_qp

_mod_qp = st.query_params.get("module")
if isinstance(_mod_qp, list):
    _mod_qp = _mod_qp[0] if _mod_qp else None
_module_filter_sentinel: str | None = None
if _mod_qp == MODULE_NONE_SENTINEL:
    _module_filter_sentinel = MODULE_NONE_SENTINEL
elif _mod_qp and str(_mod_qp).strip():
    _module_filter_sentinel = str(_mod_qp).strip()
    st.session_state["library_module_filter"] = _module_filter_sentinel

c1, c2, c3, c4 = st.columns(4)
with c1:
    q = st.text_input(
        "Semantic search",
        placeholder="Describe tests you are looking for",
        key="lib_semantic_search",
    )
with c2:
    tfilter = st.selectbox(
        "Test type",
        ["(any)", "positive", "negative", "edge", "boundary"],
    )
with c3:
    pfilter = st.selectbox("Priority", ["(any)", "high", "medium", "low"])
with c4:
    sfilter = st.selectbox("Source", ["(any)", "generated", "imported"])

_req_summaries = repo.list_requirement_summaries_for_project(str(pid))
_req_ids = [str(s["requirement_id"]) for s in _req_summaries]
_req_options = [_REQ_ALL, _REQ_UNLINKED, *_req_ids]

# Deep-link / session default → selectbox (must run before the widget exists).
if _filter_unlinked_only:
    _req_default = _REQ_UNLINKED
elif _default_req and _default_req in _req_ids:
    _req_default = _default_req
elif _default_req and _default_req not in _req_ids:
    _req_default = _REQ_ALL
else:
    _req_default = _REQ_ALL

if "library_req_filter" not in st.session_state:
    st.session_state["library_req_filter"] = _req_default
elif _filter_unlinked_only:
    st.session_state["library_req_filter"] = _REQ_UNLINKED
elif _req_qp and _req_qp in _req_options:
    st.session_state["library_req_filter"] = _req_qp

_preview_by_id = {str(s["requirement_id"]): s.get("preview") or "" for s in _req_summaries}


def _format_req_option(value: str) -> str:
    if value in (_REQ_ALL, _REQ_UNLINKED):
        return value
    preview = _preview_by_id.get(value) or ""
    return f"{value} — {preview}" if preview else value


req_choice = st.selectbox(
    "Requirement (this project)",
    options=_req_options,
    format_func=_format_req_option,
    key="library_req_filter",
    help=(
        "Filter test cases by a requirement stored for the active project. "
        "Requirements are listed A–Z by ID."
    ),
)

_filter_unlinked_only = req_choice == _REQ_UNLINKED
req_filter = "" if req_choice in (_REQ_ALL, _REQ_UNLINKED) else req_choice

_has_deep_link = (
    _filter_unlinked_only
    or bool(req_filter)
    or bool(_module_filter_sentinel)
    or (_default_req and _default_req not in _req_ids)
)
if _filter_unlinked_only:
    st.caption("Showing test cases with **no** linked requirement (imported / unmapped).")
elif req_filter:
    st.caption(f"Showing test cases linked to **{req_filter}**.")
elif _default_req and _default_req not in _req_ids:
    st.caption(
        f"Requirement **{_default_req}** is not in the current project SRS store "
        "(filter cleared to all). Re-prepare the document if you still need that ID."
    )
if _module_filter_sentinel == MODULE_NONE_SENTINEL:
    st.caption("Showing test cases with **no module** set.")
elif _module_filter_sentinel:
    st.caption(f"Showing test cases in module **{_module_filter_sentinel}**.")
if _has_deep_link:
    if st.button("Clear filters", key="lib_clear_filters"):
        # Defer session_state widget key updates until the next run (before widget).
        st.session_state["lib_clear_filters_pending"] = True
        st.rerun()
try:
    if q.strip():
        with st.spinner("Searching test cases…"):
            rows, search_mode = library_test_case_rows(
                repo,
                pid,
                q,
                test_type=tfilter,
                priority=pfilter,
                source=sfilter,
            )
    else:
        rows, search_mode = library_test_case_rows(
            repo,
            pid,
            "",
            test_type=tfilter,
            priority=pfilter,
            source=sfilter,
        )
except Exception as exc:
    msg = friendly_openai_error(exc)
    if msg:
        remember_openai_probe_failure(exc)
        st.error(msg)
        st.stop()
    raise

if _module_filter_sentinel == MODULE_NONE_SENTINEL:
    rows = [r for r in rows if not (r.get("module") or "").strip()]
elif _module_filter_sentinel:
    rows = [
        r
        for r in rows
        if (r.get("module") or "").strip() == _module_filter_sentinel
    ]

if _filter_unlinked_only:
    rows = [r for r in rows if not (r.get("linked_requirement") or "").strip()]
elif req_filter.strip():
    needle = req_filter.strip()
    rows = [
        r
        for r in rows
        if (r.get("linked_requirement") or "").strip() == needle
    ]

row_ids = {str(r["id"]) for r in rows}
selected_id = st.session_state.get("lib_selected_case_id")
if selected_id and selected_id not in row_ids:
    st.session_state.lib_selected_case_id = None
    selected_id = None

if search_mode == "semantic":
    st.caption(
        f"Semantic search: **{len(rows)}** matches for “{q.strip()}”. "
        "Use the checkbox (or row selector) on the left to view details below."
    )
elif search_mode == "keyword":
    st.caption(
        f"No vector matches; showing **{len(rows)}** keyword matches for “{q.strip()}”. "
        "(Imported cases may lack embeddings.)"
    )
elif q.strip():
    st.warning(
        f"No test cases matched “{q.strip()}”. "
        "Try different words, clear other filters, or check that cases have titles/descriptions."
    )
else:
    st.caption(
        f"Showing {len(rows)} rows. Use the checkbox (or row selector) on the left to select "
        "a test case — details appear below the table."
    )

if rows:
    show_cols = [
        "testcase_id",
        "linked_requirement",
        "module",
        "title",
        "test_type",
        "priority",
        "source",
        "is_duplicate",
    ]
    if "_similarity" in rows[0]:
        show_cols.append("_similarity")
    table_rows = [{k: r.get(k) for k in show_cols} for r in rows]

    df_event = st.dataframe(
        table_rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="lib_case_table",
    )

    sel_rows: list[int] = []
    if df_event is not None and hasattr(df_event, "selection"):
        sel_rows = list(getattr(df_event.selection, "rows", None) or [])
    if not sel_rows:
        table_state = st.session_state.get("lib_case_table")
        if isinstance(table_state, dict):
            sel_rows = list(table_state.get("selection", {}).get("rows", []) or [])
        elif table_state is not None and hasattr(table_state, "selection"):
            sel_rows = list(getattr(table_state.selection, "rows", None) or [])
    if sel_rows:
        idx = int(sel_rows[0])
        if 0 <= idx < len(rows):
            st.session_state.lib_selected_case_id = str(rows[idx]["id"])
    else:
        st.session_state.lib_selected_case_id = None

    df = test_cases_to_dataframe(rows)
    if not df.empty:
        _export_help = f"Download all {len(rows)} test cases in the current filter."
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇️ Download CSV",
                data=to_csv_bytes(df),
                file_name="test_cases.csv",
                type="primary",
                use_container_width=True,
                key="lib_export_csv",
                help=_export_help,
            )
        with c2:
            st.download_button(
                "⬇️ Download Excel",
                data=to_excel_bytes(df),
                file_name="test_cases.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
                key="lib_export_xlsx",
                help=_export_help,
            )

    selected_id = st.session_state.get("lib_selected_case_id")
    if selected_id:
        case = next((r for r in rows if str(r["id"]) == selected_id), None)
        if case is not None:
            if selected_id != st.session_state.get("lib_prev_selected_case_id"):
                st.toast("Showing test case details below.", icon="📋")
                st.session_state.lib_prev_selected_case_id = selected_id

            st.markdown('<div id="lib-test-case-detail"></div>', unsafe_allow_html=True)
            st.divider()
            st.subheader("Test case detail")
            render_library_case_detail(case)
            linked_rid = (case.get("linked_requirement") or "").strip()
            if linked_rid:
                req_chunks = repo.get_requirement_chunks_by_id(str(pid), linked_rid)
                render_library_requirement_preview(linked_rid, req_chunks)
            scroll_to_anchor("lib-test-case-detail")
        else:
            st.session_state.lib_selected_case_id = None
            st.session_state.lib_prev_selected_case_id = None
    else:
        st.session_state.lib_prev_selected_case_id = None
else:
    if not q.strip():
        st.info("No test cases match the current filters.")
    st.session_state.lib_selected_case_id = None
    st.session_state.lib_prev_selected_case_id = None
