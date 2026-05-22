"""Requirements traceability matrix with optional module filter."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
from services.project_ui import (
    MODULE_ALL,
    MODULE_NONE,
    MODULE_NONE_SENTINEL,
    active_project_name,
    module_filter_options,
    resolve_module_filter,
    test_cases_breakdown_help,
)
from theme import (
    apply_theme,
    render_active_project_banner,
    render_back_to_home_link,
    render_gradient_metric,
)

apply_theme()
render_back_to_home_link()

st.title("🔗 Requirements Traceability Matrix")
st.caption("Requirements → test cases")

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

# Load once for module dropdown options
_all_tc = repo.list_test_cases(pid, limit=5000)
_mod_opts = module_filter_options(_all_tc)
if MODULE_ALL not in _mod_opts:
    _mod_opts = [MODULE_ALL]

if st.session_state.get("trace_module_filter") not in _mod_opts:
    st.session_state["trace_module_filter"] = MODULE_ALL

mod_choice = st.selectbox(
    "Filter by module",
    options=_mod_opts,
    key="trace_module_filter",
)

module_filter = resolve_module_filter(mod_choice)
trace = repo.get_test_case_traceability(pid, module_filter=module_filter)

if module_filter is None:
    scope = "all modules in this project"
elif module_filter == MODULE_NONE_SENTINEL:
    scope = "cases with **no module** set"
else:
    scope = f"module **{mod_choice}**"

if trace["project_total"] and trace["total"] != trace["project_total"]:
    st.caption(
        f"Showing {trace['total']} of {trace['project_total']} test cases ({scope})."
    )
else:
    st.caption(f"Showing test cases for {scope}.")

m1, m2 = st.columns(2)
_trace_req_help = (
    "Distinct requirement IDs with at least one test case in the current module filter."
)

with m1:
    render_gradient_metric(
        "Test cases",
        trace["total"],
        "purple",
        help=test_cases_breakdown_help(trace),
    )
with m2:
    render_gradient_metric(
        "Requirements covered",
        trace["distinct_requirements"],
        "teal",
        help=_trace_req_help,
    )

st.subheader("Requirements → test cases")
st.caption(
    "Each row is a requirement ID with test coverage in the current filter. "
    "Open Library to see matching cases."
)


def _library_params(req_id: str | None = None, unlinked: bool = False) -> dict[str, str]:
    params: dict[str, str] = {}
    if unlinked:
        params["unlinked"] = "1"
    elif req_id:
        params["linked_requirement"] = req_id
    if module_filter is None:
        pass
    elif module_filter == MODULE_NONE_SENTINEL:
        params["module"] = MODULE_NONE_SENTINEL
    else:
        params["module"] = module_filter
    return params


if trace["by_requirement"] or trace["unlinked"]:
    header = st.columns([2, 1, 2])
    header[0].markdown("**Requirement ID**")
    header[1].markdown("**Test cases**")
    header[2].markdown("**Library**")

    for row in trace["by_requirement"]:
        req_id = row["linked_requirement"]
        count = row["test_case_count"]
        cols = st.columns([2, 1, 2])
        cols[0].write(req_id)
        cols[1].write(str(count))
        cols[2].page_link(
            "pages/Library.py",
            label=f"View {req_id} in Library →",
            icon="📚",
            query_params=_library_params(req_id=req_id),
        )

    if trace["unlinked"]:
        cols = st.columns([2, 1, 2])
        cols[0].write("*(Unlinked / no requirement ID)*")
        cols[1].write(str(trace["unlinked"]))
        cols[2].page_link(
            "pages/Library.py",
            label="View unlinked in Library →",
            icon="📚",
            query_params=_library_params(unlinked=True),
        )
else:
    st.info(
        "No test cases match this filter with a linked requirement. "
        "Try **(All modules)** or generate tests from the Generate page."
    )
