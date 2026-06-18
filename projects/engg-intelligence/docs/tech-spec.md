# Technical Specification — engg-intelligence

**Version:** 1.1
**Status:** Draft
**Date:** 2026-06-12
**Stage:** Tech Spec (Stage 4)
**Authors:** ClaudeForge Spec Agent

---

## Changelog

| Version | Date | Summary |
|---------|------|---------|
| 1.1 | 2026-06-12 | Switched from webhook/hourly to nightly batch architecture; GitHub App → Personal Access Token (PAT); removed webhook receiver; added Nightly Run Orchestrator component; added `nightly_runs` table; extended API cache TTL to 2 hours; staggered nightly schedule (01:00–02:45 UTC); removed all webhook endpoints |
| 1.0 | 2026-06-11 | Initial draft |

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack Decisions](#2-tech-stack-decisions)
3. [Data Models](#3-data-models)
4. [API Contracts](#4-api-contracts)
5. [Component Breakdown](#5-component-breakdown)
6. [Integration Details](#6-integration-details)
7. [Non-Functional Implementation](#7-non-functional-implementation)
8. [Implementation Order](#8-implementation-order)
9. [Open Technical Questions](#9-open-technical-questions)

---

## 1. Architecture Overview

### System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SYSTEMS                                   │
│                                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────────────┐│
│  │  GitHub  │  │  Jira /  │  │PagerDuty/│  │  Slack   │  │  Keka HRMS      ││
│  │  (PAT)   │  │ ClickUp  │  │ Zenduty  │  │  (Bot)   │  │  (OAuth)        ││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬─────────┘│
└───────┼─────────────┼─────────────┼──────────────┼────────────────┼───────────┘
        │ REST batch  │ REST batch  │ REST batch   │ REST batch     │ REST batch
        │ (nightly    │ (nightly    │ (nightly     │ (nightly       │ (nightly
        │  01:00 UTC) │  01:20 UTC) │  01:40 UTC)  │  02:00 UTC)    │  02:15 UTC)
        │             │             │              │                │
        │             │             │              │                │
        │   ┌─────────────────────────────────────────────────┐    │
        │   │         Celery Beat — Nightly Run Orchestrator  │    │
        │   │         Fires 01:00 UTC daily                   │    │
        │   │         Creates nightly_runs record             │    │
        │   │         Dispatches Celery group of all          │    │
        │   │         integration tasks (staggered start)     │    │
        │   │         Chord callback → Metric Computation     │    │
        │   └─────────────────────────────────────────────────┘    │
        │             │             │              │                │
        ▼             ▼             ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         REDIS 7  (Broker only)                                  │
│                                                                                 │
│  Queue: q_github    q_jira_clickup    q_incidents    q_slack    q_keka          │
│         q_digest                                                                │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────────┐
        ▼                          ▼                              ▼
┌──────────────┐         ┌──────────────────┐          ┌──────────────────────┐
│Celery Workers│         │  Celery Workers  │          │   Celery Workers     │
│  q_github    │         │  q_jira_clickup  │          │   q_incidents        │
│              │         │                  │          │   q_slack            │
│ - Nightly PR │         │ - Sprint ingest  │          │   q_keka             │
│   batch pull │         │ - Ticket ingest  │          │   q_digest           │
│   (PAT auth) │         │ - Story points   │          │                      │
│ - Release    │         │ - Cycle time     │          │ - Incident ingest    │
│   ingest     │         │                  │          │ - On-call sync       │
│ - PR Health  │         │ - Sprint Health  │          │ - MTTR/MTTA calc     │
│   metrics    │         │   metrics        │          │ - Slack buckets      │
└──────┬───────┘         └────────┬─────────┘          │ - Keka org sync      │
       │                          │                     │ - Digest generation  │
       └──────────────────────────┼─────────────────────┘
                                  │ write
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│              PostgreSQL 16 + TimescaleDB Extension                              │
│                                                                                 │
│  Regular tables:                    TimescaleDB Hypertables:                   │
│  ┌─────────────────────┐           ┌──────────────────────────────┐            │
│  │ users               │           │ team_metric_snapshots        │            │
│  │ teams               │           │ engineer_metric_snapshots     │            │
│  │ integrations        │           │ slack_activity_buckets        │            │
│  │ pull_requests       │           └──────────────────────────────┘            │
│  │ pr_reviews          │                                                        │
│  │ tickets             │           Continuous Aggregates:                      │
│  │ sprints             │           ┌──────────────────────────────┐            │
│  │ incidents           │           │ daily_team_scores            │            │
│  │ oncall_shifts       │           │ weekly_engineer_metrics      │            │
│  │ slack_activity_...  │           └──────────────────────────────┘            │
│  │ identity_mappings   │                                                        │
│  │ digest_emails       │                                                        │
│  │ team_health_config  │                                                        │
│  │ nightly_runs        │                                                        │
│  └─────────────────────┘                                                        │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │ read (SQLAlchemy 2.0 async)
                                   │ + Redis cache (2h TTL)
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          FastAPI REST API                                       │
│                                                                                 │
│  /api/v1/auth/*          JWT middleware (HS256)                                │
│  /api/v1/overview        RBAC via FastAPI Depends()                            │
│  /api/v1/teams/*         Role: admin > director > em > engineer                │
│  /api/v1/engineers/*     Rate limiting: slowapi + Redis                        │
│  /api/v1/incidents/*     Prometheus instrumentation                            │
│  /api/v1/digests/*       Structured JSON logging (structlog)                   │
│  /api/v1/admin/*                                                               │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │ HTTPS / JSON
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│              React 18 Frontend (Vite + TypeScript + React Router v7)            │
│                                                                                 │
│  Tab: Overview  │  Teams  │  Engineers  │  Incidents  │  Digests               │
│                                                                                 │
│  State: TanStack Query (server state) + Zustand (UI state)                     │
│  Charting: Recharts                                                             │
│  Styling: Tailwind CSS + shadcn/ui components                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                      SUPPORTING SERVICES                                        │
│                                                                                 │
│  Celery Beat (scheduler)          SendGrid (email delivery)                    │
│  - 01:00 UTC nightly batch        - MJML + Jinja2 digest emails                │
│    trigger (all integrations)     - Fallback: SMTP (self-hosters)              │
│  - Sunday 22:00 digest prep                                                    │
│  - Monday 02:45 digest trigger    Prometheus + Grafana                         │
│    (after nightly metrics)        - Queue depth per integration                │
│                                   - Ingestion latency p95                      │
│                                   - API request latency                        │
│                                   - Failed tasks per nightly run               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Nightly Batch → Ingestion → Storage → Metric Computation → Cache Invalidation → API → Frontend

1. NIGHTLY BATCH PATH (all integrations):
   01:00 UTC: Celery Beat fires nightly_run_orchestrator task
   → Creates nightly_runs record (status=running)
   → Dispatches Celery group of parallel integration tasks:

   01:00 UTC — GitHub batch pull (q_github):
       PAT auth; fetch PRs/reviews/commits/releases updated in last 24h
       using ?since=<yesterday_ISO8601> on GitHub REST API
       upsert pull_requests, pr_reviews, commits, github_releases tables
       update integrations.last_synced_at

   01:20 UTC — Jira/ClickUp batch pull (q_jira_clickup):
       fetch sprints and issues updated since yesterday_start_UTC
       upsert tickets, sprints, ticket_state_transitions

   01:40 UTC — PagerDuty/Zenduty batch pull (q_incidents):
       fetch incidents with since=yesterday_start_UTC&until=today_start_UTC
       upsert incidents, incident_assignments, oncall_shifts (nightly sync)

   02:00 UTC — Slack metadata batch pull (q_slack):
       poll conversations.history for non-degraded workspaces
       aggregate into slack_activity_buckets

   02:15 UTC — Keka org tree sync (q_keka):
       paginated fetch of all employees
       replace org_nodes table

   → All tasks complete → Celery chord callback triggers:

   02:30 UTC — Metric Computation Engine (chained chord):
       recompute all component scores for all teams
       write to team_metric_snapshots and engineer_metric_snapshots

   02:45 UTC — Cache invalidation:
       invalidate all team_score:{team_id} and overview:{user_id} keys
       → API ready for morning use (data fresh by 03:00 UTC)
       → Monday only: also trigger digest generation after metrics complete

   → nightly_runs record updated: status=completed (or partial/failed)

2. DIGEST PATH (weekly):
   Monday 02:45 UTC (chord callback, after nightly metrics complete):
   → Snapshot captured: reads current metric state, writes to digest_runs record
   Monday 06:00 UTC: Celery Beat enqueues digest_send tasks per recipient
   → Digest Generator reads digest_runs snapshot
   → Renders MJML + Jinja2 template per role scope
   → HTML stored in digest_emails.html_content
   → SendGrid API call; delivery status tracked via SendGrid webhook callback
   → digest_emails.delivery_status updated

3. READ PATH (API):
   Authenticated request → JWT middleware validates token
   → RBAC check (role from JWT claim vs. endpoint policy)
   → Redis cache check (key: overview:{user_id}, team_score:{team_id}, etc.)
   → Cache hit: return immediately (TTL 2 hours; data is fresh from nightly run)
   → Cache miss: query PostgreSQL (TimescaleDB hypertable or regular table)
   → Populate cache → return response
```

---

## 2. Tech Stack Decisions

### 2.1 Database: PostgreSQL 16 + TimescaleDB

**Choice:** PostgreSQL 16 with TimescaleDB 2.x extension.

**Alternatives considered:**
- Vanilla PostgreSQL 16 with declarative range partitioning
- ClickHouse (OLAP columnar store)
- InfluxDB (purpose-built time-series)

**Rationale:**
The platform has two classes of data: relational (users, teams, integrations, PRs, tickets) and time-series (nightly metric snapshots, Slack activity buckets, sparklines). TimescaleDB extends PostgreSQL with hypertables and continuous aggregates while preserving full SQL compatibility, SQLAlchemy support, and Alembic migration tooling. ClickHouse and InfluxDB would require maintaining a second data store with separate operational complexity.

**Two deployment paths (both must be supported):**

Path A — Self-hosted (recommended): Use `timescale/timescaledb:latest-pg16` Docker image. TimescaleDB available. Hypertables created via raw SQL migrations.

Path B — Managed PostgreSQL (RDS, Cloud SQL, Azure Database for PostgreSQL): TimescaleDB extension not available. Substitute: declarative range partitioning on `snapshot_at` column for `team_metric_snapshots` and `engineer_metric_snapshots`. Partition per month. Sparkline queries use standard `WHERE snapshot_at BETWEEN x AND y` with a composite index on `(team_id, snapshot_at)`. Continuous aggregates are replaced with scheduled materialized views refreshed nightly by the nightly Celery chord callback. Document the tradeoff: p95 query latency for 12-month sparkline may be 2-5x higher than TimescaleDB path on large orgs (>300 engineers).

Migration guide between paths: provided in `docs/deployment/timescaledb-to-vanilla-migration.md` (created at M9).

### 2.2 GitHub Auth: Personal Access Token (PAT)

**Choice:** Personal Access Token (PAT) (not GitHub App).

**Alternatives considered:**
- GitHub App
- GitHub OAuth App

**Rationale:**
Since there are no webhooks and all GitHub data is fetched via a single nightly batch pull, a PAT is sufficient and dramatically simpler to set up. PAT auth requires only pasting a token in the Admin UI versus installing a GitHub App (which requires org admin rights, creating an App, uploading a private key PEM, and configuring webhook endpoints). PAT rate limit is 5,000 req/hr — more than enough for one nightly batch even for large orgs (50–200 repos, last 24h of activity typically requires 200–500 requests). GitHub App would add unnecessary complexity for a read-only batch access pattern.

**Required scopes:** `repo` (read-only access to repos, PRs, reviews, commits, releases). For organisations using GitHub Enterprise or fine-grained tokens, the equivalent read-only permissions apply.

**Install flow:**
Admin navigates to Admin UI → Integrations → GitHub → Connect. Admin pastes: `personal_access_token`, `org_name`, `release_tag_pattern` (regex string). System stores encrypted in `integrations.config_json`. All API calls use: `Authorization: token {personal_access_token}`.

**Token expiry:** Fine-grained PATs expire (maximum 1 year). Store token with `expires_at` field in `integrations.config_json`; surface a warning banner in Admin UI 30 days before expiry. See Q11 in Section 9.

### 2.3 DORA Deployment Frequency Proxy

**Choice:** GitHub Releases API as the deployment frequency proxy. UI label: "Release Frequency" (not "Deployment Frequency").

**Alternatives considered:**
- Push events to default branch (overcounts: every commit push = deployment)
- GitHub Deployments API (requires CI/CD pipeline integration, out of scope v1)
- Git tags (less structured than releases; harder to filter)

**Rationale:**
GitHub Releases are explicit, intentional events created by engineers for production releases. They map more closely to actual deployments than branch pushes. The admin can configure a tag pattern regex (e.g. `v[0-9]+\.[0-9]+\.[0-9]+`) to filter which releases count. The UI labels this metric "Release Frequency" with a tooltip explaining the proxy. DORA benchmark bands for Deployment Frequency are shown alongside with a note: "Calculated from GitHub Releases. Configure tag pattern in Admin settings."

**Admin configuration:** `integrations.config_json` for GitHub includes `release_tag_pattern` (default: `.*`). Admin sets this in the GitHub integration settings page during setup.

### 2.4 Slack Degradation Policy

**Choice:** Degrade after-hours/weekend computation for workspaces with >50 channels OR >200 members. Show explicit UI warning. Exclude Slack Signal from composite health score when degraded (weight redistributed proportionally).

**Alternatives considered:**
- Partial estimation with confidence caveat
- Fixed neutral score of 50 when unavailable
- Use Slack Enterprise Grid API (different endpoint, not applicable to standard workspaces)

**Rationale:**
At 1 req/min for `conversations.history` (2025 rate limit), a workspace with 50 channels requires 50 minutes per poll cycle — leaving only 10 minutes of buffer per hour. Above 50 channels or 200 members, the risk of exceeding rate limits and producing incomplete/misleading data outweighs the value of a partial signal. Assigning a neutral score of 50 would corrupt the composite score silently; exclusion with proportional redistribution is transparent.

**Degradation check sequence:** On OAuth install → fetch `team.info` (member count) + `conversations.list` (channel count, public only) → if either threshold exceeded: set `integrations.config_json.slack_signal_degraded = true` → UI shows banner on Slack Signal sub-tab: "Slack signal unavailable — workspace too large for standard API tier (>50 channels or >200 members)." → Slack Signal excluded from composite; remaining three weights scaled: `new_weight = original_weight / (1 - 0.15)`.

**Weight redistribution formula when Slack degraded:**
- PR Health: 0.30 / 0.85 = 35.3%
- Sprint Health: 0.30 / 0.85 = 35.3%
- Incident Load: 0.25 / 0.85 = 29.4%

When any other component is also unavailable, apply the same proportional redistribution recursively.

### 2.5 Health Score Weights

**Choice:** Default weights: PR Health 30%, Sprint Health 30%, Incident Load 25%, Slack Signal 15%. Configurable per team by Admin role only in v1 (not EM). Stored in `team_health_config` table.

**Alternatives considered:**
- Hard-coded defaults (no configurability in v1)
- EM self-service weight configuration within Admin-set bounds

**Rationale:**
The schema must support per-team weight overrides from day one to avoid a migration later (per plan.md Decision 5). Restricting configuration to Admin only in v1 reduces complexity — EMs viewing the health score formula in the "Health Score Details" panel builds trust without requiring EM-editable weights. EM weight configuration is deferred to v2 as F18.

**Constraint enforcement:** Sum of four weights must equal exactly 1.0 (100%). Enforced in API validation layer (Pydantic model with `@model_validator`). Database constraint: `CHECK (weight_pr_health + weight_sprint_health + weight_incident_load + weight_slack_signal = 1.0)`. Tolerance: within 0.001 due to floating point.

### 2.6 Background Jobs: Celery 5.4 + Redis 7

**Choice:** Celery 5.4 with Redis 7 as broker. Per-integration dedicated queues. All integration tasks triggered nightly by Celery Beat (no real-time fan-out).

**Alternatives considered:**
- ARQ (async Redis Queue, lighter weight)
- Dramatiq
- RQ (Redis Queue)

**Rationale:**
Celery 5.4 provides battle-tested scheduling (Celery Beat), per-queue worker isolation, built-in retry policies with exponential backoff, and Celery chord support for the nightly pipeline (fan-out → callback pattern). The per-integration queue design (`q_github`, `q_jira_clickup`, `q_incidents`, `q_slack`, `q_keka`, `q_digest`) ensures a slow or rate-limited integration never blocks others. All integration queues are triggered once per night by the Nightly Run Orchestrator — not in real-time. Celery Beat runs as a dedicated process separate from workers to isolate scheduling reliability from worker load. Redis serves as broker only; no real-time event fan-out is required.

**Queue configuration:**
```
q_github:       concurrency=4, prefetch=1, acks_late=True
q_jira_clickup: concurrency=2, prefetch=1, acks_late=True
q_incidents:    concurrency=2, prefetch=1, acks_late=True
q_slack:        concurrency=1, prefetch=1, acks_late=True (rate-limit-sensitive)
q_keka:         concurrency=1, prefetch=1, acks_late=True
q_digest:       concurrency=4, prefetch=1, acks_late=True
```

`acks_late=True` on all queues: task is acknowledged only after successful completion, ensuring in-flight tasks are re-queued on worker crash.

### 2.7 Email: SendGrid with MJML + Jinja2

**Choice:** SendGrid HTTP API (v3) for email delivery. MJML compiled to HTML at template build time. Jinja2 for runtime variable substitution.

**Alternatives considered:**
- Mailgun
- AWS SES
- Postmark

**Rationale:**
SendGrid provides delivery webhooks (event tracking for open/bounce/delivery confirmation), transactional email reliability, and a generous free tier (100 emails/day). MJML produces responsive HTML emails that render correctly across Gmail, Outlook, and Apple Mail — hand-coding responsive email HTML is impractical.

**Fallback for self-hosters:** If `SENDGRID_API_KEY` env var is not set, the system falls back to SMTP using env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_ADDRESS`. In SMTP mode, delivery status tracking (bounce/open webhooks) is unavailable; `digest_emails.delivery_status` is set to `sent` after successful SMTP handshake without confirmation.

**Template compilation:** MJML templates are compiled to HTML at Docker image build time (not at runtime). Compiled HTML is stored in `engg_intelligence/templates/compiled/`. Jinja2 renders the compiled HTML at digest generation time with context variables.

### 2.8 Auth: JWT HS256

**Choice:** JWT with HS256. 24-hour access tokens. 30-day refresh tokens stored in `refresh_tokens` PostgreSQL table.

**Alternatives considered:**
- RS256 asymmetric JWT
- Session cookies with Redis session store
- Access token only (no refresh)

**Rationale:**
HS256 is sufficient for a single-service deployment where the signing secret never leaves the backend. RS256 would add key management complexity without benefit in a self-hosted single-tenant deployment. Refresh tokens stored in PostgreSQL (not Redis) survive Redis flushes and restarts. 30-day refresh token TTL matches typical "remember me" UX expectations without requiring daily re-login.

**Token claims structure:**
```json
{
  "sub": "user_uuid",
  "role": "em",
  "team_id": "team_uuid_or_null",
  "jti": "random_uuid",
  "iat": 1234567890,
  "exp": 1234567890
}
```

Role is embedded in the JWT claim and never read from query parameters or request body. `jti` (JWT ID) enables per-token revocation if needed without invalidating all user tokens.

### 2.9 Frontend Routing: React Router v7

**Choice:** React Router v7 (SPA mode, client-side routing).

**Alternatives considered:**
- Next.js (SSR/SSG)
- TanStack Router

**Rationale:**
The platform is a data-dense internal tool with no SEO requirements. SPA mode avoids server-side rendering complexity. React Router v7 provides the file-based routing API with type-safe route params. Vite provides fast HMR in development. TanStack Router is newer and less mature for large apps. Next.js adds deployment complexity (Node.js server for SSR) that is not warranted for an internal tool.

---

## 3. Data Models

All tables use UUID primary keys (PostgreSQL `uuid` type, default `gen_random_uuid()`). All timestamps are `TIMESTAMPTZ` (UTC). Soft-delete pattern: `is_active` boolean on `users`; all other entities use archive flags where noted.

---

### 3.1 Core Entities

#### `users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK, default gen_random_uuid() | Canonical user identifier |
| email | varchar(255) | NOT NULL, UNIQUE | Primary identity key for cross-tool resolution |
| username | varchar(100) | NOT NULL, UNIQUE | Login username |
| password_hash | varchar(255) | NOT NULL | bcrypt hash, work factor 12 |
| role | varchar(20) | NOT NULL, CHECK IN ('admin','director','em','engineer') | Role assignment |
| team_id | uuid | FK teams(id) ON DELETE SET NULL, NULLABLE | Primary team assignment (NULL for admin/director) |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | Updated via trigger |
| is_active | boolean | NOT NULL, default true | Soft-delete flag |

Indexes:
- `idx_users_email` UNIQUE on (email)
- `idx_users_username` UNIQUE on (username)
- `idx_users_team_id` on (team_id)
- `idx_users_role` on (role)

---

#### `teams`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| name | varchar(255) | NOT NULL | Display name |
| slug | varchar(100) | NOT NULL, UNIQUE | URL-safe identifier (e.g. "platform-team") |
| em_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Assigned Engineering Manager |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_teams_slug` UNIQUE on (slug)
- `idx_teams_em_user_id` on (em_user_id)

---

#### `team_memberships`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_team_memberships_user_team` UNIQUE on (user_id, team_id)
- `idx_team_memberships_team_id` on (team_id)

---

#### `org_nodes`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| employee_user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | The employee |
| manager_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Their manager (NULL for top of org) |
| source | varchar(20) | NOT NULL, CHECK IN ('manual','keka') | How this mapping was created |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_org_nodes_employee` UNIQUE on (employee_user_id)
- `idx_org_nodes_manager` on (manager_user_id)
- `idx_org_nodes_source` on (source)

Notes: When Keka sync runs, all rows with `source='keka'` are deleted and re-inserted. Rows with `source='manual'` are also deleted and replaced during a Keka sync (Keka is authoritative). On Keka disconnect, admin chooses to restore manual config or keep last Keka snapshot.

---

### 3.2 Integration Config

#### `integrations`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| team_id | uuid | FK teams(id) ON DELETE CASCADE, NULLABLE | NULL for org-wide integrations (GitHub, Slack, Keka) |
| type | varchar(30) | NOT NULL, CHECK IN ('github','jira','clickup','pagerduty','zenduty','slack','keka') | Integration type |
| config_json | text | NOT NULL | AES-256 encrypted JSON blob. Contains API tokens, URLs, config params. |
| status | varchar(20) | NOT NULL, default 'disconnected', CHECK IN ('connected','error','disconnected') | |
| last_synced_at | timestamptz | NULLABLE | Last successful sync timestamp |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_integrations_team_type` on (team_id, type)
- `idx_integrations_type_status` on (type, status)

Notes: `config_json` is encrypted at application layer using AES-256-GCM before storage. Key from env var `DB_ENCRYPTION_KEY`. The encrypted blob stores a JSON object; schema is integration-type-specific (documented per integration in Section 6).

---

#### `identity_mappings`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| canonical_user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | Platform user |
| tool | varchar(20) | NOT NULL, CHECK IN ('github','jira','clickup','slack','pagerduty','zenduty','keka') | Source tool |
| tool_user_id | varchar(255) | NOT NULL | Tool-native user ID (GitHub login, Jira account ID, Slack user ID, etc.) |
| tool_email | varchar(255) | NULLABLE | Email from tool (used for auto-resolution) |
| resolution_method | varchar(10) | NOT NULL, CHECK IN ('auto','manual') | How this mapping was established |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_identity_tool_user` UNIQUE on (tool, tool_user_id)
- `idx_identity_canonical_user` on (canonical_user_id)
- `idx_identity_tool_email` on (tool, tool_email)

---

### 3.3 GitHub Data

#### `pull_requests`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| github_id | bigint | NOT NULL, UNIQUE | GitHub's numeric PR ID |
| repo_full_name | varchar(255) | NOT NULL | e.g. "org/repo" |
| pr_number | integer | NOT NULL | PR number within repo |
| title | varchar(500) | NOT NULL | PR title |
| author_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Resolved canonical user (NULL if unresolved) |
| state | varchar(10) | NOT NULL, CHECK IN ('open','merged','closed') | |
| created_at | timestamptz | NOT NULL | When PR was opened on GitHub |
| merged_at | timestamptz | NULLABLE | Merge timestamp |
| closed_at | timestamptz | NULLABLE | Close timestamp (if closed without merge) |
| first_review_at | timestamptz | NULLABLE | Timestamp of first review event |
| cycle_time_seconds | integer | NULLABLE | (merged_at - created_at) in seconds; NULL if not merged |
| pr_size_additions | integer | NOT NULL, default 0 | Lines added |
| pr_size_deletions | integer | NOT NULL, default 0 | Lines removed |
| base_branch | varchar(255) | NOT NULL | Target branch |
| head_branch | varchar(255) | NOT NULL | Source branch |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | Team that owns this repo |
| updated_at | timestamptz | NOT NULL | GitHub's updated_at timestamp |
| last_activity_at | timestamptz | NOT NULL | Latest of: updated_at, last comment, last review — for stale PR detection |

Indexes:
- `idx_prs_github_id` UNIQUE on (github_id)
- `idx_prs_repo_number` UNIQUE on (repo_full_name, pr_number)
- `idx_prs_team_state` on (team_id, state)
- `idx_prs_team_created` on (team_id, created_at DESC)
- `idx_prs_author` on (author_user_id)
- `idx_prs_last_activity` on (last_activity_at) WHERE state = 'open'

---

#### `pr_reviews`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| github_id | bigint | NOT NULL, UNIQUE | GitHub review ID |
| pr_id | uuid | NOT NULL, FK pull_requests(id) ON DELETE CASCADE | |
| reviewer_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Resolved canonical user |
| submitted_at | timestamptz | NOT NULL | |
| state | varchar(25) | NOT NULL, CHECK IN ('approved','changes_requested','commented') | |
| comment_count | integer | NOT NULL, default 0 | |

Indexes:
- `idx_pr_reviews_github_id` UNIQUE on (github_id)
- `idx_pr_reviews_pr_id` on (pr_id)
- `idx_pr_reviews_reviewer` on (reviewer_user_id)
- `idx_pr_reviews_submitted_at` on (submitted_at DESC)

---

#### `commits`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| sha | varchar(40) | NOT NULL, UNIQUE | Git commit SHA |
| repo_full_name | varchar(255) | NOT NULL | |
| author_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | |
| committed_at | timestamptz | NOT NULL | Commit author timestamp |
| pr_id | uuid | FK pull_requests(id) ON DELETE SET NULL, NULLABLE | Associated PR (NULL for direct pushes) |

Indexes:
- `idx_commits_sha` UNIQUE on (sha)
- `idx_commits_author` on (author_user_id, committed_at DESC)
- `idx_commits_pr_id` on (pr_id)

---

#### `github_releases`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| release_id | bigint | NOT NULL, UNIQUE | GitHub release ID |
| repo_full_name | varchar(255) | NOT NULL | |
| tag_name | varchar(255) | NOT NULL | Git tag |
| published_at | timestamptz | NOT NULL | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |

Indexes:
- `idx_releases_release_id` UNIQUE on (release_id)
- `idx_releases_team_published` on (team_id, published_at DESC)

---

### 3.4 PM Data (Jira / ClickUp)

#### `sprints`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| integration_id | uuid | NOT NULL, FK integrations(id) ON DELETE CASCADE | |
| external_id | varchar(255) | NOT NULL | Jira sprint ID or ClickUp list ID |
| name | varchar(500) | NOT NULL | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| start_date | date | NULLABLE | |
| end_date | date | NULLABLE | |
| state | varchar(20) | NOT NULL, CHECK IN ('active','completed','future') | |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_sprints_integration_external` UNIQUE on (integration_id, external_id)
- `idx_sprints_team_state` on (team_id, state)
- `idx_sprints_team_end_date` on (team_id, end_date DESC)

---

#### `tickets`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| integration_id | uuid | NOT NULL, FK integrations(id) ON DELETE CASCADE | |
| external_id | varchar(255) | NOT NULL | Jira issue key or ClickUp task ID |
| title | varchar(500) | NOT NULL | |
| assignee_user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | |
| sprint_id | uuid | FK sprints(id) ON DELETE SET NULL, NULLABLE | Current sprint |
| status | varchar(100) | NOT NULL | Raw status string from tool (e.g. "In Progress") |
| story_points | decimal(6,2) | NULLABLE | |
| ticket_type | varchar(20) | NULLABLE, CHECK IN ('feature','bug','tech_debt','risk') | Admin-mapped from tool labels |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| created_at | timestamptz | NOT NULL | When ticket was created in tool |
| started_at | timestamptz | NULLABLE | First transition to in-progress state |
| completed_at | timestamptz | NULLABLE | Transition to done state |
| updated_at | timestamptz | NOT NULL | Tool's updated_at |

Indexes:
- `idx_tickets_integration_external` UNIQUE on (integration_id, external_id)
- `idx_tickets_team_sprint` on (team_id, sprint_id)
- `idx_tickets_assignee` on (assignee_user_id)
- `idx_tickets_team_completed` on (team_id, completed_at DESC)

---

#### `ticket_state_transitions`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| ticket_id | uuid | NOT NULL, FK tickets(id) ON DELETE CASCADE | |
| from_state | varchar(100) | NULLABLE | NULL for initial creation |
| to_state | varchar(100) | NOT NULL | |
| transitioned_at | timestamptz | NOT NULL | |

Indexes:
- `idx_transitions_ticket_id` on (ticket_id, transitioned_at)

---

### 3.5 Incident Data

#### `incidents`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| integration_id | uuid | NOT NULL, FK integrations(id) ON DELETE CASCADE | |
| external_id | varchar(255) | NOT NULL, UNIQUE | PagerDuty/Zenduty incident ID |
| title | varchar(500) | NOT NULL | Incident title |
| severity | varchar(5) | NOT NULL, CHECK IN ('p1','p2','p3','p4') | Normalized severity |
| service_name | varchar(255) | NULLABLE | Originating service |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | Owning team |
| triggered_at | timestamptz | NOT NULL | |
| acknowledged_at | timestamptz | NULLABLE | First ack |
| resolved_at | timestamptz | NULLABLE | Resolution time |
| mtta_seconds | integer | NULLABLE | (acknowledged_at - triggered_at) |
| mttr_seconds | integer | NULLABLE | (resolved_at - triggered_at) |
| created_at | timestamptz | NOT NULL, default now() | |
| updated_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_incidents_external_id` UNIQUE on (external_id)
- `idx_incidents_team_triggered` on (team_id, triggered_at DESC)
- `idx_incidents_severity` on (severity)
- `idx_incidents_service` on (service_name)

---

#### `incident_assignments`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| incident_id | uuid | NOT NULL, FK incidents(id) ON DELETE CASCADE | |
| user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Resolved canonical user |
| assigned_at | timestamptz | NOT NULL | |
| resolved_at | timestamptz | NULLABLE | When they resolved or were unassigned |

Indexes:
- `idx_incident_assignments_incident` on (incident_id)
- `idx_incident_assignments_user` on (user_id)

---

#### `oncall_schedules`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| integration_id | uuid | NOT NULL, FK integrations(id) ON DELETE CASCADE | |
| schedule_name | varchar(255) | NOT NULL | |
| external_id | varchar(255) | NOT NULL | Tool-native schedule ID |

Indexes:
- `idx_oncall_schedules_integration_external` UNIQUE on (integration_id, external_id)

---

#### `oncall_shifts`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| schedule_id | uuid | NOT NULL, FK oncall_schedules(id) ON DELETE CASCADE | |
| user_id | uuid | FK users(id) ON DELETE SET NULL, NULLABLE | Resolved canonical user |
| start_at | timestamptz | NOT NULL | |
| end_at | timestamptz | NOT NULL | |

Indexes:
- `idx_oncall_shifts_schedule` on (schedule_id)
- `idx_oncall_shifts_user_time` on (user_id, start_at DESC)

---

### 3.6 Slack Data

#### `slack_activity_buckets`

TimescaleDB hypertable on `bucket_hour`. Chunk interval: 1 week.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| bucket_hour | timestamptz | NOT NULL | Truncated to hour: date_trunc('hour', ts) |
| message_count | integer | NOT NULL, default 0 | Messages sent in this hour |
| is_after_hours | boolean | NOT NULL | Hour falls outside 09:00–18:00 local time |
| is_weekend | boolean | NOT NULL | Hour falls on Saturday or Sunday |
| channel_count_distinct | integer | NOT NULL, default 0 | Distinct channels active in this hour |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes (on hypertable):
- `idx_slack_buckets_user_hour` UNIQUE on (user_id, bucket_hour)
- `idx_slack_buckets_team_hour` on (team_id, bucket_hour DESC)

TimescaleDB hypertable creation (raw SQL in migration):
```sql
SELECT create_hypertable('slack_activity_buckets', 'bucket_hour',
  chunk_time_interval => INTERVAL '1 week');
```

---

### 3.7 Metric Snapshots (TimescaleDB Hypertables)

#### `team_metric_snapshots`

TimescaleDB hypertable on `snapshot_at`. Chunk interval: 1 day.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| snapshot_at | timestamptz | NOT NULL | When this snapshot was computed |
| component | varchar(30) | NOT NULL, CHECK IN ('pr_health','sprint_health','incident_load','slack_signal','composite') | |
| score | decimal(5,2) | NOT NULL | 0.00 to 100.00 |
| rag | varchar(6) | NOT NULL, CHECK IN ('red','amber','green') | Red: 0-39, Amber: 40-69, Green: 70-100 |
| computed_at | timestamptz | NOT NULL, default now() | Computation timestamp |

Indexes:
- `idx_team_snapshots_team_component_time` on (team_id, component, snapshot_at DESC)
- `idx_team_snapshots_snapshot_at` on (snapshot_at DESC)

TimescaleDB hypertable:
```sql
SELECT create_hypertable('team_metric_snapshots', 'snapshot_at',
  chunk_time_interval => INTERVAL '1 day');
```

TimescaleDB continuous aggregate for daily rollup (used for sparklines):
```sql
CREATE MATERIALIZED VIEW daily_team_scores
WITH (timescaledb.continuous) AS
SELECT team_id, component,
  time_bucket('1 day', snapshot_at) AS day,
  last(score, snapshot_at) AS score,
  last(rag, snapshot_at) AS rag
FROM team_metric_snapshots
GROUP BY team_id, component, time_bucket('1 day', snapshot_at);
```

---

#### `engineer_metric_snapshots`

TimescaleDB hypertable on `snapshot_at`. Chunk interval: 1 week.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| team_id | uuid | NOT NULL, FK teams(id) ON DELETE CASCADE | |
| snapshot_at | timestamptz | NOT NULL | |
| metric_key | varchar(100) | NOT NULL | e.g. 'pr_cycle_time_p50', 'tickets_closed_7d', 'oncall_hours_7d' |
| metric_value | decimal(12,4) | NOT NULL | |
| computed_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_eng_snapshots_user_metric_time` on (user_id, metric_key, snapshot_at DESC)
- `idx_eng_snapshots_team_time` on (team_id, snapshot_at DESC)

---

### 3.8 Health Config

#### `team_health_config`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| team_id | uuid | NOT NULL, UNIQUE, FK teams(id) ON DELETE CASCADE | One row per team |
| weight_pr_health | decimal(4,3) | NOT NULL, default 0.300, CHECK >= 0 AND <= 1 | |
| weight_sprint_health | decimal(4,3) | NOT NULL, default 0.300, CHECK >= 0 AND <= 1 | |
| weight_incident_load | decimal(4,3) | NOT NULL, default 0.250, CHECK >= 0 AND <= 1 | |
| weight_slack_signal | decimal(4,3) | NOT NULL, default 0.150, CHECK >= 0 AND <= 1 | |
| updated_at | timestamptz | NOT NULL, default now() | |
| updated_by | uuid | NOT NULL, FK users(id) | Admin who last changed weights |

Database constraint:
```sql
CONSTRAINT chk_weights_sum CHECK (
  ABS(weight_pr_health + weight_sprint_health +
      weight_incident_load + weight_slack_signal - 1.0) < 0.001
)
```

---

### 3.9 Digests

#### `digest_runs`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| run_at | timestamptz | NOT NULL | Scheduled run timestamp (Sunday 22:00 UTC snapshot; Monday 06:00 UTC send) |
| snapshot_taken_at | timestamptz | NULLABLE | When Sunday snapshot was captured |
| status | varchar(15) | NOT NULL, CHECK IN ('pending','generating','sent','failed') | |
| recipient_count | integer | NOT NULL, default 0 | Total recipients for this run |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_digest_runs_run_at` on (run_at DESC)

---

#### `digest_emails`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| digest_run_id | uuid | NOT NULL, FK digest_runs(id) ON DELETE CASCADE | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| role_scope | varchar(15) | NOT NULL, CHECK IN ('engineer','em','director') | Role used for content scoping |
| html_content | text | NOT NULL | Rendered HTML (cached, not regenerated on read) |
| sent_at | timestamptz | NULLABLE | When SendGrid accepted the email |
| delivery_status | varchar(10) | NOT NULL, default 'pending', CHECK IN ('pending','sent','failed') | |
| sendgrid_message_id | varchar(255) | NULLABLE | For delivery tracking |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_digest_emails_user_run` UNIQUE on (user_id, digest_run_id)
- `idx_digest_emails_digest_run` on (digest_run_id)
- `idx_digest_emails_status` on (delivery_status) WHERE delivery_status != 'sent'

---

### 3.10 Auth Support Tables

#### `refresh_tokens`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| token_hash | varchar(64) | NOT NULL, UNIQUE | SHA-256 hash of the refresh token |
| expires_at | timestamptz | NOT NULL | 30 days from issuance |
| revoked | boolean | NOT NULL, default false | Set true on logout |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_refresh_tokens_hash` UNIQUE on (token_hash)
- `idx_refresh_tokens_user` on (user_id)
- `idx_refresh_tokens_expires` on (expires_at) WHERE revoked = false

---

#### `password_reset_tokens`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| user_id | uuid | NOT NULL, FK users(id) ON DELETE CASCADE | |
| token_hash | varchar(64) | NOT NULL, UNIQUE | HMAC-SHA256 of the token |
| expires_at | timestamptz | NOT NULL | 1 hour from issuance |
| used | boolean | NOT NULL, default false | Invalidated after single use |
| created_at | timestamptz | NOT NULL, default now() | |

---

### 3.11 Backfill Tracking

#### `backfill_jobs`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK | |
| integration_id | uuid | NOT NULL, FK integrations(id) ON DELETE CASCADE | |
| integration_type | varchar(30) | NOT NULL | Denormalized for query convenience |
| date_from | date | NOT NULL | Backfill range start |
| date_to | date | NOT NULL | Backfill range end |
| status | varchar(15) | NOT NULL, CHECK IN ('pending','running','completed','failed') | |
| records_processed | integer | NOT NULL, default 0 | |
| records_total | integer | NULLABLE | NULL until scan complete |
| last_checkpoint | varchar(500) | NULLABLE | Last processed record ID (for resumability) |
| started_at | timestamptz | NULLABLE | |
| completed_at | timestamptz | NULLABLE | |
| error_message | text | NULLABLE | Last error if status=failed |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_backfill_jobs_integration_status` on (integration_id, status)
- `idx_backfill_jobs_status` on (status) WHERE status IN ('pending','running')

---

### 3.12 Nightly Run Tracking

#### `nightly_runs`

One row per nightly batch execution. Admin can view run history and re-trigger failed runs.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | uuid | PK, default gen_random_uuid() | |
| scheduled_at | timestamptz | NOT NULL | When the nightly window was scheduled (e.g. 2026-06-12T01:00:00Z) |
| started_at | timestamptz | NULLABLE | When the orchestrator actually began execution |
| completed_at | timestamptz | NULLABLE | When all tasks (including metric computation) finished |
| status | varchar(15) | NOT NULL, CHECK IN ('pending','running','completed','partial','failed') | Overall run status |
| integrations_completed | jsonb | NOT NULL, default '{}' | Per-integration completion flags e.g. `{"github": true, "jira": false, "pagerduty": true, "slack": true, "keka": true}` |
| metric_computation_status | varchar(15) | NOT NULL, default 'pending', CHECK IN ('pending','running','completed','failed') | Status of the chord callback metric computation step |
| error_summary | text | NULLABLE | Human-readable summary of errors if status=partial or failed |
| created_at | timestamptz | NOT NULL, default now() | |

Indexes:
- `idx_nightly_runs_scheduled_at` on (scheduled_at DESC)
- `idx_nightly_runs_status` on (status) WHERE status IN ('pending','running')

Notes:
- `status=partial` means at least one integration worker failed but metric computation still ran using the last successful data for failed integrations.
- `status=failed` means the orchestrator itself failed or metric computation failed.
- Admin UI shows the last 30 nightly run records with re-trigger button for failed/partial runs.

---

## 4. API Contracts

All endpoints:
- Require `Authorization: Bearer <access_token>` unless noted.
- Return `401` if token missing, expired, or invalid.
- Return `403` if the authenticated user's role does not permit the operation.
- Return `404` for unknown IDs. Never reveal existence of a resource to unauthorized callers (return 404, not 403, when a lower-privilege user requests a resource that belongs to another team).
- Return `429` with `Retry-After: <seconds>` header if internal rate limiting triggers (5 failed logins → 15-minute lockout; general API: 300 req/min per user).
- Error response shape:
  ```json
  {
    "error": {
      "code": "INVALID_CREDENTIALS",
      "message": "Username or password is incorrect.",
      "details": {}
    }
  }
  ```
- Success responses use HTTP 200 (GET), 201 (POST create), 204 (DELETE/logout), 200 (PUT/PATCH).
- All timestamps in responses are ISO 8601 UTC strings.
- All IDs are UUIDs as strings.
- Pagination: cursor-based where noted. Query param `cursor` (opaque base64 string). Response includes `next_cursor` (null if no more pages) and `total` (where computable without full scan).

---

### 4.1 Auth

#### POST /api/v1/auth/login
No auth required.

Request:
```json
{
  "username": "string",
  "password": "string"
}
```

Response 200:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "user": {
    "id": "uuid",
    "email": "alice@company.com",
    "username": "alice",
    "role": "em",
    "team_id": "uuid-or-null"
  }
}
```

Errors: 401 INVALID_CREDENTIALS, 429 ACCOUNT_LOCKED (after 5 consecutive failures; Retry-After header set to lockout expiry).

---

#### POST /api/v1/auth/refresh
No auth required.

Request:
```json
{ "refresh_token": "eyJ..." }
```

Response 200:
```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

Errors: 401 INVALID_REFRESH_TOKEN, 401 EXPIRED_REFRESH_TOKEN.

---

#### POST /api/v1/auth/logout
Bearer required.

Request: Empty body.

Response: 204 No Content.

Side effect: Revokes the refresh token associated with the current session (`refresh_tokens.revoked = true`).

---

#### GET /api/v1/auth/me
Bearer required.

Response 200:
```json
{
  "id": "uuid",
  "email": "alice@company.com",
  "username": "alice",
  "role": "em",
  "team_id": "uuid-or-null"
}
```

---

#### POST /api/v1/auth/password-reset/request
No auth required.

Request:
```json
{ "email": "alice@company.com" }
```

Response: 200 always (do not reveal whether email exists).
```json
{ "message": "If that email is registered, a reset link has been sent." }
```

---

#### POST /api/v1/auth/password-reset/confirm
No auth required.

Request:
```json
{
  "token": "reset-token-string",
  "new_password": "string (min 8 chars)"
}
```

Response 200:
```json
{ "message": "Password updated successfully." }
```

Errors: 400 INVALID_TOKEN, 400 EXPIRED_TOKEN, 400 PASSWORD_TOO_WEAK.

---

### 4.2 Overview

#### GET /api/v1/overview
Bearer required. Role: director sees all teams; em sees own team only.

Query params: none.

Response 200:
```json
{
  "teams": [
    {
      "team_id": "uuid",
      "name": "Platform Team",
      "slug": "platform-team",
      "composite_score": 72.5,
      "rag": "green",
      "headlines": {
        "open_prs": 4,
        "sprint_pct_done": 68,
        "active_incidents": 0
      },
      "sparkline": [
        { "date": "2026-06-05", "score": 70.1 },
        { "date": "2026-06-06", "score": 71.3 },
        { "date": "2026-06-07", "score": 69.8 },
        { "date": "2026-06-08", "score": 72.0 },
        { "date": "2026-06-09", "score": 71.5 },
        { "date": "2026-06-10", "score": 73.2 },
        { "date": "2026-06-11", "score": 72.5 }
      ],
      "last_updated_at": "2026-06-11T08:00:00Z"
    }
  ]
}
```

Cache: Redis key `overview:{user_id}`, TTL 2 hours. Invalidated nightly at 02:45 UTC after metric computation completes.

---

### 4.3 Teams

#### GET /api/v1/teams
Bearer required. Role: director or admin sees all; em sees own team.

Response 200:
```json
{
  "teams": [
    {
      "id": "uuid",
      "name": "Platform Team",
      "slug": "platform-team",
      "composite_score": 72.5,
      "rag": "green",
      "component_scores": {
        "pr_health": { "score": 80.0, "rag": "green" },
        "sprint_health": { "score": 65.0, "rag": "amber" },
        "incident_load": { "score": 90.0, "rag": "green" },
        "slack_signal": { "score": 55.0, "rag": "amber" }
      },
      "last_updated_at": "2026-06-11T08:00:00Z"
    }
  ]
}
```

---

#### GET /api/v1/teams/{team_id}
Bearer required. EM: own team only. Director/Admin: any team.

Response 200:
```json
{
  "id": "uuid",
  "name": "Platform Team",
  "slug": "platform-team",
  "em": { "id": "uuid", "username": "alice", "email": "alice@company.com" },
  "member_count": 8,
  "composite_score": 72.5,
  "rag": "green",
  "component_scores": {
    "pr_health": { "score": 80.0, "rag": "green", "weight": 0.30 },
    "sprint_health": { "score": 65.0, "rag": "amber", "weight": 0.30 },
    "incident_load": { "score": 90.0, "rag": "green", "weight": 0.25 },
    "slack_signal": { "score": 55.0, "rag": "amber", "weight": 0.15 }
  },
  "weights_custom": false,
  "last_updated_at": "2026-06-11T08:00:00Z",
  "integrations_connected": ["github", "jira", "pagerduty"]
}
```

---

#### GET /api/v1/teams/{team_id}/pr-health
Bearer required.

Response 200:
```json
{
  "team_id": "uuid",
  "component_score": 80.0,
  "rag": "green",
  "metrics": {
    "cycle_time_p50_hours": 18.5,
    "cycle_time_p90_hours": 72.0,
    "first_review_latency_p50_hours": 4.2,
    "review_turnaround_p50_hours": 6.1,
    "stale_pr_count": 3,
    "stale_pr_threshold_days": 3,
    "pr_size_p50_lines": 180,
    "review_coverage_pct": 94.0,
    "review_participation_rate_pct": 75.0,
    "review_depth_avg_comments": 2.4,
    "rework_rate_pct": 8.0,
    "author_distribution_entropy": 0.82
  },
  "dora": {
    "release_frequency_per_week": 3.2,
    "release_frequency_band": "high",
    "pr_lead_time_p50_hours": 22.0,
    "pr_lead_time_band": "high",
    "change_failure_rate_pct": 5.0,
    "change_failure_rate_band": "elite",
    "mttr_hours": 1.2,
    "mttr_band": "elite"
  },
  "last_updated_at": "2026-06-11T08:00:00Z"
}
```

---

#### GET /api/v1/teams/{team_id}/sprint-health
Response 200:
```json
{
  "team_id": "uuid",
  "component_score": 65.0,
  "rag": "amber",
  "current_sprint": {
    "id": "uuid",
    "name": "Sprint 42",
    "start_date": "2026-06-01",
    "end_date": "2026-06-14",
    "days_remaining": 3
  },
  "metrics": {
    "burndown_pct_ideal": 70.0,
    "burndown_pct_actual": 55.0,
    "scope_creep_pct": 12.0,
    "carryover_rate_pct": 18.0,
    "blocked_ticket_count": 2,
    "blocked_ticket_avg_age_days": 4.5,
    "velocity_trend_6_sprints": [42, 38, 45, 40, 37, 39],
    "ticket_cycle_time_p50_hours": 36.0,
    "commitment_vs_delivery_pct": 88.0,
    "estimation_accuracy_pct": 82.0
  },
  "throughput": {
    "prs_merged_7d": 12,
    "tickets_closed_7d": 8,
    "story_points_7d": 31.0,
    "wip_count": 9,
    "flow_efficiency_pct": 54.0
  },
  "last_updated_at": "2026-06-11T08:00:00Z"
}
```

---

#### GET /api/v1/teams/{team_id}/incident-load
Response 200:
```json
{
  "team_id": "uuid",
  "component_score": 90.0,
  "rag": "green",
  "metrics": {
    "incident_frequency_7d": 1,
    "incident_frequency_30d": 4,
    "mttr_p50_hours": 1.2,
    "mtta_p50_minutes": 8.0,
    "p1_count_30d": 0,
    "p2_count_30d": 1,
    "repeat_incidents_by_service": [
      { "service": "payments-api", "count": 2 }
    ],
    "oncall_hours_per_engineer_7d": [
      { "user_id": "uuid", "username": "bob", "hours": 24 },
      { "user_id": "uuid", "username": "carol", "hours": 24 }
    ]
  },
  "last_updated_at": "2026-06-11T08:00:00Z"
}
```

---

#### GET /api/v1/teams/{team_id}/slack-signal
Response 200 (data available):
```json
{
  "team_id": "uuid",
  "component_score": 55.0,
  "rag": "amber",
  "available": true,
  "metrics": {
    "after_hours_message_pct_7d": 22.0,
    "weekend_message_pct_7d": 8.0,
    "message_volume_trend_direction": "stable",
    "engineers_above_after_hours_threshold": 2
  },
  "last_updated_at": "2026-06-11T08:00:00Z"
}
```

Response 200 (degraded):
```json
{
  "team_id": "uuid",
  "component_score": null,
  "rag": null,
  "available": false,
  "degradation_reason": "workspace_too_large",
  "degradation_message": "Slack signal unavailable — workspace too large for standard API tier (>50 channels or >200 members).",
  "last_updated_at": null
}
```

---

#### GET /api/v1/teams/{team_id}/members
Response 200:
```json
{
  "team_id": "uuid",
  "members": [
    {
      "user_id": "uuid",
      "username": "bob",
      "email": "bob@company.com",
      "load_indicator": "high",
      "load_reason": "WIP count above team median and on-call this week",
      "metrics": {
        "open_prs": 3,
        "tickets_in_progress": 4,
        "oncall_this_week": true,
        "pr_cycle_time_p50_hours": 28.0
      }
    }
  ]
}
```

---

### 4.4 Engineers

#### GET /api/v1/engineers
Bearer required. Director: all engineers. EM: own team only. Engineer: 403.

Query params: `team_id` (optional, director only), `cursor`, `limit` (default 50).

Response 200:
```json
{
  "engineers": [
    {
      "user_id": "uuid",
      "username": "bob",
      "email": "bob@company.com",
      "role": "engineer",
      "team_id": "uuid",
      "team_name": "Platform Team",
      "load_indicator": "high",
      "headline_metrics": {
        "prs_merged_7d": 2,
        "tickets_closed_7d": 3,
        "oncall_hours_7d": 24,
        "pr_cycle_time_p50_hours": 28.0
      }
    }
  ],
  "next_cursor": "base64string-or-null",
  "total": 42
}
```

---

#### GET /api/v1/engineers/{user_id}
Bearer required. Engineer: own profile only (403 for others). EM: own team only. Director/Admin: any.

Response 200:
```json
{
  "user_id": "uuid",
  "username": "bob",
  "email": "bob@company.com",
  "role": "engineer",
  "team_id": "uuid",
  "team_name": "Platform Team",
  "load_indicator": "high",
  "identity_resolution_complete": true
}
```

---

#### GET /api/v1/engineers/{user_id}/code-activity
Query params: `days` (7/14/30, default 14).

Response 200:
```json
{
  "user_id": "uuid",
  "period_days": 14,
  "prs_authored": 5,
  "prs_merged": 4,
  "prs_open": 1,
  "avg_cycle_time_hours": 22.0,
  "cycle_time_trend": [
    { "week": "2026-W23", "p50_hours": 20.0 },
    { "week": "2026-W24", "p50_hours": 24.0 }
  ],
  "pr_size_distribution": {
    "xs_0_50": 1, "s_51_200": 2, "m_201_500": 1, "l_501_plus": 1
  }
}
```

---

#### GET /api/v1/engineers/{user_id}/review-activity
Response 200:
```json
{
  "user_id": "uuid",
  "period_days": 14,
  "prs_reviewed": 8,
  "first_review_latency_p50_hours": 3.5,
  "review_depth_avg_comments": 2.8,
  "reviews_by_state": {
    "approved": 6,
    "changes_requested": 1,
    "commented": 1
  }
}
```

---

#### GET /api/v1/engineers/{user_id}/task-delivery
Response 200:
```json
{
  "user_id": "uuid",
  "period_days": 14,
  "tickets_closed": 6,
  "ticket_cycle_time_p50_hours": 38.0,
  "carryover_count": 1,
  "story_points_delivered": 18.0,
  "wip_current": 3
}
```

---

#### GET /api/v1/engineers/{user_id}/incident-load
Response 200:
```json
{
  "user_id": "uuid",
  "period_days": 14,
  "incidents_assigned": 2,
  "personal_mttr_p50_hours": 1.5,
  "oncall_hours": 48,
  "oncall_shifts": [
    { "schedule_name": "Payments On-Call", "start_at": "2026-06-09T00:00:00Z", "end_at": "2026-06-10T00:00:00Z" }
  ]
}
```

---

#### GET /api/v1/engineers/{user_id}/collaboration
Response 200:
```json
{
  "user_id": "uuid",
  "period_days": 30,
  "reviews_given_to": [
    { "user_id": "uuid", "username": "alice", "review_count": 12 }
  ],
  "reviews_received_from": [
    { "user_id": "uuid", "username": "carol", "review_count": 9 }
  ]
}
```

---

### 4.5 Incidents

#### GET /api/v1/incidents
Bearer required. EM: own team. Director: all teams.

Query params: `days` (30/60/90, default 30), `team_id` (optional), `service` (optional), `severity` (p1/p2/p3/p4, optional), `cursor`, `limit` (default 50).

Response 200:
```json
{
  "incidents": [
    {
      "id": "uuid",
      "external_id": "PD123",
      "title": "Payment gateway timeout",
      "severity": "p2",
      "service_name": "payments-api",
      "team_id": "uuid",
      "triggered_at": "2026-06-10T14:22:00Z",
      "acknowledged_at": "2026-06-10T14:30:00Z",
      "resolved_at": "2026-06-10T15:45:00Z",
      "mtta_seconds": 480,
      "mttr_seconds": 5580
    }
  ],
  "summary": {
    "total_incidents": 12,
    "p1_count": 0,
    "p2_count": 3,
    "avg_mttr_hours": 2.1,
    "avg_mtta_minutes": 9.5
  },
  "next_cursor": null,
  "total": 12
}
```

---

#### GET /api/v1/incidents/oncall-fairness
Query params: `days` (30/60/90, default 30), `team_id` (optional).

Response 200:
```json
{
  "period_days": 30,
  "engineers": [
    {
      "user_id": "uuid",
      "username": "bob",
      "oncall_hours": 168,
      "incident_count": 3
    }
  ]
}
```

---

#### GET /api/v1/incidents/delivery-correlation
Query params: `weeks` (4/8/12, default 8), `team_id` (optional).

Response 200:
```json
{
  "weeks": 8,
  "series": [
    {
      "week": "2026-W17",
      "incident_count": 5,
      "prs_merged": 18,
      "team_id": "uuid",
      "team_name": "Platform Team"
    }
  ]
}
```

---

### 4.6 Digests

#### GET /api/v1/digests
Bearer required. Returns digests scoped to current user's role.

Response 200:
```json
{
  "digests": [
    {
      "id": "uuid",
      "digest_run_id": "uuid",
      "run_at": "2026-06-09T06:00:00Z",
      "role_scope": "em",
      "delivery_status": "sent",
      "sent_at": "2026-06-09T06:03:00Z"
    }
  ]
}
```

---

#### GET /api/v1/digests/{digest_id}
Bearer required. Returns digest HTML only if it belongs to the requesting user.

Response 200:
```json
{
  "id": "uuid",
  "run_at": "2026-06-09T06:00:00Z",
  "role_scope": "em",
  "html_content": "<html>...</html>"
}
```

---

#### GET /api/v1/digests/preview
Bearer required. Generates a preview of the next Monday's digest using current data (not cached; max 1 req/min per user).

Response 200:
```json
{
  "preview_generated_at": "2026-06-11T10:00:00Z",
  "scheduled_send_at": "2026-06-16T06:00:00Z",
  "html_content": "<html>...</html>"
}
```

---

### 4.7 Admin — Integrations

#### GET /api/v1/admin/integrations
Admin only.

Response 200:
```json
{
  "integrations": [
    {
      "id": "uuid",
      "type": "github",
      "status": "connected",
      "last_synced_at": "2026-06-11T09:00:00Z",
      "team_id": null,
      "config_summary": { "org_name": "myorg", "token_expires_at": "2027-06-12T00:00:00Z" }
    }
  ]
}
```

Note: `config_summary` contains only non-sensitive fields. API tokens and private keys are never returned.

---

#### POST /api/v1/admin/integrations
Admin only.

Request:
```json
{
  "type": "github",
  "team_id": null,
  "config": {
    "personal_access_token": "ghp_...",
    "org_name": "myorg",
    "release_tag_pattern": "v[0-9]+\\.[0-9]+\\.[0-9]+"
  }
}
```

Response 201: Integration object (without sensitive config fields).

---

#### PUT /api/v1/admin/integrations/{id}
Admin only. Partial update of config fields.

Request: Same shape as POST config, only include fields to update.
Response 200: Updated integration object.

---

#### DELETE /api/v1/admin/integrations/{id}
Admin only. Sets status to 'disconnected', clears config_json.

Response 204.

---

#### POST /api/v1/admin/integrations/{id}/test
Admin only. Tests connectivity with current config.

Response 200:
```json
{ "ok": true, "latency_ms": 142 }
```
or
```json
{ "ok": false, "error": "401 Unauthorized: invalid API token" }
```

---

#### POST /api/v1/admin/integrations/{id}/backfill
Admin only.

Request:
```json
{
  "from_date": "2026-01-01",
  "to_date": "2026-03-31",
  "team_id": "uuid-optional"
}
```

Response 202:
```json
{ "backfill_job_id": "uuid", "status": "pending" }
```

---

#### GET /api/v1/admin/integrations/{id}/backfill-status
Admin only.

Response 200:
```json
{
  "backfill_job_id": "uuid",
  "status": "running",
  "records_processed": 342,
  "records_total": 1200,
  "progress_pct": 28.5,
  "last_checkpoint": "PR#1847",
  "started_at": "2026-06-11T09:05:00Z",
  "estimated_completion_at": "2026-06-11T11:30:00Z"
}
```

---

### 4.8 Admin — Teams, Users, Org Tree

#### GET /api/v1/admin/teams
#### POST /api/v1/admin/teams
#### GET /api/v1/admin/teams/{id}
#### PUT /api/v1/admin/teams/{id}
#### DELETE /api/v1/admin/teams/{id}

Standard CRUD. POST body:
```json
{
  "name": "Platform Team",
  "slug": "platform-team",
  "em_user_id": "uuid"
}
```

DELETE: Sets team as archived (does not hard-delete). Returns 409 if team has active members.

---

#### GET /api/v1/admin/users
#### POST /api/v1/admin/users
#### GET /api/v1/admin/users/{id}
#### PUT /api/v1/admin/users/{id}
#### DELETE /api/v1/admin/users/{id}

POST body:
```json
{
  "email": "bob@company.com",
  "username": "bob",
  "password": "initial-password",
  "role": "engineer",
  "team_id": "uuid-or-null"
}
```

DELETE: Sets `users.is_active = false`. Historical data retained. 409 if deleting last admin.

---

#### GET /api/v1/admin/org-tree
Admin only.

Response 200:
```json
{
  "source": "keka",
  "last_keka_sync_at": "2026-06-11T02:00:00Z",
  "nodes": [
    {
      "employee_user_id": "uuid",
      "username": "bob",
      "manager_user_id": "uuid",
      "manager_username": "alice"
    }
  ]
}
```

---

#### PUT /api/v1/admin/org-tree
Admin only. Bulk update (replaces all manual source entries).

Request:
```json
{
  "nodes": [
    { "employee_user_id": "uuid", "manager_user_id": "uuid" }
  ]
}
```

Response 200: Updated org tree.

---

### 4.9 Admin — Identity

#### GET /api/v1/admin/identity-mismatches
Admin only.

Response 200:
```json
{
  "mismatches": [
    {
      "id": "pseudo-id",
      "tool": "github",
      "tool_user_id": "john-smith-contractor",
      "tool_email": "john.smith@contractor.io",
      "candidate_users": [
        { "user_id": "uuid", "username": "jsmith", "email": "jsmith@company.com", "match_score": 0.91 }
      ]
    }
  ],
  "total_unresolved": 3,
  "auto_resolution_rate_pct": 94.0
}
```

---

#### PUT /api/v1/admin/identity-mappings/{id}
Admin only.

Request:
```json
{
  "canonical_user_id": "uuid",
  "resolution_method": "manual"
}
```

Response 200: Updated identity_mapping record.

---

### 4.10 Admin — Nightly Runs

#### GET /api/v1/admin/nightly-runs
Auth: Admin role required.

Response 200:
```json
{
  "runs": [
    {
      "id": "uuid",
      "scheduled_at": "2026-06-12T01:00:00Z",
      "started_at": "2026-06-12T01:00:02Z",
      "status": "completed",
      "integrations_completed": {
        "github": true,
        "jira": true,
        "clickup": true,
        "pagerduty": true,
        "zenduty": true,
        "slack": true,
        "keka": true
      },
      "metric_computation_status": "completed",
      "completed_at": "2026-06-12T02:48:00Z",
      "error_summary": null
    }
  ]
}
```

---

#### POST /api/v1/admin/nightly-runs/trigger
Auth: Admin role required.

Description: Manually trigger a nightly run (for re-runs after failure or partial completion).

Request: `{}` (empty body)

Response 202:
```json
{ "run_id": "uuid", "message": "Nightly run queued" }
```

Response 409:
```json
{ "error": { "code": "run_already_active", "message": "A nightly run is already in progress" } }
```

---

## 5. Component Breakdown

### 5.1 FastAPI App

**Responsibility:** HTTP layer, authentication middleware, RBAC enforcement, request routing, rate limiting, and observability instrumentation.

**Module:** `engg_intelligence/api/`

**Structure:**
```
api/
  main.py              # FastAPI app factory, middleware registration
  deps.py              # Shared FastAPI Depends() functions
  routers/
    auth.py
    overview.py
    teams.py
    engineers.py
    incidents.py
    digests.py
    admin/
      integrations.py
      teams.py
      users.py
      org_tree.py
      identity.py
  webhooks/
    sendgrid.py        # SendGrid delivery event callbacks only
  middleware/
    auth.py            # JWT decode + user resolution
    rate_limit.py      # slowapi Redis-backed rate limiter
    logging.py         # Request/response structured logging
```

**Auth flow:**
1. `JWTMiddleware` runs on every request to `/api/v1/*`.
2. Extracts `Authorization: Bearer <token>` header.
3. Decodes and verifies JWT (HS256, checks exp, iat).
4. Resolves user from `sub` claim → loads minimal user object (id, role, team_id) from Redis cache `user:{user_id}` (TTL 5 minutes) or DB.
5. Sets `request.state.user`.

**RBAC enforcement:**
- Each router uses `Depends(require_role("admin"))` or `Depends(require_roles(["director","admin"]))` from `deps.py`.
- `require_team_access(team_id)`: validates that the requesting EM's `team_id` matches the requested `team_id`. Returns 404 (not 403) when mismatch — do not leak team existence.
- `require_self_or_above(user_id)`: for engineer endpoints, allows access only if `current_user.id == user_id` OR role is `em/director/admin`.

**Rate limiting:**
- `slowapi` library with Redis backend.
- Login endpoint: 5 req/min per IP (enforces account lockout).
- All other endpoints: 300 req/min per user (JWT subject).
- 429 response includes `Retry-After` header.

---

### 5.2 Nightly Run Orchestrator

**Responsibility:** Celery Beat task that fires at 01:00 UTC daily. Creates the `nightly_runs` record, dispatches all integration tasks as a Celery group with a chord callback to Metric Computation, and updates run status on completion or failure.

**Module:** `engg_intelligence/workers/nightly_orchestrator.py`

**Task:** `run_nightly_batch()` — triggered by Celery Beat at 01:00 UTC.

**Orchestration flow:**
1. Check if a `nightly_runs` record with `status='running'` already exists for today. If so: abort and log a warning (prevents overlapping runs).
2. Create `nightly_runs` record with `status='running'`, `started_at=now()`.
3. Build a Celery group of integration tasks (each fires at its staggered scheduled time via task ETA or countdown):
   ```python
   from celery import group, chord
   integration_tasks = group(
       sync_github_nightly.s(integration_id).set(countdown=0),        # 01:00
       sync_pm_nightly.s(integration_id).set(countdown=1200),          # 01:20
       sync_incidents_nightly.s(integration_id).set(countdown=2400),   # 01:40
       sync_slack_nightly.s(integration_id).set(countdown=3600),       # 02:00
       sync_keka_nightly.s(integration_id).set(countdown=4500),        # 02:15
   )
   chord(integration_tasks)(run_metric_computation.s(nightly_run_id))
   ```
4. On chord callback (`run_metric_computation`):
   - Check `integrations_completed` on the `nightly_runs` record.
   - Run `recompute_all_teams()` using best available data (last successful sync for any failed integration).
   - Update `nightly_runs.metric_computation_status = 'completed'`.
   - Update `nightly_runs.status = 'completed'` (or `'partial'` if any integration failed).
   - Update `nightly_runs.completed_at = now()`.
   - Invalidate all API response caches.
   - On Monday: enqueue `prepare_digest_snapshot()` task.
5. On any integration task failure: update `nightly_runs.integrations_completed[integration] = false`. Set `status='partial'`. Notify admin via in-app notification.

---

### 5.3 GitHub Ingestion Worker

**Responsibility:** Consume q_github tasks. Perform nightly batch pull of PRs/reviews/commits/releases updated in the last 24 hours using PAT authentication. Persist to PostgreSQL.

**Module:** `engg_intelligence/workers/github_worker.py`

**Tasks:**
- `sync_github_nightly(integration_id, nightly_run_id)` — nightly batch pull triggered by Nightly Run Orchestrator
- `backfill_github(integration_id, date_from, date_to, checkpoint)` — backfill task

**Nightly batch pull flow:**
1. Authenticate using PAT: `Authorization: token {personal_access_token}` from `integrations.config_json`.
2. Enumerate repos: `GET /orgs/{org_name}/repos?type=all&per_page=100`.
3. For each repo: fetch PRs updated in the last 24 hours using incremental fetch:
   ```
   GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&since={yesterday_ISO8601}&per_page=100
   ```
4. For each PR returned: upsert `pull_requests` row (ON CONFLICT ON CONSTRAINT idx_prs_github_id DO UPDATE SET ...).
5. Fetch reviews: `GET /repos/{owner}/{repo}/pulls/{number}/reviews` → upsert `pr_reviews`.
6. Fetch commits: `GET /repos/{owner}/{repo}/pulls/{number}/commits` → upsert `commits`.
7. Fetch releases updated since yesterday: `GET /repos/{owner}/{repo}/releases?per_page=100` → filter by `published_at >= yesterday`.
8. Compute `cycle_time_seconds` = `merged_at - created_at` if merged.
9. Compute `first_review_at` = min `submitted_at` from `pr_reviews` for this PR.
10. Compute `last_activity_at` = max of (PR `updated_at`, latest review `submitted_at`, latest commit `committed_at`).
11. Resolve `author_user_id` via Identity Resolver.
12. Update `integrations.last_synced_at` and `nightly_runs.integrations_completed.github = true` on success.

**Rate limit handling:**
- Check `X-RateLimit-Remaining` response header after every API call.
- If value < 200: add 1 second sleep between requests.
- PAT rate limit: 5,000 req/hr. Nightly batch for typical org (50–200 repos, last 24h activity) expects 200–500 requests — well within limit. Track consumption in Redis counter `github_rate:{integration_id}` with TTL reset at the rate limit window.

**Backfill via GraphQL:**
```graphql
query($owner: String!, $repo: String!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequests(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { endCursor hasNextPage }
      nodes {
        number title state createdAt mergedAt closedAt
        author { login }
        additions deletions headRefName baseRefName
      }
    }
  }
}
```
Checkpoint stored in `backfill_jobs.last_checkpoint` as `{repo}:{pr_number}` after each batch.

---

### 5.4 Jira/ClickUp Ingestion Worker

**Responsibility:** Consume q_jira_clickup tasks. Batch pull sprint and ticket data nightly at 01:20 UTC. Fetch sprints and issues updated since `yesterday_start_UTC`.

**Module:** `engg_intelligence/workers/pm_worker.py`

**Tasks:**
- `sync_jira_nightly(integration_id, nightly_run_id)` — nightly at 01:20 UTC
- `sync_clickup_nightly(integration_id, nightly_run_id)` — nightly at 01:20 UTC alongside Jira
- `backfill_pm(integration_id, date_from, date_to)` — backfill

**Jira sync flow:**
1. Fetch active boards: `GET /rest/agile/1.0/board` (paginated).
2. For each board, fetch active sprint: `GET /rest/agile/1.0/board/{boardId}/sprint?state=active,future`.
3. Upsert `sprints` rows.
4. For each sprint, fetch issues updated since yesterday: `GET /rest/agile/1.0/sprint/{sprintId}/issue?fields=summary,status,assignee,story_points,customfield_10016&expand=changelog&updatedAfter={yesterday_start_UTC_ms}`.
5. Upsert `tickets`. Parse `changelog.histories` → upsert `ticket_state_transitions`.
6. Update `integrations.last_synced_at` and `nightly_runs.integrations_completed.jira = true` on success.

**ClickUp sync flow:**
1. For each configured sprint list ID: `GET /api/v2/list/{list_id}/task?include_closed=true&date_updated_gt={last_synced_ts}`.
2. Map ClickUp task to ticket schema. Custom field for story points: look up by field name configured in `integrations.config_json.story_points_custom_field_name`.
3. Upsert `tickets`. No native changelog; derive transitions from `date_updated` and `status` changes on successive polls.

**Exponential backoff on 429:**
```python
delay = min(60, (2 ** attempt) + random.uniform(0, 0.2 * (2 ** attempt)))
time.sleep(delay)
```
Max 5 retries before marking task as failed.

---

### 5.5 PagerDuty/Zenduty Ingestion Worker

**Responsibility:** Consume q_incidents tasks. Batch pull incidents nightly at 01:40 UTC. Fetch incidents with `since=yesterday_start_UTC&until=today_start_UTC`. Sync on-call schedules once nightly. Compute MTTR/MTTA. Write incident metrics.

**Module:** `engg_intelligence/workers/incident_worker.py`

**Tasks:**
- `sync_pagerduty_nightly(integration_id, nightly_run_id)` — nightly at 01:40 UTC
- `sync_zenduty_nightly(integration_id, nightly_run_id)` — nightly at 01:40 UTC

**PagerDuty incident sync:**
1. `GET /incidents?since={yesterday_start_UTC}&until={today_start_UTC}&statuses[]=triggered&statuses[]=acknowledged&statuses[]=resolved&limit=100&offset={offset}`.
2. For each incident: upsert `incidents`. Compute `mtta_seconds` and `mttr_seconds` from timestamps.
3. Fetch log entries for unresolved incidents: `GET /log_entries?incident_ids[]={id}&include[]=channel`.
4. Upsert `incident_assignments`.

**Zenduty incident sync:**
1. `GET /api/account/teams/{team_unique_id}/incidents/?limit=100&offset={offset}&created_at__gte={last_synced_at}`.
2. Use analytics endpoint for aggregate MTTA/MTTR: `GET /api/account/teams/{team_unique_id}/analytics/?start_date={}&end_date={}`.
3. On-call sync (once nightly): `GET /api/account/teams/{team_unique_id}/oncall/` with token bucket rate limiter (40 req/min, burst 10). On-call schedule syncs once per nightly run — no separate 6h poll.
4. Update `nightly_runs.integrations_completed.zenduty = true` on success.

**Token bucket implementation for Zenduty:**
```python
class TokenBucket:
    def __init__(self, rate=40, burst=10):
        self.tokens = burst
        self.rate = rate
        self.last = time.monotonic()

    def consume(self):
        now = time.monotonic()
        self.tokens = min(self.burst,
            self.tokens + (now - self.last) * self.rate / 60)
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        time.sleep((1 - self.tokens) * 60 / self.rate)
        return self.consume()
```

---

### 5.6 Slack Ingestion Worker

**Responsibility:** Consume q_slack tasks. Batch pull Slack metadata nightly at 02:00 UTC. Pull workspace user list for identity resolution and conversations.history for non-degraded workspaces. Compute after-hours/weekend buckets. Degrade gracefully.

**Module:** `engg_intelligence/workers/slack_worker.py`

**Tasks:**
- `sync_slack_nightly(integration_id, nightly_run_id)` — nightly at 02:00 UTC (users + activity in one task)

**Degradation check (runs on first connect and every 24 hours):**
1. `GET /api/team.info` → extract `team.approximate_member_count`.
2. `GET /api/conversations.list?types=public_channel&limit=200` → count channels.
3. If members > 200 OR channel count > 50: set `config_json.slack_signal_degraded = true`. Skip activity sync.

**Activity sync (non-degraded):**
1. Fetch public channels: `GET /api/conversations.list`.
2. For each channel (up to 50): `GET /api/conversations.history?channel={id}&oldest={last_synced_ts}&limit=200`.
3. Rate limit: 1 request per minute per channel using a per-channel Redis lock `slack_rate:{channel_id}` with TTL 60s.
4. Process timestamps only: for each message, extract `ts` (epoch float). Do not store `text`, `user` details beyond user_id. Discard raw payload after processing.
5. For each message timestamp: resolve `user_id` via identity mappings. Determine `bucket_hour = date_trunc('hour', ts)`. Determine `is_after_hours`, `is_weekend`.
6. Upsert `slack_activity_buckets` (ON CONFLICT (user_id, bucket_hour) DO UPDATE SET message_count = message_count + excluded.message_count).

---

### 5.7 Keka Sync Worker

**Responsibility:** Consume q_keka tasks. Daily sync of org tree. Overwrite org_nodes table with Keka data.

**Module:** `engg_intelligence/workers/keka_worker.py`

**Task:** `sync_keka_nightly(integration_id, nightly_run_id)` — nightly at 02:15 UTC, after Slack sync completes.

**Sync flow:**
1. `GET /api/v1/hris/employees` (paginated, page size 50).
2. For each employee: extract `email`, `manager_email`.
3. Match email → `users.email` → get `user_id` and `manager_user_id`.
4. Within a transaction:
   a. `DELETE FROM org_nodes` (all rows, regardless of source — Keka is authoritative).
   b. Bulk insert new `org_nodes` rows with `source='keka'`.
5. Update `integrations.last_synced_at` and `nightly_runs.integrations_completed.keka = true` on success.

On Keka disconnect: emit `keka_disconnected` event. Admin UI prompts choice (restore manual config or keep Keka snapshot). If "restore manual": admin must re-enter via PUT /api/v1/admin/org-tree.

---

### 5.8 Metric Computation Engine

**Responsibility:** Triggered as a Celery chord callback after all nightly ingestion tasks complete (02:30 UTC). Recompute all component and composite health scores for all teams. Write to `team_metric_snapshots`. Invalidate Redis caches at 02:45 UTC.

**Module:** `engg_intelligence/metrics/`

**Tasks:**
- `run_metric_computation(nightly_run_id)` — chord callback, triggered after all nightly integration workers complete; recomputes all components for all teams
- `recompute_all_teams()` — called internally by `run_metric_computation`; individual component recompute functions still exist for use during backfill

**Composite score computation:**
```python
def compute_composite(team_id: UUID, weights: TeamHealthConfig) -> float:
    scores = {}
    available_components = get_available_components(team_id)

    for component in available_components:
        scores[component] = get_latest_component_score(team_id, component)

    if not scores:
        return None  # "Insufficient data"

    # Redistribute weights for missing components
    total_weight = sum(getattr(weights, f"weight_{c}") for c in available_components)
    composite = sum(
        scores[c] * (getattr(weights, f"weight_{c}") / total_weight)
        for c in available_components
    )
    return round(composite, 2)
```

**RAG thresholds:** Red: 0–39.99, Amber: 40–69.99, Green: 70–100.

**Load indicator formula (for engineer cards):**
- `wip_current > team_median_wip * 1.5` → +1 point
- `oncall_this_week == True` → +1 point
- `pr_cycle_time_p50 > team_median_cycle_time * 1.5` → +1 point
- `incidents_assigned_7d > team_median_incidents * 2` → +1 point
- Score 0 → "low", 1 → "medium", 2+ → "high"

---

### 5.9 Identity Resolver

**Responsibility:** After each ingestion job, match tool user IDs/emails to canonical `users` table entries. Log mismatches for admin review.

**Module:** `engg_intelligence/identity/resolver.py`

**Resolution flow (per ingestion record):**
1. Extract `tool_email` from payload.
2. `SELECT id FROM users WHERE email = tool_email` (exact match).
3. If found: upsert `identity_mappings` with `resolution_method='auto'`.
4. If not found: use `pg_trgm` similarity:
   ```sql
   SELECT id, email, similarity(email, :tool_email) AS sim
   FROM users
   WHERE similarity(email, :tool_email) > 0.7
   ORDER BY sim DESC LIMIT 3
   ```
5. If one result with sim > 0.85: auto-resolve with `resolution_method='auto'`.
6. If ambiguous (multiple results) or sim < 0.7: log to unresolved queue (tracked in Redis set `identity_mismatches`, persisted to admin review endpoint).
7. If `tool_user_id` already exists in `identity_mappings`: use existing mapping (do not re-resolve).

---

### 5.10 Digest Generator

**Responsibility:** Generate role-scoped weekly digest HTML for each recipient. Store in `digest_emails`. Send via SendGrid.

**Module:** `engg_intelligence/digest/`

**Tasks:**
- `prepare_digest_snapshot()` — Monday 02:45 UTC (chord callback after nightly metric computation completes): create `digest_runs` record, snapshot current metric state
- `generate_and_send_digests()` — Monday 06:00 UTC: render HTML per recipient, enqueue sends
- `send_digest_email(digest_email_id)` — individual send task in q_digest

**Idempotency guard:**
```python
existing = db.query(DigestEmail).filter(
    DigestEmail.digest_run_id == run_id,
    DigestEmail.user_id == user_id
).first()
if existing and existing.delivery_status == 'sent':
    return  # Do not re-send
```

**Template structure:**
```
engg_intelligence/templates/
  mjml/
    base.mjml
    engineer_digest.mjml
    em_digest.mjml
    director_digest.mjml
  compiled/                 # Pre-compiled HTML (at build time)
    engineer_digest.html
    em_digest.html
    director_digest.html
  jinja/
    engineer_digest.j2
    em_digest.j2
    director_digest.j2
```

**SendGrid delivery tracking:**
- Store `sendgrid_message_id` from API response.
- Expose `/webhooks/sendgrid/events` endpoint to receive delivery callbacks.
- On `delivered` event: update `digest_emails.delivery_status = 'sent'`, set `sent_at`.
- On `bounce`/`dropped`: update to `failed`. Schedule retry via `send_digest_email.apply_async(countdown=3600)`.

---

### 5.11 Celery Beat

**Responsibility:** Isolated scheduler service. Manages all periodic task triggers.

**Module:** `celery_app.py` (Beat schedule configuration)

**Schedule (all times UTC):**
```python
beat_schedule = {
    # Nightly Run Orchestrator: fires daily at 01:00 UTC
    # Dispatches all integration tasks as a Celery chord with staggered countdowns
    # GitHub: 01:00, Jira/ClickUp: 01:20, PD/Zenduty: 01:40, Slack: 02:00, Keka: 02:15
    # Metric computation chord callback: ~02:30
    # Cache invalidation: ~02:45
    "nightly-run-orchestrator": {
        "task": "workers.nightly_orchestrator.run_nightly_batch",
        "schedule": crontab(minute=0, hour=1),
    },
    # Digest: Monday 06:00 send
    # (snapshot taken as chord callback on Monday nightly run at ~02:45)
    "digest-monday-send": {
        "task": "digest.generator.generate_and_send_digests",
        "schedule": crontab(minute=0, hour=6, day_of_week=1),
    },
    # Data retention: daily purge of >12-month data
    "data-retention-purge": {
        "task": "maintenance.purge_old_data",
        "schedule": crontab(minute=0, hour=4),
    },
}
```

Celery Beat runs as a dedicated process (`celery -A celery_app beat --loglevel=info`), separate from worker processes.

---

### 5.12 Admin CLI

**Responsibility:** Command-line interface for technical admins. Backfill, database operations, user management.

**Module:** `engg_intelligence/cli.py` (entry point: `python -m engg_intelligence.cli`)

**Commands:**
```
python -m engg_intelligence.cli backfill \
  --integration github \
  --from 2026-01-01 \
  --to 2026-03-31 \
  --team platform-team \
  [--dry-run]

python -m engg_intelligence.cli nightly-run \
  --date 2026-06-10

python -m engg_intelligence.cli create-admin \
  --email admin@company.com \
  --username admin \
  --password <password>

python -m engg_intelligence.cli list-integrations

python -m engg_intelligence.cli check-identity-resolution \
  --team platform-team
```

**Backfill CLI flow:**
1. Validate `--integration` value. Exit code 1 if invalid. For GitHub, authentication uses the configured PAT.
2. Validate `--from < --to`. Exit code 1 if invalid.
3. If `--dry-run`: print what would be fetched, count records, exit 0 without DB writes.
4. Resolve team by slug (if `--team` provided).
5. Create `backfill_jobs` record with `status='pending'`.
6. Enqueue Celery backfill task. Print job ID.
7. Poll `backfill_jobs` record every 10 seconds, printing progress to stdout.
8. Exit 0 on `status='completed'`, exit 1 on `status='failed'`.

**Nightly-run CLI flow (`nightly-run --date YYYY-MM-DD`):**
1. Validate `--date` format.
2. Check no existing `nightly_runs` record for that date with `status='running'` (exit 1 if active).
3. Enqueue `run_nightly_batch` task with `scheduled_at` set to the specified date's 01:00 UTC.
4. Print the `nightly_run_id`.
5. Poll `nightly_runs` record every 15 seconds, printing status to stdout.
6. Exit 0 on `status='completed'`, exit 1 on `status='failed'`.


---

## 6. Integration Details

### 6.1 GitHub

**Auth: Personal Access Token (PAT)**

**Config fields stored in `integrations.config_json`:**
```json
{
  "personal_access_token": "<encrypted>",
  "org_name": "myorg",
  "release_tag_pattern": "v[0-9]+\\.[0-9]+\\.[0-9]+"
}
```

Required scopes: `repo` (read-only). For fine-grained PATs: enable read access to `Contents`, `Pull requests`, `Metadata`, `Releases`.

Install flow:
1. Admin navigates to Admin UI → Integrations → GitHub → Connect.
2. Admin pastes: `personal_access_token`, `org_name`, `release_tag_pattern` (regex string).
3. System stores encrypted in `integrations.config_json`.
4. All API calls use: `Authorization: token {personal_access_token}`.

**Incremental fetch strategy (nightly):**
- Use `?since=<yesterday_ISO8601>` parameter on `/repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc&since={yesterday}` to fetch only PRs updated in the last 24 hours.
- For releases: fetch `GET /repos/{owner}/{repo}/releases?per_page=100` and filter by `published_at >= yesterday_start_UTC`.
- For backfill: paginate with full date range using GraphQL cursor pagination (100 PRs per page).

**Rate limit handling:**
```python
response = requests.get(url, headers=headers)
remaining = int(response.headers.get("X-RateLimit-Remaining", 1000))
reset_ts = int(response.headers.get("X-RateLimit-Reset", time.time()))
if remaining < 200:
    time.sleep(1)  # 1s sleep between requests when rate limit is low
    logger.info("github_rate_limit_throttle", remaining=remaining)
```

PAT rate limit: 5,000 req/hr. Expected nightly usage for a typical org (50–200 repos): 200–500 requests. Well within limit.

**Backfill strategy:**
1. Enumerate repos via `GET /orgs/{org_name}/repos?type=all&per_page=100`.
2. For each repo: use GraphQL `pullRequests` query with cursor pagination (100 PRs per page).
3. Filter by `createdAt >= date_from AND createdAt <= date_to`.
4. After PR batch: fetch reviews and commits per PR via REST (parallel with `asyncio.gather`, max 5 concurrent).
5. Checkpoint after each repo: `{repo_full_name}:{last_pr_number}` stored in `backfill_jobs.last_checkpoint`.
6. Resume: skip repos before checkpoint repo; within checkpoint repo, start cursor from checkpoint PR.

**Fixture files for local dev:**
- `tests/fixtures/github/` directory contains real (anonymized) REST API responses:
  - `pulls_list_response.json`
  - `pull_request_detail.json`
  - `pull_reviews_response.json`
  - `releases_list_response.json`
- `pytest` fixture `mock_github_rest(fixture_file)` replays REST API responses through the ingestion worker.

---

### 6.2 Jira

**Auth:** API Token + email (Basic Auth, base64 encoded).
```
Authorization: Basic base64("{email}:{api_token}")
```

**Config fields stored in `integrations.config_json`:**
```json
{
  "base_url": "https://yourorg.atlassian.net",
  "email": "admin@yourorg.com",
  "api_token": "<encrypted>",
  "project_keys": ["PLAT", "INFRA"],
  "story_points_field_id": "customfield_10016",
  "board_ids": [1, 2, 3]
}
```

**Story points field resolution:**
1. Admin confirms field ID during setup wizard.
2. System tries `story_points` field first; if null tries `customfield_10016` (Jira default).
3. If still null: display "Not configured" for story point metrics.

**Batch pull sequence (nightly at 01:20 UTC — fetch sprints and issues updated since `yesterday_start_UTC`):**
1. `GET {base_url}/rest/agile/1.0/board?projectKeyOrId={project_key}` — discover boards.
2. `GET {base_url}/rest/agile/1.0/board/{boardId}/sprint?state=active,future,closed` — get sprints.
3. For each sprint: `GET {base_url}/rest/agile/1.0/sprint/{sprintId}/issue?expand=changelog&fields=summary,status,assignee,story_points,customfield_10016,issuetype,created,updated&maxResults=100&updatedAfter={yesterday_start_UTC_ms}` — fetch only issues updated since yesterday.
4. For cycle time: parse `changelog.histories` for status transitions.

**Rate limit (exponential backoff on 429):**
```python
for attempt in range(5):
    response = requests.get(url, ...)
    if response.status_code == 429:
        delay = min(60, (2 ** attempt) * (1 + random.uniform(-0.2, 0.2)))
        time.sleep(delay)
        continue
    break
```

---

### 6.3 ClickUp

**Auth:** Personal API Token.
Header: `Authorization: {token}` (no "Bearer" prefix — ClickUp-specific).

**Config fields:**
```json
{
  "api_token": "<encrypted>",
  "workspace_id": "12345678",
  "sprint_list_ids": ["901234567", "901234568"],
  "story_points_custom_field_name": "Story Points"
}
```

**Setup wizard flow:**
1. Admin connects ClickUp API token.
2. System fetches `GET /api/v2/team/{workspace_id}/space` → `GET /api/v2/space/{space_id}/folder` → `GET /api/v2/folder/{folder_id}/list`.
3. UI displays tree of Spaces → Folders → Lists.
4. Admin selects which Lists represent sprints for each team.
5. Selected List IDs stored as `sprint_list_ids` in config.

**Batch pull sequence (nightly at 01:20 UTC alongside Jira):**
1. For each `sprint_list_id`:
   ```
   GET /api/v2/list/{list_id}/task?include_closed=true&date_updated_gt={yesterday_start_UTC_ms}
   ```
2. For each task: map to `tickets` schema. Look up story points by iterating `custom_fields` array for field with `name == story_points_custom_field_name`.
3. Rate limit: track `X-RateLimit-Remaining` header. If remaining < 20, sleep 1 second between requests. Stay below 80 req/min (20% safety margin below 100 req/min limit).

---

### 6.4 PagerDuty

**Auth:** REST API Key.
Header: `Authorization: Token token={api_key}`

**Config fields:**
```json
{
  "api_key": "<encrypted>",
  "service_ids": ["P123456"],
  "team_ids": ["T789012"]
}
```

**Incident batch pull (nightly at 01:40 UTC):**
```
GET https://api.pagerduty.com/incidents
  ?since={yesterday_start_UTC}
  &until={today_start_UTC}
  &statuses[]=triggered
  &statuses[]=acknowledged
  &statuses[]=resolved
  &service_ids[]={service_id}
  &limit=100
  &offset={offset}
```

**MTTA/MTTR calculation:**
- `mtta_seconds = acknowledged_at - triggered_at` (from incident object timestamps).
- `mttr_seconds = resolved_at - triggered_at`.
- For incidents where `acknowledged_at` is null (auto-resolved without ack): `mtta_seconds = null`.

**On-call schedule sync (once nightly):**
```
GET /oncalls?schedule_ids[]={id}&since={now}&until={now+7d}&include[]=users
```
Upsert `oncall_shifts` for the upcoming 7-day window. No longer polled every 6 hours — one sync per nightly run is sufficient.

**Pagination:** Offset-based. `total` field in response used to determine page count. Page size: 100.

---

### 6.5 Zenduty

**Auth:** Token.
Header: `Authorization: Token {api_key}`

**Base URL:** `https://www.zenduty.com` (configurable via `config_json.base_url` for custom deployments or API version changes).

**Config fields:**
```json
{
  "api_key": "<encrypted>",
  "base_url": "https://www.zenduty.com",
  "team_unique_ids": ["abc123", "def456"]
}
```

**Incident batch pull (nightly at 01:40 UTC):**
```
GET {base_url}/api/account/teams/{team_unique_id}/incidents/
  ?limit=100
  &offset={offset}
  &created_at__gte={yesterday_start_UTC_iso}
```

**MTTA/MTTR — use analytics endpoint:**
```
GET {base_url}/api/account/teams/{team_unique_id}/analytics/
  ?start_date={week_start}
  &end_date={week_end}
```
Response includes `mean_time_to_acknowledge` and `mean_time_to_resolve` as aggregate values. Store per-incident values from the raw incident list where available; fall back to analytics aggregates for team-level display.

**On-call sync (once nightly, token bucket rate limiter):**
```
GET {base_url}/api/account/teams/{team_unique_id}/oncall/
```
Rate: 40 req/min. Token bucket: rate=40, burst=10. Implementation in Section 5.5. On-call syncs once per nightly run — no separate 6h poll.

**Zenduty rebranding note:** As of late 2025, Zenduty is rebranding to "Xurrent IMR". Pin to `apidocs.zenduty.com` documented endpoints. The `base_url` config field allows overriding the domain without a code change. Log a warning if the API returns a `Deprecation` response header.

---

### 6.6 Slack

**Auth:** OAuth 2.0 Bot Token (Bearer).

**Required scopes:**
- `users:read` — fetch user list
- `users:read.email` — fetch user emails for identity resolution
- `channels:read` — list public channels
- `team:read` — fetch workspace info (member count)
- `conversations.history` — read message timestamps (non-degraded workspaces only)

**Install flow:**
1. Admin clicks "Connect Slack" in Admin UI.
2. System redirects to Slack OAuth authorize URL:
   ```
   https://slack.com/oauth/v2/authorize
     ?client_id={CLIENT_ID}
     &scope=users:read,users:read.email,channels:read,team:read,conversations.history
     &redirect_uri={APP_URL}/oauth/slack/callback
   ```
3. Admin approves in Slack.
4. Slack redirects to `/oauth/slack/callback?code={code}`.
5. System exchanges code for bot token:
   ```
   POST https://slack.com/api/oauth.v2.access
     code={code}&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}
   ```
6. Store `access_token` (bot token) in `integrations.config_json` (encrypted).
7. Run degradation check (Section 2.4).

**Note on Slack App Review:** For deployment to external (non-internal) Slack workspaces, `users:read.email` scope requires Slack app review. For self-hosted internal deployments where the Slack app is installed as an "Internal Integration", app directory review is bypassed. Document this as a deployment prerequisite in `docs/deployment/slack-setup.md`.

**Privacy enforcement:**
- In `sync_slack_activity`: process `ts` (timestamp float) from each message object only.
- Do NOT read or store: `text`, `blocks`, `attachments`, `files`, `reactions`, `thread_ts` (beyond timestamp use), `user` display names.
- Immediately after aggregating into `slack_activity_buckets`, discard the raw API response from memory.

**Identity resolution via Slack:**
1. `GET /api/users.list?limit=200&cursor={cursor}`.
2. For each user: extract `profile.email`. Match to `users.email`. Upsert `identity_mappings` with `tool='slack'`.

---

### 6.7 Keka

**Auth:** OAuth 2.0 (API key-based token exchange).

**Config fields:**
```json
{
  "api_key": "<encrypted>",
  "base_url": "https://yourorg.keka.com/api"
}
```

Note: Keka `base_url` is org-specific (differs per customer). Admin must enter during setup.

**Nightly sync flow (02:15 UTC, after Slack sync completes):**
1. Authenticate: `POST {base_url}/token` with `api_key` → receive `access_token`.
2. Paginated fetch:
   ```
   GET {base_url}/v1/hris/employees?page=1&pageSize=50
   ```
3. For each employee: extract `workEmail` (primary key), `manager.workEmail`.
4. Resolve to `user_id` values via `users.email` lookup.
5. In a single transaction: DELETE all `org_nodes`, bulk INSERT new rows with `source='keka'`.

**Rate limit:** Conservative 60 req/min. Retry with exponential backoff on 429:
```python
delay = min(120, 2 ** attempt)
time.sleep(delay + random.uniform(0, 0.3 * delay))
```

**Keka API instability mitigation:**
- Version-pin API calls to `/v1/` path.
- Log any HTTP 4xx/5xx from Keka to structured logs with `integration_type=keka`.
- If Keka sync fails 3 consecutive days: set `integrations.status = 'error'`, show error banner in Admin UI.


---

## 7. Non-Functional Implementation

### 7.1 Auth Implementation

**Password hashing:**
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
```

**JWT implementation:**
```python
from jose import jwt, JWTError
import os

SECRET = os.environ["JWT_SECRET"]  # Must be >= 32 chars, validated at startup
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 86400      # 24 hours
REFRESH_TOKEN_EXPIRE_SECONDS = 2592000   # 30 days

def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "team_id": str(user.team_id) if user.team_id else None,
        "jti": str(uuid4()),
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)
```

**Startup validation:**
```python
@app.on_event("startup")
async def validate_config():
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters")
```

**Refresh token storage:**
```python
# On login: generate refresh token, hash it, store in DB
refresh_token_plain = secrets.token_urlsafe(48)
token_hash = hashlib.sha256(refresh_token_plain.encode()).hexdigest()
db.add(RefreshToken(
    user_id=user.id,
    token_hash=token_hash,
    expires_at=datetime.utcnow() + timedelta(days=30)
))
```

**RBAC FastAPI Depends:**
```python
def require_roles(*roles: str):
    async def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return checker

# Usage:
@router.get("/admin/integrations")
async def list_integrations(user=Depends(require_roles("admin"))):
    ...
```

**Login rate limiting and account lockout:**
- Track failed attempts in Redis: `login_failures:{username}` — INCR with TTL 900 seconds.
- After 5 failures: return 429 with `Retry-After: 900`.

---

### 7.2 Caching Strategy

All Redis cache keys use the pattern: `{namespace}:{identifier}`. TTLs set via `EXPIRE`.

Since data is refreshed once per night and does not change intra-day, API response caches use longer TTLs. Cache is invalidated at 02:45 UTC after nightly metric computation completes.

| Cache Key | TTL | Invalidated By | Content |
|-----------|-----|----------------|---------|
| `overview:{user_id}` | 2 hours | Nightly cache invalidation at 02:45 UTC | Overview tab response |
| `team_score:{team_id}` | 2 hours | Nightly cache invalidation at 02:45 UTC | Team scores + sparkline |
| `engineers:{team_id}` | 4 hours | Nightly cache invalidation or member change | Engineer list with load indicators |
| `user:{user_id}` | 5 min | User record update | User object (id, role, team_id) |
| `slack_rate:{channel_id}` | 60 sec | TTL expiry | Rate limit lock for conversations.history |
| `identity_mismatches` | No TTL | Identity resolver updates | Set of unresolved tool IDs |

Admin endpoints: never cached (always fresh from DB).

Cache-aside pattern:
```python
async def get_team_score(team_id: UUID, redis, db) -> dict:
    key = f"team_score:{team_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    data = await db.fetch_team_score(team_id)
    await redis.setex(key, 7200, json.dumps(data))  # 2 hours
    return data
```

---

### 7.3 Error Handling Conventions

**Ingestion workers — per-record exception isolation:**
```python
for record in batch:
    try:
        process_record(record)
        ingestion_records_processed.labels(integration=integration_type).inc()
    except Exception as e:
        logger.error("record_processing_failed",
            integration_id=str(integration_id),
            record_id=record.get("id"),
            error=str(e),
            exc_info=True)
        ingestion_record_failures.labels(integration=integration_type).inc()
        continue  # Never abort entire batch for one bad record
```

**Celery task retry policy:**
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def sync_github_nightly(self, integration_id: str, nightly_run_id: str):
    ...
```
Retry delays: 60s → 300s → 900s. After 3 failures: task moves to Celery failure state. Admin notification via in-app alert (stored in a `system_alerts` table, visible in Admin UI header).

**Nightly run error handling:**
- If any integration worker (GitHub, Jira/ClickUp, PagerDuty/Zenduty, Slack, Keka) fails after all retries:
  - The `nightly_runs.integrations_completed[integration]` is set to `false`.
  - The `nightly_runs.status` is updated to `partial`.
  - `nightly_runs.error_summary` is populated with the failure message.
  - Metric computation still runs as the chord callback, using the last successful data for failed integrations (i.e. last night's ingested data for that integration is still in PostgreSQL and will be used for scoring).
  - Admin is notified via in-app notification: "Nightly run {date} completed with errors. GitHub sync failed. Other integrations succeeded. Metrics computed using last available data."
  - Admin can re-trigger the failed integration only via `POST /api/v1/admin/nightly-runs/trigger` (full re-run) or via CLI `nightly-run --date`.

**FastAPI exception handlers:**
```python
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    return JSONResponse(status_code=422, content={
        "error": {"code": "VALIDATION_ERROR", "message": str(exc), "details": exc.errors()}
    })

@app.exception_handler(Exception)
async def generic_error_handler(request, exc):
    logger.error("unhandled_exception", error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={
        "error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred."}
    })
```
Stack traces are logged (structured), never returned in HTTP responses in production.

---

### 7.4 Logging

**Library:** `structlog` with JSON renderer in production, ConsoleRenderer in development.

**Configuration:**
```python
import structlog

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer() if os.environ.get("ENV") == "production"
            else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```

**Standard log fields:**
```json
{
  "timestamp": "2026-06-11T09:00:00.000Z",
  "level": "info",
  "service": "github_worker",
  "integration_type": "github",
  "task_id": "celery-task-uuid",
  "user_id": "user-uuid-or-null",
  "duration_ms": 142,
  "event": "pr_ingested",
  "pr_number": 421,
  "team_id": "team-uuid"
}
```

**Log level policy:**
- `DEBUG`: only emitted when `LOG_LEVEL=DEBUG` (local dev). Includes raw API response sizes, cache hit/miss.
- `INFO`: normal operations — ingestion start/complete, metric recompute, digest generated.
- `WARNING`: degraded conditions — rate limit approaching, identity resolution fallback used.
- `ERROR`: any uncaught exception; ingestion record failure; Celery task failure.

**Sensitive data never logged:** API tokens, private keys, JWT secrets, Slack message content, `config_json` values, password hashes.

---

### 7.5 Observability

**Prometheus metrics (via `prometheus-fastapi-instrumentator` + custom):**

```python
from prometheus_client import Counter, Histogram, Gauge

# Ingestion
ingestion_duration = Histogram(
    "ingestion_task_duration_seconds",
    "Duration of ingestion tasks",
    ["integration"]
)
ingestion_records_processed = Counter(
    "ingestion_records_processed_total",
    "Records ingested",
    ["integration"]
)

# Celery queue depth (scraped from Redis)
celery_queue_depth = Gauge(
    "celery_queue_depth",
    "Number of tasks in Celery queue",
    ["queue"]
)

# API (via prometheus-fastapi-instrumentator, auto-instrumented)
# api_request_duration_seconds{endpoint, method, status} histogram

# Digest
digest_send_total = Counter(
    "digest_send_total",
    "Digest email sends",
    ["status"]  # sent, failed
)
```

**Queue depth scraper (runs every 30 seconds):**
```python
@celery_app.task
def scrape_queue_depths():
    for queue in ["q_github", "q_jira_clickup", "q_incidents", "q_slack", "q_keka", "q_digest"]:
        depth = redis_client.llen(queue)
        celery_queue_depth.labels(queue=queue).set(depth)
```

**Grafana dashboards (provisioned via JSON in `monitoring/grafana/dashboards/`):**
- `queue-depth.json` — queue depth per integration, last 1 hour
- `ingestion-latency.json` — p50/p95/p99 per integration
- `api-performance.json` — request latency, error rate by endpoint
- `task-failures.json` — failed tasks per hour by queue
- `digest-delivery.json` — sent/failed digest counts per week

**Prometheus scrape config (in `monitoring/prometheus.yml`):**
```yaml
scrape_configs:
  - job_name: "fastapi"
    static_configs:
      - targets: ["api:8000"]
    metrics_path: "/metrics"
  - job_name: "celery"
    static_configs:
      - targets: ["celery-exporter:9808"]
```

---

### 7.6 Database Migrations

**Library:** Alembic 1.x with `--autogenerate` disabled in production.

**Migration file naming:** `migrations/versions/YYYYMMDD_HHMMSS_<description>.py`
Example: `migrations/versions/20260611_120000_create_core_schema.py`

**TimescaleDB DDL in migrations (raw SQL, not autogenerate):**
```python
def upgrade():
    op.execute("""
        CREATE TABLE slack_activity_buckets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            bucket_hour timestamptz NOT NULL,
            message_count integer NOT NULL DEFAULT 0,
            is_after_hours boolean NOT NULL,
            is_weekend boolean NOT NULL,
            channel_count_distinct integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        SELECT create_hypertable('slack_activity_buckets', 'bucket_hour',
            chunk_time_interval => INTERVAL '1 week')
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_slack_buckets_user_hour
            ON slack_activity_buckets (user_id, bucket_hour)
    """)
```

**Path B (managed PostgreSQL) migration variant:** Each TimescaleDB-specific migration file has a `USE_TIMESCALEDB` environment variable guard:
```python
USE_TIMESCALEDB = os.environ.get("USE_TIMESCALEDB", "true").lower() == "true"

def upgrade():
    if USE_TIMESCALEDB:
        op.execute("SELECT create_hypertable(...)")
    else:
        op.execute("""
            CREATE TABLE team_metric_snapshots (...) 
            PARTITION BY RANGE (snapshot_at)
        """)
        # Create monthly partitions for next 12 months
        for month_offset in range(13):
            ...
```

**Migration rules:**
1. `alembic upgrade head` in production before deployment.
2. All migrations must be reversible (implement `downgrade()`).
3. Never use `create_all()` or `drop_all()`.
4. All index creation uses `CREATE INDEX CONCURRENTLY` for zero-downtime.
5. All column additions use `NOT NULL DEFAULT value` pattern to avoid table rewrites on large tables.

---

### 7.7 Application-Level Encryption

**Integration config_json encryption:**

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64, os

DB_ENCRYPTION_KEY = bytes.fromhex(os.environ["DB_ENCRYPTION_KEY"])
# DB_ENCRYPTION_KEY must be 32 bytes (256 bits), stored as 64-char hex string

def encrypt_config(plaintext: dict) -> str:
    json_bytes = json.dumps(plaintext).encode()
    nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
    aesgcm = AESGCM(DB_ENCRYPTION_KEY)
    ciphertext = aesgcm.encrypt(nonce, json_bytes, None)
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt_config(encrypted: str) -> dict:
    data = base64.b64decode(encrypted)
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(DB_ENCRYPTION_KEY)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext)
```

Key rotation procedure: decrypt all `config_json` values with old key, re-encrypt with new key, update `DB_ENCRYPTION_KEY` env var. Implement as admin CLI command: `python -m engg_intelligence.cli rotate-encryption-key --new-key {hex}`.

---

### 7.8 Environment Variables

All configuration via environment variables. No hardcoded secrets.

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | Yes | `redis://host:6379/0` |
| `JWT_SECRET` | Yes | Min 32 chars |
| `DB_ENCRYPTION_KEY` | Yes | 64-char hex string (32 bytes AES key) |
| `SENDGRID_API_KEY` | No | If not set, falls back to SMTP |
| `SMTP_HOST` | No | SMTP fallback host |
| `SMTP_PORT` | No | Default 587 |
| `SMTP_USER` | No | |
| `SMTP_PASSWORD` | No | |
| `SMTP_FROM_ADDRESS` | No | |
| `APP_URL` | Yes | Base URL for OAuth callbacks and deep links |
| `SLACK_CLIENT_ID` | No | Required for Slack OAuth install |
| `SLACK_CLIENT_SECRET` | No | Required for Slack OAuth install |
| `USE_TIMESCALEDB` | No | Default "true"; set "false" for managed PostgreSQL |
| `LOG_LEVEL` | No | Default "INFO" in production, "DEBUG" in dev |
| `ENV` | Yes | "production" or "development" |
| `CELERY_BROKER_URL` | Yes | Redis URL for Celery broker |
| `CELERY_RESULT_BACKEND` | Yes | Redis URL for Celery results |


## 8. Implementation Order

Every milestone item below is independently testable: it has a defined input, a defined output, and can be verified in isolation before the next item begins. Items within the same milestone prefix (M0, M1, …) are sequenced by dependency; items in different milestones may proceed in parallel if team size allows.

---

### M0 — Foundation (target: ~2 weeks)

#### M0a: Docker-compose setup
**Delivers:** A reproducible local environment containing all runtime dependencies.

Services in `docker-compose.yml`:
- `db`: `timescale/timescaledb:latest-pg16` on port 5432. Volume: `pgdata`.
- `redis`: `redis:7-alpine` on port 6379. Volume: `redisdata`.
- `api`: FastAPI app (placeholder health check only). Depends on `db`, `redis`.
- `worker`: Celery worker (placeholder). Depends on `redis`.
- `beat`: Celery Beat (placeholder schedule). Depends on `redis`.
- `prometheus`: `prom/prometheus:latest`. Scrapes `api:8000/metrics`.
- `grafana`: `grafana/grafana:latest`. Provisioned from `monitoring/grafana/`.

**Test:** `docker-compose up` starts all containers without error. `curl http://localhost:8000/health` returns `{"status":"ok"}`.

Also deliver:
- `.env.example` with all env vars from Section 7.8, values as placeholders.
- `Makefile` with targets: `dev-up`, `dev-down`, `migrate`, `test`, `lint`.

---

#### M0b: Alembic + core schema migrations
**Delivers:** Database schema for all entities defined in Section 3.

Migration files (in order):
1. `20260611_000001_enable_extensions.py` — enable `uuid-ossp`, `pg_trgm`, `pgcrypto` (and `timescaledb` on Path A).
2. `20260611_000002_create_users_teams.py` — `users`, `teams`, `team_memberships`, `org_nodes`.
3. `20260611_000003_create_auth_tables.py` — `refresh_tokens`, `password_reset_tokens`.
4. `20260611_000004_create_integrations.py` — `integrations`, `identity_mappings`.
5. `20260611_000005_create_github_tables.py` — `pull_requests`, `pr_reviews`, `commits`, `github_releases`.
6. `20260611_000006_create_pm_tables.py` — `sprints`, `tickets`, `ticket_state_transitions`.
7. `20260611_000007_create_incident_tables.py` — `incidents`, `incident_assignments`, `oncall_schedules`, `oncall_shifts`.
8. `20260611_000008_create_slack_tables.py` — `slack_activity_buckets` (hypertable on Path A; partitioned table on Path B).
9. `20260611_000009_create_metric_snapshots.py` — `team_metric_snapshots`, `engineer_metric_snapshots` (hypertables / partitioned).
10. `20260611_000010_create_health_config.py` — `team_health_config`.
11. `20260611_000011_create_digest_tables.py` — `digest_runs`, `digest_emails`.
12. `20260611_000012_create_backfill_jobs.py` — `backfill_jobs`.
13. `20260612_000013_create_nightly_runs.py` — `nightly_runs`.

**Test:** `alembic upgrade head` completes with no errors on a fresh database. `alembic downgrade base` then `alembic upgrade head` succeeds (round-trip test).

---

#### M0c: FastAPI skeleton
**Delivers:** Runnable API with health check, structured logging, Prometheus metrics export, and request/response logging middleware.

Files:
- `engg_intelligence/api/main.py` — FastAPI app factory, CORS config (allow origins from `APP_URL`), middleware registration order.
- `engg_intelligence/api/routers/health.py` — `GET /health` returns `{"status":"ok","db":"ok","redis":"ok"}` (pings both dependencies).
- `engg_intelligence/core/logging.py` — structlog configuration (Section 7.4).
- `engg_intelligence/core/db.py` — SQLAlchemy 2.0 async engine + session factory using `DATABASE_URL`.
- `engg_intelligence/core/redis.py` — Redis async client (`redis-py` asyncio).
- `engg_intelligence/api/middleware/logging.py` — request start/end log with `duration_ms`.
- Prometheus instrumentation via `prometheus-fastapi-instrumentator` auto-applied in `main.py`.
- `GET /metrics` Prometheus scrape endpoint.

**Test:** `pytest tests/test_health.py` — health endpoint returns 200 with both `db` and `redis` reporting `ok`. Prometheus `/metrics` endpoint returns `http_request_duration_seconds` metric.

---

#### M0d: Auth — login/logout/refresh endpoints, bcrypt + JWT, RBAC middleware
**Delivers:** Complete authentication system. All protected endpoints return 401 without a valid token.

Files:
- `engg_intelligence/api/routers/auth.py` — all auth endpoints from Section 4.1.
- `engg_intelligence/api/deps.py` — `get_current_user`, `require_roles`, `require_team_access`, `require_self_or_above`.
- `engg_intelligence/api/middleware/auth.py` — JWT decode middleware.
- `engg_intelligence/models/user.py` — SQLAlchemy ORM model.
- `engg_intelligence/services/auth.py` — password hashing, JWT creation, refresh token management.
- `engg_intelligence/cli.py` — initial CLI with `create-admin` command.

**Test:**
- `POST /api/v1/auth/login` with valid credentials → 200 with tokens.
- `POST /api/v1/auth/login` with wrong password → 401.
- 5 consecutive wrong-password attempts → 429 with `Retry-After`.
- `GET /api/v1/auth/me` with valid access token → 200.
- `GET /api/v1/auth/me` with expired token → 401.
- `POST /api/v1/auth/refresh` with valid refresh token → new access token.
- `POST /api/v1/auth/logout` → 204. Subsequent refresh with same token → 401.
- `GET /api/v1/admin/integrations` as engineer role → 403.

---

#### M0e: Admin APIs — user management, team management, org tree CRUD
**Delivers:** All admin CRUD endpoints from Section 4.8. Admin can create users, teams, and configure the org tree.

Files:
- `engg_intelligence/api/routers/admin/users.py`
- `engg_intelligence/api/routers/admin/teams.py`
- `engg_intelligence/api/routers/admin/org_tree.py`
- `engg_intelligence/services/admin.py`

**Test:**
- Admin creates user via `POST /api/v1/admin/users` → 201, user can login.
- Admin creates team, assigns EM → `GET /api/v1/admin/teams/{id}` returns correct EM.
- `PUT /api/v1/admin/org-tree` with 5 nodes → `GET /api/v1/admin/org-tree` returns same 5 nodes.
- Non-admin accessing admin endpoint → 403.

---

#### M0f: Nightly Run Orchestrator — `nightly_runs` table, Celery Beat trigger, chord dispatch, completion tracking
**Delivers:** The core nightly pipeline infrastructure. Celery Beat fires at 01:00 UTC, creates a `nightly_runs` record, dispatches integration tasks as a Celery chord, and tracks completion. Admin can view run history and manually trigger runs.

Files:
- `engg_intelligence/workers/nightly_orchestrator.py` — `run_nightly_batch()` task.
- `engg_intelligence/api/routers/admin/nightly_runs.py` — `GET /api/v1/admin/nightly-runs`, `POST /api/v1/admin/nightly-runs/trigger`.
- `celery_app.py` — updated Beat schedule (replace all integration-specific schedules with single nightly trigger).
- Migration: `20260612_000013_create_nightly_runs.py` — `nightly_runs` table.

**Test:**
- Celery Beat fires `run_nightly_batch` at 01:00 UTC → `nightly_runs` record created with `status='running'`.
- Chord dispatch: all integration task stubs complete → chord callback `run_metric_computation` called.
- `GET /api/v1/admin/nightly-runs` returns most recent runs with correct statuses.
- `POST /api/v1/admin/nightly-runs/trigger` while one is running → 409 conflict.
- One integration task fails → `nightly_runs.status='partial'`, `integrations_completed[integration]=false`.

---

### M1 — GitHub Integration (target: ~3 weeks)

#### M1a: GitHub PAT connect flow + nightly batch ingestion worker (PRs/reviews/commits/releases, incremental since yesterday)
**Delivers:** Admin can connect GitHub via PAT. Nightly batch worker fetches all PRs/reviews/commits/releases updated in the last 24 hours using `?since=yesterday_ISO8601`. PRs, reviews, and commits are persisted.

Files:
- `engg_intelligence/api/routers/admin/integrations.py` — POST/GET/PUT/DELETE integration endpoints.
- `engg_intelligence/workers/github_worker.py` — full implementation of `sync_github_nightly` (PAT auth, incremental since-yesterday fetch).
- `engg_intelligence/services/github_client.py` — REST + GraphQL client with rate limit handling.
- `engg_intelligence/repositories/pull_requests.py` — upsert logic.

**Test:**
- Admin POSTs valid PAT config (`personal_access_token`, `org_name`) → integration created with `status='connected'`.
- Invalid PAT → `POST /api/v1/admin/integrations/{id}/test` returns `{"ok": false}`.
- `sync_github_nightly` with mocked REST API fixture responses → `pull_requests` rows created with correct `cycle_time_seconds`.
- Mock REST API returning `X-RateLimit-Remaining: 150` → worker adds 1s sleep between requests.
- Replay `tests/fixtures/github/pull_reviews_response.json` through worker → `pr_reviews` row created, `first_review_at` updated on PR.

---

#### M1b: GitHub backfill worker
**Delivers:** Admin can trigger a historical backfill via API or CLI. Backfill uses GraphQL pagination and is resumable.

Files:
- `engg_intelligence/workers/github_worker.py` — `backfill_github` task with GraphQL pagination and checkpointing.
- `engg_intelligence/cli.py` — `backfill` and `nightly-run` commands.
- `engg_intelligence/api/routers/admin/integrations.py` — backfill endpoints.

**Test:**
- CLI `backfill --integration github --from 2026-01-01 --to 2026-03-31 --dry-run` prints record count estimate, exits 0 without DB writes.
- Backfill runs for 50 PRs → `backfill_jobs.records_processed = 50`, checkpoint stored.
- Kill worker mid-backfill → restart → backfill resumes from checkpoint, not from scratch.
- `GET /api/v1/admin/integrations/{id}/backfill-status` returns correct `progress_pct`.

---

#### M1c: PR Health metric computation
**Delivers:** Metric computation formulas for PR Health. Called by the nightly chord callback `run_metric_computation`. `recompute_pr_health(team_id)` writes a score to `team_metric_snapshots`.

Files:
- `engg_intelligence/metrics/pr_health.py` — all PR Health metric formulas.
- `engg_intelligence/metrics/engine.py` — dispatcher calling component scorers.
- `engg_intelligence/metrics/scoring.py` — RAG threshold logic, DORA band classification.

**PR Health score formula:**
Each metric maps to a sub-score (0–100) via DORA band thresholds. Sub-scores are averaged with equal weight within the PR Health component:

| Metric | Green (100) | Amber (50) | Red (0) |
|--------|-------------|------------|---------|
| Cycle time p50 | < 24h | 24–72h | > 72h |
| First review latency p50 | < 4h | 4–24h | > 24h |
| Stale PRs | 0 | 1–2 | ≥ 3 |
| Review coverage % | ≥ 90% | 70–90% | < 70% |
| Rework rate % | < 5% | 5–15% | > 15% |

Intermediate values interpolated linearly between thresholds.

**Test:**
- Given 10 merged PRs with cycle time p50 = 18h → PR Health score ≥ 70 (green).
- Given 10 merged PRs with cycle time p50 = 96h + 3 stale PRs → PR Health score < 40 (red).
- `team_metric_snapshots` has a row with `component='pr_health'` and correct `rag`.

---

### M2 — PM Integration (target: ~3 weeks)

#### M2a: Jira integration — connect flow, nightly batch pull, sprint + ticket storage
**Delivers:** Admin connects Jira. Sprints and tickets are ingested nightly at 01:20 UTC, fetching items updated since yesterday.

Files:
- `engg_intelligence/workers/pm_worker.py` — `sync_jira_nightly` task.
- `engg_intelligence/services/jira_client.py` — REST client.
- `engg_intelligence/repositories/sprints.py`, `tickets.py`.

**Test:**
- Admin connects Jira with valid API token → `integrations.status = 'connected'`.
- `sync_jira_nightly` with mocked Jira fixture → sprints and tickets upserted correctly.
- `ticket_state_transitions` rows created for each changelog history entry.
- Jira 429 response → worker retries with exponential backoff, does not crash.

---

#### M2b: ClickUp integration — connect flow + setup wizard, nightly batch pull
**Delivers:** Admin connects ClickUp and maps Lists to sprints via the setup wizard. Tickets are ingested nightly at 01:20 UTC alongside Jira.

Files:
- `engg_intelligence/workers/pm_worker.py` — `sync_clickup_nightly` task.
- `engg_intelligence/services/clickup_client.py` — REST client.
- `engg_intelligence/api/routers/admin/integrations.py` — `GET /api/v1/admin/integrations/clickup/workspace-tree` helper endpoint (returns Space→Folder→List hierarchy for wizard).

**Test:**
- ClickUp workspace-tree endpoint returns hierarchical list with correct List IDs.
- Admin selects 2 Lists → config stored with `sprint_list_ids`.
- `sync_clickup` with mocked ClickUp fixture → tickets upserted with story points resolved from custom field.

---

#### M2c: Sprint Health + Throughput metric computation
**Delivers:** Sprint Health metric formulas. Called by the nightly chord callback. `recompute_sprint_health(team_id)` writes a score.

Files:
- `engg_intelligence/metrics/sprint_health.py`

**Sprint Health score formula (sub-scores averaged with equal weight):**

| Metric | Green (100) | Amber (50) | Red (0) |
|--------|-------------|------------|---------|
| Burndown actual vs ideal % | ≥ 90% | 70–90% | < 70% |
| Scope creep % | < 5% | 5–15% | > 15% |
| Carry-over rate % | < 10% | 10–25% | > 25% |
| Velocity trend (6-sprint delta) | stable or improving | ±10% change | > 10% decline |
| Commitment vs delivery % | ≥ 90% | 75–90% | < 75% |

**Test:**
- Team with 0 scope creep, 5% carry-over, 92% burndown → Sprint Health ≥ 70.
- Team with 20% scope creep, 35% carry-over → Sprint Health < 40.

---

### M3 — Incident Integration (target: ~2 weeks)

#### M3a: PagerDuty integration — connect flow, nightly incident batch pull, nightly on-call sync
**Delivers:** Admin connects PagerDuty. Incidents and on-call shifts ingested nightly at 01:40 UTC.

Files:
- `engg_intelligence/workers/incident_worker.py` — `sync_pagerduty_nightly` task.
- `engg_intelligence/services/pagerduty_client.py`.

**Test:**
- PagerDuty incident with `resolved_at` set → `mtta_seconds` and `mttr_seconds` computed correctly.
- On-call sync creates `oncall_shifts` rows for next 7 days.

---

#### M3b: Zenduty integration — connect flow, nightly batch pull, rate-limited on-call sync
**Delivers:** Admin connects Zenduty. Incidents and on-call shifts ingested nightly at 01:40 UTC with token bucket rate limiting.

Files:
- `engg_intelligence/workers/incident_worker.py` — `sync_zenduty_nightly` task.
- `engg_intelligence/services/zenduty_client.py` — token bucket implementation.

**Test:**
- Token bucket correctly limits to 40 req/min (unit test: simulate 50 rapid calls, verify ≥ 75 seconds elapsed).
- Analytics endpoint MTTA/MTTR values stored when per-incident values absent.

---

#### M3c: Incident Load metric computation
**Delivers:** `recompute_incident_load(team_id)` writes score.

Files:
- `engg_intelligence/metrics/incident_load.py`

**Incident Load score formula:**

| Metric | Green (100) | Amber (50) | Red (0) |
|--------|-------------|------------|---------|
| P1/P2 incidents (30d) | 0 | 1–2 | ≥ 3 |
| MTTR p50 | < 1h | 1–4h | > 4h |
| MTTA p50 | < 5 min | 5–15 min | > 15 min |
| On-call load std deviation (fairness) | low | medium | high |

**Test:**
- Team with 0 P1/P2 incidents, MTTR p50 = 30 min → Incident Load ≥ 80.
- Team with 3 P1 incidents in 30d, MTTR p50 = 5h → Incident Load < 40.

---

### M4 — Core Frontend (target: ~3 weeks)

#### M4a: Composite health score engine with configurable weights
**Delivers:** Composite score computed from all available components. Weights from `team_health_config`. Redistribution when components unavailable.

Files:
- `engg_intelligence/metrics/engine.py` — `recompute_composite`, `compute_composite` (Section 5.8).
- `engg_intelligence/api/routers/admin/teams.py` — weight update endpoint (`PUT /api/v1/admin/teams/{id}/health-config`).

**Test:**
- All 4 components available, default weights → composite = weighted average.
- Slack degraded → composite computed from 3 components with redistributed weights, verified against formula in Section 2.4.
- Weight sum != 1.0 → API returns 400 validation error.
- Non-admin attempting weight update → 403.

---

#### M4b: Overview API + frontend Overview tab
**Delivers:** `GET /api/v1/overview` returns team cards. React Overview tab renders health cards with sparklines, headlines, RAG badges.

Frontend files:
- `frontend/src/pages/Overview.tsx`
- `frontend/src/components/TeamHealthCard.tsx`
- `frontend/src/components/Sparkline.tsx`
- `frontend/src/hooks/useOverview.ts` — TanStack Query hook with 5-minute stale time.

**Test (API):**
- EM calling overview → array of 1 team (own team).
- Director calling overview → all teams.
- Redis cache hit reduces DB query count on second call within 2 hours (nightly cache TTL).

**Test (frontend, Playwright or Vitest component tests):**
- TeamHealthCard renders green badge for score ≥ 70.
- Sparkline renders 7 data points.
- EM sees exactly 1 card; director sees all cards.

---

#### M4c: Teams API + frontend Teams tab with sub-tabs and drill-down
**Delivers:** All Teams API endpoints (Section 4.3). React Teams tab with PR Health / Sprint Health / Incident Load / Slack Signal / Team Members sub-tabs.

Frontend files:
- `frontend/src/pages/Teams.tsx`
- `frontend/src/pages/TeamDetail.tsx`
- `frontend/src/components/PRHealthPanel.tsx`
- `frontend/src/components/SprintHealthPanel.tsx`
- `frontend/src/components/IncidentLoadPanel.tsx`
- `frontend/src/components/SlackSignalPanel.tsx`
- `frontend/src/components/TeamMembersPanel.tsx`

**Test:** Slack degraded integration → SlackSignalPanel shows degradation banner, not a score.

---

### M5 — Engineers + Incidents Tabs (target: ~2 weeks)

#### M5a: Engineers API + frontend Engineers tab + detail page
**Delivers:** All Engineer API endpoints (Section 4.4). Engineers tab with load indicators. Engineer detail page with all 5 sub-tabs.

Frontend files:
- `frontend/src/pages/Engineers.tsx`
- `frontend/src/pages/EngineerDetail.tsx`
- `frontend/src/components/LoadIndicatorBadge.tsx`
- `frontend/src/components/CodeActivityPanel.tsx`
- `frontend/src/components/ReviewActivityPanel.tsx`
- `frontend/src/components/TaskDeliveryPanel.tsx`
- `frontend/src/components/IncidentLoadPanel.tsx` (reused from M4c)
- `frontend/src/components/CollaborationPanel.tsx`

**Privacy test:** Engineer user calling `GET /api/v1/engineers/{other_user_id}` → 403.

---

#### M5b: Incidents API + frontend Incidents tab
**Delivers:** All Incidents API endpoints (Section 4.5). Incidents tab with timeline, on-call fairness view, delivery-correlation chart.

Frontend files:
- `frontend/src/pages/Incidents.tsx`
- `frontend/src/components/IncidentTimeline.tsx`
- `frontend/src/components/OncallFairnessChart.tsx`
- `frontend/src/components/DeliveryCorrelationChart.tsx`

---

### M6 — Slack Integration (target: ~2 weeks)

#### M6a: Slack OAuth install + degradation check
**Delivers:** Admin can install the Slack Bot via OAuth. Degradation check runs on install and marks large workspaces.

Files:
- `engg_intelligence/api/routers/oauth_slack.py` — OAuth flow (`GET /oauth/slack/callback`).
- `engg_intelligence/services/slack_client.py` — OAuth token exchange, degradation check.

**Test:**
- Mock Slack OAuth flow → bot token stored encrypted in `integrations.config_json`.
- Workspace with 250 members → `slack_signal_degraded = true` in config.
- `GET /api/v1/teams/{team_id}/slack-signal` for degraded team → `available: false` with correct message.

---

#### M6b: Slack metadata ingestion + after-hours bucket computation
**Delivers:** Worker polls `conversations.history` for non-degraded workspaces. Message timestamps aggregated into `slack_activity_buckets`.

Files:
- `engg_intelligence/workers/slack_worker.py` — full implementation.
- `engg_intelligence/services/slack_client.py` — paginated history fetch with per-channel rate limiting.

**Privacy test:** Worker processes 100 message events → zero `text` or `blocks` fields stored anywhere in database.

---

#### M6c: Slack Signal metric computation
**Delivers:** `recompute_slack_signal(team_id)` writes score.

Files:
- `engg_intelligence/metrics/slack_signal.py`

**Slack Signal score formula (sub-scores averaged):**

| Metric | Green (100) | Amber (50) | Red (0) |
|--------|-------------|------------|---------|
| After-hours message % (7d) | < 10% | 10–25% | > 25% |
| Weekend message % (7d) | < 5% | 5–15% | > 15% |
| Message volume trend | stable | ±20% | > 20% drop or > 50% spike |

---

### M7 — Weekly Digest (target: ~2 weeks)

#### M7a: Digest generator — MJML templates, Jinja2, role-scoped content
**Delivers:** Sunday 22:00 UTC Celery Beat task creates `digest_runs` snapshot. MJML templates compiled at build time. `generate_and_send_digests` renders HTML per recipient and stores in `digest_emails`.

MJML template content per role:

**Engineer digest** (`em_digest.mjml`): own PR activity (PRs merged, avg cycle time), review participation (PRs reviewed, latency), tickets closed, on-call hours past week.

**EM digest** (`em_digest.mjml`): team composite score + RAG, component scores, top 3 risks (stale PRs, blocked tickets, P1/P2 incidents), DORA snapshot (release frequency, PR lead time, MTTR), 7-day sparkline.

**Director digest** (`director_digest.mjml`): cross-team health table (team name, composite score, RAG, delta from last week), teams in Red, DORA comparison across teams.

Files:
- `engg_intelligence/digest/generator.py`
- `engg_intelligence/digest/renderer.py` — Jinja2 render with role-scoped context builders.
- `engg_intelligence/templates/mjml/*.mjml`
- `engg_intelligence/templates/compiled/*.html` (generated at build)

**Test:**
- Engineer user → digest HTML contains no other engineers' names.
- EM user → digest HTML contains team score, 3 component scores, risk list.
- Director user → digest HTML contains rows for all teams.

---

#### M7b: SendGrid integration + Celery Beat Monday schedule
**Delivers:** Monday 06:00 UTC Celery Beat task sends all generated digests via SendGrid. Delivery status tracked.

Files:
- `engg_intelligence/services/email.py` — SendGrid client + SMTP fallback.
- `engg_intelligence/api/webhooks/sendgrid.py` — delivery event callback handler (`POST /webhooks/sendgrid/events`).

**Test:**
- `SENDGRID_API_KEY` set → digest sent via SendGrid, `sendgrid_message_id` stored.
- `SENDGRID_API_KEY` not set → digest sent via SMTP, `delivery_status` set to `sent` after SMTP handshake.
- SendGrid delivery webhook with `delivered` event → `digest_emails.delivery_status = 'sent'`.
- SendGrid delivery webhook with `bounce` event → retry enqueued.

---

#### M7c: Digests tab frontend
**Delivers:** React Digests tab lists past digests, renders HTML in iframe, shows next digest preview.

Frontend files:
- `frontend/src/pages/Digests.tsx`
- `frontend/src/components/DigestViewer.tsx`

---

### M8 — Identity Resolution + Keka (target: ~2 weeks)

#### M8a: Identity resolver service
**Delivers:** After each ingestion, email-based exact match + pg_trgm fuzzy match resolves tool user IDs to canonical `users` rows. Unresolved entries tracked.

Files:
- `engg_intelligence/identity/resolver.py` (Section 5.9).

**Test:**
- GitHub PR author with email matching `users.email` exactly → `identity_mappings` row with `resolution_method='auto'`.
- GitHub PR author email with 90% trigram similarity → auto-resolved.
- GitHub PR author email with 60% similarity → appears in `GET /api/v1/admin/identity-mismatches`.

---

#### M8b: Admin identity mismatch UI
**Delivers:** Admin UI page listing unresolved identity mappings with candidate users. Admin can manually resolve.

Frontend files:
- `frontend/src/pages/admin/IdentityMappings.tsx`

**Test:**
- Admin resolves mismatch via `PUT /api/v1/admin/identity-mappings/{id}` → mapping created with `resolution_method='manual'`, removed from mismatch list.

---

#### M8c: Keka HRMS daily sync
**Delivers:** Keka OAuth connect flow. Nightly 02:15 UTC sync (part of nightly batch) overwrites `org_nodes` with Keka data.

Files:
- `engg_intelligence/workers/keka_worker.py`.
- `engg_intelligence/services/keka_client.py`.

**Test:**
- Keka sync with 50 employees → `org_nodes` has exactly 50 rows with `source='keka'`.
- Manual `org_nodes` rows present before Keka sync → all deleted and replaced.
- Keka API 3 consecutive failures → `integrations.status = 'error'`, error shown in Admin UI.

---

### M9 — Hardening + Observability (target: ~2 weeks)

Deliverables:
- Kubernetes Helm chart in `helm/engg-intelligence/` with deployments for: `api` (2 replicas), `worker-github` (2 replicas), `worker-pm` (2 replicas), `worker-incidents` (1 replica), `worker-slack` (1 replica), `worker-keka` (1 replica), `worker-digest` (1 replica), `beat` (1 replica — singleton, `spec.replicas: 1` enforced by chart).
- `HorizontalPodAutoscaler` for `api` and `worker-github` (scale on CPU > 70%).
- Helm `values.yaml` with all env vars as Kubernetes Secret refs.
- Grafana dashboard JSON provisioned via ConfigMap.
- `monitoring/grafana/dashboards/*.json` for all 5 dashboards (Section 7.5).
- `monitoring/prometheus.yml` scrape config.
- Load test script (`tests/load/locustfile.py`): 50 concurrent users, 5-minute ramp, targets Overview and Teams endpoints. Success criterion: p95 < 500ms, error rate < 1%.
- Data retention purge task: `DELETE FROM team_metric_snapshots WHERE snapshot_at < now() - interval '12 months'` (and equivalent for other hypertables). Runs daily at 03:00 UTC via Celery Beat.
- `docs/deployment/` directory with:
  - `docker-compose-quickstart.md`
  - `kubernetes-production.md`
  - `slack-setup.md` (Slack App Review prerequisite)
  - `timescaledb-to-vanilla-migration.md`

**Test:** Load test passes success criteria. `alembic upgrade head` on a database with 12 months of seed data completes in < 5 minutes. Grafana dashboard loads with no broken panel queries.


---

## 9. Open Technical Questions

| # | Question | Decision needed by | Recommended approach |
|---|----------|--------------------|----------------------|
| 1 | **TimescaleDB on managed PostgreSQL (RDS, Cloud SQL, Azure DB for PostgreSQL)** — these platforms do not support the TimescaleDB extension. If a customer's infrastructure team mandates a managed PostgreSQL service, the TimescaleDB deployment path is unavailable. | Before M0a | Document two deployment paths as specified in Section 2.1 and Section 7.6. Path A (TimescaleDB Docker): full feature set, hypertables, continuous aggregates. Path B (managed PostgreSQL): vanilla range partitioning, Celery-driven materialized view refresh, no continuous aggregates. Both paths validated in CI with separate `docker-compose.timescale.yml` and `docker-compose.vanilla.yml`. Provide `docs/deployment/timescaledb-to-vanilla-migration.md` at M9. The `USE_TIMESCALEDB` env var gates all DDL differences. |
| 2 | **ClickUp sprint detection** — ClickUp has no native Sprint concept. Teams use Lists, Folders, or custom Sprint fields in varying configurations. Automatic detection is unreliable across organisations. | Before M2b | Require admin to explicitly select sprint containers (Lists) during the ClickUp setup wizard (M2b). The wizard fetches and displays the full Space → Folder → List hierarchy. Admin maps each team to its sprint Lists. Cannot be inferred automatically. If a team has not completed the ClickUp wizard, Sprint Health metrics show "Setup required" instead of a score. |
| 3 | **Zenduty rebranding to "Xurrent IMR"** — Zenduty announced a rebranding in late 2025. API base URL and authentication headers may change. Currently documented API at `apidocs.zenduty.com` may be deprecated. | Before M3b | Pin all Zenduty API calls to the currently documented `apidocs.zenduty.com` endpoints. Add `base_url` override field in `integrations.config_json` so the domain can be updated without a code deploy. Log a `warning` if any Zenduty API response contains a `Deprecation` or `Sunset` header. Monitor `apidocs.zenduty.com` release notes as part of M9 hardening. |
| 4 | **Slack `users:read.email` scope requires Slack app directory review** — for Slack apps distributed to external workspaces, `users:read.email` requires Slack's app review process (which can take weeks). This blocks identity resolution for email-based mapping. | Before M6a | For internal self-hosted deployments: create Slack app as an "Internal Integration" (not listed in Slack App Directory). Internal apps bypass app review. Document this in `docs/deployment/slack-setup.md`. For any customer deploying to workspaces they do not own: initiate Slack app review as a deployment prerequisite. Provide a fallback: if `users:read.email` scope is denied, use `users:read` alone and match Slack display names against `users.username` with pg_trgm (lower accuracy; admin must resolve more mismatches). |
| 5 | **JWT refresh token storage: PostgreSQL vs Redis** — PostgreSQL persists refresh tokens across Redis flushes and restarts; Redis is faster but ephemeral (tokens lost on flush/eviction). | Before M0d | **Decision: PostgreSQL `refresh_tokens` table.** Rationale: a Redis flush (common during maintenance, memory pressure, or misconfiguration) would log out all users simultaneously — unacceptable for a tool used daily by EMs. PostgreSQL provides ACID durability. The added query latency (~1ms) on refresh is acceptable since refresh is an infrequent operation (once per 24 hours per user). Implement a daily Celery task to purge expired/revoked tokens from the table. |
| 6 | **Metric computation trigger** — previously considered event-driven (per-webhook) or hourly. | Before M4a (now M0f) | **Resolved: nightly Celery chord.** Metric computation runs as a chord callback after all nightly integration workers complete (~02:30 UTC). All components for all teams are recomputed in one coordinated pass. No partial per-event recomputation. Freshness SLA: data fresh by 03:00 UTC daily (morning for IST users). Redis cache TTL of 2 hours ensures the API serves nightly-fresh data all day. |
| 7 | **DORA lead time calculation: commit timestamp vs PR merge timestamp** — true DORA "lead time for changes" is (commit → production deployment). Without CI/CD integration (out of scope v1), there is no "production" signal. Two proxy options: (a) PR merge time, or (b) GitHub Release publish time. | Before M1c | **Decision: PR merge time as proxy.** `pr_lead_time = merged_at - first_commit_at`. Label in UI: "PR Lead Time" with tooltip: "Time from first commit in this PR to merge. Not equivalent to DORA Lead Time for Changes, which requires production deployment data." DORA band classification applied to PR Lead Time values using DORA thresholds (Elite < 1h, High 1h–1d, Medium 1–7d, Low > 7d). When CI/CD integration is added in v2, this metric can be recomputed using actual deployment timestamps. |
| 8 | **Data encryption at rest: `integrations.config_json` contains API tokens and OAuth secrets.** Column-level encryption vs application-level encryption. PostgreSQL's `pgcrypto` extension provides `pgp_sym_encrypt`/`pgp_sym_decrypt` but requires key management in SQL queries. Application-level AES-256-GCM is more portable. | Before M0b | **Decision: Application-level AES-256-GCM** using Python's `cryptography` library (Section 7.7). Rationale: the encryption/decryption key (`DB_ENCRYPTION_KEY`) never touches the database, which is the primary threat model. pgcrypto would require passing the key in every SQL query, making it visible in query logs. Application-level encryption keeps the key exclusively in the application process and env var. Key rotation is implemented as a CLI command (`rotate-encryption-key`). |
| 9 | **SendGrid sender domain verification** — SendGrid requires domain verification (DNS TXT/CNAME records) before transactional emails can be sent. This is a deployment prerequisite that the deploying organisation's IT/DNS team must complete. Without it, all digest emails will fail. | Before M7b | Document as a deployment prerequisite in `docs/deployment/docker-compose-quickstart.md` and `docs/deployment/kubernetes-production.md`: "Before enabling the weekly digest, complete SendGrid sender domain verification (DNS records required) or configure SMTP fallback." Provide SMTP fallback (Section 2.7) so self-hosters without SendGrid can still send digests. During M7b testing, validate the SMTP fallback path end-to-end in CI using `mailpit` (local SMTP test server) in `docker-compose.test.yml`. |
| 10 | **GitHub PAT rotation** — GitHub fine-grained PATs expire (maximum 1 year). Classic PATs can be set to no expiry but GitHub now recommends fine-grained tokens with expiry. How does admin rotate the token without disrupting nightly runs? | Before M1a | Store the PAT with an `expires_at` field in `integrations.config_json`. Surface a warning banner in Admin UI 30 days before expiry (daily check at nightly run start). Rotation procedure: admin generates a new PAT in GitHub → pastes into Admin UI via `PUT /api/v1/admin/integrations/{id}` → system immediately tests connectivity with new token → on success, replaces stored token. No downtime: next nightly run picks up the new token. If admin misses the warning and token expires, nightly run fails with `status=partial` and GitHub marked as failed; error banner prompts admin to rotate. |
| 11 | **Nightly run window overlap** — if a nightly run takes longer than expected (large org, many repos, slow APIs), could the next day's run start before the current one completes? | Before M0f | The Nightly Run Orchestrator checks for an active `nightly_runs` record (status='running') at startup. If one exists, it aborts and logs a warning. Maximum expected run time: 02:45 UTC (02:45 - 01:00 = 105 minutes). Data retention purge and other maintenance tasks are scheduled at 04:00 UTC to avoid overlap. If a run is still running at 01:00 UTC the next day, admin is alerted. |

---

## Appendix A: Codebase Directory Structure

```
engg-intelligence/
├── docker-compose.yml
├── docker-compose.test.yml
├── Makefile
├── .env.example
├── pyproject.toml
├── alembic.ini
├── celery_app.py
│
├── migrations/
│   └── versions/
│       ├── 20260611_000001_enable_extensions.py
│       └── ...
│
├── engg_intelligence/
│   ├── __init__.py
│   ├── cli.py
│   ├── api/
│   │   ├── main.py
│   │   ├── deps.py
│   │   ├── middleware/
│   │   │   ├── auth.py
│   │   │   ├── rate_limit.py
│   │   │   └── logging.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── overview.py
│   │   │   ├── teams.py
│   │   │   ├── engineers.py
│   │   │   ├── incidents.py
│   │   │   ├── digests.py
│   │   │   └── admin/
│   │   │       ├── integrations.py
│   │   │       ├── teams.py
│   │   │       ├── users.py
│   │   │       ├── org_tree.py
│   │   │       ├── identity.py
│   │   │       └── nightly_runs.py
│   │   └── webhooks/
│   │       └── sendgrid.py
│   ├── core/
│   │   ├── db.py
│   │   ├── redis.py
│   │   ├── logging.py
│   │   └── config.py
│   ├── models/
│   │   ├── user.py
│   │   ├── team.py
│   │   ├── integration.py
│   │   ├── pull_request.py
│   │   ├── ticket.py
│   │   ├── incident.py
│   │   ├── slack_bucket.py
│   │   ├── metric_snapshot.py
│   │   ├── nightly_run.py
│   │   └── digest.py
│   ├── repositories/
│   │   ├── pull_requests.py
│   │   ├── tickets.py
│   │   ├── incidents.py
│   │   └── ...
│   ├── services/
│   │   ├── auth.py
│   │   ├── email.py
│   │   ├── github_client.py
│   │   ├── jira_client.py
│   │   ├── clickup_client.py
│   │   ├── pagerduty_client.py
│   │   ├── zenduty_client.py
│   │   ├── slack_client.py
│   │   └── keka_client.py
│   ├── workers/
│   │   ├── nightly_orchestrator.py
│   │   ├── github_worker.py
│   │   ├── pm_worker.py
│   │   ├── incident_worker.py
│   │   ├── slack_worker.py
│   │   └── keka_worker.py
│   ├── metrics/
│   │   ├── engine.py
│   │   ├── scoring.py
│   │   ├── pr_health.py
│   │   ├── sprint_health.py
│   │   ├── incident_load.py
│   │   └── slack_signal.py
│   ├── identity/
│   │   └── resolver.py
│   ├── digest/
│   │   ├── generator.py
│   │   └── renderer.py
│   └── templates/
│       ├── mjml/
│       ├── compiled/
│       └── jinja/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── router.tsx
│       ├── api/           (TanStack Query hooks)
│       ├── components/
│       ├── pages/
│       ├── stores/        (Zustand stores)
│       └── types/
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── github/
│   │   │   ├── pull_request_opened.json
│   │   │   ├── pull_request_merged.json
│   │   │   ├── pull_request_review_approved.json
│   │   │   └── release_published.json
│   │   ├── jira/
│   │   ├── clickup/
│   │   ├── pagerduty/
│   │   └── zenduty/
│   ├── unit/
│   ├── integration/
│   └── load/
│       └── locustfile.py
│
├── helm/
│   └── engg-intelligence/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│
└── monitoring/
    ├── prometheus.yml
    └── grafana/
        └── dashboards/
            ├── queue-depth.json
            ├── ingestion-latency.json
            ├── api-performance.json
            ├── task-failures.json
            └── digest-delivery.json
```

---

## Appendix B: Frontend Tech Stack Summary

| Concern | Library | Version | Notes |
|---------|---------|---------|-------|
| Framework | React | 18.x | |
| Build | Vite | 5.x | |
| Language | TypeScript | 5.x | strict mode |
| Routing | React Router | v7 | SPA mode |
| Server state | TanStack Query | v5 | 5-minute stale time default |
| UI state | Zustand | v4 | auth state, sidebar state |
| Styling | Tailwind CSS | v3 | + shadcn/ui components |
| Charts | Recharts | v2 | sparklines, bar charts, area charts |
| HTTP client | Axios | v1 | with request interceptor for JWT attach |
| Testing | Vitest + React Testing Library | | |
| E2E | Playwright | v1 | |

---

## Appendix C: Python Dependencies (key packages)

```toml
[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.30"}
sqlalchemy = {extras = ["asyncio"], version = "^2.0"}
asyncpg = "^0.30"
alembic = "^1.13"
redis = {extras = ["asyncio"], version = "^5.0"}
celery = {extras = ["redis"], version = "^5.4"}
passlib = {extras = ["bcrypt"], version = "^1.7"}
python-jose = {extras = ["cryptography"], version = "^3.3"}
cryptography = "^42"
structlog = "^24"
prometheus-fastapi-instrumentator = "^7"
slowapi = "^0.1"
httpx = "^0.27"
pydantic = "^2.7"
pydantic-settings = "^2.3"
jinja2 = "^3.1"
sendgrid = "^6.11"
mjml = "^0.0"  # MJML Python wrapper for build-time compilation
click = "^8.1"  # CLI framework

[tool.poetry.group.dev.dependencies]
pytest = "^8"
pytest-asyncio = "^0.23"
pytest-cov = "^5"
httpx = "^0.27"  # for FastAPI TestClient async
factory-boy = "^3.3"
faker = "^25"
locust = "^2.29"
playwright = "^1.44"
```

---

*End of Technical Specification — engg-intelligence v1.0*
