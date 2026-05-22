"""Streamlit entry: welcome, project selection, and next-step navigation."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from services.bootstrap import get_repo
from services.project_ui import active_project_name
from theme import (
    apply_theme,
    render_active_project_banner,
    render_home_action_card,
    render_home_api_status,
    render_home_empty_state,
    render_home_welcome,
    render_home_your_path,
)


def _home_step_progress(repo: Any, project_id: str | None) -> tuple[int | None, set[int]]:
    """Map project data to checklist: completed steps and current active step."""
    if not project_id:
        return 1, set()
    trace = repo.get_test_case_traceability(project_id)
    has_generated = int(trace.get("generated") or 0) > 0
    has_context = (
        int(trace.get("imported") or 0) > 0
        or repo.count_bug_reports(project_id) > 0
        or repo.count_requirements(project_id) > 0
    )
    done: set[int] = {1}
    if has_context:
        done.add(2)
    if has_generated:
        done.add(3)
    if has_generated:
        return None, done
    return (3 if has_context else 2), done


load_dotenv()

apply_theme()

st.title("🧪 TestCraft AI")

try:
    repo = get_repo()
except Exception as e:
    st.error(f"❌ Configuration error: {e}")
    st.stop()

projects = repo.list_projects()
api_ready = bool(os.getenv("OPENAI_API_KEY"))

if not projects:
    render_home_welcome(
        "Welcome to AI-powered test generation for QA teams",
        accent=True,
    )
    render_home_empty_state()
    render_home_your_path(active_step=1, completed_steps=set())
else:
    render_home_welcome(
        "Welcome back",
        subtitle="Glad to see you again. Let's keep building up Quality!",
    )

    opts = {p["name"]: p["id"] for p in projects}
    names = list(opts.keys())
    valid_ids = {p["id"] for p in projects}
    if st.session_state.get("project_id") not in valid_ids:
        st.session_state["project_id"] = projects[0]["id"]
    default_idx = 0
    for i, p in enumerate(projects):
        if p["id"] == st.session_state.get("project_id"):
            default_idx = i
            break
    render_active_project_banner(
        active_project_name(projects, st.session_state["project_id"])
    )

    pick, manage = st.columns([3, 1])
    with pick:
        choice = st.selectbox(
            "Which product are you testing?",
            options=names,
            index=default_idx,
            key="home_project_name",
        )
    st.session_state["project_id"] = opts[choice]
    with manage:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        st.page_link("pages/Settings.py", label="Manage in Settings →")

    step_active, step_done = _home_step_progress(
        repo, st.session_state.get("project_id")
    )
    render_home_your_path(active_step=step_active, completed_steps=step_done)

    st.markdown("#### Get started")
    c1, c2, c3 = st.columns(3)
    with c1:
        render_home_action_card(
            "indigo",
            "📥",
            "Import CSV",
            "Optional: import past bugs and test cases from CSV so the AI can use your project history.",
            "pages/Import.py",
            link_label="Import →",
        )
    with c2:
        render_home_action_card(
            "purple",
            "🪄",
            "Generate tests",
            "AI-powered test cases from your context",
            "pages/Generate.py",
            link_label="Generate →",
        )
    with c3:
        render_home_action_card(
            "teal",
            "📊",
            "View Dashboard",
            "Progress, coverage and quality insights",
            "pages/Dashboard.py",
            link_label="Dashboard →",
        )

    st.markdown(
        '<div class="home-quick-access">'
        '<div class="home-quick-access__label">Quick access</div></div>',
        unsafe_allow_html=True,
    )
    q1, q2, q3 = st.columns(3)
    q1.page_link("pages/Library.py", label="Library", icon="📚")
    q2.page_link("pages/Traceability.py", label="Traceability", icon="🔗")
    q3.page_link("pages/Bugs.py", label="Bug reports", icon="🐛")

render_home_api_status(api_ready=api_ready)
