"""Overview API router.

GET /api/v1/overview — returns health cards for all teams the caller can see.
  - EM: returns their own team only
  - Director/Admin: returns all teams

Results are cached in Redis for 2 hours per user.

Spec reference: §8 M4b
"""
from __future__ import annotations

import json
from datetime import timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import AnyAuthenticatedUser, CurrentUser, get_current_user
from app.core.redis import get_redis
from app.metrics.composite_score import (
    _latest_component_score,
    _rag_from_score,
    get_sparkline_7d,
)
from app.models.incidents import Incident
from app.models.metrics import TeamMetricSnapshot
from app.models.team import Team, TeamMembership
from app.schemas.overview import OverviewResponse, TeamHealthCard

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/overview", tags=["overview"])

_CACHE_TTL = 7200  # 2 hours


@router.get("", response_model=OverviewResponse)
async def get_overview(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OverviewResponse:
    """Return health cards for all teams visible to the current user.

    EM: returns only their own team's card.
    Director/Admin: returns all teams.
    Cached per user for 2 hours.
    """
    cache_key = f"overview:{current_user.id}"
    redis = get_redis()

    # --- Cache check ---
    try:
        cached = await redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return OverviewResponse(**data)
    except Exception:
        logger.warning("overview_cache_read_failed", user_id=str(current_user.id))

    # --- Build team list ---
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

    cards: list[TeamHealthCard] = []
    for team in teams:
        card = await _build_team_health_card(team_id=team.id, team_name=team.name, db=db)
        cards.append(card)

    response = OverviewResponse(teams=cards, total=len(cards))

    # --- Cache result ---
    try:
        await redis.setex(cache_key, _CACHE_TTL, response.model_dump_json())
    except Exception:
        logger.warning("overview_cache_write_failed", user_id=str(current_user.id))

    return response


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _build_team_health_card(
    team_id: UUID,
    team_name: str,
    db: AsyncSession,
) -> TeamHealthCard:
    """Build a TeamHealthCard from stored snapshots without re-computing."""
    # Composite score from latest snapshot
    composite_score = await _latest_component_score(
        team_id=team_id, component="composite", db=db
    )
    if composite_score is None:
        composite_score = 0.0
    rag = _rag_from_score(composite_score)

    # Open PR count from pr_health component data (approximated from snapshots)
    # We use stored metrics; a full recompute is done by the nightly task.
    open_pr_count = await _open_pr_count(team_id=team_id, db=db)

    # Sprint completion % from latest sprint_health snapshot
    sprint_completion_pct = await _sprint_completion_pct(team_id=team_id, db=db)

    # Active incident count
    active_incident_count = await _active_incident_count(team_id=team_id, db=db)

    # Sparkline (7-day composite scores)
    sparkline_7d = await get_sparkline_7d(team_id=team_id, db=db)

    return TeamHealthCard(
        team_id=team_id,
        team_name=team_name,
        composite_score=composite_score,
        rag=rag,
        open_pr_count=open_pr_count,
        sprint_completion_pct=sprint_completion_pct,
        active_incident_count=active_incident_count,
        sparkline_7d=sparkline_7d,
    )


async def _open_pr_count(team_id: UUID, db: AsyncSession) -> int:
    """Count open PRs for a team directly from pull_requests table."""
    from app.models.github import PullRequest

    result = await db.execute(
        select(func.count()).select_from(PullRequest).where(
            and_(PullRequest.team_id == team_id, PullRequest.state == "open")
        )
    )
    return result.scalar_one() or 0


async def _sprint_completion_pct(team_id: UUID, db: AsyncSession) -> float | None:
    """Return current sprint completion % from the most recent sprint_health snapshot.

    This is a best-effort read from stored JSON payload; falls back to None.
    """
    # The sprint_health snapshot stores score only; completion is a metric detail.
    # For the overview card we recompute from tickets if recent data is available.
    from app.models.tickets import Sprint, Ticket

    active_sprint_result = await db.execute(
        select(Sprint).where(
            and_(Sprint.team_id == team_id, Sprint.state == "active")
        ).limit(1)
    )
    sprint = active_sprint_result.scalar_one_or_none()
    if sprint is None:
        return None

    total_result = await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.sprint_id == sprint.id)
    )
    total = total_result.scalar_one() or 0
    if total == 0:
        return None

    done_result = await db.execute(
        select(func.count()).select_from(Ticket).where(
            and_(
                Ticket.sprint_id == sprint.id,
                Ticket.status.in_(("done", "closed", "resolved", "complete", "completed")),
            )
        )
    )
    done = done_result.scalar_one() or 0
    return round(done / total * 100, 1)


async def _active_incident_count(team_id: UUID, db: AsyncSession) -> int:
    """Count incidents that are triggered but not yet resolved."""
    result = await db.execute(
        select(func.count()).select_from(Incident).where(
            and_(
                Incident.team_id == team_id,
                Incident.resolved_at.is_(None),
            )
        )
    )
    return result.scalar_one() or 0
