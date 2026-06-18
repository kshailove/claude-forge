"""Teams API router.

Endpoints:
  GET /api/v1/teams                       — list teams (RBAC scoped)
  GET /api/v1/teams/{team_id}             — team detail + composite + DORA + members
  GET /api/v1/teams/{team_id}/pr-health   — PR health detail + stale PRs
  GET /api/v1/teams/{team_id}/pr-health/stale-prs — stale PR drill-down
  GET /api/v1/teams/{team_id}/sprint-health — sprint health detail
  GET /api/v1/teams/{team_id}/incident-load — incident load detail + recent incidents
  GET /api/v1/teams/{team_id}/slack-signal — slack signal or degraded banner
  GET /api/v1/teams/{team_id}/members     — team members with load indicators

Spec reference: §8 M4c
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import (
    AnyAuthenticatedUser,
    CurrentUser,
    get_current_user,
    require_team_access,
)
from app.core.redis import get_redis
from app.metrics.composite_score import (
    CompositeScore,
    _is_slack_degraded,
    _latest_component_score,
    _rag_from_score,
    compute_composite_score,
)
from app.metrics.dora import DORAMetrics, compute_dora_metrics
from app.metrics.incident_load import (
    IncidentLoadMetrics,
    compute_incident_load,
    compute_incident_load_score,
)
from app.metrics.pr_health import (
    PRHealthMetrics,
    compute_pr_health,
    compute_pr_health_score,
)
from app.metrics.sprint_health import (
    SprintHealthMetrics,
    compute_sprint_health,
    compute_sprint_health_score,
)
from app.models.github import PullRequest
from app.models.incidents import Incident
from app.models.team import Team, TeamMembership
from app.models.user import User
from app.schemas.teams import (
    CompositeScoreDetail,
    DORAMetricsSummary,
    IncidentItem,
    IncidentLoadDetailResponse,
    MemberLoadIndicator,
    PRHealthDetailResponse,
    RepeatServiceItem,
    SlackSignalDetailResponse,
    SprintHealthDetailResponse,
    StalePR,
    StalePRListResponse,
    TeamDetailResponse,
    TeamMembersResponse,
    TeamSummary,
    TeamsListResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])

_CACHE_TTL = 7200  # 2 hours
_STALE_DAYS = 3


# ---------------------------------------------------------------------------
# GET /api/v1/teams
# ---------------------------------------------------------------------------


@router.get("", response_model=TeamsListResponse)
async def list_teams(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamsListResponse:
    """List teams visible to the current user with health scores.

    Director/Admin: all teams.
    EM: only their own team.
    """
    if current_user.is_director_or_above:
        teams_result = await db.execute(select(Team).order_by(Team.name))
        teams: list[Team] = list(teams_result.scalars().all())
    elif current_user.team_id is not None:
        teams_result = await db.execute(
            select(Team).where(Team.id == current_user.team_id)
        )
        teams = list(teams_result.scalars().all())
    else:
        teams = []

    summaries: list[TeamSummary] = []
    for team in teams:
        composite_score = await _latest_component_score(
            team_id=team.id, component="composite", db=db
        )
        rag = _rag_from_score(composite_score) if composite_score is not None else None

        # EM display name
        em_username: str | None = None
        if team.em_user_id is not None:
            em_result = await db.execute(
                select(User.username).where(User.id == team.em_user_id)
            )
            em_username = em_result.scalar_one_or_none()

        member_count_result = await db.execute(
            select(func.count()).select_from(TeamMembership).where(
                TeamMembership.team_id == team.id
            )
        )
        member_count = member_count_result.scalar_one() or 0

        summaries.append(
            TeamSummary(
                team_id=team.id,
                team_name=team.name,
                slug=team.slug,
                composite_score=composite_score,
                rag=rag,
                em_username=em_username,
                member_count=member_count,
            )
        )

    return TeamsListResponse(teams=summaries, total=len(summaries))


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}
# ---------------------------------------------------------------------------


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team_detail(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Return team detail: composite score, all sub-scores, DORA metrics, members.

    Cached per team for 2 hours.
    """
    cache_key = f"team_score:{team_id}"
    redis = get_redis()

    try:
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return TeamDetailResponse(**data)
    except Exception:
        logger.warning("team_detail_cache_read_failed", team_id=str(team_id))

    team = await _get_team_or_404(team_id=team_id, db=db)

    # Composite score
    composite = await compute_composite_score(team_id=team_id, db=db)
    composite_detail = _composite_to_schema(composite)

    # DORA metrics
    try:
        dora_metrics = await compute_dora_metrics(team_id=team_id, db=db)
        dora_summary = DORAMetricsSummary(**dora_metrics.model_dump())
    except Exception:
        logger.warning("dora_metrics_failed", team_id=str(team_id))
        dora_summary = None

    # Members
    members = await _build_members_list(team_id=team_id, db=db)

    response = TeamDetailResponse(
        team_id=team.id,
        team_name=team.name,
        slug=team.slug,
        composite=composite_detail,
        dora=dora_summary,
        members=members,
        member_count=len(members),
    )

    try:
        await redis.setex(cache_key, _CACHE_TTL, response.model_dump_json())
    except Exception:
        logger.warning("team_detail_cache_write_failed", team_id=str(team_id))

    return response


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/pr-health
# ---------------------------------------------------------------------------


@router.get("/{team_id}/pr-health", response_model=PRHealthDetailResponse)
async def get_pr_health(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> PRHealthDetailResponse:
    """Return PR Health metrics with stale PR list."""
    await _get_team_or_404(team_id=team_id, db=db)

    metrics = await compute_pr_health(team_id=team_id, db=db)
    score = compute_pr_health_score(metrics)
    rag = _rag_from_score(score) if score > 0 else None

    stale_prs = await _build_stale_prs(team_id=team_id, db=db)

    return PRHealthDetailResponse(
        team_id=team_id,
        score=score,
        rag=rag,
        avg_cycle_time_seconds=metrics.avg_cycle_time_seconds,
        p50_cycle_time_seconds=metrics.p50_cycle_time_seconds,
        p95_cycle_time_seconds=metrics.p95_cycle_time_seconds,
        avg_first_review_latency_seconds=metrics.avg_first_review_latency_seconds,
        p50_first_review_latency_seconds=metrics.p50_first_review_latency_seconds,
        stale_pr_count=metrics.stale_pr_count,
        review_coverage_pct=metrics.review_coverage_pct,
        review_participation_pct=metrics.review_participation_pct,
        rework_rate_pct=metrics.rework_rate_pct,
        merged_pr_count=metrics.merged_pr_count,
        open_pr_count=metrics.open_pr_count,
        window_days=metrics.window_days,
        stale_prs=stale_prs,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/pr-health/stale-prs
# ---------------------------------------------------------------------------


@router.get("/{team_id}/pr-health/stale-prs", response_model=StalePRListResponse)
async def get_stale_prs(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> StalePRListResponse:
    """Drill-down: list of all stale PRs for a team."""
    await _get_team_or_404(team_id=team_id, db=db)
    stale_prs = await _build_stale_prs(team_id=team_id, db=db)
    return StalePRListResponse(team_id=team_id, stale_prs=stale_prs, total=len(stale_prs))


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/sprint-health
# ---------------------------------------------------------------------------


@router.get("/{team_id}/sprint-health", response_model=SprintHealthDetailResponse)
async def get_sprint_health(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> SprintHealthDetailResponse:
    """Return Sprint Health metrics for a team."""
    await _get_team_or_404(team_id=team_id, db=db)

    metrics = await compute_sprint_health(team_id=team_id, db=db)
    if metrics is None:
        metrics = SprintHealthMetrics(setup_required=True)

    score = compute_sprint_health_score(metrics)
    rag = _rag_from_score(score) if score > 0 else None

    return SprintHealthDetailResponse(
        team_id=team_id,
        score=score if not metrics.setup_required else None,
        rag=rag,
        current_sprint_name=metrics.current_sprint_name,
        current_sprint_id=metrics.current_sprint_id,
        current_sprint_completion_pct=metrics.current_sprint_completion_pct,
        scope_creep_pct=metrics.scope_creep_pct,
        carry_over_rate_pct=metrics.carry_over_rate_pct,
        blocked_ticket_count=metrics.blocked_ticket_count,
        blocked_avg_age_days=metrics.blocked_avg_age_days,
        velocity_trend_points=metrics.velocity_trend_points,
        sprint_commitment_rate_pct=metrics.sprint_commitment_rate_pct,
        wip_count=metrics.wip_count,
        flow_distribution=metrics.flow_distribution,
        setup_required=metrics.setup_required,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/incident-load
# ---------------------------------------------------------------------------


@router.get("/{team_id}/incident-load", response_model=IncidentLoadDetailResponse)
async def get_incident_load(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> IncidentLoadDetailResponse:
    """Return Incident Load metrics + list of recent incidents."""
    await _get_team_or_404(team_id=team_id, db=db)

    metrics = await compute_incident_load(team_id=team_id, db=db)
    score = compute_incident_load_score(metrics)
    rag = _rag_from_score(score)

    recent_incidents = await _recent_incidents(team_id=team_id, db=db)

    return IncidentLoadDetailResponse(
        team_id=team_id,
        score=score,
        rag=rag,
        incident_count=metrics.incident_count,
        p1_count=metrics.p1_count,
        p2_count=metrics.p2_count,
        p3_count=metrics.p3_count,
        p4_count=metrics.p4_count,
        avg_mttr_seconds=metrics.avg_mttr_seconds,
        p50_mttr_seconds=metrics.p50_mttr_seconds,
        p95_mttr_seconds=metrics.p95_mttr_seconds,
        avg_mtta_seconds=metrics.avg_mtta_seconds,
        incidents_per_week=metrics.incidents_per_week,
        repeat_services=[
            RepeatServiceItem(service_name=rs.service_name, count=rs.count)
            for rs in metrics.repeat_services
        ],
        window_days=metrics.window_days,
        recent_incidents=recent_incidents,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/slack-signal
# ---------------------------------------------------------------------------


@router.get("/{team_id}/slack-signal", response_model=SlackSignalDetailResponse)
async def get_slack_signal(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> SlackSignalDetailResponse:
    """Return Slack Signal metrics or degraded banner."""
    await _get_team_or_404(team_id=team_id, db=db)

    degraded = await _is_slack_degraded(team_id=team_id, db=db)
    if degraded:
        return SlackSignalDetailResponse(
            team_id=team_id,
            degraded=True,
            reason="Slack integration is not configured or no recent data available.",
        )

    score = await _latest_component_score(
        team_id=team_id, component="slack_signal", db=db
    )
    rag = _rag_from_score(score) if score is not None else None

    return SlackSignalDetailResponse(
        team_id=team_id,
        degraded=False,
        score=score,
        rag=rag,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/teams/{team_id}/members
# ---------------------------------------------------------------------------


@router.get("/{team_id}/members", response_model=TeamMembersResponse)
async def get_team_members(
    team_id: UUID,
    current_user: CurrentUser = Depends(require_team_access()),
    db: AsyncSession = Depends(get_db),
) -> TeamMembersResponse:
    """Return team members with their load indicators."""
    await _get_team_or_404(team_id=team_id, db=db)
    members = await _build_members_list(team_id=team_id, db=db)
    return TeamMembersResponse(team_id=team_id, members=members, total=len(members))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_team_or_404(team_id: UUID, db: AsyncSession) -> Team:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team: Team | None = result.scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return team


def _composite_to_schema(c: CompositeScore) -> CompositeScoreDetail:
    return CompositeScoreDetail(
        score=c.score,
        rag=c.rag,
        pr_health_score=c.pr_health_score,
        sprint_health_score=c.sprint_health_score,
        incident_load_score=c.incident_load_score,
        slack_signal_score=c.slack_signal_score,
        pr_health_weight=c.pr_health_weight,
        sprint_health_weight=c.sprint_health_weight,
        incident_load_weight=c.incident_load_weight,
        slack_signal_weight=c.slack_signal_weight,
        slack_degraded=c.slack_degraded,
    )


async def _build_stale_prs(team_id: UUID, db: AsyncSession) -> list[StalePR]:
    """Return stale open PRs (no activity for > 3 days) with author usernames."""
    stale_threshold = datetime.now(tz=timezone.utc) - timedelta(days=_STALE_DAYS)

    prs_result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.team_id == team_id,
                PullRequest.state == "open",
                PullRequest.last_activity_at < stale_threshold,
            )
        ).order_by(PullRequest.last_activity_at.asc())
    )
    prs: list[PullRequest] = list(prs_result.scalars().all())

    now = datetime.now(tz=timezone.utc)
    result: list[StalePR] = []
    for pr in prs:
        # Resolve author username
        author_name = "unknown"
        if pr.author_user_id is not None:
            user_result = await db.execute(
                select(User.username).where(User.id == pr.author_user_id)
            )
            author_name = user_result.scalar_one_or_none() or "unknown"

        # last_activity_at may be naive; normalise
        last_activity = pr.last_activity_at
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        days_stale = (now - last_activity).total_seconds() / 86400.0

        # Build a GitHub-style PR URL from repo name + number
        url = f"https://github.com/{pr.repo_full_name}/pull/{pr.pr_number}"

        result.append(
            StalePR(
                title=pr.title,
                url=url,
                days_stale=round(days_stale, 1),
                author=author_name,
            )
        )

    return result


async def _recent_incidents(team_id: UUID, db: AsyncSession, limit: int = 20) -> list[IncidentItem]:
    """Return the most recent incidents for a team."""
    result = await db.execute(
        select(Incident)
        .where(Incident.team_id == team_id)
        .order_by(Incident.triggered_at.desc())
        .limit(limit)
    )
    incidents: list[Incident] = list(result.scalars().all())

    return [
        IncidentItem(
            id=inc.id,
            title=inc.title,
            severity=inc.severity,
            triggered_at=inc.triggered_at,
            resolved_at=inc.resolved_at,
            mttr_seconds=float(inc.mttr_seconds) if inc.mttr_seconds is not None else None,
            service_name=inc.service_name,
        )
        for inc in incidents
    ]


async def _build_members_list(team_id: UUID, db: AsyncSession) -> list[MemberLoadIndicator]:
    """Return per-member load indicators from raw data."""
    memberships_result = await db.execute(
        select(TeamMembership).where(TeamMembership.team_id == team_id)
    )
    memberships: list[TeamMembership] = list(memberships_result.scalars().all())

    indicators: list[MemberLoadIndicator] = []
    now = datetime.now(tz=timezone.utc)

    for membership in memberships:
        user_result = await db.execute(
            select(User).where(User.id == membership.user_id)
        )
        user: User | None = user_result.scalar_one_or_none()
        if user is None:
            continue

        # Open PRs authored by this user in this team
        open_pr_result = await db.execute(
            select(func.count()).select_from(PullRequest).where(
                and_(
                    PullRequest.team_id == team_id,
                    PullRequest.author_user_id == user.id,
                    PullRequest.state == "open",
                )
            )
        )
        open_pr_count = open_pr_result.scalar_one() or 0

        # Active incidents assigned to this user
        from app.models.incidents import IncidentAssignment
        active_inc_result = await db.execute(
            select(func.count()).select_from(IncidentAssignment).join(
                Incident, Incident.id == IncidentAssignment.incident_id
            ).where(
                and_(
                    IncidentAssignment.user_id == user.id,
                    Incident.team_id == team_id,
                    Incident.resolved_at.is_(None),
                )
            )
        )
        active_incident_count = active_inc_result.scalar_one() or 0

        # On-call hours in last 7 days (from oncall_shifts)
        from app.models.incidents import OncallShift
        seven_days_ago = now - timedelta(days=7)
        shifts_result = await db.execute(
            select(OncallShift).where(
                and_(
                    OncallShift.user_id == user.id,
                    OncallShift.start_at >= seven_days_ago,
                )
            )
        )
        shifts: list[OncallShift] = list(shifts_result.scalars().all())
        on_call_hours = sum(
            (min(s.end_at, now) - max(s.start_at, seven_days_ago)).total_seconds() / 3600
            for s in shifts
            if s.end_at > s.start_at
        )

        indicators.append(
            MemberLoadIndicator(
                user_id=user.id,
                username=user.username,
                email=user.email,
                open_pr_count=open_pr_count,
                on_call_hours_7d=round(on_call_hours, 1),
                active_incident_count=active_incident_count,
                role=user.role,
            )
        )

    return indicators
