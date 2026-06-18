"""Incidents API router.

Endpoints:
  GET /api/v1/incidents              — company-wide paginated incidents list
  GET /api/v1/incidents/summary      — aggregated summary for incidents tab header
  GET /api/v1/incidents/oncall-load  — on-call fairness view
  GET /api/v1/incidents/by-service   — breakdown by service
  GET /api/v1/incidents/timeline     — daily incident count for chart

Spec reference: §8 M5b
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import CurrentUser, get_current_user
from app.models.incidents import Incident, IncidentAssignment, OncallShift
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.schemas.incidents import (
    CorrelationSignal,
    EngineerOncallLoad,
    IncidentListItem,
    IncidentsByServiceResponse,
    IncidentsSummaryResponse,
    IncidentsListResponse,
    IncidentsTimelineResponse,
    OncallLoadResponse,
    ServiceIncidentStats,
    SeverityBreakdown,
    TimelineDay,
    WorstIncident,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])

_VALID_WINDOWS = {30, 60, 90}


# ---------------------------------------------------------------------------
# Helpers: build team_id filter for current user
# ---------------------------------------------------------------------------


async def _allowed_team_ids(
    current_user: CurrentUser,
    db: AsyncSession,
    team_id_filter: UUID | None = None,
) -> list[UUID] | None:
    """Return a list of team IDs the current user can see.

    Director/Admin: all teams (None means no filter needed).
    EM: only their own team.
    """
    if current_user.is_director_or_above:
        if team_id_filter is not None:
            return [team_id_filter]
        return None  # no restriction
    else:
        # EM: restrict to own team
        if current_user.team_id is None:
            return []
        if team_id_filter is not None and team_id_filter != current_user.team_id:
            return []
        return [current_user.team_id]


def _window_start(window_days: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(days=window_days)


# ---------------------------------------------------------------------------
# GET /api/v1/incidents/summary
# ---------------------------------------------------------------------------

# NOTE: summary, oncall-load, by-service, and timeline routes MUST be
# declared before /{incident_id} style routes to avoid path shadowing.


@router.get("/summary", response_model=IncidentsSummaryResponse)
async def get_incidents_summary(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    team_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentsSummaryResponse:
    """Return aggregated incident summary for the Incidents tab header."""
    if window_days not in _VALID_WINDOWS:
        window_days = 30
    since = _window_start(window_days)
    allowed_teams = await _allowed_team_ids(current_user, db, team_id)

    # Build base filter
    base_filter = [Incident.triggered_at >= since]
    if allowed_teams is not None:
        base_filter.append(Incident.team_id.in_(allowed_teams))

    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(Incident).where(and_(*base_filter))
    )
    total = total_result.scalar_one() or 0

    # By severity
    severity_result = await db.execute(
        select(Incident.severity, func.count().label("cnt"))
        .where(and_(*base_filter))
        .group_by(Incident.severity)
    )
    sev_map: dict[str, int] = {row[0].lower(): row[1] for row in severity_result.all()}

    by_severity = SeverityBreakdown(
        p1=sev_map.get("p1", 0),
        p2=sev_map.get("p2", 0),
        p3=sev_map.get("p3", 0),
        p4=sev_map.get("p4", 0),
    )

    # Avg MTTR
    mttr_result = await db.execute(
        select(func.avg(Incident.mttr_seconds)).where(
            and_(*base_filter, Incident.mttr_seconds.isnot(None))
        )
    )
    avg_mttr = mttr_result.scalar_one_or_none()

    # Worst MTTR incident
    worst_result = await db.execute(
        select(Incident)
        .where(and_(*base_filter, Incident.mttr_seconds.isnot(None)))
        .order_by(Incident.mttr_seconds.desc())
        .limit(1)
    )
    worst_inc: Incident | None = worst_result.scalar_one_or_none()
    worst_incident_schema = (
        WorstIncident(
            id=worst_inc.id,
            title=worst_inc.title,
            severity=worst_inc.severity,
            mttr_seconds=float(worst_inc.mttr_seconds) if worst_inc.mttr_seconds else None,
            triggered_at=worst_inc.triggered_at,
        )
        if worst_inc
        else None
    )

    # Correlation signal: check if weeks with >3 incidents correlate with higher PR cycle time
    correlation = await _compute_correlation_signal(base_filter, window_days, db)

    return IncidentsSummaryResponse(
        total_count=total,
        by_severity=by_severity,
        avg_mttr_seconds=float(avg_mttr) if avg_mttr is not None else None,
        worst_mttr_incident=worst_incident_schema,
        correlation_signal=correlation,
        window_days=window_days,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/incidents/oncall-load
# ---------------------------------------------------------------------------


@router.get("/oncall-load", response_model=OncallLoadResponse)
async def get_oncall_load(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    team_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OncallLoadResponse:
    """Return per-engineer on-call hours + page counts with Gini fairness score."""
    if window_days not in _VALID_WINDOWS:
        window_days = 30
    since = _window_start(window_days)
    now = datetime.now(tz=timezone.utc)
    allowed_teams = await _allowed_team_ids(current_user, db, team_id)

    # Get all relevant users
    if allowed_teams is None:
        # All engineers
        users_result = await db.execute(
            select(User).where(User.role == "engineer").order_by(User.username)
        )
        users: list[User] = list(users_result.scalars().all())
    else:
        if not allowed_teams:
            return OncallLoadResponse(engineers=[], gini_coefficient=None, window_days=window_days)
        memberships_result = await db.execute(
            select(TeamMembership.user_id).where(
                TeamMembership.team_id.in_(allowed_teams)
            )
        )
        member_ids = [row[0] for row in memberships_result.all()]
        if not member_ids:
            return OncallLoadResponse(engineers=[], gini_coefficient=None, window_days=window_days)
        users_result = await db.execute(
            select(User).where(User.id.in_(member_ids)).order_by(User.username)
        )
        users = list(users_result.scalars().all())

    engineer_loads: list[EngineerOncallLoad] = []
    page_counts: list[int] = []

    for user in users:
        # On-call hours
        shifts_result = await db.execute(
            select(OncallShift).where(
                and_(
                    OncallShift.user_id == user.id,
                    OncallShift.start_at >= since,
                )
            )
        )
        shifts: list[OncallShift] = list(shifts_result.scalars().all())
        on_call_hours = sum(
            (min(s.end_at, now) - max(s.start_at, since)).total_seconds() / 3600
            for s in shifts
            if s.end_at > s.start_at
        )

        # Pages received
        pages_result = await db.execute(
            select(func.count()).select_from(IncidentAssignment).join(
                Incident, Incident.id == IncidentAssignment.incident_id
            ).where(
                and_(
                    IncidentAssignment.user_id == user.id,
                    Incident.triggered_at >= since,
                )
            )
        )
        pages = pages_result.scalar_one() or 0
        page_counts.append(pages)

        team_name: str | None = None
        if user.team_id is not None:
            team_res = await db.execute(select(Team.name).where(Team.id == user.team_id))
            team_name = team_res.scalar_one_or_none()

        engineer_loads.append(
            EngineerOncallLoad(
                user_id=user.id,
                name=user.username,
                on_call_hours=round(on_call_hours, 1),
                pages_received=pages,
                team_name=team_name,
            )
        )

    # Gini coefficient of paging distribution
    gini = _gini_coefficient(page_counts) if page_counts else None

    return OncallLoadResponse(
        engineers=engineer_loads,
        gini_coefficient=round(gini, 4) if gini is not None else None,
        window_days=window_days,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/incidents/by-service
# ---------------------------------------------------------------------------


@router.get("/by-service", response_model=IncidentsByServiceResponse)
async def get_incidents_by_service(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    team_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentsByServiceResponse:
    """Return incident counts broken down by service."""
    if window_days not in _VALID_WINDOWS:
        window_days = 30
    since = _window_start(window_days)
    allowed_teams = await _allowed_team_ids(current_user, db, team_id)

    base_filter = [Incident.triggered_at >= since, Incident.service_name.isnot(None)]
    if allowed_teams is not None:
        base_filter.append(Incident.team_id.in_(allowed_teams))

    result = await db.execute(
        select(
            Incident.service_name,
            func.count().label("incident_count"),
            func.sum(case((Incident.severity == "p1", 1), else_=0)).label("p1_count"),
            func.avg(Incident.mttr_seconds).label("avg_mttr"),
        )
        .where(and_(*base_filter))
        .group_by(Incident.service_name)
        .order_by(func.count().desc())
    )
    rows = result.all()

    services: list[ServiceIncidentStats] = []
    for row in rows:
        service_name, incident_count, p1_count, avg_mttr = row
        # repeat_count: incidents that came from a service with >= 3 occurrences
        repeat_count = incident_count if incident_count >= 3 else 0
        services.append(
            ServiceIncidentStats(
                service_name=service_name or "unknown",
                incident_count=incident_count,
                p1_count=int(p1_count or 0),
                avg_mttr_seconds=float(avg_mttr) if avg_mttr is not None else None,
                repeat_count=repeat_count,
            )
        )

    return IncidentsByServiceResponse(services=services, window_days=window_days)


# ---------------------------------------------------------------------------
# GET /api/v1/incidents/timeline
# ---------------------------------------------------------------------------


@router.get("/timeline", response_model=IncidentsTimelineResponse)
async def get_incidents_timeline(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    team_id: UUID | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentsTimelineResponse:
    """Return daily incident counts for chart rendering."""
    if window_days not in _VALID_WINDOWS:
        window_days = 30
    since = _window_start(window_days)
    allowed_teams = await _allowed_team_ids(current_user, db, team_id)

    base_filter = [Incident.triggered_at >= since]
    if allowed_teams is not None:
        base_filter.append(Incident.team_id.in_(allowed_teams))

    _day = cast(Incident.triggered_at, Date).label("day")
    result = await db.execute(
        select(
            _day,
            func.count().label("count"),
            func.sum(case((Incident.severity == "p1", 1), else_=0)).label("p1_count"),
        )
        .where(and_(*base_filter))
        .group_by(_day)
        .order_by(_day)
    )
    rows = result.all()

    # Build day-keyed map
    day_map: dict[str, TimelineDay] = {}
    for row in rows:
        day_val, count, p1_count = row
        # day_val may be a date object or string depending on dialect
        if hasattr(day_val, "strftime"):
            day_str = day_val.strftime("%Y-%m-%d")
        else:
            day_str = str(day_val)[:10]
        day_map[day_str] = TimelineDay(
            date=day_str,
            count=int(count),
            p1_count=int(p1_count or 0),
        )

    # Fill gaps with zero days
    timeline: list[TimelineDay] = []
    now = datetime.now(tz=timezone.utc)
    for day_offset in range(window_days, -1, -1):
        day = now - timedelta(days=day_offset)
        day_str = day.strftime("%Y-%m-%d")
        timeline.append(day_map.get(day_str, TimelineDay(date=day_str, count=0, p1_count=0)))

    return IncidentsTimelineResponse(timeline=timeline, window_days=window_days)


# ---------------------------------------------------------------------------
# GET /api/v1/incidents
# ---------------------------------------------------------------------------


@router.get("", response_model=IncidentsListResponse)
async def list_incidents(
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
    severity: str | None = Query(default=None),
    team_id: UUID | None = Query(default=None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IncidentsListResponse:
    """Return paginated list of incidents company-wide (scoped by RBAC)."""
    if window_days not in _VALID_WINDOWS:
        window_days = 30
    since = _window_start(window_days)
    allowed_teams = await _allowed_team_ids(current_user, db, team_id)

    base_filter = [Incident.triggered_at >= since]
    if allowed_teams is not None:
        base_filter.append(Incident.team_id.in_(allowed_teams))
    if severity:
        base_filter.append(Incident.severity == severity.lower())

    # Total count
    total_result = await db.execute(
        select(func.count()).select_from(Incident).where(and_(*base_filter))
    )
    total = total_result.scalar_one() or 0

    # Paginated results
    offset = (page - 1) * page_size
    incidents_result = await db.execute(
        select(Incident)
        .where(and_(*base_filter))
        .order_by(Incident.triggered_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    incidents: list[Incident] = list(incidents_result.scalars().all())

    # Resolve team names in bulk
    team_ids_needed = {inc.team_id for inc in incidents if inc.team_id is not None}
    team_name_map: dict[UUID, str] = {}
    if team_ids_needed:
        teams_result = await db.execute(
            select(Team.id, Team.name).where(Team.id.in_(team_ids_needed))
        )
        team_name_map = {row[0]: row[1] for row in teams_result.all()}

    items: list[IncidentListItem] = [
        IncidentListItem(
            id=inc.id,
            title=inc.title,
            severity=inc.severity,
            service_name=inc.service_name,
            team_name=team_name_map.get(inc.team_id),
            triggered_at=inc.triggered_at,
            resolved_at=inc.resolved_at,
            mttr_seconds=float(inc.mttr_seconds) if inc.mttr_seconds is not None else None,
        )
        for inc in incidents
    ]

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return IncidentsListResponse(
        incidents=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _gini_coefficient(values: list[int]) -> float | None:
    """Compute Gini coefficient of a distribution. 0 = equal, 1 = maximally unequal."""
    n = len(values)
    if n == 0:
        return None
    total = sum(values)
    if total == 0:
        return 0.0
    sorted_vals = sorted(values)
    cumulative = 0.0
    gini_sum = 0.0
    for i, v in enumerate(sorted_vals, start=1):
        cumulative += v
        gini_sum += (2 * i - n - 1) * v
    return gini_sum / (n * total)


async def _compute_correlation_signal(
    base_filter: list,
    window_days: int,
    db: AsyncSession,
) -> CorrelationSignal:
    """Simple heuristic: check if avg MTTR in weeks with >3 incidents is higher.

    We compare avg PR cycle time in weeks where incident spikes occurred vs.
    weeks without spikes to detect a correlation pattern.
    """
    try:
        from app.models.github import PullRequest

        # Get weekly incident counts
        since = datetime.now(tz=timezone.utc) - timedelta(days=window_days)
        week_result = await db.execute(
            select(
                func.date_trunc("week", Incident.triggered_at).label("week"),
                func.count().label("cnt"),
            )
            .where(and_(*base_filter))
            .group_by(func.date_trunc("week", Incident.triggered_at))
        )
        week_rows = week_result.all()

        spike_weeks = [row[0] for row in week_rows if row[1] > 3]
        if not spike_weeks:
            return CorrelationSignal(detected=False)

        # For each spike week, check PR cycle time in the following week
        pr_lags: list[float] = []
        for spike_week in spike_weeks:
            lag_start = spike_week + timedelta(days=7)
            lag_end = spike_week + timedelta(days=14)
            lag_result = await db.execute(
                select(func.avg(PullRequest.cycle_time_seconds)).where(
                    and_(
                        PullRequest.merged_at >= lag_start,
                        PullRequest.merged_at < lag_end,
                        PullRequest.cycle_time_seconds.isnot(None),
                    )
                )
            )
            avg_lag = lag_result.scalar_one_or_none()
            if avg_lag is not None:
                pr_lags.append(float(avg_lag))

        if not pr_lags:
            return CorrelationSignal(detected=False)

        # Compare to baseline PR cycle time
        baseline_result = await db.execute(
            select(func.avg(PullRequest.cycle_time_seconds)).where(
                and_(
                    PullRequest.merged_at >= since,
                    PullRequest.cycle_time_seconds.isnot(None),
                )
            )
        )
        baseline_avg = baseline_result.scalar_one_or_none()

        if baseline_avg is None or baseline_avg == 0:
            return CorrelationSignal(detected=False)

        post_spike_avg = sum(pr_lags) / len(pr_lags)
        # Signal if post-spike PR cycle time is at least 20% higher than baseline
        if post_spike_avg > float(baseline_avg) * 1.2:
            avg_lag_days = round((post_spike_avg - float(baseline_avg)) / 86400, 1)
            return CorrelationSignal(
                detected=True,
                description=(
                    f"Incident spikes in last {window_days}d preceded PR cycle time "
                    f"increase by avg {avg_lag_days} days in the following week."
                ),
                avg_lag_days=avg_lag_days,
            )

        return CorrelationSignal(detected=False)

    except Exception:
        logger.warning("correlation_signal_failed")
        return CorrelationSignal(detected=False)
