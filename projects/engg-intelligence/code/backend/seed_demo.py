"""Demo seed script — populates the database with realistic fake data.

Run inside the API container:
    docker compose exec api python seed_demo.py

Creates:
  - 3 teams (Platform, Frontend, Data)
  - 1 EM + 4 engineers per team (15 users total, plus existing admin)
  - 1 stub integration per team (PagerDuty) — needed as FK for incidents
  - ~30 PRs + reviews per team (last 30 days)
  - ~15 tickets per team (mix of done / in-progress)
  - 1 active sprint + 1 completed sprint per team
  - ~10 incidents per team (last 30 days, mix of severities)
  - TeamMetricSnapshot rows (last 14 days) for composite + 4 components
  - EngineerMetricSnapshot rows
"""
from __future__ import annotations

import base64
import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ── DB connection (sync, psycopg2) ──────────────────────────────────────────
DATABASE_URL = (
    os.environ.get("DATABASE_URL", "")
    .replace("postgresql+asyncpg://", "postgresql://")
)
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# ── Encryption helper (mirrors app.core.encryption) ─────────────────────────
_ENC_KEY = bytes.fromhex(os.environ["DB_ENCRYPTION_KEY"])


def _encrypt(config: dict) -> str:
    plaintext = json.dumps(config, separators=(",", ":")).encode()
    nonce = os.urandom(12)
    ciphertext = AESGCM(_ENC_KEY).encrypt(nonce, plaintext, associated_data=None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


# ── Helpers ──────────────────────────────────────────────────────────────────
rng = random.Random(42)  # deterministic


def uid() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def days_ago(n: float) -> datetime:
    return now_utc() - timedelta(days=n)


def rand_dt(start_days: float, end_days: float) -> datetime:
    seconds = rng.uniform(start_days * 86400, end_days * 86400)
    return now_utc() - timedelta(seconds=seconds)


def bcrypt_hash(password: str) -> str:
    import passlib.hash
    return passlib.hash.bcrypt.using(rounds=4).hash(password)


# ── Seed data definitions ────────────────────────────────────────────────────
TEAMS = [
    {"name": "Platform Engineering", "slug": "platform"},
    {"name": "Frontend Product",     "slug": "frontend"},
    {"name": "Data & ML",            "slug": "data-ml"},
]

ENGINEERS_BY_TEAM = {
    "platform": [
        ("alice",   "alice@acme.dev"),
        ("bob",     "bob@acme.dev"),
        ("carol",   "carol@acme.dev"),
        ("dave",    "dave@acme.dev"),
    ],
    "frontend": [
        ("eve",     "eve@acme.dev"),
        ("frank",   "frank@acme.dev"),
        ("grace",   "grace@acme.dev"),
        ("heidi",   "heidi@acme.dev"),
    ],
    "data-ml": [
        ("ivan",    "ivan@acme.dev"),
        ("judy",    "judy@acme.dev"),
        ("karl",    "karl@acme.dev"),
        ("lena",    "lena@acme.dev"),
    ],
}

EMS_BY_TEAM = {
    "platform": ("em_platform", "em.platform@acme.dev"),
    "frontend": ("em_frontend", "em.frontend@acme.dev"),
    "data-ml":  ("em_dataml",   "em.dataml@acme.dev"),
}

REPOS_BY_TEAM = {
    "platform": "acme/platform-core",
    "frontend": "acme/web-app",
    "data-ml":  "acme/ml-pipeline",
}

SERVICES_BY_TEAM = {
    "platform": ["api-gateway", "auth-service", "infra-agent"],
    "frontend": ["web-frontend", "cdn-edge", "static-assets"],
    "data-ml":  ["feature-store", "model-serving", "data-ingestion"],
}

TICKET_TITLES = [
    "Implement retry logic for external API calls",
    "Add rate limiting to authentication endpoint",
    "Fix memory leak in connection pool",
    "Refactor legacy config loader",
    "Add dark mode support",
    "Improve error messages for invalid inputs",
    "Write integration tests for payment module",
    "Upgrade dependency: sqlalchemy 2.0 migration",
    "Reduce build time by parallelising test suites",
    "Add prometheus metrics for background jobs",
    "Fix flaky test in CI pipeline",
    "Document API authentication flow",
    "Optimise slow database query in reports endpoint",
    "Add webhook support for deployment events",
    "Investigate Sentry spike on Nov 12",
]

PR_TITLES = [
    "feat: add retry middleware with exponential backoff",
    "fix: resolve race condition in session handler",
    "chore: upgrade dependencies",
    "feat: implement dark mode toggle",
    "refactor: extract auth helpers into separate module",
    "fix: null pointer exception in report generator",
    "feat: add prometheus metrics endpoint",
    "docs: update API authentication guide",
    "test: add integration tests for billing flow",
    "feat: implement webhook delivery system",
    "fix: memory leak in redis connection pool",
    "perf: optimise slow query in analytics endpoint",
    "refactor: split monolithic config module",
    "feat: add structured logging with structlog",
    "fix: correct timezone handling in digest scheduler",
]

INCIDENT_TITLES = [
    "API gateway returning 502 errors",
    "Database connection pool exhausted",
    "High latency on /api/v1/reports endpoint",
    "Authentication service OOM restart",
    "CDN cache poisoning alert",
    "Model serving latency spike",
    "Data ingestion pipeline stalled",
    "Feature store sync failure",
    "Frontend deployment rollback",
    "Background job queue depth > 10k",
]


# ── Main seeder ──────────────────────────────────────────────────────────────

def seed(session: Session) -> None:
    print("Seeding demo data...")

    # Check if already seeded
    row = session.execute(text("SELECT count(*) FROM teams")).scalar()
    if row and row > 0:
        print(f"  Teams already exist ({row} found) — skipping.")
        return

    # ── Stub integration (needed as FK for incidents) ────────────────────────
    # One org-level PagerDuty integration (team_id = NULL for org-wide)
    stub_integration_id = uid()
    session.execute(text("""
        INSERT INTO integrations (id, team_id, type, config_json, status, created_at, updated_at)
        VALUES (:id, NULL, 'pagerduty', :cfg, 'connected', now(), now())
    """), {
        "id": stub_integration_id,
        "cfg": _encrypt({"api_key": "demo-key", "service_ids": []}),
    })
    print("  Created stub integration")

    # ── Jira/ClickUp stub integration (needed as FK for tickets & sprints) ──
    stub_ticket_integration_id = uid()
    session.execute(text("""
        INSERT INTO integrations (id, team_id, type, config_json, status, created_at, updated_at)
        VALUES (:id, NULL, 'jira', :cfg, 'connected', now(), now())
    """), {
        "id": stub_ticket_integration_id,
        "cfg": _encrypt({"api_token": "demo-token", "domain": "acme.atlassian.net"}),
    })
    print("  Created stub ticket integration")

    pw_hash = bcrypt_hash("Engineer1!")

    for team_def in TEAMS:
        slug = team_def["slug"]
        team_id = uid()

        em_username, em_email = EMS_BY_TEAM[slug]
        em_id = uid()

        # ── Insert EM user ───────────────────────────────────────────────────
        session.execute(text("""
            INSERT INTO users (id, email, username, password_hash, role, team_id, is_active, created_at, updated_at)
            VALUES (:id, :email, :username, :pw, 'em', NULL, true, now(), now())
        """), {"id": em_id, "email": em_email, "username": em_username, "pw": pw_hash})

        # ── Insert team ──────────────────────────────────────────────────────
        session.execute(text("""
            INSERT INTO teams (id, name, slug, em_user_id, created_at, updated_at)
            VALUES (:id, :name, :slug, :em_id, now(), now())
        """), {"id": team_id, "name": team_def["name"], "slug": slug, "em_id": em_id})

        # Update EM's team_id now that team exists
        session.execute(text(
            "UPDATE users SET team_id = :tid WHERE id = :uid"
        ), {"tid": team_id, "uid": em_id})

        # Add EM to team_memberships
        session.execute(text("""
            INSERT INTO team_memberships (id, user_id, team_id, created_at)
            VALUES (:id, :uid, :tid, now())
        """), {"id": uid(), "uid": em_id, "tid": team_id})

        print(f"  Created team '{team_def['name']}' with EM {em_username}")

        # ── Insert engineers ─────────────────────────────────────────────────
        eng_ids: list[str] = []
        for (username, email) in ENGINEERS_BY_TEAM[slug]:
            eng_id = uid()
            eng_ids.append(eng_id)
            session.execute(text("""
                INSERT INTO users (id, email, username, password_hash, role, team_id, is_active, created_at, updated_at)
                VALUES (:id, :email, :username, :pw, 'engineer', :tid, true, now(), now())
            """), {"id": eng_id, "email": email, "username": username, "pw": pw_hash, "tid": team_id})

            session.execute(text("""
                INSERT INTO team_memberships (id, user_id, team_id, created_at)
                VALUES (:id, :uid, :tid, now())
            """), {"id": uid(), "uid": eng_id, "tid": team_id})

        print(f"    Added {len(eng_ids)} engineers")

        repo = REPOS_BY_TEAM[slug]

        # ── Pull Requests ────────────────────────────────────────────────────
        pr_ids: list[str] = []
        for i in range(30):
            pr_id = uid()
            pr_ids.append(pr_id)
            author_id = rng.choice(eng_ids)
            created = rand_dt(30, 1)
            is_merged = rng.random() < 0.65
            is_open = not is_merged and rng.random() < 0.6
            state = "merged" if is_merged else ("open" if is_open else "closed")
            merged_at = (created + timedelta(hours=rng.uniform(4, 96))) if is_merged else None
            first_review_at = (created + timedelta(hours=rng.uniform(1, 24))) if rng.random() < 0.8 else None
            cycle_time = int((merged_at - created).total_seconds()) if merged_at else None
            last_activity = merged_at or (created + timedelta(hours=rng.uniform(1, 48)))
            session.execute(text("""
                INSERT INTO pull_requests
                    (id, github_id, repo_full_name, pr_number, title, author_user_id,
                     state, created_at, merged_at, closed_at, first_review_at,
                     cycle_time_seconds, pr_size_additions, pr_size_deletions,
                     base_branch, head_branch, team_id, updated_at, last_activity_at)
                VALUES
                    (:id, :gid, :repo, :num, :title, :author,
                     :state, :created, :merged, :closed, :first_review,
                     :cycle, :adds, :dels,
                     'main', :branch, :tid, :updated, :last_activity)
            """), {
                "id": pr_id, "gid": rng.randint(10000, 9999999),
                "repo": repo, "num": i + 1,
                "title": rng.choice(PR_TITLES),
                "author": author_id, "state": state,
                "created": created,
                "merged": merged_at,
                "closed": merged_at if (state == "closed" and not is_merged) else None,
                "first_review": first_review_at,
                "cycle": cycle_time,
                "adds": rng.randint(5, 500), "dels": rng.randint(2, 200),
                "branch": f"feature/task-{rng.randint(100, 999)}",
                "tid": team_id, "updated": last_activity, "last_activity": last_activity,
            })

            # Add 1-2 reviews per merged PR
            if is_merged or rng.random() < 0.5:
                for _ in range(rng.randint(1, 2)):
                    reviewer_id = rng.choice([e for e in eng_ids if e != author_id] or eng_ids)
                    review_at = first_review_at or (created + timedelta(hours=rng.uniform(2, 48)))
                    session.execute(text("""
                        INSERT INTO pr_reviews (id, github_id, pr_id, reviewer_user_id, submitted_at, state, comment_count)
                        VALUES (:id, :gid, :pr_id, :reviewer, :at, :state, :comments)
                    """), {
                        "id": uid(), "gid": rng.randint(100000, 9999999),
                        "pr_id": pr_id, "reviewer": reviewer_id,
                        "at": review_at,
                        "state": rng.choice(["approved", "changes_requested", "commented"]),
                        "comments": rng.randint(0, 8),
                    })

        print(f"    Created {len(pr_ids)} PRs")

        # ── Sprints ──────────────────────────────────────────────────────────
        completed_sprint_id = uid()
        session.execute(text("""
            INSERT INTO sprints (id, integration_id, external_id, name, team_id, start_date, end_date, state, created_at, updated_at)
            VALUES (:id, :iid, :ext_id, :name, :tid, :start, :end, 'completed', now(), now())
        """), {
            "id": completed_sprint_id, "iid": stub_ticket_integration_id,
            "ext_id": f"{slug}-sprint-22",
            "name": f"Sprint 22 — {team_def['name']}",
            "tid": team_id,
            "start": (now_utc() - timedelta(days=28)).date(),
            "end": (now_utc() - timedelta(days=14)).date(),
        })

        active_sprint_id = uid()
        session.execute(text("""
            INSERT INTO sprints (id, integration_id, external_id, name, team_id, start_date, end_date, state, created_at, updated_at)
            VALUES (:id, :iid, :ext_id, :name, :tid, :start, :end, 'active', now(), now())
        """), {
            "id": active_sprint_id, "iid": stub_ticket_integration_id,
            "ext_id": f"{slug}-sprint-23",
            "name": f"Sprint 23 — {team_def['name']}",
            "tid": team_id,
            "start": (now_utc() - timedelta(days=7)).date(),
            "end": (now_utc() + timedelta(days=7)).date(),
        })

        # ── Tickets ──────────────────────────────────────────────────────────
        done_statuses = ["done", "closed", "completed"]
        wip_statuses = ["in_progress", "in review", "blocked"]
        todo_statuses = ["todo", "backlog"]

        for i in range(20):
            assignee = rng.choice(eng_ids)
            in_current = rng.random() < 0.6
            sprint_id = active_sprint_id if in_current else completed_sprint_id
            status = rng.choice(done_statuses if not in_current else wip_statuses + done_statuses)
            started = rand_dt(20, 5) if status not in todo_statuses else None
            completed = (started + timedelta(hours=rng.uniform(8, 200))) if (status in done_statuses and started) else None
            session.execute(text("""
                INSERT INTO tickets
                    (id, integration_id, external_id, title, assignee_user_id, sprint_id,
                     status, story_points, ticket_type, team_id, created_at, started_at, completed_at, updated_at)
                VALUES
                    (:id, :iid, :ext, :title, :assignee, :sprint,
                     :status, :pts, :ttype, :tid, :created, :started, :completed, now())
            """), {
                "id": uid(), "iid": stub_ticket_integration_id,
                "ext": f"{slug.upper()}-{100 + i}",
                "title": rng.choice(TICKET_TITLES),
                "assignee": assignee, "sprint": sprint_id,
                "status": status, "pts": rng.choice([1, 2, 3, 5, 8]),
                "ttype": rng.choice(["feature", "bug", "tech_debt", "risk"]),
                "tid": team_id,
                "created": rand_dt(28, 10),
                "started": started, "completed": completed,
            })

        print(f"    Created sprints + tickets")

        # ── Incidents ────────────────────────────────────────────────────────
        services = SERVICES_BY_TEAM[slug]
        for i in range(12):
            severity = rng.choices(["p1", "p2", "p3", "p4"], weights=[5, 20, 45, 30])[0]
            triggered = rand_dt(30, 0.5)
            is_resolved = rng.random() < 0.85
            mtta = rng.randint(60, 1800) if is_resolved else None
            mttr = rng.randint(600, 18000) if is_resolved else None
            resolved_at = (triggered + timedelta(seconds=mttr)) if mttr else None
            ack_at = (triggered + timedelta(seconds=mtta)) if mtta else None

            inc_id = uid()
            session.execute(text("""
                INSERT INTO incidents
                    (id, integration_id, external_id, title, severity, service_name,
                     team_id, triggered_at, acknowledged_at, resolved_at,
                     mtta_seconds, mttr_seconds, created_at, updated_at)
                VALUES
                    (:id, :iid, :ext, :title, :sev, :svc,
                     :tid, :triggered, :ack, :resolved,
                     :mtta, :mttr, now(), now())
            """), {
                "id": inc_id, "iid": stub_integration_id,
                "ext": f"INC-{rng.randint(10000, 99999)}",
                "title": rng.choice(INCIDENT_TITLES),
                "sev": severity, "svc": rng.choice(services),
                "tid": team_id,
                "triggered": triggered, "ack": ack_at, "resolved": resolved_at,
                "mtta": mtta, "mttr": mttr,
            })

            # Assign to 1-2 engineers
            for eng_id in rng.sample(eng_ids, min(2, len(eng_ids))):
                session.execute(text("""
                    INSERT INTO incident_assignments (id, incident_id, user_id, assigned_at, resolved_at)
                    VALUES (:id, :iid, :uid, :at, :resolved)
                """), {
                    "id": uid(), "iid": inc_id, "uid": eng_id,
                    "at": triggered, "resolved": resolved_at,
                })

        print(f"    Created 12 incidents")

        # ── Team metric snapshots (last 14 days) ─────────────────────────────
        components = {
            "pr_health":      (rng.uniform(55, 90),  5),
            "sprint_health":  (rng.uniform(50, 85),  6),
            "incident_load":  (rng.uniform(45, 80),  7),
            "slack_signal":   (rng.uniform(60, 95),  4),
        }

        def rag(score: float) -> str:
            if score >= 70:
                return "green"
            if score >= 50:
                return "amber"
            return "red"

        for day_offset in range(14, -1, -1):
            snap_at = now_utc() - timedelta(days=day_offset)
            composite = 0.0
            weights = {"pr_health": 0.30, "sprint_health": 0.30, "incident_load": 0.25, "slack_signal": 0.15}
            comp_scores: dict[str, float] = {}

            for component, (base, drift) in components.items():
                score = min(100, max(0, base + rng.gauss(0, drift)))
                comp_scores[component] = score
                composite += score * weights[component]

                session.execute(text("""
                    INSERT INTO team_metric_snapshots (id, team_id, snapshot_at, component, score, rag, computed_at)
                    VALUES (:id, :tid, :snap, :comp, :score, :rag, now())
                """), {
                    "id": uid(), "tid": team_id, "snap": snap_at,
                    "comp": component, "score": round(score, 2), "rag": rag(score),
                })

            session.execute(text("""
                INSERT INTO team_metric_snapshots (id, team_id, snapshot_at, component, score, rag, computed_at)
                VALUES (:id, :tid, :snap, 'composite', :score, :rag, now())
            """), {
                "id": uid(), "tid": team_id, "snap": snap_at,
                "score": round(composite, 2), "rag": rag(composite),
            })

        print(f"    Created 14-day metric snapshots")

        # ── Engineer metric snapshots ─────────────────────────────────────────
        eng_metrics = [
            "prs_authored_30d", "prs_merged_30d", "tickets_closed_30d",
            "avg_cycle_time_hours", "review_count_30d",
        ]
        for eng_id in eng_ids:
            for day_offset in range(7, -1, -1):
                snap_at = now_utc() - timedelta(days=day_offset)
                for metric in eng_metrics:
                    if "hours" in metric:
                        val = rng.uniform(4, 72)
                    else:
                        val = rng.randint(0, 10)
                    session.execute(text("""
                        INSERT INTO engineer_metric_snapshots
                            (id, user_id, team_id, snapshot_at, metric_key, metric_value, computed_at)
                        VALUES (:id, :uid, :tid, :snap, :key, :val, now())
                    """), {
                        "id": uid(), "uid": eng_id, "tid": team_id,
                        "snap": snap_at, "key": metric, "val": round(val, 4),
                    })

        print(f"    Created engineer metric snapshots")

    session.commit()
    print("\nSeed complete!")
    print("  All engineers/EMs have password: Engineer1!")
    print("  Login with username (e.g. 'alice', 'em_platform') not email")


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
