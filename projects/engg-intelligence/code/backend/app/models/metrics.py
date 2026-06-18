"""TeamMetricSnapshot and EngineerMetricSnapshot ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TeamMetricSnapshot(Base):
    """Nightly team health score snapshot.

    Path A: TimescaleDB hypertable on snapshot_at (1-day chunks).
    Path B: range-partitioned by month.
    Both paths share this ORM model.
    """

    __tablename__ = "team_metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    component: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    rag: Mapped[str] = mapped_column(String(6), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    team: Mapped["Team"] = relationship("Team")  # type: ignore[name-defined]

    @property
    def score_float(self) -> float:
        return float(self.score)

    def __repr__(self) -> str:
        return (
            f"<TeamMetricSnapshot team_id={self.team_id} "
            f"component={self.component!r} score={self.score} rag={self.rag!r}>"
        )


class EngineerMetricSnapshot(Base):
    """Nightly per-engineer metric snapshots.

    Path A: TimescaleDB hypertable on snapshot_at (1-week chunks).
    Path B: range-partitioned by month.
    """

    __tablename__ = "engineer_metric_snapshots"

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
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
    team: Mapped["Team"] = relationship("Team", foreign_keys=[team_id])  # type: ignore[name-defined]

    def __repr__(self) -> str:
        return (
            f"<EngineerMetricSnapshot user_id={self.user_id} "
            f"metric={self.metric_key!r} value={self.metric_value}>"
        )
