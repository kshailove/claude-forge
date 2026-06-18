"""DigestRun and DigestEmail ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DigestRun(Base):
    __tablename__ = "digest_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_taken_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    emails: Mapped[list["DigestEmail"]] = relationship(
        "DigestEmail", back_populates="digest_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<DigestRun id={self.id} run_at={self.run_at} status={self.status!r}>"


class DigestEmail(Base):
    __tablename__ = "digest_emails"
    __table_args__ = (
        UniqueConstraint("user_id", "digest_run_id", name="uq_digest_emails_user_run"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    digest_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("digest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_scope: Mapped[str] = mapped_column(String(15), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    sendgrid_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    digest_run: Mapped["DigestRun"] = relationship("DigestRun", back_populates="emails")
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
