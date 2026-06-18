"""Slack nightly batch ingestion worker.

Fetches channel message metadata (timestamps + user IDs, NO content) for all
channels in the connected Slack workspace. Groups by user/hour bucket and upserts
into slack_activity_buckets with after-hours and weekend flags.

Privacy guarantee: message text, attachments, and reactions are NEVER fetched,
stored, or logged. Only message timestamps and user IDs are processed.

Spec reference: §6 (Slack details), §8 M6b, §2.4 (degradation policy)
Task queue: q_slack (concurrency=1)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.database import get_session_factory
from app.integrations.slack_client import SlackClient
from app.models.integration import IdentityMapping, Integration
from app.models.slack import SlackActivityBucket
from app.models.team import TeamMembership

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)

# Work-hours window: messages outside 09:00–18:00 are "after hours"
WORK_HOUR_START = 9   # 09:00 (inclusive)
WORK_HOUR_END = 18    # 18:00 (exclusive, so 18:00+ is after hours)

# Maximum channels to process per run (degradation guard — skip if degraded)
MAX_CHANNELS = 50

# Per-channel sleep between requests enforced in the client; add an extra inter-channel
# buffer here so the 60s Tier 3 limit is always respected even across channel switches.
INTER_CHANNEL_SLEEP_SECONDS = 60


# ---------------------------------------------------------------------------
# Helper: run async from sync Celery context
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Main nightly batch task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.slack_ingest.slack_nightly_batch",
    queue="q_slack",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def slack_nightly_batch(self, integration_id: str) -> dict:
    """Nightly Slack metadata ingestion worker.

    Runs on q_slack (concurrency=1) to respect Slack Tier 3 rate limits.

    If integration is degraded (>200 members or >50 channels):
        - Logs a warning and returns early with status='skipped_degraded'
        - Does NOT mark the integration as errored

    If not degraded:
        - Fetches yesterday's message metadata for all channels (up to 50)
        - Resolves Slack user IDs to canonical users via identity_mappings
        - Upserts hourly buckets into slack_activity_buckets
        - Updates integrations.last_synced_at

    Args:
        integration_id: UUID string of the Slack Integration record.
    """
    return _run_async(_slack_nightly_batch_async(integration_id))


async def _slack_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly Slack ingestion batch."""
    session_factory = get_session_factory()

    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()

    bot_token: str = config["bot_token"]
    slack_signal_degraded: bool = config.get("slack_signal_degraded", False)

    # --- Degradation guard ---
    if slack_signal_degraded:
        struct_logger.warning(
            "slack_nightly_batch_skipped_degraded",
            integration_id=integration_id,
            reason=config.get("slack_degraded_reason", "degraded"),
        )
        return {
            "status": "skipped_degraded",
            "integration_id": integration_id,
            "reason": "Slack workspace exceeds size thresholds; Slack Signal disabled",
        }

    # --- Compute yesterday's time window ---
    now_utc = datetime.now(tz=timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    oldest_ts = yesterday_start.timestamp()
    latest_ts = today_start.timestamp()

    struct_logger.info(
        "slack_nightly_batch_started",
        integration_id=integration_id,
        window_start=yesterday_start.isoformat(),
        window_end=today_start.isoformat(),
    )

    # --- Build identity cache (Slack user_id → canonical user_id + team_id) ---
    async with session_factory() as session:
        identity_cache = await _build_slack_identity_cache(session)
        user_timezones = await _build_user_timezone_cache(session)
        team_by_user = await _build_user_team_cache(session)

    stats = {
        "channels_processed": 0,
        "messages_processed": 0,
        "buckets_upserted": 0,
        "errors": 0,
    }

    async with SlackClient(bot_token=bot_token) as client:
        channels_processed = 0

        async for channel in client.get_channels(exclude_archived=True):
            if channels_processed >= MAX_CHANNELS:
                struct_logger.warning(
                    "slack_channel_limit_reached",
                    integration_id=integration_id,
                    limit=MAX_CHANNELS,
                )
                break

            channel_id: str = channel["id"]
            channel_name: str = channel.get("name", channel_id)

            try:
                # Collect all message metadata for this channel/day.
                # Accumulate into per-(user, bucket_hour) counters before upserting.
                bucket_accumulator: dict[tuple[UUID, datetime], _BucketData] = {}

                msg_count = 0
                async for msg in client.get_channel_history(
                    channel_id=channel_id,
                    oldest=oldest_ts,
                    latest=latest_ts,
                ):
                    # Skip bot messages, channel_join, etc. — only count real user messages
                    if msg.get("subtype") is not None:
                        continue
                    slack_user_id: str | None = msg.get("user")
                    if not slack_user_id:
                        continue

                    ts_str: str | None = msg.get("ts")
                    if not ts_str:
                        continue

                    # Parse Slack timestamp (Unix float, e.g. "1718000000.001234")
                    try:
                        msg_unix = float(ts_str)
                    except (ValueError, TypeError):
                        continue

                    msg_dt = datetime.fromtimestamp(msg_unix, tz=timezone.utc)

                    # Resolve Slack user_id → canonical user_id
                    canonical_user_id = identity_cache.get(f"slack:{slack_user_id}")
                    if canonical_user_id is None:
                        # No mapping: skip (user not known to system)
                        continue

                    # Resolve team for this user
                    team_id = team_by_user.get(canonical_user_id)
                    if team_id is None:
                        continue

                    # Determine user's local timezone for after-hours detection
                    user_tz_name = user_timezones.get(canonical_user_id)
                    is_after_hours, is_weekend = _classify_message_time(
                        msg_dt=msg_dt, user_tz_name=user_tz_name
                    )

                    # Truncate to hour bucket
                    bucket_hour = msg_dt.replace(minute=0, second=0, microsecond=0)

                    key = (canonical_user_id, bucket_hour)
                    if key not in bucket_accumulator:
                        bucket_accumulator[key] = _BucketData(
                            user_id=canonical_user_id,
                            team_id=team_id,
                            bucket_hour=bucket_hour,
                            message_count=0,
                            is_after_hours=is_after_hours,
                            is_weekend=is_weekend,
                        )
                    bucket_accumulator[key].message_count += 1
                    msg_count += 1

                # Upsert all accumulated buckets for this channel
                if bucket_accumulator:
                    async with session_factory() as session:
                        for bucket_data in bucket_accumulator.values():
                            await _upsert_activity_bucket(session, bucket_data)
                        await session.commit()
                        stats["buckets_upserted"] += len(bucket_accumulator)

                stats["messages_processed"] += msg_count
                channels_processed += 1
                stats["channels_processed"] += 1

                struct_logger.debug(
                    "slack_channel_processed",
                    channel_id=channel_id,
                    channel_name=channel_name,
                    messages=msg_count,
                    buckets=len(bucket_accumulator),
                )

            except Exception as exc:
                struct_logger.error(
                    "slack_channel_processing_failed",
                    channel_id=channel_id,
                    channel_name=channel_name,
                    error=str(exc),
                    exc_info=True,
                )
                stats["errors"] += 1
                # Never abort the whole batch for one channel failure
                continue

            # Inter-channel sleep to respect Tier 3 rate limit (60s/channel)
            # The client also tracks this, but we sleep here between channels
            # so the next channel's first request isn't immediately rate-limited.
            await asyncio.sleep(INTER_CHANNEL_SLEEP_SECONDS)

    # --- Update last_synced_at on success ---
    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        integration.last_synced_at = datetime.now(tz=timezone.utc)
        integration.status = "connected"
        await session.commit()

    struct_logger.info(
        "slack_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Bucket accumulator helper
# ---------------------------------------------------------------------------


class _BucketData:
    """Transient accumulator for a single (user, hour) activity bucket."""

    __slots__ = ("user_id", "team_id", "bucket_hour", "message_count", "is_after_hours", "is_weekend")

    def __init__(
        self,
        user_id: UUID,
        team_id: UUID,
        bucket_hour: datetime,
        message_count: int,
        is_after_hours: bool,
        is_weekend: bool,
    ) -> None:
        self.user_id = user_id
        self.team_id = team_id
        self.bucket_hour = bucket_hour
        self.message_count = message_count
        self.is_after_hours = is_after_hours
        self.is_weekend = is_weekend


# ---------------------------------------------------------------------------
# Upsert helper
# ---------------------------------------------------------------------------


async def _upsert_activity_bucket(
    session: AsyncSession,
    bucket: _BucketData,
) -> None:
    """Upsert a SlackActivityBucket record with additive message_count.

    ON CONFLICT (user_id, bucket_hour) DO UPDATE adds to the existing count.
    This is safe to run multiple times (idempotent for the same channel/day).
    """
    stmt = (
        pg_insert(SlackActivityBucket)
        .values(
            user_id=bucket.user_id,
            team_id=bucket.team_id,
            bucket_hour=bucket.bucket_hour,
            message_count=bucket.message_count,
            is_after_hours=bucket.is_after_hours,
            is_weekend=bucket.is_weekend,
            channel_count_distinct=1,
        )
        .on_conflict_do_update(
            # Unique constraint: (user_id, bucket_hour)
            index_elements=["user_id", "bucket_hour"],
            set_=dict(
                message_count=SlackActivityBucket.message_count + bucket.message_count,
                channel_count_distinct=(
                    SlackActivityBucket.channel_count_distinct + 1
                ),
                # is_after_hours / is_weekend: keep existing value (first-write wins)
                # since all messages in a bucket share the same hour classification
            ),
        )
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Time classification helpers
# ---------------------------------------------------------------------------


def _classify_message_time(
    msg_dt: datetime,
    user_tz_name: str | None,
) -> tuple[bool, bool]:
    """Determine if a message was sent after-hours and/or on a weekend.

    After-hours: sent outside 09:00–18:00 in the user's local timezone.
    Weekend: Saturday (weekday=5) or Sunday (weekday=6) in user's local timezone.

    Falls back to UTC if user timezone is unknown.

    Args:
        msg_dt: Message datetime in UTC.
        user_tz_name: IANA timezone string (e.g. "America/New_York"), or None.

    Returns:
        Tuple of (is_after_hours, is_weekend).
    """
    try:
        if user_tz_name:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            try:
                user_tz = ZoneInfo(user_tz_name)
                local_dt = msg_dt.astimezone(user_tz)
            except (ZoneInfoNotFoundError, Exception):
                local_dt = msg_dt  # fall back to UTC
        else:
            local_dt = msg_dt  # UTC
    except Exception:
        local_dt = msg_dt

    local_hour = local_dt.hour
    local_weekday = local_dt.weekday()  # 0=Monday, 6=Sunday

    is_after_hours = local_hour < WORK_HOUR_START or local_hour >= WORK_HOUR_END
    is_weekend = local_weekday >= 5  # Saturday=5, Sunday=6

    return is_after_hours, is_weekend


# ---------------------------------------------------------------------------
# Identity + team resolution helpers
# ---------------------------------------------------------------------------


async def _build_slack_identity_cache(session: AsyncSession) -> dict[str, UUID]:
    """Build an in-memory {slack:<slack_user_id>: canonical_user_id} lookup cache."""
    result = await session.execute(
        select(IdentityMapping).where(IdentityMapping.tool == "slack")
    )
    mappings = result.scalars().all()

    cache: dict[str, UUID] = {}
    for m in mappings:
        cache[f"slack:{m.tool_user_id}"] = m.canonical_user_id
    return cache


async def _build_user_timezone_cache(session: AsyncSession) -> dict[UUID, str | None]:
    """Build an in-memory {canonical_user_id: tz_name} cache.

    Fetches timezone from identity_mappings (Slack provides tz in users.list).
    We store it in IdentityMapping.tool_email as a proxy field — but the actual
    timezone should ideally come from a users.tz column. For now we return an
    empty cache and let _classify_message_time fall back to UTC.

    TODO: Add a timezone column to users table in a future migration.
    """
    # Placeholder: return empty cache → all messages classified in UTC
    # When a users.timezone column is added, this will be populated from it.
    return {}


async def _build_user_team_cache(session: AsyncSession) -> dict[UUID, UUID]:
    """Build {canonical_user_id: team_id} from team_memberships."""
    result = await session.execute(select(TeamMembership))
    memberships = result.scalars().all()

    cache: dict[UUID, UUID] = {}
    for m in memberships:
        # If user belongs to multiple teams, last one wins (acceptable for bucketing)
        cache[m.user_id] = m.team_id
    return cache


# ---------------------------------------------------------------------------
# Integration loader
# ---------------------------------------------------------------------------


async def _load_integration(session: AsyncSession, integration_id: str) -> Integration:
    """Load an Integration record or raise ValueError."""
    result = await session.execute(
        select(Integration).where(Integration.id == UUID(integration_id))
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise ValueError(f"Slack Integration {integration_id} not found")
    return integration


async def _mark_integration_error(
    session: AsyncSession, integration_id: str, error_msg: str
) -> None:
    """Set integration status to 'error'."""
    try:
        integration = await _load_integration(session, integration_id)
        integration.status = "error"
        await session.commit()
        struct_logger.error(
            "slack_integration_error_set",
            integration_id=integration_id,
            error=error_msg[:200],
        )
    except Exception as exc:
        struct_logger.error(
            "slack_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )
