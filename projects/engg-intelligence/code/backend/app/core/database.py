"""SQLAlchemy 2.0 async engine and session factory.

Usage in FastAPI endpoints via dependency injection:
    async def my_endpoint(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(User))

Usage in Celery tasks (sync context):
    async with async_session_factory() as session:
        ...
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Module-level engine & session factory (initialised lazily)
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return (or lazily create) the global async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=not settings.is_production,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (or lazily create) the global async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _async_session_factory


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    The session is automatically committed on success and rolled back on error.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Health check helper
# ---------------------------------------------------------------------------

async def ping_database() -> bool:
    """Return True if the database is reachable, False otherwise."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Synchronous session factory for Celery tasks (non-async context)
# ---------------------------------------------------------------------------

_sync_engine = None
_sync_session_factory: sessionmaker[Session] | None = None


def get_sync_engine():
    """Return (or lazily create) a synchronous SQLAlchemy engine.

    The DATABASE_URL uses the asyncpg driver; swap to psycopg2 for sync.
    """
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        # Convert asyncpg URL to psycopg2-compatible URL for sync engine
        sync_url = settings.database_url.replace(
            "postgresql+asyncpg://", "postgresql+psycopg2://"
        ).replace(
            "postgresql+asyncpg:", "postgresql:"
        )
        _sync_engine = create_engine(
            sync_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _sync_engine


@contextmanager
def SyncSessionLocal() -> Generator[Session, None, None]:
    """Context manager that yields a synchronous SQLAlchemy session.

    Usage in Celery tasks:
        with SyncSessionLocal() as session:
            session.execute(text("DELETE FROM ..."))
            session.commit()
    """
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(
            bind=get_sync_engine(),
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    session: Session = _sync_session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Cleanup (called on application shutdown)
# ---------------------------------------------------------------------------

async def close_engine() -> None:
    """Dispose of the connection pool cleanly on app shutdown."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
