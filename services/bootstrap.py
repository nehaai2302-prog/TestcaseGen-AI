"""Cached Supabase client for Streamlit."""

from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from services.supabase_repo import SupabaseRepo, _get_client


@st.cache_resource
def _cached_supabase_client():
    load_dotenv()
    return _get_client()


def get_repo() -> SupabaseRepo:
    """Fresh repo each run so new methods are picked up; client stays cached."""
    return SupabaseRepo(client=_cached_supabase_client())
