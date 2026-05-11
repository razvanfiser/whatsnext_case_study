"""Database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
SessionLocal: sessionmaker[Session] | None = None


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        msg = "DATABASE_URL is not set"
        raise RuntimeError(msg)
    return url


def configure_engine(*, database_url: str | None = None) -> None:
    global _engine, SessionLocal
    url = database_url or get_database_url()
    _engine = create_engine(url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        msg = "Database not configured; call configure_engine() at application startup"
        raise RuntimeError(msg)
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
