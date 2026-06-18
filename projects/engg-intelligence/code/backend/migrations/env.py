"""Alembic environment configuration — sync psycopg2 engine.

Alembic migrations run synchronously via psycopg2 (the standard approach).
The application itself uses asyncpg at runtime, but Alembic only needs sync access.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Ensure the backend root is on sys.path so `from app.models import Base` resolves.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base  # noqa: F401 — registers all ORM models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    # Convert asyncpg URL to psycopg2 URL for sync Alembic use
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        url = config.get_main_option("sqlalchemy.url", "")
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url


def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = get_database_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            # Each migration runs and commits in its own transaction.
            # Required so that 002_timescaledb_aggregates can see tables
            # committed by 001_core_schema via a separate connection.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
