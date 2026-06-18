"""NightlyRun ORM model — tracks nightly batch pipeline execution."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NightlyRun(Base):
    """One row per nightly batch execution.

    Status flow:
        pending → running → completed | partial | failed

    ``integrations_completed`` is a JSONB dict tracking per-integration success:
        {"github": true, "jira": false, "pagerduty": true, "slack": true, "keka": true}
    """

    __tablename__ = "nightly_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="pending")
    integrations_completed: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metric_computation_status: Mapped[str] = mapped_column(
        String(15), nullable=False, default="pending"
    )
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def mark_integration_complete(self, integration_type: str, success: bool = True) -> None:
        """Update the JSONB dict for a specific integration's completion status."""
        if self.integrations_completed is None:
            self.integrations_completed = {}
        # JSONB column needs assignment (not in-place mutation) for SQLAlchemy to detect change
        updated = dict(self.integrations_completed)
        updated[integration_type] = success
        self.integrations_completed = updated

    def compute_status(self) -> str:
        """Derive the overall run status from integration completion flags."""
        if not self.integrations_completed:
            return "failed"
        all_done = all(self.integrations_completed.values())
        any_done = any(self.integrations_completed.values())
        if all_done:
            return "completed"
        if any_done:
            return "partial"
        return "failed"

    def __repr__(self) -> str:
        return (
            f"<NightlyRun id={self.id} "
            f"scheduled_at={self.scheduled_at} status={self.status!r}>"
        )
