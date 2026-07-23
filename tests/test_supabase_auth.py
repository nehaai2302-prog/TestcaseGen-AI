"""Tests for Supabase auth session helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services import supabase_auth


@pytest.fixture
def session_state() -> dict:
    return {}


@pytest.fixture
def mock_streamlit(session_state: dict):
    with patch.object(supabase_auth, "st") as mock_st:
        mock_st.session_state = session_state
        yield mock_st


def test_is_authenticated_false_when_empty(mock_streamlit) -> None:
    assert supabase_auth.is_authenticated() is False


def test_is_authenticated_true_with_session(mock_streamlit, session_state: dict) -> None:
    session_state[supabase_auth.SESSION_AUTH_KEY] = {
        "access_token": "token-abc",
        "refresh_token": "refresh-abc",
        "user_id": "user-1",
        "email": "qa@example.com",
    }
    assert supabase_auth.is_authenticated() is True


def test_get_current_user_returns_profile(mock_streamlit, session_state: dict) -> None:
    session_state[supabase_auth.SESSION_AUTH_KEY] = {
        "access_token": "token-abc",
        "refresh_token": "refresh-abc",
        "user_id": "11111111-1111-1111-1111-111111111111",
        "email": "qa@example.com",
        "first_name": "Neha",
    }
    user = supabase_auth.get_current_user()
    assert user == {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "qa@example.com",
        "first_name": "Neha",
    }


def test_get_welcome_first_name_prefers_profile(
    mock_streamlit, session_state: dict
) -> None:
    session_state[supabase_auth.SESSION_AUTH_KEY] = {
        "access_token": "token-abc",
        "refresh_token": "refresh-abc",
        "user_id": "user-1",
        "email": "qa@example.com",
        "first_name": "Neha",
    }
    assert supabase_auth.get_welcome_first_name() == "Neha"


def test_get_welcome_first_name_falls_back_to_email(
    mock_streamlit, session_state: dict
) -> None:
    session_state[supabase_auth.SESSION_AUTH_KEY] = {
        "access_token": "token-abc",
        "refresh_token": "refresh-abc",
        "user_id": "user-1",
        "email": "neha.qa@example.com",
        "first_name": "",
    }
    assert supabase_auth.get_welcome_first_name() == "Neha"


def test_store_session_sets_auth_token(mock_streamlit, session_state: dict) -> None:
    session = MagicMock()
    session.access_token = "access"
    session.refresh_token = "refresh"
    session.user.id = "uid-1"
    session.user.email = "user@test.com"
    session.user.user_metadata = {"first_name": "Alex"}

    supabase_auth._store_session(session)

    assert session_state["auth_token"] == "access"
    assert session_state[supabase_auth.SESSION_AUTH_KEY]["user_id"] == "uid-1"
    assert session_state[supabase_auth.SESSION_AUTH_KEY]["first_name"] == "Alex"


def test_sign_out_clears_session(mock_streamlit, session_state: dict) -> None:
    session_state[supabase_auth.SESSION_AUTH_KEY] = {
        "access_token": "token",
        "refresh_token": "refresh",
        "user_id": "uid",
        "email": "a@b.com",
    }
    session_state["auth_token"] = "token"
    session_state["project_id"] = "proj-1"

    with patch.object(supabase_auth, "_anon_client") as mock_client_factory, patch(
        "services.session_project.clear_active_project"
    ) as mock_clear:
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        supabase_auth.sign_out()
        mock_clear.assert_called_once()

    assert supabase_auth.SESSION_AUTH_KEY not in session_state
    assert "auth_token" not in session_state
