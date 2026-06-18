"""Celery tasks for weekly digest generation and delivery.

Beat schedule (defined in celery_app.py):
  Sunday 22:00 UTC  → digest_snapshot_task   — creates DigestRun snapshot
  Monday 06:00 UTC  → digest_trigger_all     — fans out per-user send tasks

Queue: q_digest

Spec §8 M7b.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog
from celery.utils.log import get_task_logger

from app.celery_app import celery_app

logger = get_task_logger(__name__)
struct_logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: run async code from sync Celery task
# ---------------------------------------------------------------------------

def _run_async(coro: Any) -> Any:
    """Execute an async coroutine from a synchronous Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Task 1: Snapshot — Sunday 22:00 UTC
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.digest_tasks.digest_snapshot_task",
    queue="q_digest",
    max_retries=2,
    acks_late=True,
)
def digest_snapshot_task(self) -> dict:
    """Create a DigestRun record capturing the current metric state.

    Fired Sunday 22:00 UTC by Celery Beat.
    """
    struct_logger.info("digest_snapshot_task_started")

    async def _run() -> str:
        from app.core.database import get_session_factory
        from app.digest.generator import DigestGenerator

        generator = DigestGenerator()
        async with get_session_factory()() as db:
            digest_run_id = await generator.create_digest_snapshot(db)
        return digest_run_id

    try:
        digest_run_id = _run_async(_run())
        struct_logger.info("digest_snapshot_task_done", digest_run_id=digest_run_id)
        return {"digest_run_id": digest_run_id, "status": "created"}
    except Exception as exc:
        struct_logger.error("digest_snapshot_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300) from exc


# ---------------------------------------------------------------------------
# Task 2: Send one digest — enqueued per-user by digest_trigger_all
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.digest_tasks.digest_send_task",
    queue="q_digest",
    max_retries=2,
    acks_late=True,
)
def digest_send_task(self, user_id: str, digest_run_id: str) -> dict:
    """Generate and send one user's digest.

    Called by digest_trigger_all for each active user.
    """
    struct_logger.info(
        "digest_send_task_started",
        user_id=user_id,
        digest_run_id=digest_run_id,
    )

    async def _run() -> bool:
        from app.core.database import get_session_factory
        from app.digest.generator import DigestGenerator
        from app.digest.sender import DigestSender

        generator = DigestGenerator()
        sender = DigestSender()
        factory = get_session_factory()

        async with factory() as db:
            # Generate the HTML and store it in digest_emails
            await generator.generate_for_recipient(
                user_id=user_id,
                digest_run_id=digest_run_id,
                db=db,
            )

        async with factory() as db:
            # Send from the stored record
            success = await sender.send_digest(
                user_id=user_id,
                digest_run_id=digest_run_id,
                db=db,
            )
        return success

    try:
        success = _run_async(_run())
        struct_logger.info(
            "digest_send_task_done",
            user_id=user_id,
            digest_run_id=digest_run_id,
            success=success,
        )
        return {"user_id": user_id, "digest_run_id": digest_run_id, "success": success}
    except Exception as exc:
        struct_logger.error(
            "digest_send_task_failed",
            user_id=user_id,
            digest_run_id=digest_run_id,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60) from exc


# ---------------------------------------------------------------------------
# Task 3: Fan-out — Monday 06:00 UTC
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    name="app.tasks.digest_tasks.digest_trigger_all",
    queue="q_digest",
    max_retries=1,
    acks_late=True,
)
def digest_trigger_all(self) -> dict:
    """Fetch the latest DigestRun and enqueue digest_send_task for every active user.

    Fired Monday 06:00 UTC by Celery Beat.
    """
    struct_logger.info("digest_trigger_all_started")

    async def _get_recipients() -> tuple[str, list[str]]:
        from app.core.database import get_session_factory
        from app.models.digest import DigestRun
        from app.models.user import User
        from sqlalchemy import select

        async with get_session_factory()() as db:
            # Get the most recent DigestRun
            run_result = await db.execute(
                select(DigestRun)
                .order_by(DigestRun.created_at.desc())
                .limit(1)
            )
            digest_run: DigestRun | None = run_result.scalar_one_or_none()

            if digest_run is None:
                struct_logger.warning("digest_trigger_all_no_run_found")
                return "", []

            # Get all active users
            users_result = await db.execute(
                select(User.id).where(User.is_active.is_(True))
            )
            user_ids = [str(row[0]) for row in users_result.all()]

        return str(digest_run.id), user_ids

    try:
        digest_run_id, user_ids = _run_async(_get_recipients())

        if not digest_run_id:
            struct_logger.error("digest_trigger_all_aborted_no_run")
            return {"status": "aborted", "reason": "no digest run found"}

        # Enqueue one send task per user with a small stagger
        enqueued = 0
        for i, user_id in enumerate(user_ids):
            digest_send_task.apply_async(
                args=[user_id, digest_run_id],
                queue="q_digest",
                countdown=i * 2,  # 2-second stagger per user
            )
            enqueued += 1

        struct_logger.info(
            "digest_trigger_all_done",
            digest_run_id=digest_run_id,
            enqueued=enqueued,
        )
        return {
            "digest_run_id": digest_run_id,
            "enqueued": enqueued,
            "status": "dispatched",
        }
    except Exception as exc:
        struct_logger.error("digest_trigger_all_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=120) from exc
