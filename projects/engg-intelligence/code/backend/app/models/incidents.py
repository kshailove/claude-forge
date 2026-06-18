"""Incident, IncidentAssignment, OncallSchedule, OncallShift ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Incident(Base):
    __tablename__ = "incidents"

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
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(5), nullable=False)
    service_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mtta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mttr_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    integration: Mapped["Integration"] = relationship("Integration")  # type: ignore[name-defined]
    team: Mapped["Team"] = relationship("Team")  # type: ignore[name-defined]
    assignments: Mapped[list["IncidentAssignment"]] = relationship(
        "IncidentAssignment", back_populates="incident", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Incident {self.external_id!r} severity={self.severity!r}>"


class IncidentAssignment(Base):
    __tablename__ = "incident_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped["Incident"] = relationship("Incident", back_populates="assignments")
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]


class OncallSchedule(Base):
    __tablename__ = "oncall_schedules"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "external_id", name="uq_oncall_schedules_integration_external"
        ),
    )

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
    )
    schedule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    integration: Mapped["Integration"] = relationship("Integration")  # type: ignore[name-defined]
    shifts: Mapped[list["OncallShift"]] = relationship(
        "OncallShift", back_populates="schedule", cascade="all, delete-orphan"
    )


class OncallShift(Base):
    __tablename__ = "oncall_shifts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("oncall_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    schedule: Mapped["OncallSchedule"] = relationship("OncallSchedule", back_populates="shifts")
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
