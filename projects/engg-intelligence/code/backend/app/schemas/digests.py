"""Pydantic v2 schemas for the Digests API endpoints.

Spec §8 M7c.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DigestSummary(BaseModel):
    """One digest entry in the list view."""

    model_config = ConfigDict(from_attributes=True)

    digest_id: UUID
    digest_run_id: UUID
    sent_at: datetime | None
    subject: str
    preview_text: str
    delivery_status: str


class DigestListResponse(BaseModel):
    """Response for GET /api/v1/digests."""

    digests: list[DigestSummary]
    total: int


class DigestDetailResponse(BaseModel):
    """Response for GET /api/v1/digests/{digest_id}."""

    digest_id: UUID
    digest_run_id: UUID
    html_content: str
    sent_at: datetime | None
    subject: str
    delivery_status: str


class DigestPreviewResponse(BaseModel):
    """Response for GET /api/v1/digests/preview — next Monday's digest preview."""

    html_content: str
    generated_at: datetime
    role_scope: str
