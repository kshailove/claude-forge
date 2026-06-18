"""User schemas (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: str = Field(..., max_length=255)
    username: str = Field(..., max_length=100)
    role: str
    team_id: uuid.UUID | None = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=100)
    role: str | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
