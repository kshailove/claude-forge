# Research Report — Cross-Tool Intelligence Platform for Engineering Teams
## Project: engg-intelligence
**Date:** 2026-06-11
**Stage:** Research (Stage 1)

---

## 1. Problem Space

### What Problem Is Actually Being Solved?

Engineering leaders — managers, directors, and VPs — operate in information fragmentation. On any given Monday morning, an EM must check GitHub for PR backlogs, Jira/ClickUp for sprint status, PagerDuty/Zenduty for recent incidents, and Slack patterns for team stress signals. Each tool gives a slice of truth; none gives the whole picture. The result:

- **Late detection**: A struggling sprint or a burned-out engineer only surfaces in a 1:1 two weeks after the damage is done.
- **Context-switching tax**: EMs report spending 1–3 hours per week just aggregating status before they can even start thinking.
- **No cross-signal correlation**: An incident spike that causes PR slowdowns a week later is invisible because the two tools don't talk.
- **Gut-feel decisions**: Without benchmarks, EMs can't distinguish "this team is slow" from "this team is in the bottom quartile vs. DORA Elite."

### Who Has This Problem and How Painful Is It?

| Persona | Pain Level | Core Pain |
|---|---|---|
| Engineering Manager (EM) | High — daily | Building a mental model of 10–15 engineers across 4+ tools every morning |
| Director/VP | Medium — weekly | No way to compare team health across 3–10 teams without calling meetings |
| Engineer | Low — periodic | No self-serve view of their own throughput or digest |
| Admin/DevOps | Low — setup only | Integration configuration scattered across tools |

**Market signal:** The DORA/accelerate report, now in its 8th year (2024), has mainstream corporate adoption. Engineering leaders are expected to report DORA metrics to leadership; they need a tool that makes this possible without dedicated data engineering effort.

### What Do Users Currently Do Instead?

- **Custom spreadsheets**: EMs build "team dashboards" in Google Sheets with manual weekly entries. Fragile, not real-time, requires discipline.
- **GitHub Insights / Jira dashboards**: Tool-native dashboards exist but don't cross-reference. Jira doesn't know about GitHub cycle time; GitHub doesn't know about sprint carry-over.
- **Notification overload**: EMs subscribe to Slack notifications from all tools. This is noise, not signal.
- **Third-party tools**: Companies with budget adopt LinearB, Jellyfish, Swarmia, or GetDX — tools this project competes with. Companies without budget build nothing.

---

## 2. Existing Solutions & Competitors

### LinearB
**What it is:** Engineering workflow analytics focused on EMs. Integrates GitHub/GitLab + Jira/Linear + PagerDuty.

**Strengths:**
- gitStream: workflow automation (PR routing, review assignment) — unique differentiation
- PR cycle time, DORA metrics, team-level reports
- Free tier (up to 10 users); paid from ~$12/user/month
- Good EM-focused UX; Slack notifications for blocked PRs

**Weaknesses:**
- No Slack metadata signals (no after-hours/burnout proxy)
- No ClickUp integration (Jira/Linear only)
- No Zenduty support (PagerDuty only)
- No Keka HRMS org tree
- Workflow automation (gitStream) adds complexity; may not be needed by target users
- Not self-hostable; cloud-only SaaS

**Gap this project fills:** Slack metadata, ClickUp, Zenduty, Keka HRMS, self-hosted deployment

---

### Jellyfish
**What it is:** Enterprise engineering intelligence platform focused on investment allocation and executive reporting.

**Strengths:**
- Investment allocation categories (Roadmap / Unplanned / Infrastructure / Support)
- Board-level reporting; ties engineering work to business objectives
- Supports GitHub, Jira, and more

**Weaknesses:**
- Priced at $100K+/year for enterprises — completely inaccessible to the target market
- Complexity overkill for teams < 200 engineers
- Opaque pricing; sales-led
- Not self-hostable
- No ClickUp, no Zenduty, no Keka

**Gap this project fills:** Affordable, self-hostable, Keka org tree, ClickUp/Zenduty support

---

### Swarmia
**What it is:** Team-first engineering analytics prioritising developer buy-in.

**Strengths:**
- Individual data private to the individual by default (engineers trust it)
- Working agreements feature: teams set their own health norms
- Good GitHub + Jira integration
- ~$15–20/dev/month

**Weaknesses:**
- No Slack signal analysis
- No incident management integration
- No ClickUp or Zenduty
- No Keka
- Cloud-only

**Gap this project fills:** Incident health (PagerDuty/Zenduty), Slack signals, ClickUp, Keka, self-hosted

---

### GetDX (DX)
**What it is:** Developer Experience platform with survey-based qualitative data + quantitative metrics.

**Strengths:**
- Combines survey signals with code metrics — richer picture of developer sentiment
- Developer-first focus; high adoption rates reported

**Weaknesses:**
- Survey overhead (friction for adoption)
- Primarily qualitative; quantitative metrics secondary
- Cloud SaaS only; enterprise pricing

**Gap this project fills:** No survey overhead; purely metric-driven; self-hosted option

---

### Waydev
**What it is:** Git analytics focused on code contribution metrics.

**Strengths:**
- Strong Git-level metrics (code churn, focus time, working hours)
- GitHub, GitLab, Bitbucket support

**Weaknesses:**
- IC performance scoring approach — can feel surveillance-like to engineers
- Weak project management integrations
- No incident management
- No Slack signals

**Gap this project fills:** Explicitly avoids IC performance scoring; adds incident + PM integrations

---

### Competitive Gap Summary

| Feature | This Project | LinearB | Jellyfish | Swarmia | GetDX |
|---|---|---|---|---|---|
| ClickUp | Yes | No | No | No | No |
| Zenduty | Yes | No | No | No | No |
| Keka HRMS | Yes | No | No | No | No |
| Slack signals | Yes | No | No | No | No |
| Self-hosted | Yes | No | No | No | No |
| Incident correlation | Yes | Partial | No | No | No |
| Affordable | Yes | Yes | No | Partial | No |
| No IC perf scoring | Yes | No | No | Yes | Yes |

**Unique positioning:** The only platform that supports the Indian/APAC startup tool stack (ClickUp + Zenduty + Keka) and can be self-hosted.

---

## 3. Technology Landscape

### Backend: Python / FastAPI

**Recommended stack (confirmed):**
- **FastAPI 0.115+** (latest stable as of 2026-06): async-first, OpenAPI auto-docs, Pydantic v2 data validation
- **SQLAlchemy 2.x** with async engine (`asyncpg` driver) for PostgreSQL
- **Alembic** for database migrations — must be committed to version control; never use `create_all()` in production
- **Pydantic v2** for request/response validation and data contracts
- **python-jose** or **PyJWT** for JWT token management (static auth v1)
- **passlib + bcrypt** for password hashing
- **httpx** (async HTTP client) for all outbound API calls — never `requests` in async context

**Rationale:** FastAPI + asyncpg + SQLAlchemy 2.x is the 2025 standard for high-throughput Python APIs. Async is critical for an ingestion service that fans out to 5+ external APIs concurrently.

---

### Background Jobs: Celery + Redis

**Recommended:**
- **Celery 5.4+** with Redis broker and Redis result backend
- **celery-beat** for hourly scheduling (run as isolated service — never co-process with workers)
- **Flower** for real-time worker monitoring dashboard
- **django-celery-beat** pattern: store schedules in PostgreSQL so they survive restarts and can be managed via admin UI

**Architecture pattern:**
```
FastAPI → Redis (broker) → Celery Workers (ingestion per integration) → PostgreSQL
celery-beat → per-integration hourly sync tasks
```

**Queue design:** Use separate Celery queues per integration type (`q_github`, `q_jira`, `q_pagerduty`, etc.) to prevent one slow integration from blocking others.

**Gotcha:** Never run `celery beat` inside the same process as a worker. Restart policies and health checks must be separate.

---

### Database: PostgreSQL

**Recommended extensions:**
- **TimescaleDB** extension for time-series metric snapshots (hypertables for PR cycle time series, incident frequency, etc.). Delivers 100x faster inserts than vanilla PostgreSQL for time-series; continuous aggregates for pre-computed team-level stats.
- Standard PostgreSQL for entity storage (users, teams, integrations config, digests)
- **pg_trgm** extension for fuzzy identity matching (email-based cross-tool user resolution)

**Decision to make in planning stage:** TimescaleDB vs. partitioned vanilla PostgreSQL. TimescaleDB adds operational complexity (it's a PostgreSQL extension, not a separate service) but provides significant query performance benefits for the time-series heavy metrics catalogue. For a v1 with hourly refresh (not real-time), partitioned vanilla PostgreSQL is viable but TimescaleDB is the safer long-term bet.

---

### Frontend: TypeScript / React + Vite

**Recommended stack:**
- **React 19** + **Vite 6** (fast dev build, ESM-native)
- **TanStack Query v5** (React Query) for server-state data fetching, caching, and background revalidation. Reduces re-renders by ~70% in dashboard applications vs custom solutions.
- **Zustand** for lightweight client-state (selected team, date range filter)
- **Recharts v3** (~150kB bundle) for charts. SVG-based, declarative React API, widely adopted (3.6M weekly downloads), composable. Alternative: **Tremor** for pre-styled chart components that pair with shadcn/ui aesthetics.
- **shadcn/ui + Tailwind CSS** for UI components — copy-paste, no runtime dependency
- **React Router v7** for client-side routing
- **TypeScript strict mode** throughout

**Charting decision:** Recharts for custom metric charts (sparklines, burndown, scatter plots); Tremor for dashboard cards (pre-styled KPI cards, bar lists). Using both is common and adds minimal bundle overhead.

**Avoid:** D3.js directly — high complexity for a primarily data display use case. The libraries above wrap D3 internals while providing a React-native API.

---

### Email Delivery

- **SendGrid** (or **Amazon SES** for cost at scale) for transactional email
- **MJML** for responsive email templates — compiles to cross-client HTML; abstracts email client compatibility
- Weekly digests generated by a Celery Beat task every Monday 06:00 UTC; rendered as MJML → HTML before delivery
- **Jinja2** for template variable injection (role-scoped digest content)

---

### Auth (v1: Static Credentials)

- **bcrypt** password hashing with work factor ≥12
- **JWT** (HS256) tokens with 24-hour expiry; refresh tokens optional but recommended
- Middleware-based RBAC: role stored in JWT claim; FastAPI `Depends()` decorators enforce per-endpoint access
- Static credentials pattern is simple; the main gotcha is password reset flow (needs email delivery from Day 1, not deferred)

---

### Infrastructure

- **Docker + docker-compose**: services are FastAPI, Celery workers (per integration), Celery Beat, PostgreSQL, Redis, Flower
- **Kubernetes (prod)**: Helm charts for each service; HPA for Celery workers based on Redis queue depth
- **Prometheus + Grafana**: metrics exporter for queue depth, ingestion latency, task failure rate

---

## 4. Integration Landscape

### GitHub

**Auth model:** GitHub App (preferred over PAT) — install once per org, no per-user tokens needed. App-level API access.

**Rate limits:**
- Authenticated (GitHub App): 15,000 requests/hour per installation (for Enterprise Cloud orgs)
- Standard PAT/OAuth: 5,000 requests/hour per token
- Secondary: max 100 concurrent requests; 900 points/minute for REST

**Strategy:** Use **webhooks** as the primary data delivery mechanism for `pull_request`, `pull_request_review`, `push`, and `deployment` events. Webhooks do not consume rate limits. REST/GraphQL API for historical backfill (3-month cold start) and gap-filling.

**GraphQL vs REST for GitHub:** GraphQL is 45% faster and uses 67% less bandwidth for complex queries (e.g., fetching PR + reviews + comments in one call). Use GraphQL for the cold-start backfill; REST for webhook payloads (already structured).

**Key endpoints:**
- `GET /repos/{owner}/{repo}/pulls` — list PRs
- `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` — review events
- `GET /repos/{owner}/{repo}/pulls/{pull_number}/commits` — commits (for cycle time)
- `POST /repos/{owner}/{repo}/hooks` — register webhook

**Gotchas:**
- PRs don't expose deployment events natively; DORA "deployment frequency" requires GitHub Releases or a CI/CD pipeline event (scope this carefully in spec stage)
- Large orgs can have hundreds of repos; webhook registration must iterate repos or use org-level webhook
- `X-GitHub-Delivery` header uniquely identifies each webhook payload — store it for deduplication

---

### Jira

**Auth model:** Atlassian API Token (Basic Auth with email + token) or OAuth 2.0 (3LO). API token is simpler for v1 admin-paste flow.

**Rate limits (Jira Cloud):** Points-based model. Write operations = 1 point each. New enforcement (March 2026) applies to Forge/Connect/OAuth apps; API token-based traffic governed by existing burst limits. Burst limit: typically 500 requests per burst; sustained rate enforced per tier. Expect and handle HTTP 429 with exponential backoff.

**Key endpoints (REST API v3):**
- `GET /rest/agile/1.0/board/{boardId}/sprint` — list sprints
- `GET /rest/agile/1.0/sprint/{sprintId}/issue` — sprint issues
- `GET /rest/api/3/search?jql=...` — issue search (JQL)
- `GET /rest/api/3/issue/{issueKey}/changelog` — status transition history (for ticket cycle time)

**Gotchas:**
- Velocity Report data is NOT available via a supported public API endpoint. You must calculate velocity by summing story points across sprint issues — this can differ from Jira's own velocity chart due to mid-sprint edits.
- `story_points` field name varies by Jira configuration (`story_points`, `customfield_10016`, or others). Admin must confirm the custom field ID at setup.
- Jira Cloud vs. Jira Server/Data Center have different API base URLs and auth models. v1 should target Jira Cloud only.

---

### ClickUp

**Auth model:** Personal API Token (header `Authorization: <token>` — no "Bearer" prefix) or OAuth 2.0.

**Rate limits:** 100 requests/minute per token (documented); observed ~900/min in practice. Response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp).

**Key endpoints:**
- `GET /api/v2/team/{team_id}/space` — list spaces
- `GET /api/v2/space/{space_id}/folder` — list folders
- `GET /api/v2/list/{list_id}/task` — list tasks with assignees, status, dates
- `GET /api/v2/task/{task_id}` — task detail with custom fields
- ClickUp calls "Sprints" by the feature name "Sprint Folder" — data model differs from Jira's native sprint concept

**Gotchas:**
- ClickUp's data model is Workspace → Space → Folder → List → Task. Sprint maps to a List (or a tag). The admin needs to configure which List(s) represent a sprint.
- No native "story points" field — teams use a custom field. Admin must configure the field name at setup.
- Webhooks are available but require list/task-level subscription; org-level webhooks not supported.

---

### PagerDuty

**Auth model:** REST API Key (account-level or user-level). Header: `Authorization: Token token=<key>`.

**Rate limits:** 960 requests/minute per API key. 960 requests/minute per user across all their keys. Using a registered App token in combination with a user key effectively doubles the limit.

**Key endpoints:**
- `GET /incidents` — list incidents with filters (date range, service, severity)
- `GET /schedules` — on-call schedules
- `GET /oncalls` — current on-call assignments
- `GET /log_entries` — incident timeline events (used to calculate MTTA/MTTR)
- `GET /services` — service catalogue

**Gotchas:**
- MTTR must be calculated from `log_entries` (triggered → acknowledged → resolved timestamps); it is not a first-class field on the incident object.
- On-call "hours" calculation requires fetching schedule overrides and computing actual on-call windows per engineer — complex pagination.
- PagerDuty uses cursor-based pagination (`more: true` + `offset`).

---

### Zenduty

**Auth model:** Token-based. Header: `Authorization: Token <api_key>`. Keys generated via account settings.

**Rate limits:**
- General API: ~100 requests/minute (alert API limit)
- Incidents triggered: ~60/minute
- On-Call GET API: **40 calls/minute** (significantly tighter than PagerDuty)

**Key endpoints:**
- `GET /api/account/teams/{team_unique_id}/incidents/` — list incidents
- `GET /api/account/teams/{team_unique_id}/schedules/` — on-call schedules
- `GET /api/account/teams/{team_unique_id}/oncall/` — current on-call
- `GET /api/account/teams/{team_unique_id}/analytics/` — MTTA/MTTR aggregates (native endpoint — reduces calculation burden)

**Gotchas:**
- Zenduty's On-Call API is **40 req/min** — the most constrained of all integrations. The sync worker for Zenduty must be the most conservative about polling.
- API-Integration type (legacy) was deprecated May 2025; use Generic Integration instead.
- Zenduty was recently rebranded as "Xurrent IMR" — API base URL and docs may update. Pin to `apidocs.zenduty.com` and monitor for changes.
- MTTA/MTTR available as aggregate via the analytics endpoint — prefer this over calculating from raw log entries.

---

### Slack

**Auth model:** OAuth 2.0 with Bot Token (`xoxb-...`). Scopes required: `users:read`, `users:read.email` (separate scope from `users:read`!), `channels:read`, `team:read`.

**Critical 2025 rate limit change:** As of May 29, 2025, non-Marketplace apps have new rate limits on `conversations.history` and `conversations.replies`:
- **15 messages per request**
- **1 request per minute** for these methods

Since this project uses **metadata only** (timestamps, not message content), the relevant methods are:
- `users.list` — enumerate workspace members (Tier 2: ~20 req/min)
- `users.info` — user profile including email (Tier 4: ~100 req/min)
- `conversations.list` — channel list (Tier 2)
- `admin.analytics.messages.metadata` — **Enterprise Grid only** — returns structural metadata without content

**Important scope decision:** Without `conversations.history`, after-hours frequency signals cannot be derived from the standard Bot Token. For non-Enterprise Slack workspaces, the after-hours and weekend frequency metrics require reading message timestamps from `conversations.history`. This directly conflicts with the 2025 rate limit change.

**Recommended approach:**
1. For **Enterprise Slack**: Use `admin.analytics.messages.metadata` — returns timestamps without content, fully GDPR-compliant.
2. For **standard Slack (non-Enterprise)**: Use `conversations.history` with strict rate-limit management and exponential backoff. Pull only timestamps, discard content immediately. Cache heavily.
3. Slack signal freshness will be lower than other integrations — accept 6-hour staleness for Slack signals vs. 1-hour for others.

**Gotchas:**
- `users:read.email` is a **separate OAuth scope** from `users:read` — must be explicitly requested or email is silently absent from all user objects (breaks identity resolution).
- Workspace event delivery: 30,000 deliveries/workspace/hour via Events API.
- Message volume spikes require timestamp bucketing on ingest — do not store raw message timestamps at scale.

---

### Keka HRMS

**Auth model:** OAuth 2.0. API key generated from developer portal. Pagination default: 100 records per page.

**Key endpoints:**
- `GET /api/v1/hris/employees` — employee list with manager relationships
- `GET /api/v1/hris/org-chart` — hierarchical org structure
- Employee object includes: `employee_id`, `email`, `manager_email`, `department`, `designation`

**Rate limits:** Not publicly documented. Treat conservatively: max 60 requests/minute, implement exponential backoff on 429.

**Sync strategy:** Keka org tree changes infrequently (daily max). Sync daily (not hourly) — schedule a daily Celery Beat task separate from the hourly metric sync.

**Gotchas:**
- Keka API availability: Keka is an Indian HRMS product. Documentation at `apidocs.keka.com` is less comprehensive than Western equivalents. Treat API contracts as less stable; version-pin API calls.
- The `email` field is the identity resolution key — confirm it matches the primary email used in GitHub/Slack/Jira.
- If Keka is configured, the system must **replace** the manually-configured org tree, not merge. This is a data migration concern at setup.

---

## 5. Risks & Unknowns

### Technical Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Rate limit exhaustion across 5+ integrations during cold-start backfill | High | High | Per-integration queue with throttling; stagger backfill across days; use webhooks post-backfill |
| Identity resolution failures (same person has different emails across tools) | High | Medium | Admin UI for manual override; fuzzy matching via pg_trgm; log all resolution failures |
| Slack rate limit change (2025) making after-hours signals infeasible on non-Enterprise | Medium | High | Degrade gracefully — show "Slack signal not available" for non-Enterprise; document requirement |
| ClickUp sprint model incompatibility | Medium | Medium | Add setup wizard that maps ClickUp Lists/Folders to sprint concept; make configurable per team |
| GitHub deployment frequency calculation without CI/CD integration | Medium | Medium | Use GitHub Releases as proxy; clearly label as "release frequency" not "deploy frequency" in v1 |
| Celery worker crashes during 3-month backfill causing partial data | Medium | Low | Idempotent tasks with per-record checkpointing in DB; backfill is resumable |
| Zenduty 40 req/min on-call API causing slow syncs | Low | High | Cache on-call schedule; sync on-call assignments every 6 hours (not hourly) |
| TimescaleDB extension management complexity in Kubernetes | Low | Low | TimescaleDB has official Helm charts; use managed cloud option (Timescale Cloud) if self-hosting Kubernetes |

### Product Risks

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Engineers perceive the platform as surveillance / performance scoring | High | High | Strictly scoped access (engineer sees only own data); no IC ranking tables; explicit callout in UX: "load signal, not performance score" |
| EMs don't trust the health score formula | Medium | Medium | Make scoring weights configurable per team; show formula transparency in UI |
| Low adoption because ingestion takes too long (cold start) | Medium | Medium | Show partial data as it arrives; progress indicator for backfill; webhook data appears within minutes |
| Digest emails ignored (noise) | Low | Medium | Make digest opt-in per section; let EM customise what appears in their team digest |

### What Needs a Spike or Prototype

1. **GitHub DORA: deployment frequency** — spike required to determine which GitHub event best proxies a "deployment". Options: GitHub Releases, branch push to `main`, GitHub Deployment API events. Run a spike against a real org before committing in spec stage.
2. **Slack after-hours signals for non-Enterprise** — spike against a test workspace to validate that `conversations.history` timestamps can be fetched within the new rate limits for a typical 50-person workspace. If infeasible, the Slack Signal component score must be excluded or degraded.
3. **ClickUp sprint configuration** — spike with a real ClickUp workspace to map the List/Folder structure to sprint semantics and confirm story point custom fields are accessible via API.
4. **Identity resolution accuracy** — test against a real multi-tool setup (GitHub + Jira + Slack) with a known set of users. Measure what percentage resolve automatically vs. require admin intervention.

---

## 6. Recommended Direction

### Opinionated Recommendation

**Build a read-only, metric-aggregation platform** — not a workflow automation tool. The product's value is in the unified view and weekly digest, not in automating PR routing (that is LinearB's territory). Stay firmly in "observe and understand" rather than "act".

**Technology stack (confirmed):**
- Backend: FastAPI + SQLAlchemy 2 (async) + Alembic + Celery + Redis
- Frontend: React 19 + Vite + TanStack Query + Recharts + shadcn/ui
- Database: PostgreSQL with TimescaleDB extension (evaluate in spec stage; vanilla PG is fallback)
- Email: SendGrid + MJML + Jinja2
- Infrastructure: docker-compose for local; Kubernetes + Helm for prod

**Integration priority order:**
1. GitHub (webhooks first; REST for backfill) — highest data density, fastest ROI
2. Jira OR ClickUp (admin selects at setup) — sprint data is core to health score
3. PagerDuty OR Zenduty (admin selects at setup) — incident load is a key health signal
4. Slack — implement last; most constrained by rate limits; treat as optional enhancement
5. Keka — daily sync; lowest priority; optional feature

**Key architectural decisions for the planning stage:**

1. **TimescaleDB vs. partitioned vanilla PostgreSQL** — recommend TimescaleDB; spec stage should confirm operational readiness.
2. **GitHub App vs. PAT** — recommend GitHub App for production; PAT acceptable for v1 MVP to reduce setup complexity.
3. **Webhook-first vs. polling-first for GitHub** — recommend webhook-first for hourly refresh; REST API polling as fallback/gap-fill.
4. **How to handle Slack Enterprise vs. non-Enterprise** — recommend designing for non-Enterprise (standard workspaces) as the target market, with a graceful fallback that disables after-hours signals when rate limits prevent feasibility.
5. **DORA deployment frequency proxy** — spec stage must decide: GitHub Releases, main branch push, or GitHub Deployment API events. This requires a spike.
6. **Health score formula** — weights must be configurable per team from Day 1; hard-coding defaults is acceptable but the schema must support team-level weight overrides.

### Summary

**Build the APAC-first, self-hosted engineering intelligence platform** with full support for ClickUp, Zenduty, and Keka — the tool stack that LinearB/Jellyfish/Swarmia all miss. Lead with a precise, interpretable health score and weekly digest. Defer all workflow automation, alerting, and IC performance scoring to future versions.

---

*Sources consulted:*
- [GitHub REST API Rate Limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- [Jira Cloud Rate Limiting](https://developer.atlassian.com/cloud/jira/platform/rate-limiting/)
- [ClickUp API Rate Limits](https://developer.clickup.com/docs/rate-limits)
- [PagerDuty REST API Rate Limits](https://support.pagerduty.com/main/docs/rest-api-rate-limits)
- [Zenduty Rate Limits](https://zenduty.com/docs/rate-limits/)
- [Slack API Rate Limits 2025 changes](https://api.slack.com/changelog/2025-05-terms-rate-limit-update-and-faq)
- [Keka API Documentation](https://apidocs.keka.com/)
- [Jellyfish vs LinearB vs Swarmia Comparison](https://codepulsehq.com/guides/engineering-analytics-tools-comparison)
- [Recharts v3 vs Tremor vs Nivo 2026](https://www.pkgpulse.com/guides/recharts-v3-vs-tremor-vs-nivo-react-charting-2026)
- [TanStack Query best practices](https://rtcamp.com/handbook/react-best-practices/data-loading/)
- [FastAPI Celery Redis architecture 2025](https://medium.com/@dewasheesh.rana/celery-redis-fastapi-the-ultimate-2025-production-guide-broker-vs-backend-explained-5b84ef508fa7)
- [TimescaleDB Python integration](https://github.com/jmitchel3/timescaledb-python)
- [Alembic + FastAPI + PostgreSQL best practices](https://medium.com/@vamshimohan.b/alembic-for-fastapi-and-sqlalchemy-the-complete-guide-to-database-migrations-with-real-examples-c4b167d8b2bd)
- [Slack metadata privacy compliance](https://www.worklytics.co/resources/how-to-track-slack-activity-without-reading-messages-gdpr-compliant-employee-monitoring)
- [DORA metrics calculation guide](https://www.aviator.co/blog/how-to-calculate-dora-metrics/)
