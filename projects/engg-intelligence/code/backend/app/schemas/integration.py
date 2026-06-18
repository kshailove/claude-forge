"""Pydantic v2 schemas for Integration API endpoints (M1a+).

Spec reference: §4.7, §3.11
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# GitHub connect
# ---------------------------------------------------------------------------


class GitHubConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/github/connect request body."""

    personal_access_token: str = Field(
        ...,
        min_length=1,
        description="GitHub Personal Access Token with 'repo' scope.",
    )
    org_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="GitHub organisation name (e.g. 'myorg').",
    )
    release_tag_pattern: str = Field(
        default=".*",
        max_length=500,
        description="Regex pattern to filter release tags (e.g. 'v[0-9]+\\.[0-9]+\\.[0-9]+').",
    )

    @field_validator("release_tag_pattern")
    @classmethod
    def validate_tag_pattern(cls, v: str) -> str:
        import re
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"release_tag_pattern is not a valid regex: {exc}") from exc
        return v


# ---------------------------------------------------------------------------
# Integration response
# ---------------------------------------------------------------------------


class IntegrationConfigSummary(BaseModel):
    """Non-sensitive config fields safe to return in API responses."""

    org_name: str | None = None
    release_tag_pattern: str | None = None
    token_expires_at: datetime | None = None


class IntegrationResponse(BaseModel):
    """Response shape for a single integration record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    status: str
    team_id: uuid.UUID | None
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    config_summary: dict = Field(default_factory=dict)


class IntegrationListResponse(BaseModel):
    integrations: list[IntegrationResponse]


class GitHubStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/github/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    org_name: str | None
    release_tag_pattern: str | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# PagerDuty connect
# ---------------------------------------------------------------------------


class PagerDutyConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/pagerduty/connect request body."""

    api_key: str = Field(
        ...,
        min_length=1,
        description="PagerDuty API token (REST API key, not OAuth).",
    )
    service_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of PagerDuty service IDs to filter. "
            "Empty list or None = ingest all services."
        ),
    )


class PagerDutyStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/pagerduty/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    service_ids: list[str] | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Zenduty connect
# ---------------------------------------------------------------------------


class ZendutyConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/zenduty/connect request body."""

    api_key: str = Field(
        ...,
        min_length=1,
        description="Zenduty API key.",
    )
    base_url: str = Field(
        default="https://www.zenduty.com/api/v1",
        description=(
            "Zenduty API base URL. Overridable in case of rebranding "
            "(spec Decision 3)."
        ),
    )
    team_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of Zenduty team unique IDs to filter. "
            "Empty or None = sync all teams."
        ),
    )


class ZendutyStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/zenduty/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    base_url: str | None
    team_ids: list[str] | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Incident backfill
# ---------------------------------------------------------------------------


class IncidentBackfillRequest(BaseModel):
    """POST /api/v1/admin/integrations/{provider}/backfill request body."""

    from_date: date = Field(..., description="Backfill start date (ISO 8601).")
    to_date: date = Field(..., description="Backfill end date (ISO 8601, inclusive).")

    @field_validator("to_date")
    @classmethod
    def to_date_after_from_date(cls, v: date, info) -> date:
        from_date = info.data.get("from_date")
        if from_date is not None and v < from_date:
            raise ValueError("to_date must be on or after from_date")
        return v


class BackfillRequest(BaseModel):
    """POST /api/v1/admin/integrations/github/backfill request body."""

    from_date: date = Field(..., description="Backfill start date (ISO 8601 date string).")
    to_date: date = Field(..., description="Backfill end date (ISO 8601 date string, inclusive).")
    team_id: uuid.UUID | None = Field(
        default=None,
        description="If provided, backfill only repos belonging to this team.",
    )

    @field_validator("to_date")
    @classmethod
    def to_date_after_from_date(cls, v: date, info) -> date:
        from_date = info.data.get("from_date")
        if from_date is not None and v < from_date:
            raise ValueError("to_date must be on or after from_date")
        return v


class BackfillJobResponse(BaseModel):
    """Response for POST /api/v1/admin/integrations/github/backfill."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    integration_id: uuid.UUID
    integration_type: str
    date_from: date
    date_to: date
    status: str
    records_processed: int
    records_total: int | None
    last_checkpoint: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime

    @property
    def progress_pct(self) -> float | None:
        if self.records_total and self.records_total > 0:
            return round(self.records_processed / self.records_total * 100, 1)
        return None


class BackfillJobListResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/backfill."""

    jobs: list[BackfillJobResponse]
    total: int


class BackfillStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/backfill/{job_id}."""

    backfill_job_id: uuid.UUID
    status: str
    records_processed: int
    records_total: int | None
    progress_pct: float | None
    last_checkpoint: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


# ---------------------------------------------------------------------------
# Jira connect (M2a)
# ---------------------------------------------------------------------------


class JiraConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/jira/connect request body."""

    base_url: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Jira Cloud base URL, e.g. 'https://mycompany.atlassian.net'.",
    )
    email: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Atlassian account email associated with the API token.",
    )
    api_token: str = Field(
        ...,
        min_length=1,
        description="Jira Cloud API token (from id.atlassian.com/manage-profile/security/api-tokens).",
    )
    project_keys: list[str] = Field(
        default_factory=list,
        description="List of Jira project keys to ingest, e.g. ['PROJ', 'ENG'].",
    )
    team_id: uuid.UUID | None = Field(
        default=None,
        description="Optional team UUID to associate with this integration.",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")


class JiraStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/jira/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    base_url: str | None
    project_keys: list[str] | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# ClickUp connect + configure (M2b)
# ---------------------------------------------------------------------------


class ClickUpConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/clickup/connect request body."""

    api_token: str = Field(
        ...,
        min_length=1,
        description="ClickUp personal API token (starts with pk_).",
    )
    workspace_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="ClickUp workspace (team) ID.",
    )
    team_id: uuid.UUID | None = Field(
        default=None,
        description="Optional internal team UUID to associate with this integration.",
    )


class ClickUpConfigureSprintsRequest(BaseModel):
    """POST /api/v1/admin/integrations/clickup/configure-sprints request body."""

    sprint_list_ids: dict[str, list[str]] = Field(
        ...,
        description=(
            "Mapping of internal team UUID → list of ClickUp List IDs that represent "
            "sprint backlogs. Example: {'<team_uuid>': ['12345', '67890']}"
        ),
    )


class ClickUpStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/clickup/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    workspace_id: str | None
    sprint_list_ids: dict | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Slack connect (M6a)
# ---------------------------------------------------------------------------


class SlackConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/slack/connect request body."""

    bot_token: str = Field(
        ...,
        min_length=1,
        description=(
            "Slack bot OAuth token (starts with xoxb-). "
            "Required scopes: channels:history, channels:read, groups:history, "
            "groups:read, users:read, team:read"
        ),
    )
    signing_secret: str = Field(
        ...,
        min_length=1,
        description="Slack app signing secret for request verification.",
    )

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v.startswith("xoxb-"):
            raise ValueError("bot_token must start with 'xoxb-' (Slack bot token)")
        return v


class SlackConnectResponse(BaseModel):
    """Response for POST /api/v1/admin/integrations/slack/connect."""

    connected: bool
    degraded: bool
    reason: str | None = None
    integration_id: uuid.UUID | None = None
    workspace_name: str | None = None
    workspace_id: str | None = None


class SlackStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/slack/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    degraded: bool
    degraded_reason: str | None
    workspace_id: str | None
    integration_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Keka HRMS connect (M8c)
# ---------------------------------------------------------------------------


class KekaConnectRequest(BaseModel):
    """POST /api/v1/admin/integrations/keka/connect request body."""

    client_id: str = Field(
        ...,
        min_length=1,
        description="Keka OAuth2 client ID.",
    )
    client_secret: str = Field(
        ...,
        min_length=1,
        description="Keka OAuth2 client secret.",
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Keka tenant ID (used in token endpoint URL: "
            "https://{tenant_id}.keka.com/connect/token)."
        ),
    )
    base_url: str = Field(
        default="https://api.keka.com/v1",
        description="Keka API base URL. Defaults to https://api.keka.com/v1.",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v.rstrip("/")


class KekaStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/integrations/keka/status."""

    connected: bool
    status: str
    last_synced_at: datetime | None
    tenant_id: str | None
    base_url: str | None
    integration_id: uuid.UUID | None


class KekaDisconnectRequest(BaseModel):
    """DELETE /api/v1/admin/integrations/keka request body."""

    keep_keka_snapshot: bool = Field(
        default=True,
        description=(
            "If True, keep the last Keka org snapshot in org_nodes. "
            "If False, delete all Keka org_nodes (admin will need to re-enter manual org tree)."
        ),
    )
