"""Data retention purge task.

Scheduled daily at 03:00 UTC (see celery_app.py beat_schedule).
Deletes rows older than policy thresholds from all time-series and raw tables.

Spec §8 M9 — Hardening + Observability
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from celery import Task
from sqlalchemy import text

from app.celery_app import celery_app
from app.core.database import SyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class _PurgeStatement:
    """Holds a DELETE statement and a human-readable table name for logging."""

    table: str
    sql: str


# ---------------------------------------------------------------------------
# Retention policy statements
# Each row is executed independently; a failure on one does not block others.
# ---------------------------------------------------------------------------

_PURGE_STATEMENTS: list[_PurgeStatement] = [
    _PurgeStatement(
        table="team_metric_snapshots",
        sql="DELETE FROM team_metric_snapshots WHERE snapshot_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="engineer_metric_snapshots",
        sql="DELETE FROM engineer_metric_snapshots WHERE snapshot_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="slack_activity_buckets",
        sql="DELETE FROM slack_activity_buckets WHERE bucket_hour < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="pull_requests",
        sql="DELETE FROM pull_requests WHERE created_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="commits",
        sql="DELETE FROM commits WHERE committed_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="incidents",
        sql="DELETE FROM incidents WHERE triggered_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="tickets",
        sql="DELETE FROM tickets WHERE created_at < now() - INTERVAL '12 months'",
    ),
    _PurgeStatement(
        table="refresh_tokens",
        sql="DELETE FROM refresh_tokens WHERE expires_at < now()",
    ),
    _PurgeStatement(
        table="nightly_runs",
        sql="DELETE FROM nightly_runs WHERE started_at < now() - INTERVAL '6 months'",
    ),
]


@celery_app.task(
    name="app.tasks.maintenance.purge_old_data",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 minutes
    queue="q_github",  # lightweight — share the github queue
)
def purge_old_data(self: Task) -> dict[str, int]:
    """Delete rows that have exceeded their retention window.

    Returns a dict mapping table name → deleted row count.

    Runs each DELETE in its own transaction so a failure on one table
    (e.g. the table does not exist yet) does not roll back all prior deletions.
    """
    logger.info("Starting data retention purge")
    results: dict[str, int] = {}
    errors: list[str] = []

    for stmt in _PURGE_STATEMENTS:
        try:
            with SyncSessionLocal() as session:
                result = session.execute(text(stmt.sql))
                deleted = result.rowcount
                session.commit()
            results[stmt.table] = deleted
            logger.info(
                "Purge: deleted %d rows from %s",
                deleted,
                stmt.table,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Purge failed for table %s: %s",
                stmt.table,
                exc,
                exc_info=True,
            )
            errors.append(f"{stmt.table}: {exc}")
            results[stmt.table] = -1  # sentinel for failed table

    total_deleted = sum(v for v in results.values() if v >= 0)
    logger.info(
        "Data retention purge complete. Total deleted: %d rows. Errors: %d.",
        total_deleted,
        len(errors),
    )

    if errors:
        # Raise so Celery marks the task as FAILURE and retries it
        raise RuntimeError(
            f"Purge completed with {len(errors)} error(s): {'; '.join(errors)}"
        )

    return results
