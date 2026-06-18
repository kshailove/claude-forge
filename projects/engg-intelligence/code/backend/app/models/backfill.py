"""BackfillJob ORM model for tracking historical data backfill progress.

Spec reference: §3.11 (backfill_jobs table)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BackfillJob(Base):
    """Tracks progress of a historical data backfill task.

    One row per backfill request. Celery worker updates ``records_processed``
    and ``last_checkpoint`` as it processes each repo/PR batch.
    """

    __tablename__ = "backfill_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalised for query convenience — avoids a join when listing jobs
    integration_type: Mapped[str] = mapped_column(String(30), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(15), nullable=False, default="pending"
    )  # pending | running | completed | failed
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Last processed record ID for resumability: e.g. "org/repo:1847"
    last_checkpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    integration: Mapped["Integration"] = relationship("Integration")  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<BackfillJob id={self.id} type={self.integration_type!r} "
            f"status={self.status!r} processed={self.records_processed}>"
        )
