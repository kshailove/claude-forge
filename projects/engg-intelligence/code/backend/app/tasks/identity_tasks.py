"""Identity resolution Celery tasks.

Spec reference: §5.9, M8a, M8b
Task queue: q_github (general purpose — no dedicated identity queue)
"""
from __future__ import annotations

import asyncio
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
# auto_resolve_identities task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.tasks.identity_tasks.auto_resolve_identities",
    queue="q_github",
    max_retries=2,
    acks_late=True,
)
def auto_resolve_identities(self) -> dict:
    """Run auto-resolution for all tools and re-resolve all FK back-references.

    Called:
      - At the END of each nightly ingest (via orchestrator post-nightly hook)
      - Manually via POST /api/v1/admin/identity-mappings/auto-resolve

    Returns a summary dict with per-tool resolved/unresolved counts.
    """
    return _run_async(_auto_resolve_identities_async())


async def _auto_resolve_identities_async() -> dict:
    """Async implementation of auto_resolve_identities."""
    from app.core.database import get_session_factory
    from app.services.identity_resolver import IdentityResolver, ALL_TOOLS

    resolver = IdentityResolver()
    session_factory = get_session_factory()
    summary: dict = {"tools": {}, "status": "completed"}

    for tool in ALL_TOOLS:
        try:
            async with session_factory() as session:
                result = await resolver.auto_resolve_all(tool, session)
                await session.commit()
                summary["tools"][tool] = {
                    "resolved": result.resolved_count,
                    "unresolved": result.unresolved_count,
                    "conflicts": len(result.conflicts),
                }
                struct_logger.info(
                    "identity_auto_resolved_tool",
                    tool=tool,
                    resolved=result.resolved_count,
                    unresolved=result.unresolved_count,
                )
        except Exception as exc:
            struct_logger.error(
                "identity_resolve_tool_failed",
                tool=tool,
                error=str(exc),
                exc_info=True,
            )
            summary["tools"][tool] = {"error": str(exc)}

    # Re-resolve FK back-references across all source tables
    try:
        async with session_factory() as session:
            resolver2 = IdentityResolver()
            await resolver2.resolve_github_users(session)
            await resolver2.resolve_jira_users(session)
            await resolver2.resolve_pagerduty_users(session)
            await resolver2.resolve_slack_users(session)
            await session.commit()
        struct_logger.info("identity_fk_resolution_complete")
    except Exception as exc:
        struct_logger.error(
            "identity_fk_resolution_failed",
            error=str(exc),
            exc_info=True,
        )
        summary["fk_resolution_error"] = str(exc)

    struct_logger.info("identity_auto_resolve_all_complete", summary=summary)
    return summary
