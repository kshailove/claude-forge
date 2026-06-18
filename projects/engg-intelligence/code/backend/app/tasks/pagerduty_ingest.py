"""PagerDuty nightly batch ingestion worker.

Fetches incidents, oncall schedules, and oncall shifts for the previous 24 hours.
Upserts records into PostgreSQL using ON CONFLICT DO UPDATE.
Handles rate limits and 5xx errors with retries.

Spec reference: §5.5, §6.3, M3a
Task queue: q_incidents
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
from app.integrations.pagerduty_client import (
    PagerDutyClient,
    PagerDutyRateLimitError,
    extract_pagerduty_timestamps,
    normalize_pagerduty_severity,
)
from app.models.incidents import Incident, IncidentAssignment, OncallSchedule, OncallShift
from app.models.integration import IdentityMapping, Integration

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)


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
    name="app.tasks.pagerduty_ingest.pagerduty_nightly_batch",
    queue="q_incidents",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def pagerduty_nightly_batch(self, integration_id: str) -> dict:
    """Nightly PagerDuty batch worker.

    Pulls all incidents for yesterday (since=yesterday_start_UTC, until=today_start_UTC).
    Upserts incidents, incident_assignments to PostgreSQL.
    Also syncs oncall schedules and shifts for yesterday.
    Updates integrations.last_synced_at on success.

    Args:
        integration_id: UUID string of the Integration record.
    """
    return _run_async(_pagerduty_nightly_batch_async(integration_id))


async def _pagerduty_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly PagerDuty batch."""
    session_factory = get_session_factory()
    now_utc = datetime.now(tz=timezone.utc)

    # Yesterday's UTC window
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()
        team_id: UUID | None = integration.team_id

    api_key: str = config["api_key"]
    service_ids: list[str] = config.get("service_ids") or []

    struct_logger.info(
        "pagerduty_nightly_batch_started",
        integration_id=integration_id,
        since=yesterday_start.isoformat(),
        until=today_start.isoformat(),
        service_ids=service_ids,
    )

    stats: dict[str, int] = {
        "incidents_upserted": 0,
        "assignments_upserted": 0,
        "schedules_upserted": 0,
        "shifts_upserted": 0,
        "errors": 0,
    }

    try:
        async with PagerDutyClient(api_key=api_key) as client:
            # Build identity cache once per batch
            async with session_factory() as session:
                identity_cache = await _build_identity_cache(session, tool="pagerduty")

            # ---- Ingest incidents ----
            async with session_factory() as session:
                async for incident_data in client.get_incidents(
                    since=yesterday_start,
                    until=today_start,
                    service_ids=service_ids or None,
                ):
                    try:
                        await _upsert_incident(
                            session=session,
                            client=client,
                            incident_data=incident_data,
                            integration_id=UUID(integration_id),
                            team_id=team_id,
                            identity_cache=identity_cache,
                            stats=stats,
                        )
                        await session.commit()
                    except Exception as exc:
                        await session.rollback()
                        struct_logger.error(
                            "pagerduty_incident_upsert_failed",
                            incident_id=incident_data.get("id"),
                            error=str(exc),
                            exc_info=True,
                        )
                        stats["errors"] += 1
                        continue

            # ---- Sync oncall schedules ----
            await _sync_oncall_schedules(
                client=client,
                integration_id=UUID(integration_id),
                since=yesterday_start,
                until=today_start,
                identity_cache=identity_cache,
                stats=stats,
            )

        # Update last_synced_at
        async with session_factory() as session:
            integration = await _load_integration(session, integration_id)
            integration.last_synced_at = datetime.now(tz=timezone.utc)
            integration.status = "connected"
            await session.commit()

    except PagerDutyRateLimitError as exc:
        struct_logger.error(
            "pagerduty_rate_limit_exhausted",
            integration_id=integration_id,
            retry_after=exc.retry_after,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise

    except Exception as exc:
        struct_logger.error(
            "pagerduty_nightly_batch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise

    struct_logger.info(
        "pagerduty_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Incident ingestion
# ---------------------------------------------------------------------------


async def _upsert_incident(
    *,
    session: AsyncSession,
    client: PagerDutyClient,
    incident_data: dict,
    integration_id: UUID,
    team_id: UUID | None,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Upsert a single PagerDuty incident and its assignments."""
    pd_id: str = incident_data["id"]
    external_id: str = pd_id  # PagerDuty ID string e.g. 'P123ABC'
    title: str = (incident_data.get("title") or incident_data.get("description") or "")[:500]

    # Severity normalization
    urgency: str | None = incident_data.get("urgency")
    priority: dict | None = incident_data.get("priority") or {}
    priority_name: str | None = priority.get("name") if priority else None
    severity = normalize_pagerduty_severity(urgency=urgency, priority_name=priority_name)

    # Service name
    service: dict | None = incident_data.get("service") or {}
    service_name: str | None = (service.get("summary") or service.get("name") or None) if service else None
    if service_name:
        service_name = service_name[:255]

    # Parse triggered_at
    triggered_at_str: str | None = incident_data.get("created_at")
    if not triggered_at_str:
        struct_logger.warning("pagerduty_incident_missing_created_at", pd_id=pd_id)
        return
    triggered_at = _parse_pd_dt(triggered_at_str)

    # Fetch log entries to get acknowledged_at and resolved_at
    try:
        log_entries = await client.get_incident_log_entries(pd_id)
    except Exception as exc:
        struct_logger.warning(
            "pagerduty_log_entries_failed",
            pd_id=pd_id,
            error=str(exc),
        )
        log_entries = []

    acknowledged_at, resolved_at = extract_pagerduty_timestamps(
        log_entries=log_entries,
        incident_data=incident_data,
    )

    # Compute MTTA / MTTR
    mtta_seconds: int | None = None
    if acknowledged_at is not None:
        delta = (acknowledged_at - triggered_at).total_seconds()
        mtta_seconds = max(0, int(delta))

    mttr_seconds: int | None = None
    if resolved_at is not None:
        delta = (resolved_at - triggered_at).total_seconds()
        mttr_seconds = max(0, int(delta))

    # Resolve team_id: if integration has no team, try to infer (or keep None)
    effective_team_id: UUID | None = team_id
    if effective_team_id is None:
        struct_logger.debug(
            "pagerduty_incident_no_team",
            pd_id=pd_id,
            note="Integration has no team_id; incident stored without team attribution",
        )
        return  # Skip incidents with no team context

    # Upsert incident
    stmt = (
        pg_insert(Incident)
        .values(
            integration_id=integration_id,
            external_id=external_id,
            title=title,
            severity=severity,
            service_name=service_name,
            team_id=effective_team_id,
            triggered_at=triggered_at,
            acknowledged_at=acknowledged_at,
            resolved_at=resolved_at,
            mtta_seconds=mtta_seconds,
            mttr_seconds=mttr_seconds,
        )
        .on_conflict_do_update(
            index_elements=["external_id"],
            set_=dict(
                title=title,
                severity=severity,
                service_name=service_name,
                acknowledged_at=acknowledged_at,
                resolved_at=resolved_at,
                mtta_seconds=mtta_seconds,
                mttr_seconds=mttr_seconds,
            ),
        )
        .returning(Incident.id)
    )
    result = await session.execute(stmt)
    incident_id: UUID = result.scalar_one()
    stats["incidents_upserted"] += 1

    # Upsert incident assignments
    assignments: list[dict] = incident_data.get("assignments") or []
    for assignment in assignments:
        try:
            await _upsert_assignment(
                session=session,
                assignment_data=assignment,
                incident_id=incident_id,
                triggered_at=triggered_at,
                resolved_at=resolved_at,
                identity_cache=identity_cache,
            )
            stats["assignments_upserted"] += 1
        except Exception as exc:
            struct_logger.error(
                "pagerduty_assignment_upsert_failed",
                incident_id=str(incident_id),
                error=str(exc),
            )
            stats["errors"] += 1


async def _upsert_assignment(
    *,
    session: AsyncSession,
    assignment_data: dict,
    incident_id: UUID,
    triggered_at: datetime,
    resolved_at: datetime | None,
    identity_cache: dict,
) -> None:
    """Upsert a single incident assignment."""
    assignee: dict | None = assignment_data.get("assignee") or {}
    pd_user_id: str | None = assignee.get("id") if assignee else None
    pd_user_email: str | None = assignee.get("email") if assignee else None

    user_id: UUID | None = _resolve_identity(
        identity_cache, tool_user_id=pd_user_id, email=pd_user_email
    )

    at_str: str | None = assignment_data.get("at")
    assigned_at = _parse_pd_dt(at_str) if at_str else triggered_at

    stmt = (
        pg_insert(IncidentAssignment)
        .values(
            incident_id=incident_id,
            user_id=user_id,
            assigned_at=assigned_at,
            resolved_at=resolved_at,
        )
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Oncall schedule + shift sync
# ---------------------------------------------------------------------------


async def _sync_oncall_schedules(
    *,
    client: PagerDutyClient,
    integration_id: UUID,
    since: datetime,
    until: datetime,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Fetch all schedules and sync yesterday's on-call shifts."""
    session_factory = get_session_factory()

    try:
        schedules = await client.get_oncall_schedules()
    except Exception as exc:
        struct_logger.error(
            "pagerduty_schedules_fetch_failed",
            error=str(exc),
        )
        stats["errors"] += 1
        return

    for schedule_data in schedules:
        schedule_external_id: str = schedule_data["id"]
        schedule_name: str = (schedule_data.get("name") or schedule_data.get("summary") or "")[:255]

        try:
            async with session_factory() as session:
                # Upsert oncall_schedule
                schedule_stmt = (
                    pg_insert(OncallSchedule)
                    .values(
                        integration_id=integration_id,
                        external_id=schedule_external_id,
                        schedule_name=schedule_name,
                    )
                    .on_conflict_do_update(
                        constraint="uq_oncall_schedules_integration_external",
                        set_=dict(schedule_name=schedule_name),
                    )
                    .returning(OncallSchedule.id)
                )
                sched_result = await session.execute(schedule_stmt)
                schedule_id: UUID = sched_result.scalar_one()
                await session.commit()
                stats["schedules_upserted"] += 1

            # Fetch oncall shifts for yesterday's window
            oncalls = await client.get_schedule_oncalls(
                schedule_id=schedule_external_id,
                since=since,
                until=until,
            )

            for oncall_data in oncalls:
                try:
                    user_ref: dict | None = oncall_data.get("user") or {}
                    pd_user_id: str | None = user_ref.get("id") if user_ref else None
                    pd_user_email: str | None = user_ref.get("email") if user_ref else None
                    user_id: UUID | None = _resolve_identity(
                        identity_cache, tool_user_id=pd_user_id, email=pd_user_email
                    )

                    start_str: str | None = oncall_data.get("start")
                    end_str: str | None = oncall_data.get("end")
                    if not start_str or not end_str:
                        continue

                    start_at = _parse_pd_dt(start_str)
                    end_at = _parse_pd_dt(end_str)

                    async with session_factory() as session:
                        shift_stmt = (
                            pg_insert(OncallShift)
                            .values(
                                schedule_id=schedule_id,
                                user_id=user_id,
                                start_at=start_at,
                                end_at=end_at,
                            )
                            .on_conflict_do_nothing()
                        )
                        await session.execute(shift_stmt)
                        await session.commit()
                        stats["shifts_upserted"] += 1
                except Exception as exc:
                    struct_logger.error(
                        "pagerduty_shift_upsert_failed",
                        schedule_external_id=schedule_external_id,
                        error=str(exc),
                    )
                    stats["errors"] += 1

        except Exception as exc:
            struct_logger.error(
                "pagerduty_schedule_sync_failed",
                schedule_external_id=schedule_external_id,
                error=str(exc),
            )
            stats["errors"] += 1
            continue


# ---------------------------------------------------------------------------
# Identity resolution helpers
# ---------------------------------------------------------------------------


async def _build_identity_cache(session: AsyncSession, tool: str) -> dict:
    """Build an in-memory {tool_user_id: user_id, email: user_id} lookup cache."""
    result = await session.execute(
        select(IdentityMapping).where(IdentityMapping.tool == tool)
    )
    mappings = result.scalars().all()

    cache: dict[str, UUID] = {}
    for m in mappings:
        cache[f"id:{m.tool_user_id}"] = m.canonical_user_id
        if m.tool_email:
            cache[f"email:{m.tool_email.lower()}"] = m.canonical_user_id
    return cache


def _resolve_identity(
    cache: dict,
    tool_user_id: str | None,
    email: str | None,
) -> UUID | None:
    """Resolve a tool user ID or email to a canonical user_id."""
    if tool_user_id:
        user_id = cache.get(f"id:{tool_user_id}")
        if user_id:
            return user_id
    if email:
        user_id = cache.get(f"email:{email.lower()}")
        if user_id:
            return user_id
    return None


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------


async def _load_integration(session: AsyncSession, integration_id: str) -> Integration:
    """Load an Integration record or raise ValueError."""
    result = await session.execute(
        select(Integration).where(Integration.id == UUID(integration_id))
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise ValueError(f"Integration {integration_id} not found")
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
            "pagerduty_integration_error_set",
            integration_id=integration_id,
            error=error_msg[:200],
        )
    except Exception as exc:
        struct_logger.error(
            "pagerduty_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )


def _parse_pd_dt(dt_str: str) -> datetime:
    """Parse a PagerDuty ISO 8601 datetime string to a timezone-aware UTC datetime."""
    dt_str_clean = dt_str.rstrip("Z")
    if "+" in dt_str_clean:
        dt = datetime.fromisoformat(dt_str_clean)
    else:
        dt = datetime.fromisoformat(dt_str_clean).replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
