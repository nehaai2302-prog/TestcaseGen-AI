"""Shared LLM factory for agent nodes."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def get_chat_model() -> ChatOpenAI:
    model_name = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model_name, temperature=0.2)


def get_analyst_chat_model() -> ChatOpenAI:
    """Analyst-only model override (defaults to main chat model)."""
    model_name = os.getenv("OPENAI_ANALYST_MODEL") or os.getenv(
        "OPENAI_CHAT_MODEL", "gpt-4o-mini"
    )
    return ChatOpenAI(model=model_name, temperature=0.1)


def get_model_name() -> str:
    return os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
