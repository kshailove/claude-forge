"""SlackActivityBucket ORM model (TimescaleDB hypertable or partitioned table)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SlackActivityBucket(Base):
    """Hourly Slack message-count aggregates per user.

    Stored as a TimescaleDB hypertable on bucket_hour (Path A) or as a
    range-partitioned table by month (Path B). The DDL is managed in the
    Alembic migration; the ORM model maps to the same logical table in both cases.
    """

    __tablename__ = "slack_activity_buckets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    bucket_hour: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_after_hours: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=False)
    channel_count_distinct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
    team: Mapped["Team"] = relationship("Team", foreign_keys=[team_id])  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<SlackActivityBucket user_id={self.user_id} "
            f"bucket_hour={self.bucket_hour} count={self.message_count}>"
        )
