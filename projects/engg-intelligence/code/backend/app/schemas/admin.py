"""Admin API request/response schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class CreateUserRequest(BaseModel):
    """POST /api/v1/admin/users request body."""

    email: str = Field(..., max_length=255)
    username: str = Field(..., max_length=100)
    password: str = Field(..., min_length=8, description="Initial plaintext password")
    role: str = Field(..., description="One of: admin, director, em, engineer")
    team_id: uuid.UUID | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"admin", "director", "em", "engineer"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return v


class UpdateUserRequest(BaseModel):
    """PUT /api/v1/admin/users/{id} request body."""

    email: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=100)
    role: str | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"admin", "director", "em", "engineer"}
        if v not in allowed:
            raise ValueError(f"role must be one of {sorted(allowed)}")
        return v


class UserDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    role: str
    team_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    users: list[UserDetail]
    total: int


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


class CreateTeamRequest(BaseModel):
    """POST /api/v1/admin/teams request body."""

    name: str = Field(..., max_length=255)
    slug: str = Field(
        ..., max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe identifier e.g. 'platform-team'"
    )
    em_user_id: uuid.UUID | None = None


class UpdateTeamRequest(BaseModel):
    """PUT /api/v1/admin/teams/{id} request body."""

    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(
        default=None, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    em_user_id: uuid.UUID | None = None


class TeamDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    em_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class TeamListResponse(BaseModel):
    teams: list[TeamDetail]
    total: int


# ---------------------------------------------------------------------------
# Org Tree
# ---------------------------------------------------------------------------


class OrgTreeNode(BaseModel):
    """A single employee → manager edge in the org tree."""

    employee_user_id: uuid.UUID
    manager_user_id: uuid.UUID | None = None


class OrgTreeRequest(BaseModel):
    """PUT /api/v1/admin/org-tree request body (bulk replace manual source)."""

    nodes: list[OrgTreeNode] = Field(..., min_length=0)


class OrgTreeNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_user_id: uuid.UUID
    manager_user_id: uuid.UUID | None
    source: str


class OrgTreeResponse(BaseModel):
    source: str
    last_keka_sync_at: datetime | None
    nodes: list[OrgTreeNodeResponse]


# ---------------------------------------------------------------------------
# Nightly Runs
# ---------------------------------------------------------------------------


class NightlyRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scheduled_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    status: str
    integrations_completed: dict
    metric_computation_status: str
    error_summary: str | None
    created_at: datetime


class NightlyRunListResponse(BaseModel):
    runs: list[NightlyRunResponse]


class TriggerNightlyRunResponse(BaseModel):
    run_id: uuid.UUID
    message: str


# ---------------------------------------------------------------------------
# Health Config
# ---------------------------------------------------------------------------


class TeamHealthConfigUpdate(BaseModel):
    """PUT /api/v1/admin/teams/{id}/health-config request body."""

    weight_pr_health: float = Field(..., ge=0.0, le=1.0)
    weight_sprint_health: float = Field(..., ge=0.0, le=1.0)
    weight_incident_load: float = Field(..., ge=0.0, le=1.0)
    weight_slack_signal: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def weights_must_sum_to_one(self) -> "TeamHealthConfigUpdate":
        total = (
            self.weight_pr_health
            + self.weight_sprint_health
            + self.weight_incident_load
            + self.weight_slack_signal
        )
        if abs(total - 1.0) >= 0.001:
            raise ValueError(
                f"The four weights must sum to exactly 1.0 (got {total:.4f}). "
                "Adjust weights so they sum to 1.000."
            )
        return self
