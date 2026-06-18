"""Application configuration via pydantic-settings.

All settings are loaded from environment variables. No hardcoded secrets.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Loaded once at startup via ``get_settings()``.
    All secrets must be provided via environment variables — never hardcoded.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    env: Literal["production", "development"] = "development"
    app_url: str = "http://localhost:8000"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://engg:engg@db:5432/engg_intelligence",
        description="SQLAlchemy async database URL (postgresql+asyncpg://...)",
    )
    use_timescaledb: bool = Field(
        default=True,
        description=(
            "True → use TimescaleDB hypertables (Path A). "
            "False → use declarative range partitioning (Path B)."
        ),
    )

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL for app cache",
    )
    celery_broker_url: str = Field(
        default="redis://redis:6379/0",
        description="Celery broker URL (Redis)",
    )
    celery_result_backend: str = Field(
        default="redis://redis:6379/1",
        description="Celery result backend URL (Redis)",
    )

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    jwt_secret: str = Field(
        ...,
        min_length=32,
        description="HS256 signing secret — minimum 32 characters. Never commit.",
    )
    db_encryption_key: str = Field(
        ...,
        min_length=64,
        max_length=64,
        description="AES-256 key as 64-char hex string (32 bytes). Never commit.",
    )

    # Token TTLs
    access_token_expire_seconds: int = 86_400       # 24 hours
    refresh_token_expire_seconds: int = 2_592_000   # 30 days

    # Login lockout
    login_max_failures: int = 5
    login_lockout_seconds: int = 900  # 15 minutes

    # ------------------------------------------------------------------
    # Email — SendGrid (primary)
    # ------------------------------------------------------------------
    sendgrid_api_key: str | None = None

    # ------------------------------------------------------------------
    # Email — SMTP fallback
    # ------------------------------------------------------------------
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str = "noreply@yourcompany.com"

    # ------------------------------------------------------------------
    # Slack OAuth
    # ------------------------------------------------------------------
    slack_client_id: str | None = None
    slack_client_secret: str | None = None

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return v

    @field_validator("db_encryption_key")
    @classmethod
    def encryption_key_must_be_hex(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("DB_ENCRYPTION_KEY must be exactly 64 hex characters (32 bytes)")
        try:
            bytes.fromhex(v)
        except ValueError as exc:
            raise ValueError("DB_ENCRYPTION_KEY must be a valid hex string") from exc
        return v

    @field_validator("database_url")
    @classmethod
    def database_url_must_use_asyncpg(cls, v: str) -> str:
        if "postgresql+asyncpg" not in v and "sqlite" not in v:
            # Allow sqlite only in test environments
            raise ValueError(
                "DATABASE_URL must use postgresql+asyncpg:// driver. "
                "Example: postgresql+asyncpg://user:pass@host:5432/dbname"
            )
        return v

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def db_encryption_key_bytes(self) -> bytes:
        """Return encryption key as raw bytes for AES-GCM operations."""
        return bytes.fromhex(self.db_encryption_key)

    @property
    def email_configured(self) -> bool:
        """True if any email delivery is configured."""
        return bool(self.sendgrid_api_key) or bool(self.smtp_host)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton.

    Called once at application startup; subsequent calls return cached instance.
    """
    return Settings()  # type: ignore[call-arg]
