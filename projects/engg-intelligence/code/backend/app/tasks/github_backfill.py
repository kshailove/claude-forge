"""GitHub historical backfill worker.

Performs a full historical backfill of GitHub PR/review/commit/release data
for an arbitrary date range. Uses the same REST API client as the nightly
batch but with date-range filtering instead of `since=yesterday`.

Supports resumability via ``backfill_jobs.last_checkpoint``.

Spec reference: §5.3 (Backfill strategy), §3.11 (backfill_jobs), M1b
Task queue: q_github
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
from app.integrations.github_client import GitHubClient, GitHubRateLimitError
from app.models.backfill import BackfillJob
from app.models.integration import Integration
from app.tasks.github_ingest import (
    _build_identity_cache,
    _get_team_id_for_repo,
    _load_integration,
    _mark_integration_error,
    _parse_github_datetime,
    _upsert_commit,
    _upsert_pr,
    _upsert_release,
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
    name="app.tasks.github_backfill.github_backfill",
    queue="q_github",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def github_backfill(
    self,
    integration_id: str,
    from_date: str,
    to_date: str,
    team_id: str | None = None,
    job_id: str | None = None,
) -> dict:
    """Historical GitHub backfill task.

    Args:
        integration_id: UUID string of the Integration record.
        from_date: ISO 8601 date string for backfill start (inclusive).
        to_date: ISO 8601 date string for backfill end (inclusive).
        team_id: Optional UUID string. If provided, only backfill repos for this team.
        job_id: UUID string of the BackfillJob tracking record.
    """
    return _run_async(
        _github_backfill_async(
            integration_id=integration_id,
            from_date_str=from_date,
            to_date_str=to_date,
            team_id_str=team_id,
            job_id_str=job_id,
        )
    )


async def _github_backfill_async(
    integration_id: str,
    from_date_str: str,
    to_date_str: str,
    team_id_str: str | None,
    job_id_str: str | None,
) -> dict:
    """Async implementation of the GitHub backfill."""
    from_date = date.fromisoformat(from_date_str)
    to_date = date.fromisoformat(to_date_str)
    team_id: UUID | None = UUID(team_id_str) if team_id_str else None
    job_id: UUID | None = UUID(job_id_str) if job_id_str else None

    # from_dt / to_dt as timezone-aware datetimes for comparison
    from_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
    to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)

    session_factory = get_session_factory()

    # Load integration config
    async with session_factory() as session:
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()
        pat = config["personal_access_token"]
        org_name = config["org_name"]
        tag_pattern = config.get("release_tag_pattern", ".*")

        # Load checkpoint from job if resuming
        checkpoint_repo: str | None = None
        checkpoint_pr_number: int | None = None
        if job_id:
            job = await _load_job(session, job_id)
            if job and job.last_checkpoint:
                parts = job.last_checkpoint.split(":")
                if len(parts) == 2:
                    checkpoint_repo = parts[0]
                    try:
                        checkpoint_pr_number = int(parts[1])
                    except ValueError:
                        pass

    # Mark job as running
    if job_id:
        async with session_factory() as session:
            await _update_job_status(
                session, job_id, "running", started_at=datetime.now(tz=timezone.utc)
            )

    struct_logger.info(
        "github_backfill_started",
        integration_id=integration_id,
        from_date=from_date_str,
        to_date=to_date_str,
        team_id=team_id_str,
        checkpoint_repo=checkpoint_repo,
    )

    stats = {
        "repos_processed": 0,
        "prs_upserted": 0,
        "reviews_upserted": 0,
        "commits_upserted": 0,
        "releases_upserted": 0,
        "errors": 0,
    }

    try:
        async with GitHubClient(pat=pat) as client:
            # Enumerate repos
            repos: list[dict] = []
            async for repo in await client.get_org_repos(org_name):
                repos.append(repo)

            # Total repos gives a rough baseline for progress
            if job_id:
                async with session_factory() as session:
                    await _update_job_records_total(session, job_id, len(repos))

            past_checkpoint = checkpoint_repo is None  # True if no checkpoint to skip

            for repo in repos:
                repo_full_name: str = repo["full_name"]
                owner, repo_name = repo_full_name.split("/", 1)

                # Skip repos before checkpoint
                if not past_checkpoint:
                    if repo_full_name == checkpoint_repo:
                        past_checkpoint = True
                    else:
                        continue

                # If team_id filter provided, skip repos not belonging to that team
                if team_id is not None:
                    async with session_factory() as session:
                        repo_team = await _get_team_id_for_repo(
                            session, repo_full_name, UUID(integration_id)
                        )
                    if repo_team != team_id:
                        continue

                try:
                    async with session_factory() as session:
                        identity_cache = await _build_identity_cache(session)
                        repo_team_id = await _get_team_id_for_repo(
                            session, repo_full_name, UUID(integration_id)
                        )

                    if repo_team_id is None:
                        struct_logger.debug(
                            "github_backfill_repo_no_team", repo=repo_full_name
                        )
                        continue

                    # Fetch PRs created within the date range
                    # For backfill we use REST /pulls with since=from_dt and filter by created_at
                    pr_count = 0
                    async with session_factory() as session:
                        async for pr_data in await client.get_recent_prs(
                            owner, repo_name, since_dt=from_dt
                        ):
                            pr_created_at = _parse_github_datetime(pr_data["created_at"])
                            if pr_created_at > to_dt:
                                continue
                            # Skip PRs before checkpoint for the first repo
                            if (
                                repo_full_name == checkpoint_repo
                                and checkpoint_pr_number is not None
                                and pr_data["number"] <= checkpoint_pr_number
                            ):
                                continue

                            try:
                                await _upsert_pr(
                                    client=client,
                                    session=session,
                                    pr_data=pr_data,
                                    repo_full_name=repo_full_name,
                                    owner=owner,
                                    repo_name=repo_name,
                                    team_id=repo_team_id,
                                    identity_cache=identity_cache,
                                    stats=stats,
                                )
                                pr_count += 1

                                # Checkpoint after each PR — records_processed tracks repos done
                                # so it remains consistent with records_total (also repo count).
                                if job_id:
                                    checkpoint = f"{repo_full_name}:{pr_data['number']}"
                                    await _update_job_checkpoint(
                                        session,
                                        job_id,
                                        checkpoint=checkpoint,
                                        records_processed=stats["repos_processed"],
                                    )
                            except Exception as exc:
                                struct_logger.error(
                                    "github_backfill_pr_failed",
                                    repo=repo_full_name,
                                    pr_number=pr_data.get("number"),
                                    error=str(exc),
                                )
                                stats["errors"] += 1
                                continue

                        await session.commit()

                    # Fetch releases in date range
                    async with session_factory() as session:
                        releases = await client.get_recent_releases(
                            owner, repo_name, tag_pattern
                        )
                        for release_data in releases:
                            pub_at = _parse_github_datetime(release_data["published_at"])
                            if from_dt <= pub_at <= to_dt:
                                await _upsert_release(
                                    session=session,
                                    release_data=release_data,
                                    repo_full_name=repo_full_name,
                                    team_id=repo_team_id,
                                )
                                stats["releases_upserted"] += 1
                        await session.commit()

                    stats["repos_processed"] += 1

                    # Repo fully done — update progress counter (repos done / repos total)
                    if job_id:
                        async with session_factory() as session:
                            await _update_job_checkpoint(
                                session,
                                job_id,
                                checkpoint=f"{repo_full_name}:done",
                                records_processed=stats["repos_processed"],
                            )

                except Exception as exc:
                    struct_logger.error(
                        "github_backfill_repo_failed",
                        repo=repo_full_name,
                        error=str(exc),
                        exc_info=True,
                    )
                    stats["errors"] += 1
                    continue

        # Mark job completed — final repos count matches records_total
        if job_id:
            async with session_factory() as session:
                await _update_job_status(
                    session,
                    job_id,
                    "completed",
                    completed_at=datetime.now(tz=timezone.utc),
                    records_processed=stats["repos_processed"],
                )

    except GitHubRateLimitError as exc:
        struct_logger.error(
            "github_backfill_rate_limit",
            integration_id=integration_id,
            reset_at=exc.reset_at.isoformat(),
        )
        if job_id:
            async with session_factory() as session:
                await _update_job_status(
                    session, job_id, "failed", error_message=str(exc)
                )
        raise

    except Exception as exc:
        struct_logger.error(
            "github_backfill_failed",
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
        "github_backfill_completed",
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


async def _update_job_records_total(
    session: AsyncSession, job_id: UUID, total: int
) -> None:
    job = await _load_job(session, job_id)
    if job is None:
        return
    job.records_total = total
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
