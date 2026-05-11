"""HTTP and LLM enrichment service package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["app"]


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        from annotator_backend.main import app as fastapi_app

        return fastapi_app
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
