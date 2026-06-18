"""Digests API router.

Endpoints:
  GET /api/v1/digests           — list past digests for the authenticated user
  GET /api/v1/digests/preview   — preview of next Monday's digest (not stored)
  GET /api/v1/digests/{digest_id} — get full rendered HTML for one digest

RBAC: every user sees only their own digests.

Spec §8 M7c.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import CurrentUser, get_current_user
from app.digest.generator import DigestGenerator
from app.models.digest import DigestEmail
from app.schemas.digests import (
    DigestDetailResponse,
    DigestListResponse,
    DigestPreviewResponse,
    DigestSummary,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/digests", tags=["digests"])

_generator = DigestGenerator()


# ---------------------------------------------------------------------------
# GET /api/v1/digests
# ---------------------------------------------------------------------------


@router.get("", response_model=DigestListResponse)
async def list_digests(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DigestListResponse:
    """List all past digest emails for the authenticated user.

    Returns entries ordered most-recent first.
    Each user sees only their own digests (RBAC enforced by user_id filter).
    """
    result = await db.execute(
        select(DigestEmail)
        .where(DigestEmail.user_id == current_user.id)
        .order_by(DigestEmail.created_at.desc())
    )
    emails: list[DigestEmail] = list(result.scalars().all())

    summaries = [_to_summary(e) for e in emails]
    return DigestListResponse(digests=summaries, total=len(summaries))


# ---------------------------------------------------------------------------
# GET /api/v1/digests/preview  — must come BEFORE /{digest_id} in the router
# ---------------------------------------------------------------------------


@router.get("/preview", response_model=DigestPreviewResponse)
async def preview_digest(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DigestPreviewResponse:
    """Generate a live preview of next Monday's digest without storing it.

    Calls DigestGenerator.preview_for_user() which renders the same role-scoped
    HTML as the Monday send but does NOT persist to digest_emails.
    """
    html = await _generator.preview_for_user(
        user_id=str(current_user.id),
        db=db,
    )

    return DigestPreviewResponse(
        html_content=html,
        generated_at=datetime.now(tz=timezone.utc),
        role_scope=current_user.role,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/digests/{digest_id}
# ---------------------------------------------------------------------------


@router.get("/{digest_id}", response_model=DigestDetailResponse)
async def get_digest(
    digest_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DigestDetailResponse:
    """Return the full rendered HTML for one past digest.

    Users can only access their own digests — returns 404 for other users'
    digests to avoid leaking existence information.
    """
    result = await db.execute(
        select(DigestEmail).where(
            and_(
                DigestEmail.id == digest_id,
                DigestEmail.user_id == current_user.id,
            )
        )
    )
    digest_email: DigestEmail | None = result.scalar_one_or_none()
    if digest_email is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    subject = _build_subject(digest_email)

    return DigestDetailResponse(
        digest_id=digest_email.id,
        digest_run_id=digest_email.digest_run_id,
        html_content=digest_email.html_content,
        sent_at=digest_email.sent_at,
        subject=subject,
        delivery_status=digest_email.delivery_status,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_subject(e: DigestEmail) -> str:
    """Construct a display subject from sent_at or created_at."""
    ts = e.sent_at or e.created_at
    return f"Engineering Weekly — {ts.strftime('%b %d, %Y')}"


def _to_summary(e: DigestEmail) -> DigestSummary:
    """Convert a DigestEmail ORM row to a DigestSummary schema."""
    subject = _build_subject(e)

    # Extract a plain-text preview from html_content (first 120 chars of visible text)
    preview_text = _extract_preview(e.html_content)

    return DigestSummary(
        digest_id=e.id,
        digest_run_id=e.digest_run_id,
        sent_at=e.sent_at,
        subject=subject,
        preview_text=preview_text,
        delivery_status=e.delivery_status,
    )


def _extract_preview(html: str, max_len: int = 120) -> str:
    """Cheap tag-strip for preview text — no external deps."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len] + ("…" if len(text) > max_len else "")
