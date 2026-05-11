"""Pydantic schemas for API requests and responses."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TicketCreate(BaseModel):
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    customer_email: EmailStr


class TicketOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    title: str
    body: str
    customer_email: str
    category: str | None = None
    priority: str | None = None
    sentiment: str | None = None
    summary: str | None = None
    enrichment_status: str
    error_code: str | None = None
    inference_model: str | None = Field(default=None, serialization_alias="model")
    prompt_version: str | None = None
    created_at: datetime
    updated_at: datetime


class TicketListResponse(BaseModel):
    items: list[TicketOut]
    limit: int
    offset: int


class TicketSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class TicketSearchHit(TicketOut):
    distance: float


class TicketSearchResponse(BaseModel):
    items: list[TicketSearchHit]
