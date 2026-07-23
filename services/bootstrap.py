"""Cached Supabase client for Streamlit."""

from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from services.supabase_auth import get_authenticated_client, get_current_user_id, is_authenticated
from services.supabase_repo import SupabaseRepo, _get_service_client


@st.cache_resource
def _cached_service_client():
    load_dotenv(override=True)
    return _get_service_client()


def get_repo() -> SupabaseRepo:
    """User-scoped repo; RLS enforces project isolation."""
    if not is_authenticated():
        raise RuntimeError("Sign in required to access data.")
    return SupabaseRepo(
        client=get_authenticated_client(),
        user_id=get_current_user_id(),
    )


def get_service_repo() -> SupabaseRepo:
    """Service-role client for server-only operations (e.g. demo video URLs)."""
    return SupabaseRepo(client=_cached_service_client())
