"""Integration tests for /api/v1/engineers endpoints.

Covers:
  - Engineer sees own profile → 200
  - Engineer accesses peer → 404 (privacy: not 403)
  - EM sees own team's engineers only
  - Director sees all engineers
  - Profile has required fields
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from conftest import ENGINEER_USER_ID, EM_USER_ID, SAMPLE_TEAM_ID, SAMPLE_TEAM2_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_second_engineer(db, team_id=None):
    """Seed a second engineer user in the DB."""
    from app.core.security import hash_password
    from app.models.user import User
    second_id = uuid.UUID("11111111-0000-0000-0000-000000000099")
    user = User(
        id=second_id,
        email="second@example.com",
        username="second_engineer",
        password_hash=hash_password("TestPass!"),
        role="engineer",
        team_id=team_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# Engineer views own profile
# ---------------------------------------------------------------------------


class TestEngineerSeesOwnProfile:
    async def test_engineer_sees_own_profile(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """Engineer accessing their own profile → 200."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 200

    async def test_engineer_own_profile_has_required_fields(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """Engineer profile response includes user_id, name, email, role."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        for field in ("user_id", "name", "email", "role"):
            assert field in data

    async def test_engineer_own_profile_has_code_activity(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """Engineer profile includes code_activity section."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        data = response.json()
        assert "code_activity" in data


# ---------------------------------------------------------------------------
# Engineer accessing peer profile → 404
# ---------------------------------------------------------------------------


class TestEngineerPeerProfile:
    async def test_engineer_sees_peer_profile_returns_404(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """Engineer requesting another engineer's profile → 404 (not 403) for privacy."""
        second = await _seed_second_engineer(async_db_session, team_id=SAMPLE_TEAM_ID)

        response = await test_client.get(
            f"/api/v1/engineers/{second.id}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        # Spec: return 404 not 403 to avoid leaking profile existence
        assert response.status_code == 404

    async def test_engineer_peer_returns_404_not_403(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """Explicitly verify 404 is returned (not 403) for privacy."""
        random_id = uuid.uuid4()
        response = await test_client.get(
            f"/api/v1/engineers/{random_id}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 404
        assert response.status_code != 403


# ---------------------------------------------------------------------------
# EM sees own team engineers only
# ---------------------------------------------------------------------------


class TestEMSeesOwnTeamEngineers:
    async def test_em_sees_own_team_engineers_only(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """GET /engineers with EM token → returns engineers from own team only."""
        response = await test_client.get(
            "/api/v1/engineers",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "engineers" in data
        # All returned engineers should be from sample_team
        for eng in data["engineers"]:
            assert eng.get("team_name") == "Alpha Squad" or eng.get("team_name") is None

    async def test_em_can_view_own_team_engineer_profile(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM accessing a profile of an engineer on their team → 200."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_em_cannot_view_other_team_engineer_profile(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM accessing an engineer from a different team → 404."""
        # Seed second team engineer (not in EM's team)
        second_team_id = uuid.UUID("22222222-0000-0000-0000-000000000001")
        second = await _seed_second_engineer(async_db_session, team_id=second_team_id)

        response = await test_client.get(
            f"/api/v1/engineers/{second.id}",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Director sees all engineers
# ---------------------------------------------------------------------------


class TestDirectorSeesAllEngineers:
    async def test_director_can_view_any_engineer_profile(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """Director can view any engineer profile → 200."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200

    async def test_director_list_engineers_includes_all(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """GET /engineers with director → returns all engineers."""
        response = await test_client.get(
            "/api/v1/engineers",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "engineers" in data
        assert len(data["engineers"]) >= 1


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------


class TestUnauthorized:
    async def test_no_token_returns_401(self, test_client, async_db_session, sample_team):
        response = await test_client.get("/api/v1/engineers")
        assert response.status_code == 401
