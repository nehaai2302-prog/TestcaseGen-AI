"""Projects and non-secret runtime knobs."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
from services.session_project import clear_active_project, set_active_project
from services.supabase_repo import DuplicateProjectNameError
from services.openai_errors import KEY_INVALID_MSG, KEY_MISSING_MSG, resolve_openai_banner_message
from theme import apply_theme, render_back_to_home_link

apply_theme()
render_back_to_home_link()
st.title("⚙️ Settings")
st.caption("Create a workspace here, then return to Home for your next steps.")

try:
    repo = get_repo()
except Exception as e:
    st.error(str(e))
    st.stop()

st.subheader("Projects")
with st.form("new_project"):
    name = st.text_input("Project name")
    desc = st.text_area("Description (optional)")
    switch_to_new = st.checkbox("Switch to this project now", value=False)
    if st.form_submit_button("➕ Create project"):
        clean_name = name.strip()
        if not clean_name:
            st.error("Name is required.")
        elif clean_name.lower() in {
            str(p.get("name") or "").strip().lower() for p in repo.list_projects()
        }:
            st.error("A project with this name already exists. Choose a different name.")
        else:
            prev_active_id = str(st.session_state.get("project_id") or "").strip() or None
            try:
                p = repo.create_project(clean_name, desc.strip() or None)
            except DuplicateProjectNameError:
                st.error("A project with this name already exists. Choose a different name.")
            else:
                if switch_to_new:
                    set_active_project(str(p["id"]))
                    st.success("Project created and switched.")
                else:
                    # Re-assert previous active project so creation never changes context implicitly.
                    if prev_active_id:
                        set_active_project(prev_active_id)
                        st.success("Project created. Active project unchanged.")
                    else:
                        st.success("Project created successfully.")
                st.page_link("Home.py", label="Continue on Home →", icon="🏠")

projects = repo.list_projects()
if projects:
    st.dataframe(projects, use_container_width=True, hide_index=True)
    del_id = st.selectbox(
        "Delete project",
        options=[p["id"] for p in projects],
        format_func=lambda i: next(p["name"] for p in projects if p["id"] == i),
    )
    if st.button("🗑️ Delete selected project", type="primary"):
        repo.delete_project(str(del_id))
        clear_active_project()
        st.success("Deleted. Refresh sidebar.")
        st.rerun()

st.subheader("Retrieval knobs (session)")
st.caption("These override defaults for the next generation run in this browser session.")
st.session_state["retrieval_top_k"] = st.slider("Top K per retrieval", 3, 30, 12)
st.session_state["retrieval_threshold"] = st.slider(
    "Similarity threshold", 0.05, 0.5, 0.15, step=0.01
)

banner_msg = resolve_openai_banner_message()
if banner_msg:
    st.subheader("AI setup")
    st.warning(banner_msg)
    if banner_msg == KEY_MISSING_MSG:
        st.caption(
            "Deployers: set the API key in `.env` (see `.env.example`) or "
            "**Streamlit Cloud → Secrets**, then restart the app."
        )
    elif banner_msg == KEY_INVALID_MSG:
        st.caption(
            "Deployers: update the API key in `.env` or **Streamlit Cloud → Secrets**, "
            "then restart the app."
        )
