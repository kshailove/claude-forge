"""Pydantic v2 schemas for the Overview API.

Spec reference: §8 M4b
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TeamHealthCard(BaseModel):
    """Health summary card for a single team."""

    team_id: UUID
    team_name: str
    composite_score: float = Field(ge=0, le=100)
    rag: Literal["red", "amber", "green"]
    open_pr_count: int = Field(ge=0)
    sprint_completion_pct: float | None = Field(default=None, ge=0, le=100)
    active_incident_count: int = Field(ge=0)
    sparkline_7d: list[float] = Field(default_factory=list)


class OverviewResponse(BaseModel):
    """Response envelope for GET /api/v1/overview."""

    teams: list[TeamHealthCard]
    total: int
