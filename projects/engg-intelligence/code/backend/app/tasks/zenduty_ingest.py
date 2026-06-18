"""Zenduty nightly batch ingestion worker.

Fetches incidents (paginated, filtered client-side for yesterday), oncall schedules,
and oncall shifts. Upserts records into PostgreSQL using ON CONFLICT DO UPDATE.
Handles rate limits and 5xx errors with retries.

Spec reference: §5.5, §6.4, M3b
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
from app.integrations.zenduty_client import (
    ZendutyClient,
    ZendutyRateLimitError,
    compute_zenduty_timestamps,
    normalize_zenduty_severity,
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
    name="app.tasks.zenduty_ingest.zenduty_nightly_batch",
    queue="q_incidents",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def zenduty_nightly_batch(self, integration_id: str) -> dict:
    """Nightly Zenduty batch worker.

    Pulls all incidents (paginated) and filters client-side for yesterday.
    Upserts incidents, incident_assignments.
    Syncs oncall schedules and shifts for yesterday.
    Updates integrations.last_synced_at on success.

    Args:
        integration_id: UUID string of the Integration record.
    """
    return _run_async(_zenduty_nightly_batch_async(integration_id))


async def _zenduty_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly Zenduty batch."""
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
    base_url: str = config.get("base_url", "https://www.zenduty.com/api/v1")
    configured_team_ids: list[str] = config.get("team_ids") or []

    struct_logger.info(
        "zenduty_nightly_batch_started",
        integration_id=integration_id,
        since=yesterday_start.isoformat(),
        until=today_start.isoformat(),
        base_url=base_url,
    )

    stats: dict[str, int] = {
        "incidents_upserted": 0,
        "assignments_upserted": 0,
        "schedules_upserted": 0,
        "shifts_upserted": 0,
        "errors": 0,
    }

    try:
        async with ZendutyClient(api_key=api_key, base_url=base_url) as client:
            # Build identity cache
            async with session_factory() as session:
                identity_cache = await _build_identity_cache(session, tool="zenduty")

            # ---- Ingest incidents (paginated, filter client-side) ----
            await _ingest_incidents(
                client=client,
                integration_id=UUID(integration_id),
                team_id=team_id,
                yesterday_start=yesterday_start,
                today_start=today_start,
                identity_cache=identity_cache,
                stats=stats,
            )

            # ---- Sync oncall schedules ----
            # Resolve which teams to sync: use config team_ids or fetch all
            teams_to_sync: list[str] = configured_team_ids
            if not teams_to_sync:
                try:
                    all_teams = await client.get_teams()
                    teams_to_sync = [t.get("unique_id") or t.get("id") or "" for t in all_teams]
                    teams_to_sync = [t for t in teams_to_sync if t]
                except Exception as exc:
                    struct_logger.error(
                        "zenduty_fetch_teams_failed",
                        error=str(exc),
                    )
                    teams_to_sync = []

            await _sync_oncall_schedules(
                client=client,
                integration_id=UUID(integration_id),
                team_ids=teams_to_sync,
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

    except ZendutyRateLimitError as exc:
        struct_logger.error(
            "zenduty_rate_limit_exhausted",
            integration_id=integration_id,
            retry_after=exc.retry_after,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise

    except Exception as exc:
        struct_logger.error(
            "zenduty_nightly_batch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise

    struct_logger.info(
        "zenduty_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Incident ingestion
# ---------------------------------------------------------------------------


async def _ingest_incidents(
    *,
    client: ZendutyClient,
    integration_id: UUID,
    team_id: UUID | None,
    yesterday_start: datetime,
    today_start: datetime,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Paginate through all Zenduty incidents and upsert those created yesterday."""
    session_factory = get_session_factory()
    page = 1
    found_older = False  # optimization: stop when we've passed yesterday's window

    while not found_older:
        try:
            page_data = await client.get_incidents(page=page)
        except Exception as exc:
            struct_logger.error(
                "zenduty_fetch_incidents_failed",
                page=page,
                error=str(exc),
            )
            stats["errors"] += 1
            break

        incidents: list[dict] = page_data.get("results", [])
        if not incidents:
            break

        for incident_data in incidents:
            try:
                triggered_at, acknowledged_at, resolved_at = compute_zenduty_timestamps(
                    incident_data
                )
                if triggered_at is None:
                    continue

                # Client-side date filter
                if triggered_at >= today_start:
                    continue  # too new — skip
                if triggered_at < yesterday_start:
                    # Zenduty returns newest-first; once we pass yesterday, stop
                    found_older = True
                    break

                # This incident belongs to yesterday's window
                if team_id is None:
                    struct_logger.debug(
                        "zenduty_incident_no_team",
                        incident_number=incident_data.get("incident_number"),
                    )
                    continue

                await _upsert_incident(
                    integration_id=integration_id,
                    team_id=team_id,
                    incident_data=incident_data,
                    triggered_at=triggered_at,
                    acknowledged_at=acknowledged_at,
                    resolved_at=resolved_at,
                    identity_cache=identity_cache,
                    stats=stats,
                )
            except Exception as exc:
                struct_logger.error(
                    "zenduty_incident_processing_failed",
                    incident_number=incident_data.get("incident_number"),
                    error=str(exc),
                    exc_info=True,
                )
                stats["errors"] += 1
                continue

        if found_older:
            break

        # Check if there's a next page
        if not page_data.get("next"):
            break

        page += 1


async def _upsert_incident(
    *,
    integration_id: UUID,
    team_id: UUID,
    incident_data: dict,
    triggered_at: datetime,
    acknowledged_at: datetime | None,
    resolved_at: datetime | None,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Upsert a single Zenduty incident and its assignments."""
    session_factory = get_session_factory()

    incident_number = incident_data.get("incident_number")
    external_id: str = str(incident_number)
    title: str = (incident_data.get("title") or incident_data.get("summary") or "")[:500]

    urgency: int | None = incident_data.get("urgency")
    severity = normalize_zenduty_severity(urgency)

    service_name: str | None = None
    service: dict | None = incident_data.get("service") or {}
    if service and isinstance(service, dict):
        service_name = (service.get("name") or service.get("summary") or None)
        if service_name:
            service_name = service_name[:255]

    # Compute MTTA / MTTR
    mtta_seconds: int | None = None
    if acknowledged_at is not None:
        delta = (acknowledged_at - triggered_at).total_seconds()
        mtta_seconds = max(0, int(delta))

    mttr_seconds: int | None = None
    if resolved_at is not None:
        delta = (resolved_at - triggered_at).total_seconds()
        mttr_seconds = max(0, int(delta))

    async with session_factory() as session:
        stmt = (
            pg_insert(Incident)
            .values(
                integration_id=integration_id,
                external_id=external_id,
                title=title,
                severity=severity,
                service_name=service_name,
                team_id=team_id,
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
        await session.commit()
        stats["incidents_upserted"] += 1

    # Upsert assignments
    assigned_to: list[dict] = incident_data.get("assigned_to") or []
    for assignee_data in assigned_to:
        try:
            await _upsert_assignment(
                incident_id=incident_id,
                assignee_data=assignee_data,
                triggered_at=triggered_at,
                resolved_at=resolved_at,
                identity_cache=identity_cache,
            )
            stats["assignments_upserted"] += 1
        except Exception as exc:
            struct_logger.error(
                "zenduty_assignment_upsert_failed",
                incident_id=str(incident_id),
                error=str(exc),
            )
            stats["errors"] += 1


async def _upsert_assignment(
    *,
    incident_id: UUID,
    assignee_data: dict,
    triggered_at: datetime,
    resolved_at: datetime | None,
    identity_cache: dict,
) -> None:
    """Upsert a single incident assignment."""
    session_factory = get_session_factory()

    zd_user: dict | None = assignee_data.get("user") or assignee_data
    zd_user_id: str | None = str(zd_user.get("id") or "") or None
    zd_email: str | None = zd_user.get("email") if zd_user else None

    user_id: UUID | None = _resolve_identity(
        identity_cache, tool_user_id=zd_user_id, email=zd_email
    )

    async with session_factory() as session:
        stmt = (
            pg_insert(IncidentAssignment)
            .values(
                incident_id=incident_id,
                user_id=user_id,
                assigned_at=triggered_at,
                resolved_at=resolved_at,
            )
            .on_conflict_do_nothing()
        )
        await session.execute(stmt)
        await session.commit()


# ---------------------------------------------------------------------------
# Oncall schedule + shift sync
# ---------------------------------------------------------------------------


async def _sync_oncall_schedules(
    *,
    client: ZendutyClient,
    integration_id: UUID,
    team_ids: list[str],
    since: datetime,
    until: datetime,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Fetch schedules for all configured teams and sync yesterday's on-call shifts."""
    session_factory = get_session_factory()

    for zd_team_id in team_ids:
        try:
            schedules = await client.get_schedules(zd_team_id)
        except Exception as exc:
            struct_logger.error(
                "zenduty_fetch_schedules_failed",
                team_id=zd_team_id,
                error=str(exc),
            )
            stats["errors"] += 1
            continue

        for schedule_data in schedules:
            schedule_external_id: str = str(
                schedule_data.get("unique_id") or schedule_data.get("id") or ""
            )
            schedule_name: str = (schedule_data.get("name") or schedule_external_id)[:255]

            try:
                async with session_factory() as session:
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

                # Fetch oncalls for yesterday
                oncalls = await client.get_schedule_oncalls(
                    team_id=zd_team_id,
                    schedule_id=schedule_external_id,
                    start_time=since,
                    end_time=until,
                )

                for oncall_data in oncalls:
                    try:
                        user_ref: dict | None = oncall_data.get("user") or {}
                        zd_user_id: str | None = str(user_ref.get("id") or "") or None if user_ref else None
                        zd_email: str | None = user_ref.get("email") if user_ref else None
                        user_id: UUID | None = _resolve_identity(
                            identity_cache, tool_user_id=zd_user_id, email=zd_email
                        )

                        start_str: str | None = oncall_data.get("start") or oncall_data.get("start_time")
                        end_str: str | None = oncall_data.get("end") or oncall_data.get("end_time")
                        if not start_str or not end_str:
                            continue

                        start_at = _parse_zd_dt(start_str)
                        end_at = _parse_zd_dt(end_str)

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
                            "zenduty_shift_upsert_failed",
                            schedule_external_id=schedule_external_id,
                            error=str(exc),
                        )
                        stats["errors"] += 1

            except Exception as exc:
                struct_logger.error(
                    "zenduty_schedule_sync_failed",
                    zd_team_id=zd_team_id,
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
            "zenduty_integration_error_set",
            integration_id=integration_id,
            error=error_msg[:200],
        )
    except Exception as exc:
        struct_logger.error(
            "zenduty_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )


def _parse_zd_dt(dt_str: str) -> datetime:
    """Parse a Zenduty ISO 8601 datetime string to a timezone-aware UTC datetime."""
    dt_str_clean = dt_str.rstrip("Z")
    if "+" in dt_str_clean:
        dt = datetime.fromisoformat(dt_str_clean)
    else:
        dt = datetime.fromisoformat(dt_str_clean).replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
