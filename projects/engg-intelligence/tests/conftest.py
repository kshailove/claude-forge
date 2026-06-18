"""Shared pytest fixtures for the engg-intelligence test suite.

Provides:
  - async_db_session: AsyncSession backed by SQLite in-memory
  - test_client: FastAPI AsyncClient with overridden DB + Redis dependencies
  - admin_token, director_token, em_token, engineer_token: pre-minted JWTs
  - sample_team, sample_users: pre-seeded DB records
  - mock_redis: fakeredis.aioredis instance
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Environment must be set before any app imports so Settings.model_validate
# succeeds without a .env file.
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-chars-long!!")
os.environ.setdefault("DB_ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("USE_TIMESCALEDB", "false")

# Add the backend app directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code", "backend"))
# Add the tests directory to sys.path so sub-packages can do `from conftest import ...`
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must import Base after sys.path is set
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.models.team import Team, TeamMembership
from app.models.user import User

# ---------------------------------------------------------------------------
# Patch get_settings lru_cache so test env vars take effect
# ---------------------------------------------------------------------------
from app.core.config import get_settings as _real_get_settings
_real_get_settings.cache_clear()


# ---------------------------------------------------------------------------
# SQLite in-memory async engine + session factory
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use the default asyncio event loop policy."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create an in-memory SQLite engine per test function."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession backed by the in-memory SQLite engine."""
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Return a fakeredis async instance."""
    try:
        import fakeredis.aioredis as fakeredis_async
        fake = fakeredis_async.FakeRedis()
        return fake
    except ImportError:
        # Fallback: AsyncMock with common Redis interface
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock(return_value=True)
        redis.setex = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.ttl = AsyncMock(return_value=-2)
        redis.ping = AsyncMock(return_value=True)
        return redis


# ---------------------------------------------------------------------------
# JWT token fixtures
# ---------------------------------------------------------------------------

ADMIN_USER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DIRECTOR_USER_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000002")
EM_USER_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000003")
ENGINEER_USER_ID = uuid.UUID("ffffffff-0000-0000-0000-000000000004")
SAMPLE_TEAM_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000005")
SAMPLE_TEAM2_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000006")


@pytest.fixture
def admin_token() -> str:
    return create_access_token(
        user_id=ADMIN_USER_ID,
        role="admin",
        team_id=None,
    )


@pytest.fixture
def director_token() -> str:
    return create_access_token(
        user_id=DIRECTOR_USER_ID,
        role="director",
        team_id=None,
    )


@pytest.fixture
def em_token() -> str:
    return create_access_token(
        user_id=EM_USER_ID,
        role="em",
        team_id=SAMPLE_TEAM_ID,
    )


@pytest.fixture
def engineer_token() -> str:
    return create_access_token(
        user_id=ENGINEER_USER_ID,
        role="engineer",
        team_id=SAMPLE_TEAM_ID,
    )


# ---------------------------------------------------------------------------
# Seeded DB records
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sample_team(async_db_session: AsyncSession) -> Team:
    """Insert one Team row and return it."""
    team = Team(
        id=SAMPLE_TEAM_ID,
        name="Alpha Squad",
        slug="alpha-squad",
        em_user_id=EM_USER_ID,
    )
    async_db_session.add(team)
    await async_db_session.flush()
    return team


@pytest_asyncio.fixture
async def sample_users(async_db_session: AsyncSession, sample_team: Team):
    """Insert admin, director, EM, and engineer users and return them as a dict."""
    pw_hash = hash_password("TestPass123!")

    admin = User(
        id=ADMIN_USER_ID,
        email="admin@example.com",
        username="admin_user",
        password_hash=pw_hash,
        role="admin",
        team_id=None,
        is_active=True,
    )
    director = User(
        id=DIRECTOR_USER_ID,
        email="director@example.com",
        username="director_user",
        password_hash=pw_hash,
        role="director",
        team_id=None,
        is_active=True,
    )
    em = User(
        id=EM_USER_ID,
        email="em@example.com",
        username="em_user",
        password_hash=pw_hash,
        role="em",
        team_id=SAMPLE_TEAM_ID,
        is_active=True,
    )
    engineer = User(
        id=ENGINEER_USER_ID,
        email="engineer@example.com",
        username="engineer_user",
        password_hash=pw_hash,
        role="engineer",
        team_id=SAMPLE_TEAM_ID,
        is_active=True,
    )

    for user in [admin, director, em, engineer]:
        async_db_session.add(user)
    await async_db_session.flush()

    # Add engineer to team membership
    membership = TeamMembership(
        id=uuid.uuid4(),
        user_id=ENGINEER_USER_ID,
        team_id=SAMPLE_TEAM_ID,
    )
    async_db_session.add(membership)
    await async_db_session.flush()

    return {"admin": admin, "director": director, "em": em, "engineer": engineer}


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_client(async_db_session: AsyncSession, mock_redis):
    """Return an httpx.AsyncClient wired to the FastAPI app with DB and Redis mocked."""
    from httpx import AsyncClient, ASGITransport

    app = create_app()

    # Override DB dependency
    async def override_get_db():
        yield async_db_session

    app.dependency_overrides[get_db] = override_get_db

    # Patch Redis globally — patch both the core module and any router-level imports
    with patch("app.core.redis.get_redis", return_value=mock_redis), \
         patch("app.routers.auth.get_redis", return_value=mock_redis), \
         patch("app.routers.teams.get_redis", return_value=mock_redis), \
         patch("app.routers.overview.get_redis", return_value=mock_redis), \
         patch("app.core.redis.ping_redis", return_value=True), \
         patch("app.core.database.ping_database", return_value=True):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client


# ---------------------------------------------------------------------------
# GitHub mock client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_github_client():
    """Return a mock GitHubClient with common methods stubbed."""
    mock = AsyncMock()
    mock.validate_pat = AsyncMock(return_value={"login": "testuser", "id": 12345})
    mock.get_org_repos = AsyncMock(return_value=iter([]))
    mock.get_recent_prs = AsyncMock(return_value=iter([]))
    mock.get_pr_reviews = AsyncMock(return_value=[])
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=None)
    return mock
