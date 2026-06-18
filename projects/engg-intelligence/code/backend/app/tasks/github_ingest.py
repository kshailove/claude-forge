"""GitHub nightly batch ingestion worker.

Fetches PRs/reviews/commits/releases updated in the last 24 hours for all
repos in the configured GitHub org. Upserts records into PostgreSQL using
ON CONFLICT DO UPDATE. Handles rate limits and 5xx errors with retries.

Spec reference: §5.3, §6.1, M1a
Task queue: q_github
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.database import get_session_factory
from app.integrations.github_client import GitHubClient, GitHubRateLimitError
from app.models.github import Commit, GithubRelease, PRReview, PullRequest
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
    name="app.tasks.github_ingest.github_nightly_batch",
    queue="q_github",
    max_retries=3,
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def github_nightly_batch(self, integration_id: str) -> dict:
    """Nightly GitHub batch worker.

    Pulls all PRs/reviews/commits/releases updated in the last 24h for all
    repos in the org. Upserts to PostgreSQL. Updates integrations.last_synced_at.

    Args:
        integration_id: UUID string of the Integration record.
    """
    return _run_async(_github_nightly_batch_async(integration_id))


async def _github_nightly_batch_async(integration_id: str) -> dict:
    """Async implementation of the nightly GitHub batch."""
    session_factory = get_session_factory()
    since_dt = datetime.now(tz=timezone.utc) - timedelta(hours=24)

    async with session_factory() as session:
        # Load integration and decrypt config
        integration = await _load_integration(session, integration_id)
        config = integration.get_config()

        pat = config["personal_access_token"]
        org_name = config["org_name"]
        tag_pattern = config.get("release_tag_pattern", ".*")

        # PAT expiry warning check
        expires_at_str = config.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                days_until_expiry = (expires_at - datetime.now(tz=timezone.utc)).days
                if days_until_expiry <= 30:
                    struct_logger.warning(
                        "github_pat_expiry_warning",
                        integration_id=integration_id,
                        expires_at=expires_at_str,
                        days_remaining=days_until_expiry,
                        flag="GITHUB_PAT_EXPIRY_WARNING",
                    )
            except (ValueError, TypeError):
                pass

    struct_logger.info(
        "github_nightly_batch_started",
        integration_id=integration_id,
        org_name=org_name,
        since_dt=since_dt.isoformat(),
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
            # Enumerate all repos in org
            async with session_factory() as session:
                async for repo in await client.get_org_repos(org_name):
                    repo_full_name: str = repo["full_name"]
                    owner, repo_name = repo_full_name.split("/", 1)

                    try:
                        await _process_repo(
                            client=client,
                            session=session,
                            repo_full_name=repo_full_name,
                            owner=owner,
                            repo_name=repo_name,
                            since_dt=since_dt,
                            tag_pattern=tag_pattern,
                            integration_id=UUID(integration_id),
                            stats=stats,
                        )
                        await session.commit()
                        stats["repos_processed"] += 1
                    except Exception as exc:
                        await session.rollback()
                        struct_logger.error(
                            "github_repo_processing_failed",
                            repo=repo_full_name,
                            error=str(exc),
                            exc_info=True,
                        )
                        stats["errors"] += 1
                        # Never abort the whole batch for one repo failure
                        continue

        # Update last_synced_at on success
        async with session_factory() as session:
            integration = await _load_integration(session, integration_id)
            integration.last_synced_at = datetime.now(tz=timezone.utc)
            integration.status = "connected"
            await session.commit()

    except GitHubRateLimitError as exc:
        struct_logger.error(
            "github_rate_limit_exhausted",
            integration_id=integration_id,
            reset_at=exc.reset_at.isoformat(),
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise  # Will trigger Celery retry

    except Exception as exc:
        struct_logger.error(
            "github_nightly_batch_failed",
            integration_id=integration_id,
            error=str(exc),
            exc_info=True,
        )
        async with session_factory() as session:
            await _mark_integration_error(session, integration_id, str(exc))
        raise  # Will trigger Celery retry

    struct_logger.info(
        "github_nightly_batch_completed",
        integration_id=integration_id,
        **stats,
    )
    return {"status": "completed", "integration_id": integration_id, **stats}


# ---------------------------------------------------------------------------
# Per-repo processing
# ---------------------------------------------------------------------------


async def _process_repo(
    *,
    client: GitHubClient,
    session: AsyncSession,
    repo_full_name: str,
    owner: str,
    repo_name: str,
    since_dt: datetime,
    tag_pattern: str,
    integration_id: UUID,
    stats: dict,
) -> None:
    """Process a single repository: fetch and upsert PRs, reviews, commits, releases."""
    # Determine team_id for this repo — look up by repo mapping or use integration's team
    team_id = await _get_team_id_for_repo(session, repo_full_name, integration_id)
    if team_id is None:
        struct_logger.debug(
            "github_repo_no_team", repo=repo_full_name
        )
        return

    # Build identity lookup cache for this batch
    identity_cache = await _build_identity_cache(session)

    # ---- PRs ----
    async for pr_data in await client.get_recent_prs(owner, repo_name, since_dt):
        try:
            await _upsert_pr(
                session=session,
                client=client,
                pr_data=pr_data,
                repo_full_name=repo_full_name,
                owner=owner,
                repo_name=repo_name,
                team_id=team_id,
                identity_cache=identity_cache,
                stats=stats,
            )
        except Exception as exc:
            struct_logger.error(
                "github_pr_processing_failed",
                repo=repo_full_name,
                pr_number=pr_data.get("number"),
                error=str(exc),
                exc_info=True,
            )
            stats["errors"] += 1
            continue

    # ---- Releases ----
    try:
        releases = await client.get_recent_releases(owner, repo_name, tag_pattern)
        for release_data in releases:
            published_at_str = release_data.get("published_at")
            if published_at_str is None:
                continue
            published_at = _parse_github_datetime(published_at_str)
            # Only ingest releases published since yesterday
            if published_at < since_dt:
                continue
            await _upsert_release(
                session=session,
                release_data=release_data,
                repo_full_name=repo_full_name,
                team_id=team_id,
            )
            stats["releases_upserted"] += 1
    except Exception as exc:
        struct_logger.error(
            "github_releases_fetch_failed",
            repo=repo_full_name,
            error=str(exc),
        )
        stats["errors"] += 1


async def _upsert_pr(
    *,
    session: AsyncSession,
    client: GitHubClient,
    pr_data: dict,
    repo_full_name: str,
    owner: str,
    repo_name: str,
    team_id: UUID,
    identity_cache: dict,
    stats: dict,
) -> None:
    """Upsert a single PR including its reviews and commits."""
    pr_number: int = pr_data["number"]
    github_id: int = pr_data["id"]
    state_raw: str = pr_data["state"]  # "open" | "closed"
    merged_at_str: str | None = pr_data.get("merged_at")
    closed_at_str: str | None = pr_data.get("closed_at")
    created_at_str: str = pr_data["created_at"]
    updated_at_str: str = pr_data["updated_at"]

    # Normalize state
    if merged_at_str:
        state = "merged"
    elif state_raw == "closed":
        state = "closed"
    else:
        state = "open"

    created_at = _parse_github_datetime(created_at_str)
    updated_at = _parse_github_datetime(updated_at_str)
    merged_at = _parse_github_datetime(merged_at_str) if merged_at_str else None
    closed_at = _parse_github_datetime(closed_at_str) if closed_at_str else None

    cycle_time_seconds: int | None = None
    if merged_at is not None:
        cycle_time_seconds = int((merged_at - created_at).total_seconds())

    # Author identity resolution
    author_login: str | None = None
    author_email: str | None = None
    if pr_data.get("user"):
        author_login = pr_data["user"].get("login")
    author_user_id = _resolve_identity(identity_cache, login=author_login, email=author_email)

    pr_size_additions: int = pr_data.get("additions", 0) or 0
    pr_size_deletions: int = pr_data.get("deletions", 0) or 0

    # ---- Fetch reviews ----
    reviews = await client.get_pr_reviews(owner, repo_name, pr_number)
    first_review_at: datetime | None = None
    if reviews:
        submitted_times = [
            _parse_github_datetime(r["submitted_at"])
            for r in reviews
            if r.get("submitted_at")
        ]
        if submitted_times:
            first_review_at = min(submitted_times)

    # ---- Fetch commits ----
    commits = await client.get_pr_commits(owner, repo_name, pr_number)
    latest_commit_at: datetime | None = None
    if commits:
        commit_times = [
            _parse_github_datetime(c["commit"]["committer"]["date"])
            for c in commits
            if c.get("commit", {}).get("committer", {}).get("date")
        ]
        if commit_times:
            latest_commit_at = max(commit_times)

    # last_activity_at = max(updated_at, first_review_at, latest_commit_at)
    last_activity_candidates = [updated_at]
    if first_review_at:
        last_activity_candidates.append(first_review_at)
    if latest_commit_at:
        last_activity_candidates.append(latest_commit_at)
    last_activity_at = max(last_activity_candidates)

    # ---- Upsert pull_requests ----
    pr_stmt = (
        pg_insert(PullRequest)
        .values(
            github_id=github_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            title=pr_data.get("title", "")[:500],
            author_user_id=author_user_id,
            state=state,
            created_at=created_at,
            merged_at=merged_at,
            closed_at=closed_at,
            first_review_at=first_review_at,
            cycle_time_seconds=cycle_time_seconds,
            pr_size_additions=pr_size_additions,
            pr_size_deletions=pr_size_deletions,
            base_branch=(pr_data.get("base", {}).get("ref") or "")[:255],
            head_branch=(pr_data.get("head", {}).get("ref") or "")[:255],
            team_id=team_id,
            updated_at=updated_at,
            last_activity_at=last_activity_at,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=dict(
                title=pr_data.get("title", "")[:500],
                author_user_id=author_user_id,
                state=state,
                merged_at=merged_at,
                closed_at=closed_at,
                first_review_at=first_review_at,
                cycle_time_seconds=cycle_time_seconds,
                pr_size_additions=pr_size_additions,
                pr_size_deletions=pr_size_deletions,
                updated_at=updated_at,
                last_activity_at=last_activity_at,
            ),
        )
        .returning(PullRequest.id)
    )
    pr_result = await session.execute(pr_stmt)
    pr_id: UUID = pr_result.scalar_one()
    stats["prs_upserted"] += 1

    # ---- Upsert pr_reviews ----
    for review_data in reviews:
        try:
            await _upsert_review(
                session=session,
                review_data=review_data,
                pr_id=pr_id,
                identity_cache=identity_cache,
            )
            stats["reviews_upserted"] += 1
        except Exception as exc:
            struct_logger.error(
                "github_review_upsert_failed",
                pr_id=str(pr_id),
                error=str(exc),
            )
            stats["errors"] += 1

    # ---- Upsert commits ----
    for commit_data in commits:
        try:
            await _upsert_commit(
                session=session,
                commit_data=commit_data,
                repo_full_name=repo_full_name,
                pr_id=pr_id,
                identity_cache=identity_cache,
            )
            stats["commits_upserted"] += 1
        except Exception as exc:
            struct_logger.error(
                "github_commit_upsert_failed",
                pr_id=str(pr_id),
                error=str(exc),
            )
            stats["errors"] += 1


async def _upsert_review(
    *,
    session: AsyncSession,
    review_data: dict,
    pr_id: UUID,
    identity_cache: dict,
) -> None:
    """Upsert a single PR review record."""
    github_id: int = review_data["id"]
    submitted_at_str: str | None = review_data.get("submitted_at")
    if not submitted_at_str:
        return

    reviewer_login: str | None = None
    if review_data.get("user"):
        reviewer_login = review_data["user"].get("login")
    reviewer_user_id = _resolve_identity(identity_cache, login=reviewer_login, email=None)

    # Normalize review state
    raw_state = (review_data.get("state") or "").upper()
    state_map = {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes_requested",
        "COMMENTED": "commented",
        "DISMISSED": "approved",  # treat dismissed as approved for scoring
    }
    state = state_map.get(raw_state, "commented")

    # GitHub review list does not return comment_count directly;
    # we set to 0 and let a future enhancement fetch review comments
    comment_count = 0
    body = review_data.get("body") or ""
    if body.strip():
        comment_count = 1  # At minimum 1 if there's a review body

    stmt = (
        pg_insert(PRReview)
        .values(
            github_id=github_id,
            pr_id=pr_id,
            reviewer_user_id=reviewer_user_id,
            submitted_at=_parse_github_datetime(submitted_at_str),
            state=state,
            comment_count=comment_count,
        )
        .on_conflict_do_update(
            index_elements=["github_id"],
            set_=dict(
                reviewer_user_id=reviewer_user_id,
                state=state,
                comment_count=comment_count,
            ),
        )
    )
    await session.execute(stmt)


async def _upsert_commit(
    *,
    session: AsyncSession,
    commit_data: dict,
    repo_full_name: str,
    pr_id: UUID,
    identity_cache: dict,
) -> None:
    """Upsert a single commit record."""
    sha: str = commit_data["sha"]
    committer_date_str: str | None = (
        commit_data.get("commit", {}).get("committer", {}).get("date")
    )
    author_email: str | None = (
        commit_data.get("commit", {}).get("author", {}).get("email")
    )
    author_login: str | None = None
    if commit_data.get("author"):
        author_login = commit_data["author"].get("login")

    author_user_id = _resolve_identity(identity_cache, login=author_login, email=author_email)

    if not committer_date_str:
        return

    stmt = (
        pg_insert(Commit)
        .values(
            sha=sha,
            repo_full_name=repo_full_name,
            author_user_id=author_user_id,
            committed_at=_parse_github_datetime(committer_date_str),
            pr_id=pr_id,
        )
        .on_conflict_do_update(
            index_elements=["sha"],
            set_=dict(
                author_user_id=author_user_id,
                pr_id=pr_id,
            ),
        )
    )
    await session.execute(stmt)


async def _upsert_release(
    *,
    session: AsyncSession,
    release_data: dict,
    repo_full_name: str,
    team_id: UUID,
) -> None:
    """Upsert a GitHub release record."""
    release_id: int = release_data["id"]
    tag_name: str = release_data.get("tag_name", "")[:255]
    published_at_str: str = release_data["published_at"]

    stmt = (
        pg_insert(GithubRelease)
        .values(
            release_id=release_id,
            repo_full_name=repo_full_name,
            tag_name=tag_name,
            published_at=_parse_github_datetime(published_at_str),
            team_id=team_id,
        )
        .on_conflict_do_update(
            index_elements=["release_id"],
            set_=dict(
                tag_name=tag_name,
                repo_full_name=repo_full_name,
                team_id=team_id,
            ),
        )
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Identity resolution helpers
# ---------------------------------------------------------------------------


async def _build_identity_cache(session: AsyncSession) -> dict:
    """Build an in-memory {login: user_id, email: user_id} lookup cache.

    Fetches all GitHub identity mappings from identity_mappings table.
    """
    result = await session.execute(
        select(IdentityMapping).where(IdentityMapping.tool == "github")
    )
    mappings = result.scalars().all()

    cache: dict[str, UUID] = {}
    for m in mappings:
        cache[f"login:{m.tool_user_id}"] = m.canonical_user_id
        if m.tool_email:
            cache[f"email:{m.tool_email.lower()}"] = m.canonical_user_id
    return cache


def _resolve_identity(
    cache: dict,
    login: str | None,
    email: str | None,
) -> UUID | None:
    """Resolve a GitHub login or email to a canonical user_id.

    Returns None if no mapping found (PR will be recorded without author attribution).
    """
    if login:
        user_id = cache.get(f"login:{login}")
        if user_id:
            return user_id
    if email:
        user_id = cache.get(f"email:{email.lower()}")
        if user_id:
            return user_id
    return None


# ---------------------------------------------------------------------------
# Team resolution
# ---------------------------------------------------------------------------


async def _get_team_id_for_repo(
    session: AsyncSession,
    repo_full_name: str,
    integration_id: UUID,
) -> UUID | None:
    """Determine which team owns a given repository.

    Strategy:
    1. Check existing pull_requests for this repo — use their team_id.
    2. Fall back: check if integration has a team_id.
    3. Fall back: return None (repo not yet mapped to a team).
    """
    # Check existing PRs for this repo
    result = await session.execute(
        select(PullRequest.team_id)
        .where(PullRequest.repo_full_name == repo_full_name)
        .limit(1)
    )
    existing_team_id = result.scalar_one_or_none()
    if existing_team_id:
        return existing_team_id

    # Fall back to integration team_id
    result = await session.execute(
        select(Integration.team_id).where(Integration.id == integration_id)
    )
    team_id = result.scalar_one_or_none()
    return team_id


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
        struct_logger.error(
            "github_integration_error_set",
            integration_id=integration_id,
            error=error_msg[:200],
        )
    except Exception as exc:
        struct_logger.error(
            "github_mark_error_failed",
            integration_id=integration_id,
            error=str(exc),
        )


def _parse_github_datetime(dt_str: str) -> datetime:
    """Parse a GitHub ISO 8601 datetime string to a timezone-aware datetime."""
    # GitHub uses "2026-06-12T01:00:00Z" format
    dt_str = dt_str.rstrip("Z")
    if "+" in dt_str:
        dt = datetime.fromisoformat(dt_str)
    else:
        dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
