# engg-intelligence — Product Requirements Document

**Version:** 1.0
**Status:** Draft
**Last updated:** 2026-06-11
**Authors:** ClaudeForge PRD Agent
**Approved by:** —

---

## Table of Contents

1. [Overview](#1-overview)
2. [Users](#2-users)
3. [Goals & Non-Goals](#3-goals--non-goals)
4. [Features](#4-features)
5. [User Flows](#5-user-flows)
6. [Data Requirements](#6-data-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [Open Questions](#8-open-questions)

---

## 1. Overview

### Problem Statement

Engineering managers, directors, and engineers lack a unified view across GitHub, Jira/ClickUp, Slack, and PagerDuty/Zenduty. Context-switching across 4+ tools daily prevents early detection of team health problems — stalled sprints, PR backlogs, and engineer overload surface only after damage is done. No single tool answers: "Is my team healthy, on track, and not burning out?"

### Solution Summary

A self-hosted engineering intelligence platform that aggregates data from all developer tools into a single hourly-refreshed health score per team, with a five-tab navigation shell (Overview, Teams, Engineers, Incidents, Digests) and a role-scoped weekly email digest. The platform is read-only and observational — it does not automate workflows, rank individual contributors, or replace any existing tool.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Time-to-insight for EM | < 3 minutes from login to team health summary | Usability test with 3 EMs |
| Cold-start backfill | 3-month history available within 24 hours of first integration connect | QA test run on real org |
| Hourly metric freshness | All metrics updated within 60 minutes of source event | Automated integration test checking `last_synced_at` timestamp |
| Identity resolution rate | > 90% of engineers auto-resolved across 2 or more tools without admin intervention | Setup wizard completion log |
| Digest delivery | Weekly digest sent to all configured recipients by 07:00 UTC every Monday | Email delivery log; 0 missed sends in first 4 weeks |
| Health score correlation | EM confirms health score directionally agrees with qualitative team state in 80% or more of weekly reviews | Manual survey at 4-week mark |
| Zero IC ranking | No feature ranks individual engineers against each other | Product review checklist before release |

---

## 2. Users

### Persona 1 — Engineering Manager (EM)

| Attribute | Detail |
|-----------|--------|
| **Role** | Manages 6–15 engineers across 1–2 squads. Primary daily user. |
| **Goals** | Know within 5 minutes every morning whether the team is on track; spot cross-signal patterns (e.g. incident spike causing PR slowdown); prepare for weekly leadership sync without manually aggregating data from 4 tools. |
| **Pain points** | Spends 1–3 hours per week building a status picture from GitHub, Jira/ClickUp, PagerDuty, and Slack; no benchmark for "is this PR cycle time actually bad?"; problems surface in 1:1s two weeks after the damage is done. |
| **Key actions** | View Overview tab daily; drill into team sub-tabs when a metric is amber/red; review digest every Monday; manage own team's integration settings; check engineer load indicators to spot overload. |
| **Data access** | Own team only. Cannot see other teams or other engineers. |

### Persona 2 — Director / VP of Engineering

| Attribute | Detail |
|-----------|--------|
| **Role** | Oversees 3–10 squads, 30–100 engineers. Secondary weekly user. Accountable to CTO/CEO on engineering throughput. |
| **Goals** | Get a cross-team health overview in one view without calling a meeting; identify which team is in the red before it becomes a skip-level conversation; present DORA metrics to leadership without requesting a custom dashboard build. |
| **Pain points** | No cross-team view today; weekly EM sync is spent hearing status summaries that should be automated; DORA metrics require manual calculation or dedicated data engineering. |
| **Key actions** | Review Overview grid on Mondays; compare DORA benchmark bands across teams; read weekly digest; drill into a specific team when health score drops. |
| **Data access** | All teams and all engineers. |

### Persona 3 — Engineer

| Attribute | Detail |
|-----------|--------|
| **Role** | Individual contributor. 2–8 years experience. Tertiary, self-service user. |
| **Goals** | See own PR cycle times and review participation to calibrate expectations; read own weekly digest to understand contribution footprint; avoid being blindsided by a negative performance conversation. |
| **Pain points** | No self-serve view of own data today; metrics feel like surveillance "about them" rather than insight "for them"; no way to benchmark own output. |
| **Key actions** | View own engineer detail page; read weekly digest email; view own Digests tab history. |
| **Data access** | Own profile only. Cannot see other engineers, other teams, or any team-level health scores. |

### Persona 4 — Admin

| Attribute | Detail |
|-----------|--------|
| **Role** | Configures the platform. Often a DevOps or Engineering Ops lead. Setup-phase-heavy. |
| **Goals** | Connect all integrations; configure teams, users, and org tree; resolve identity mismatches; keep integrations healthy. |
| **Pain points** | Integration configuration is currently scattered across 4+ tool admin panels; identity mismatches require manual investigation across tools. |
| **Key actions** | Connect/disconnect integrations; create users and assign roles; configure teams; fix identity resolution mismatches; monitor backfill progress. |
| **Data access** | Full access to all configuration and all data. |

---

## 3. Goals & Non-Goals

### Goals

- [ ] **G1** — Provide a single composite health score (RAG + 0–100) per team updated within 60 minutes of any source event, covering PR Health, Sprint Health, Incident Load, and Slack Signal.
- [ ] **G2** — Enable an EM to reach their team health summary within 3 minutes of logging in, with no prior platform training.
- [ ] **G3** — Deliver a role-scoped weekly digest via email to all configured recipients by 07:00 UTC every Monday with zero missed sends across any 4-week window.
- [ ] **G4** — Auto-resolve > 90% of engineer identities across 2 or more connected tools using email as the canonical key, requiring no admin intervention.
- [ ] **G5** — Surface a 3-month historical backfill within 24 hours of the first integration connection.
- [ ] **G6** — Ensure no feature in the product ranks, scores, or compares individual engineers against each other.
- [ ] **G7** — Support configurable health score weights per team from day one without requiring a database migration.
- [ ] **G8** — Degrade gracefully when any optional integration (Slack, incident tool, sprint tool) is not connected, displaying only the metrics available from connected integrations.

### Non-Goals (v1)

- **NG1** — Mobile app or native mobile-responsive design beyond basic viewport support.
- **NG2** — Real-time data streaming. Hourly refresh (with 6-hour cadence for Zenduty on-call) is the defined freshness target.
- **NG3** — Individual contributor performance scoring, ranking tables, or any cross-engineer comparison view.
- **NG4** — Public REST API for external consumers.
- **NG5** — SSO or OAuth login (Google, GitHub, SAML, Okta). Static credentials only.
- **NG6** — Threshold-based alerting (Slack alerts, email alerts beyond the weekly Monday digest).
- **NG7** — Keka OOO/leave data for throughput normalization.
- **NG8** — GitLab or Bitbucket support.
- **NG9** — Multi-tenant or SaaS hosting model.
- **NG10** — CSV or PDF export of reports.
- **NG11** — AI-generated narrative summaries or recommendations (no LLM calls).
- **NG12** — PR workflow automation (auto-assignment, routing, SLA nudges).
- **NG13** — Custom metric formula editor or weight builder UI for admins.
- **NG14** — Investment allocation categories (no Jellyfish-style business objective mapping).

---

## 4. Features

Features are numbered F01–F25. Priority designations: **Must-have** (implement before launch), **Nice-to-have** (include if schedule permits), **Future** (v2+).

---

### F01 — Static Authentication (Login / Logout / Role-Based Access)

**Priority:** Must-have
**Persona:** All

**Description:**
Users log in with a username and password. Sessions are managed via JWT tokens with a 24-hour expiry. The system enforces role-based access control at the API layer — each endpoint checks the role claim in the JWT before returning any data. Four roles exist: Admin, Director/VP, Engineering Manager, Engineer. Roles are assigned by an Admin at user creation time and cannot be self-assigned. A password reset flow is available via email.

**User Story:**
As any user, I want to log in with my credentials and have the system show only the data I am entitled to see, so that sensitive team and engineer data is not exposed beyond my role.

**Acceptance Criteria:**
- AC1: A user who submits a valid username and password receives a JWT access token and is redirected to the Overview tab within 2 seconds.
- AC2: A user who submits an incorrect password receives an HTTP 401 response with the message "Invalid credentials".
- AC3: A user who submits an incorrect password 5 or more consecutive times receives an HTTP 429 response and cannot attempt another login for 15 minutes.
- AC4: An Engineer role user who attempts to access any endpoint scoped to a team other than their own receives an HTTP 403 response.
- AC5: An Engineering Manager role user who attempts to access any endpoint scoped to a team other than their own receives an HTTP 403 response.
- AC6: A Director/VP role user can access data for all teams and all engineers without receiving a 403.
- AC7: An Admin role user can access all data and all configuration endpoints.
- AC8: A JWT token older than 24 hours is rejected with HTTP 401 on any authenticated endpoint.
- AC9: A user who clicks "Logout" has their token invalidated and is redirected to the login page within 1 second.
- AC10: An Admin can trigger a password reset email for any user from the user management page.
- AC11: The password reset link expires after 1 hour.
- AC12: Passwords are stored using bcrypt with a work factor of 12 or higher.

**Edge Cases & Notes:**
- The Admin role can also perform Director/VP-level data access in addition to configuration access.
- There is no self-registration flow; all accounts are created by an Admin.
- JWT refresh token behaviour must be resolved at spec stage (optional but recommended per research).
- Password reset requires SendGrid to be configured; if not configured, this flow is unavailable and must display a clear error message.

---

### F02 — GitHub Integration

**Priority:** Must-have
**Persona:** Admin (setup), EM, Director

**Description:**
An Admin connects the platform to a GitHub organisation via a GitHub App installation or a Personal Access Token (auth model to be confirmed at spec stage). The system registers org-level webhooks to receive real-time PR, review, push, and deployment events. On first connection, a 3-month REST/GraphQL backfill runs automatically. Post-backfill, webhooks are the primary data delivery mechanism. All PR Health metrics and DORA inputs (except deployment frequency proxy, which requires a spike) are derived from this integration.

**User Story:**
As an Admin, I want to connect our GitHub organisation to the platform so that all PR Health metrics and DORA data are available to Engineering Managers and Directors without any manual data entry.

**Acceptance Criteria:**
- AC1: An Admin who completes the GitHub App installation flow or pastes a PAT sees a "Connected" status on the GitHub integration card within 30 seconds.
- AC2: After connection, a backfill job starts automatically and the admin sees a progress indicator showing the percentage of repositories processed.
- AC3: The backfill makes all 3 months of PR, review, and commit data available within 24 hours of connection for an organisation with up to 50 repositories.
- AC4: A webhook event for a newly opened PR is processed and reflected in the PR Health metrics within 60 minutes of the event occurring on GitHub.
- AC5: Each webhook payload is deduplicated using the `X-GitHub-Delivery` header so that duplicate events do not create duplicate metric records.
- AC6: An Admin who disconnects the GitHub integration sees all GitHub-derived metrics change to a "Data unavailable" state in the UI within 5 minutes.
- AC7: The platform computes all 10 PR Health metrics listed in the metrics catalogue (cycle time, first review latency, review turnaround time, stale PR count, PR size distribution, review coverage, review participation rate, review depth, rework rate, author distribution) from GitHub data.
- AC8: A stale PR is defined as any open PR with no activity (comments, reviews, commits, or label changes) for more than 3 days.
- AC9: The GitHub integration page displays the last successful sync timestamp.
- AC10: If the GitHub API returns an HTTP 429 rate limit response, the ingestion worker backs off exponentially and retries without dropping events.

**Edge Cases & Notes:**
- The auth model (GitHub App vs. PAT) is an open decision for spec stage. GitHub App is preferred (higher rate limits: 15,000 req/hr vs. 5,000 for PAT; org-level install).
- DORA Deployment Frequency proxy method (GitHub Releases vs. branch push vs. GitHub Deployment API) requires a spike before spec commits to an approach. The UI must label the metric accurately (e.g. "Release Frequency" if using GitHub Releases) and not claim it is "Deployment Frequency" until the proxy is validated.
- Large organisations with hundreds of repositories must use org-level webhooks rather than per-repo registration.
- The CLI backfill script (F12) must support `--integration github` as a flag to re-run the GitHub backfill for a specific date range.

---

### F03 — Project Management Integration (Jira or ClickUp)

**Priority:** Must-have
**Persona:** Admin (setup), EM, Director

**Description:**
An Admin selects either Jira or ClickUp (one tool per organisation) and connects it via API token. The system polls for sprint and ticket data hourly. For ClickUp, a setup wizard guides the Admin to map ClickUp Lists or Folders to the sprint concept, since ClickUp has no native sprint object. For Jira, the Admin must confirm the story points custom field ID. On first connection, a 3-month backfill runs automatically. Sprint Health and Throughput metrics are derived from this integration.

**User Story:**
As an Admin, I want to connect Jira or ClickUp so that sprint burndown, velocity, and throughput data is available to Engineering Managers without them needing to log into the project management tool directly.

**Acceptance Criteria:**
- AC1: An Admin who selects "Jira" and pastes a valid Atlassian API token sees a "Connected" status on the Jira integration card within 30 seconds.
- AC2: An Admin who selects "ClickUp" and pastes a valid API token sees a "Connected" status on the ClickUp integration card within 30 seconds.
- AC3: The ClickUp setup wizard presents all Spaces, Folders, and Lists from the connected workspace and requires the Admin to designate which Lists represent sprints for each team before the backfill starts.
- AC4: The Jira setup wizard requires the Admin to confirm the story points custom field ID before the backfill starts.
- AC5: After connection, a backfill job makes 3 months of sprint and ticket data available within 24 hours for an organisation with up to 20 active boards.
- AC6: Sprint Health metrics are recomputed within 60 minutes of a ticket status change in the connected PM tool.
- AC7: The platform computes all 8 Sprint Health metrics listed in the metrics catalogue (burndown, scope creep %, carry-over rate, blocked ticket count and aging, velocity trend, ticket cycle time, commitment vs. delivery rate, estimation accuracy).
- AC8: The platform computes all 9 Throughput metrics (PRs merged/week, tickets closed/week, story points delivered, flow velocity, flow efficiency, flow load, flow distribution, WIP per engineer, ticket aging by state) at both team and per-engineer levels.
- AC9: If the Jira or ClickUp API returns HTTP 429, the ingestion worker backs off and retries without dropping records.
- AC10: An Admin who switches from Jira to ClickUp (or vice versa) is warned that existing sprint data will be archived and replaced with data from the new tool.

**Edge Cases & Notes:**
- Only one PM tool is active at a time per organisation; switching tools is an Admin action with a data migration warning.
- ClickUp story points use a custom field; the Admin must configure the field name at setup. If not configured, story point metrics display as "Not configured".
- Jira velocity calculation is performed by summing story points per sprint; this may differ from Jira's built-in velocity chart due to mid-sprint edits. The discrepancy must be documented in a tooltip.
- ClickUp sprint configuration (List-to-sprint mapping) must be re-confirmed after ClickUp workspace restructuring.
- A spike against a real ClickUp workspace is required before M2 implementation begins (see Open Questions).

---

### F04 — Incident Integration (PagerDuty or Zenduty)

**Priority:** Must-have
**Persona:** Admin (setup), EM, Director

**Description:**
An Admin selects either PagerDuty or Zenduty (one tool per organisation) and connects it via API key. The system polls for incident data hourly and for on-call schedule data every 6 hours (Zenduty's on-call API is limited to 40 requests/minute, making sub-hourly sync infeasible). MTTR, MTTA, incident frequency, on-call load, and repeat incidents per service are computed from this integration. On first connection, a 3-month backfill runs automatically.

**User Story:**
As an EM, I want incident data from PagerDuty or Zenduty surfaced in the platform so that I can see my team's on-call load and MTTR without logging into a separate incident management tool.

**Acceptance Criteria:**
- AC1: An Admin who selects "PagerDuty" and pastes a valid API key sees a "Connected" status on the PagerDuty integration card within 30 seconds.
- AC2: An Admin who selects "Zenduty" and pastes a valid API key sees a "Connected" status on the Zenduty integration card within 30 seconds.
- AC3: After connection, a backfill job makes 3 months of incident data available within 24 hours.
- AC4: MTTR for each incident is computed from the difference between the incident triggered timestamp and the incident resolved timestamp.
- AC5: MTTA for each incident is computed from the difference between the incident triggered timestamp and the first acknowledgement timestamp.
- AC6: On-call schedule data is refreshed no more frequently than every 6 hours for both PagerDuty and Zenduty integrations.
- AC7: The platform computes all 6 Incident Health metrics (frequency, MTTR, MTTA, paging distribution per engineer, repeat incidents by service, on-call hours per engineer) from incident integration data.
- AC8: If the incident tool API returns HTTP 429, the ingestion worker backs off and retries without dropping records.
- AC9: For Zenduty, the MTTA/MTTR analytics endpoint is used in preference to raw log entry calculation.
- AC10: An Admin who disconnects the incident integration sees all incident-derived metrics change to "Data unavailable" state in the UI within 5 minutes.

**Edge Cases & Notes:**
- Zenduty was rebranded as "Xurrent IMR" in late 2025. The integration must pin to the documented API base URL and monitor for changes.
- PagerDuty's MTTR is not a first-class field on the incident object; it must be calculated from `log_entries` (triggered → acknowledged → resolved timestamps).
- On-call hours per engineer requires fetching schedule overrides and computing actual on-call windows per person, which involves complex pagination in PagerDuty.

---

### F05 — Composite Team Health Score

**Priority:** Must-have
**Persona:** EM, Director

**Description:**
Each team has a composite health score displayed as both a RAG status (Red/Amber/Green) and a numeric score from 0 to 100. The composite is a weighted average of four component scores: PR Health, Sprint Health, Incident Load, and Slack Signal. Default weights are applied at team creation time but can be changed per team by an Admin (and optionally by the EM for their own team — configurable at spec stage). If a component's data source integration is not connected, that component is excluded from the composite and the remaining components are re-weighted proportionally. Users can drill down from composite → component score → underlying metrics.

**User Story:**
As an EM, I want a single health score for my team that tells me at a glance whether the team is healthy, at risk, or in trouble, so that I do not need to check four separate tools every morning.

**Acceptance Criteria:**
- AC1: Each team displays exactly one composite health score consisting of a numeric value from 0 to 100 and one of three RAG designations: Red (0–39), Amber (40–69), Green (70–100).
- AC2: The composite score is computed as the weighted average of the component scores for all connected integrations.
- AC3: If one or more component integrations are not connected, the composite is recomputed using only the connected components with weights normalised to sum to 100%.
- AC4: Default weights at team creation are PR Health 30%, Sprint Health 30%, Incident Load 25%, Slack Signal 15%.
- AC5: An Admin can change the weights for any team such that the four weights sum to exactly 100%.
- AC6: An EM can view the current weights and component score breakdown for their team from a "Health Score Details" panel.
- AC7: A user who clicks on the composite score is taken to a drill-down view showing all four component scores.
- AC8: A user who clicks on a component score is taken to a view showing all underlying metrics for that component.
- AC9: The composite score and all component scores are recalculated within 60 minutes of any underlying metric changing.
- AC10: A tooltip on the composite score displays the current weights, the component scores, and the formula used to derive the composite.
- AC11: DORA benchmark bands (Elite/High/Medium/Low) are displayed alongside the team health score for Deployment Frequency, Lead Time for Changes, Change Failure Rate, and MTTR.

**Edge Cases & Notes:**
- The default weight configuration (30/30/25/15) is a starting point; the spec stage must confirm whether EMs or only Admins can change weights.
- When Slack Signal is unavailable (e.g. non-Enterprise workspace with rate-limited signals), the Slack Signal weight is redistributed proportionally across the other three components.
- If all four component integrations are disconnected, the health score displays as "Insufficient data" rather than a numeric value.

---

### F06 — Overview Tab

**Priority:** Must-have
**Persona:** EM, Director

**Description:**
The Overview tab is the landing page after login. An EM sees one team health card for their team. A Director sees a grid of health cards for all teams. Each card shows: composite health score (RAG badge + numeric), three headline numbers (Open PRs, Sprint % done, Active incidents), and a 7-day sparkline of the composite score. Clicking a card navigates to the Team detail page.

**User Story:**
As an EM or Director, I want to see the health status of all relevant teams on a single page immediately after login, so that I can identify which teams need attention within the first 30 seconds of opening the platform.

**Acceptance Criteria:**
- AC1: The Overview tab is the first page displayed after a successful login for all roles.
- AC2: An EM who logs in sees exactly one team health card representing their own team.
- AC3: A Director who logs in sees a grid of team health cards, one per team they have access to.
- AC4: Each health card displays the team name, the RAG status indicator, the numeric composite score (0–100), and the three headline numbers: Open PRs (count), Sprint % done (percentage), Active incidents (count).
- AC5: Each health card displays a 7-day sparkline showing the daily composite score for the last 7 days.
- AC6: A user who clicks on a health card is navigated to the Teams tab showing that team's detail page within 1 second.
- AC7: Health cards refresh without a full page reload when the underlying data is updated, with a maximum staleness of 60 minutes.
- AC8: A health card for a team with no connected integrations displays "No data" in place of metrics.
- AC9: The Overview tab loads and displays all team cards within 3 seconds on a standard broadband connection.
- AC10: An Engineer role user does not see the Overview tab and is redirected to their own Engineer detail page after login.

**Edge Cases & Notes:**
- If a team has no active sprint, "Sprint % done" displays as "No active sprint".
- The Director's grid should be sortable by health score (ascending and descending) and by team name.
- Mobile viewport rendering is out of scope for v1, but the grid must not break on 1280px-wide screens.

---

### F07 — Teams Tab and Team Detail Page

**Priority:** Must-have
**Persona:** EM, Director

**Description:**
The Teams tab shows a list or grid of teams with health scores. Clicking a team opens a Team detail page with five sub-tabs: PR Health, Sprint Health, Incident Load, Slack Signal, and Team Members. Each sub-tab shows the component score and all underlying metrics for that component. Clicking any metric navigates to a drill-down view (e.g. clicking "Stale PRs" shows the list of stale PRs with age and author). The Team Members sub-tab shows each engineer's composite load indicator and key metrics (not a performance score).

**User Story:**
As an EM, I want to drill into my team's PR Health sub-tab and see which specific PRs are stale, who authored them, and how long they have been open, so that I can address the bottleneck in the next standup.

**Acceptance Criteria:**
- AC1: The Teams tab displays a list or grid of teams, each showing the team name, RAG status, and numeric composite score.
- AC2: An EM sees only their own team on the Teams tab.
- AC3: A Director sees all teams on the Teams tab.
- AC4: A user who clicks a team is taken to the Team detail page for that team.
- AC5: The Team detail page has exactly five sub-tabs: PR Health, Sprint Health, Incident Load, Slack Signal, Team Members.
- AC6: Each sub-tab displays the component score for that dimension at the top, followed by all underlying metrics for that component.
- AC7: A user who clicks on an underlying metric is taken to a drill-down view that shows the raw records contributing to that metric (e.g. a list of individual stale PRs with title, author, age, and GitHub URL).
- AC8: The PR Health sub-tab displays all 10 PR Health metrics from the metrics catalogue.
- AC9: The Sprint Health sub-tab displays all 8 Sprint Health metrics and all 9 Throughput metrics.
- AC10: The Incident Load sub-tab displays all 6 Incident Health metrics.
- AC11: The Slack Signal sub-tab displays after-hours message frequency, weekend message frequency, response time trends, and message volume trend. When Slack Signal data is unavailable, the sub-tab displays a clear explanation of why data is not available.
- AC12: The Team Members sub-tab shows each engineer's name, role, composite load indicator, and up to 3 key metrics at a glance, without ranking or scoring engineers against each other.
- AC13: All sub-tab data loads within 2 seconds of the sub-tab being selected.
- AC14: The Team detail page displays a "Last updated" timestamp showing when data was most recently refreshed.

**Edge Cases & Notes:**
- If a component's integration is not connected (e.g. no incident tool), the corresponding sub-tab displays "Integration not connected" with a link to Admin settings.
- The drill-down for "PR size distribution" shows a histogram, not individual PR records.
- DORA metrics (Deployment Frequency, Lead Time, Change Failure Rate, MTTR) are displayed on the PR Health sub-tab as a secondary section with benchmark band context (Elite/High/Medium/Low).

---

### F08 — Engineers Tab and Engineer Detail Page

**Priority:** Must-have
**Persona:** EM, Director, Engineer

**Description:**
The Engineers tab shows a list of engineers. An EM sees only their own team's engineers; a Director sees all engineers. Each row shows the engineer's name, role, and composite load indicator (not a performance score), plus key metric values at a glance. Clicking an engineer opens their detail page with five sub-tabs: Code Activity, Review Activity, Task Delivery, Incident Load, Collaboration. An Engineer role user is redirected directly to their own detail page and cannot see the Engineers list or any other engineer's profile.

**User Story:**
As an EM, I want to see each engineer's load indicator on the Engineers tab so that I can quickly identify which engineers may be overloaded or underutilised before it becomes a problem.

**Acceptance Criteria:**
- AC1: The Engineers tab displays a list of engineers, each row showing: name, role, composite load indicator (expressed as Low/Medium/High, not a numeric score), and up to 4 key metric values.
- AC2: An EM on the Engineers tab sees only engineers belonging to their own team.
- AC3: A Director on the Engineers tab sees all engineers across all teams, with a team name column.
- AC4: An Engineer role user who navigates to /engineers is redirected to their own engineer detail page.
- AC5: An Engineer role user who attempts to access another engineer's detail page receives an HTTP 403 response.
- AC6: The Engineer detail page has exactly five sub-tabs: Code Activity, Review Activity, Task Delivery, Incident Load, Collaboration.
- AC7: The Code Activity sub-tab displays PRs authored, PRs merged, average PR cycle time, and PR size trend for the selected engineer.
- AC8: The Review Activity sub-tab displays PRs reviewed, first-review latency, and review depth (average comments per review) for the selected engineer.
- AC9: The Task Delivery sub-tab displays tickets closed, ticket cycle time, and carry-over count for the selected engineer.
- AC10: The Incident Load sub-tab displays pages received, personal MTTR average, and on-call hours for the selected engineer.
- AC11: The Collaboration sub-tab displays which engineers the selected engineer most often reviews, and which engineers most often review the selected engineer's PRs.
- AC12: No sub-tab on the Engineer detail page contains a comparison of this engineer's metrics against any other individual engineer.
- AC13: A tooltip on the composite load indicator on the Engineers list page explains the label (e.g. "High load: this engineer has a WIP count above the team median and is on-call this week").
- AC14: All sub-tab data loads within 2 seconds of the sub-tab being selected.

**Edge Cases & Notes:**
- The composite load indicator (Low/Medium/High) is a workload signal, not a performance score. Its derivation must be documented in a tooltip. The exact formula is defined at spec stage.
- Engineers tab is accessible to the EM and Director; the Engineer role user bypasses this tab entirely.
- If an engineer has no data in a sub-tab (e.g. they have not been on-call), the sub-tab displays "No data for this period" rather than zeros.

---

### F09 — Weekly Digest (Email + In-App)

**Priority:** Must-have
**Persona:** EM, Director, Engineer

**Description:**
Every Monday, a Celery Beat job triggers at 06:00 UTC to generate and send role-scoped weekly digests via SendGrid. Engineers receive their own activity summary and throughput data. EMs receive their team's health summary, top risks, and DORA snapshot. Directors receive a cross-team health overview, risk flags, and DORA comparison. All digests are also viewable in the Digests tab in-app, rendered in the same format as the email. The Digests tab shows a list of past digests and a preview of the next Monday's digest.

**User Story:**
As an EM, I want to receive a weekly digest every Monday morning summarising my team's health, top risks, and DORA metrics, so that I arrive at the weekly leadership sync already informed without spending time manually aggregating data.

**Acceptance Criteria:**
- AC1: The Celery Beat job runs at 06:00 UTC every Monday and completes digest generation for all configured recipients by 07:00 UTC.
- AC2: Each recipient receives a digest scoped only to data they are entitled to see under their role.
- AC3: An Engineer's digest contains: own PRs authored and merged in the past week, own tickets closed, own review participation count, and own on-call hours.
- AC4: An EM's digest contains: team composite health score and RAG, component score changes from the prior week, top 3 metric risks (metrics furthest from target), and a DORA snapshot for their team.
- AC5: A Director's digest contains: a table of all teams with health scores, teams that changed RAG status in the past week, cross-team DORA comparison, and a risk flag section for teams in Red status.
- AC6: Digest email delivery is confirmed via SendGrid delivery webhook; failed deliveries are logged and retried once within 1 hour.
- AC7: Zero digest sends are missed (defined as: the digest job fails to send to any configured recipient) across any 4-week window.
- AC8: The Digests tab in-app displays a chronological list of all past digests the user is entitled to view.
- AC9: A "Next digest preview" section in the Digests tab renders the content of the next Monday's digest based on current data.
- AC10: Each digest is rendered in English only.
- AC11: A user who clicks on a metric in the digest email is taken to the corresponding drill-down view in the platform (deep link).

**Edge Cases & Notes:**
- If SendGrid is not configured, the digest tab still shows the in-app digest but the email send fails silently with an admin-visible error log entry.
- The digest generation must be idempotent: if the job runs twice on the same Monday (e.g. due to a restart), duplicate emails must not be sent.
- Digest content is generated from metric snapshots taken at 05:00 UTC Monday (1 hour before send), not live data at send time.
- Email templates are built with MJML and Jinja2; all templates must render correctly in Gmail, Outlook, and Apple Mail.

---

### F10 — Admin Settings

**Priority:** Must-have
**Persona:** Admin

**Description:**
The Admin settings area provides four management pages: Integrations (connect/disconnect each integration, paste API tokens, select Jira vs. ClickUp and PagerDuty vs. Zenduty), Teams (create teams, add/remove members, assign boards and services), Users (create user accounts, assign roles, link EMs to teams), and Org Tree (configure employee-to-manager hierarchy). An EM can access a restricted self-service page for their own team's integration settings but cannot access other teams' settings or user management.

**User Story:**
As an Admin, I want a single settings area where I can configure all integrations, manage teams and users, and set up the org tree, so that the platform is fully operational without requiring access to a database or CLI.

**Acceptance Criteria:**
- AC1: The Admin settings area is accessible only to Admin role users.
- AC2: The Integrations page shows each supported integration (GitHub, Jira, ClickUp, PagerDuty, Zenduty, Slack, Keka) with a status indicator (Connected, Disconnected, Error).
- AC3: An Admin who pastes an API token and clicks "Connect" for any integration receives a success or failure message within 10 seconds.
- AC4: An Admin can select exactly one of Jira or ClickUp as the active PM tool and exactly one of PagerDuty or Zenduty as the active incident tool.
- AC5: An Admin who disconnects an integration is shown a confirmation dialog warning that metrics derived from that integration will become unavailable.
- AC6: The Teams page allows an Admin to create a team, give it a name, and add or remove engineers and an EM.
- AC7: The Users page allows an Admin to create a user account with a username, email, password, and role assignment.
- AC8: The Users page allows an Admin to assign an EM to one or more teams.
- AC9: The Org Tree page allows an Admin to manually configure employee-to-manager reporting relationships via a form-based interface.
- AC10: An EM who navigates to Admin settings sees only a restricted "My Team Settings" page and cannot access the Users page, the Org Tree page, or other teams' integration settings.
- AC11: The Identity Resolution page (within Admin settings) shows all unresolved identity mismatches with a form for the Admin to manually map identities.
- AC12: An Admin can delete a user account. Deleting a user archives their historical data rather than hard-deleting it.

**Edge Cases & Notes:**
- EM self-service scope (which integration settings they can modify) must be confirmed at spec stage.
- If an Admin attempts to delete the only Admin account, the system must block the action and display an error.
- Health score weights are also configurable from Admin settings (either on the Team management page or as a separate sub-section — spec to decide).

---

### F11 — Identity Resolution

**Priority:** Must-have
**Persona:** Admin

**Description:**
When data is ingested from multiple integrations, the system maps each data record to a canonical engineer identity using email address as the primary key. The system attempts fuzzy matching (via pg_trgm) for partial matches and logs all unresolved mismatches for Admin review. An Admin can manually link a GitHub username, Jira account ID, Slack user ID, PagerDuty/Zenduty user, or Keka employee record to a canonical user in the platform via the Admin settings Identity Resolution page.

**User Story:**
As an Admin, I want the system to automatically match the same engineer across GitHub, Jira, and Slack using their email, so that PR data, ticket data, and Slack signals are attributed to the correct person without manual data entry for every engineer.

**Acceptance Criteria:**
- AC1: During ingestion, the system uses email address as the primary key to match records from each integration to a canonical platform user.
- AC2: When two or more tool accounts share an identical email, they are automatically linked without admin intervention.
- AC3: When the system cannot resolve an identity match with confidence, the unresolved pair is logged in the Identity Resolution page under "Pending matches".
- AC4: The Identity Resolution page shows each unresolved mismatch with the tool name, tool-side identifier, and candidate platform users for the Admin to select.
- AC5: An Admin who selects a candidate and clicks "Confirm" immediately links that tool account to the selected platform user.
- AC6: An Admin who clicks "Create new user" for an unresolved mismatch creates a new canonical user and links the tool account to it.
- AC7: Resolved identities persist and are not re-queued for review on the next ingestion cycle.
- AC8: The system automatically resolves more than 90% of identities in an organisation where all tools use the same primary email address for each employee.
- AC9: The Slack integration requests the `users:read.email` OAuth scope so that Slack user emails are available for identity matching.
- AC10: A resolution accuracy report is available to the Admin showing the total engineers in the org, the number auto-resolved, and the number pending manual resolution.

**Edge Cases & Notes:**
- If a team member uses different email addresses across tools, the admin must manually resolve. The system must not auto-merge identities with low confidence.
- Identity mismatches can cause metric under-attribution (engineer appears to have no GitHub activity if their GitHub email differs from their Jira email). A warning must appear on the engineer detail page when identity resolution is incomplete.

---

### F12 — On-Demand CLI Backfill Script

**Priority:** Must-have
**Persona:** Admin (technical)

**Description:**
A CLI script (`backfill.py` or `manage.py backfill`) allows a technical Admin to trigger a historical data backfill for any integration, for a specified date range, and optionally scoped to a single team. This is used for recovery after an ingestion failure, filling gaps, or extending history beyond the default 3-month cold start.

**User Story:**
As a technical Admin, I want to run a CLI command to re-ingest 3 months of GitHub data for a specific team after an ingestion failure, so that I can recover from data loss without writing custom scripts.

**Acceptance Criteria:**
- AC1: The CLI script accepts the following flags: `--integration` (values: github, jira, clickup, pagerduty, zenduty, slack), `--from` (ISO 8601 date), `--to` (ISO 8601 date), and `--team` (optional team identifier).
- AC2: Running the script with valid flags begins the backfill and prints progress to stdout in real time.
- AC3: The backfill is idempotent: running it twice for the same date range does not create duplicate records.
- AC4: The script validates the `--integration` flag value and returns a non-zero exit code with a human-readable error message if an unsupported value is provided.
- AC5: The script validates that `--from` is earlier than `--to` and returns a non-zero exit code with a readable error if not.
- AC6: The script can be run while the main application is running without causing data inconsistency.
- AC7: A `--dry-run` flag prints what would be backfilled without making any API calls or database writes.
- AC8: The script exits with code 0 on success and a non-zero code on failure.

**Edge Cases & Notes:**
- Rate limits must be respected during CLI backfill; the script must use the same rate-limit-aware HTTP client as the automated ingestion workers.
- Backfill progress is also visible in the Admin UI (see F20 — Backfill Progress Indicator).

---

### F13 — Hourly Metric Refresh (Celery Beat Jobs)

**Priority:** Must-have
**Persona:** Admin (operational), EM, Director

**Description:**
Celery Beat schedules one ingestion job per active integration per hour. Each job fetches new data from the integration's API (or processes webhook events from the queue), updates the metric tables, and recalculates affected team and engineer scores. Exceptions: Keka syncs daily, Zenduty on-call syncs every 6 hours. Each job records a `last_synced_at` timestamp visible in Admin settings.

**User Story:**
As an EM, I want to know that the health scores I see in the morning reflect activity from within the last hour, so that I can trust the data when making daily decisions.

**Acceptance Criteria:**
- AC1: Celery Beat schedules hourly sync jobs for GitHub, Jira/ClickUp, PagerDuty, and Slack integrations.
- AC2: Celery Beat schedules the Zenduty on-call sync every 6 hours (not hourly).
- AC3: Celery Beat schedules the Keka org tree sync once per day at a configurable UTC time (default: 02:00 UTC).
- AC4: Each sync job updates the `last_synced_at` timestamp in the integrations table upon successful completion.
- AC5: A sync job that fails logs the error and the `last_synced_at` timestamp is not updated, preserving the last known good sync time.
- AC6: The Admin settings Integrations page displays the `last_synced_at` value for each connected integration.
- AC7: Each integration uses a dedicated Celery queue (e.g. `q_github`, `q_jira`) so that a slow or failing integration does not block others.
- AC8: Celery Beat runs as a separate process from Celery workers.
- AC9: A failed sync job is retried up to 3 times with exponential backoff before being marked as failed.
- AC10: Metric scores are recalculated after each successful sync job completes.

**Edge Cases & Notes:**
- If a sync job has been failing for more than 2 hours, the Admin settings Integrations page shows an "Error" status badge on the affected integration with the failure message.
- The hourly cadence is a minimum guarantee. Webhook-driven events (GitHub PRs) may be processed more frequently as they arrive.

---

### F14 — Slack Integration

**Priority:** Nice-to-have
**Persona:** Admin (setup), EM, Director

**Description:**
An Admin connects a Slack Bot to the workspace via OAuth 2.0. The Bot reads message metadata (timestamps only — no message content) to compute after-hours message frequency, weekend message frequency, response time trends, and message volume trend per engineer. These signals serve as a proxy for burnout risk and disengagement. For non-Enterprise Slack workspaces, after-hours signals may be infeasible due to the May 2025 rate limit change (1 req/min for `conversations.history`). The system degrades gracefully in this case.

**User Story:**
As an EM, I want to see whether any engineers are sending significantly more messages outside of working hours, so that I can proactively address potential burnout before it affects productivity.

**Acceptance Criteria:**
- AC1: An Admin who completes the Slack OAuth 2.0 flow sees a "Connected" status on the Slack integration card within 30 seconds.
- AC2: The Slack OAuth scopes requested include `users:read`, `users:read.email`, `channels:read`, and `team:read`.
- AC3: The system reads only message timestamps from `conversations.history` and does not store, log, or display message content.
- AC4: After-hours is defined as messages sent outside 09:00–18:00 in the engineer's local timezone (or UTC if timezone is not available).
- AC5: The Slack Signal sub-tab on the Team detail page displays all 4 Slack Signal metrics when data is available.
- AC6: When the Slack API `conversations.history` rate limit prevents data collection for a workspace, the Slack Signal sub-tab displays a message: "Slack signal data is unavailable for this workspace. After-hours and weekend frequency metrics require Enterprise Grid or a Slack Marketplace app installation."
- AC7: When Slack Signal data is unavailable, the Slack Signal component is excluded from the composite health score and the remaining weights are proportionally redistributed.
- AC8: The Slack integration sync completes within 6 hours for a workspace with up to 500 engineers.
- AC9: The `users:read.email` scope is successfully acquired during the OAuth flow so that Slack user emails are available for identity resolution.

**Edge Cases & Notes:**
- A spike against a real non-Enterprise Slack workspace is required before implementing to validate whether `conversations.history` timestamps can be fetched within the 2025 rate limits for a typical 50-person workspace.
- The threshold at which the platform disables after-hours signals must be determined at spec stage (e.g. workspaces with more than N active channels or M monthly active users).
- Message volume trend (sudden drop = disengagement; spike = firefighting) requires at least 4 weeks of data to be meaningful; the UI must show a "Insufficient history" state for the first 4 weeks post-connection.

---

### F15 — Incidents Tab

**Priority:** Nice-to-have
**Persona:** EM, Director

**Description:**
A dedicated Incidents tab provides an organisation-wide view of incident data aggregated from the connected incident tool (PagerDuty or Zenduty). Features include: a timeline view (last 30, 60, or 90 days, selectable), breakdowns by service, by severity, and by team, an on-call load fairness view showing hours per engineer, and an incident-delivery correlation view showing whether incident spikes preceded PR slowdowns.

**User Story:**
As a Director, I want to see whether teams with high incident loads have lower PR throughput in subsequent weeks, so that I can make informed decisions about on-call rotation design and engineer allocation.

**Acceptance Criteria:**
- AC1: The Incidents tab is accessible to EM and Director roles.
- AC2: The Incidents tab shows a timeline of all incidents for the past 30 days by default, selectable to 60 or 90 days.
- AC3: The timeline can be filtered by service, by severity (P1/P2/P3/P4 or equivalent), and by team.
- AC4: An on-call load fairness view shows each engineer's on-call hours for the selected time period, without ranking engineers against each other.
- AC5: The incident-delivery correlation view shows a chart overlaying weekly incident count with weekly PR merge count for each team over the selected time range.
- AC6: An EM on the Incidents tab sees data only for their own team's services and engineers.
- AC7: A Director on the Incidents tab sees all teams' incident data.
- AC8: The Incidents tab loads within 3 seconds for a date range of 90 days.
- AC9: Clicking on a specific incident in the timeline shows the incident title, severity, MTTR, MTTA, and responding engineer (not a link to the incident tool — display only).

**Edge Cases & Notes:**
- If no incident integration is connected, the Incidents tab displays "Connect PagerDuty or Zenduty in Admin settings to enable this view."
- The incident-delivery correlation view is informational and explicitly labelled as correlation, not causation.

---

### F16 — DORA Benchmark Bands Display

**Priority:** Nice-to-have
**Persona:** EM, Director

**Description:**
For each of the four DORA metrics (Deployment Frequency, Lead Time for Changes, Change Failure Rate, MTTR), the platform displays the team's current value alongside the DORA Elite/High/Medium/Low benchmark bands. This allows Directors to communicate performance levels to leadership using industry-standard language.

**User Story:**
As a Director, I want to see which DORA performance band each team falls into for each metric, so that I can report to leadership that "Team Alpha is a High performer on Lead Time" using an industry-standard benchmark.

**Acceptance Criteria:**
- AC1: Each DORA metric displays the team's calculated value alongside four benchmark bands labelled Elite, High, Medium, and Low.
- AC2: The team's current value is visually highlighted within the appropriate band.
- AC3: The DORA benchmark band thresholds used match the 2024 DORA report definitions: Deployment Frequency (Elite: multiple per day, High: daily to weekly, Medium: weekly to monthly, Low: monthly or less); Lead Time (Elite: <1 hour, High: 1 day to 1 week, Medium: 1 week to 1 month, Low: >1 month); Change Failure Rate (Elite/High: 0–15%, Medium: 16–30%, Low: >30%); MTTR (Elite: <1 hour, High: <1 day, Medium: 1 day to 1 week, Low: >1 week).
- AC4: A tooltip on each DORA metric explains the proxy method used (e.g. "Deployment Frequency is approximated using GitHub Releases").
- AC5: If GitHub is not connected, DORA metrics display as "Data unavailable".
- AC6: DORA metrics are displayed on both the Team detail page (PR Health sub-tab) and the Director's Overview view.

**Edge Cases & Notes:**
- DORA Deployment Frequency proxy method must be confirmed at spec stage (see Open Questions). The UI label must match the proxy used.
- Change Failure Rate requires incident data in addition to GitHub data; if the incident integration is not connected, Change Failure Rate displays as "Insufficient data".

---

### F17 — Keka HRMS Org Tree Override

**Priority:** Nice-to-have
**Persona:** Admin

**Description:**
An optional Keka HRMS integration allows the platform to sync the employee-to-manager org tree from Keka daily. When Keka is connected and syncs successfully, the Keka-derived org tree replaces the manually configured org tree for all routing and access control decisions. The manual org tree is preserved in the database as a fallback but is not active while Keka is connected.

**User Story:**
As an Admin at a company that uses Keka for HRMS, I want the platform's org tree to stay in sync with Keka automatically, so that I do not need to update the platform manually every time an engineer joins, leaves, or changes managers.

**Acceptance Criteria:**
- AC1: An Admin who connects Keka via OAuth 2.0 and the sync succeeds sees "Keka (Active — org tree synced)" on the Integrations page.
- AC2: After Keka connects, the org tree displayed in Admin settings reflects the Keka-derived hierarchy, not the manually configured one.
- AC3: Keka syncs once per day at a configurable UTC time (default: 02:00 UTC).
- AC4: If Keka sync fails, the previously synced org tree remains active and the Admin sees an error notification on the Integrations page.
- AC5: An Admin who disconnects Keka is prompted to choose whether to restore the manually configured org tree or keep the last Keka-synced tree as the active configuration.
- AC6: The Keka sync uses the employee's email field as the identity resolution key to map Keka employees to canonical platform users.
- AC7: The Keka integration page displays the last successful sync timestamp.

**Edge Cases & Notes:**
- If Keka is configured, the system must fully replace the manually configured org tree, not merge the two sources.
- Keka API contracts are less stable than other integrations; the integration must pin to a specific API version and log breaking changes for admin review.
- Keka OOO/leave data is explicitly out of scope for v1.

---

### F18 — EM Self-Service Integration Settings

**Priority:** Nice-to-have
**Persona:** Engineering Manager

**Description:**
An EM can access a restricted settings page scoped to their own team, allowing them to configure certain integration parameters for their team (e.g. confirm the ClickUp List that maps to their sprint, adjust health score weights for their team). They cannot access other teams' settings, user management, or org tree configuration.

**User Story:**
As an EM, I want to configure my team's ClickUp sprint mapping without needing to involve the Admin, so that I can onboard my team to the platform independently.

**Acceptance Criteria:**
- AC1: An EM who navigates to Settings sees a "My Team Settings" page scoped to their team only.
- AC2: An EM can update the ClickUp List or Jira board associated with their team from the My Team Settings page.
- AC3: An EM can adjust the health score component weights for their team from the My Team Settings page, within bounds set by the Admin (spec to define whether bounds are enforced).
- AC4: An EM who attempts to access the Admin users management page receives an HTTP 403 response.
- AC5: An EM who attempts to access another team's settings page receives an HTTP 403 response.
- AC6: Changes made by an EM on the My Team Settings page take effect within 60 minutes (next hourly sync cycle).

**Edge Cases & Notes:**
- The exact scope of what an EM can configure is confirmed at spec stage. This feature is Nice-to-have and the scope may be reduced.

---

### F19 — Health Score Formula Transparency

**Priority:** Nice-to-have
**Persona:** EM, Director

**Description:**
A "Health Score Details" panel, accessible from any composite score display, shows the exact formula: component weights, component scores, and the underlying metric values that fed into each component score. This builds trust with EMs who may otherwise distrust an opaque number.

**User Story:**
As an EM, I want to click on my team's health score and see exactly how it was computed — which metrics fed into it and what each component score was — so that I can explain it to my team without guessing.

**Acceptance Criteria:**
- AC1: Clicking the composite score on any health card opens a "Health Score Details" panel.
- AC2: The panel shows the four component names, their weights (as percentages), their individual component scores, and the weighted contribution of each to the composite.
- AC3: The panel shows a formula: `Composite = (PR Health Score × W1%) + (Sprint Health Score × W2%) + (Incident Load Score × W3%) + (Slack Signal Score × W4%)` with actual values substituted.
- AC4: Each component score in the panel is a clickable link that navigates to the relevant sub-tab on the Team detail page.
- AC5: The panel shows the timestamp of the last recalculation.
- AC6: When a component is excluded due to a disconnected integration, the panel shows which component is excluded and shows the adjusted weights used.

**Edge Cases & Notes:**
- This feature can be deferred if schedule is tight but the tooltip from AC10 of F05 provides a minimum viable version of this functionality.

---

### F20 — Backfill Progress Indicator

**Priority:** Nice-to-have
**Persona:** Admin

**Description:**
The Admin settings Integrations page shows a real-time progress indicator for any in-progress backfill job, showing the percentage of repositories or records processed, estimated time remaining, and a log of the last 10 events processed.

**User Story:**
As an Admin, I want to see backfill progress in the UI so that I know the system is working and can estimate when historical data will be available.

**Acceptance Criteria:**
- AC1: When a backfill job is running, the Integrations page for that integration shows a progress bar with the percentage of repositories or records completed.
- AC2: The progress indicator shows an estimated time remaining, updated at least every 60 seconds.
- AC3: When the backfill completes successfully, the progress bar is replaced by a "Backfill complete" message with the timestamp of completion.
- AC4: When the backfill fails, the progress indicator shows the error message and the last successful record processed.
- AC5: The backfill can be re-run from the Admin UI by clicking a "Run backfill" button.

**Edge Cases & Notes:**
- Progress reporting requires the backfill Celery task to publish progress updates to Redis, which the frontend polls (or receives via SSE/WebSocket — implementation detail for spec stage).

---

### F21 — SSO / OAuth Login

**Priority:** Future
**Persona:** All

**Description:**
Support Google Workspace, GitHub, and SAML-based SSO login. Users can log in without a password using their organisation's identity provider.

**Notes:** Deferred to v2. Static credentials are sufficient for v1. No scope or AC defined at this stage.

---

### F22 — GitLab / Bitbucket Integration

**Priority:** Future
**Persona:** Admin, EM, Director

**Description:**
Support GitLab and Bitbucket as alternatives to GitHub for code repository data.

**Notes:** Deferred to v2. The target market for v1 is GitHub-based organisations. No scope or AC defined at this stage.

---

### F23 — Threshold-Based Alerting

**Priority:** Future
**Persona:** EM, Director

**Description:**
Configurable alerts that trigger Slack messages or emails when a metric crosses a defined threshold (e.g. "5 PRs stale > 3 days → post to #eng-ops").

**Notes:** Deferred to v2. The weekly digest is the only notification mechanism in v1. No scope or AC defined at this stage.

---

### F24 — AI-Generated Digest Narratives

**Priority:** Future
**Persona:** EM, Director

**Description:**
LLM-generated narrative summaries inserted into the weekly digest to explain metric trends in natural language (e.g. "Your team's PR cycle time increased 40% this week, likely correlated with the 2 P1 incidents on Tuesday").

**Notes:** Deferred to v2. No LLM calls in v1. No scope or AC defined at this stage.

---

### F25 — CSV / PDF Export

**Priority:** Future
**Persona:** EM, Director

**Description:**
Ability to export any metric view, team report, or digest as a CSV or PDF file.

**Notes:** Deferred to v2. No export capability in v1. No scope or AC defined at this stage.

---

## 5. User Flows

### Flow 1 — Admin First-Time Setup

```
Admin logs in (default admin credentials set at deploy time)
         │
         ▼
Admin Settings → Integrations
         │
         ▼
[1] Connect GitHub (App install or PAT paste)
    → Connection confirmed within 30s
    → Cold-start backfill starts automatically
    → Progress indicator visible in Admin UI
         │
         ▼
[2] Select PM tool: Jira OR ClickUp
    → If ClickUp: Setup wizard maps Lists to sprints, configures story point field
    → If Jira: Confirm story point custom field ID
    → Backfill starts
         │
         ▼
[3] Select Incident tool: PagerDuty OR Zenduty
    → Paste API key → Connection confirmed
    → Backfill starts
         │
         ▼
[4] (Optional) Connect Slack → OAuth flow → Bot installed
[5] (Optional) Connect Keka → OAuth flow → Daily org sync starts
         │
         ▼
Admin Settings → Teams
         │
    Create team(s)
    Add engineers to each team
    Assign EM to each team
         │
         ▼
Admin Settings → Users
         │
    Create user accounts
    Assign roles (Admin / Director / EM / Engineer)
         │
         ▼
Admin Settings → Org Tree
         │
    (If Keka not connected) Configure employee→manager hierarchy manually
    (If Keka connected) Review Keka-synced hierarchy
         │
         ▼
Admin Settings → Identity Resolution
         │
    Review pending identity mismatches
    Resolve manually or confirm auto-resolved matches
         │
         ▼
Setup complete → Navigate to Overview
```

---

### Flow 2 — EM Daily Morning Check (Time Target: < 3 Minutes)

```
EM logs in
         │
         ▼
Overview tab (landing page)
         │
    Team health card visible:
    • Composite score (e.g. Amber, 58/100)
    • Open PRs: 7
    • Sprint % done: 43%
    • Active incidents: 0
    • 7-day sparkline (trending down)
         │
    [Score is Amber — investigate]
         │
         ▼
Click team health card → Teams tab → Team detail
         │
    PR Health sub-tab (component score: 61/100)
    • Stale PR count: 4 (↑ from 1 last week)
    • Avg cycle time: 3.2 days (↑ from 2.1)
         │
    [4 stale PRs — click metric to drill down]
         │
         ▼
Drill-down: List of 4 stale PRs
         │
    PR #421 — "Refactor auth middleware" — 6 days — Author: Alice
    PR #418 — "Add logging to payment flow" — 4 days — Author: Bob
    PR #415 — "Fix null pointer in search" — 3 days — Author: Alice
    PR #412 — "Update Dockerfile" — 3 days — Author: Carlos
         │
         ▼
EM has full picture in < 3 minutes
    → Action: Bring PR #421 and #418 to standup for unblocking
```

---

### Flow 3 — Director Weekly Overview Check

```
Director logs in (typically Monday morning after receiving digest)
         │
         ▼
Overview tab
         │
    Grid of all team health cards (e.g. 5 teams):
    • Team Alpha: Green 78  • Team Beta: Red 32
    • Team Gamma: Amber 55  • Team Delta: Green 71
    • Team Epsilon: Amber 61
         │
    [Team Beta is Red — click to investigate]
         │
         ▼
Teams tab → Team Beta detail
         │
    Sprint Health sub-tab (component score: 28/100)
    • Carry-over rate: 67% (Red)
    • Scope creep: 22% (Red)
    • Velocity trend: declining 3 sprints (Amber)
         │
    Incident Load sub-tab (component score: 35/100)
    • Incident frequency: 8 this week (Red)
    • MTTR: 4.2 hours (Amber)
         │
         ▼
Director correlates incident load with sprint health degradation
    → Action: Schedule discussion with Team Beta EM
```

---

### Flow 4 — Engineer Viewing Own Profile

```
Engineer logs in
         │
         ▼
Redirected directly to own Engineer detail page
(Engineers tab list is not accessible)
         │
    Default view: Code Activity sub-tab
    • PRs authored this week: 2
    • PRs merged this week: 1
    • Avg PR cycle time: 1.8 days
    • PR size trend: stable (200–400 lines)
         │
    [Navigate to Review Activity sub-tab]
         │
    • PRs reviewed this week: 3
    • First-review latency: avg 4.2 hours
    • Review depth: avg 2.1 comments/PR
         │
    [Navigate to Digests tab to read Monday digest]
         │
    • Own activity summary from past week
    • Throughput: 1 PR merged, 3 tickets closed, 0 incidents
```

---

### Flow 5 — Admin Resolving an Identity Mismatch

```
Admin opens Admin Settings → Identity Resolution
         │
    Sees: "3 pending mismatches"
         │
    Mismatch 1:
    GitHub: john.smith@contractor.io  |  No matching platform user
    Candidate matches: John Smith (john@company.com)
         │
    Admin clicks "Confirm match" → Linked
         │
    Mismatch 2:
    Jira: jdoe (no email exposed)  |  Candidate: Jane Doe (jane.doe@company.com)
         │
    Admin clicks "Confirm match" → Linked
         │
    Mismatch 3:
    Slack: U0123ABCDE  |  No candidate matches found
         │
    Admin clicks "Create new user" → Creates canonical user with Slack identity linked
         │
    Resolution page shows: "All mismatches resolved.
    Identity resolution rate: 94% auto-resolved."
```

---

### Flow 6 — Weekly Digest Delivery (Automated)

```
[Every Sunday 05:00 UTC] — Metric snapshot captured for digest
         │
         ▼
[Every Monday 06:00 UTC] — Celery Beat triggers digest generation job
         │
    For each user with digest enabled:
    [Determine role → Generate role-scoped content]
         │
    Engineer digest:
    → Own PRs, tickets, reviews, on-call hours from past 7 days
         │
    EM digest:
    → Team health score + RAG + week-over-week change
    → Top 3 metric risks (furthest from target)
    → DORA snapshot
         │
    Director digest:
    → All teams table with health scores
    → RAG changes from prior week
    → Cross-team DORA comparison
    → Red-status risk flags
         │
         ▼
[Send via SendGrid] → Delivery confirmed via webhook callback
         │
    [By 07:00 UTC] All digests delivered
         │
         ▼
In-app Digests tab updated with new digest entry for each user
```

---

## 6. Data Requirements

| Data Entity | Source Integration | Freshness SLA | Retention | Sensitivity | Notes |
|-------------|-------------------|---------------|-----------|-------------|-------|
| Pull requests (metadata) | GitHub | 60 minutes | 12 months | Low | PR title, author, dates, merge status, size. No code content stored. |
| PR reviews | GitHub | 60 minutes | 12 months | Low | Reviewer, timestamps, approval status, comment count. No review text stored. |
| PR commits | GitHub | 60 minutes | 12 months | Low | Commit timestamps, author email. No commit message or diff content stored. |
| Repository list | GitHub | Daily | 12 months | Low | Repo name, default branch, org. |
| Sprint data | Jira / ClickUp | 60 minutes | 12 months | Low | Sprint name, start/end date, ticket counts. |
| Tickets / Issues | Jira / ClickUp | 60 minutes | 12 months | Low | ID, status, assignee email, created/closed dates, story points. No ticket description stored. |
| Ticket status transitions | Jira / ClickUp | 60 minutes | 12 months | Low | Status change timestamps per ticket. Used for cycle time calculation. |
| Incidents | PagerDuty / Zenduty | 60 minutes | 12 months | Medium | Incident ID, severity, triggered/acknowledged/resolved timestamps, assigned user. No incident description stored. |
| On-call schedules | PagerDuty / Zenduty | 6 hours | 12 months | Medium | Engineer-to-schedule mapping, on-call windows. |
| Slack message timestamps | Slack | 6 hours | 12 months | High | Timestamps only — no message content, no channel names, no thread context. Used to compute after-hours and weekend frequency. Must be deleted after aggregation. |
| Slack user list | Slack | Daily | 12 months | Medium | Slack user ID, email, display name. Used for identity resolution only. |
| Org tree / reporting hierarchy | Manual config or Keka | Daily (Keka) / On-change (manual) | Indefinite | Medium | Employee email, manager email, department. |
| Keka employee records | Keka | Daily | 12 months | High | Employee ID, email, manager email, designation, department. No compensation, personal, or leave data. |
| Platform users | Internal | Real-time | Indefinite | High | Username, email, bcrypt password hash, role, team assignment. |
| Team health score snapshots | Computed | Hourly | 12 months | Low | Composite score, component scores, weights, timestamp. Stored as time-series for sparkline and trend views. |
| Engineer metric snapshots | Computed | Hourly | 12 months | Low | Per-engineer metric values per hour. Stored as time-series. |
| Weekly digests | Generated | Weekly | 12 months | Medium | Rendered digest content per user per week. Role-scoped. |
| Backfill job state | Internal | Real-time | 90 days | Low | Job ID, integration, progress %, last processed record, error state. |
| Identity resolution mappings | Computed | Real-time | Indefinite | Medium | Canonical user ID → tool-specific user IDs. Admin overrides. |

### Data Privacy Notes

- No message content from any integration is stored at any point in the pipeline. Slack timestamps are aggregated into hourly frequency counts and the raw timestamps are discarded.
- No ticket or PR descriptions, commit messages, or incident descriptions are stored.
- GDPR considerations: Slack email and user data must be deletable upon user request. Platform users can be archived (not hard-deleted) to preserve historical metric attributions.
- Keka data is the most sensitive: employee-manager relationships must not be exposed beyond Admin-level access.

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Requirement | Target | Measurement |
|-------------|--------|-------------|
| Overview tab page load | Page fully rendered within 3 seconds on a 50 Mbps connection | Lighthouse / manual test |
| Team detail page sub-tab load | Sub-tab data visible within 2 seconds of selection | Browser network timing |
| Drill-down view load | Drill-down records visible within 2 seconds of click | Browser network timing |
| Metric freshness | All metrics updated within 60 minutes of a source event | Automated test checking `last_synced_at` vs. current time |
| Digest generation | All digests for up to 200 recipients generated within 60 minutes | Celery task timing log |
| API response time (p95) | 95th percentile of all API responses < 500ms under normal load | APM tool (e.g. Prometheus histogram) |
| Backfill throughput | 3-month GitHub backfill for an org with 50 repos and 500 PRs/month completes within 24 hours | QA test |
| Maximum supported org size | Up to 500 engineers without requiring TimescaleDB or infrastructure re-architecture changes | Load test |

### 7.2 Security

| Requirement | Detail |
|-------------|--------|
| Password storage | bcrypt with work factor ≥ 12. Plaintext passwords must never be logged or stored. |
| JWT security | JWT tokens signed with HS256 using a secret of ≥ 256 bits. Tokens expire after 24 hours. |
| Role enforcement | All API endpoints enforce role-based access via FastAPI `Depends()` decorators. Role is derived from JWT claim; it is never passed as a client-side parameter. |
| API token storage | Integration API tokens (GitHub, Jira, Slack, etc.) are encrypted at rest using AES-256. Never returned to the frontend after initial save. |
| Transport security | All traffic between client and server must use HTTPS (TLS 1.2+). No HTTP in production. |
| Slack data handling | Slack message timestamps are aggregated within the ingestion worker and raw timestamps are discarded within 24 hours. No message content is processed at any point. |
| Secrets management | All secrets (database passwords, API tokens, JWT secret) are passed via environment variables or a secrets manager. Never committed to version control. |
| Login rate limiting | Account lockout after 5 consecutive failed login attempts for 15 minutes. |
| RBAC scope creep prevention | A Celery task that processes data for Team A must not be able to write to Team B's metric tables. Team ID scope is enforced in the task parameters. |
| Dependency security | All Python and Node.js dependencies must be pinned to specific versions in `requirements.txt` and `package-lock.json`. A dependency audit must be run before v1 release. |

### 7.3 Reliability

| Requirement | Detail |
|-------------|--------|
| Digest delivery SLA | Zero digest sends missed across any 4-week window. Failed sends retried once within 1 hour. |
| Backfill idempotency | Backfill tasks are idempotent: re-running for the same date range does not create duplicate records. |
| Celery worker crash recovery | Worker crashes are detected by the process supervisor (Docker/Kubernetes). Workers restart automatically within 60 seconds. In-flight tasks are re-queued. |
| Database connection pooling | Connection pool sized for concurrent requests from FastAPI + Celery workers without exhausting PostgreSQL `max_connections`. |
| Graceful integration degradation | If any integration's API is unreachable, the corresponding metrics show "Data unavailable" with the last known sync timestamp. The rest of the platform continues to function. |
| Data retention | All metric data retained for 12 months. Data older than 12 months is automatically purged by a scheduled Celery task. |
| Deployment strategy | docker-compose for local/self-hosted. Kubernetes with Helm charts for production. Zero-downtime deployments using rolling update strategy. |
| Database migrations | All schema changes managed via Alembic migrations committed to version control. `create_all()` is never used in production. |
| Monitoring | Prometheus metrics exported from FastAPI and Celery workers. Grafana dashboards for: queue depth per integration, ingestion latency, task failure rate, API error rate. |

### 7.4 Scalability Constraints (v1)

- Designed for organisations with up to 500 engineers.
- Above 500 engineers, TimescaleDB continuous aggregates and Celery queue scaling must be re-evaluated.
- Multi-tenancy is explicitly out of scope for v1; the platform is single-tenant.

---

## 8. Open Questions

The following questions are unresolved at PRD stage and must be answered during the tech spec stage before implementation begins.

| # | Question | Options | Owner | Impact |
|---|----------|---------|-------|--------|
| OQ1 | TimescaleDB vs. vanilla PostgreSQL with partitioning? | (A) TimescaleDB: better time-series query performance, continuous aggregates; operational complexity. (B) Vanilla PostgreSQL + declarative partitioning: simpler to operate; query performance ceiling at scale. | Spec/Architect | Affects all time-series queries, migration complexity, and managed DB compatibility (RDS/Cloud SQL do not support TimescaleDB). |
| OQ2 | GitHub App vs. Personal Access Token for v1? | (A) GitHub App: org-level install, 15,000 req/hr, no per-user token; more complex setup. (B) PAT: simple admin-paste flow, 5,000 req/hr per token; per-user token management problem at scale. | Spec/Architect | Affects rate limit budget, onboarding UX, and long-term token management. |
| OQ3 | DORA Deployment Frequency proxy method? | (A) GitHub Releases API: aligns with release events, labelled "release frequency". (B) Push events to default branch: approximates deployments, may overcount. (C) GitHub Deployment API: accurate but requires CI/CD integration (out of scope v1). Spike required against a real org. | Engineering | Affects DORA accuracy and UI labelling. Must be resolved before M1 implementation. |
| OQ4 | Slack after-hours signal threshold and degradation UX? | Define: at what workspace size or channel count does `conversations.history` become infeasible under 2025 rate limits (1 req/min)? What does the UI show when degraded — "not available" only, or a partial estimate with a confidence caveat? Spike required against a non-Enterprise test workspace. | Spec + Product | Affects Slack Signal component score, health composite fallback, and user communication. |
| OQ5 | Health score weight configurability: Admin only or EM self-service? | (A) Admin only: consistent across org, lower complexity. (B) EM can adjust own team's weights within bounds set by Admin: more flexibility, higher complexity. | Product | Affects feature scope for F18 (EM Self-Service) and F05 (Health Score). |
| OQ6 | JWT refresh token implementation? | (A) Access token only (24h expiry): simple, but forces re-login daily. (B) Access + refresh token pair (24h access, 7-day refresh): better UX, requires token revocation logic. | Spec/Backend | Affects auth UX and session management complexity. |
| OQ7 | ClickUp sprint mapping persistence? | If a ClickUp workspace is restructured (Lists moved, renamed), does the admin need to re-run the sprint mapping wizard? Define a strategy for detecting and alerting on ClickUp structure changes. | Spec/Product | Affects data continuity for ClickUp users after workspace changes. |
| OQ8 | Slack signal degradation: exclude component or neutral score? | When Slack Signal data is unavailable (non-Enterprise rate-limited workspace), is the Slack Signal component (a) excluded and remaining weights normalised, or (b) assigned a neutral score of 50/100 to avoid penalising the team for a missing integration? | Product | Affects health score calculation in the majority of non-Enterprise deployments. |
| OQ9 | Engineer detail page: composite load indicator formula? | Define the exact inputs and thresholds for the Low/Medium/High load indicator displayed on the Engineers tab. What metrics feed into it (WIP, on-call hours, PR cycle time)? What are the thresholds? | Product + Spec | Affects F08 implementation and must be defined before frontend work on Engineers tab. |
| OQ10 | Backfill progress reporting mechanism (UI)? | (A) REST polling from Admin UI every 10 seconds. (B) Server-Sent Events (SSE) for real-time progress push. (C) WebSocket. | Spec/Frontend | Affects F20 (Backfill Progress Indicator) implementation complexity. |

---

*End of Product Requirements Document*
