"""Auth endpoint request/response schemas (Pydantic v2)."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login request body."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)


class TokenUserInfo(BaseModel):
    """Minimal user info embedded in login/me responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    role: str
    team_id: uuid.UUID | None


class LoginResponse(BaseModel):
    """POST /api/v1/auth/login response body."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    user: TokenUserInfo


class RefreshRequest(BaseModel):
    """POST /api/v1/auth/refresh request body."""

    refresh_token: str = Field(..., min_length=1)


class RefreshResponse(BaseModel):
    """POST /api/v1/auth/refresh response body."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds


class MeResponse(BaseModel):
    """GET /api/v1/auth/me response body."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    role: str
    team_id: uuid.UUID | None


class PasswordResetRequestBody(BaseModel):
    """POST /api/v1/auth/password-reset/request body."""

    email: str = Field(..., min_length=1, max_length=255)


class PasswordResetConfirmBody(BaseModel):
    """POST /api/v1/auth/password-reset/confirm body."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)
