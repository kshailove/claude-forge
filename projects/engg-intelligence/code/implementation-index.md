# Implementation Index — M0 Foundation

**Milestone:** M0 Foundation
**Date:** 2026-06-12
**Status:** Complete

---

## File Count: 41 files

---

## Infrastructure (M0a)

| File | Purpose |
|------|---------|
| `.env.example` | All required env vars with placeholder values |
| `Dockerfile` | Multi-stage image for API and Celery services. Installs Node.js for MJML template compilation at build time. |
| `docker-compose.yml` | Path A (TimescaleDB) — all services: db, redis, api, celery-worker, celery-beat, prometheus, grafana |
| `docker-compose.vanilla.yml` | Path B (Managed PostgreSQL, USE_TIMESCALEDB=false) — same services without TimescaleDB |
| `monitoring/prometheus.yml` | Prometheus scrape config for FastAPI and Celery metrics |
| `monitoring/grafana/dashboards/` | Grafana dashboard directory (provisioned at M9) |

---

## Database / Migrations (M0b)

| File | Purpose |
|------|---------|
| `backend/alembic.ini` | Alembic config — file_template, timezone=UTC, sqlalchemy.url placeholder |
| `backend/migrations/env.py` | Alembic env — async engine, DATABASE_URL from env, loads all models for autogenerate |
| `backend/migrations/versions/001_core_schema.py` | **Single migration creating ALL tables** from Tech Spec §3, gated on USE_TIMESCALEDB |

### Tables created in migration 001:
- `teams`, `users`, `team_memberships`, `org_nodes` — core entities (§3.1)
- `refresh_tokens`, `password_reset_tokens` — auth support (§3.10)
- `integrations`, `identity_mappings` — integration config (§3.2)
- `pull_requests`, `pr_reviews`, `commits`, `github_releases` — GitHub data (§3.3)
- `sprints`, `tickets`, `ticket_state_transitions` — PM data (§3.4)
- `incidents`, `incident_assignments`, `oncall_schedules`, `oncall_shifts` — incident data (§3.5)
- `slack_activity_buckets` — TimescaleDB hypertable (Path A) or range-partitioned (Path B) (§3.6)
- `team_metric_snapshots`, `engineer_metric_snapshots` — metric snapshots with hypertables/partitions (§3.7)
- `team_health_config` — per-team weight config with CHECK constraint (§3.8)
- `digest_runs`, `digest_emails` — digest tracking (§3.9)
- `backfill_jobs` — backfill tracking (§3.11)
- `nightly_runs` — nightly pipeline tracking (§3.12)
- `update_updated_at_column()` trigger function + triggers on all updated_at columns
- TimescaleDB `daily_team_scores` continuous aggregate (Path A only)
- All indexes as specified in §3

---

## FastAPI Skeleton (M0c)

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app factory — CORS, rate limiting (slowapi), Prometheus instrumentation, structured logging, request middleware, health check endpoint |
| `backend/app/core/config.py` | `Settings` via pydantic-settings — all env vars, startup validators for JWT_SECRET and DB_ENCRYPTION_KEY |
| `backend/app/core/database.py` | SQLAlchemy 2.0 async engine, `async_sessionmaker`, `get_db()` FastAPI dependency, `ping_database()`, `close_engine()` |
| `backend/app/core/redis.py` | Redis async client via redis-py asyncio, `get_redis()`, `ping_redis()`, `cache_get/set/delete/delete_pattern()` helpers |
| `backend/app/core/security.py` | bcrypt hashing (work factor 12), JWT HS256 create/decode, refresh token generation/hashing, Redis-backed login lockout tracking |
| `backend/app/core/encryption.py` | AES-256-GCM encrypt/decrypt for `integrations.config_json` using `cryptography` library |
| `backend/app/core/rbac.py` | `CurrentUser` class, `get_current_user()` dependency, `require_roles()`, `require_team_access()`, `require_self_or_above()`, convenience type aliases |
| `backend/requirements.txt` | Pinned Python dependencies — FastAPI, SQLAlchemy 2.0, asyncpg, Celery 5.4, passlib[bcrypt], python-jose, cryptography, structlog, prometheus-fastapi-instrumentator, slowapi, pydantic v2 |

---

## ORM Models (M0c)

| File | Tables |
|------|--------|
| `backend/app/models/__init__.py` | Package init — imports all models so Alembic discovers them |
| `backend/app/models/user.py` | `User`, `RefreshToken`, `PasswordResetToken` |
| `backend/app/models/team.py` | `Team`, `TeamMembership`, `OrgNode`, `TeamHealthConfig` |
| `backend/app/models/integration.py` | `Integration` (with `get_config()`/`set_config()` encryption helpers), `IdentityMapping` |
| `backend/app/models/github.py` | `PullRequest`, `PRReview`, `Commit`, `GithubRelease` |
| `backend/app/models/tickets.py` | `Sprint`, `Ticket`, `TicketStateTransition` |
| `backend/app/models/incidents.py` | `Incident`, `IncidentAssignment`, `OncallSchedule`, `OncallShift` |
| `backend/app/models/slack.py` | `SlackActivityBucket` |
| `backend/app/models/metrics.py` | `TeamMetricSnapshot`, `EngineerMetricSnapshot` |
| `backend/app/models/digest.py` | `DigestRun`, `DigestEmail` |
| `backend/app/models/nightly.py` | `NightlyRun` (with `mark_integration_complete()`, `compute_status()` helpers) |

---

## Pydantic Schemas (M0c)

| File | Schemas |
|------|---------|
| `backend/app/schemas/__init__.py` | Package re-exports |
| `backend/app/schemas/auth.py` | `LoginRequest`, `LoginResponse`, `RefreshRequest`, `RefreshResponse`, `MeResponse`, `TokenUserInfo`, password reset schemas |
| `backend/app/schemas/user.py` | `UserBase`, `UserCreate`, `UserUpdate`, `UserResponse` |
| `backend/app/schemas/team.py` | `TeamBase`, `TeamCreate`, `TeamUpdate`, `TeamResponse` |
| `backend/app/schemas/admin.py` | `CreateUserRequest`, `UpdateUserRequest`, `UserListResponse`, `CreateTeamRequest`, `UpdateTeamRequest`, `TeamListResponse`, `OrgTreeNode`, `OrgTreeRequest`, `OrgTreeResponse`, `NightlyRunResponse`, `NightlyRunListResponse`, `TriggerNightlyRunResponse`, `TeamHealthConfigUpdate` (with weight-sum validator) |

---

## Auth Endpoints (M0d)

| File | Endpoints |
|------|-----------|
| `backend/app/routers/auth.py` | `POST /api/v1/auth/login` — bcrypt verify, JWT creation, refresh token storage, account lockout |
| | `POST /api/v1/auth/refresh` — validate refresh token, issue new access token |
| | `POST /api/v1/auth/logout` — revoke refresh token |
| | `GET /api/v1/auth/me` — return current user profile |

---

## Admin Endpoints (M0e)

| File | Endpoints |
|------|-----------|
| `backend/app/routers/admin.py` | `POST /api/v1/admin/users` — create user |
| | `GET /api/v1/admin/users` — list users |
| | `GET /api/v1/admin/users/{id}` — get user |
| | `PUT /api/v1/admin/users/{id}` — update user |
| | `DELETE /api/v1/admin/users/{id}` — soft-delete (blocks last-admin deletion) |
| | `POST /api/v1/admin/teams` — create team |
| | `GET /api/v1/admin/teams` — list teams |
| | `GET /api/v1/admin/teams/{id}` — get team |
| | `PUT /api/v1/admin/teams/{id}` — update team |
| | `POST /api/v1/admin/org-tree` — bulk upsert manual org tree |
| | `GET /api/v1/admin/org-tree` — get current org tree |
| | `GET /api/v1/admin/nightly-runs` — list last 30 runs |
| | `POST /api/v1/admin/nightly-runs/trigger` — manually trigger run (409 if active) |

---

## Nightly Run Orchestrator (M0f)

| File | Purpose |
|------|---------|
| `backend/app/celery_app.py` | Celery app with all queue routing, Beat schedule (01:00 UTC nightly, 06:00 Monday digest, 04:00 data retention), queue definitions |
| `backend/celeryconfig.py` | Per-queue concurrency settings, worker pool config |
| `backend/app/tasks/__init__.py` | Tasks package init |
| `backend/app/tasks/orchestrator.py` | `run_nightly_batch` — Celery Beat task, creates nightly_runs record, dispatches chord of staggered integration tasks; `run_metric_computation` — chord callback, updates run status, invalidates caches; `invalidate_caches` — Redis pattern deletion; `trigger_digest_snapshot`, `trigger_digest_send`, `purge_old_data` stubs |

---

## Key Design Decisions Implemented

1. **TimescaleDB gating** — `USE_TIMESCALEDB` env var gates all hypertable DDL in `001_core_schema.py`. Path B uses declarative range partitioning with 14 monthly partitions.
2. **AES-256-GCM encryption** — `Integration.set_config()`/`get_config()` methods transparently encrypt/decrypt `config_json`. Key never touches the DB.
3. **bcrypt work factor 12** — enforced in `passlib.CryptContext` in `security.py`.
4. **JWT HS256, 24h access / 30d refresh** — implemented in `security.py`; refresh tokens stored in PostgreSQL `refresh_tokens` table (not Redis) per spec decision Q5.
5. **RBAC via FastAPI Depends()** — role derived exclusively from JWT claim; `require_roles()`, `require_team_access()`, `require_self_or_above()` in `rbac.py`.
6. **Account lockout** — Redis counter `login_failures:{username}` with 900s TTL; 5 failures → 429 with `Retry-After` header.
7. **Nightly orchestrator** — Celery chord pattern: group of staggered integration tasks → metric computation callback → cache invalidation.
8. **updated_at triggers** — PostgreSQL trigger function `update_updated_at_column()` applied to all tables with `updated_at` column.
9. **Pydantic v2** — `model_validator`, `field_validator` used throughout; `from_attributes=True` for ORM-to-schema conversion.
10. **No hardcoded secrets** — all secrets via `Settings` from environment variables.
