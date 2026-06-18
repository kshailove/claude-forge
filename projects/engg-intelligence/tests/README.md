# engg-intelligence Test Suite

Comprehensive pytest-based tests covering unit, integration, and acceptance layers.

## Structure

```
tests/
  conftest.py             — shared fixtures (DB, Redis, tokens, seeded data)
  README.md               — this file

  unit/                   — pure logic tests (no network, no real DB)
    test_security.py      — JWT + bcrypt
    test_encryption.py    — AES-256-GCM encrypt/decrypt
    test_pr_health.py     — PR Health metric engine
    test_sprint_health.py — Sprint Health metric engine
    test_incident_load.py — Incident Load metric + Gini coefficient
    test_composite_score.py — Composite scoring + RAG + weight redistribution
    test_dora.py          — DORA metrics model and band classification
    test_slack_signal.py  — Slack signal degraded logic
    test_identity_resolver.py — IdentityResolver service

  integration/            — API endpoint tests (in-memory SQLite + fakeredis)
    test_auth_api.py      — /auth/login, /auth/refresh, /auth/logout, /auth/me
    test_admin_api.py     — /admin/users, /admin/teams (admin-only)
    test_overview_api.py  — /overview (RBAC scoping)
    test_teams_api.py     — /teams (RBAC, stale PRs, slack degraded)
    test_engineers_api.py — /engineers (privacy 404, EM scoping)
    test_incidents_api.py — /incidents (pagination, summary, timeline)
    test_digests_api.py   — /digests (scoping, privacy)

  acceptance/             — End-to-end AC validation
    test_ac_health_scoring.py    — Custom weights, slack degraded, RAG boundaries
    test_ac_rbac.py              — Role enforcement across all endpoints
    test_ac_nightly_pipeline.py  — Orchestrator creates run, overlap rejected
    test_ac_digest_scoping.py    — Digest privacy per role
    test_ac_identity_resolution.py — Email match, manual lock, unresolved list
```

## Running Tests

### Prerequisites

```bash
# From the project root
cd projects/engg-intelligence/code/backend
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx fakeredis aiosqlite pytest-httpx
```

### Run all tests

```bash
cd projects/engg-intelligence
pytest tests/ -v
```

### Run by layer

```bash
# Unit only (fast, no I/O)
pytest tests/unit/ -v

# Integration only
pytest tests/integration/ -v

# Acceptance only
pytest tests/acceptance/ -v
```

### Run a single file

```bash
pytest tests/unit/test_composite_score.py -v
```

### Run with coverage

```bash
pytest tests/ --cov=app --cov-report=term-missing -v
```

## Environment Variables

The test suite sets these automatically via `conftest.py`:

| Variable | Test Value |
|---|---|
| `JWT_SECRET` | `test-secret-that-is-at-least-32-chars-long!!` |
| `DB_ENCRYPTION_KEY` | `aaaa...` (64 hex chars) |
| `DATABASE_URL` | `sqlite+aiosqlite:///:memory:` |
| `REDIS_URL` | `redis://localhost:6379/0` (mocked via fakeredis) |
| `ENV` | `development` |
| `USE_TIMESCALEDB` | `false` |

No real network calls are made. Redis is mocked via `fakeredis.aioredis`.

## Fixture Reference

| Fixture | Scope | Purpose |
|---|---|---|
| `async_db_session` | function | In-memory SQLite AsyncSession |
| `test_client` | function | httpx.AsyncClient with overridden deps |
| `mock_redis` | function | fakeredis instance |
| `admin_token` | function | Valid JWT for admin role |
| `director_token` | function | Valid JWT for director role |
| `em_token` | function | Valid JWT for em role (team=alpha-squad) |
| `engineer_token` | function | Valid JWT for engineer role |
| `sample_team` | function | Pre-seeded Team row |
| `sample_users` | function | Dict of pre-seeded users per role |

## Test Count Summary

- **Unit tests**: ~70
- **Integration tests**: ~45
- **Acceptance tests**: ~35
- **Total**: ~150
