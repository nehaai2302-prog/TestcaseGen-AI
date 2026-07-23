"""Tests for generation/analyst model selection helpers."""

from __future__ import annotations

from agent.llm import (
    get_analyst_model_name,
    get_generation_model_name,
    get_model_name,
)


def test_generation_model_prefers_generation_override(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-model")
    monkeypatch.setenv("OPENAI_GENERATION_MODEL", "generation-model")
    assert get_generation_model_name() == "generation-model"
    assert get_model_name() == "generation-model"


def test_generation_model_falls_back_to_chat_model(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_GENERATION_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-model")
    assert get_generation_model_name() == "chat-model"


def test_analyst_model_prefers_analyst_override(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "chat-model")
    monkeypatch.setenv("OPENAI_ANALYST_MODEL", "analyst-model")
    assert get_analyst_model_name() == "analyst-model"

