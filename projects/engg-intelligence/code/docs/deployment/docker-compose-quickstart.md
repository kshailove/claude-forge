# Docker Compose Quickstart

Get the full engg-intelligence stack running locally in under 10 minutes.

---

## Prerequisites

| Tool | Minimum version | Install |
|------|----------------|---------|
| Docker | 24.x | https://docs.docker.com/get-docker/ |
| Docker Compose | v2.x (`docker compose`) | Bundled with Docker Desktop |

> Docker Desktop on macOS/Windows already bundles Compose v2. On Linux, install the
> `docker-compose-plugin` package.

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/your-org/engg-intelligence.git
cd engg-intelligence
```

---

## Step 2 — Configure environment variables

Copy the example env file and fill in required values:

```bash
cp .env.example .env
```

Open `.env` in your editor and set **at minimum**:

```env
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=<64-char hex string>
DB_ENCRYPTION_KEY=<64-char hex string>
```

All other variables have sensible defaults for local development. Leave
`SENDGRID_API_KEY` and `SMTP_*` empty for now — the digest email feature will
simply log a warning instead of sending.

> **Never commit `.env` to version control.** The `.gitignore` already excludes it.

---

## Step 3 — Start all services

```bash
docker compose up -d
```

This starts: PostgreSQL (TimescaleDB), Redis, the FastAPI API server,
a Celery worker, Celery Beat scheduler, Prometheus, and Grafana.

Wait for services to become healthy:

```bash
docker compose ps
```

All services should show `(healthy)` or `Up`. The API is ready when:

```bash
curl -s http://localhost:8000/health | python -m json.tool
# {"status": "ok", "db": "ok", "redis": "ok"}
```

---

## Step 4 — Run database migrations

Apply all Alembic migrations to create the schema:

```bash
docker compose exec api alembic upgrade head
```

Expected output ends with something like:
```
INFO  [alembic.runtime.migration] Running upgrade -> abc123, initial schema
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, add timescaledb hypertables
```

---

## Step 5 — Create the first admin user

```bash
docker compose exec api python -m app.cli create-admin
```

You will be prompted for:
- **Admin email** — your work email, e.g. `you@yourcompany.com`
- **Password** — minimum 8 characters (prompted twice for confirmation)

---

## Step 6 — Open the application

| Service | URL | Default credentials |
|---------|-----|---------------------|
| Frontend / API | http://localhost:8000 | Admin user you just created |
| API docs (Swagger) | http://localhost:8000/docs | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3001 | admin / admin |

Log in at http://localhost:8000 with the admin account created in Step 5.

---

## Email prerequisites (SendGrid)

Digest emails require a SendGrid API key. Without one, the system runs normally
but digest delivery is skipped with a warning in logs.

To enable email:
1. Sign up at https://sendgrid.com (free tier supports 100 emails/day)
2. Create an API key with **Mail Send** permission
3. Set `SENDGRID_API_KEY=SG.your-key` in `.env`
4. Restart: `docker compose restart api celery-worker`

---

## SMTP fallback

If you prefer SMTP over SendGrid, leave `SENDGRID_API_KEY` empty and set:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_ADDRESS=you@gmail.com
```

For Gmail, use an **App Password** (not your account password).
Generate one at: https://myaccount.google.com/apppasswords

---

## Useful commands

```bash
# View API logs
docker compose logs -f api

# Open a Python shell inside the API container
docker compose exec api python

# Run the test suite
docker compose exec api pytest tests/

# Stop all services (preserves data volumes)
docker compose down

# Stop and delete all data
docker compose down -v
```

---

## Path B — Vanilla PostgreSQL (no TimescaleDB)

If you want to run against a managed PostgreSQL instance (RDS, Cloud SQL, etc.),
use the vanilla compose file and set `USE_TIMESCALEDB=false`:

```bash
cp docker-compose.vanilla.yml docker-compose.override.yml
# Edit .env: USE_TIMESCALEDB=false, DATABASE_URL=postgresql+asyncpg://...
docker compose up -d
```

See `docs/deployment/timescaledb-to-vanilla-migration.md` for a migration guide.
