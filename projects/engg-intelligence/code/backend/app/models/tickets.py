"""Sprint, Ticket, and TicketStateTransition ORM models (Jira/ClickUp)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Sprint(Base):
    __tablename__ = "sprints"
    __table_args__ = (
        UniqueConstraint("integration_id", "external_id", name="uq_sprints_integration_external"),
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
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
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
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="sprint"
    )

    def __repr__(self) -> str:
        return f"<Sprint id={self.id} name={self.name!r} state={self.state!r}>"


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint(
            "integration_id", "external_id", name="uq_tickets_integration_external"
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
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sprint_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("sprints.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    story_points: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    ticket_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    integration: Mapped["Integration"] = relationship("Integration")  # type: ignore[name-defined]
    assignee: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[assignee_user_id]
    )
    sprint: Mapped["Sprint | None"] = relationship("Sprint", back_populates="tickets")
    team: Mapped["Team"] = relationship("Team")  # type: ignore[name-defined]
    state_transitions: Mapped[list["TicketStateTransition"]] = relationship(
        "TicketStateTransition", back_populates="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Ticket {self.external_id!r} status={self.status!r}>"


class TicketStateTransition(Base):
    __tablename__ = "ticket_state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    to_state: Mapped[str] = mapped_column(String(100), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="state_transitions")
