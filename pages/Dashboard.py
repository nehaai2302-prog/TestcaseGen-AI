"""Project overview and recent generation runs."""



from __future__ import annotations



from datetime import datetime



import streamlit as st



from services.bootstrap import get_repo

from services.project_ui import active_project_name, test_cases_breakdown_help

from theme import apply_theme, render_active_project_banner, render_back_to_home_link, render_gradient_metric



apply_theme()

render_back_to_home_link()



st.title("📊 Dashboard")



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





def _format_timestamp(value: object) -> str:

    if value is None:

        return "—"

    text = str(value).strip()

    if not text:

        return "—"

    try:

        normalized = text.replace("Z", "+00:00")

        if " " in normalized and "T" not in normalized:

            normalized = normalized.replace(" ", "T", 1)

        dt = datetime.fromisoformat(normalized)

        return dt.strftime("%Y-%m-%d %H:%M:%S")

    except ValueError:

        return text.replace("T", " ")[:19]





def _format_date_only(value: object) -> str:

    full = _format_timestamp(value)

    if full == "—":

        return full

    return full.split(" ", 1)[0]





trace = repo.get_test_case_traceability(pid)



hist_rows = repo.list_generation_history(pid, limit=15)

last_row = hist_rows[0] if hist_rows else None

last_ts = _format_timestamp(last_row.get("created_at") if last_row else None)

last_ts_date = _format_date_only(last_row.get("created_at") if last_row else None)

last_ts_help = f"Full timestamp: {last_ts}" if last_row else None



req_metric_help = (
    "Distinct requirement IDs with at least one linked test case in this project. "
    "Use Traceability Matrix for a per-module breakdown and matrix."
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    render_gradient_metric(
        "Test cases",
        trace["total"],
        "purple",
        help=test_cases_breakdown_help(trace),
    )
    st.page_link("pages/Library.py", label="View in Library →", icon="📚")

with c2:

    render_gradient_metric(
        "Bug reports",
        repo.count_bug_reports(pid),
        "warm",
        help="All bug reports for this project (typically imported from CSV).",
    )

    st.page_link("pages/Bugs.py", label="View all bug reports →", icon="🐛")

with c3:

    render_gradient_metric(
        "Requirements covered",
        trace["distinct_requirements"],
        "teal",
        help=req_metric_help,
    )

    st.page_link(

        "pages/Traceability.py",

        label="View traceability matrix →",

        icon="🔗",

    )

with c4:

    render_gradient_metric(
        "Last generation",
        last_ts_date,
        "indigo",
        help=last_ts_help,
    )

    if last_row:

        if st.button(

            "Show last run in table ↓",

            key="dash_filter_last_run",

            type="tertiary",

            icon="🔽",

        ):

            st.session_state["dash_show_last_run_only"] = True

            st.rerun()



show_last_only = bool(st.session_state.get("dash_show_last_run_only")) and last_row is not None



st.subheader("Recent generation runs")

if show_last_only:

    col_a, col_b = st.columns([3, 1])

    with col_a:

        st.caption(f"Filtered to last run at **{last_ts}**.")

    with col_b:

        if st.button(

            "Show all runs",

            key="dash_clear_last_run_filter",

            type="tertiary",

            icon="📋",

        ):

            st.session_state.pop("dash_show_last_run_only", None)

            st.rerun()

    display_rows = [last_row]

else:

    display_rows = hist_rows



if display_rows:

    table_rows = []

    for r in display_rows:

        row = dict(r)

        if row.get("created_at") is not None:

            row["created_at"] = _format_timestamp(row["created_at"])

        table_rows.append(row)

    st.dataframe(table_rows, use_container_width=True, hide_index=True)

else:

    st.info("No generation history yet.")


