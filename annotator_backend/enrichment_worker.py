"""Background enrichment: LLM call in a fresh DB session with bounded retries."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from annotator_backend.config import get_settings
from annotator_backend.llm import (
    PROMPT_VERSION,
    EnrichmentError,
    TransientEnrichmentError,
    enrich_ticket,
)
from db import models as db_models
from db import session as db_session

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
_DETAIL_MAX_LEN = 200


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _truncate_detail(text: str, max_len: int = _DETAIL_MAX_LEN) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _phase(ticket_id: uuid.UUID, phase: str, enrichment_id: uuid.UUID | None = None) -> None:
    if enrichment_id is not None:
        logger.info(
            "enrichment_phase ticket_id=%s enrichment_id=%s phase=%s",
            ticket_id,
            enrichment_id,
            phase,
        )
    else:
        logger.info("enrichment_phase ticket_id=%s phase=%s", ticket_id, phase)


def run_enrichment_job(ticket_id: uuid.UUID) -> None:
    job_outcome = "aborted"
    db = None

    if db_session.SessionLocal is None:
        logger.error("enrichment_skip ticket_id=%s reason=no_session_factory", ticket_id)
        job_outcome = "skip_no_session"
        logger.info("enrichment_job_finished ticket_id=%s outcome=%s", ticket_id, job_outcome)
        return

    settings = get_settings()
    db = db_session.SessionLocal()
    logger.info("enrichment_job_started ticket_id=%s", ticket_id)

    try:
        ticket = db.get(db_models.SupportTicket, ticket_id)
        if ticket is None:
            logger.warning("enrichment_skip ticket_id=%s reason=ticket_not_found", ticket_id)
            job_outcome = "skip_ticket_not_found"
            return

        _phase(ticket_id, "loaded_ticket")

        enrichment = db.scalar(
            select(db_models.TicketEnrichment).where(
                db_models.TicketEnrichment.ticket_id == ticket_id,
                db_models.TicketEnrichment.is_current.is_(True),
            )
        )
        if enrichment is None:
            logger.warning(
                "enrichment_skip ticket_id=%s reason=no_current_enrichment",
                ticket_id,
            )
            job_outcome = "skip_no_enrichment"
            return

        _phase(ticket_id, "loaded_enrichment", enrichment.id)

        if enrichment.status in ("completed", "failed"):
            logger.info(
                "enrichment_skip ticket_id=%s enrichment_id=%s reason=terminal_status status=%s",
                ticket_id,
                enrichment.id,
                enrichment.status,
            )
            job_outcome = f"skip_terminal_{enrichment.status}"
            return

        logger.info(
            "enrichment_run_begin ticket_id=%s enrichment_id=%s prior_status=%s",
            ticket_id,
            enrichment.id,
            enrichment.status,
        )

        enrichment.status = "processing"
        enrichment.updated_at = _utc_now()
        db.commit()

        _phase(ticket_id, "status_processing_persisted", enrichment.id)

        for attempt in range(MAX_ATTEMPTS):
            db.refresh(ticket)
            db.refresh(enrichment)
            logger.info(
                "enrichment_attempt_begin ticket_id=%s enrichment_id=%s attempt=%s max=%s",
                ticket_id,
                enrichment.id,
                attempt + 1,
                MAX_ATTEMPTS,
            )
            _phase(ticket_id, "llm_call_begin", enrichment.id)
            try:
                result = enrich_ticket(
                    title=ticket.title,
                    body=ticket.body,
                    settings=settings,
                )
            except TransientEnrichmentError as e:
                _phase(ticket_id, "llm_call_transient_error", enrichment.id)
                detail = _truncate_detail(str(e))
                logger.warning(
                    "enrichment_transient ticket_id=%s enrichment_id=%s attempt=%s detail=%s",
                    ticket_id,
                    enrichment.id,
                    attempt + 1,
                    detail,
                )
                enrichment.retry_count += 1
                enrichment.last_attempt_at = _utc_now()
                enrichment.updated_at = _utc_now()
                db.commit()
                if attempt < MAX_ATTEMPTS - 1:
                    backoff = 2**attempt
                    logger.debug(
                        "enrichment_backoff ticket_id=%s seconds=%s",
                        ticket_id,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
                enrichment.status = "failed"
                enrichment.error_code = "provider_timeout"
                enrichment.model = settings.openai_model
                enrichment.prompt_version = PROMPT_VERSION
                enrichment.updated_at = _utc_now()
                db.commit()
                logger.error(
                    "enrichment_failed ticket_id=%s enrichment_id=%s error_code=provider_timeout",
                    ticket_id,
                    enrichment.id,
                )
                _phase(ticket_id, "persist_failed_timeout", enrichment.id)
                job_outcome = "failed_provider_timeout"
                return
            except EnrichmentError as e:
                _phase(ticket_id, "llm_call_validation_error", enrichment.id)
                detail = _truncate_detail(str(e))
                logger.warning(
                    "enrichment_failed ticket_id=%s enrichment_id=%s error_code=%s detail=%s",
                    ticket_id,
                    enrichment.id,
                    e.code,
                    detail,
                )
                enrichment.status = "failed"
                enrichment.error_code = e.code
                enrichment.last_attempt_at = _utc_now()
                enrichment.model = settings.openai_model
                enrichment.prompt_version = PROMPT_VERSION
                enrichment.updated_at = _utc_now()
                db.commit()
                _phase(ticket_id, "persist_failed_enrichment_error", enrichment.id)
                job_outcome = "failed_enrichment_error"
                return
            else:
                _phase(ticket_id, "llm_call_success", enrichment.id)
                enrichment.status = "completed"
                enrichment.category = result.category
                enrichment.priority = result.priority
                enrichment.sentiment = result.sentiment
                enrichment.summary = result.summary
                enrichment.last_attempt_at = _utc_now()
                enrichment.model = settings.openai_model
                enrichment.prompt_version = PROMPT_VERSION
                enrichment.updated_at = _utc_now()
                enrichment.error_code = None
                db.commit()
                _phase(ticket_id, "persist_completed", enrichment.id)
                logger.info(
                    "enrichment_completed ticket_id=%s enrichment_id=%s category=%s "
                    "priority=%s sentiment=%s",
                    ticket_id,
                    enrichment.id,
                    result.category,
                    result.priority,
                    result.sentiment,
                )
                job_outcome = "completed"
                return
    except Exception:
        job_outcome = "unexpected_error"
        logger.exception(
            "enrichment_unexpected ticket_id=%s",
            ticket_id,
        )
        db.rollback()
        raise
    finally:
        if db is not None:
            db.close()
        logger.info("enrichment_job_finished ticket_id=%s outcome=%s", ticket_id, job_outcome)
