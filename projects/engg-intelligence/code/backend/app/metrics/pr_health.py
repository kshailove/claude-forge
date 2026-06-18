"""PR Health metric computation engine.

Computes all PR Health metrics and the overall PR Health score (0–100)
for a team within a rolling time window.

Spec reference: §5.8, §5.3 (M1c), tech-spec Section 5 scoring table
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.github import PRReview, PullRequest
from app.models.metrics import TeamMetricSnapshot
from app.models.team import TeamMembership

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pydantic v2 metrics dataclass
# ---------------------------------------------------------------------------


class PRHealthMetrics(BaseModel):
    """All computed PR Health metrics for a team within the window."""

    # Cycle time
    avg_cycle_time_seconds: float | None = None
    p50_cycle_time_seconds: float | None = None
    p75_cycle_time_seconds: float | None = None
    p95_cycle_time_seconds: float | None = None

    # Review latency
    avg_first_review_latency_seconds: float | None = None
    p50_first_review_latency_seconds: float | None = None

    # Review turnaround (time between consecutive reviews on same PR)
    avg_review_turnaround_seconds: float | None = None

    # Stale PRs (open PRs with no activity in > 3 days)
    stale_pr_count: int = 0
    stale_pr_threshold_days: int = 3

    # PR size
    pr_size_p50_lines: float | None = None
    pr_size_p95_lines: float | None = None

    # Coverage & participation
    review_coverage_pct: float | None = None  # % merged PRs with >= 1 review
    review_participation_pct: float | None = None  # % team engineers who reviewed >= 1 PR

    # Review depth
    avg_review_depth: float | None = None  # mean comment_count per review

    # Rework rate
    rework_rate_pct: float | None = None  # % PRs closed without merge

    # Author distribution (bus factor signal)
    author_count: int = 0

    # Computed window
    window_days: int = 30
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    # PR counts used in computation
    merged_pr_count: int = 0
    open_pr_count: int = 0
    closed_without_merge_count: int = 0


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


async def compute_pr_health(
    team_id: UUID,
    db: AsyncSession,
    window_days: int = 30,
) -> PRHealthMetrics:
    """Compute all PR Health metrics for a team within the rolling window.

    Args:
        team_id: Team UUID.
        db: Async SQLAlchemy session.
        window_days: Rolling window in days (default 30).

    Returns:
        PRHealthMetrics instance with all computed metrics.
    """
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=window_days)
    stale_threshold = now - timedelta(days=3)

    # ---- Merged PRs (cycle time, review coverage, rework) ----
    merged_prs_result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.team_id == team_id,
                PullRequest.state == "merged",
                PullRequest.merged_at >= window_start,
                PullRequest.merged_at.is_not(None),
            )
        )
    )
    merged_prs: Sequence[PullRequest] = merged_prs_result.scalars().all()

    # ---- Open PRs (stale detection) ----
    open_prs_result = await db.execute(
        select(PullRequest).where(
            and_(
                PullRequest.team_id == team_id,
                PullRequest.state == "open",
            )
        )
    )
    open_prs: Sequence[PullRequest] = open_prs_result.scalars().all()

    # ---- Closed-without-merge PRs ----
    closed_prs_result = await db.execute(
        select(func.count()).select_from(PullRequest).where(
            and_(
                PullRequest.team_id == team_id,
                PullRequest.state == "closed",
                PullRequest.merged_at.is_(None),
                PullRequest.closed_at >= window_start,
            )
        )
    )
    closed_without_merge_count: int = closed_prs_result.scalar_one() or 0

    # ---- All reviews for merged PRs in window ----
    pr_ids = [pr.id for pr in merged_prs]
    reviews_by_pr: dict[UUID, list[PRReview]] = {}
    if pr_ids:
        reviews_result = await db.execute(
            select(PRReview).where(PRReview.pr_id.in_(pr_ids))
        )
        for review in reviews_result.scalars().all():
            reviews_by_pr.setdefault(review.pr_id, []).append(review)

    # ---- Team member count (for participation %) ----
    members_result = await db.execute(
        select(func.count()).select_from(TeamMembership).where(
            TeamMembership.team_id == team_id
        )
    )
    team_member_count: int = members_result.scalar_one() or 0

    # ---- Compute cycle time metrics ----
    cycle_times = [
        pr.cycle_time_seconds
        for pr in merged_prs
        if pr.cycle_time_seconds is not None
    ]

    avg_cycle_time = _safe_mean(cycle_times)
    p50_cycle_time = _safe_percentile(cycle_times, 50)
    p75_cycle_time = _safe_percentile(cycle_times, 75)
    p95_cycle_time = _safe_percentile(cycle_times, 95)

    # ---- First review latency ----
    first_review_latencies: list[float] = []
    for pr in merged_prs:
        if pr.first_review_at and pr.created_at:
            latency = (pr.first_review_at - pr.created_at).total_seconds()
            if latency >= 0:
                first_review_latencies.append(latency)

    avg_first_review_latency = _safe_mean(first_review_latencies)
    p50_first_review_latency = _safe_percentile(first_review_latencies, 50)

    # ---- Review turnaround (time between consecutive reviews on same PR) ----
    turnaround_times: list[float] = []
    for pr_id, pr_reviews in reviews_by_pr.items():
        sorted_reviews = sorted(pr_reviews, key=lambda r: r.submitted_at)
        for i in range(1, len(sorted_reviews)):
            delta = (sorted_reviews[i].submitted_at - sorted_reviews[i - 1].submitted_at).total_seconds()
            if delta >= 0:
                turnaround_times.append(delta)

    avg_review_turnaround = _safe_mean(turnaround_times)

    # ---- Stale PR count ----
    stale_pr_count = sum(
        1 for pr in open_prs if pr.last_activity_at < stale_threshold
    )

    # ---- PR size ----
    pr_sizes = [
        (pr.pr_size_additions or 0) + (pr.pr_size_deletions or 0)
        for pr in merged_prs
    ]
    pr_size_p50 = _safe_percentile(pr_sizes, 50)
    pr_size_p95 = _safe_percentile(pr_sizes, 95)

    # ---- Review coverage % ----
    reviewed_pr_count = sum(1 for pr_id, revs in reviews_by_pr.items() if len(revs) >= 1)
    review_coverage_pct: float | None = None
    if merged_prs:
        review_coverage_pct = round(reviewed_pr_count / len(merged_prs) * 100, 1)

    # ---- Review participation % ----
    reviewing_user_ids: set[UUID] = set()
    for pr_reviews_list in reviews_by_pr.values():
        for review in pr_reviews_list:
            if review.reviewer_user_id is not None:
                reviewing_user_ids.add(review.reviewer_user_id)

    review_participation_pct: float | None = None
    if team_member_count > 0:
        review_participation_pct = round(
            len(reviewing_user_ids) / team_member_count * 100, 1
        )

    # ---- Average review depth (comment_count per review) ----
    all_review_comment_counts = [
        review.comment_count
        for pr_reviews_list in reviews_by_pr.values()
        for review in pr_reviews_list
    ]
    avg_review_depth = _safe_mean(all_review_comment_counts)

    # ---- Rework rate % ----
    total_closed = len(merged_prs) + closed_without_merge_count
    rework_rate_pct: float | None = None
    if total_closed > 0:
        rework_rate_pct = round(closed_without_merge_count / total_closed * 100, 1)

    # ---- Author count ----
    author_ids: set[UUID] = set()
    for pr in merged_prs:
        if pr.author_user_id is not None:
            author_ids.add(pr.author_user_id)
    author_count = len(author_ids)

    return PRHealthMetrics(
        avg_cycle_time_seconds=avg_cycle_time,
        p50_cycle_time_seconds=p50_cycle_time,
        p75_cycle_time_seconds=p75_cycle_time,
        p95_cycle_time_seconds=p95_cycle_time,
        avg_first_review_latency_seconds=avg_first_review_latency,
        p50_first_review_latency_seconds=p50_first_review_latency,
        avg_review_turnaround_seconds=avg_review_turnaround,
        stale_pr_count=stale_pr_count,
        stale_pr_threshold_days=3,
        pr_size_p50_lines=pr_size_p50,
        pr_size_p95_lines=pr_size_p95,
        review_coverage_pct=review_coverage_pct,
        review_participation_pct=review_participation_pct,
        avg_review_depth=avg_review_depth,
        rework_rate_pct=rework_rate_pct,
        author_count=author_count,
        window_days=window_days,
        merged_pr_count=len(merged_prs),
        open_pr_count=len(open_prs),
        closed_without_merge_count=closed_without_merge_count,
    )


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def compute_pr_health_score(metrics: PRHealthMetrics) -> float:
    """Compute overall PR Health score (0–100) from computed metrics.

    Scoring formula from tech-spec §M1c:
    Each metric sub-score (0–100) is computed using DORA band thresholds
    with linear interpolation between bands.

    Weights:
    - Cycle time p50:         25%
    - First review latency p50: 20%
    - Stale PRs:              20%
    - Review coverage %:      15%
    - Review participation %: 10%
    - Rework rate %:          10%

    Returns 0.0 if no data is available (returned as "Insufficient data" by API).
    """
    sub_scores: list[tuple[float, float]] = []  # (score, weight)

    # --- Cycle time p50 (seconds → hours for threshold comparison) ---
    if metrics.p50_cycle_time_seconds is not None:
        hours = metrics.p50_cycle_time_seconds / 3600
        score = _interpolate_score(
            value=hours,
            green_max=24.0,   # < 24h → 100
            amber_max=72.0,   # 24–72h → 50
            # > 72h → 0
            high_is_bad=True,
        )
        sub_scores.append((score, 0.25))

    # --- First review latency p50 ---
    if metrics.p50_first_review_latency_seconds is not None:
        hours = metrics.p50_first_review_latency_seconds / 3600
        score = _interpolate_score(
            value=hours,
            green_max=4.0,    # < 4h → 100
            amber_max=24.0,   # 4–24h → 50
            high_is_bad=True,
        )
        sub_scores.append((score, 0.20))

    # --- Stale PR count ---
    # Only include stale score if there is actual PR activity (otherwise no data)
    if metrics.merged_pr_count > 0 or metrics.open_pr_count > 0:
        stale = metrics.stale_pr_count
        if stale == 0:
            stale_score = 100.0
        elif stale <= 2:
            stale_score = _lerp(stale, 0, 2, 100.0, 50.0)
        else:
            # >= 3 → score 0; interpolate downward from 50 → 0 as stale increases
            stale_score = max(0.0, _lerp(stale, 2, 10, 50.0, 0.0))
        sub_scores.append((stale_score, 0.20))

    # --- Review coverage % ---
    if metrics.review_coverage_pct is not None:
        cov = metrics.review_coverage_pct
        if cov >= 90.0:
            cov_score = 100.0
        elif cov >= 70.0:
            cov_score = _lerp(cov, 70.0, 90.0, 50.0, 100.0)
        else:
            cov_score = max(0.0, _lerp(cov, 0.0, 70.0, 0.0, 50.0))
        sub_scores.append((cov_score, 0.15))

    # --- Review participation % ---
    if metrics.review_participation_pct is not None:
        part = metrics.review_participation_pct
        if part >= 75.0:
            part_score = 100.0
        elif part >= 50.0:
            part_score = _lerp(part, 50.0, 75.0, 50.0, 100.0)
        else:
            part_score = max(0.0, _lerp(part, 0.0, 50.0, 0.0, 50.0))
        sub_scores.append((part_score, 0.10))

    # --- Rework rate % ---
    if metrics.rework_rate_pct is not None:
        rework = metrics.rework_rate_pct
        score = _interpolate_score(
            value=rework,
            green_max=5.0,    # < 5% → 100
            amber_max=15.0,   # 5–15% → 50
            high_is_bad=True,
        )
        sub_scores.append((score, 0.10))

    if not sub_scores:
        return 0.0

    # Normalise weights to sum to 1.0 (some sub-scores may be missing)
    total_weight = sum(w for _, w in sub_scores)
    if total_weight == 0:
        return 0.0

    weighted_score = sum(s * w for s, w in sub_scores) / total_weight
    return round(min(100.0, max(0.0, weighted_score)), 2)


def _rag_from_score(score: float) -> str:
    """Return RAG status based on score. Red: 0–39, Amber: 40–69, Green: 70–100."""
    if score >= 70.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"


# ---------------------------------------------------------------------------
# Write snapshot to DB
# ---------------------------------------------------------------------------


async def write_pr_health_snapshot(
    team_id: UUID,
    db: AsyncSession,
    window_days: int = 30,
) -> TeamMetricSnapshot:
    """Compute PR Health metrics and write a snapshot to ``team_metric_snapshots``.

    Called by the nightly chord callback ``run_metric_computation``.

    Returns:
        The inserted TeamMetricSnapshot row.
    """
    now = datetime.now(tz=timezone.utc)

    metrics = await compute_pr_health(team_id=team_id, db=db, window_days=window_days)
    score = compute_pr_health_score(metrics)
    rag = _rag_from_score(score)

    from decimal import Decimal
    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="pr_health",
        score=Decimal(str(round(score, 2))),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "pr_health_snapshot_written",
        team_id=str(team_id),
        score=score,
        rag=rag,
        merged_prs=metrics.merged_pr_count,
        stale_prs=metrics.stale_pr_count,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _safe_mean(values: list[float]) -> float | None:
    """Return mean of a list, or None if empty."""
    if not values:
        return None
    return statistics.mean(values)


def _safe_percentile(values: list[float], percentile: int) -> float | None:
    """Return the p-th percentile of a list using nearest-rank method."""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    idx = max(0, min(n - 1, int(percentile / 100 * n + 0.5) - 1))
    return float(sorted_vals[idx])


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
    """Map a metric value to a 0–100 score using DORA-style thresholds.

    For high_is_bad=True (lower value is better):
        value <= green_max  → 100 (green)
        green_max < value <= amber_max → lerp 100→50 (amber)
        value > amber_max → lerp 50→0 (red)
    """
    if high_is_bad:
        if value <= green_max:
            return 100.0
        if value <= amber_max:
            return _lerp(value, green_max, amber_max, 100.0, 50.0)
        # Beyond amber threshold — interpolate 50→0 over 2x the amber range
        red_max = amber_max + (amber_max - green_max)
        return max(0.0, _lerp(value, amber_max, red_max, 50.0, 0.0))
    else:
        # low_is_bad: higher value is better
        if value >= green_max:
            return 100.0
        if value >= amber_max:
            return _lerp(value, amber_max, green_max, 50.0, 100.0)
        return max(0.0, _lerp(value, 0.0, amber_max, 0.0, 50.0))
