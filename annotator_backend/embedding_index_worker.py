"""Background job: embed ticket title+body for semantic search (pgvector)."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert

from annotator_backend.config import get_settings
from annotator_backend.embeddings import embed_texts, ticket_index_text
from db import models as db_models
from db import session as db_session

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_embedding_index_job(ticket_id: uuid.UUID) -> None:
    if db_session.SessionLocal is None:
        logger.warning("embedding_index_skip ticket_id=%s reason=no_session_factory", ticket_id)
        return

    settings = get_settings()
    db = db_session.SessionLocal()
    try:
        ticket = db.get(db_models.SupportTicket, ticket_id)
        if ticket is None:
            logger.warning("embedding_index_skip ticket_id=%s reason=ticket_not_found", ticket_id)
            return

        text = ticket_index_text(ticket.title, ticket.body)
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = db.get(db_models.TicketSearchEmbedding, ticket_id)
        if existing is not None and existing.content_hash == content_hash:
            logger.info("embedding_index_skip ticket_id=%s reason=unchanged_hash", ticket_id)
            return

        vectors = embed_texts([text], settings=settings)
        vec = vectors[0]
        if len(vec) != settings.openai_embedding_dimensions:
            logger.error(
                "embedding_index_failed ticket_id=%s reason=wrong_dim expected=%s got=%s",
                ticket_id,
                settings.openai_embedding_dimensions,
                len(vec),
            )
            return

        now = _utc_now()
        ins = insert(db_models.TicketSearchEmbedding).values(
            ticket_id=ticket_id,
            embedding=vec,
            model=settings.openai_embedding_model,
            content_hash=content_hash,
            updated_at=now,
        )
        ins = ins.on_conflict_do_update(
            index_elements=[db_models.TicketSearchEmbedding.ticket_id],
            set_={
                "embedding": ins.excluded.embedding,
                "model": ins.excluded.model,
                "content_hash": ins.excluded.content_hash,
                "updated_at": ins.excluded.updated_at,
            },
        )
        db.execute(ins)
        db.commit()
        logger.info("embedding_index_ok ticket_id=%s", ticket_id)
    except Exception:
        logger.exception("embedding_index_failed ticket_id=%s", ticket_id)
        db.rollback()
    finally:
        db.close()
