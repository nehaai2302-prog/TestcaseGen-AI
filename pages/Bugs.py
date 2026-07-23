"""Browse bug reports imported for the active project."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
from services.project_ui import active_project_name
from services.supabase_auth import require_auth
from theme import (
    apply_theme,
    render_active_project_banner,
    render_back_to_home_link,
    render_bug_report_detail,
    scroll_to_anchor,
)

apply_theme()
require_auth()
render_back_to_home_link()

st.title("🐛 Bug reports")

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

pid = st.session_state.get("project_id")
if not pid:
    st.warning("Select a project from the home page first.")
    st.stop()

if "bugs_selected_id" not in st.session_state:
    st.session_state.bugs_selected_id = None
if "bugs_prev_selected_id" not in st.session_state:
    st.session_state.bugs_prev_selected_id = None

projects = repo.list_projects()
render_active_project_banner(active_project_name(projects, pid))

rows = repo.list_bug_reports(pid, limit=500)

st.caption(
    f"Showing {len(rows)} bug report(s). Use the checkbox (or row selector) on the left "
    "to select a bug — details appear below the table."
)

if rows:
    show_cols = [
        "bug_number",
        "title",
        "severity",
        "component",
        "resolution",
        "created_at",
    ]
    table_rows = [{k: r.get(k) for k in show_cols} for r in rows]

    df_event = st.dataframe(
        table_rows,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="bugs_table",
    )

    sel_rows: list[int] = []
    if df_event is not None and hasattr(df_event, "selection"):
        sel_rows = list(getattr(df_event.selection, "rows", None) or [])
    if not sel_rows:
        table_state = st.session_state.get("bugs_table")
        if isinstance(table_state, dict):
            sel_rows = list(table_state.get("selection", {}).get("rows", []) or [])
        elif table_state is not None and hasattr(table_state, "selection"):
            sel_rows = list(getattr(table_state.selection, "rows", None) or [])

    if sel_rows:
        idx = int(sel_rows[0])
        if 0 <= idx < len(rows):
            st.session_state.bugs_selected_id = str(rows[idx]["id"])
    else:
        st.session_state.bugs_selected_id = None

    selected_id = st.session_state.get("bugs_selected_id")
    if selected_id:
        bug = next((r for r in rows if str(r["id"]) == selected_id), None)
        if bug is not None:
            if selected_id != st.session_state.get("bugs_prev_selected_id"):
                st.toast("Showing bug details below.", icon="🐛")
                st.session_state.bugs_prev_selected_id = selected_id

            st.markdown('<div id="bugs-detail-anchor"></div>', unsafe_allow_html=True)
            st.divider()
            st.subheader("Bug report detail")
            render_bug_report_detail(bug)
            scroll_to_anchor("bugs-detail-anchor")
        else:
            st.session_state.bugs_selected_id = None
            st.session_state.bugs_prev_selected_id = None
    else:
        st.session_state.bugs_prev_selected_id = None
else:
    st.info("No bug reports yet. Import bugs on the **Import** page.")
    st.session_state.bugs_selected_id = None
    st.session_state.bugs_prev_selected_id = None
