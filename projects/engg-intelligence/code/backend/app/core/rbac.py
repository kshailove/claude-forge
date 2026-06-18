"""RBAC FastAPI dependencies.

All role enforcement in the API layer goes through these Depends() functions.
Role is ALWAYS derived from the JWT claim — never from query params or request body.

Roles (from lowest to highest privilege):
  engineer  → own profile only
  em        → own team's data only
  director  → all teams, all engineers (read)
  admin     → everything, including configuration endpoints

Spec reference: §5.1, §7.1
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError

from app.core.security import decode_access_token

# ---------------------------------------------------------------------------
# Current-user resolution (called by every authenticated endpoint)
# ---------------------------------------------------------------------------

class CurrentUser:
    """Minimal user context extracted from the JWT claim."""

    __slots__ = ("id", "role", "team_id")

    def __init__(self, user_id: str, role: str, team_id: str | None) -> None:
        self.id: UUID = UUID(user_id)
        self.role: str = role
        self.team_id: UUID | None = UUID(team_id) if team_id else None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_director_or_above(self) -> bool:
        return self.role in ("admin", "director")

    @property
    def is_em_or_above(self) -> bool:
        return self.role in ("admin", "director", "em")


async def get_current_user(request: Request) -> CurrentUser:
    """FastAPI dependency: extract and validate JWT from Authorization header.

    Sets ``request.state.user`` as a side-effect for downstream middleware.
    Raises HTTP 401 for missing/invalid/expired tokens.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "INVALID_TOKEN",
                "message": "Authentication credentials are missing or invalid.",
                "details": {},
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise credentials_exception

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise credentials_exception

    try:
        payload = decode_access_token(token)
        user_id: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if user_id is None or role is None:
            raise credentials_exception
        current_user = CurrentUser(
            user_id=user_id,
            role=role,
            team_id=payload.get("team_id"),
        )
    except JWTError as exc:
        # Distinguish expired token for clearer error messaging
        exc_str = str(exc).lower()
        if "expired" in exc_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "TOKEN_EXPIRED",
                        "message": "Access token has expired. Please refresh.",
                        "details": {},
                    }
                },
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise credentials_exception from exc

    request.state.user = current_user
    return current_user


# ---------------------------------------------------------------------------
# Role-based access dependencies
# ---------------------------------------------------------------------------

def require_roles(*roles: str):
    """Return a FastAPI dependency that enforces one of the given roles.

    Usage:
        @router.get("/admin/users")
        async def list_users(user=Depends(require_roles("admin"))):
            ...
    """
    async def checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_PERMISSIONS",
                        "message": (
                            f"This endpoint requires one of: {', '.join(roles)}. "
                            f"Your role is: {current_user.role}."
                        ),
                        "details": {},
                    }
                },
            )
        return current_user

    return checker


def require_team_access(team_id_param: str = "team_id"):
    """Return a dependency that validates an EM can only access their own team.

    For directors and admins the check is skipped.
    Returns 404 (not 403) when a lower-privilege user requests a different team
    to avoid leaking team existence (per spec §4 API Contracts).
    """
    async def checker(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.is_director_or_above:
            return current_user

        # Extract team_id from path params
        path_team_id_str: str | None = request.path_params.get(team_id_param)
        if path_team_id_str is None:
            return current_user

        try:
            path_team_id = UUID(path_team_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if current_user.team_id != path_team_id:
            # Return 404 to avoid leaking team existence
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return current_user

    return checker


def require_self_or_above(user_id_param: str = "user_id"):
    """Return a dependency that allows access only to own profile or higher roles.

    Engineers can only see their own data.
    EMs/Directors/Admins can see any user's data (subject to team scope for EMs).
    Returns 403 when an engineer tries to access another engineer's data.
    """
    async def checker(
        request: Request,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current_user.is_em_or_above:
            return current_user

        # Engineer role: can only access own profile
        path_user_id_str: str | None = request.path_params.get(user_id_param)
        if path_user_id_str is None:
            return current_user

        try:
            path_user_id = UUID(path_user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if current_user.id != path_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_PERMISSIONS",
                        "message": "Engineers can only access their own profile.",
                        "details": {},
                    }
                },
            )
        return current_user

    return checker


# ---------------------------------------------------------------------------
# Convenience type aliases for use in endpoint signatures
# ---------------------------------------------------------------------------

AdminUser = Annotated[CurrentUser, Depends(require_roles("admin"))]
DirectorOrAdminUser = Annotated[CurrentUser, Depends(require_roles("admin", "director"))]
EMOrAboveUser = Annotated[CurrentUser, Depends(require_roles("admin", "director", "em"))]
AnyAuthenticatedUser = Annotated[CurrentUser, Depends(get_current_user)]
