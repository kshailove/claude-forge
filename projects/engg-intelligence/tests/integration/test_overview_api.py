"""Integration tests for GET /api/v1/overview endpoint.

Covers:
  - EM sees only own team card
  - Director sees all team cards
  - Card has required fields: team_id, rag, composite_score, sparkline_7d
  - Admin sees all teams
  - No auth → 401
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from conftest import (
    DIRECTOR_USER_ID,
    EM_USER_ID,
    SAMPLE_TEAM_ID,
    SAMPLE_TEAM2_ID,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_second_team(db_session, admin_token):
    """Insert a second team in the DB for director cross-team tests."""
    from app.models.team import Team
    team2 = Team(
        id=SAMPLE_TEAM2_ID,
        name="Beta Squad",
        slug="beta-squad",
    )
    db_session.add(team2)
    await db_session.flush()
    return team2


# ---------------------------------------------------------------------------
# EM scoping
# ---------------------------------------------------------------------------


class TestEMSeesOnlyOwnTeam:
    async def test_em_sees_only_own_team_card(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM token → response has exactly 1 card for their own team."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "teams" in data
        teams = data["teams"]
        assert len(teams) == 1
        assert str(teams[0]["team_id"]) == str(SAMPLE_TEAM_ID)

    async def test_em_overview_total_matches_teams_count(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM overview: total field matches number of teams returned."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == len(data["teams"])


# ---------------------------------------------------------------------------
# Director / Admin sees all teams
# ---------------------------------------------------------------------------


class TestDirectorSeesAllTeams:
    async def test_director_sees_all_teams(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """Director token → sees all teams (at least 1 seeded team)."""
        # Seed a second team
        await _seed_second_team(async_db_session, director_token)

        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        team_ids = {str(t["team_id"]) for t in data["teams"]}
        assert str(SAMPLE_TEAM_ID) in team_ids
        assert str(SAMPLE_TEAM2_ID) in team_ids

    async def test_admin_sees_all_teams(
        self, test_client, async_db_session, sample_team, sample_users, admin_token
    ):
        """Admin token → sees all teams."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "teams" in data
        assert len(data["teams"]) >= 1


# ---------------------------------------------------------------------------
# Card required fields
# ---------------------------------------------------------------------------


class TestCardHasRequiredFields:
    async def test_card_has_required_fields(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Each overview card has team_id, rag, composite_score, and sparkline_7d."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["teams"]) >= 1
        card = data["teams"][0]

        assert "team_id" in card
        assert "rag" in card
        assert "composite_score" in card
        assert "sparkline_7d" in card

    async def test_card_rag_is_valid_value(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """RAG value in card is one of red/amber/green."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        card = response.json()["teams"][0]
        assert card["rag"] in ("red", "amber", "green")

    async def test_card_sparkline_is_list(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """sparkline_7d is a list."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        card = response.json()["teams"][0]
        assert isinstance(card["sparkline_7d"], list)

    async def test_card_team_name_present(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Each card includes team_name."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        card = response.json()["teams"][0]
        assert "team_name" in card
        assert card["team_name"] == "Alpha Squad"


# ---------------------------------------------------------------------------
# No auth
# ---------------------------------------------------------------------------


class TestOverviewNoAuth:
    async def test_no_token_returns_401(self, test_client, async_db_session, sample_team):
        response = await test_client.get("/api/v1/overview")
        assert response.status_code == 401
