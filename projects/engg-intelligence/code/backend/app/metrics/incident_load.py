"""Incident Load metric computation engine.

Computes incident volume, MTTR/MTTA percentiles, on-call fairness, and repeat
services for a team within a rolling time window. Also produces the Incident
Load score (0–100, high = low load).

Spec reference: §5.6, §8 M3c
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incidents import Incident, IncidentAssignment, OncallSchedule, OncallShift
from app.models.metrics import TeamMetricSnapshot

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic v2 metrics model
# ---------------------------------------------------------------------------


class RepeatService(BaseModel):
    """A service that triggered ≥3 incidents in the window."""

    service_name: str
    count: int


class IncidentLoadMetrics(BaseModel):
    """All computed Incident Load metrics for a team within the window."""

    # Counts
    incident_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    p3_count: int = 0
    p4_count: int = 0

    # MTTR (seconds) — only for resolved incidents
    avg_mttr_seconds: float | None = None
    p50_mttr_seconds: float | None = None
    p95_mttr_seconds: float | None = None

    # MTTA (seconds) — time to acknowledge
    avg_mtta_seconds: float | None = None
    p50_mtta_seconds: float | None = None

    # Rate
    incidents_per_week: float = 0.0

    # Repeat offenders: services with ≥3 incidents
    repeat_services: list[RepeatService] = Field(default_factory=list)

    # Paging distribution: {user_id_str: page_count}
    paging_distribution: dict[str, int] = Field(default_factory=dict)

    # On-call hours per engineer: {user_id_str: hours}
    on_call_hours_per_engineer: dict[str, float] = Field(default_factory=dict)

    # Window
    window_days: int = 30
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


async def compute_incident_load(
    team_id: UUID,
    db: AsyncSession,
    window_days: int = 30,
) -> IncidentLoadMetrics:
    """Compute all Incident Load metrics for a team within the rolling window.

    Args:
        team_id: Team UUID.
        db: Async SQLAlchemy session.
        window_days: Rolling window in days (default 30).

    Returns:
        IncidentLoadMetrics with all computed fields populated.
    """
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=window_days)

    # ---- Fetch all incidents in window for this team ----
    incidents_result = await db.execute(
        select(Incident).where(
            and_(
                Incident.team_id == team_id,
                Incident.triggered_at >= window_start,
                Incident.triggered_at <= now,
            )
        )
    )
    incidents = incidents_result.scalars().all()

    # ---- Severity counts ----
    incident_count = len(incidents)
    p1_count = sum(1 for i in incidents if i.severity == "p1")
    p2_count = sum(1 for i in incidents if i.severity == "p2")
    p3_count = sum(1 for i in incidents if i.severity == "p3")
    p4_count = sum(1 for i in incidents if i.severity == "p4")

    # ---- MTTR ----
    mttr_values = [
        float(i.mttr_seconds)
        for i in incidents
        if i.mttr_seconds is not None and i.mttr_seconds >= 0
    ]
    avg_mttr = _safe_mean(mttr_values)
    p50_mttr = _safe_percentile(mttr_values, 50)
    p95_mttr = _safe_percentile(mttr_values, 95)

    # ---- MTTA ----
    mtta_values = [
        float(i.mtta_seconds)
        for i in incidents
        if i.mtta_seconds is not None and i.mtta_seconds >= 0
    ]
    avg_mtta = _safe_mean(mtta_values)
    p50_mtta = _safe_percentile(mtta_values, 50)

    # ---- Rate ----
    incidents_per_week = incident_count / (window_days / 7) if window_days > 0 else 0.0

    # ---- Repeat services (≥3 incidents in window) ----
    service_counts: dict[str, int] = {}
    for inc in incidents:
        if inc.service_name:
            service_counts[inc.service_name] = service_counts.get(inc.service_name, 0) + 1

    repeat_services = [
        RepeatService(service_name=svc, count=cnt)
        for svc, cnt in sorted(service_counts.items(), key=lambda x: -x[1])
        if cnt >= 3
    ]

    # ---- Paging distribution ----
    # Fetch incident assignments for incidents in this window
    if incidents:
        incident_ids = [i.id for i in incidents]
        assignments_result = await db.execute(
            select(IncidentAssignment).where(
                IncidentAssignment.incident_id.in_(incident_ids)
            )
        )
        assignments = assignments_result.scalars().all()
    else:
        assignments = []

    paging_distribution: dict[str, int] = {}
    for assignment in assignments:
        if assignment.user_id is not None:
            uid_str = str(assignment.user_id)
            paging_distribution[uid_str] = paging_distribution.get(uid_str, 0) + 1

    # ---- On-call hours per engineer from oncall_shifts in window ----
    on_call_hours: dict[str, float] = {}

    # Get all schedules for integrations associated with this team's incidents
    # We join through OncallSchedule → OncallShift for the team's integration
    if incidents:
        # Get integration_ids used for this team's incidents
        integration_ids = list({i.integration_id for i in incidents})

        schedules_result = await db.execute(
            select(OncallSchedule).where(
                OncallSchedule.integration_id.in_(integration_ids)
            )
        )
        schedules = schedules_result.scalars().all()
        schedule_ids = [s.id for s in schedules]

        if schedule_ids:
            shifts_result = await db.execute(
                select(OncallShift).where(
                    and_(
                        OncallShift.schedule_id.in_(schedule_ids),
                        OncallShift.start_at >= window_start,
                        OncallShift.start_at <= now,
                    )
                )
            )
            shifts = shifts_result.scalars().all()

            for shift in shifts:
                if shift.user_id is not None:
                    uid_str = str(shift.user_id)
                    # Clamp shift to window
                    shift_start = max(shift.start_at, window_start)
                    shift_end = min(shift.end_at, now)
                    if shift_end > shift_start:
                        hours = (shift_end - shift_start).total_seconds() / 3600
                        on_call_hours[uid_str] = on_call_hours.get(uid_str, 0.0) + hours

    return IncidentLoadMetrics(
        incident_count=incident_count,
        p1_count=p1_count,
        p2_count=p2_count,
        p3_count=p3_count,
        p4_count=p4_count,
        avg_mttr_seconds=avg_mttr,
        p50_mttr_seconds=p50_mttr,
        p95_mttr_seconds=p95_mttr,
        avg_mtta_seconds=avg_mtta,
        p50_mtta_seconds=p50_mtta,
        incidents_per_week=round(incidents_per_week, 2),
        repeat_services=repeat_services,
        paging_distribution=paging_distribution,
        on_call_hours_per_engineer=on_call_hours,
        window_days=window_days,
    )


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def compute_incident_load_score(metrics: IncidentLoadMetrics) -> float:
    """Compute overall Incident Load score (0–100, high = low load).

    Weights (spec §M3c):
      - incidents_per_week : 35%
      - avg_mttr           : 35%
      - p1_count           : 20%
      - paging_gini        : 10%

    Gini coefficient: lower = fairer paging distribution = better.
    gini = sum(|xi - xj|) / (2 * n^2 * mean)

    Returns 0.0 if no data (insufficient data).
    """
    sub_scores: list[tuple[float, float]] = []  # (score, weight)

    # --- Incidents per week (35%) ---
    ipw = metrics.incidents_per_week
    # 0/week → 100, 5/week → 50, 10+/week → 0
    ipw_score = _interpolate_score(ipw, green_max=0.5, amber_max=5.0, high_is_bad=True)
    sub_scores.append((ipw_score, 0.35))

    # --- Avg MTTR (35%) ---
    if metrics.avg_mttr_seconds is not None:
        # < 1h → 100, 1h–24h → 50, > 24h → 0
        hours = metrics.avg_mttr_seconds / 3600
        mttr_score = _interpolate_score(hours, green_max=1.0, amber_max=24.0, high_is_bad=True)
        sub_scores.append((mttr_score, 0.35))

    # --- P1 count (20%) ---
    p1 = metrics.p1_count
    if p1 == 0:
        p1_score = 100.0
    elif p1 <= 1:
        p1_score = _lerp(p1, 0, 1, 100.0, 70.0)
    elif p1 <= 3:
        p1_score = _lerp(p1, 1, 3, 70.0, 30.0)
    else:
        p1_score = max(0.0, _lerp(p1, 3, 10, 30.0, 0.0))
    sub_scores.append((p1_score, 0.20))

    # --- Paging Gini (10%) ---
    paging_values = list(metrics.paging_distribution.values())
    gini = _gini_coefficient(paging_values)
    # gini=0 (perfect fairness) → 100, gini=1 (all on one person) → 0
    gini_score = max(0.0, min(100.0, (1.0 - gini) * 100.0))
    sub_scores.append((gini_score, 0.10))

    if not sub_scores:
        return 0.0

    total_weight = sum(w for _, w in sub_scores)
    if total_weight == 0:
        return 0.0

    weighted_score = sum(s * w for s, w in sub_scores) / total_weight
    return round(min(100.0, max(0.0, weighted_score)), 2)


# ---------------------------------------------------------------------------
# Write snapshot to DB
# ---------------------------------------------------------------------------


async def write_incident_load_snapshot(
    team_id: UUID,
    metrics: IncidentLoadMetrics,
    score: float,
    db: AsyncSession,
) -> TeamMetricSnapshot:
    """Persist an Incident Load metric snapshot to team_metric_snapshots.

    Args:
        team_id: Team UUID.
        metrics: Computed IncidentLoadMetrics.
        score: Pre-computed score (0–100).
        db: Async SQLAlchemy session (caller must commit).

    Returns:
        The inserted TeamMetricSnapshot row.
    """
    now = datetime.now(tz=timezone.utc)
    rag = _rag_from_score(score)

    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="incident_load",
        score=Decimal(str(round(score, 2))),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "incident_load_snapshot_written",
        team_id=str(team_id),
        score=score,
        rag=rag,
        incident_count=metrics.incident_count,
        incidents_per_week=metrics.incidents_per_week,
        p1_count=metrics.p1_count,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.mean(values)


def _safe_percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx = max(0, min(n - 1, int(percentile / 100 * n + 0.5) - 1))
    return float(sorted_vals[idx])


def _gini_coefficient(values: list[int]) -> float:
    """Compute Gini coefficient for a list of non-negative integers.

    gini = sum(|xi - xj|) / (2 * n^2 * mean)

    Returns 0.0 for empty or uniform distributions (perfectly fair).
    Returns 1.0 for maximally unequal distributions.
    """
    if not values or len(values) < 2:
        return 0.0
    n = len(values)
    mean_val = statistics.mean(values)
    if mean_val == 0:
        return 0.0
    total_diff = sum(abs(xi - xj) for xi in values for xj in values)
    return total_diff / (2 * n * n * mean_val)


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
    return y0 + t * (y1 - y0)


def _interpolate_score(
    value: float,
    green_max: float,
    amber_max: float,
    high_is_bad: bool = True,
) -> float:
    """Map a metric value to a 0–100 score using threshold bands."""
    if high_is_bad:
        if value <= green_max:
            return 100.0
        if value <= amber_max:
            return _lerp(value, green_max, amber_max, 100.0, 50.0)
        red_max = amber_max + (amber_max - green_max)
        return max(0.0, _lerp(value, amber_max, red_max, 50.0, 0.0))
    else:
        if value >= green_max:
            return 100.0
        if value >= amber_max:
            return _lerp(value, amber_max, green_max, 50.0, 100.0)
        return max(0.0, _lerp(value, 0.0, amber_max, 0.0, 50.0))


def _rag_from_score(score: float) -> str:
    if score >= 70.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"
