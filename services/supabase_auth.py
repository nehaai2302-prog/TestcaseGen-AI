"""Supabase Auth helpers for Streamlit session management."""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from supabase import Client, create_client

SESSION_AUTH_KEY = "auth_session"


class AuthError(RuntimeError):
    """Raised when sign-in or sign-up fails."""


def _anon_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")
    return create_client(url, key)


def _first_name_from_user(user: Any) -> str:
    meta = getattr(user, "user_metadata", None) or {}
    if not isinstance(meta, dict):
        return ""
    raw = str(meta.get("first_name") or meta.get("full_name") or "").strip()
    if not raw:
        return ""
    return raw.split()[0]


def _store_session(session: Any, email: str | None = None) -> None:
    user = session.user
    resolved_email = email or getattr(user, "email", None) or ""
    payload = {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": str(user.id),
        "email": resolved_email,
        "first_name": _first_name_from_user(user),
    }
    st.session_state[SESSION_AUTH_KEY] = payload
    st.session_state["auth_token"] = session.access_token


def sign_up(
    email: str,
    password: str,
    *,
    first_name: str | None = None,
) -> dict[str, Any]:
    client = _anon_client()
    cleaned_name = (first_name or "").strip()
    payload: dict[str, Any] = {
        "email": email.strip(),
        "password": password,
    }
    if cleaned_name:
        payload["options"] = {"data": {"first_name": cleaned_name.split()[0]}}
    try:
        res = client.auth.sign_up(payload)
    except Exception as e:
        raise AuthError(str(e)) from e
    if res.session:
        _store_session(res.session, email.strip())
    return {"user": res.user, "session": res.session}


def sign_in(email: str, password: str) -> dict[str, Any]:
    client = _anon_client()
    try:
        res = client.auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
    except Exception as e:
        raise AuthError(str(e)) from e
    if not res.session:
        raise AuthError("Sign-in did not return a session.")
    _store_session(res.session, email.strip())
    return {"user": res.user, "session": res.session}


def sign_out() -> None:
    sess = get_auth_session()
    if sess and sess.get("access_token"):
        try:
            client = _anon_client()
            client.auth.set_session(sess["access_token"], sess["refresh_token"])
            client.auth.sign_out()
        except Exception:
            pass
    for key in (SESSION_AUTH_KEY, "auth_token"):
        st.session_state.pop(key, None)
    from services.session_project import clear_active_project

    clear_active_project()


def get_auth_session() -> dict[str, Any] | None:
    raw = st.session_state.get(SESSION_AUTH_KEY)
    return raw if isinstance(raw, dict) else None


def get_access_token() -> str | None:
    sess = get_auth_session()
    if sess and sess.get("access_token"):
        return str(sess["access_token"])
    legacy = st.session_state.get("auth_token")
    return str(legacy) if legacy else None


def get_auth_token() -> str | None:
    """Alias used by PLAN.md and downstream callers."""
    return get_access_token()


def get_current_user_id() -> str | None:
    sess = get_auth_session()
    if sess and sess.get("user_id"):
        return str(sess["user_id"])
    return None


def get_current_user() -> dict[str, Any] | None:
    sess = get_auth_session()
    if not sess or not sess.get("user_id"):
        return None
    return {
        "id": str(sess["user_id"]),
        "email": str(sess.get("email") or ""),
        "first_name": str(sess.get("first_name") or "").strip(),
    }


def get_welcome_first_name() -> str | None:
    """First name for Home greetings; falls back to email local-part if unset."""
    user = get_current_user()
    if not user:
        return None
    name = str(user.get("first_name") or "").strip()
    if name:
        return name.split()[0]
    email = str(user.get("email") or "").strip()
    local = email.split("@", 1)[0].strip()
    if not local:
        return None
    token = local.replace(".", " ").replace("_", " ").replace("-", " ").split()[0]
    if not token:
        return None
    return token[:1].upper() + token[1:]


def is_authenticated() -> bool:
    return bool(get_access_token())


def init_auth_session() -> None:
    """Refresh the JWT on app startup when a refresh token is stored."""
    sess = get_auth_session()
    if not sess or not sess.get("refresh_token"):
        return
    try:
        client = _anon_client()
        res = client.auth.refresh_session(str(sess["refresh_token"]))
        if res.session:
            _store_session(res.session, str(sess.get("email") or ""))
    except Exception:
        st.session_state.pop(SESSION_AUTH_KEY, None)
        st.session_state.pop("auth_token", None)


def get_authenticated_client() -> Client:
    sess = get_auth_session()
    if not sess or not sess.get("access_token"):
        raise RuntimeError("Sign in required.")
    client = _anon_client()
    client.auth.set_session(
        str(sess["access_token"]),
        str(sess.get("refresh_token") or ""),
    )
    return client


def require_auth() -> None:
    """Stop the page unless the user is signed in."""
    if is_authenticated():
        return
    st.warning("Please sign in to continue.")
    st.page_link("pages/Auth/Login.py", label="Go to Login", icon="🔐")
    st.stop()
