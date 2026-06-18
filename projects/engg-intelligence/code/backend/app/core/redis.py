"""Redis async client factory and helpers.

Provides:
  - A lazily initialised global Redis client (connection pool, asyncio-native).
  - ``get_redis()`` FastAPI dependency / direct accessor.
  - ``ping_redis()`` for health checks.
  - ``close_redis()`` for graceful shutdown.

All callers use ``await redis.get(key)`` / ``await redis.setex(key, ttl, value)`` etc.
No Redis secrets are hardcoded — the URL comes from Settings.
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Module-level client (initialised lazily on first call)
# ---------------------------------------------------------------------------
_redis_client: Redis | None = None


def get_redis() -> Redis:
    """Return (or lazily create) the global async Redis client.

    The connection pool is shared across all coroutines in the process.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def ping_redis() -> bool:
    """Return True if Redis is reachable, False otherwise."""
    try:
        client = get_redis()
        return await client.ping()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

async def cache_get(key: str) -> Any | None:
    """Return a JSON-decoded value from Redis, or None on miss."""
    client = get_redis()
    raw = await client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    """JSON-encode and store a value in Redis with a TTL."""
    client = get_redis()
    await client.setex(key, ttl_seconds, json.dumps(value, default=str))


async def cache_delete(key: str) -> None:
    """Delete a single key from Redis."""
    client = get_redis()
    await client.delete(key)


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a glob pattern. Returns number of keys deleted."""
    client = get_redis()
    keys = await client.keys(pattern)
    if not keys:
        return 0
    return await client.delete(*keys)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def close_redis() -> None:
    """Close the Redis connection pool on application shutdown."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
