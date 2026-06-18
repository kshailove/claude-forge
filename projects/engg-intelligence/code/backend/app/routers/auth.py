"""Auth router — login, refresh, logout, me endpoints.

Spec §4.1 and §7.1.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rbac import AnyAuthenticatedUser, get_current_user
from app.core.redis import get_redis
from app.core.security import (
    clear_login_failures,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    is_account_locked,
    lockout_remaining_seconds,
    record_login_failure,
    refresh_token_expires_at,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    TokenUserInfo,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate with username + password, return access + refresh tokens."""
    redis = get_redis()

    # --- Account lockout check ---
    if await is_account_locked(redis, body.username):
        remaining = await lockout_remaining_seconds(redis, body.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "ACCOUNT_LOCKED",
                    "message": (
                        "Account temporarily locked due to repeated login failures. "
                        f"Try again in {remaining} seconds."
                    ),
                    "details": {},
                }
            },
            headers={"Retry-After": str(remaining)},
        )

    # --- Fetch user ---
    result = await db.execute(
        select(User).where(User.username == body.username, User.is_active == True)
    )
    user: User | None = result.scalar_one_or_none()

    # --- Verify credentials ---
    if user is None or not verify_password(body.password, user.password_hash):
        await record_login_failure(redis, body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "Username or password is incorrect.",
                    "details": {},
                }
            },
        )

    # --- Successful login: clear failure counter ---
    await clear_login_failures(redis, body.username)

    # --- Create tokens ---
    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        team_id=user.team_id,
    )
    refresh_token_plain = generate_refresh_token()
    token_hash = hash_refresh_token(refresh_token_plain)
    expires_at = refresh_token_expires_at()

    db_refresh_token = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.flush()

    from app.core.config import get_settings
    settings = get_settings()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_plain,
        expires_in=settings.access_token_expire_seconds,
        user=TokenUserInfo(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
            team_id=user.team_id,
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """Exchange a refresh token for a new access token."""
    token_hash = hash_refresh_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token: RefreshToken | None = result.scalar_one_or_none()

    now = datetime.now(tz=timezone.utc)

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_REFRESH_TOKEN",
                    "message": "Refresh token is invalid.",
                    "details": {},
                }
            },
        )

    if db_token.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_REFRESH_TOKEN",
                    "message": "Refresh token has been revoked.",
                    "details": {},
                }
            },
        )

    if db_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "EXPIRED_REFRESH_TOKEN",
                    "message": "Refresh token has expired. Please log in again.",
                    "details": {},
                }
            },
        )

    # Fetch the user
    result = await db.execute(
        select(User).where(User.id == db_token.user_id, User.is_active == True)
    )
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_REFRESH_TOKEN",
                    "message": "User account not found or deactivated.",
                    "details": {},
                }
            },
        )

    access_token = create_access_token(
        user_id=user.id,
        role=user.role,
        team_id=user.team_id,
    )

    from app.core.config import get_settings
    settings = get_settings()

    return RefreshResponse(
        access_token=access_token,
        expires_in=settings.access_token_expire_seconds,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def logout(
    body: RefreshRequest,
    current_user: AnyAuthenticatedUser,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke the current session's refresh token."""
    token_hash = hash_refresh_token(body.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == current_user.id,
        )
    )
    db_token: RefreshToken | None = result.scalar_one_or_none()
    if db_token is not None:
        db_token.revoked = True
        await db.flush()


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def me(
    current_user: AnyAuthenticatedUser,
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Return the currently authenticated user's profile."""
    result = await db.execute(select(User).where(User.id == current_user.id))
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return MeResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        team_id=user.team_id,
    )
