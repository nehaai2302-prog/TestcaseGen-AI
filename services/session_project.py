"""Persist active project across browser refresh and page-local workflow resets."""

from __future__ import annotations

from typing import Any

import streamlit as st

PROJECT_QUERY_PARAM = "project_id"

GENERATE_WORKFLOW_KEYS = (
    "req_chunks",
    "req_doc_name",
    "req_parse_quality",
    "srs_change_report",
    "last_run",
)


def sync_project_to_url(project_id: str | None) -> None:
    """Write active project into the URL so F5 keeps the same workspace."""
    if project_id:
        st.query_params[PROJECT_QUERY_PARAM] = str(project_id)
    elif PROJECT_QUERY_PARAM in st.query_params:
        del st.query_params[PROJECT_QUERY_PARAM]


def _valid_project_ids() -> set[str]:
    try:
        from services.bootstrap import get_repo

        projects = get_repo().list_projects()
        return {str(p["id"]) for p in projects}
    except Exception:
        return set()


def restore_project_from_session() -> None:
    """Restore project_id from URL after browser refresh; keep URL in sync."""
    qp_raw = st.query_params.get(PROJECT_QUERY_PARAM)
    qp = str(qp_raw).strip() if qp_raw else None
    sid = st.session_state.get("project_id")
    sid = str(sid).strip() if sid else None

    valid = _valid_project_ids()

    if sid and valid and sid not in valid:
        st.session_state.pop("project_id", None)
        sid = None
        sync_project_to_url(None)

    if qp and valid and qp not in valid:
        sync_project_to_url(sid)
        qp = None

    if sid:
        if qp != sid:
            sync_project_to_url(sid)
        return

    if qp:
        st.session_state["project_id"] = qp
        return


def set_active_project(project_id: str) -> None:
    """Select workspace for this browser session and persist in the URL."""
    new_id = str(project_id).strip()
    prev_id = str(st.session_state.get("project_id") or "").strip()
    if prev_id and prev_id != new_id:
        clear_generate_workflow()
    st.session_state["project_id"] = new_id
    st.session_state["generate_workflow_project_id"] = new_id
    sync_project_to_url(new_id)


def clear_active_project() -> None:
    st.session_state.pop("project_id", None)
    st.session_state.pop("generate_workflow_project_id", None)
    clear_generate_workflow()
    sync_project_to_url(None)


def ensure_generate_workflow_for_project(project_id: str) -> None:
    """Drop prepared requirements / last run when the active project changes."""
    pid = str(project_id).strip()
    bound = str(st.session_state.get("generate_workflow_project_id") or "").strip()
    if bound != pid:
        clear_generate_workflow()
        st.session_state["generate_workflow_project_id"] = pid


def clear_generate_workflow() -> None:
    """Reset Generate page state for a new document/run (keeps active project)."""
    for key in GENERATE_WORKFLOW_KEYS:
        st.session_state.pop(key, None)
    st.session_state["generate_upload_nonce"] = (
        int(st.session_state.get("generate_upload_nonce") or 0) + 1
    )
