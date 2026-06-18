"""JWT + bcrypt security utilities.

- Password hashing with bcrypt (work factor 12 as per spec §7.1)
- JWT HS256 access token creation and verification
- Refresh token generation and hashing (SHA-256)
- Login failure tracking in Redis (account lockout)

IMPORTANT: No secrets are hardcoded — all come from Settings.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Password hashing (bcrypt, work factor 12)
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain* password. Work factor 12."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT — access tokens
# ---------------------------------------------------------------------------

ALGORITHM = "HS256"


def create_access_token(
    user_id: UUID | str,
    role: str,
    team_id: UUID | str | None = None,
) -> str:
    """Create a signed HS256 access token.

    Claims (per spec §2.8):
        sub   — user UUID (string)
        role  — role string ('admin'|'director'|'em'|'engineer')
        team_id — UUID string or null
        jti   — random UUID for per-token revocation
        iat   — issued-at epoch
        exp   — expiry epoch (now + 24h)
    """
    settings = get_settings()
    now = int(time.time())
    payload: dict = {
        "sub": str(user_id),
        "role": role,
        "team_id": str(team_id) if team_id else None,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + settings.access_token_expire_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify an access token. Raises JWTError on failure."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------

def generate_refresh_token() -> str:
    """Generate a cryptographically secure refresh token (URL-safe, 48 bytes)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Return SHA-256 hex digest of the refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expires_at() -> datetime:
    """Return the expiry datetime (30 days from now) for a new refresh token."""
    settings = get_settings()
    return datetime.now(tz=timezone.utc).replace(microsecond=0).__class__.fromtimestamp(
        time.time() + settings.refresh_token_expire_seconds, tz=timezone.utc
    )


# ---------------------------------------------------------------------------
# Login rate limiting helpers (Redis-backed)
# ---------------------------------------------------------------------------

_LOCKOUT_KEY_PREFIX = "login_failures:"


def login_failure_key(username: str) -> str:
    return f"{_LOCKOUT_KEY_PREFIX}{username}"


async def record_login_failure(redis: "Redis", username: str) -> int:  # type: ignore[name-defined]
    """Increment failed-login counter. Returns current failure count."""
    settings = get_settings()
    key = login_failure_key(username)
    count = await redis.incr(key)
    if count == 1:
        # Set TTL only on first failure so counter resets after lockout window
        await redis.expire(key, settings.login_lockout_seconds)
    return count


async def get_login_failures(redis: "Redis", username: str) -> int:  # type: ignore[name-defined]
    """Return current failure count for *username*."""
    val = await redis.get(login_failure_key(username))
    return int(val) if val else 0


async def clear_login_failures(redis: "Redis", username: str) -> None:  # type: ignore[name-defined]
    """Clear the failure counter after a successful login."""
    await redis.delete(login_failure_key(username))


async def is_account_locked(redis: "Redis", username: str) -> bool:  # type: ignore[name-defined]
    """Return True if the account has exceeded the failure threshold."""
    settings = get_settings()
    count = await get_login_failures(redis, username)
    return count >= settings.login_max_failures


async def lockout_remaining_seconds(redis: "Redis", username: str) -> int:  # type: ignore[name-defined]
    """Return remaining lockout seconds (0 if not locked)."""
    ttl = await redis.ttl(login_failure_key(username))
    return max(0, ttl)
