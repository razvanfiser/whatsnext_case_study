"""Ticket HTTP API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from annotator_backend.config import get_settings
from annotator_backend.dedupe import content_duplicate_hash, normalize_email
from annotator_backend.embedding_index_worker import run_embedding_index_job
from annotator_backend.enrichment_worker import run_enrichment_job
from annotator_backend.schemas import (
    TicketCreate,
    TicketListResponse,
    TicketOut,
    TicketSearchHit,
    TicketSearchRequest,
    TicketSearchResponse,
)
from db.models import Customer, SupportTicket, TicketEnrichment, TicketSearchEmbedding
from db.session import get_db

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_db)]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _current_enrichment(session: Session, ticket_id: uuid.UUID) -> TicketEnrichment | None:
    return session.scalar(
        select(TicketEnrichment).where(
            TicketEnrichment.ticket_id == ticket_id,
            TicketEnrichment.is_current.is_(True),
        )
    )


def _ticket_to_out(
    *,
    ticket: SupportTicket,
    customer: Customer,
    enrichment: TicketEnrichment | None,
) -> TicketOut:
    if enrichment is None:
        return TicketOut(
            id=ticket.id,
            title=ticket.title,
            body=ticket.body,
            customer_email=customer.email,
            enrichment_status="pending",
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )
    return TicketOut(
        id=ticket.id,
        title=ticket.title,
        body=ticket.body,
        customer_email=customer.email,
        category=enrichment.category,
        priority=enrichment.priority,
        sentiment=enrichment.sentiment,
        summary=enrichment.summary,
        enrichment_status=enrichment.status,
        error_code=enrichment.error_code,
        inference_model=enrichment.model,
        prompt_version=enrichment.prompt_version,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _parse_since(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


@router.post("/tickets")
def create_ticket(
    payload: TicketCreate,
    db: SessionDep,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    dup_hash = content_duplicate_hash(
        payload.customer_email,
        payload.title,
        payload.body,
    )

    existing = db.scalar(
        select(SupportTicket)
        .where(SupportTicket.duplicate_hash == dup_hash)
        .options(joinedload(SupportTicket.customer)),
    )
    if existing is not None and existing.customer is not None:
        enr = _current_enrichment(db, existing.id)
        out = _ticket_to_out(ticket=existing, customer=existing.customer, enrichment=enr)
        return JSONResponse(
            status_code=200,
            content=out.model_dump(mode="json", by_alias=True),
        )

    norm_email = normalize_email(str(payload.customer_email))
    now = utc_now()

    cust_stmt = (
        pg_insert(Customer)
        .values(email=norm_email, full_name=None, created_at=now, updated_at=now)
        .on_conflict_do_update(index_elements=["email"], set_={"updated_at": now})
        .returning(Customer.id)
    )
    customer_id = db.execute(cust_stmt).scalar_one()

    ticket = SupportTicket(
        customer_id=customer_id,
        title=payload.title.strip(),
        body=payload.body.strip(),
        duplicate_hash=dup_hash,
        created_at=now,
        updated_at=now,
    )

    enrichment = TicketEnrichment(
        ticket=ticket,
        status="pending",
        is_current=True,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.add(enrichment)

    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        db.expunge(ticket)
        db.expunge(enrichment)
        existing2 = db.scalar(
            select(SupportTicket)
            .where(SupportTicket.duplicate_hash == dup_hash)
            .options(joinedload(SupportTicket.customer)),
        )
        if existing2 is None or existing2.customer is None:
            raise
        enr2 = _current_enrichment(db, existing2.id)
        out2 = _ticket_to_out(ticket=existing2, customer=existing2.customer, enrichment=enr2)
        return JSONResponse(status_code=200, content=out2.model_dump(mode="json", by_alias=True))

    # Persist before scheduling enrichment: BackgroundTasks can run before get_db's
    # post-yield commit, so a new session in the worker would not see this row yet.
    db.commit()
    background_tasks.add_task(run_enrichment_job, ticket.id)
    background_tasks.add_task(run_embedding_index_job, ticket.id)

    db.refresh(ticket)
    customer = db.get(Customer, ticket.customer_id)
    if customer is None:
        raise HTTPException(status_code=500, detail="customer missing for ticket")
    db.refresh(enrichment)
    out3 = _ticket_to_out(ticket=ticket, customer=customer, enrichment=enrichment)
    return JSONResponse(status_code=201, content=out3.model_dump(mode="json", by_alias=True))


@router.get("/tickets", response_model=TicketListResponse)
def list_tickets(
    db: SessionDep,
    category: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TicketListResponse:
    since_dt = _parse_since(since)
    stmt = (
        select(SupportTicket, Customer, TicketEnrichment)
        .join(Customer, Customer.id == SupportTicket.customer_id)
        .join(
            TicketEnrichment,
            (TicketEnrichment.ticket_id == SupportTicket.id)
            & (TicketEnrichment.is_current.is_(True)),
        )
        .order_by(SupportTicket.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if since_dt is not None:
        stmt = stmt.where(SupportTicket.created_at >= since_dt)
    if category is not None:
        stmt = stmt.where(TicketEnrichment.category == category)
    if priority is not None:
        stmt = stmt.where(TicketEnrichment.priority == priority)

    rows = db.execute(stmt).all()
    items = [_ticket_to_out(ticket=t, customer=c, enrichment=e) for t, c, e in rows]
    return TicketListResponse(items=items, limit=limit, offset=offset)


@router.post("/tickets/search", response_model=TicketSearchResponse)
def search_tickets(
    payload: TicketSearchRequest,
    db: SessionDep,
) -> TicketSearchResponse:
    from annotator_backend.embeddings import embed_query

    settings = get_settings()
    try:
        qvec = embed_query(payload.query.strip(), settings=settings)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="embedding provider unavailable",
        ) from None

    dist_expr = TicketSearchEmbedding.embedding.cosine_distance(qvec)
    stmt = (
        select(SupportTicket, Customer, TicketEnrichment, dist_expr.label("dist"))
        .select_from(TicketSearchEmbedding)
        .join(SupportTicket, SupportTicket.id == TicketSearchEmbedding.ticket_id)
        .join(Customer, Customer.id == SupportTicket.customer_id)
        .outerjoin(
            TicketEnrichment,
            (TicketEnrichment.ticket_id == SupportTicket.id)
            & (TicketEnrichment.is_current.is_(True)),
        )
        .order_by(dist_expr)
        .limit(payload.limit)
    )
    rows = db.execute(stmt).all()
    items: list[TicketSearchHit] = []
    for t, c, e, dist in rows:
        out = _ticket_to_out(ticket=t, customer=c, enrichment=e)
        items.append(
            TicketSearchHit.model_validate(
                {**out.model_dump(), "distance": float(dist)},
            )
        )
    return TicketSearchResponse(items=items)


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: uuid.UUID, db: SessionDep) -> TicketOut:
    ticket = db.scalar(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(joinedload(SupportTicket.customer)),
    )
    if ticket is None or ticket.customer is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    enr = _current_enrichment(db, ticket.id)
    return _ticket_to_out(ticket=ticket, customer=ticket.customer, enrichment=enr)
