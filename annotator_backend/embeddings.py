"""OpenAI text embeddings for semantic search (pgvector indexing)."""

from __future__ import annotations

from openai import OpenAI

from annotator_backend.config import Settings


def ticket_index_text(title: str, body: str) -> str:
    return f"{title.strip()}\n{body.strip()}"


def embed_texts(texts: list[str], *, settings: Settings) -> list[list[float]]:
    if not texts:
        return []
    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
    resp = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
        dimensions=settings.openai_embedding_dimensions,
    )
    rows = sorted(resp.data, key=lambda r: r.index)
    return [row.embedding for row in rows]


def embed_query(query: str, *, settings: Settings) -> list[float]:
    return embed_texts([query], settings=settings)[0]
