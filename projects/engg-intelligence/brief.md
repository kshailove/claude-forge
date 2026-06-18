# Cross-Tool Intelligence Platform for Engineering Teams

## Problem

Engineering managers, directors, and engineers lack a unified view across their
developer tools. They context-switch between GitHub, Jira/Clickup, Slack, and
PagerDuty/Zenduty to understand team health, delivery velocity, and blockers.
Problems are spotted late and there is no single place to answer:
"Is my team healthy, on track, and not burning out? Whats the throughput and velocity of the team? Which engineers are slacking? Which teams or engineers need mentoring, coaching or upskilling in which areas?"

---

## Users & Roles

| Role | Access | Description |
|------|--------|-------------|
| **Admin** | Full access | Configures teams, users, integrations, org tree |
| **Director/VP** | All teams | Oversees 3–10 teams. Weekly usage. Cross-team signals. |
| **Engineering Manager (EM)** | Own team only | Manages 10–15 engineers. Daily usage. |
| **Engineer** | Own profile only | Sees own activity, throughput, and digest |

- Auth: Static credentials (username/password) — no SSO in v1
- Role is assigned by admin during user creation

---

## Org Tree / Hierarchy

- Admin manually configures employee-to-manager reporting structure in-app
- **Keka HRMS integration** (optional): if configured, Keka org tree **overrides**
  the manually configured reporting structure
- Keka scope in v1: org tree only (employee → manager → director hierarchy)
- Future: Keka OOO/leave data for throughput normalization (out of scope v1)

---

## Navigation Architecture (Progressive Disclosure)

### App Shell
```
[ Overview ]  [ Teams ]  [ Engineers ]  [ Incidents ]  [ Digests ]
```

### Level 1 — Overview (Landing Page)
- EM sees: Their team's health card
- Director sees: Grid of all team health cards
- Each card: Composite Health Score (RAG + numeric) + 3 headline numbers
  (Open PRs / Sprint % done / Active incidents) + 7-day sparkline
- Click card → Team detail

### Level 2 — Teams Tab
- List/grid of teams with health scores
- Click team → Team detail page with tabbed sub-sections:
  - PR Health
  - Sprint Health
  - Incident Load
  - Slack Signal
  - Team Members (load indicators, not perf scores)
- Each sub-section shows component score + underlying metrics
- Click a metric → Drill-down (e.g. click "Stale PRs" → list of stale PRs)

### Level 2 — Engineers Tab
- List of engineers (EM sees own team; Director sees all)
- Each row: name, role, composite load indicator, key metrics at a glance
- Click engineer → Engineer detail page:
  - Code Activity (PRs authored, merged, avg cycle time, PR size trend)
  - Review Activity (PRs reviewed, first-review latency, review depth)
  - Task Delivery (tickets closed, cycle time, carry-over count)
  - Incident Load (pages received, personal MTTR avg, on-call hours)
  - Collaboration (who they most often review / are reviewed by)
- Engineers can only see their own profile

### Level 2 — Incidents Tab
- Aggregated across PagerDuty OR Zenduty (company-wide, one tool)
- Timeline view (last 30/60/90 days, selectable)
- Breakdowns: by service, by severity, by team
- On-call load fairness view
- Incident–delivery correlation: did incident spikes precede PR slowdowns?

### Level 2 — Digests Tab
- List of past weekly digests (rendered in-app)
- Preview of next Monday's digest
- Each digest is scoped to the recipient's access entitlement

---

## Health Scoring

### Composite Team Health Score
- Single RAG status (Red/Amber/Green) + numeric score (0–100) per team
- Weighted composite of 4 components:
  1. PR Health score
  2. Sprint Health score
  3. Incident Load score
  4. Slack Signal score
- Drill-down from composite → individual component score → underlying metrics

### DORA Benchmark Bands
- Show where each team falls on DORA Elite/High/Medium/Low bands:
  - Deployment Frequency
  - Lead Time for Changes
  - Change Failure Rate
  - MTTR
- Allows Director to say "we're High performers on Lead Time"

---

## Full Metrics Catalogue

### PR Health
- PR cycle time (open → merge)
- First review latency
- Review turnaround time
- Stale PR count (>3 days without activity)
- PR size distribution
- Review coverage (% PRs with ≥1 review before merge)
- Review participation rate (% engineers who review, not just receive reviews)
- Review depth (avg comments per PR)
- Rework rate (PRs closed without merging)
- Author distribution (bus factor signal)

### Sprint / Delivery Health
- Sprint burndown (actual vs ideal)
- Scope creep % (tickets added mid-sprint)
- Carry-over rate (% tickets not completed)
- Blocked ticket count + aging
- Velocity trend (last 6 sprints)
- Ticket cycle time (opened → done)
- Sprint commitment vs delivery rate
- Estimation accuracy (actual vs estimated)

### Throughput Metrics (per engineer and per team)
- PRs merged per week/sprint
- Tickets closed per week/sprint
- Story points delivered per sprint
- Flow Velocity (flow items completed per sprint)
- Flow Efficiency (active time / total time — blocked vs moving)
- Flow Load (total WIP)
- Flow Distribution (% Features vs Defects vs Tech Debt vs Risks)
- WIP per engineer
- Ticket aging by state (backlog / in-progress / in-review / done)

### Incident Health
- Incident frequency (per week/sprint)
- MTTR (mean time to resolve)
- MTTA (mean time to acknowledge)
- Paging distribution per engineer (fairness signal)
- Repeat incidents by service
- On-call load hours per engineer

### DORA Metrics
- Deployment Frequency
- Lead Time for Changes (commit → production)
- Change Failure Rate (% deploys causing incidents)
- MTTR

### Slack Signal (metadata only — no message content)
- After-hours message frequency (burnout proxy)
- Weekend message frequency
- Response time trends
- Message volume trend (sudden drop = disengagement; spike = firefighting)

### Collaboration & Knowledge Health
- Bus factor (% codebase only one person has touched)
- Knowledge distribution (review gatekeeping signal)
- Cross-team dependency count (tickets blocked on another team)

---

## Weekly Digest

- Sent every Monday via email
- Recipients: EMs, Directors, and individual Engineers
- **Each recipient receives only data they are entitled to see:**
  - Engineer: own activity summary, throughput data
  - EM: own team's health summary, top risks, DORA snapshot
  - Director: cross-team health overview, risk flags, DORA comparison
- Also viewable in-app under the Digests tab (rendered version)

---

## Integrations

| Integration | Purpose | Notes |
|-------------|---------|-------|
| **GitHub** | PRs, commits, review events, branch staleness | Required |
| **Jira OR Clickup** | Sprint data, tickets, blockers, assignees | One tool company-wide (admin selects) |
| **PagerDuty OR Zenduty** | Incidents, severity, MTTR, assignees | One tool company-wide (admin selects) |
| **Slack** | Workspace metadata only (timestamps, response times — no message content) | Required |
| **Keka** | Org tree (employee → manager hierarchy) | Optional; overrides manual org tree if configured |

### Identity Resolution
- Canonical identity key: **email address**
- System matches GitHub username, Jira account, Slack user, PD/Zenduty user,
  Keka employee record by email
- Admin can manually fix identity mismatches in settings

---

## Admin Settings (In-App)

- **Integrations page**: Connect/disconnect each integration, paste API tokens,
  select org/workspace, choose Jira vs Clickup and PD vs Zenduty
- **Team management**: Create teams, add/remove members, assign boards/services
- **User management**: Create user accounts, assign roles, link EMs to teams
- **Org tree**: Configure employee-to-manager hierarchy (if Keka not configured)
- **EM self-service**: EMs can manage their own team's integration settings
  (they cannot access other teams' settings or user management)

---

## Data & Backfill

- **Cold start backfill**: On first connection of any integration, automatically
  pull last 3 months of historical data
- **On-demand backfill script**: Separate CLI script accepting:
  - `--integration` (github / jira / clickup / pagerduty / zenduty / slack)
  - `--from` (date)
  - `--to` (date)
  - `--team` (optional, to scope to a single team)
  - Other relevant parameters as needed
- **Data retention**: 12 months of data retained for all metrics and trends
- **Refresh cadence**: Hourly (not real-time)

---

## Tech Stack

- **Backend**: Python / FastAPI
- **Frontend**: TypeScript / React + Vite
- **Database**: PostgreSQL
- **Background jobs**: Celery + Redis (hourly ingestion, digest generation)
- **Auth**: Static credentials (username/password) — Google SSO deferred
- **Hosting**: Docker + docker-compose (local), Kubernetes (prod)

---

## Out of Scope (v1)

- Mobile app
- Real-time data (hourly refresh is sufficient)
- Individual IC performance scoring (engineer view is load/workload signal only)
- Public API
- Google SSO / OAuth
- Threshold-based alerting (Slack alerts, email alerts beyond Monday digest)
- Keka OOO/leave data for throughput normalization
- GitLab / Bitbucket support
- Multi-tenant / multi-company deployment

---

## Future Considerations

- Keka OOO data → throughput normalization (throughput per engineer adjusted
  for leave days)
- Threshold-based Slack alerts (e.g. "5 PRs stale >3 days → post to #eng-ops")
- Google SSO integration
- Deployment frequency tracking (requires CI/CD integration or GitHub Releases)
- Confluence Integration 
