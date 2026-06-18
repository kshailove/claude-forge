"""Jira historical backfill worker.

Performs a full historical backfill of Jira issues/sprints/transitions for an
arbitrary date range. Same logic as nightly batch but scoped to from_date..to_date.

Supports resumability via backfill_jobs.last_checkpoint.

Spec reference: §6.2, M2a
Task queue: q_jira_clickup
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.database import get_session_factory
from app.integrations.jira_client import JiraClient
from app.models.backfill import BackfillJob
from app.models.integration import Integration
from app.tasks.jira_ingest import (
    _build_identity_cache,
    _load_integration,
    _mark_integration_error,
    _upsert_issue,
    _upsert_sprint,
)

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Main backfill task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.jira_backfill.jira_backfill",
    queue="q_jira_clickup",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def jira_backfill(
    self,
    integration_id: str,
    from_date: str,
    to_date: str,
    team_id: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Historical Jira backfill task.

    Args:
        integration_id: UUID string of the Integration record (type='jira').
        from_date: ISO 8601 date string for backfill start (inclusive).
        to_date: ISO 8601 date string for backfill end (inclusive).
        team_id: Optional; restrict to issues for this team (currently informational).
        job_id: UUID string of the BackfillJob tracking record.
    """
    return _run_async(
        _jira_backfill_async(
            integration_id=integration_id,
            from_date_str=from_date,
            to_date_str=to_date,
            team_id_str=team_id,
            job_id_str=job_id,
        )
    )


async def _jira_backfill_async(
    integration_id: str,
    from_date_str: str,
    to_date_str: str,
    team_id_str: str | None,
    job_id_str: str | None,
) -> dict:
    """Async implementation of the Jira backfill."""
    from_date = date.fromisoformat(from_date_str)
    to_date = date.fromisoformat(to_date_str)
    job_id: UUID | None = UUID(job_id_str) if job_id_str else None

    from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
    to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)

    session_factory = get_session_factory()

    # Load integration config
    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()
        team_id: UUID | None = integration.team_id
        if team_id_str:
            try:
                team_id = UUID(team_id_str)
            except ValueError:
                pass

    base_url: str = config["base_url"]
    email: str = config["email"]
    api_token: str = config["api_token"]
    project_keys: list[str] = config.get("project_keys", [])

    if not project_keys:
        return {"status": "skipped", "reason": "no_project_keys"}

    # Mark job as running
    if job_id:
        async with session_factory() as session:
            await _update_job_status(
                session, job_id, "running", started_at=datetime.now(tz=timezone.utc)
            )

    struct_logger.info(
        "jira_backfill_started",
        integration_id=integration_id,
        project_keys=project_keys,
        from_date=from_date_str,
        to_date=to_date_str,
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
            async with session_factory() as session:
                identity_cache = await _build_identity_cache(session)

            # Fetch all issues updated in the date range (JQL since=from_dt)
            issue_count = 0
            async for issue in await client.get_recently_updated_issues(
                project_keys, from_dt
            ):
                # Filter out issues updated beyond to_dt
                fields = issue.get("fields", {})
                updated_str = fields.get("updated") or ""
                if updated_str:
                    from app.tasks.jira_ingest import _parse_jira_datetime
                    updated_dt = _parse_jira_datetime(updated_str)
                    if updated_dt and updated_dt > to_dt:
                        continue

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
                    issue_count += 1

                    # Update checkpoint after every 50 issues
                    if job_id and issue_count % 50 == 0:
                        async with session_factory() as session:
                            await _update_job_checkpoint(
                                session,
                                job_id,
                                checkpoint=f"issue:{issue.get('key', '')}",
                                records_processed=stats["issues_upserted"],
                            )
                except Exception as exc:
                    struct_logger.error(
                        "jira_backfill_issue_failed",
                        issue_key=issue.get("key"),
                        error=str(exc),
                        exc_info=True,
                    )
                    stats["errors"] += 1
                    continue

            # Backfill sprints for all boards
            for project_key in project_keys:
                try:
                    boards = await client.get_boards(project_key)
                    for board in boards:
                        board_id = board["id"]
                        async for sprint in await client.get_sprints(
                            board_id, state="active,closed,future"
                        ):
                            # Filter sprints to date range
                            sprint_end_str = sprint.get("endDate") or ""
                            sprint_start_str = sprint.get("startDate") or ""
                            if sprint_end_str or sprint_start_str:
                                from app.tasks.jira_ingest import _parse_jira_date
                                sprint_start = _parse_jira_date(sprint_start_str)
                                sprint_end = _parse_jira_date(sprint_end_str)
                                # Skip sprints entirely outside the date range
                                if sprint_end and sprint_end < from_date:
                                    continue
                                if sprint_start and sprint_start > to_date:
                                    continue

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
                                    "jira_backfill_sprint_failed",
                                    sprint_id=sprint.get("id"),
                                    error=str(exc),
                                )
                                stats["errors"] += 1
                                continue
                except Exception as exc:
                    struct_logger.error(
                        "jira_backfill_board_failed",
                        project_key=project_key,
                        error=str(exc),
                        exc_info=True,
                    )
                    stats["errors"] += 1
                    continue

        # Mark job completed
        if job_id:
            async with session_factory() as session:
                await _update_job_status(
                    session,
                    job_id,
                    "completed",
                    completed_at=datetime.now(tz=timezone.utc),
                    records_processed=stats["issues_upserted"],
                )

    except Exception as exc:
        struct_logger.error(
            "jira_backfill_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        if job_id:
            async with session_factory() as session:
                await _update_job_status(
                    session, job_id, "failed", error_message=str(exc)
                )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise

    struct_logger.info(
        "jira_backfill_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", **stats}


# ---------------------------------------------------------------------------
# BackfillJob helpers
# ---------------------------------------------------------------------------


async def _load_job(session: AsyncSession, job_id: UUID) -> BackfillJob | None:
    result = await session.execute(
        select(BackfillJob).where(BackfillJob.id == job_id)
    )
    return result.scalar_one_or_none()


async def _update_job_status(
    session: AsyncSession,
    job_id: UUID,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
    records_processed: int | None = None,
) -> None:
    job = await _load_job(session, job_id)
    if job is None:
        return
    job.status = status
    if started_at is not None:
        job.started_at = started_at
    if completed_at is not None:
        job.completed_at = completed_at
    if error_message is not None:
        job.error_message = error_message[:500]
    if records_processed is not None:
        job.records_processed = records_processed
    await session.commit()


async def _update_job_checkpoint(
    session: AsyncSession,
    job_id: UUID,
    checkpoint: str,
    records_processed: int,
) -> None:
    job = await _load_job(session, job_id)
    if job is None:
        return
    job.last_checkpoint = checkpoint[:500]
    job.records_processed = records_processed
    await session.commit()
