"""Pydantic v2 schemas for the Engineers API.

Spec reference: §8 M5a
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Engineers list
# ---------------------------------------------------------------------------


class EngineerSummary(BaseModel):
    """One row in the engineers list table."""

    user_id: UUID
    name: str
    email: str
    role: str
    team_name: str | None = None
    composite_load_indicator: str  # "high" | "medium" | "low"
    pr_authored_30d: int = Field(ge=0)
    pr_merged_30d: int = Field(ge=0)
    tickets_closed_30d: int = Field(ge=0)
    incidents_paged_30d: int = Field(ge=0)


class EngineersListResponse(BaseModel):
    engineers: list[EngineerSummary]
    total: int


# ---------------------------------------------------------------------------
# Engineer detail
# ---------------------------------------------------------------------------


class CodeActivity(BaseModel):
    prs_authored: int = Field(ge=0)
    prs_merged: int = Field(ge=0)
    avg_cycle_time_seconds: float | None = None
    pr_size_trend: list[float] = Field(default_factory=list)


class ReviewActivity(BaseModel):
    prs_reviewed: int = Field(ge=0)
    avg_first_review_latency_seconds: float | None = None
    avg_review_depth: float | None = None  # avg comments per review


class TaskDelivery(BaseModel):
    tickets_closed: int = Field(ge=0)
    avg_ticket_cycle_time_seconds: float | None = None
    carry_over_count: int = Field(ge=0)


class IncidentLoad(BaseModel):
    pages_received: int = Field(ge=0)
    personal_avg_mttr_seconds: float | None = None
    on_call_hours: float = Field(ge=0)


class ReviewPartner(BaseModel):
    user_id: UUID
    name: str
    review_count: int = Field(ge=0)


class Collaboration(BaseModel):
    top_review_partners: list[ReviewPartner] = Field(default_factory=list)


class EngineerDetailResponse(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str
    team_name: str | None = None
    code_activity: CodeActivity
    review_activity: ReviewActivity
    task_delivery: TaskDelivery
    incident_load: IncidentLoad
    collaboration: Collaboration
