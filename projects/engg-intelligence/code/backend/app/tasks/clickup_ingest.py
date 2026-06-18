"""ClickUp nightly batch ingestion worker.

Fetches tasks updated in the last 24 hours for all configured sprint lists,
across all teams. Upserts records into tickets, ticket_state_transitions, and
sprints tables. Updates integrations.last_synced_at on success.

Spec reference: §6.3, M2b
Task queue: q_jira_clickup
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.database import get_session_factory
from app.integrations.clickup_client import ClickUpClient
from app.models.integration import IdentityMapping, Integration
from app.models.tickets import Sprint, Ticket, TicketStateTransition

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
# ClickUp status → normalised flow state mapping
# ---------------------------------------------------------------------------

CLICKUP_STATUS_TO_STATE: dict[str, str] = {
    # To Do
    "open": "todo",
    "to do": "todo",
    "backlog": "todo",
    "new": "todo",
    # In Progress
    "in progress": "in_progress",
    "in development": "in_progress",
    "development": "in_progress",
    "active": "in_progress",
    "doing": "in_progress",
    # Review / Testing
    "review": "in_review",
    "in review": "in_review",
    "testing": "in_review",
    "in testing": "in_review",
    "qa review": "in_review",
    "code review": "in_review",
    # Done
    "complete": "done",
    "completed": "done",
    "done": "done",
    "closed": "done",
    "resolved": "done",
    "released": "done",
    # Blocked
    "blocked": "blocked",
    "on hold": "blocked",
    "waiting": "blocked",
    "impeded": "blocked",
}


def _map_clickup_status(raw_status: str) -> str:
    """Map a raw ClickUp status string to a normalised flow state."""
    return CLICKUP_STATUS_TO_STATE.get(raw_status.lower().strip(), raw_status.lower())


# ---------------------------------------------------------------------------
# ClickUp task type → ticket_type enum
# ---------------------------------------------------------------------------

CLICKUP_TYPE_TO_TICKET_TYPE: dict[str, str] = {
    "bug": "bug",
    "defect": "bug",
    "feature": "feature",
    "story": "feature",
    "task": "feature",
    "enhancement": "feature",
    "tech debt": "tech_debt",
    "technical debt": "tech_debt",
    "refactor": "tech_debt",
    "risk": "risk",
    "security": "risk",
}


def _map_clickup_type(raw_type: str | None) -> str | None:
    if not raw_type:
        return None
    return CLICKUP_TYPE_TO_TICKET_TYPE.get(raw_type.lower().strip())


# ---------------------------------------------------------------------------
# Main nightly batch task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.clickup_ingest.clickup_nightly_batch",
    queue="q_jira_clickup",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def clickup_nightly_batch(self, integration_id: str) -> dict:
    """Nightly ClickUp batch worker.

    For each configured team → sprint list mapping, fetches tasks updated since
    yesterday. Upserts tickets, state transitions, and sprint records.
    Updates integrations.last_synced_at on success.

    Args:
        integration_id: UUID string of the Integration record (type='clickup').
    """
    return _run_async(_clickup_nightly_batch_async(integration_id))


async def _clickup_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly ClickUp batch."""
    session_factory = get_session_factory()

    # Yesterday start UTC in milliseconds (ClickUp uses Unix ms timestamps)
    now = datetime.now(tz=timezone.utc)
    yesterday_start = (now - timedelta(hours=24)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_start_ms = int(yesterday_start.timestamp() * 1000)

    # Load integration config
    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()

    api_token: str = config["api_token"]
    workspace_id: str = config["workspace_id"]
    # sprint_list_ids: { team_uuid: [list_id, ...] }
    sprint_list_ids: dict[str, list[str]] = config.get("sprint_list_ids", {})

    if not sprint_list_ids:
        struct_logger.warning(
            "clickup_no_sprint_lists",
            integration_id=integration_id,
            note="No sprint_list_ids configured — run setup wizard to map teams to Lists",
        )
        return {"status": "skipped", "reason": "no_sprint_list_ids_configured"}

    struct_logger.info(
        "clickup_nightly_batch_started",
        integration_id=integration_id,
        workspace_id=workspace_id,
        team_count=len(sprint_list_ids),
        since_ms=yesterday_start_ms,
    )

    stats = {
        "tasks_upserted": 0,
        "transitions_upserted": 0,
        "sprints_upserted": 0,
        "errors": 0,
    }

    try:
        async with ClickUpClient(api_token=api_token) as client:
            async with session_factory() as session:
                identity_cache = await _build_identity_cache(session)

            for team_id_str, list_ids in sprint_list_ids.items():
                try:
                    team_id = UUID(team_id_str)
                except ValueError:
                    struct_logger.warning(
                        "clickup_invalid_team_uuid",
                        team_id=team_id_str,
                    )
                    stats["errors"] += 1
                    continue

                for list_id in list_ids:
                    # Each configured List is treated as a sprint
                    try:
                        async with session_factory() as session:
                            await _upsert_sprint_from_list(
                                client=client,
                                session=session,
                                list_id=list_id,
                                integration_id=UUID(integration_id),
                                team_id=team_id,
                                stats=stats,
                            )
                            await session.commit()
                    except Exception as exc:
                        struct_logger.error(
                            "clickup_sprint_upsert_failed",
                            list_id=list_id,
                            error=str(exc),
                        )
                        stats["errors"] += 1
                        continue

                    # Resolve sprint_id for linking tasks
                    async with session_factory() as session:
                        sprint_result = await session.execute(
                            select(Sprint.id).where(
                                Sprint.integration_id == UUID(integration_id),
                                Sprint.external_id == list_id,
                            )
                        )
                        sprint_db_id: UUID | None = sprint_result.scalar_one_or_none()

                    # Ingest tasks updated since yesterday
                    async for task in await client.get_tasks(
                        list_id=list_id, date_updated_gt=yesterday_start_ms
                    ):
                        try:
                            async with session_factory() as session:
                                await _upsert_task(
                                    client=client,
                                    session=session,
                                    task=task,
                                    integration_id=UUID(integration_id),
                                    team_id=team_id,
                                    sprint_id=sprint_db_id,
                                    identity_cache=identity_cache,
                                    stats=stats,
                                )
                                await session.commit()
                        except Exception as exc:
                            struct_logger.error(
                                "clickup_task_processing_failed",
                                task_id=task.get("id"),
                                error=str(exc),
                                exc_info=True,
                            )
                            stats["errors"] += 1
                            continue

        # Update last_synced_at
        async with session_factory() as session:
            integration = await _load_integration(session, integration_id)
            integration.last_synced_at = datetime.now(tz=timezone.utc)
            integration.status = "connected"
            await session.commit()

    except Exception as exc:
        struct_logger.error(
            "clickup_nightly_batch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise  # Triggers Celery retry

    struct_logger.info(
        "clickup_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Sprint upsert (from ClickUp List)
# ---------------------------------------------------------------------------


async def _upsert_sprint_from_list(
    *,
    client: ClickUpClient,
    session: AsyncSession,
    list_id: str,
    integration_id: UUID,
    team_id: UUID,
    stats: dict,
) -> None:
    """Treat a ClickUp List as a sprint and upsert it into the sprints table."""
    # Fetch list metadata to get name and dates
    response = await client._get(f"/api/v2/list/{list_id}")
    list_data = response.json()

    name: str = (list_data.get("name") or f"List {list_id}")[:500]

    # ClickUp lists may have start_date and due_date (Unix ms or None)
    start_date: date | None = _ms_to_date(list_data.get("start_date"))
    end_date: date | None = _ms_to_date(list_data.get("due_date"))

    # Determine sprint state from list status
    list_status_type = (list_data.get("status") or {}).get("type", "").lower()
    if list_status_type == "closed":
        state = "completed"
    elif list_status_type == "open":
        # Determine active vs future from dates
        today = datetime.now(tz=timezone.utc).date()
        if start_date and start_date > today:
            state = "future"
        else:
            state = "active"
    else:
        state = "active"

    stmt = (
        pg_insert(Sprint)
        .values(
            integration_id=integration_id,
            external_id=list_id,
            name=name,
            team_id=team_id,
            start_date=start_date,
            end_date=end_date,
            state=state,
        )
        .on_conflict_do_update(
            index_elements=["integration_id", "external_id"],
            set_=dict(
                name=name,
                state=state,
                start_date=start_date,
                end_date=end_date,
            ),
        )
    )
    await session.execute(stmt)
    stats["sprints_upserted"] += 1


# ---------------------------------------------------------------------------
# Task upsert
# ---------------------------------------------------------------------------


async def _upsert_task(
    *,
    client: ClickUpClient,
    session: AsyncSession,
    task: dict,
    integration_id: UUID,
    team_id: UUID,
    sprint_id: UUID | None,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Upsert a single ClickUp task into the tickets table."""
    external_id: str = task["id"]
    title: str = (task.get("name") or "")[:500]

    # Status
    status_obj = task.get("status") or {}
    raw_status: str = (status_obj.get("status") or "unknown")[:100]

    # Ticket type from task type field
    raw_type = task.get("task_type") or (task.get("custom_type"))
    ticket_type = _map_clickup_type(raw_type)

    # Story points — stored in a custom field named "Story Points" or "Points"
    story_points: Decimal | None = _extract_story_points(task)

    # Assignees — ClickUp supports multiple; take the first for now
    assignee_user_id: UUID | None = None
    assignees = task.get("assignees") or []
    for assignee in assignees:
        assignee_clickup_id = str(assignee.get("id", ""))
        assignee_user_id = _resolve_identity_clickup(identity_cache, assignee_clickup_id)
        if assignee_user_id:
            break

    # Timestamps (ClickUp provides Unix ms strings)
    created_at = _ms_to_datetime(task.get("date_created"))
    updated_at = _ms_to_datetime(task.get("date_updated"))

    if created_at is None or updated_at is None:
        struct_logger.warning("clickup_task_missing_dates", task_id=external_id)
        return

    # completed_at from date_done field
    completed_at = _ms_to_datetime(task.get("date_done"))

    # Upsert ticket
    stmt = (
        pg_insert(Ticket)
        .values(
            integration_id=integration_id,
            external_id=external_id,
            title=title,
            assignee_user_id=assignee_user_id,
            sprint_id=sprint_id,
            status=raw_status,
            story_points=story_points,
            ticket_type=ticket_type,
            team_id=team_id,
            created_at=created_at,
            completed_at=completed_at,
            updated_at=updated_at,
        )
        .on_conflict_do_update(
            index_elements=["integration_id", "external_id"],
            set_=dict(
                title=title,
                assignee_user_id=assignee_user_id,
                sprint_id=sprint_id,
                status=raw_status,
                story_points=story_points,
                ticket_type=ticket_type,
                completed_at=completed_at,
                updated_at=updated_at,
            ),
        )
        .returning(Ticket.id, Ticket.started_at)
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    ticket_db_id: UUID = row[0]
    existing_started_at: datetime | None = row[1]
    stats["tasks_upserted"] += 1

    # ---- Fetch and upsert activity (state transitions) ----
    try:
        activity_entries = await client.get_task_activity(external_id)
        started_at = await _upsert_clickup_transitions(
            session=session,
            ticket_id=ticket_db_id,
            activity_entries=activity_entries,
            existing_started_at=existing_started_at,
            stats=stats,
        )
        # Back-patch started_at if discovered
        if started_at is not None and existing_started_at is None:
            await session.execute(
                pg_insert(Ticket)
                .values(
                    integration_id=integration_id,
                    external_id=external_id,
                    title=title,
                    status=raw_status,
                    team_id=team_id,
                    created_at=created_at,
                    updated_at=updated_at,
                    started_at=started_at,
                )
                .on_conflict_do_update(
                    index_elements=["integration_id", "external_id"],
                    set_=dict(started_at=started_at),
                )
            )
    except Exception as exc:
        struct_logger.warning(
            "clickup_activity_fetch_failed",
            task_id=external_id,
            error=str(exc),
        )
        stats["errors"] += 1


async def _upsert_clickup_transitions(
    *,
    session: AsyncSession,
    ticket_id: UUID,
    activity_entries: list[dict],
    existing_started_at: datetime | None,
    stats: dict,
) -> datetime | None:
    """Upsert ticket_state_transitions from ClickUp task activity.

    Returns the first transition into an in-progress state, or None.
    """
    started_at: datetime | None = None

    for entry in activity_entries:
        field = entry.get("field", "")
        if field != "status":
            continue

        transitioned_at_ms = entry.get("date")
        if not transitioned_at_ms:
            continue
        transitioned_at = _ms_to_datetime(transitioned_at_ms)
        if transitioned_at is None:
            continue

        from_state = (entry.get("before") or "")[:100] or None
        to_state = (entry.get("after") or "")[:100]
        if not to_state:
            continue

        # Detect started_at
        to_normalised = _map_clickup_status(to_state)
        if to_normalised == "in_progress" and started_at is None:
            started_at = transitioned_at

        # Dedup: check before insert
        existing = await session.execute(
            select(TicketStateTransition.id).where(
                TicketStateTransition.ticket_id == ticket_id,
                TicketStateTransition.transitioned_at == transitioned_at,
                TicketStateTransition.to_state == to_state,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        transition = TicketStateTransition(
            ticket_id=ticket_id,
            from_state=from_state,
            to_state=to_state,
            transitioned_at=transitioned_at,
        )
        session.add(transition)
        stats["transitions_upserted"] += 1

    return started_at


# ---------------------------------------------------------------------------
# Identity resolution
# ---------------------------------------------------------------------------


async def _build_identity_cache(session: AsyncSession) -> dict:
    """Build an in-memory lookup cache for ClickUp identity mappings."""
    result = await session.execute(
        select(IdentityMapping).where(IdentityMapping.tool == "clickup")
    )
    mappings = result.scalars().all()
    cache: dict[str, UUID] = {}
    for m in mappings:
        cache[f"clickup_id:{m.tool_user_id}"] = m.canonical_user_id
        if m.tool_email:
            cache[f"email:{m.tool_email.lower()}"] = m.canonical_user_id
    return cache


def _resolve_identity_clickup(
    cache: dict,
    clickup_user_id: str,
) -> UUID | None:
    """Resolve a ClickUp user ID to a canonical user_id."""
    return cache.get(f"clickup_id:{clickup_user_id}")


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


def _extract_story_points(task: dict) -> Decimal | None:
    """Extract story points from ClickUp task custom fields."""
    custom_fields = task.get("custom_fields") or []
    for field in custom_fields:
        name = (field.get("name") or "").lower()
        if "story" in name or "points" in name or "estimate" in name:
            value = field.get("value")
            if value is not None:
                try:
                    return Decimal(str(value))
                except Exception:
                    pass
    return None


def _ms_to_datetime(ms_value: Any) -> datetime | None:
    """Convert a Unix milliseconds value (int or str) to a timezone-aware datetime."""
    if ms_value is None:
        return None
    try:
        ms = int(ms_value)
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _ms_to_date(ms_value: Any) -> date | None:
    """Convert a Unix milliseconds value to a date."""
    dt = _ms_to_datetime(ms_value)
    return dt.date() if dt else None


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
    except Exception as exc:
        struct_logger.error(
            "clickup_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )
