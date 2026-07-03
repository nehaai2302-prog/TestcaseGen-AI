"""Translate raw OpenAI/LLM failures into short, user-friendly messages.

Used by Streamlit pages so a missing, invalid, or expired ``OPENAI_API_KEY``
(or a quota / connectivity problem) shows a clear banner instead of a full
traceback in the UI and terminal.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

KEY_MISSING_MSG = (
    "⚠️ AI features aren't set up yet — no API key configured. "
    "Contact your **administrator or project owner**. You can still explore "
    "**Dashboard, Traceability, Bugs, and Demo**; **Generate, Import, and "
    "Library search** need a key."
)

KEY_INVALID_MSG = (
    "⚠️ AI features aren't available — the app's API key looks invalid or expired. "
    "If you're a guest, contact your **administrator or project owner**. You can "
    "still use **Dashboard, Traceability, Bugs, and Demo**; **Generate, Import, "
    "and Library search** need a working key."
)

QUOTA_MSG = (
    "⚠️ AI usage limit reached for this app. Try again later or contact your "
    "**administrator or project owner**. **Generate, Import, and Library search** "
    "may fail until this is resolved."
)

CONNECTION_MSG = (
    "🌐 Could not reach the AI service. Check your internet connection and try again."
)

GLOBAL_BANNER_MESSAGES = frozenset({KEY_MISSING_MSG, KEY_INVALID_MSG, QUOTA_MSG})

# Option C banner placement: main | sidebar | both (preview only for "both")
BANNER_STYLES = frozenset({"main", "sidebar", "both"})
DEFAULT_BANNER_STYLE = "sidebar"

_DEFAULT_PROBE_TTL_SECONDS = 300
_probe_cache: dict[str, tuple[float, str | None]] = {}


@dataclass(frozen=True)
class _ProbeResult:
    """Outcome of a live OpenAI probe."""

    banner_message: str | None
    verified: bool


def _probe_ttl_seconds() -> int:
    raw = (os.environ.get("OPENAI_KEY_PROBE_TTL_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_PROBE_TTL_SECONDS
    try:
        return max(0, int(raw))
    except ValueError:
        return _DEFAULT_PROBE_TTL_SECONDS


def openai_key_present() -> bool:
    """True if an OpenAI API key is set in the environment."""
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def clear_openai_key_probe_cache() -> None:
    """Clear cached key validation (for tests or after secret rotation)."""
    _probe_cache.clear()


def _default_embed_probe() -> None:
    """Minimal embedding call — same stack as requirement ingest / import."""
    from services.embeddings import get_embeddings_model

    get_embeddings_model().embed_query("ping")


def probe_openai_key(*, probe_call=_default_embed_probe) -> _ProbeResult:
    """Call OpenAI once; return a banner message for config/quota problems."""
    try:
        probe_call()
    except Exception as exc:
        msg = friendly_openai_error(exc)
        if msg in GLOBAL_BANNER_MESSAGES:
            return _ProbeResult(banner_message=msg, verified=False)
        return _ProbeResult(banner_message=None, verified=False)
    return _ProbeResult(banner_message=None, verified=True)


def resolve_openai_banner_message(
    *,
    force_refresh: bool = False,
    probe_call=_default_embed_probe,
) -> str | None:
    """Return a global banner message when the key is missing or unusable."""
    if not openai_key_present():
        return KEY_MISSING_MSG

    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    ttl = _probe_ttl_seconds()
    now = time.monotonic()
    if not force_refresh and ttl > 0:
        cached = _probe_cache.get(key)
        if cached is not None and now - cached[0] < ttl:
            return cached[1]

    result = probe_openai_key(probe_call=probe_call)
    if ttl > 0 and (result.verified or result.banner_message is not None):
        _probe_cache[key] = (now, result.banner_message)
    return result.banner_message


def openai_key_ready() -> bool:
    """True when the key is set and a live OpenAI probe succeeded."""
    return resolve_openai_banner_message() is None


def remember_openai_probe_failure(exc: BaseException) -> None:
    """Invalidate cache when a page action proves the key/config is bad."""
    msg = friendly_openai_error(exc)
    if msg not in GLOBAL_BANNER_MESSAGES:
        return
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if key:
        _probe_cache[key] = (time.monotonic(), msg)


def _iter_exception_chain(exc: BaseException):
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = cur.__cause__ or cur.__context__


def friendly_openai_error(exc: BaseException) -> str | None:
    """Return a friendly message if ``exc`` is an OpenAI key/quota/connection
    problem, else ``None`` so the caller can re-raise the original error.
    """
    for err in _iter_exception_chain(exc):
        name = type(err).__name__
        msg = str(err).lower()

        if name in ("AuthenticationError", "PermissionDeniedError"):
            return KEY_INVALID_MSG
        if name == "RateLimitError":
            return QUOTA_MSG
        if name in ("APIConnectionError", "APITimeoutError"):
            return CONNECTION_MSG

        if any(
            token in msg
            for token in (
                "incorrect api key",
                "invalid api key",
                "invalid_api_key",
                "expired",
                "unauthorized",
                "error code: 401",
            )
        ):
            return KEY_INVALID_MSG

        if (
            "openai_api_key" in msg
            or "api_key client option must be set" in msg
            or ("api key" in msg and "set" in msg)
            or "did not find openai_api_key" in msg
        ):
            return KEY_MISSING_MSG

        if "insufficient_quota" in msg or "exceeded your current quota" in msg:
            return QUOTA_MSG

    return None


def resolve_key_banner_placement(*, query_banner: str | None = None) -> str:
    """Placement for the global missing-key banner (Option C).

    ``?key_banner=main|sidebar|both`` overrides ``OPENAI_KEY_BANNER`` in the env.
    Use ``both`` only to compare layouts side by side in the running app.
    """
    if query_banner is not None:
        qp = query_banner.strip().lower()
    else:
        import streamlit as st  # noqa: PLC0415

        qp_raw = st.query_params.get("key_banner")
        qp = str(qp_raw).strip().lower() if qp_raw else ""
    if qp in BANNER_STYLES:
        return qp
    env = (os.environ.get("OPENAI_KEY_BANNER") or DEFAULT_BANNER_STYLE).strip().lower()
    return env if env in BANNER_STYLES else DEFAULT_BANNER_STYLE


def render_openai_key_banner(*, placement: str | None = None) -> None:
    """Show a non-blocking warning when the OpenAI key is missing or invalid."""
    msg = resolve_openai_banner_message()
    if not msg:
        return
    import streamlit as st  # noqa: PLC0415

    style = (placement or resolve_key_banner_placement()).strip().lower()
    if style not in BANNER_STYLES:
        style = DEFAULT_BANNER_STYLE
    if style in ("main", "both"):
        st.warning(msg)
    if style in ("sidebar", "both"):
        st.sidebar.warning(msg)
