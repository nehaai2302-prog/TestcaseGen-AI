"""Tests for OpenAI error message helpers."""

from __future__ import annotations

from services.openai_errors import (
    KEY_INVALID_MSG,
    KEY_MISSING_MSG,
    QUOTA_MSG,
    clear_openai_key_probe_cache,
    friendly_openai_error,
    openai_key_present,
    openai_key_ready,
    probe_openai_key,
    remember_openai_probe_failure,
    resolve_key_banner_placement,
    resolve_openai_banner_message,
)


class _FakeAuthError(Exception):
    pass


class _FakeRateLimitError(Exception):
    pass


class _FakeTypeError(Exception):
    pass


def test_openai_key_present(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert openai_key_present() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert openai_key_present() is True
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    assert openai_key_present() is False


def test_friendly_openai_error_missing_key_message():
    exc = RuntimeError("Did not find openai_api_key, please add an API key.")
    assert friendly_openai_error(exc) == KEY_MISSING_MSG


def test_friendly_openai_error_invalid_key_message():
    exc = _FakeAuthError("Error code: 401 - Incorrect API key provided")
    assert friendly_openai_error(exc) == KEY_INVALID_MSG


def test_friendly_openai_error_quota_message():
    exc = RuntimeError("You exceeded your current quota, please check your plan.")
    assert friendly_openai_error(exc) == QUOTA_MSG


def test_friendly_openai_error_unknown_returns_none():
    assert friendly_openai_error(ValueError("something else")) is None


def test_resolve_key_banner_placement_env(monkeypatch):
    monkeypatch.delenv("OPENAI_KEY_BANNER", raising=False)
    assert resolve_key_banner_placement(query_banner="") == "sidebar"
    monkeypatch.setenv("OPENAI_KEY_BANNER", "main")
    assert resolve_key_banner_placement(query_banner="") == "main"


def test_resolve_key_banner_placement_query_override():
    assert resolve_key_banner_placement(query_banner="both") == "both"
    assert resolve_key_banner_placement(query_banner="main") == "main"


def test_resolve_openai_banner_message_missing(monkeypatch):
    clear_openai_key_probe_cache()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_openai_banner_message() == KEY_MISSING_MSG
    assert openai_key_ready() is False


def test_resolve_openai_banner_message_valid(monkeypatch):
    clear_openai_key_probe_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-valid")
    monkeypatch.setenv("OPENAI_KEY_PROBE_TTL_SECONDS", "300")

    def _ok_probe():
        return None

    assert resolve_openai_banner_message(probe_call=_ok_probe) is None
    assert openai_key_ready() is True


def test_resolve_openai_banner_message_invalid(monkeypatch):
    clear_openai_key_probe_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    monkeypatch.setenv("OPENAI_KEY_PROBE_TTL_SECONDS", "300")

    def _auth_fail_probe():
        raise _FakeAuthError("Error code: 401 - Incorrect API key provided")

    assert resolve_openai_banner_message(probe_call=_auth_fail_probe) == KEY_INVALID_MSG
    assert openai_key_ready() is False


def test_probe_openai_key_quota_is_global_banner(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-quota")

    def _quota_probe():
        raise _FakeRateLimitError("You exceeded your current quota, please check your plan.")

    result = probe_openai_key(probe_call=_quota_probe)
    assert result.banner_message == QUOTA_MSG
    assert result.verified is False


def test_probe_openai_key_typeerror_is_not_verified():
    """Regression: models.list(limit=1) TypeError must not count as a valid key."""

    def _broken_probe():
        raise _FakeTypeError("Models.list() got an unexpected keyword argument 'limit'")

    result = probe_openai_key(probe_call=_broken_probe)
    assert result.banner_message is None
    assert result.verified is False


def test_resolve_openai_banner_message_uses_cache(monkeypatch):
    clear_openai_key_probe_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-cached")
    monkeypatch.setenv("OPENAI_KEY_PROBE_TTL_SECONDS", "300")
    calls = {"n": 0}

    def _counting_probe():
        calls["n"] += 1

    factory = _counting_probe
    assert resolve_openai_banner_message(probe_call=factory) is None
    assert resolve_openai_banner_message(probe_call=factory) is None
    assert calls["n"] == 1


def test_remember_openai_probe_failure_updates_cache(monkeypatch):
    clear_openai_key_probe_cache()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    monkeypatch.setenv("OPENAI_KEY_PROBE_TTL_SECONDS", "300")

    def _ok_probe():
        return None

    assert resolve_openai_banner_message(probe_call=_ok_probe) is None
    remember_openai_probe_failure(
        _FakeAuthError("Error code: 401 - Incorrect API key provided")
    )
    assert resolve_openai_banner_message(probe_call=_ok_probe) == KEY_INVALID_MSG
