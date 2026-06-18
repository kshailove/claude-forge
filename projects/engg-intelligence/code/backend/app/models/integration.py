"""Integration and IdentityMapping ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy import Uuid as UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.encryption import decrypt_config, encrypt_config


class Integration(Base):
    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    # config_json stores AES-256-GCM encrypted JSON blob
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="disconnected")
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    team: Mapped["Team | None"] = relationship("Team")  # type: ignore[name-defined]

    # ------------------------------------------------------------------
    # Encryption helpers — never return raw config_json from the API
    # ------------------------------------------------------------------

    def get_config(self) -> dict:
        """Decrypt and return the integration config as a dict."""
        return decrypt_config(self.config_json)

    def set_config(self, config: dict) -> None:
        """Encrypt and store an integration config dict."""
        self.config_json = encrypt_config(config)

    def get_config_summary(self) -> dict:
        """Return a safe subset of the config (no secrets) for API responses."""
        config = self.get_config()
        safe_fields = {
            "github": ["org_name", "release_tag_pattern"],
            "jira": ["base_url", "email", "project_keys", "story_points_field_id", "board_ids"],
            "clickup": ["workspace_id", "sprint_list_ids", "story_points_custom_field_name"],
            "pagerduty": ["service_ids", "team_ids"],
            "zenduty": ["base_url", "team_unique_ids"],
            "slack": ["slack_signal_degraded"],
            "keka": ["base_url"],
        }
        allowed = safe_fields.get(self.type, [])
        return {k: v for k, v in config.items() if k in allowed}

    def __repr__(self) -> str:
        return f"<Integration id={self.id} type={self.type!r} status={self.status!r}>"


class IdentityMapping(Base):
    __tablename__ = "identity_mappings"
    __table_args__ = (
        UniqueConstraint("tool", "tool_user_id", name="uq_identity_tool_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    canonical_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_method: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    canonical_user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
