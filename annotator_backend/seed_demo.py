"""Load demo tickets with completed enrichments for manual testing (optional embeddings).

Usage (from repo root, venv active, DATABASE_URL set):

    python -m annotator_backend.seed_demo
    python -m annotator_backend.seed_demo --embeddings   # requires OPENAI_API_KEY; fills pgvector

Idempotent per ticket: skips inserts when duplicate_hash already exists. Safe to re-run with
--embeddings to backfill vectors after failures.
"""

from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from annotator_backend.config import get_settings
from annotator_backend.dedupe import content_duplicate_hash, normalize_email
from annotator_backend.embedding_index_worker import run_embedding_index_job
from db import models as db_models
from db import session as db_session
from db.session import configure_engine

_DEMO_NS = uuid.UUID("0193b00e-0000-7b3b-a000-000000000001")

# Titles/bodies match CASE_Razvan.md sample payloads; enrichments are hand-written for demos.
_SAMPLES: list[dict[str, str]] = [
    {
        "customer_email": "anna@example.com",
        "title": "Charged twice for October subscription",
        "body": (
            "Hi, I see two charges of €49 on my card from Oct 3. Please refund one. "
            "This is the second time this happens and I'm getting frustrated."
        ),
        "category": "billing",
        "priority": "high",
        "sentiment": "negative",
        "summary": (
            "Customer reports duplicate subscription charges and frustration while asking "
            "for a refund."
        ),
    },
    {
        "customer_email": "dev@startup.io",
        "title": "App crashes on PDF export",
        "body": (
            "Every time I try to export my project to PDF the app freezes completely and "
            "I lose unsaved work. I'm on v2.3.1, macOS 14.2. Happens 100% of the time with "
            "files over ~20 pages."
        ),
        "category": "bug",
        "priority": "high",
        "sentiment": "negative",
        "summary": (
            "Customer reports the application freezing and losing work when exporting "
            "large PDFs on macOS."
        ),
    },
    {
        "customer_email": "happy@customer.com",
        "title": "Love the new dashboard",
        "body": (
            "Just wanted to say the redesign is great. Much cleaner. Would be amazing to "
            "have dark mode though — my eyes will thank you."
        ),
        "category": "feature_request",
        "priority": "low",
        "sentiment": "positive",
        "summary": ("Customer praises the dashboard redesign and asks for an optional dark mode."),
    },
    {
        "customer_email": "locked.out@example.org",
        "title": "Can't log in",
        "body": (
            "Password reset email never arrives. Checked spam. Tried three times over the "
            "last hour. My account email is below."
        ),
        "category": "account",
        "priority": "medium",
        "sentiment": "negative",
        "summary": ("Customer cannot log in and reports password reset emails never arriving."),
    },
]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _deterministic_customer_id(email: str) -> uuid.UUID:
    return uuid.uuid5(_DEMO_NS, f"cust:{normalize_email(email)}")


def _deterministic_ticket_id(dup_hash: str) -> uuid.UUID:
    return uuid.uuid5(_DEMO_NS, f"ticket:{dup_hash}")


def _deterministic_enrichment_id(dup_hash: str) -> uuid.UUID:
    return uuid.uuid5(_DEMO_NS, f"enr:{dup_hash}")


def seed_rows(*, with_embeddings: bool) -> None:
    configure_engine(database_url=get_settings().database_url)
    if db_session.SessionLocal is None:
        raise RuntimeError("SessionLocal not configured")
    settings = get_settings()
    now = _utc_now()
    ticket_ids: list[uuid.UUID] = []

    db = db_session.SessionLocal()
    try:
        for row in _SAMPLES:
            dup = content_duplicate_hash(row["customer_email"], row["title"], row["body"])
            existing = db.scalar(
                select(db_models.SupportTicket).where(
                    db_models.SupportTicket.duplicate_hash == dup,
                ),
            )
            if existing is not None:
                ticket_ids.append(existing.id)
                print(f"skip insert (duplicate_hash exists): {row['title'][:50]!r}")
                continue

            norm = normalize_email(row["customer_email"])
            cust = db.scalar(
                select(db_models.Customer).where(db_models.Customer.email == norm),
            )
            if cust is None:
                cust_id_new = _deterministic_customer_id(row["customer_email"])
                cust = db_models.Customer(
                    id=cust_id_new,
                    email=norm,
                    full_name=None,
                    created_at=now,
                    updated_at=now,
                )
                db.add(cust)
                db.flush()
            cust_id = cust.id

            tid = _deterministic_ticket_id(dup)
            ticket = db_models.SupportTicket(
                id=tid,
                customer_id=cust_id,
                title=row["title"].strip(),
                body=row["body"].strip(),
                duplicate_hash=dup,
                created_at=now,
                updated_at=now,
            )
            db.add(ticket)
            db.add(
                db_models.TicketEnrichment(
                    id=_deterministic_enrichment_id(dup),
                    ticket_id=tid,
                    category=row["category"],
                    priority=row["priority"],
                    sentiment=row["sentiment"],
                    summary=row["summary"],
                    status="completed",
                    model=settings.openai_model,
                    prompt_version="2",
                    error_code=None,
                    retry_count=0,
                    last_attempt_at=now,
                    is_current=True,
                    created_at=now,
                    updated_at=now,
                ),
            )
            db.commit()
            ticket_ids.append(tid)
            print(f"inserted ticket {tid} ({row['title'][:40]!r}…)")

        if with_embeddings:
            for tid in ticket_ids:
                run_embedding_index_job(tid)
                print(f"embedding job finished for ticket_id={tid}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo tickets for manual testing.")
    parser.add_argument(
        "--embeddings",
        action="store_true",
        help="Call OpenAI and upsert pgvector rows (needs OPENAI_API_KEY)",
    )
    args = parser.parse_args()
    seed_rows(with_embeddings=args.embeddings)


if __name__ == "__main__":
    main()
