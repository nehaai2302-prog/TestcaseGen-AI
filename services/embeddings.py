"""OpenAI embedding wrapper."""

from __future__ import annotations

import os

from langchain_openai import OpenAIEmbeddings


def get_embeddings_model() -> OpenAIEmbeddings:
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return OpenAIEmbeddings(model=model)


async def aembed_texts(model: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await model.aembed_documents(texts)


def embed_texts(model: OpenAIEmbeddings, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return model.embed_documents(texts)


def embed_query(model: OpenAIEmbeddings, text: str) -> list[float]:
    return model.embed_query(text)
