"""Pydantic v2 schemas for identity resolution and identity mapping endpoints.

Spec reference: §4.9 (Admin — Identity), §5.9 (Identity Resolver), M8a, M8b
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------


class ResolveResult(BaseModel):
    """Result returned by IdentityResolver.auto_resolve_all()."""

    tool: str
    resolved_count: int
    unresolved_count: int
    conflicts: list[str] = Field(
        default_factory=list,
        description="tool_user_ids that had ambiguous matches (multiple candidates).",
    )


# ---------------------------------------------------------------------------
# Unresolved mapping
# ---------------------------------------------------------------------------


class UnresolvedMapping(BaseModel):
    """A tool user that could not be auto-resolved to a canonical user."""

    tool: str
    tool_user_id: str
    tool_display_name: str | None = None
    tool_email: str | None = None


# ---------------------------------------------------------------------------
# Manual mapping request / response
# ---------------------------------------------------------------------------


class ManualMappingRequest(BaseModel):
    """POST /api/v1/admin/identity-mappings — create a manual identity mapping."""

    canonical_user_id: uuid.UUID = Field(
        ...,
        description="UUID of the canonical user in the users table.",
    )
    tool: str = Field(
        ...,
        description="Source tool identifier (github, jira, clickup, slack, pagerduty, zenduty, keka).",
    )
    tool_user_id: str = Field(
        ...,
        max_length=255,
        description="Tool-native user ID or login.",
    )
    tool_email: str | None = Field(
        default=None,
        max_length=255,
        description="Email address as known to the tool (optional, for reference).",
    )


class IdentityMappingResponse(BaseModel):
    """Serialised identity_mappings record returned from API endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_user_id: uuid.UUID
    tool: str
    tool_user_id: str
    tool_email: str | None
    resolution_method: str
    created_at: datetime
    updated_at: datetime


class IdentityMappingListResponse(BaseModel):
    """Paginated list of identity mappings."""

    mappings: list[IdentityMappingResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Unresolved-per-tool response
# ---------------------------------------------------------------------------


class UnresolvedByToolResponse(BaseModel):
    """GET /api/v1/admin/identity-mappings/unresolved response body."""

    github: list[UnresolvedMapping] = Field(default_factory=list)
    jira: list[UnresolvedMapping] = Field(default_factory=list)
    clickup: list[UnresolvedMapping] = Field(default_factory=list)
    slack: list[UnresolvedMapping] = Field(default_factory=list)
    pagerduty: list[UnresolvedMapping] = Field(default_factory=list)
    zenduty: list[UnresolvedMapping] = Field(default_factory=list)
    keka: list[UnresolvedMapping] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Auto-resolve trigger response
# ---------------------------------------------------------------------------


class AutoResolveJobResponse(BaseModel):
    """POST /api/v1/admin/identity-mappings/auto-resolve response body."""

    status: str
    task_id: str | None = None
    message: str
