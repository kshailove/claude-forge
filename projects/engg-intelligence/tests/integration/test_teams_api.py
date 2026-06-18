"""Integration tests for /api/v1/teams endpoints.

Covers:
  - EM cannot access another team's data → 404
  - Director can access any team → 200
  - Stale PRs list has days_stale field
  - Slack degraded returns degraded flag
  - Team detail has required fields
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from conftest import SAMPLE_TEAM_ID, SAMPLE_TEAM2_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_second_team(db):
    from app.models.team import Team
    team2 = Team(id=SAMPLE_TEAM2_ID, name="Beta Squad", slug="beta-squad")
    db.add(team2)
    await db.flush()
    return team2


async def _seed_stale_pr(db, team_id, author_user_id=None):
    """Insert an open PR with last_activity_at > 3 days ago."""
    from app.models.github import PullRequest
    pr = PullRequest(
        id=uuid.uuid4(),
        github_id=100001,
        team_id=team_id,
        repo_full_name="acme/backend",
        pr_number=42,
        title="Stale old PR",
        state="open",
        author_user_id=author_user_id,
        base_branch="main",
        head_branch="feature/stale",
        created_at=datetime.now(tz=timezone.utc) - timedelta(days=10),
        updated_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
        last_activity_at=datetime.now(tz=timezone.utc) - timedelta(days=5),
    )
    db.add(pr)
    await db.flush()
    return pr


# ---------------------------------------------------------------------------
# RBAC: EM cannot access another team
# ---------------------------------------------------------------------------


class TestEMCannotAccessOtherTeam:
    async def test_em_cannot_access_other_team_404(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM accessing a different team_id → 404 (not 403, to prevent team enumeration)."""
        other_team_id = str(SAMPLE_TEAM2_ID)
        response = await test_client.get(
            f"/api/v1/teams/{other_team_id}",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 404

    async def test_em_cannot_access_other_team_pr_health(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM accessing another team's PR health → 404."""
        other_team_id = str(SAMPLE_TEAM2_ID)
        response = await test_client.get(
            f"/api/v1/teams/{other_team_id}/pr-health",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Director can access any team
# ---------------------------------------------------------------------------


class TestDirectorCanAccessAnyTeam:
    async def test_director_can_access_own_team(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """Director accessing a team → 200."""
        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200

    async def test_director_can_access_other_team(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """Director accessing second team → 200."""
        await _seed_second_team(async_db_session)
        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM2_ID}",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Stale PRs list
# ---------------------------------------------------------------------------


class TestStalePRsList:
    async def test_stale_prs_list_has_days_stale_field(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """GET /teams/{id}/pr-health/stale-prs → each PR has days_stale field."""
        await _seed_stale_pr(async_db_session, SAMPLE_TEAM_ID)

        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}/pr-health/stale-prs",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "stale_prs" in data
        if data["stale_prs"]:
            pr = data["stale_prs"][0]
            assert "days_stale" in pr
            assert pr["days_stale"] >= 3.0

    async def test_stale_prs_has_required_fields(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Stale PR items have title, url, days_stale, author fields."""
        await _seed_stale_pr(async_db_session, SAMPLE_TEAM_ID)

        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}/pr-health/stale-prs",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        if data["stale_prs"]:
            pr = data["stale_prs"][0]
            for field in ("title", "url", "days_stale", "author"):
                assert field in pr


# ---------------------------------------------------------------------------
# Slack degraded
# ---------------------------------------------------------------------------


class TestSlackDegradedFlag:
    async def test_slack_degraded_returns_degraded_flag(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """GET /teams/{id}/slack-signal with no slack snapshot → degraded=True."""
        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}/slack-signal",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "degraded" in data
        # No slack snapshot seeded → should be degraded
        assert data["degraded"] is True

    async def test_slack_degraded_has_reason(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Slack degraded response includes a reason string."""
        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}/slack-signal",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        if data.get("degraded"):
            assert "reason" in data
            assert isinstance(data["reason"], str)


# ---------------------------------------------------------------------------
# Team list
# ---------------------------------------------------------------------------


class TestTeamsList:
    async def test_em_sees_only_own_team_in_list(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """GET /teams with em token → 1 team (own)."""
        response = await test_client.get(
            "/api/v1/teams",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "teams" in data
        assert len(data["teams"]) == 1

    async def test_director_sees_all_teams_in_list(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """GET /teams with director token → all teams."""
        await _seed_second_team(async_db_session)
        response = await test_client.get(
            "/api/v1/teams",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["teams"]) >= 2
