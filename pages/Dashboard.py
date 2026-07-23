"""Project overview and recent generation runs."""



from __future__ import annotations



from datetime import datetime



import re



import streamlit as st



from services.bootstrap import get_repo

from services.project_ui import active_project_name
from services.supabase_auth import require_auth

from theme import apply_theme, render_active_project_banner, render_back_to_home_link, render_gradient_metric



apply_theme()
require_auth()

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





def _parse_dedup_stats(model_name: object) -> dict[str, int]:
    text = str(model_name or "")
    stats: dict[str, int] = {}
    for key in ("dedup_kept", "batch_title", "batch_verbatim", "batch_cross_req", "batch_semantic", "library"):
        match = re.search(rf"{key}=(\d+)", text)
        if match:
            stats[key] = int(match.group(1))
    return stats


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
last_dedup = _parse_dedup_stats(last_row.get("model_name") if last_row else None)
last_ts = _format_timestamp(last_row.get("created_at") if last_row else None)

last_ts_date = _format_date_only(last_row.get("created_at") if last_row else None)

last_ts_help = f"Full timestamp: {last_ts}" if last_row else None



req_metric_help = (
    "Distinct requirement IDs with at least one linked test case "
    "(generated and/or imported). Open Traceability for the per-requirement split."
)

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    render_gradient_metric(
        "Generated test cases",
        trace["generated"],
        "purple",
        help="Cases created by the QAWeaver pipeline for this project.",
    )
    st.page_link("pages/Library.py", label="View in Library →", icon="📚")

with c2:
    render_gradient_metric(
        "Imported testcases (history)",
        trace["imported"],
        "indigo",
        help="Test cases imported from CSV/XLSX (project history), not AI-generated.",
    )

with c3:
    render_gradient_metric(
        "Bug reports",
        repo.count_bug_reports(pid),
        "warm",
        help="All bug reports for this project (typically imported from CSV).",
    )
    st.page_link("pages/Bugs.py", label="View all bug reports →", icon="🐛")

with c4:
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

with c5:
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

if last_dedup:
    st.caption(
        "Last generation dedup: kept "
        f"**{last_dedup.get('dedup_kept', '—')}** · "
        f"title −{last_dedup.get('batch_title', 0)} · "
        f"verbatim −{last_dedup.get('batch_verbatim', 0)} · "
        f"cross-req −{last_dedup.get('batch_cross_req', 0)} · "
        f"semantic −{last_dedup.get('batch_semantic', 0)} · "
        f"library −{last_dedup.get('library', 0)}"
    )

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


