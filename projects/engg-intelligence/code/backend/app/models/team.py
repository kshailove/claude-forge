"""Team, TeamMembership and OrgNode ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    em_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    em: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[em_user_id]
    )
    members: Mapped[list["User"]] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys="User.team_id", back_populates="team"
    )
    memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership", back_populates="team", cascade="all, delete-orphan"
    )
    health_config: Mapped["TeamHealthConfig | None"] = relationship(  # type: ignore[name-defined]
        "TeamHealthConfig", back_populates="team", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} slug={self.slug!r}>"


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "team_id", name="uq_team_memberships_user_team"),
    )

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
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    team: Mapped["Team"] = relationship("Team", back_populates="memberships")


class OrgNode(Base):
    __tablename__ = "org_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    employee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    employee: Mapped["User"] = relationship("User", foreign_keys=[employee_user_id])  # type: ignore[name-defined]
    manager: Mapped["User | None"] = relationship("User", foreign_keys=[manager_user_id])  # type: ignore[name-defined]


class TeamHealthConfig(Base):
    __tablename__ = "team_health_config"

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
        unique=True,
    )
    weight_pr_health: Mapped[float] = mapped_column(nullable=False, default=0.300)
    weight_sprint_health: Mapped[float] = mapped_column(nullable=False, default=0.300)
    weight_incident_load: Mapped[float] = mapped_column(nullable=False, default=0.250)
    weight_slack_signal: Mapped[float] = mapped_column(nullable=False, default=0.150)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("users.id"),
        nullable=False,
    )

    team: Mapped["Team"] = relationship("Team", back_populates="health_config")
    updater: Mapped["User"] = relationship("User", foreign_keys=[updated_by])  # type: ignore[name-defined]
