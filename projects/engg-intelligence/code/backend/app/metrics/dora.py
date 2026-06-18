"""DORA (DevOps Research and Assessment) metrics computation engine.

Computes the four DORA key metrics for a team within a rolling window:
  1. Deployment Frequency — from github_releases
  2. Lead Time for Changes — merged PR first-commit to merge time
  3. Change Failure Rate — (P1+P2 incidents) / releases * 100
  4. Mean Time to Restore (MTTR) — from incident_load avg_mttr_seconds

Spec reference: §5.7, §8 M3c
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

from app.models.github import Commit, GithubRelease, PullRequest
from app.models.incidents import Incident
from app.models.metrics import TeamMetricSnapshot

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Band classification constants
# ---------------------------------------------------------------------------

# Deployment frequency thresholds (per day)
DF_ELITE_PER_DAY = 1.0      # ≥1/day
DF_HIGH_PER_WEEK = 1 / 7    # ≥1/week (≈0.143/day)
DF_MEDIUM_PER_MONTH = 1 / 30  # ≥1/month (≈0.033/day)

# Lead time thresholds (seconds)
LT_ELITE_SECS = 3_600       # < 1 hour
LT_HIGH_SECS = 86_400       # < 1 day
LT_MEDIUM_SECS = 604_800    # < 1 week

# Change failure rate thresholds (%)
CFR_ELITE_PCT = 5.0
CFR_HIGH_PCT = 10.0
CFR_MEDIUM_PCT = 15.0

# MTTR thresholds (seconds)
MTTR_ELITE_SECS = 3_600     # < 1 hour
MTTR_HIGH_SECS = 86_400     # < 1 day
MTTR_MEDIUM_SECS = 604_800  # < 1 week


# ---------------------------------------------------------------------------
# Pydantic v2 metrics model
# ---------------------------------------------------------------------------


class DORAMetrics(BaseModel):
    """All four DORA key metrics for a team within the window."""

    # 1. Deployment Frequency
    deployment_frequency: int | None = 0    # total deployments in window
    deployment_frequency_per_day: float = 0.0
    deployment_frequency_band: str = "low"  # "elite"|"high"|"medium"|"low"

    # 2. Lead Time for Changes
    lead_time_for_changes_seconds: float | None = None
    lead_time_band: str = "low"

    # 3. Change Failure Rate
    change_failure_rate_pct: float | None = None  # None if no releases
    change_failure_rate_band: str = "low"

    # 4. Mean Time to Restore
    mttr_seconds: float | None = None
    mttr_band: str = "low"

    # Window metadata
    window_days: int = 30
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


async def compute_dora_metrics(
    team_id: UUID,
    db: AsyncSession,
    window_days: int = 30,
) -> DORAMetrics:
    """Compute all four DORA metrics for a team within the rolling window.

    Args:
        team_id: Team UUID.
        db: Async SQLAlchemy session.
        window_days: Rolling window in days (default 30).

    Returns:
        DORAMetrics instance with all fields populated.
    """
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=window_days)

    # ---- 1. Deployment Frequency — github_releases in window ----
    releases_result = await db.execute(
        select(GithubRelease).where(
            and_(
                GithubRelease.team_id == team_id,
                GithubRelease.published_at >= window_start,
                GithubRelease.published_at <= now,
            )
        )
    )
    releases = releases_result.scalars().all()
    deployment_frequency = len(releases)
    deployment_frequency_per_day = (
        deployment_frequency / window_days if window_days > 0 else 0.0
    )
    deployment_frequency_band = _df_band(deployment_frequency_per_day)

    # ---- 2. Lead Time for Changes ----
    # For each merged PR in window: merged_at - min(commit.committed_at)
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
    merged_prs = merged_prs_result.scalars().all()

    lead_times: list[float] = []
    for pr in merged_prs:
        if pr.merged_at is None:
            continue
        # Fetch the earliest commit in this PR
        earliest_commit_result = await db.execute(
            select(func.min(Commit.committed_at)).where(
                Commit.pr_id == pr.id
            )
        )
        earliest_commit_at = earliest_commit_result.scalar_one_or_none()
        if earliest_commit_at is None:
            # No commits linked — skip
            continue
        # Ensure timezone-aware comparison
        merged_at = pr.merged_at
        if merged_at.tzinfo is None:
            merged_at = merged_at.replace(tzinfo=timezone.utc)
        if earliest_commit_at.tzinfo is None:
            earliest_commit_at = earliest_commit_at.replace(tzinfo=timezone.utc)

        lt = (merged_at - earliest_commit_at).total_seconds()
        if lt >= 0:
            lead_times.append(lt)

    lead_time_for_changes = _safe_mean(lead_times)
    lead_time_band = _lt_band(lead_time_for_changes)

    # ---- 3. Change Failure Rate ----
    # (P1 + P2 incidents triggered in window) / releases * 100
    if deployment_frequency > 0:
        high_sev_incidents_result = await db.execute(
            select(func.count()).select_from(Incident).where(
                and_(
                    Incident.team_id == team_id,
                    Incident.severity.in_(["p1", "p2"]),
                    Incident.triggered_at >= window_start,
                    Incident.triggered_at <= now,
                )
            )
        )
        high_sev_count = high_sev_incidents_result.scalar_one() or 0
        change_failure_rate_pct = min(100.0, (high_sev_count / deployment_frequency) * 100)
    else:
        change_failure_rate_pct = None

    change_failure_rate_band = _cfr_band(change_failure_rate_pct)

    # ---- 4. MTTR from incidents ----
    mttr_result = await db.execute(
        select(func.avg(Incident.mttr_seconds)).where(
            and_(
                Incident.team_id == team_id,
                Incident.mttr_seconds.is_not(None),
                Incident.triggered_at >= window_start,
                Incident.triggered_at <= now,
            )
        )
    )
    avg_mttr_raw = mttr_result.scalar_one_or_none()
    mttr_seconds = float(avg_mttr_raw) if avg_mttr_raw is not None else None
    mttr_band = _mttr_band(mttr_seconds)

    return DORAMetrics(
        deployment_frequency=deployment_frequency,
        deployment_frequency_per_day=round(deployment_frequency_per_day, 4),
        deployment_frequency_band=deployment_frequency_band,
        lead_time_for_changes_seconds=lead_time_for_changes,
        lead_time_band=lead_time_band,
        change_failure_rate_pct=change_failure_rate_pct,
        change_failure_rate_band=change_failure_rate_band,
        mttr_seconds=mttr_seconds,
        mttr_band=mttr_band,
        window_days=window_days,
    )


# ---------------------------------------------------------------------------
# Write snapshot to DB
# ---------------------------------------------------------------------------


async def write_dora_snapshot(
    team_id: UUID,
    metrics: DORAMetrics,
    db: AsyncSession,
) -> TeamMetricSnapshot:
    """Persist a DORA composite score snapshot to team_metric_snapshots.

    The composite score is a simple mean of the four band scores (0–100 each).
    Band → score: elite=100, high=75, medium=50, low=25.

    Args:
        team_id: Team UUID.
        metrics: Computed DORAMetrics.
        db: Async SQLAlchemy session (caller must commit).

    Returns:
        The inserted TeamMetricSnapshot row.
    """
    now = datetime.now(tz=timezone.utc)

    band_score_map = {"elite": 100.0, "high": 75.0, "medium": 50.0, "low": 25.0}
    band_scores = [
        band_score_map.get(metrics.deployment_frequency_band, 25.0),
        band_score_map.get(metrics.lead_time_band, 25.0),
        band_score_map.get(metrics.change_failure_rate_band, 25.0),
        band_score_map.get(metrics.mttr_band, 25.0),
    ]
    composite_score = statistics.mean(band_scores)
    rag = _rag_from_score(composite_score)

    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="dora",
        score=Decimal(str(round(composite_score, 2))),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "dora_snapshot_written",
        team_id=str(team_id),
        composite_score=composite_score,
        rag=rag,
        df_band=metrics.deployment_frequency_band,
        lt_band=metrics.lead_time_band,
        cfr_band=metrics.change_failure_rate_band,
        mttr_band=metrics.mttr_band,
    )
    return snapshot


# ---------------------------------------------------------------------------
# Band classifiers
# ---------------------------------------------------------------------------


def _df_band(per_day: float) -> str:
    """Classify deployment frequency per day into DORA bands."""
    if per_day >= DF_ELITE_PER_DAY:
        return "elite"
    if per_day >= DF_HIGH_PER_WEEK:
        return "high"
    if per_day >= DF_MEDIUM_PER_MONTH:
        return "medium"
    return "low"


def _lt_band(seconds: float | None) -> str:
    """Classify lead time for changes into DORA bands."""
    if seconds is None:
        return "low"
    if seconds < LT_ELITE_SECS:
        return "elite"
    if seconds < LT_HIGH_SECS:
        return "high"
    if seconds < LT_MEDIUM_SECS:
        return "medium"
    return "low"


def _cfr_band(pct: float | None) -> str:
    """Classify change failure rate % into DORA bands."""
    if pct is None:
        return "low"
    if pct < CFR_ELITE_PCT:
        return "elite"
    if pct < CFR_HIGH_PCT:
        return "high"
    if pct < CFR_MEDIUM_PCT:
        return "medium"
    return "low"


def _mttr_band(seconds: float | None) -> str:
    """Classify MTTR (seconds) into DORA bands."""
    if seconds is None:
        return "low"
    if seconds < MTTR_ELITE_SECS:
        return "elite"
    if seconds < MTTR_HIGH_SECS:
        return "high"
    if seconds < MTTR_MEDIUM_SECS:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return statistics.mean(values)


def _rag_from_score(score: float) -> str:
    if score >= 70.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"
