"""Jira nightly batch ingestion worker.

Fetches issues updated in the last 24 hours across all configured project_keys.
Upserts records into tickets, ticket_state_transitions, and sprints tables.
Updates integrations.last_synced_at on success.

Spec reference: §6.2, M2a
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
from app.integrations.jira_client import JiraClient, _map_jira_status
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
# Ticket type mapping from Jira issue type names
# ---------------------------------------------------------------------------

JIRA_ISSUETYPE_TO_TICKET_TYPE: dict[str, str] = {
    "bug": "bug",
    "defect": "bug",
    "story": "feature",
    "epic": "feature",
    "task": "feature",
    "new feature": "feature",
    "improvement": "feature",
    "sub-task": "feature",
    "subtask": "feature",
    "tech debt": "tech_debt",
    "technical debt": "tech_debt",
    "refactor": "tech_debt",
    "risk": "risk",
    "security": "risk",
}


def _map_issue_type(raw_type: str) -> str | None:
    """Map a Jira issue type to our ticket_type enum, or None if unmappable."""
    return JIRA_ISSUETYPE_TO_TICKET_TYPE.get(raw_type.lower().strip())


# ---------------------------------------------------------------------------
# Main nightly batch task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.jira_ingest.jira_nightly_batch",
    queue="q_jira_clickup",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def jira_nightly_batch(self, integration_id: str) -> dict:
    """Nightly Jira batch worker.

    Pulls all issues updated in the last 24 h across configured project_keys.
    Upserts to tickets + ticket_state_transitions + sprints tables.
    Updates integrations.last_synced_at.

    Args:
        integration_id: UUID string of the Integration record (type='jira').
    """
    return _run_async(_jira_nightly_batch_async(integration_id))


async def _jira_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly Jira batch."""
    session_factory = get_session_factory()

    # Yesterday start UTC — covers the full previous day's changes
    now = datetime.now(tz=timezone.utc)
    yesterday_start = (now - timedelta(hours=24)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Load integration config
    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()
        team_id: UUID | None = integration.team_id

    base_url: str = config["base_url"]
    email: str = config["email"]
    api_token: str = config["api_token"]
    project_keys: list[str] = config.get("project_keys", [])

    if not project_keys:
        struct_logger.warning(
            "jira_no_project_keys",
            integration_id=integration_id,
        )
        return {"status": "skipped", "reason": "no_project_keys"}

    struct_logger.info(
        "jira_nightly_batch_started",
        integration_id=integration_id,
        project_keys=project_keys,
        since_dt=yesterday_start.isoformat(),
    )

    stats = {
        "issues_upserted": 0,
        "transitions_upserted": 0,
        "sprints_upserted": 0,
        "errors": 0,
    }

    try:
        async with JiraClient(
            base_url=base_url, email=email, api_token=api_token
        ) as client:
            # Build identity cache once
            async with session_factory() as session:
                identity_cache = await _build_identity_cache(session)

            # ---- Ingest recently updated issues ----
            async for issue in await client.get_recently_updated_issues(
                project_keys, yesterday_start
            ):
                try:
                    async with session_factory() as session:
                        await _upsert_issue(
                            client=client,
                            session=session,
                            issue=issue,
                            integration_id=UUID(integration_id),
                            team_id=team_id,
                            identity_cache=identity_cache,
                            stats=stats,
                        )
                        await session.commit()
                except Exception as exc:
                    struct_logger.error(
                        "jira_issue_processing_failed",
                        issue_key=issue.get("key"),
                        error=str(exc),
                        exc_info=True,
                    )
                    stats["errors"] += 1
                    continue

            # ---- Ingest active sprints for all boards ----
            for project_key in project_keys:
                try:
                    boards = await client.get_boards(project_key)
                    for board in boards:
                        board_id = board["id"]
                        async for sprint in await client.get_sprints(
                            board_id, state="active,closed,future"
                        ):
                            try:
                                async with session_factory() as session:
                                    await _upsert_sprint(
                                        session=session,
                                        sprint_data=sprint,
                                        integration_id=UUID(integration_id),
                                        team_id=team_id,
                                        stats=stats,
                                    )
                                    await session.commit()
                            except Exception as exc:
                                struct_logger.error(
                                    "jira_sprint_upsert_failed",
                                    sprint_id=sprint.get("id"),
                                    error=str(exc),
                                )
                                stats["errors"] += 1
                                continue
                except Exception as exc:
                    struct_logger.error(
                        "jira_board_fetch_failed",
                        project_key=project_key,
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
            "jira_nightly_batch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise  # Triggers Celery retry

    struct_logger.info(
        "jira_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Issue upsert
# ---------------------------------------------------------------------------


async def _upsert_issue(
    *,
    client: JiraClient,
    session: AsyncSession,
    issue: dict,
    integration_id: UUID,
    team_id: UUID | None,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Upsert a single Jira issue into the tickets table."""
    external_id: str = issue["key"]
    fields: dict = issue.get("fields", {})

    title: str = (fields.get("summary") or "")[:500]
    raw_status: str = (
        (fields.get("status") or {}).get("name") or "unknown"
    )
    status_normalised = _map_jira_status(raw_status)

    # Issue type → ticket_type enum
    raw_issue_type: str = (
        (fields.get("issuetype") or {}).get("name") or ""
    )
    ticket_type = _map_issue_type(raw_issue_type)

    # Story points — Jira stores in customfield_10016 or 'story_points'
    story_points_raw = fields.get("story_points") or fields.get("customfield_10016")
    story_points: Decimal | None = None
    if story_points_raw is not None:
        try:
            story_points = Decimal(str(story_points_raw))
        except Exception:
            pass

    # Assignee
    assignee_account_id: str | None = None
    if fields.get("assignee"):
        assignee_account_id = fields["assignee"].get("accountId")
    assignee_user_id = _resolve_identity_jira(identity_cache, assignee_account_id)

    # Timestamps
    created_at = _parse_jira_datetime(fields.get("created") or "")
    updated_at = _parse_jira_datetime(fields.get("updated") or "")
    resolution_date_str = fields.get("resolutiondate")
    completed_at: datetime | None = None
    if resolution_date_str:
        completed_at = _parse_jira_datetime(resolution_date_str)

    if created_at is None or updated_at is None:
        struct_logger.warning("jira_issue_missing_dates", external_id=external_id)
        return

    # Resolve sprint (if present in fields)
    sprint_id: UUID | None = None
    sprint_field = fields.get("sprint") or {}
    if sprint_field and isinstance(sprint_field, dict):
        sprint_external_id = str(sprint_field.get("id", ""))
        if sprint_external_id:
            sprint_result = await session.execute(
                select(Sprint.id).where(
                    Sprint.integration_id == integration_id,
                    Sprint.external_id == sprint_external_id,
                )
            )
            sprint_id = sprint_result.scalar_one_or_none()

    # Upsert ticket
    stmt = (
        pg_insert(Ticket)
        .values(
            integration_id=integration_id,
            external_id=external_id,
            title=title,
            assignee_user_id=assignee_user_id,
            sprint_id=sprint_id,
            status=raw_status[:100],
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
                status=raw_status[:100],
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
    stats["issues_upserted"] += 1

    # ---- Fetch and upsert changelog (state transitions) ----
    try:
        changelog_entries = await client.get_issue_changelog(issue.get("id", external_id))
        started_at = await _upsert_transitions(
            session=session,
            ticket_id=ticket_db_id,
            changelog_entries=changelog_entries,
            existing_started_at=existing_started_at,
            stats=stats,
        )
        # Back-patch started_at on the ticket if we now know it
        if started_at is not None and existing_started_at is None:
            update_stmt = (
                pg_insert(Ticket)
                .values(
                    integration_id=integration_id,
                    external_id=external_id,
                    title=title,
                    status=raw_status[:100],
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
            await session.execute(update_stmt)
    except Exception as exc:
        struct_logger.warning(
            "jira_changelog_fetch_failed",
            external_id=external_id,
            error=str(exc),
        )
        stats["errors"] += 1


async def _upsert_transitions(
    *,
    session: AsyncSession,
    ticket_id: UUID,
    changelog_entries: list[dict],
    existing_started_at: datetime | None,
    stats: dict,
) -> datetime | None:
    """Upsert ticket_state_transitions from Jira changelog.

    Returns the first transition into an in-progress state (started_at),
    or None if not found.
    """
    started_at: datetime | None = None

    for entry in changelog_entries:
        transitioned_at = _parse_jira_datetime(entry.get("created") or "")
        if transitioned_at is None:
            continue

        for item in entry.get("items", []):
            if item.get("field") != "status":
                continue

            from_state = (item.get("fromString") or "").strip()[:100] or None
            to_state = (item.get("toString") or "").strip()[:100]
            if not to_state:
                continue

            # Detect started_at: first transition into an in-progress state
            to_normalised = _map_jira_status(to_state)
            if to_normalised == "in_progress" and started_at is None:
                started_at = transitioned_at

            # Upsert transition — use (ticket_id, transitioned_at, to_state) as
            # a logical unique key via INSERT ... ON CONFLICT DO NOTHING.
            # ticket_state_transitions has no unique constraint beyond PK so we
            # do a check-then-insert pattern.
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
# Sprint upsert
# ---------------------------------------------------------------------------


async def _upsert_sprint(
    *,
    session: AsyncSession,
    sprint_data: dict,
    integration_id: UUID,
    team_id: UUID | None,
    stats: dict,
) -> None:
    """Upsert a Jira sprint into the sprints table."""
    external_id = str(sprint_data["id"])
    name: str = (sprint_data.get("name") or "")[:500]
    raw_state: str = sprint_data.get("state", "future").lower()

    state_map = {
        "active": "active",
        "closed": "completed",
        "future": "future",
    }
    state = state_map.get(raw_state, "future")

    start_date: date | None = _parse_jira_date(sprint_data.get("startDate"))
    end_date: date | None = _parse_jira_date(sprint_data.get("endDate"))

    if team_id is None:
        return  # Cannot upsert sprint without team

    stmt = (
        pg_insert(Sprint)
        .values(
            integration_id=integration_id,
            external_id=external_id,
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
# Identity resolution
# ---------------------------------------------------------------------------


async def _build_identity_cache(session: AsyncSession) -> dict:
    """Build an in-memory lookup cache for Jira identity mappings."""
    result = await session.execute(
        select(IdentityMapping).where(IdentityMapping.tool == "jira")
    )
    mappings = result.scalars().all()
    cache: dict[str, UUID] = {}
    for m in mappings:
        cache[f"account_id:{m.tool_user_id}"] = m.canonical_user_id
        if m.tool_email:
            cache[f"email:{m.tool_email.lower()}"] = m.canonical_user_id
    return cache


def _resolve_identity_jira(
    cache: dict,
    account_id: str | None,
) -> UUID | None:
    """Resolve a Jira account ID to a canonical user_id."""
    if account_id:
        user_id = cache.get(f"account_id:{account_id}")
        if user_id:
            return user_id
    return None


# ---------------------------------------------------------------------------
# Misc helpers
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
    except Exception as exc:
        struct_logger.error(
            "jira_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )


def _parse_jira_datetime(dt_str: str) -> datetime | None:
    """Parse a Jira ISO 8601 datetime string to timezone-aware datetime."""
    if not dt_str:
        return None
    try:
        # Jira returns: "2026-06-12T14:30:00.000+0530" or "...+0000"
        # Python's fromisoformat doesn't handle "+0530" without colon until 3.11
        import re as _re

        # Normalise offset: +0530 → +05:30
        dt_str = _re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", dt_str.rstrip("Z"))
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _parse_jira_date(date_str: str | None) -> date | None:
    """Parse a Jira date string (YYYY-MM-DD or ISO datetime) to a date."""
    if not date_str:
        return None
    try:
        # Could be full datetime or just date
        if "T" in date_str:
            dt = _parse_jira_datetime(date_str)
            return dt.date() if dt else None
        return date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return None
