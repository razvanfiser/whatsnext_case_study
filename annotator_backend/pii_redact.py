"""Best-effort regex redaction for text sent to the LLM only (DB/API stay raw).

Email addresses are intentionally not modified — see README / notes.
"""

from __future__ import annotations

import re

REDACTED_SSN = "[REDACTED_SSN]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_CREDIT_CARD = "[REDACTED_CREDIT_CARD]"
REDACTED_API_KEY = "[REDACTED_API_KEY]"

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# OpenAI-style secret
_SK_KEY = re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")

# HTTP bearer token in prose (paste into ticket)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b", re.IGNORECASE)

# US-centric; international formats may slip through — acceptable for a take-home.
_US_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?" r"\(?\d{3}\)?" r"[-.\s]?" r"\d{3}" r"[-.\s]?" r"\d{4}(?!\d)"
)

# 13–19 digits with optional single separators between digits (best effort; may false-positive).
_CC_LIKE = re.compile(r"(?<!\d)(?:\d[- ]?){12,18}\d(?!\d)")


def redact_for_llm(text: str) -> str:
    """Return a copy of ``text`` with obvious high-risk patterns replaced by fixed tokens.

    Does not redact email addresses (support triage context).
    """
    if not text:
        return text
    out = text
    out = _SSN.sub(REDACTED_SSN, out)
    out = _SK_KEY.sub(REDACTED_API_KEY, out)
    out = _BEARER.sub(REDACTED_API_KEY, out)
    out = _US_PHONE.sub(REDACTED_PHONE, out)
    out = _CC_LIKE.sub(REDACTED_CREDIT_CARD, out)
    return out
