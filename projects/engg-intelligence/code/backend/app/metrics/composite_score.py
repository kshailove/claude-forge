"""Composite health score engine.

Computes a weighted composite score (0–100) from four component scores:
  - PR Health        (default 30%)
  - Sprint Health    (default 30%)
  - Incident Load    (default 25%)
  - Slack Signal     (default 15%)

When slack is degraded, its weight is redistributed proportionally to the
remaining components (spec §2.4).

Spec reference: §8 M4a
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import TeamMetricSnapshot
from app.models.team import TeamHealthConfig

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "pr_health": 0.30,
    "sprint_health": 0.30,
    "incident_load": 0.25,
    "slack_signal": 0.15,
}


# ---------------------------------------------------------------------------
# Pydantic v2 output model
# ---------------------------------------------------------------------------


class CompositeScore(BaseModel):
    """Composite health score for a team."""

    score: float  # 0–100
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
    computed_at: datetime = datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


async def compute_composite_score(
    team_id: UUID,
    db: AsyncSession,
) -> CompositeScore:
    """Compute and persist a composite health score for the given team.

    Steps:
    1. Load per-component weights from team_health_config (fall back to defaults).
    2. Load the most recent score for each component from team_metric_snapshots.
    3. If slack is degraded, exclude slack and redistribute its weight.
    4. Compute weighted sum (skip None scores with proportional weight redistribution).
    5. Derive RAG status.
    6. Write a 'composite' snapshot to team_metric_snapshots.
    7. Return CompositeScore.
    """
    now = datetime.now(tz=timezone.utc)

    # ---- 1. Load weights ----
    config_result = await db.execute(
        select(TeamHealthConfig).where(TeamHealthConfig.team_id == team_id)
    )
    config: TeamHealthConfig | None = config_result.scalar_one_or_none()

    if config is not None:
        weights = {
            "pr_health": float(config.weight_pr_health),
            "sprint_health": float(config.weight_sprint_health),
            "incident_load": float(config.weight_incident_load),
            "slack_signal": float(config.weight_slack_signal),
        }
    else:
        weights = dict(DEFAULT_WEIGHTS)

    # ---- 2. Determine if slack is degraded ----
    # Slack is considered degraded when no recent snapshot exists for it,
    # or when the integration config marks it degraded. For now we detect
    # degradation by absence of a recent slack_signal snapshot.
    slack_degraded = await _is_slack_degraded(team_id=team_id, db=db)

    # ---- 3. Load latest per-component scores ----
    components = ["pr_health", "sprint_health", "incident_load", "slack_signal"]
    latest_scores: dict[str, float | None] = {}

    for component in components:
        score = await _latest_component_score(
            team_id=team_id, component=component, db=db
        )
        latest_scores[component] = score

    if slack_degraded:
        latest_scores["slack_signal"] = None

    # ---- 4. Redistribute weights for missing / degraded components ----
    effective_weights = dict(weights)
    if slack_degraded:
        # Redistribute slack weight proportionally to remaining components
        slack_w = effective_weights.pop("slack_signal", 0.0)
        remaining_total = sum(effective_weights.values())
        if remaining_total > 0:
            for k in list(effective_weights.keys()):
                effective_weights[k] += slack_w * (effective_weights[k] / remaining_total)
        effective_weights["slack_signal"] = 0.0

    # Compute weighted sum with further redistribution for any None scores
    available: list[tuple[str, float, float]] = []  # (component, score, weight)
    missing_weight = 0.0
    for comp in components:
        w = effective_weights.get(comp, 0.0)
        s = latest_scores.get(comp)
        if s is None or w == 0.0:
            missing_weight += w
        else:
            available.append((comp, s, w))

    composite: float
    if not available:
        composite = 0.0
    else:
        available_total_w = sum(w for _, _, w in available)
        total_w = available_total_w + missing_weight  # missing gets redistributed
        # Proportionally boost available weights
        boosted = [(comp, s, w + missing_weight * (w / available_total_w)) for comp, s, w in available]
        composite = sum(s * w for _, s, w in boosted) / sum(w for _, _, w in boosted)

    composite = round(min(100.0, max(0.0, composite)), 2)
    rag = _rag_from_score(composite)

    # ---- 5. Write composite snapshot ----
    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="composite",
        score=Decimal(str(composite)),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "composite_score_computed",
        team_id=str(team_id),
        score=composite,
        rag=rag,
        slack_degraded=slack_degraded,
        pr=latest_scores.get("pr_health"),
        sprint=latest_scores.get("sprint_health"),
        incident=latest_scores.get("incident_load"),
        slack=latest_scores.get("slack_signal"),
    )

    return CompositeScore(
        score=composite,
        rag=rag,
        pr_health_score=latest_scores.get("pr_health"),
        sprint_health_score=latest_scores.get("sprint_health"),
        incident_load_score=latest_scores.get("incident_load"),
        slack_signal_score=latest_scores.get("slack_signal"),
        pr_health_weight=effective_weights.get("pr_health", weights["pr_health"]),
        sprint_health_weight=effective_weights.get("sprint_health", weights["sprint_health"]),
        incident_load_weight=effective_weights.get("incident_load", weights["incident_load"]),
        slack_signal_weight=effective_weights.get("slack_signal", weights["slack_signal"]),
        slack_degraded=slack_degraded,
        computed_at=now,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _latest_component_score(
    team_id: UUID,
    component: str,
    db: AsyncSession,
) -> float | None:
    """Return the most recent score for a component from team_metric_snapshots."""
    result = await db.execute(
        select(TeamMetricSnapshot.score)
        .where(
            and_(
                TeamMetricSnapshot.team_id == team_id,
                TeamMetricSnapshot.component == component,
            )
        )
        .order_by(TeamMetricSnapshot.snapshot_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    return float(row) if row is not None else None


async def _is_slack_degraded(team_id: UUID, db: AsyncSession) -> bool:
    """Return True when no slack_signal snapshot exists for the team.

    In production this would also check an integration config flag; for now
    we treat absence of any snapshot as degraded.
    """
    result = await db.execute(
        select(TeamMetricSnapshot.id)
        .where(
            and_(
                TeamMetricSnapshot.team_id == team_id,
                TeamMetricSnapshot.component == "slack_signal",
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is None


async def get_sparkline_7d(team_id: UUID, db: AsyncSession) -> list[float]:
    """Return the last 7 daily composite scores for sparkline display."""
    result = await db.execute(
        select(TeamMetricSnapshot.score, TeamMetricSnapshot.snapshot_at)
        .where(
            and_(
                TeamMetricSnapshot.team_id == team_id,
                TeamMetricSnapshot.component == "composite",
            )
        )
        .order_by(TeamMetricSnapshot.snapshot_at.desc())
        .limit(7)
    )
    rows = result.all()
    # Return in chronological order (oldest first)
    return [float(row.score) for row in reversed(rows)]


def _rag_from_score(score: float) -> Literal["red", "amber", "green"]:
    """red < 40, amber < 70, green >= 70."""
    if score >= 70.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"
