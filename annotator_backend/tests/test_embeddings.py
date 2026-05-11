"""Tests for annotator_backend.embeddings."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from annotator_backend.config import Settings
from annotator_backend.embeddings import embed_texts, ticket_index_text


class EmbeddingsTests(unittest.TestCase):
    def test_ticket_index_text_joins_and_strips(self) -> None:
        self.assertEqual(ticket_index_text(" Title ", " Body "), "Title\nBody")

    def test_embed_texts_empty_input(self) -> None:
        settings = Settings(
            database_url="postgresql://localhost/db",
            openai_api_key="test",
        )
        self.assertEqual(embed_texts([], settings=settings), [])

    def test_embed_texts_orders_response_by_index(self) -> None:
        settings = Settings(
            database_url="postgresql://localhost/db",
            openai_api_key="test",
        )
        row0 = MagicMock()
        row0.index = 0
        row0.embedding = [1.0, 0.0]
        row1 = MagicMock()
        row1.index = 1
        row1.embedding = [0.0, 2.0]
        resp = MagicMock()
        resp.data = [row1, row0]
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = resp

        with patch("annotator_backend.embeddings.OpenAI", return_value=fake_client):
            out = embed_texts(["a", "b"], settings=settings)

        self.assertEqual(out, [[1.0, 0.0], [0.0, 2.0]])
        fake_client.embeddings.create.assert_called_once()
        call_kw = fake_client.embeddings.create.call_args.kwargs
        self.assertEqual(call_kw["model"], settings.openai_embedding_model)
        self.assertEqual(call_kw["dimensions"], settings.openai_embedding_dimensions)
        self.assertEqual(call_kw["input"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
