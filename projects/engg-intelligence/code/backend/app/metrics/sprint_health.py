"""Sprint Health metric computation engine.

Computes all Sprint Health metrics and the overall Sprint Health score (0–100)
for a team based on the active sprint and the last 6 completed sprints.

Spec reference: §5.9, M2c
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import TeamMetricSnapshot
from app.models.tickets import Sprint, Ticket, TicketStateTransition

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic v2 metrics model
# ---------------------------------------------------------------------------


class SprintHealthMetrics(BaseModel):
    """All computed Sprint Health metrics for a team."""

    # Active sprint
    current_sprint_name: str | None = None
    current_sprint_id: str | None = None

    # Completion
    current_sprint_completion_pct: float | None = None  # done / total * 100

    # Scope creep: tickets added after sprint start / original count * 100
    scope_creep_pct: float | None = None

    # Carry-over: incomplete tickets from last sprint / total last sprint * 100
    carry_over_rate_pct: float | None = None

    # Blocked tickets
    blocked_ticket_count: int = 0
    blocked_avg_age_days: float | None = None  # mean days in blocked state

    # Velocity trend (last 6 completed sprints)
    velocity_trend_points: list[float] = Field(default_factory=list)

    # Cycle time (last 30 days, done tickets)
    avg_ticket_cycle_time_seconds: float | None = None

    # Sprint commitment rate (last completed sprint)
    sprint_commitment_rate_pct: float | None = None  # delivered SP / committed SP * 100

    # WIP
    wip_count: int = 0

    # Flow distribution (completed tickets in last sprint)
    flow_distribution: dict[str, float] = Field(default_factory=dict)

    # Setup gate
    setup_required: bool = False

    # Computed at
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


async def compute_sprint_health(
    team_id: UUID,
    db: AsyncSession,
) -> SprintHealthMetrics | None:
    """Compute Sprint Health metrics for a team.

    Returns None (with setup_required=True) if no sprints are configured.

    Args:
        team_id: Team UUID.
        db: Async SQLAlchemy session.

    Returns:
        SprintHealthMetrics instance or None if no data.
    """
    now = datetime.now(tz=timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # ---- Load active sprint ----
    active_sprint_result = await db.execute(
        select(Sprint).where(
            and_(Sprint.team_id == team_id, Sprint.state == "active")
        ).order_by(Sprint.start_date.desc().nullslast())
        .limit(1)
    )
    active_sprint: Sprint | None = active_sprint_result.scalar_one_or_none()

    # ---- Load last 6 completed sprints ----
    completed_sprints_result = await db.execute(
        select(Sprint).where(
            and_(Sprint.team_id == team_id, Sprint.state == "completed")
        ).order_by(Sprint.end_date.desc().nullslast())
        .limit(6)
    )
    completed_sprints: list[Sprint] = list(completed_sprints_result.scalars().all())

    if active_sprint is None and not completed_sprints:
        logger.info(
            "sprint_health_no_data",
            team_id=str(team_id),
            reason="no_sprints_found",
        )
        return SprintHealthMetrics(setup_required=True)

    metrics = SprintHealthMetrics()

    # ---- Active sprint metrics ----
    if active_sprint is not None:
        metrics.current_sprint_name = active_sprint.name
        metrics.current_sprint_id = str(active_sprint.id)

        active_tickets_result = await db.execute(
            select(Ticket).where(Ticket.sprint_id == active_sprint.id)
        )
        active_tickets: list[Ticket] = list(active_tickets_result.scalars().all())

        total_count = len(active_tickets)
        done_count = sum(
            1 for t in active_tickets if t.status.lower() in ("done", "closed", "resolved", "complete", "completed")
        )

        if total_count > 0:
            metrics.current_sprint_completion_pct = round(done_count / total_count * 100, 1)

        # WIP count
        metrics.wip_count = sum(
            1 for t in active_tickets
            if t.status.lower() in ("in progress", "in_progress", "development", "coding", "in development")
        )

        # Blocked tickets
        blocked_tickets = [
            t for t in active_tickets
            if t.status.lower() in ("blocked", "impediment", "on hold", "waiting")
        ]
        metrics.blocked_ticket_count = len(blocked_tickets)

        # Blocked avg age days: time since ticket entered blocked state
        if blocked_tickets:
            blocked_ages = await _compute_blocked_ages(
                db=db,
                blocked_tickets=blocked_tickets,
                now=now,
            )
            if blocked_ages:
                metrics.blocked_avg_age_days = round(statistics.mean(blocked_ages), 1)

        # Scope creep: tickets added after sprint start
        if active_sprint.start_date is not None and total_count > 0:
            sprint_start_dt = datetime(
                active_sprint.start_date.year,
                active_sprint.start_date.month,
                active_sprint.start_date.day,
                tzinfo=timezone.utc,
            )
            added_after_start = sum(
                1 for t in active_tickets if t.created_at > sprint_start_dt
            )
            original_count = total_count - added_after_start
            if original_count > 0:
                metrics.scope_creep_pct = round(added_after_start / original_count * 100, 1)
            elif added_after_start > 0:
                metrics.scope_creep_pct = 100.0

    # ---- Last completed sprint carry-over + commitment rate + flow distribution ----
    if completed_sprints:
        last_sprint = completed_sprints[0]

        last_tickets_result = await db.execute(
            select(Ticket).where(Ticket.sprint_id == last_sprint.id)
        )
        last_tickets: list[Ticket] = list(last_tickets_result.scalars().all())
        last_total = len(last_tickets)

        if last_total > 0:
            last_done = [
                t for t in last_tickets
                if t.status.lower() in ("done", "closed", "resolved", "complete", "completed")
            ]
            last_incomplete = last_total - len(last_done)
            metrics.carry_over_rate_pct = round(last_incomplete / last_total * 100, 1)

            # Sprint commitment rate (story points)
            committed_sp = _sum_story_points(last_tickets)
            delivered_sp = _sum_story_points(last_done)
            if committed_sp and committed_sp > 0:
                metrics.sprint_commitment_rate_pct = round(
                    delivered_sp / committed_sp * 100, 1
                )

            # Flow distribution from completed tickets in last sprint
            if last_done:
                type_counts: dict[str, int] = {"feature": 0, "bug": 0, "tech_debt": 0, "risk": 0}
                for t in last_done:
                    ttype = (t.ticket_type or "feature").lower()
                    if ttype in type_counts:
                        type_counts[ttype] += 1
                    else:
                        type_counts["feature"] += 1  # default to feature
                total_done = len(last_done)
                metrics.flow_distribution = {
                    k: round(v / total_done * 100, 1) for k, v in type_counts.items()
                }

    # ---- Velocity trend (last 6 completed sprints, story points delivered) ----
    velocity_points: list[float] = []
    for sprint in reversed(completed_sprints):  # chronological order
        sprint_tickets_result = await db.execute(
            select(Ticket).where(Ticket.sprint_id == sprint.id)
        )
        sprint_tickets = list(sprint_tickets_result.scalars().all())
        done_tickets = [
            t for t in sprint_tickets
            if t.status.lower() in ("done", "closed", "resolved", "complete", "completed")
        ]
        sp = _sum_story_points(done_tickets)
        velocity_points.append(float(sp))
    metrics.velocity_trend_points = velocity_points

    # ---- Avg ticket cycle time (last 30 days, done tickets) ----
    recent_done_result = await db.execute(
        select(Ticket).where(
            and_(
                Ticket.team_id == team_id,
                Ticket.status.in_(("done", "closed", "resolved", "complete", "completed")),
                Ticket.completed_at.is_not(None),
                Ticket.completed_at >= thirty_days_ago,
                Ticket.started_at.is_not(None),
            )
        )
    )
    recent_done: list[Ticket] = list(recent_done_result.scalars().all())
    cycle_times: list[float] = []
    for t in recent_done:
        if t.started_at and t.completed_at:
            secs = (t.completed_at - t.started_at).total_seconds()
            if secs >= 0:
                cycle_times.append(secs)
    if cycle_times:
        metrics.avg_ticket_cycle_time_seconds = round(statistics.mean(cycle_times), 1)

    return metrics


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def compute_sprint_health_score(metrics: SprintHealthMetrics) -> float:
    """Compute Sprint Health score (0–100) from computed metrics.

    Weights:
    - Completion %:              30%
    - Carry-over rate:           20%  (inverse — lower is better)
    - Scope creep:               15%  (inverse)
    - Blocked tickets:           15%  (inverse)
    - Velocity trend direction:  20%

    Returns 0.0 if no data.
    """
    if metrics.setup_required:
        return 0.0

    sub_scores: list[tuple[float, float]] = []

    # --- Completion % (higher is better) ---
    if metrics.current_sprint_completion_pct is not None:
        cpt = metrics.current_sprint_completion_pct
        if cpt >= 80.0:
            cpt_score = 100.0
        elif cpt >= 50.0:
            cpt_score = _lerp(cpt, 50.0, 80.0, 50.0, 100.0)
        else:
            cpt_score = max(0.0, _lerp(cpt, 0.0, 50.0, 0.0, 50.0))
        sub_scores.append((cpt_score, 0.30))

    # --- Carry-over rate (lower is better, green < 10%, amber < 30%) ---
    if metrics.carry_over_rate_pct is not None:
        co = metrics.carry_over_rate_pct
        co_score = _interpolate_score(value=co, green_max=10.0, amber_max=30.0, high_is_bad=True)
        sub_scores.append((co_score, 0.20))

    # --- Scope creep (lower is better, green < 10%, amber < 25%) ---
    if metrics.scope_creep_pct is not None:
        sc = metrics.scope_creep_pct
        sc_score = _interpolate_score(value=sc, green_max=10.0, amber_max=25.0, high_is_bad=True)
        sub_scores.append((sc_score, 0.15))

    # --- Blocked ticket count (0 = 100, 1-2 = amber, 3+ = red, capped at 10) ---
    # Only include blocked score when there is an active sprint (sprint_id is known)
    if metrics.current_sprint_id is not None:
        blocked = metrics.blocked_ticket_count
        if blocked == 0:
            blocked_score = 100.0
        elif blocked <= 2:
            blocked_score = _lerp(float(blocked), 0.0, 2.0, 100.0, 50.0)
        else:
            blocked_score = max(0.0, _lerp(float(blocked), 2.0, 10.0, 50.0, 0.0))
        sub_scores.append((blocked_score, 0.15))

    # --- Velocity trend direction (last 6 sprints) ---
    vt = metrics.velocity_trend_points
    if len(vt) >= 2:
        trend_score = _velocity_trend_score(vt)
        sub_scores.append((trend_score, 0.20))

    if not sub_scores:
        return 0.0

    total_weight = sum(w for _, w in sub_scores)
    if total_weight == 0:
        return 0.0

    weighted = sum(s * w for s, w in sub_scores) / total_weight
    return round(min(100.0, max(0.0, weighted)), 2)


def _velocity_trend_score(points: list[float]) -> float:
    """Score velocity trend direction.

    Positive trend (last > median) → 100
    Flat (within 10% of median)    → 70
    Declining                      → lerp 70→0
    """
    if not points or len(points) < 2:
        return 70.0  # neutral when insufficient data

    median_val = statistics.median(points)
    last_val = points[-1]

    if median_val == 0:
        return 70.0

    pct_change = (last_val - median_val) / median_val * 100.0

    if pct_change > 10.0:
        return 100.0
    elif pct_change >= -10.0:
        return 70.0
    else:
        # Declining: lerp 70→0 as pct_change goes from -10 to -100
        return max(0.0, _lerp(pct_change, -10.0, -100.0, 70.0, 0.0))


# ---------------------------------------------------------------------------
# Write snapshot to DB
# ---------------------------------------------------------------------------


async def write_sprint_health_snapshot(
    team_id: UUID,
    metrics: SprintHealthMetrics,
    score: float,
    db: AsyncSession,
) -> TeamMetricSnapshot:
    """Persist a SprintHealthMetrics snapshot to team_metric_snapshots."""
    now = datetime.now(tz=timezone.utc)
    rag = _rag_from_score(score)

    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="sprint_health",
        score=Decimal(str(round(score, 2))),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "sprint_health_snapshot_written",
        team_id=str(team_id),
        score=score,
        rag=rag,
        completion_pct=metrics.current_sprint_completion_pct,
        carry_over=metrics.carry_over_rate_pct,
        blocked_count=metrics.blocked_ticket_count,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _compute_blocked_ages(
    *,
    db: AsyncSession,
    blocked_tickets: list[Ticket],
    now: datetime,
) -> list[float]:
    """Compute how many days each blocked ticket has been in the blocked state.

    Looks at ticket_state_transitions for the most recent transition into a
    blocked-like state. Falls back to ticket.updated_at.
    """
    blocked_statuses = {"blocked", "impediment", "on hold", "waiting"}
    ages: list[float] = []

    for ticket in blocked_tickets:
        # Find the most recent transition TO a blocked state
        transitions_result = await db.execute(
            select(TicketStateTransition).where(
                TicketStateTransition.ticket_id == ticket.id
            ).order_by(TicketStateTransition.transitioned_at.desc())
        )
        transitions: list[TicketStateTransition] = list(transitions_result.scalars().all())

        blocked_since: datetime | None = None
        for t in transitions:
            if t.to_state.lower().strip() in blocked_statuses:
                blocked_since = t.transitioned_at
                break

        if blocked_since is None:
            # Fallback: use updated_at as proxy
            blocked_since = ticket.updated_at

        if blocked_since:
            age_days = (now - blocked_since).total_seconds() / 86400.0
            if age_days >= 0:
                ages.append(age_days)

    return ages


def _sum_story_points(tickets: list[Ticket]) -> float:
    """Sum story points for a list of tickets, treating None as 0."""
    total = 0.0
    for t in tickets:
        if t.story_points is not None:
            total += float(t.story_points)
    return total


def _rag_from_score(score: float) -> str:
    """Red: 0–39, Amber: 40–69, Green: 70–100."""
    if score >= 70.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """Linear interpolation: map x in [x0, x1] to y in [y0, y1]."""
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    t = max(0.0, min(1.0, t))
    return y0 + t * (y1 - y0)


def _interpolate_score(
    value: float,
    green_max: float,
    amber_max: float,
    high_is_bad: bool = True,
) -> float:
    """Map a metric value to 0–100 using DORA-style thresholds.

    For high_is_bad=True (lower is better):
        value <= green_max → 100
        green_max < value <= amber_max → lerp 100→50
        value > amber_max → lerp 50→0 (capped at 0)
    """
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
