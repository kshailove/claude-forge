"""Acceptance tests for RBAC (Role-Based Access Control).

AC criteria verified:
  - EM cannot call admin endpoints → 403
  - Engineer cannot call admin endpoints → 403
  - Engineer accessing peer profile → 404 (not 403, for privacy)
  - Director sees cross-team data → 200
  - Role is always derived from JWT, never query param
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from conftest import ENGINEER_USER_ID, SAMPLE_TEAM_ID, SAMPLE_TEAM2_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC: EM cannot call admin endpoints
# ---------------------------------------------------------------------------


class TestEMCannotCallAdminEndpoints:
    async def test_ac_em_cannot_call_admin_users(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """AC: EM POST /admin/users → 403 INSUFFICIENT_PERMISSIONS."""
        response = await test_client.post(
            "/api/v1/admin/users",
            json={
                "email": "hacker@example.com",
                "username": "hacker",
                "password": "SecurePass!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 403

    async def test_ac_em_cannot_get_admin_users(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """AC: EM GET /admin/users → 403."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 403

    async def test_ac_em_cannot_create_admin_teams(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """AC: EM POST /admin/teams → 403."""
        response = await test_client.post(
            "/api/v1/admin/teams",
            json={"name": "Rogue Team", "slug": "rogue-team"},
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# AC: Engineer cannot call admin endpoints
# ---------------------------------------------------------------------------


class TestEngineerCannotCallAdminEndpoints:
    async def test_ac_engineer_cannot_call_admin_users(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Engineer POST /admin/users → 403."""
        response = await test_client.post(
            "/api/v1/admin/users",
            json={
                "email": "another@example.com",
                "username": "another",
                "password": "SecurePass!",
                "role": "engineer",
            },
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 403

    async def test_ac_engineer_cannot_list_admin_users(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Engineer GET /admin/users → 403."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 403

    async def test_ac_engineer_cannot_trigger_nightly_run(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Engineer POST /admin/nightly-runs → 403 or 404."""
        response = await test_client.post(
            "/api/v1/admin/nightly-runs",
            json={},
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code in (403, 404, 405)


# ---------------------------------------------------------------------------
# AC: Engineer peer profile returns 404, not 403
# ---------------------------------------------------------------------------


class TestEngineerPeerReturns404NotForbidden:
    async def test_ac_engineer_peer_profile_returns_404_not_403(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Engineer accessing another user's profile → 404, not 403 (privacy spec)."""
        # Use a UUID that doesn't belong to the engineer
        other_user_id = uuid.uuid4()
        response = await test_client.get(
            f"/api/v1/engineers/{other_user_id}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        # Must be 404, NEVER 403
        assert response.status_code == 404
        assert response.status_code != 403

    async def test_ac_engineer_another_seeded_engineer_returns_404(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Engineer accessing EM user (different role) profile → 404."""
        from conftest import EM_USER_ID
        response = await test_client.get(
            f"/api/v1/engineers/{EM_USER_ID}",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        # Privacy: 404 not 403
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# AC: Director sees cross-team data
# ---------------------------------------------------------------------------


class TestDirectorCrossTeamAccess:
    async def test_ac_director_sees_cross_team_data(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """AC: Director can access team detail for any team → 200."""
        response = await test_client.get(
            f"/api/v1/teams/{SAMPLE_TEAM_ID}",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200

    async def test_ac_director_overview_shows_multiple_teams(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """AC: Director /overview includes all visible teams."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "teams" in data

    async def test_ac_director_can_view_all_engineer_profiles(
        self, test_client, async_db_session, sample_team, sample_users, director_token
    ):
        """AC: Director can view any engineer profile → 200."""
        response = await test_client.get(
            f"/api/v1/engineers/{ENGINEER_USER_ID}",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# AC: Role is from JWT, not query parameter
# ---------------------------------------------------------------------------


class TestRoleFromJWT:
    async def test_ac_role_not_spoofable_via_query_param(
        self, test_client, async_db_session, sample_team, sample_users, engineer_token
    ):
        """AC: Adding ?role=admin query param does not elevate privileges."""
        response = await test_client.get(
            "/api/v1/admin/users?role=admin",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        # Role from JWT (engineer) → 403
        assert response.status_code == 403

    async def test_ac_no_token_always_401(
        self, test_client, async_db_session, sample_team
    ):
        """AC: No token → 401 regardless of query params."""
        response = await test_client.get("/api/v1/admin/users?role=admin")
        assert response.status_code == 401
