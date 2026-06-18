"""Pydantic v2 schemas for the Teams API.

Spec reference: §8 M4c
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class MemberLoadIndicator(BaseModel):
    """Load summary for a single team member."""

    user_id: UUID
    username: str
    email: str
    open_pr_count: int = Field(ge=0)
    on_call_hours_7d: float = Field(ge=0)
    active_incident_count: int = Field(ge=0)
    role: str


# ---------------------------------------------------------------------------
# Teams list
# ---------------------------------------------------------------------------


class TeamSummary(BaseModel):
    """Brief team record for the teams list endpoint."""

    team_id: UUID
    team_name: str
    slug: str
    composite_score: float | None = Field(default=None, ge=0, le=100)
    rag: Literal["red", "amber", "green"] | None = None
    em_username: str | None = None
    member_count: int = Field(ge=0)


class TeamsListResponse(BaseModel):
    teams: list[TeamSummary]
    total: int


# ---------------------------------------------------------------------------
# Team detail
# ---------------------------------------------------------------------------


class CompositeScoreDetail(BaseModel):
    score: float
    rag: Literal["red", "amber", "green"]
    pr_health_score: float | None
    sprint_health_score: float | None
    incident_load_score: float | None
    slack_signal_score: float | None
    pr_health_weight: float
    sprint_health_weight: float
    incident_load_weight: float
    slack_signal_weight: float
    slack_degraded: bool


class DORAMetricsSummary(BaseModel):
    deployment_frequency: int
    deployment_frequency_per_day: float
    deployment_frequency_band: str
    lead_time_for_changes_seconds: float | None
    lead_time_band: str
    change_failure_rate_pct: float | None
    change_failure_rate_band: str
    mttr_seconds: float | None
    mttr_band: str
    window_days: int
    computed_at: datetime


class TeamDetailResponse(BaseModel):
    team_id: UUID
    team_name: str
    slug: str
    composite: CompositeScoreDetail
    dora: DORAMetricsSummary | None
    members: list[MemberLoadIndicator]
    member_count: int


# ---------------------------------------------------------------------------
# PR Health detail
# ---------------------------------------------------------------------------


class StalePR(BaseModel):
    title: str
    url: str
    days_stale: float
    author: str


class PRHealthDetailResponse(BaseModel):
    team_id: UUID
    score: float | None
    rag: Literal["red", "amber", "green"] | None
    # Core metrics
    avg_cycle_time_seconds: float | None
    p50_cycle_time_seconds: float | None
    p95_cycle_time_seconds: float | None
    avg_first_review_latency_seconds: float | None
    p50_first_review_latency_seconds: float | None
    stale_pr_count: int
    review_coverage_pct: float | None
    review_participation_pct: float | None
    rework_rate_pct: float | None
    merged_pr_count: int
    open_pr_count: int
    window_days: int
    # Drill-down
    stale_prs: list[StalePR] = Field(default_factory=list)


class StalePRListResponse(BaseModel):
    team_id: UUID
    stale_prs: list[StalePR]
    total: int


# ---------------------------------------------------------------------------
# Sprint Health detail
# ---------------------------------------------------------------------------


class SprintHealthDetailResponse(BaseModel):
    team_id: UUID
    score: float | None
    rag: Literal["red", "amber", "green"] | None
    current_sprint_name: str | None
    current_sprint_id: str | None
    current_sprint_completion_pct: float | None
    scope_creep_pct: float | None
    carry_over_rate_pct: float | None
    blocked_ticket_count: int
    blocked_avg_age_days: float | None
    velocity_trend_points: list[float]
    sprint_commitment_rate_pct: float | None
    wip_count: int
    flow_distribution: dict[str, float]
    setup_required: bool


# ---------------------------------------------------------------------------
# Incident Load detail
# ---------------------------------------------------------------------------


class RepeatServiceItem(BaseModel):
    service_name: str
    count: int


class IncidentItem(BaseModel):
    id: UUID
    title: str
    severity: str
    triggered_at: datetime
    resolved_at: datetime | None
    mttr_seconds: float | None
    service_name: str | None


class IncidentLoadDetailResponse(BaseModel):
    team_id: UUID
    score: float | None
    rag: Literal["red", "amber", "green"] | None
    incident_count: int
    p1_count: int
    p2_count: int
    p3_count: int
    p4_count: int
    avg_mttr_seconds: float | None
    p50_mttr_seconds: float | None
    p95_mttr_seconds: float | None
    avg_mtta_seconds: float | None
    incidents_per_week: float
    repeat_services: list[RepeatServiceItem]
    window_days: int
    recent_incidents: list[IncidentItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Slack Signal detail
# ---------------------------------------------------------------------------


class SlackSignalDetailResponse(BaseModel):
    team_id: UUID
    degraded: bool
    reason: str | None = None
    score: float | None = None
    rag: Literal["red", "amber", "green"] | None = None


# ---------------------------------------------------------------------------
# Team Members
# ---------------------------------------------------------------------------


class TeamMembersResponse(BaseModel):
    team_id: UUID
    members: list[MemberLoadIndicator]
    total: int
