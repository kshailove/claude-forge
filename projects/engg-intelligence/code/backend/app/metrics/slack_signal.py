"""Slack Signal metric computation engine.

Computes Slack Signal health metrics (0–100) for a team within a rolling window.
Quantifies after-hours messaging patterns as a leading burnout indicator.

Degradation policy (spec §2.4):
    If the Slack integration is marked as degraded (workspace >200 members or >50
    channels), compute_slack_signal_score() returns None. The caller (orchestrator
    chord callback) redistributes the Slack Signal weight across other active
    metrics proportionally.

Scoring weights:
    - After-hours message percentage: 50%
    - Weekend message percentage:     30%
    - Volume stability:               20%

Spec reference: §8 M6c, §2.4 (degradation), §5 (scoring table)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metrics import TeamMetricSnapshot
from app.models.slack import SlackActivityBucket

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring thresholds
# ---------------------------------------------------------------------------

# After-hours pct: < 10% → 100, > 40% → 0 (linear)
AFTER_HOURS_GREEN_MAX_PCT = 10.0
AFTER_HOURS_RED_MIN_PCT = 40.0

# Weekend pct: < 5% → 100, > 25% → 0 (linear)
WEEKEND_GREEN_MAX_PCT = 5.0
WEEKEND_RED_MIN_PCT = 25.0

# Volume coefficient of variation: < 0.3 → 100 (stable), > 1.0 → 0 (highly variable)
VOLUME_CV_GREEN_MAX = 0.3
VOLUME_CV_RED_MIN = 1.0

# Burnout spike threshold: engineers sending >30% after-hours messages are flagged
AFTER_HOURS_SPIKE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Pydantic v2 metrics model
# ---------------------------------------------------------------------------


class SlackSignalMetrics(BaseModel):
    """All computed Slack Signal metrics for a team within the window."""

    degraded: bool = False
    degraded_reason: str | None = None

    # Core metrics (None if degraded or insufficient data)
    after_hours_message_pct: float | None = None   # % messages sent outside 09–18
    weekend_message_pct: float | None = None        # % messages sent on weekends
    avg_daily_message_volume: float | None = None   # mean messages per day

    # 7-day trend: one float per day (most recent last)
    message_volume_trend: list[float] | None = None

    # Engineers with >30% after-hours messages (potential burnout signal)
    engineers_with_after_hours_spike: list[str] | None = None  # canonical user_id strings

    # Placeholder: computed from channel activity gaps in a future iteration
    response_time_trend: list[float] | None = None

    # Metadata
    window_days: int = 30
    computed_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    total_message_count: int = 0


# ---------------------------------------------------------------------------
# Main computation function
# ---------------------------------------------------------------------------


async def compute_slack_signal(
    team_id: UUID,
    db: AsyncSession,
    window_days: int = 30,
) -> SlackSignalMetrics:
    """Compute all Slack Signal metrics for a team within the rolling window.

    If the Slack integration is degraded, returns a metrics object with
    degraded=True and all metric fields set to None. The score function
    will return None and the orchestrator will redistribute weights.

    Args:
        team_id: Team UUID.
        db: Async SQLAlchemy session.
        window_days: Rolling window in days (default 30).

    Returns:
        SlackSignalMetrics instance.
    """
    # --- Check degradation state ---
    from sqlalchemy import select as _sel
    from app.models.integration import Integration

    slack_result = await db.execute(
        _sel(Integration).where(Integration.type == "slack")
    )
    slack_integration = slack_result.scalar_one_or_none()

    if slack_integration is not None:
        try:
            config = slack_integration.get_config()
            if config.get("slack_signal_degraded"):
                reason = config.get(
                    "slack_degraded_reason",
                    "Workspace exceeds size thresholds (>200 members or >50 channels)",
                )
                logger.info(
                    "slack_signal_degraded",
                    team_id=str(team_id),
                    reason=reason,
                )
                return SlackSignalMetrics(
                    degraded=True,
                    degraded_reason=reason,
                    window_days=window_days,
                )
        except Exception:
            pass  # If we can't decrypt config, continue with computation attempt

    if slack_integration is None or slack_integration.status != "connected":
        return SlackSignalMetrics(
            degraded=True,
            degraded_reason="Slack integration not connected",
            window_days=window_days,
        )

    # --- Query time window ---
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=window_days)

    # --- Total message counts: all, after-hours, weekend ---
    total_q = await db.execute(
        select(func.sum(SlackActivityBucket.message_count)).where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
            )
        )
    )
    total_messages: int = total_q.scalar_one() or 0

    after_hours_q = await db.execute(
        select(func.sum(SlackActivityBucket.message_count)).where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
                SlackActivityBucket.is_after_hours.is_(True),
            )
        )
    )
    after_hours_messages: int = after_hours_q.scalar_one() or 0

    weekend_q = await db.execute(
        select(func.sum(SlackActivityBucket.message_count)).where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
                SlackActivityBucket.is_weekend.is_(True),
            )
        )
    )
    weekend_messages: int = weekend_q.scalar_one() or 0

    if total_messages == 0:
        # No data in window — insufficient data, return with nulls
        return SlackSignalMetrics(
            degraded=False,
            window_days=window_days,
            total_message_count=0,
        )

    after_hours_pct = round(after_hours_messages / total_messages * 100, 2)
    weekend_pct = round(weekend_messages / total_messages * 100, 2)

    # --- Daily volume trend (7 days) ---
    seven_days_ago = now - timedelta(days=7)
    daily_q = await db.execute(
        select(
            func.date_trunc("day", SlackActivityBucket.bucket_hour).label("day"),
            func.sum(SlackActivityBucket.message_count).label("daily_count"),
        )
        .where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= seven_days_ago,
            )
        )
        .group_by(func.date_trunc("day", SlackActivityBucket.bucket_hour))
        .order_by(func.date_trunc("day", SlackActivityBucket.bucket_hour))
    )
    daily_rows = daily_q.all()

    # Pad to 7 days (fill missing days with 0)
    daily_counts_by_day: dict[str, float] = {}
    for row in daily_rows:
        day_key = row.day.strftime("%Y-%m-%d") if hasattr(row.day, "strftime") else str(row.day)[:10]
        daily_counts_by_day[day_key] = float(row.daily_count or 0)

    message_volume_trend: list[float] = []
    for i in range(7):
        day = (seven_days_ago + timedelta(days=i)).strftime("%Y-%m-%d")
        message_volume_trend.append(daily_counts_by_day.get(day, 0.0))

    # Average daily volume over full window
    window_daily_q = await db.execute(
        select(
            func.date_trunc("day", SlackActivityBucket.bucket_hour).label("day"),
            func.sum(SlackActivityBucket.message_count).label("daily_count"),
        )
        .where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
            )
        )
        .group_by(func.date_trunc("day", SlackActivityBucket.bucket_hour))
    )
    window_daily_rows = window_daily_q.all()
    daily_volumes = [float(r.daily_count or 0) for r in window_daily_rows]
    avg_daily = round(sum(daily_volumes) / len(daily_volumes), 2) if daily_volumes else None

    # --- Per-engineer after-hours spike detection ---
    # Find engineers where after_hours_messages / total_messages > AFTER_HOURS_SPIKE_THRESHOLD
    eng_total_q = await db.execute(
        select(
            SlackActivityBucket.user_id,
            func.sum(SlackActivityBucket.message_count).label("total"),
        )
        .where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
            )
        )
        .group_by(SlackActivityBucket.user_id)
    )
    eng_totals = {str(row.user_id): int(row.total or 0) for row in eng_total_q.all()}

    eng_ah_q = await db.execute(
        select(
            SlackActivityBucket.user_id,
            func.sum(SlackActivityBucket.message_count).label("ah_total"),
        )
        .where(
            and_(
                SlackActivityBucket.team_id == team_id,
                SlackActivityBucket.bucket_hour >= window_start,
                SlackActivityBucket.is_after_hours.is_(True),
            )
        )
        .group_by(SlackActivityBucket.user_id)
    )
    eng_ah = {str(row.user_id): int(row.ah_total or 0) for row in eng_ah_q.all()}

    engineers_with_spike: list[str] = []
    for user_id_str, total in eng_totals.items():
        if total == 0:
            continue
        ah = eng_ah.get(user_id_str, 0)
        ah_ratio = ah / total
        if ah_ratio > AFTER_HOURS_SPIKE_THRESHOLD:
            engineers_with_spike.append(user_id_str)

    logger.info(
        "slack_signal_computed",
        team_id=str(team_id),
        total_messages=total_messages,
        after_hours_pct=after_hours_pct,
        weekend_pct=weekend_pct,
        avg_daily=avg_daily,
        spike_count=len(engineers_with_spike),
    )

    return SlackSignalMetrics(
        degraded=False,
        after_hours_message_pct=after_hours_pct,
        weekend_message_pct=weekend_pct,
        avg_daily_message_volume=avg_daily,
        message_volume_trend=message_volume_trend,
        engineers_with_after_hours_spike=engineers_with_spike if engineers_with_spike else None,
        response_time_trend=None,  # placeholder — computed from channel gaps in future
        window_days=window_days,
        total_message_count=total_messages,
    )


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def compute_slack_signal_score(metrics: SlackSignalMetrics) -> float | None:
    """Compute overall Slack Signal score (0–100) from computed metrics.

    Returns None if degraded — the orchestrator must redistribute this
    component's weight across other active metrics (spec §2.4).

    Score formula (weights sum to 100%):
    - After-hours message %: 50% (lower % → higher score)
    - Weekend message %:     30% (lower % → higher score)
    - Volume stability:      20% (lower CV → higher score)

    After-hours scoring:
        < 10% → 100
        > 40% → 0
        (linear interpolation in between)

    Weekend scoring:
        < 5%  → 100
        > 25% → 0
        (linear interpolation in between)

    Volume stability (coefficient of variation of daily counts):
        < 0.3 CV → 100 (very stable)
        > 1.0 CV → 0   (highly variable / spiky)
        (linear interpolation in between)

    Returns:
        Score 0.0–100.0, or None if degraded.
    """
    if metrics.degraded:
        return None

    sub_scores: list[tuple[float, float]] = []  # (score, weight)

    # --- After-hours % (50% weight) ---
    if metrics.after_hours_message_pct is not None:
        ah_score = _linear_score(
            value=metrics.after_hours_message_pct,
            good_max=AFTER_HOURS_GREEN_MAX_PCT,
            bad_min=AFTER_HOURS_RED_MIN_PCT,
            high_is_bad=True,
        )
        sub_scores.append((ah_score, 0.50))

    # --- Weekend % (30% weight) ---
    if metrics.weekend_message_pct is not None:
        we_score = _linear_score(
            value=metrics.weekend_message_pct,
            good_max=WEEKEND_GREEN_MAX_PCT,
            bad_min=WEEKEND_RED_MIN_PCT,
            high_is_bad=True,
        )
        sub_scores.append((we_score, 0.30))

    # --- Volume stability (20% weight) ---
    if metrics.message_volume_trend and len(metrics.message_volume_trend) >= 2:
        cv = _coefficient_of_variation(metrics.message_volume_trend)
        vol_score = _linear_score(
            value=cv,
            good_max=VOLUME_CV_GREEN_MAX,
            bad_min=VOLUME_CV_RED_MIN,
            high_is_bad=True,
        )
        sub_scores.append((vol_score, 0.20))

    if not sub_scores:
        # No data available — cannot score
        return None

    # Normalise weights in case some sub-scores are missing
    total_weight = sum(w for _, w in sub_scores)
    if total_weight == 0:
        return None

    weighted = sum(s * w for s, w in sub_scores) / total_weight
    return round(min(100.0, max(0.0, weighted)), 2)


def _linear_score(
    value: float,
    good_max: float,
    bad_min: float,
    high_is_bad: bool = True,
) -> float:
    """Map a metric value to a 0–100 score using linear interpolation.

    For high_is_bad=True (lower value is better):
        value <= good_max → 100
        value >= bad_min  → 0
        between           → linear interpolation
    """
    if high_is_bad:
        if value <= good_max:
            return 100.0
        if value >= bad_min:
            return 0.0
        # Linear interpolation
        t = (value - good_max) / (bad_min - good_max)
        return round(max(0.0, min(100.0, 100.0 * (1.0 - t))), 2)
    else:
        if value >= good_max:
            return 100.0
        if value <= bad_min:
            return 0.0
        t = (value - bad_min) / (good_max - bad_min)
        return round(max(0.0, min(100.0, 100.0 * t)), 2)


def _coefficient_of_variation(values: list[float]) -> float:
    """Compute coefficient of variation (std_dev / mean) for a list of values.

    Returns 0.0 if mean is 0 (perfectly stable — all zeros means no activity,
    which we treat as stable for CV purposes; the raw count will score separately).
    """
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    return std_dev / mean


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


async def write_slack_signal_snapshot(
    team_id: UUID,
    metrics: SlackSignalMetrics,
    score: float | None,
    db: AsyncSession,
) -> TeamMetricSnapshot | None:
    """Write a Slack Signal snapshot to team_metric_snapshots.

    If score is None (degraded), the snapshot is NOT written — the weight
    is redistributed by the orchestrator across other active components.

    Returns:
        The inserted TeamMetricSnapshot row, or None if degraded/no-score.
    """
    if score is None:
        logger.info(
            "slack_signal_snapshot_skipped",
            team_id=str(team_id),
            reason="degraded or insufficient data",
        )
        return None

    now = datetime.now(tz=timezone.utc)
    rag = _rag_from_score(score)

    snapshot = TeamMetricSnapshot(
        team_id=team_id,
        snapshot_at=now,
        component="slack_signal",
        score=Decimal(str(round(score, 2))),
        rag=rag,
        computed_at=now,
    )
    db.add(snapshot)
    await db.flush()

    logger.info(
        "slack_signal_snapshot_written",
        team_id=str(team_id),
        score=score,
        rag=rag,
        total_messages=metrics.total_message_count,
        after_hours_pct=metrics.after_hours_message_pct,
        weekend_pct=metrics.weekend_message_pct,
        spike_engineers=len(metrics.engineers_with_after_hours_spike or []),
    )
    return snapshot
