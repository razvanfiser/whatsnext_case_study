"""Deterministic duplicate hash for support ticket content."""

from __future__ import annotations

import hashlib


def normalize_email(email: str) -> str:
    return email.strip().lower()


def content_duplicate_hash(email: str, title: str, body: str) -> str:
    norm = normalize_email(email)
    parts = (norm, title.strip(), body.strip())
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
