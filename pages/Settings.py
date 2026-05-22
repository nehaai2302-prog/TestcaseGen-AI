"""Projects and non-secret runtime knobs."""

from __future__ import annotations

import streamlit as st

from services.bootstrap import get_repo
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
    if st.form_submit_button("➕ Create project"):
        if not name.strip():
            st.error("Name is required.")
        else:
            p = repo.create_project(name.strip(), desc.strip() or None)
            st.session_state["project_id"] = p["id"]
            st.success(f"Created project **{p['name']}**. Head back to Home to continue.")
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
        st.session_state.pop("project_id", None)
        st.success("Deleted. Refresh sidebar.")
        st.rerun()

st.subheader("Retrieval knobs (session)")
st.caption("These override defaults for the next generation run in this browser session.")
st.session_state["retrieval_top_k"] = st.slider("Top K per retrieval", 3, 30, 12)
st.session_state["retrieval_threshold"] = st.slider(
    "Similarity threshold", 0.05, 0.5, 0.15, step=0.01
)

st.subheader("Secrets")
st.markdown(
    """
Configure locally via `.env` (see `.env.example`) or **Streamlit Cloud secrets**:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Optional: `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDING_MODEL`, `RETRIEVAL_TOP_K`, `RETRIEVAL_MATCH_THRESHOLD`, `DEDUP_SIMILARITY_THRESHOLD`.
"""
)
