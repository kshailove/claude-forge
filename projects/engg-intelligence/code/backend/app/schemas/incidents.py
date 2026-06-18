"""Pydantic v2 schemas for the Incidents API.

Spec reference: §8 M5b
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Incidents list
# ---------------------------------------------------------------------------


class IncidentListItem(BaseModel):
    """One row in the paginated incidents list."""

    id: UUID
    title: str
    severity: str
    service_name: str | None = None
    team_name: str | None = None
    triggered_at: datetime
    resolved_at: datetime | None = None
    mttr_seconds: float | None = None


class IncidentsListResponse(BaseModel):
    incidents: list[IncidentListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Incidents summary
# ---------------------------------------------------------------------------


class SeverityBreakdown(BaseModel):
    p1: int = Field(ge=0)
    p2: int = Field(ge=0)
    p3: int = Field(ge=0)
    p4: int = Field(ge=0)


class WorstIncident(BaseModel):
    id: UUID
    title: str
    severity: str
    mttr_seconds: float | None = None
    triggered_at: datetime


class CorrelationSignal(BaseModel):
    detected: bool
    description: str | None = None
    avg_lag_days: float | None = None


class IncidentsSummaryResponse(BaseModel):
    total_count: int = Field(ge=0)
    by_severity: SeverityBreakdown
    avg_mttr_seconds: float | None = None
    worst_mttr_incident: WorstIncident | None = None
    correlation_signal: CorrelationSignal
    window_days: int


# ---------------------------------------------------------------------------
# On-call load
# ---------------------------------------------------------------------------


class EngineerOncallLoad(BaseModel):
    user_id: UUID
    name: str
    on_call_hours: float = Field(ge=0)
    pages_received: int = Field(ge=0)
    team_name: str | None = None


class OncallLoadResponse(BaseModel):
    engineers: list[EngineerOncallLoad]
    gini_coefficient: float | None = None  # fairness score 0=perfectly fair, 1=all load on one
    window_days: int


# ---------------------------------------------------------------------------
# By-service breakdown
# ---------------------------------------------------------------------------


class ServiceIncidentStats(BaseModel):
    service_name: str
    incident_count: int = Field(ge=0)
    p1_count: int = Field(ge=0)
    avg_mttr_seconds: float | None = None
    repeat_count: int = Field(ge=0)  # count of services with >= 3 incidents


class IncidentsByServiceResponse(BaseModel):
    services: list[ServiceIncidentStats]
    window_days: int


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TimelineDay(BaseModel):
    date: str  # "YYYY-MM-DD"
    count: int = Field(ge=0)
    p1_count: int = Field(ge=0)


class IncidentsTimelineResponse(BaseModel):
    timeline: list[TimelineDay]
    window_days: int
