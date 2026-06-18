"""TimescaleDB continuous aggregates — must run after 001_core_schema commits.

Revision ID: 002_timescaledb_aggregates
Revises: 001_core_schema
Create Date: 2026-06-15 00:00:01

Continuous aggregates require running outside a transaction block, so they
are split into this separate migration which Alembic commits independently.
"""
from __future__ import annotations

import os

from alembic import op

revision: str = "002_timescaledb_aggregates"
down_revision: str | None = "001_core_schema"
branch_labels: str | None = None
depends_on: str | None = None

USE_TIMESCALEDB: bool = os.environ.get("USE_TIMESCALEDB", "true").lower() == "true"


def upgrade() -> None:
    if not USE_TIMESCALEDB:
        return

    # Continuous aggregates cannot run inside a transaction block.
    # Use a separate psycopg2 autocommit connection.
    import psycopg2

    url = (
        os.environ.get("DATABASE_URL", "")
        .replace("postgresql+asyncpg://", "postgresql://")
    )

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS daily_team_scores
            WITH (timescaledb.continuous) AS
            SELECT team_id,
                   component,
                   time_bucket('1 day', snapshot_at) AS day,
                   last(score, snapshot_at)           AS score,
                   last(rag, snapshot_at)             AS rag
            FROM team_metric_snapshots
            GROUP BY team_id, component, time_bucket('1 day', snapshot_at)
        """)
        cur.close()
    finally:
        conn.close()


def downgrade() -> None:
    if not USE_TIMESCALEDB:
        return

    import psycopg2

    url = (
        os.environ.get("DATABASE_URL", "")
        .replace("postgresql+asyncpg://", "postgresql://")
    )

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS daily_team_scores")
        cur.close()
    finally:
        conn.close()
