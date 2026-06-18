"""Core schema — all tables for engg-intelligence M0.

Revision ID: 001_core_schema
Revises: (initial migration — no parent)
Create Date: 2026-06-12 00:00:01

Implements all tables from Tech Spec Section 3 plus two deployment paths:
  Path A — TimescaleDB (USE_TIMESCALEDB=true): hypertables + continuous aggregates
  Path B — Managed PostgreSQL  (USE_TIMESCALEDB=false): declarative range partitioning
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "001_core_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

USE_TIMESCALEDB: bool = os.environ.get("USE_TIMESCALEDB", "true").lower() == "true"


# ---------------------------------------------------------------------------
# upgrade — create all tables
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    if USE_TIMESCALEDB:
        op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE')

    # ------------------------------------------------------------------
    # 1a. teams (no FK to users initially; em_user_id added after users)
    # Correct creation order: teams first (without em_user_id FK), then users
    # (which references teams), then add FK on teams.em_user_id → users.
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE teams (
            id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR(255) NOT NULL,
            slug       VARCHAR(100) NOT NULL,
            em_user_id UUID,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_teams_slug UNIQUE (slug)
        )
    """)
    op.create_index("idx_teams_slug", "teams", ["slug"], unique=True)
    op.create_index("idx_teams_em_user_id", "teams", ["em_user_id"])

    # ------------------------------------------------------------------
    # 1b. users (references teams)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE users (
            id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            email         VARCHAR(255) NOT NULL,
            username      VARCHAR(100) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role          VARCHAR(20)  NOT NULL
                          CHECK (role IN ('admin','director','em','engineer')),
            team_id       UUID         REFERENCES teams(id) ON DELETE SET NULL,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
            is_active     BOOLEAN      NOT NULL DEFAULT true,
            CONSTRAINT uq_users_email    UNIQUE (email),
            CONSTRAINT uq_users_username UNIQUE (username)
        )
    """)
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    op.create_index("idx_users_username", "users", ["username"], unique=True)
    op.create_index("idx_users_team_id", "users", ["team_id"])
    op.create_index("idx_users_role", "users", ["role"])

    # Now add em_user_id FK on teams → users
    op.execute("""
        ALTER TABLE teams
            ADD CONSTRAINT fk_teams_em_user_id
            FOREIGN KEY (em_user_id) REFERENCES users(id) ON DELETE SET NULL
    """)

    # updated_at trigger helper
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """)
    for tbl in ("users", "teams"):
        op.execute(f"""
            CREATE TRIGGER trg_{tbl}_updated_at
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
        """)

    # ------------------------------------------------------------------
    # 2. team_memberships
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE team_memberships (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            team_id    UUID        NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_team_memberships_user_team UNIQUE (user_id, team_id)
        )
    """)
    op.create_index("idx_team_memberships_user_team", "team_memberships",
                    ["user_id", "team_id"], unique=True)
    op.create_index("idx_team_memberships_team_id", "team_memberships", ["team_id"])

    # ------------------------------------------------------------------
    # 3. org_nodes
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE org_nodes (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            employee_user_id UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            manager_user_id  UUID        REFERENCES users(id) ON DELETE SET NULL,
            source           VARCHAR(20) NOT NULL CHECK (source IN ('manual','keka')),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_org_nodes_employee UNIQUE (employee_user_id)
        )
    """)
    op.create_index("idx_org_nodes_employee", "org_nodes", ["employee_user_id"], unique=True)
    op.create_index("idx_org_nodes_manager", "org_nodes", ["manager_user_id"])
    op.create_index("idx_org_nodes_source", "org_nodes", ["source"])
    op.execute("""
        CREATE TRIGGER trg_org_nodes_updated_at
        BEFORE UPDATE ON org_nodes
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 4. refresh_tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE refresh_tokens (
            id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64)  NOT NULL,
            expires_at TIMESTAMPTZ  NOT NULL,
            revoked    BOOLEAN      NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash)
        )
    """)
    op.create_index("idx_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])
    op.execute("""
        CREATE INDEX idx_refresh_tokens_expires
        ON refresh_tokens (expires_at) WHERE revoked = false
    """)

    # ------------------------------------------------------------------
    # 5. password_reset_tokens
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE password_reset_tokens (
            id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            used       BOOLEAN     NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_password_reset_tokens_hash UNIQUE (token_hash)
        )
    """)

    # ------------------------------------------------------------------
    # 6. integrations
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE integrations (
            id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id        UUID        REFERENCES teams(id) ON DELETE CASCADE,
            type           VARCHAR(30) NOT NULL
                           CHECK (type IN ('github','jira','clickup','pagerduty',
                                          'zenduty','slack','keka')),
            config_json    TEXT        NOT NULL,
            status         VARCHAR(20) NOT NULL DEFAULT 'disconnected'
                           CHECK (status IN ('connected','error','disconnected')),
            last_synced_at TIMESTAMPTZ,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.create_index("idx_integrations_team_type", "integrations", ["team_id", "type"])
    op.create_index("idx_integrations_type_status", "integrations", ["type", "status"])
    op.execute("""
        CREATE TRIGGER trg_integrations_updated_at
        BEFORE UPDATE ON integrations
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 7. identity_mappings
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE identity_mappings (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            canonical_user_id UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tool              VARCHAR(20) NOT NULL
                              CHECK (tool IN ('github','jira','clickup','slack',
                                             'pagerduty','zenduty','keka')),
            tool_user_id      VARCHAR(255) NOT NULL,
            tool_email        VARCHAR(255),
            resolution_method VARCHAR(10) NOT NULL CHECK (resolution_method IN ('auto','manual')),
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_identity_tool_user UNIQUE (tool, tool_user_id)
        )
    """)
    op.create_index("idx_identity_tool_user", "identity_mappings",
                    ["tool", "tool_user_id"], unique=True)
    op.create_index("idx_identity_canonical_user", "identity_mappings", ["canonical_user_id"])
    op.create_index("idx_identity_tool_email", "identity_mappings", ["tool", "tool_email"])
    op.execute("""
        CREATE TRIGGER trg_identity_mappings_updated_at
        BEFORE UPDATE ON identity_mappings
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 8. pull_requests
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE pull_requests (
            id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            github_id           BIGINT       NOT NULL,
            repo_full_name      VARCHAR(255) NOT NULL,
            pr_number           INTEGER      NOT NULL,
            title               VARCHAR(500) NOT NULL,
            author_user_id      UUID         REFERENCES users(id) ON DELETE SET NULL,
            state               VARCHAR(10)  NOT NULL CHECK (state IN ('open','merged','closed')),
            created_at          TIMESTAMPTZ  NOT NULL,
            merged_at           TIMESTAMPTZ,
            closed_at           TIMESTAMPTZ,
            first_review_at     TIMESTAMPTZ,
            cycle_time_seconds  INTEGER,
            pr_size_additions   INTEGER      NOT NULL DEFAULT 0,
            pr_size_deletions   INTEGER      NOT NULL DEFAULT 0,
            base_branch         VARCHAR(255) NOT NULL,
            head_branch         VARCHAR(255) NOT NULL,
            team_id             UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            updated_at          TIMESTAMPTZ  NOT NULL,
            last_activity_at    TIMESTAMPTZ  NOT NULL,
            CONSTRAINT uq_prs_github_id     UNIQUE (github_id),
            CONSTRAINT uq_prs_repo_number   UNIQUE (repo_full_name, pr_number)
        )
    """)
    op.create_index("idx_prs_github_id", "pull_requests", ["github_id"], unique=True)
    op.create_index("idx_prs_repo_number", "pull_requests",
                    ["repo_full_name", "pr_number"], unique=True)
    op.create_index("idx_prs_team_state", "pull_requests", ["team_id", "state"])
    op.execute("""
        CREATE INDEX idx_prs_team_created ON pull_requests (team_id, created_at DESC)
    """)
    op.create_index("idx_prs_author", "pull_requests", ["author_user_id"])
    op.execute("""
        CREATE INDEX idx_prs_last_activity ON pull_requests (last_activity_at)
        WHERE state = 'open'
    """)

    # ------------------------------------------------------------------
    # 9. pr_reviews
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE pr_reviews (
            id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            github_id        BIGINT      NOT NULL,
            pr_id            UUID        NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
            reviewer_user_id UUID        REFERENCES users(id) ON DELETE SET NULL,
            submitted_at     TIMESTAMPTZ NOT NULL,
            state            VARCHAR(25) NOT NULL
                             CHECK (state IN ('approved','changes_requested','commented')),
            comment_count    INTEGER     NOT NULL DEFAULT 0,
            CONSTRAINT uq_pr_reviews_github_id UNIQUE (github_id)
        )
    """)
    op.create_index("idx_pr_reviews_github_id", "pr_reviews", ["github_id"], unique=True)
    op.create_index("idx_pr_reviews_pr_id", "pr_reviews", ["pr_id"])
    op.create_index("idx_pr_reviews_reviewer", "pr_reviews", ["reviewer_user_id"])
    op.execute("""
        CREATE INDEX idx_pr_reviews_submitted_at ON pr_reviews (submitted_at DESC)
    """)

    # ------------------------------------------------------------------
    # 10. commits
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE commits (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            sha            VARCHAR(40)  NOT NULL,
            repo_full_name VARCHAR(255) NOT NULL,
            author_user_id UUID         REFERENCES users(id) ON DELETE SET NULL,
            committed_at   TIMESTAMPTZ  NOT NULL,
            pr_id          UUID         REFERENCES pull_requests(id) ON DELETE SET NULL,
            CONSTRAINT uq_commits_sha UNIQUE (sha)
        )
    """)
    op.create_index("idx_commits_sha", "commits", ["sha"], unique=True)
    op.execute("""
        CREATE INDEX idx_commits_author ON commits (author_user_id, committed_at DESC)
    """)
    op.create_index("idx_commits_pr_id", "commits", ["pr_id"])

    # ------------------------------------------------------------------
    # 11. github_releases
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE github_releases (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id     BIGINT       NOT NULL,
            repo_full_name VARCHAR(255) NOT NULL,
            tag_name       VARCHAR(255) NOT NULL,
            published_at   TIMESTAMPTZ  NOT NULL,
            team_id        UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            CONSTRAINT uq_github_releases_release_id UNIQUE (release_id)
        )
    """)
    op.create_index("idx_releases_release_id", "github_releases", ["release_id"], unique=True)
    op.execute("""
        CREATE INDEX idx_releases_team_published
        ON github_releases (team_id, published_at DESC)
    """)

    # ------------------------------------------------------------------
    # 12. sprints
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE sprints (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id UUID         NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
            external_id    VARCHAR(255) NOT NULL,
            name           VARCHAR(500) NOT NULL,
            team_id        UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            start_date     DATE,
            end_date       DATE,
            state          VARCHAR(20)  NOT NULL
                           CHECK (state IN ('active','completed','future')),
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_sprints_integration_external UNIQUE (integration_id, external_id)
        )
    """)
    op.create_index("idx_sprints_integration_external", "sprints",
                    ["integration_id", "external_id"], unique=True)
    op.create_index("idx_sprints_team_state", "sprints", ["team_id", "state"])
    op.execute("""
        CREATE INDEX idx_sprints_team_end_date ON sprints (team_id, end_date DESC)
    """)
    op.execute("""
        CREATE TRIGGER trg_sprints_updated_at
        BEFORE UPDATE ON sprints
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 13. tickets
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE tickets (
            id               UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id   UUID           NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
            external_id      VARCHAR(255)   NOT NULL,
            title            VARCHAR(500)   NOT NULL,
            assignee_user_id UUID           REFERENCES users(id) ON DELETE SET NULL,
            sprint_id        UUID           REFERENCES sprints(id) ON DELETE SET NULL,
            status           VARCHAR(100)   NOT NULL,
            story_points     DECIMAL(6,2),
            ticket_type      VARCHAR(20)    CHECK (ticket_type IN ('feature','bug','tech_debt','risk')),
            team_id          UUID           NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            created_at       TIMESTAMPTZ    NOT NULL,
            started_at       TIMESTAMPTZ,
            completed_at     TIMESTAMPTZ,
            updated_at       TIMESTAMPTZ    NOT NULL,
            CONSTRAINT uq_tickets_integration_external UNIQUE (integration_id, external_id)
        )
    """)
    op.create_index("idx_tickets_integration_external", "tickets",
                    ["integration_id", "external_id"], unique=True)
    op.create_index("idx_tickets_team_sprint", "tickets", ["team_id", "sprint_id"])
    op.create_index("idx_tickets_assignee", "tickets", ["assignee_user_id"])
    op.execute("""
        CREATE INDEX idx_tickets_team_completed ON tickets (team_id, completed_at DESC)
    """)

    # ------------------------------------------------------------------
    # 14. ticket_state_transitions
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE ticket_state_transitions (
            id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            ticket_id        UUID         NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            from_state       VARCHAR(100),
            to_state         VARCHAR(100) NOT NULL,
            transitioned_at  TIMESTAMPTZ  NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX idx_transitions_ticket_id
        ON ticket_state_transitions (ticket_id, transitioned_at)
    """)

    # ------------------------------------------------------------------
    # 15. incidents
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE incidents (
            id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id   UUID         NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
            external_id      VARCHAR(255) NOT NULL,
            title            VARCHAR(500) NOT NULL,
            severity         VARCHAR(5)   NOT NULL CHECK (severity IN ('p1','p2','p3','p4')),
            service_name     VARCHAR(255),
            team_id          UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            triggered_at     TIMESTAMPTZ  NOT NULL,
            acknowledged_at  TIMESTAMPTZ,
            resolved_at      TIMESTAMPTZ,
            mtta_seconds     INTEGER,
            mttr_seconds     INTEGER,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT uq_incidents_external_id UNIQUE (external_id)
        )
    """)
    op.create_index("idx_incidents_external_id", "incidents", ["external_id"], unique=True)
    op.execute("""
        CREATE INDEX idx_incidents_team_triggered ON incidents (team_id, triggered_at DESC)
    """)
    op.create_index("idx_incidents_severity", "incidents", ["severity"])
    op.create_index("idx_incidents_service", "incidents", ["service_name"])
    op.execute("""
        CREATE TRIGGER trg_incidents_updated_at
        BEFORE UPDATE ON incidents
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 16. incident_assignments
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE incident_assignments (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id UUID        NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
            user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
            assigned_at TIMESTAMPTZ NOT NULL,
            resolved_at TIMESTAMPTZ
        )
    """)
    op.create_index("idx_incident_assignments_incident", "incident_assignments", ["incident_id"])
    op.create_index("idx_incident_assignments_user", "incident_assignments", ["user_id"])

    # ------------------------------------------------------------------
    # 17. oncall_schedules
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE oncall_schedules (
            id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id UUID         NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
            schedule_name  VARCHAR(255) NOT NULL,
            external_id    VARCHAR(255) NOT NULL,
            CONSTRAINT uq_oncall_schedules_integration_external UNIQUE (integration_id, external_id)
        )
    """)
    op.create_index("idx_oncall_schedules_integration_external", "oncall_schedules",
                    ["integration_id", "external_id"], unique=True)

    # ------------------------------------------------------------------
    # 18. oncall_shifts
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE oncall_shifts (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            schedule_id UUID        NOT NULL REFERENCES oncall_schedules(id) ON DELETE CASCADE,
            user_id     UUID        REFERENCES users(id) ON DELETE SET NULL,
            start_at    TIMESTAMPTZ NOT NULL,
            end_at      TIMESTAMPTZ NOT NULL
        )
    """)
    op.create_index("idx_oncall_shifts_schedule", "oncall_shifts", ["schedule_id"])
    op.execute("""
        CREATE INDEX idx_oncall_shifts_user_time ON oncall_shifts (user_id, start_at DESC)
    """)

    # ------------------------------------------------------------------
    # 19. slack_activity_buckets (hypertable on Path A, partitioned on Path B)
    # ------------------------------------------------------------------
    if USE_TIMESCALEDB:
        op.execute("""
            CREATE TABLE slack_activity_buckets (
                id                     UUID        NOT NULL DEFAULT gen_random_uuid(),
                user_id                UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                team_id                UUID        NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                bucket_hour            TIMESTAMPTZ NOT NULL,
                message_count          INTEGER     NOT NULL DEFAULT 0,
                is_after_hours         BOOLEAN     NOT NULL,
                is_weekend             BOOLEAN     NOT NULL,
                channel_count_distinct INTEGER     NOT NULL DEFAULT 0,
                created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (id, bucket_hour)
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
        op.execute("""
            CREATE INDEX idx_slack_buckets_team_hour
            ON slack_activity_buckets (team_id, bucket_hour DESC)
        """)
    else:
        # Path B: range-partitioned by month
        op.execute("""
            CREATE TABLE slack_activity_buckets (
                id                     UUID        NOT NULL DEFAULT gen_random_uuid(),
                user_id                UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                team_id                UUID        NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                bucket_hour            TIMESTAMPTZ NOT NULL,
                message_count          INTEGER     NOT NULL DEFAULT 0,
                is_after_hours         BOOLEAN     NOT NULL,
                is_weekend             BOOLEAN     NOT NULL,
                channel_count_distinct INTEGER     NOT NULL DEFAULT 0,
                created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (id, bucket_hour),
                CONSTRAINT uq_slack_buckets_user_hour UNIQUE (user_id, bucket_hour)
            ) PARTITION BY RANGE (bucket_hour)
        """)
        _create_monthly_partitions("slack_activity_buckets", "bucket_hour")
        op.execute("""
            CREATE INDEX idx_slack_buckets_team_hour
            ON slack_activity_buckets (team_id, bucket_hour DESC)
        """)

    # ------------------------------------------------------------------
    # 20. team_metric_snapshots (hypertable / partitioned)
    # ------------------------------------------------------------------
    if USE_TIMESCALEDB:
        op.execute("""
            CREATE TABLE team_metric_snapshots (
                id          UUID          NOT NULL DEFAULT gen_random_uuid(),
                team_id     UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                snapshot_at TIMESTAMPTZ   NOT NULL,
                component   VARCHAR(30)   NOT NULL
                            CHECK (component IN
                                ('pr_health','sprint_health','incident_load',
                                 'slack_signal','composite')),
                score       DECIMAL(5,2)  NOT NULL,
                rag         VARCHAR(6)    NOT NULL CHECK (rag IN ('red','amber','green')),
                computed_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
                PRIMARY KEY (id, snapshot_at)
            )
        """)
        op.execute("""
            SELECT create_hypertable('team_metric_snapshots', 'snapshot_at',
                chunk_time_interval => INTERVAL '1 day')
        """)
        op.execute("""
            CREATE INDEX idx_team_snapshots_team_component_time
            ON team_metric_snapshots (team_id, component, snapshot_at DESC)
        """)
        op.execute("""
            CREATE INDEX idx_team_snapshots_snapshot_at
            ON team_metric_snapshots (snapshot_at DESC)
        """)
        # NOTE: The TimescaleDB continuous aggregate (daily_team_scores) is created
        # in migration 002_timescaledb_aggregates.py, which runs after this
        # migration commits — continuous aggregates cannot run inside a transaction.
    else:
        op.execute("""
            CREATE TABLE team_metric_snapshots (
                id          UUID          NOT NULL DEFAULT gen_random_uuid(),
                team_id     UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                snapshot_at TIMESTAMPTZ   NOT NULL,
                component   VARCHAR(30)   NOT NULL
                            CHECK (component IN
                                ('pr_health','sprint_health','incident_load',
                                 'slack_signal','composite')),
                score       DECIMAL(5,2)  NOT NULL,
                rag         VARCHAR(6)    NOT NULL CHECK (rag IN ('red','amber','green')),
                computed_at TIMESTAMPTZ   NOT NULL DEFAULT now(),
                PRIMARY KEY (id, snapshot_at)
            ) PARTITION BY RANGE (snapshot_at)
        """)
        _create_monthly_partitions("team_metric_snapshots", "snapshot_at")
        op.execute("""
            CREATE INDEX idx_team_snapshots_team_component_time
            ON team_metric_snapshots (team_id, component, snapshot_at DESC)
        """)
        op.execute("""
            CREATE INDEX idx_team_snapshots_snapshot_at
            ON team_metric_snapshots (snapshot_at DESC)
        """)

    # ------------------------------------------------------------------
    # 21. engineer_metric_snapshots (hypertable / partitioned)
    # ------------------------------------------------------------------
    if USE_TIMESCALEDB:
        op.execute("""
            CREATE TABLE engineer_metric_snapshots (
                id           UUID           NOT NULL DEFAULT gen_random_uuid(),
                user_id      UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                team_id      UUID           NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                snapshot_at  TIMESTAMPTZ    NOT NULL,
                metric_key   VARCHAR(100)   NOT NULL,
                metric_value DECIMAL(12,4)  NOT NULL,
                computed_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
                PRIMARY KEY (id, snapshot_at)
            )
        """)
        op.execute("""
            SELECT create_hypertable('engineer_metric_snapshots', 'snapshot_at',
                chunk_time_interval => INTERVAL '1 week')
        """)
        op.execute("""
            CREATE INDEX idx_eng_snapshots_user_metric_time
            ON engineer_metric_snapshots (user_id, metric_key, snapshot_at DESC)
        """)
        op.execute("""
            CREATE INDEX idx_eng_snapshots_team_time
            ON engineer_metric_snapshots (team_id, snapshot_at DESC)
        """)
    else:
        op.execute("""
            CREATE TABLE engineer_metric_snapshots (
                id           UUID           NOT NULL DEFAULT gen_random_uuid(),
                user_id      UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                team_id      UUID           NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
                snapshot_at  TIMESTAMPTZ    NOT NULL,
                metric_key   VARCHAR(100)   NOT NULL,
                metric_value DECIMAL(12,4)  NOT NULL,
                computed_at  TIMESTAMPTZ    NOT NULL DEFAULT now(),
                PRIMARY KEY (id, snapshot_at)
            ) PARTITION BY RANGE (snapshot_at)
        """)
        _create_monthly_partitions("engineer_metric_snapshots", "snapshot_at")
        op.execute("""
            CREATE INDEX idx_eng_snapshots_user_metric_time
            ON engineer_metric_snapshots (user_id, metric_key, snapshot_at DESC)
        """)
        op.execute("""
            CREATE INDEX idx_eng_snapshots_team_time
            ON engineer_metric_snapshots (team_id, snapshot_at DESC)
        """)

    # ------------------------------------------------------------------
    # 22. team_health_config
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE team_health_config (
            id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id              UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            weight_pr_health     DECIMAL(4,3)  NOT NULL DEFAULT 0.300
                                 CHECK (weight_pr_health >= 0 AND weight_pr_health <= 1),
            weight_sprint_health DECIMAL(4,3)  NOT NULL DEFAULT 0.300
                                 CHECK (weight_sprint_health >= 0 AND weight_sprint_health <= 1),
            weight_incident_load DECIMAL(4,3)  NOT NULL DEFAULT 0.250
                                 CHECK (weight_incident_load >= 0 AND weight_incident_load <= 1),
            weight_slack_signal  DECIMAL(4,3)  NOT NULL DEFAULT 0.150
                                 CHECK (weight_slack_signal >= 0 AND weight_slack_signal <= 1),
            updated_at           TIMESTAMPTZ   NOT NULL DEFAULT now(),
            updated_by           UUID          NOT NULL REFERENCES users(id),
            CONSTRAINT uq_team_health_config_team_id UNIQUE (team_id),
            CONSTRAINT chk_weights_sum CHECK (
                ABS(weight_pr_health + weight_sprint_health +
                    weight_incident_load + weight_slack_signal - 1.0) < 0.001
            )
        )
    """)
    op.execute("""
        CREATE TRIGGER trg_team_health_config_updated_at
        BEFORE UPDATE ON team_health_config
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ------------------------------------------------------------------
    # 23. digest_runs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE digest_runs (
            id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            run_at            TIMESTAMPTZ NOT NULL,
            snapshot_taken_at TIMESTAMPTZ,
            status            VARCHAR(15) NOT NULL
                              CHECK (status IN ('pending','generating','sent','failed')),
            recipient_count   INTEGER     NOT NULL DEFAULT 0,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX idx_digest_runs_run_at ON digest_runs (run_at DESC)
    """)

    # ------------------------------------------------------------------
    # 24. digest_emails
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE digest_emails (
            id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            digest_run_id        UUID        NOT NULL REFERENCES digest_runs(id) ON DELETE CASCADE,
            user_id              UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role_scope           VARCHAR(15) NOT NULL
                                 CHECK (role_scope IN ('engineer','em','director')),
            html_content         TEXT        NOT NULL,
            sent_at              TIMESTAMPTZ,
            delivery_status      VARCHAR(10) NOT NULL DEFAULT 'pending'
                                 CHECK (delivery_status IN ('pending','sent','failed')),
            sendgrid_message_id  VARCHAR(255),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_digest_emails_user_run UNIQUE (user_id, digest_run_id)
        )
    """)
    op.create_index("idx_digest_emails_user_run", "digest_emails",
                    ["user_id", "digest_run_id"], unique=True)
    op.create_index("idx_digest_emails_digest_run", "digest_emails", ["digest_run_id"])
    op.execute("""
        CREATE INDEX idx_digest_emails_status ON digest_emails (delivery_status)
        WHERE delivery_status != 'sent'
    """)

    # ------------------------------------------------------------------
    # 25. backfill_jobs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE backfill_jobs (
            id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            integration_id      UUID         NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
            integration_type    VARCHAR(30)  NOT NULL,
            date_from           DATE         NOT NULL,
            date_to             DATE         NOT NULL,
            status              VARCHAR(15)  NOT NULL
                                CHECK (status IN ('pending','running','completed','failed')),
            records_processed   INTEGER      NOT NULL DEFAULT 0,
            records_total       INTEGER,
            last_checkpoint     VARCHAR(500),
            started_at          TIMESTAMPTZ,
            completed_at        TIMESTAMPTZ,
            error_message       TEXT,
            created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
        )
    """)
    op.create_index("idx_backfill_jobs_integration_status", "backfill_jobs",
                    ["integration_id", "status"])
    op.execute("""
        CREATE INDEX idx_backfill_jobs_status ON backfill_jobs (status)
        WHERE status IN ('pending', 'running')
    """)

    # ------------------------------------------------------------------
    # 26. nightly_runs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE nightly_runs (
            id                         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            scheduled_at               TIMESTAMPTZ NOT NULL,
            started_at                 TIMESTAMPTZ,
            completed_at               TIMESTAMPTZ,
            status                     VARCHAR(15) NOT NULL
                                       CHECK (status IN ('pending','running','completed',
                                                        'partial','failed')),
            integrations_completed     JSONB       NOT NULL DEFAULT '{}',
            metric_computation_status  VARCHAR(15) NOT NULL DEFAULT 'pending'
                                       CHECK (metric_computation_status IN
                                           ('pending','running','completed','failed')),
            error_summary              TEXT,
            created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX idx_nightly_runs_scheduled_at ON nightly_runs (scheduled_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_nightly_runs_status ON nightly_runs (status)
        WHERE status IN ('pending', 'running')
    """)


# ---------------------------------------------------------------------------
# Helper: create monthly range partitions for the next 13 months (Path B)
# ---------------------------------------------------------------------------

def _create_monthly_partitions(table_name: str, partition_col: str) -> None:
    """Create monthly range partitions from today - 12 months through today + 1 month."""
    today = date.today()
    # Start from 13 months ago, create partitions for 14 months total
    start = date(today.year - 1, today.month, 1)

    for i in range(14):
        # Compute month start and next-month start
        month_year = start.year + (start.month - 1 + i) // 12
        month_num = (start.month - 1 + i) % 12 + 1
        next_month_num = month_num % 12 + 1
        next_year = month_year + (1 if month_num == 12 else 0)

        partition_from = f"{month_year:04d}-{month_num:02d}-01"
        partition_to = f"{next_year:04d}-{next_month_num:02d}-01"
        partition_suffix = f"{month_year:04d}_{month_num:02d}"

        op.execute(f"""
            CREATE TABLE {table_name}_{partition_suffix}
            PARTITION OF {table_name}
            FOR VALUES FROM ('{partition_from}') TO ('{partition_to}')
        """)


# ---------------------------------------------------------------------------
# downgrade — drop all tables (reverse order of creation)
# ---------------------------------------------------------------------------

def downgrade() -> None:
    if USE_TIMESCALEDB:
        op.execute("DROP MATERIALIZED VIEW IF EXISTS daily_team_scores")

    tables_to_drop = [
        "nightly_runs",
        "backfill_jobs",
        "digest_emails",
        "digest_runs",
        "team_health_config",
        "engineer_metric_snapshots",
        "team_metric_snapshots",
        "slack_activity_buckets",
        "oncall_shifts",
        "oncall_schedules",
        "incident_assignments",
        "incidents",
        "ticket_state_transitions",
        "tickets",
        "sprints",
        "github_releases",
        "commits",
        "pr_reviews",
        "pull_requests",
        "identity_mappings",
        "integrations",
        "password_reset_tokens",
        "refresh_tokens",
        "org_nodes",
        "team_memberships",
    ]
    for table in tables_to_drop:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Drop users and teams (circular FK)
    op.execute("ALTER TABLE teams DROP CONSTRAINT IF EXISTS fk_teams_em_user_id")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS teams CASCADE")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS \"uuid-ossp\"")
    if USE_TIMESCALEDB:
        op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE")
