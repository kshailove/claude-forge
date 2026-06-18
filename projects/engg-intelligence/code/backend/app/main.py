"""FastAPI application factory.

Wires together:
  - CORS middleware
  - JWT auth middleware (validates Bearer token on all /api/v1/* routes)
  - Rate limiting (slowapi)
  - Prometheus instrumentation
  - Structured request/response logging (structlog)
  - All routers

Spec §5.1, M0c.
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.database import close_engine, ping_database
from app.core.redis import close_redis, get_redis, ping_redis

# ---------------------------------------------------------------------------
# Structlog configuration
# ---------------------------------------------------------------------------

settings = get_settings()

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (slowapi — Redis-backed)
# ---------------------------------------------------------------------------

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
)

# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown hooks."""
    # --- Startup ---
    logger.info("app_startup", env=settings.env, log_level=settings.log_level)

    # Validate JWT_SECRET length at startup (per spec §7.1)
    if len(settings.jwt_secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters. Server will not start.")

    # Pre-warm connections
    db_ok = await ping_database()
    redis_ok = await ping_redis()
    logger.info("startup_health", db=db_ok, redis=redis_ok)
    if not db_ok:
        logger.warning("db_unreachable_at_startup")
    if not redis_ok:
        logger.warning("redis_unreachable_at_startup")

    yield

    # --- Shutdown ---
    logger.info("app_shutdown")
    await close_engine()
    await close_redis()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Application factory — returns the configured FastAPI instance."""
    _settings = get_settings()

    _app = FastAPI(
        title="engg-intelligence API",
        description="Engineering intelligence platform — aggregates GitHub, Jira, PagerDuty, Slack into team health scores.",
        version="0.1.0",
        docs_url="/docs" if not _settings.is_production else None,
        redoc_url="/redoc" if not _settings.is_production else None,
        lifespan=lifespan,
    )

    # --- Rate limiter ---
    _app.state.limiter = limiter
    _app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    _app.add_middleware(SlowAPIMiddleware)

    # --- CORS ---
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=[_settings.app_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Request logging middleware ---
    @_app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        start_time = time.monotonic()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "http_request",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    # --- Prometheus instrumentation ---
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(_app).expose(_app, endpoint="/metrics", include_in_schema=False)

    # --- Exception handlers ---
    @_app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "details": exc.errors(),
                }
            },
        )

    @_app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred.",
                    "details": {},
                }
            },
        )

    # --- Health check (no auth required) ---
    @_app.get("/health", include_in_schema=False)
    async def health_check() -> dict:
        db_ok = await ping_database()
        redis_ok = await ping_redis()
        return {
            "status": "ok" if (db_ok and redis_ok) else "degraded",
            "db": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
        }

    # --- Register routers ---
    from app.routers.auth import router as auth_router
    from app.routers.admin import router as admin_router
    from app.routers.integrations import router as integrations_router
    from app.routers.overview import router as overview_router
    from app.routers.teams import router as teams_router
    from app.routers.engineers import router as engineers_router
    from app.routers.incidents import router as incidents_router
    from app.routers.digests import router as digests_router

    _app.include_router(auth_router, prefix="/api/v1")
    _app.include_router(admin_router, prefix="/api/v1")
    _app.include_router(integrations_router, prefix="/api/v1")
    _app.include_router(overview_router, prefix="/api/v1")
    _app.include_router(teams_router, prefix="/api/v1")
    _app.include_router(engineers_router, prefix="/api/v1")
    _app.include_router(incidents_router, prefix="/api/v1")
    _app.include_router(digests_router, prefix="/api/v1")

    return _app


# ---------------------------------------------------------------------------
# Application instance (used by uvicorn and gunicorn)
# ---------------------------------------------------------------------------

app = create_app()
