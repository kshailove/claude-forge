"""Engineers API router.

Endpoints:
  GET /api/v1/engineers             — list engineers (RBAC scoped)
  GET /api/v1/engineers/{user_id}   — engineer detail (own profile or EM+)

Spec reference: §8 M5a
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import CurrentUser, get_current_user
from app.models.github import PRReview, PullRequest
from app.models.incidents import Incident, IncidentAssignment, OncallShift
from app.models.team import Team, TeamMembership
from app.models.tickets import Sprint, Ticket
from app.models.user import User
from app.schemas.engineers import (
    CodeActivity,
    Collaboration,
    EngineerDetailResponse,
    EngineerSummary,
    EngineersListResponse,
    IncidentLoad,
    ReviewActivity,
    ReviewPartner,
    TaskDelivery,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/engineers", tags=["engineers"])

_WINDOW_DAYS = 30
_DONE_STATUSES = frozenset({"done", "closed", "resolved", "complete", "completed"})
_HIGH_LOAD_WIP = 3  # open PRs threshold for "high" load
_HIGH_LOAD_PAGES = 5  # paging count threshold for "high" load


# ---------------------------------------------------------------------------
# GET /api/v1/engineers
# ---------------------------------------------------------------------------


@router.get("", response_model=EngineersListResponse)
async def list_engineers(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineersListResponse:
    """List engineers with per-engineer metrics.

    EM: returns only their own team's engineers.
    Director/Admin: returns all engineers.
    Engineer role: returns empty list (engineers access own profile via detail endpoint).
    """
    window_start = datetime.now(tz=timezone.utc) - timedelta(days=_WINDOW_DAYS)

    if current_user.is_director_or_above:
        users_result = await db.execute(
            select(User).where(User.role == "engineer").order_by(User.username)
        )
        engineers: list[User] = list(users_result.scalars().all())
    elif current_user.is_em_or_above and current_user.team_id is not None:
        # EM: only their team's engineers
        memberships_result = await db.execute(
            select(TeamMembership.user_id).where(
                TeamMembership.team_id == current_user.team_id
            )
        )
        member_ids = [row[0] for row in memberships_result.all()]
        if not member_ids:
            return EngineersListResponse(engineers=[], total=0)
        users_result = await db.execute(
            select(User)
            .where(and_(User.id.in_(member_ids), User.role == "engineer"))
            .order_by(User.username)
        )
        engineers = list(users_result.scalars().all())
    else:
        # Engineer or unauthenticated edge-case — return empty
        return EngineersListResponse(engineers=[], total=0)

    summaries: list[EngineerSummary] = []
    for eng in engineers:
        team_name = await _get_team_name(eng, db)

        # PRs authored in window
        pr_authored = await _count_prs_authored(eng.id, window_start, db)
        # PRs merged in window
        pr_merged = await _count_prs_merged(eng.id, window_start, db)
        # Tickets closed in window
        tickets_closed = await _count_tickets_closed(eng.id, window_start, db)
        # Pages received in window (incident assignments)
        pages = await _count_pages_received(eng.id, window_start, db)

        # Composite load indicator: based on open PR count + paging count
        open_prs = await _count_open_prs(eng.id, db)
        load = _compute_load_indicator(open_prs, pages)

        summaries.append(
            EngineerSummary(
                user_id=eng.id,
                name=eng.username,
                email=eng.email,
                role=eng.role,
                team_name=team_name,
                composite_load_indicator=load,
                pr_authored_30d=pr_authored,
                pr_merged_30d=pr_merged,
                tickets_closed_30d=tickets_closed,
                incidents_paged_30d=pages,
            )
        )

    return EngineersListResponse(engineers=summaries, total=len(summaries))


# ---------------------------------------------------------------------------
# GET /api/v1/engineers/{user_id}
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=EngineerDetailResponse)
async def get_engineer_detail(
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EngineerDetailResponse:
    """Return engineer detail.

    Engineer role: can only access own profile — return 404 for privacy.
    EM: can access engineers on their team; 404 for others.
    Director/Admin: can access any engineer.
    """
    # Resolve engineer
    eng_result = await db.execute(select(User).where(User.id == user_id))
    eng: User | None = eng_result.scalar_one_or_none()
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # RBAC: engineer can only see own profile
    if not current_user.is_em_or_above:
        if current_user.id != user_id:
            # Return 404 (not 403) for privacy per spec
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # EM: can only see engineers on their team
    if current_user.is_em_or_above and not current_user.is_director_or_above:
        if eng.team_id != current_user.team_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    window_start = datetime.now(tz=timezone.utc) - timedelta(days=_WINDOW_DAYS)
    now = datetime.now(tz=timezone.utc)

    team_name = await _get_team_name(eng, db)

    # Code Activity
    code_activity = await _build_code_activity(eng.id, window_start, now, db)

    # Review Activity
    review_activity = await _build_review_activity(eng.id, window_start, db)

    # Task Delivery
    task_delivery = await _build_task_delivery(eng.id, window_start, db)

    # Incident Load
    incident_load = await _build_incident_load(eng.id, window_start, now, db)

    # Collaboration
    collaboration = await _build_collaboration(eng.id, window_start, db)

    return EngineerDetailResponse(
        user_id=eng.id,
        name=eng.username,
        email=eng.email,
        role=eng.role,
        team_name=team_name,
        code_activity=code_activity,
        review_activity=review_activity,
        task_delivery=task_delivery,
        incident_load=incident_load,
        collaboration=collaboration,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_load_indicator(open_prs: int, pages_30d: int) -> str:
    if open_prs >= _HIGH_LOAD_WIP or pages_30d >= _HIGH_LOAD_PAGES:
        return "high"
    if open_prs >= 2 or pages_30d >= 2:
        return "medium"
    return "low"


async def _get_team_name(eng: User, db: AsyncSession) -> str | None:
    if eng.team_id is None:
        return None
    team_result = await db.execute(
        select(Team.name).where(Team.id == eng.team_id)
    )
    return team_result.scalar_one_or_none()


async def _count_prs_authored(user_id: UUID, since: datetime, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(PullRequest).where(
            and_(
                PullRequest.author_user_id == user_id,
                PullRequest.created_at >= since,
            )
        )
    )
    return result.scalar_one() or 0


async def _count_prs_merged(user_id: UUID, since: datetime, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(PullRequest).where(
            and_(
                PullRequest.author_user_id == user_id,
                PullRequest.merged_at >= since,
                PullRequest.state == "merged",
            )
        )
    )
    return result.scalar_one() or 0


async def _count_open_prs(user_id: UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(PullRequest).where(
            and_(
                PullRequest.author_user_id == user_id,
                PullRequest.state == "open",
            )
        )
    )
    return result.scalar_one() or 0


async def _count_tickets_closed(user_id: UUID, since: datetime, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(Ticket).where(
            and_(
                Ticket.assignee_user_id == user_id,
                Ticket.completed_at >= since,
                Ticket.status.in_(_DONE_STATUSES),
            )
        )
    )
    return result.scalar_one() or 0


async def _count_pages_received(user_id: UUID, since: datetime, db: AsyncSession) -> int:
    """Count incidents where the engineer was paged (assigned) in the window."""
    result = await db.execute(
        select(func.count()).select_from(IncidentAssignment).join(
            Incident, Incident.id == IncidentAssignment.incident_id
        ).where(
            and_(
                IncidentAssignment.user_id == user_id,
                Incident.triggered_at >= since,
            )
        )
    )
    return result.scalar_one() or 0


async def _build_code_activity(
    user_id: UUID, since: datetime, now: datetime, db: AsyncSession
) -> CodeActivity:
    authored = await _count_prs_authored(user_id, since, db)
    merged = await _count_prs_merged(user_id, since, db)

    # Avg cycle time for merged PRs in window
    cycle_result = await db.execute(
        select(func.avg(PullRequest.cycle_time_seconds)).where(
            and_(
                PullRequest.author_user_id == user_id,
                PullRequest.merged_at >= since,
                PullRequest.cycle_time_seconds.isnot(None),
            )
        )
    )
    avg_cycle = cycle_result.scalar_one_or_none()

    # PR size trend: avg PR size (additions+deletions) per week for last 4 weeks
    pr_size_trend: list[float] = []
    for week_offset in range(3, -1, -1):
        week_start = now - timedelta(days=(week_offset + 1) * 7)
        week_end = now - timedelta(days=week_offset * 7)
        size_result = await db.execute(
            select(func.avg(PullRequest.pr_size_additions + PullRequest.pr_size_deletions)).where(
                and_(
                    PullRequest.author_user_id == user_id,
                    PullRequest.created_at >= week_start,
                    PullRequest.created_at < week_end,
                )
            )
        )
        avg_size = size_result.scalar_one_or_none()
        pr_size_trend.append(round(float(avg_size), 1) if avg_size is not None else 0.0)

    return CodeActivity(
        prs_authored=authored,
        prs_merged=merged,
        avg_cycle_time_seconds=float(avg_cycle) if avg_cycle is not None else None,
        pr_size_trend=pr_size_trend,
    )


async def _build_review_activity(
    user_id: UUID, since: datetime, db: AsyncSession
) -> ReviewActivity:
    # Count distinct PRs reviewed by this user
    reviews_result = await db.execute(
        select(func.count()).select_from(PRReview).where(
            and_(
                PRReview.reviewer_user_id == user_id,
                PRReview.submitted_at >= since,
            )
        )
    )
    prs_reviewed = reviews_result.scalar_one() or 0

    # Avg first review latency: time from PR created_at to first_review_at for PRs this user reviewed
    latency_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", PullRequest.first_review_at)
                - func.extract("epoch", PullRequest.created_at)
            )
        ).join(PRReview, PRReview.pr_id == PullRequest.id).where(
            and_(
                PRReview.reviewer_user_id == user_id,
                PRReview.submitted_at >= since,
                PullRequest.first_review_at.isnot(None),
            )
        )
    )
    avg_latency = latency_result.scalar_one_or_none()

    # Avg review depth: avg comment_count per review
    depth_result = await db.execute(
        select(func.avg(PRReview.comment_count)).where(
            and_(
                PRReview.reviewer_user_id == user_id,
                PRReview.submitted_at >= since,
            )
        )
    )
    avg_depth = depth_result.scalar_one_or_none()

    return ReviewActivity(
        prs_reviewed=prs_reviewed,
        avg_first_review_latency_seconds=float(avg_latency) if avg_latency is not None else None,
        avg_review_depth=float(avg_depth) if avg_depth is not None else None,
    )


async def _build_task_delivery(
    user_id: UUID, since: datetime, db: AsyncSession
) -> TaskDelivery:
    tickets_closed = await _count_tickets_closed(user_id, since, db)

    # Avg ticket cycle time: completed_at - started_at for closed tickets
    cycle_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", Ticket.completed_at)
                - func.extract("epoch", Ticket.started_at)
            )
        ).where(
            and_(
                Ticket.assignee_user_id == user_id,
                Ticket.completed_at >= since,
                Ticket.status.in_(_DONE_STATUSES),
                Ticket.started_at.isnot(None),
            )
        )
    )
    avg_ticket_cycle = cycle_result.scalar_one_or_none()

    # Carry-over: tickets assigned to this user in a completed sprint but not done
    # Find all completed sprints in window
    completed_sprints_result = await db.execute(
        select(Sprint.id).where(
            and_(
                Sprint.state.in_(("completed", "closed")),
                Sprint.end_date.isnot(None),
            )
        )
    )
    completed_sprint_ids = [row[0] for row in completed_sprints_result.all()]

    carry_over = 0
    if completed_sprint_ids:
        carry_result = await db.execute(
            select(func.count()).select_from(Ticket).where(
                and_(
                    Ticket.assignee_user_id == user_id,
                    Ticket.sprint_id.in_(completed_sprint_ids),
                    Ticket.status.notin_(_DONE_STATUSES),
                )
            )
        )
        carry_over = carry_result.scalar_one() or 0

    return TaskDelivery(
        tickets_closed=tickets_closed,
        avg_ticket_cycle_time_seconds=float(avg_ticket_cycle) if avg_ticket_cycle is not None else None,
        carry_over_count=carry_over,
    )


async def _build_incident_load(
    user_id: UUID, since: datetime, now: datetime, db: AsyncSession
) -> IncidentLoad:
    pages = await _count_pages_received(user_id, since, db)

    # Personal avg MTTR for incidents assigned to this engineer in the window
    mttr_result = await db.execute(
        select(func.avg(Incident.mttr_seconds)).join(
            IncidentAssignment, IncidentAssignment.incident_id == Incident.id
        ).where(
            and_(
                IncidentAssignment.user_id == user_id,
                Incident.triggered_at >= since,
                Incident.mttr_seconds.isnot(None),
            )
        )
    )
    avg_mttr = mttr_result.scalar_one_or_none()

    # On-call hours in window from OncallShift
    shifts_result = await db.execute(
        select(OncallShift).where(
            and_(
                OncallShift.user_id == user_id,
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

    return IncidentLoad(
        pages_received=pages,
        personal_avg_mttr_seconds=float(avg_mttr) if avg_mttr is not None else None,
        on_call_hours=round(on_call_hours, 1),
    )


async def _build_collaboration(
    user_id: UUID, since: datetime, db: AsyncSession
) -> Collaboration:
    """Find engineers who most often review this user's PRs (top review partners)."""
    # Get PRs authored by this user in the window
    authored_prs_result = await db.execute(
        select(PullRequest.id).where(
            and_(
                PullRequest.author_user_id == user_id,
                PullRequest.created_at >= since,
            )
        )
    )
    pr_ids = [row[0] for row in authored_prs_result.all()]

    if not pr_ids:
        return Collaboration(top_review_partners=[])

    # Count reviews per reviewer on those PRs
    reviewer_counts_result = await db.execute(
        select(PRReview.reviewer_user_id, func.count().label("review_count"))
        .where(
            and_(
                PRReview.pr_id.in_(pr_ids),
                PRReview.reviewer_user_id.isnot(None),
                PRReview.reviewer_user_id != user_id,
            )
        )
        .group_by(PRReview.reviewer_user_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    rows = reviewer_counts_result.all()

    partners: list[ReviewPartner] = []
    for reviewer_id, review_count in rows:
        reviewer_result = await db.execute(
            select(User).where(User.id == reviewer_id)
        )
        reviewer: User | None = reviewer_result.scalar_one_or_none()
        if reviewer is not None:
            partners.append(
                ReviewPartner(
                    user_id=reviewer.id,
                    name=reviewer.username,
                    review_count=review_count,
                )
            )

    return Collaboration(top_review_partners=partners)
