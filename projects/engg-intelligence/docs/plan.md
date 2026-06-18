# Plan — Cross-Tool Intelligence Platform for Engineering Teams
## Project: engg-intelligence
**Date:** 2026-06-11
**Stage:** Plan (Stage 2)

---

## 1. Project Goals

### Primary Goal

Build a self-hosted engineering intelligence platform that gives engineering managers a single, trustworthy health score per team — updated hourly — by aggregating data from GitHub, Jira/ClickUp, PagerDuty/Zenduty, and Slack, with a weekly digest delivered every Monday.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Time-to-insight for EM | < 3 minutes from login to team health summary | Usability test with 3 EMs |
| Cold-start data backfill | 3-month history available within 24h of first integration connect | QA test run on real org |
| Hourly metric freshness | All metrics updated within 60 min of source event | Automated integration test checking `last_synced_at` timestamp |
| Identity resolution rate | > 90% of engineers auto-resolved across ≥ 2 tools without admin intervention | Measured in setup wizard completion log |
| Digest delivery | Weekly digest sent to all configured recipients by 07:00 UTC every Monday | Email delivery log; 0 missed sends in first 4 weeks |
| Composite health score correlation | EM confirms health score directionally agrees with their qualitative team state in ≥ 80% of weekly reviews | Manual survey at 4-week mark |
| Zero IC performance ranking | No feature ranks individual engineers against each other in v1 | Product review checklist |

---

## 2. Scope

### In Scope (v1)

**Integrations:**
- GitHub (required): PR data via webhooks + REST backfill; GitHub App auth
- Jira (admin selects): sprint and ticket data via REST polling
- ClickUp (admin selects, alternative to Jira): sprint and task data via REST polling
- PagerDuty (admin selects): incident data via REST polling
- Zenduty (admin selects, alternative to PagerDuty): incident data via REST polling
- Slack (required): after-hours and weekend frequency signals via metadata only (timestamps, no content)
- Keka HRMS (optional): org tree override via daily sync

**Auth and roles:**
- Static username/password credentials (bcrypt + JWT)
- Four roles: Admin, Director/VP, Engineering Manager, Engineer
- Role-scoped data access enforced at API layer

**Navigation — 5-tab shell:**
- Overview tab: composite health score (RAG + 0-100) per team, 3 headlines, sparkline per team
- Teams tab: team detail with PR Health / Sprint Health / Incident Load / Slack Signal / Team Members sub-tabs and drill-down
- Engineers tab: per-engineer load indicators; detail page with Code Activity / Review Activity / Task Delivery / Incident Load / Collaboration sub-tabs
- Incidents tab: incident timeline, breakdowns, on-call fairness, incident-delivery correlation view
- Digests tab: past weekly digests and preview

**Health scoring:**
- Composite RAG + numeric (0-100) per team
- Weighted composite of PR Health + Sprint Health + Incident Load + Slack Signal
- Team-configurable weights (schema supports overrides from Day 1; defaults applied at setup)
- DORA benchmark bands: Elite / High / Medium / Low

**Metrics catalogue — full list delivered in v1:**
- PR Health: cycle time, first review latency, review turnaround, stale PRs >3 days, PR size, review coverage, participation rate, review depth, rework rate, author distribution
- Sprint: burndown, scope creep %, carry-over rate, blocked tickets, velocity trend (6 sprints), ticket cycle time, commitment vs. delivery, estimation accuracy
- Throughput: PRs merged/week, tickets closed/week, story points delivered, flow velocity/efficiency/load/distribution, WIP, ticket aging by state
- Incidents: frequency, MTTR, MTTA, paging distribution, repeat incidents, on-call hours per engineer
- DORA: deploy frequency (via GitHub Releases as proxy), lead time, change failure rate, MTTR
- Slack Signal: after-hours message frequency, weekend message frequency, response time trends, volume trend (metadata only; no content)
- Collaboration: bus factor, knowledge distribution, cross-team dependency count

**Data:**
- 3-month backfill on first integration connect
- On-demand CLI backfill script
- 12-month data retention
- Hourly refresh for all integrations except Keka (daily) and Zenduty on-call (every 6 hours)

**Weekly digest:**
- Sent every Monday via email (SendGrid + MJML + Jinja2)
- Role-scoped: Director sees all teams; EM sees own team; Engineer sees own profile
- Also viewable in Digests tab in-app

**Org tree:**
- Manual configuration in-app
- Optional Keka HRMS override (replaces, does not merge with, manual config)

**Infrastructure:**
- docker-compose for local/self-hosted deployment
- Kubernetes + Helm charts for production deployment
- Prometheus + Grafana for operational monitoring

### Out of Scope (v1)

- SSO / OAuth login (no Google, GitHub, or SAML auth — static credentials only)
- GitLab, Bitbucket, Azure DevOps integrations
- Linear, Asana, Monday.com, Shortcut integrations
- Alerting / notifications (Slack alerts, PagerDuty escalations triggered by the platform)
- PR workflow automation (no gitStream-style auto-assignment or routing)
- Individual engineer performance ranking, scoring, or comparison tables
- AI-generated narratives or recommendations (no LLM calls)
- Mobile app or native mobile-responsive design beyond basic viewport support
- Multi-tenancy / SaaS hosting model
- Billing, subscription management, or license enforcement
- Zapier / webhook outbound integrations
- Surveys or qualitative signal collection (no GetDX-style forms)
- Investment allocation categories (no Jellyfish-style business objective mapping)
- CSV/PDF export of reports
- Custom metric builder or formula editor

### Future Scope (v2+)

- SSO (Okta, Google Workspace, SAML)
- GitLab and Bitbucket integrations
- Alerting: configurable thresholds that push Slack or email notifications
- AI-generated weekly narrative summaries (LLM-powered digest text)
- PR workflow automation (auto-assignment, SLA nudges)
- CSV/PDF export
- Custom metric formula editor with weight builder
- Multi-tenancy mode for SaaS deployment
- Linear and Shortcut integrations
- Quarterly/monthly digest cadences
- Mobile-responsive progressive web app

---

## 3. User Personas

### Persona 1: Engineering Manager (Primary — daily user)

**Profile:** Manages 6–15 engineers across 1–2 squads. Tools in daily use: GitHub, Jira or ClickUp, Slack. Occasional PagerDuty.

**Primary jobs-to-be-done:**
- Know within 5 minutes every morning whether the team is on track this sprint, whether PRs are stuck, and whether anyone is showing signs of overload
- Prepare for weekly leadership sync without spending 60–90 minutes aggregating status from 4 tools
- Spot cross-signal patterns (incident spike causing PR slowdown) that are invisible in any single tool

**Frustrations with status quo:** Manual Google Sheets, tool-native dashboards that don't talk to each other, no benchmark for "is this PR cycle time actually bad?"

---

### Persona 2: Director / VP of Engineering (Secondary — weekly user)

**Profile:** Oversees 3–10 squads, 30–100 engineers. Heavy consumer of weekly reporting. Accountable to CTO/CEO on engineering throughput.

**Primary jobs-to-be-done:**
- Get a cross-team health overview in one view without calling a meeting
- Identify which team is in the red before it becomes a skip-level conversation
- Show DORA metrics to leadership without asking engineers to build a custom dashboard

**Frustrations with status quo:** No cross-team view; spends the weekly EM sync hearing status summaries that should be automated.

---

### Persona 3: Engineer (Tertiary — occasional self-service)

**Profile:** IC contributor. 2–8 years experience. Cares about their own throughput, review participation, and not being blindsided by a negative performance conversation.

**Primary jobs-to-be-done:**
- See their own PR cycle times and review participation to calibrate expectations
- Read their own weekly digest to understand their contribution footprint without surveillance anxiety

**Frustrations with status quo:** No self-serve view of their own data; feels like metrics are collected "about them" but not "for them."

---

## 4. Milestones

| Milestone | What it includes | Rough effort |
|-----------|-----------------|--------------|
| M0: Foundation | Docker-compose setup; FastAPI skeleton; PostgreSQL + TimescaleDB schema; Alembic migrations; Celery + Redis wiring; JWT auth with 4 roles; Admin user creation; pipeline-state infra | 2 weeks |
| M1: GitHub Integration | GitHub App install flow; webhook receiver and deduplication; REST backfill for 3 months (PRs, reviews, commits); PR Health metrics computed and stored; CLI backfill script | 3 weeks |
| M2: Project Management Integration | Jira OR ClickUp (admin selects at setup); sprint data ingestion; Sprint Health and Throughput metrics; ClickUp setup wizard for sprint mapping and custom story point field | 3 weeks |
| M3: Incident Integration | PagerDuty OR Zenduty (admin selects); incident data ingestion; MTTR/MTTA calculation; on-call schedule sync (6h cadence for Zenduty); Incident Load metrics | 2 weeks |
| M4: Core Frontend — Overview + Teams | React app scaffold; Overview tab (health score cards, sparklines, 3 headlines); Teams tab with sub-tabs; Composite health score engine with configurable weights; RAG + 0-100 scoring; DORA benchmark bands | 3 weeks |
| M5: Engineers + Incidents tabs | Engineers tab with load indicators and detail page (all sub-tabs); Incidents tab (timeline, on-call fairness, incident-delivery correlation) | 2 weeks |
| M6: Slack Integration | Slack Bot OAuth install; user enumeration for identity resolution; after-hours and weekend frequency computation from message timestamps; graceful degradation for non-Enterprise rate limits | 2 weeks |
| M7: Weekly Digest + Digests Tab | Celery Beat Monday 06:00 UTC task; MJML + Jinja2 email templates; role-scoped digest generation; SendGrid delivery; Digests tab in-app with history and preview | 2 weeks |
| M8: Identity Resolution + Keka | Email-based canonical identity resolution; pg_trgm fuzzy match; admin override UI for mismatches; Keka HRMS optional daily sync for org tree | 2 weeks |
| M9: Hardening + Observability | Prometheus metrics export; Grafana dashboards for queue depth and ingestion latency; Kubernetes Helm charts; load testing; error monitoring; documentation | 2 weeks |

**Total rough estimate: 23 weeks** (~5.5 months) for a single senior full-stack engineer + one backend engineer. With a team of 3 (2 backend, 1 frontend), this compresses to approximately 10–12 weeks.

> Note: These estimates assume no concurrent non-project commitments and that integration spikes (see Section 5) do not surface major blockers. Add 20% buffer for integration API surprises.

---

## 5. Key Decisions

The tech spec stage must explicitly resolve the following decisions before implementation begins:

**Decision 1: TimescaleDB vs. partitioned vanilla PostgreSQL**
- TimescaleDB provides hypertables and continuous aggregates that will significantly improve query performance for the time-series-heavy metrics catalogue (PR cycle time series, hourly snapshots, incident frequency buckets).
- Vanilla PostgreSQL with declarative partitioning is simpler to operate but lacks continuous aggregates.
- Must decide: accept the operational overhead of TimescaleDB (official Helm chart available) for the long-term query benefit, or use vanilla PostgreSQL and accept a query performance ceiling.
- Recommendation from research: TimescaleDB. Spec must confirm the Kubernetes operational story.

**Decision 2: GitHub App vs. Personal Access Token**
- GitHub App is the correct long-term auth model (org-level install, higher rate limits: 15K req/hr, no per-user tokens).
- PAT is faster to implement for v1 but creates a per-user token management problem at scale.
- Spec must decide whether to accept the GitHub App setup complexity in v1 or defer to v2. Research recommends GitHub App for v1.

**Decision 3: DORA deployment frequency proxy**
- GitHub does not expose a single canonical "deployment" event. Three options: (a) GitHub Releases API, (b) push events to the default branch, (c) GitHub Deployment API (requires CI/CD integration).
- A spike against a real GitHub org is required before the spec can commit to an approach.
- Must decide proxy and label it accurately in the UI ("release frequency" if using GitHub Releases, not "deployment frequency").

**Decision 4: Slack Enterprise vs. non-Enterprise graceful degradation**
- Slack's 2025 rate limit change (1 req/min for `conversations.history` on non-Marketplace apps) may make after-hours signal computation infeasible for large non-Enterprise workspaces.
- Spec must define the exact threshold at which the platform disables after-hours signals and what the UI communicates when this happens.
- Must decide: is the Slack Signal component score omitted entirely from the health composite when degraded, or does it fall back to a neutral value?

**Decision 5: Health score composite weight defaults and configurability UX**
- The schema must support per-team weight overrides from Day 1 (not hard-coded defaults that require a migration later).
- Spec must define the default weight distribution (e.g., PR Health 30% + Sprint Health 30% + Incident Load 25% + Slack Signal 15%) and the admin UX for changing them.
- Must decide whether weights are configured per-team by the EM or only by the Admin role.

---

## 6. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Rate limit exhaustion across integrations during 3-month cold-start backfill | High | High | Per-integration Celery queue with throttling middleware; stagger backfill start times across integrations; webhook-first post-backfill eliminates most ongoing REST usage |
| Slack non-Enterprise after-hours signals technically infeasible at scale (2025 rate limit change) | High | Medium | Degrade gracefully with clear UI message; design health score to work without Slack Signal from Day 1; spike against a test workspace before committing to implementation |
| ClickUp sprint model incompatibility (List/Folder structure varies per team's configuration) | Medium | High | Setup wizard that guides admin to map ClickUp Lists to sprint concept; configurable per team; spike with a real ClickUp workspace before M2 build |
| Identity resolution failures (engineers have different emails across GitHub, Jira, Slack) | Medium | High | Email-based canonical key with pg_trgm fuzzy match; admin override UI; log all failures for admin review; identity resolution accuracy measured in QA before launch |
| Engineers perceive the platform as surveillance or performance scoring | High | High | Engineer role sees only own data; no cross-engineer ranking tables anywhere in the product; explicit "load signal, not performance score" copy in UI; privacy statement in onboarding |
| GitHub DORA deployment frequency proxy produces inaccurate or misleading data | Medium | Medium | Spike before spec stage commits to approach; clearly label the proxy method in UI; allow admin to configure which branch/event is the deployment signal |
| Zenduty 40 req/min on-call API causes slow syncs during backfill | High | Low | On-call schedule sync every 6 hours (not hourly); batch requests carefully within the 40 req/min limit; accept that on-call data is slightly stale during initial setup |
| EM distrust of the composite health score formula | Medium | High | Make weights configurable and visible; add a "formula transparency" tooltip in the UI showing the exact weights and inputs for any score |
| Backfill task crashes leave partial data with no recovery path | Low | High | Idempotent Celery tasks with per-record checkpointing in DB; backfill is resumable from last successful record; admin UI shows backfill progress |
| Keka API instability (undocumented limits, branding changes, contract changes) | Medium | Low | Daily sync only (not hourly); version-pin API calls; make Keka optional — product must work without it |

---

## 7. Dependencies & Assumptions

### External Dependencies

- **GitHub** — must have at least one GitHub organisation with admin access to install a GitHub App or generate a PAT. No GitHub, no product (it is the required core integration).
- **SendGrid** — required for weekly digest email delivery. An active SendGrid account with a verified sender domain must be configured before M7 (digest) milestone.
- **Slack** — required integration per brief. Admin must have Slack workspace admin rights to install the Bot OAuth app.
- **Jira or ClickUp** — at least one must be connected for sprint health metrics. Product degrades gracefully without this (sprint-related scores not computed).
- **PagerDuty or Zenduty** — at least one must be connected for incident health metrics. Product degrades gracefully without this.

### Infrastructure Assumptions

- The deployment target for v1 is a single-node docker-compose setup or a Kubernetes cluster with at least 3 nodes (for FastAPI, Celery workers, and database). Minimum 4 vCPUs, 8GB RAM recommended.
- PostgreSQL 16+ is available, with TimescaleDB extension installable (available in the official TimescaleDB Docker image). If a managed PostgreSQL service is used (RDS, Cloud SQL), TimescaleDB is not available on those platforms — vanilla PostgreSQL with partitioning must be used instead. The spec must account for this deployment variant.
- Redis 7+ is available for Celery broker and result backend.
- Outbound internet access from the server to GitHub, Jira, ClickUp, PagerDuty, Zenduty, Slack, and SendGrid APIs is assumed. Airgapped deployments are out of scope for v1.

### Product Assumptions

- The admin setting up the platform has credentials for all configured integrations (GitHub App install rights, Jira API token, ClickUp API token, etc.). The platform does not provide a self-service credential acquisition flow.
- Engineers at the customer organisation primarily use a single consistent email address across all tools (GitHub, Jira/ClickUp, Slack, Keka). Where they do not, an admin must manually resolve the mismatch. Identity resolution accuracy is not guaranteed to be 100% automatic.
- For ClickUp users: the EM or admin can identify which ClickUp Lists or Folders represent sprint-equivalent containers for their team. The platform cannot infer this automatically.
- The customer organisation uses GitHub as their primary code repository. The platform is not designed for GitLab or Bitbucket users in v1.
- Slack usage: the customer's Slack workspace is standard (non-Enterprise Grid). After-hours signals may be limited or degraded depending on workspace size and the 2025 rate limit constraints. This must be communicated clearly in onboarding.
- Weekly digest emails will be sent in English. No i18n in v1.
- The organisation has fewer than 500 engineers. Above this scale, TimescaleDB continuous aggregates and Celery queue design should be re-evaluated.

---

*End of plan.md*
