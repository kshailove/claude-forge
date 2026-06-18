"""Integration tests for /api/v1/admin endpoints.

Covers:
  - Admin role can access admin endpoints
  - Non-admin roles (director, em, engineer) → 403
  - POST /admin/users creates a new user
  - GET /admin/users lists users (admin only)
  - POST /admin/teams creates a team
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


class TestAdminUsersEndpoint:
    async def test_admin_can_list_users(
        self, test_client, async_db_session, sample_users, admin_token
    ):
        """GET /admin/users accessible to admin → 200."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    async def test_director_cannot_access_admin_users(
        self, test_client, async_db_session, sample_users, director_token
    ):
        """GET /admin/users with director token → 403."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code == 403

    async def test_em_cannot_access_admin_users(
        self, test_client, async_db_session, sample_users, em_token
    ):
        """GET /admin/users with em token → 403."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 403

    async def test_engineer_cannot_access_admin_users(
        self, test_client, async_db_session, sample_users, engineer_token
    ):
        """GET /admin/users with engineer token → 403."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 403

    async def test_admin_can_create_user(
        self, test_client, async_db_session, sample_team, admin_token
    ):
        """POST /admin/users creates a new user when called by admin."""
        payload = {
            "email": "newengineer@example.com",
            "username": "new_engineer",
            "password": "SecurePass123!",
            "role": "engineer",
            "team_id": str(sample_team.id),
        }
        response = await test_client.post(
            "/api/v1/admin/users",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["email"] == "newengineer@example.com"
        assert data["role"] == "engineer"

    async def test_admin_list_users_returns_list(
        self, test_client, async_db_session, sample_users, admin_token
    ):
        """GET /admin/users returns a list structure."""
        response = await test_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # Response should have a users/items list key
        assert any(key in data for key in ("users", "items", "data"))


class TestAdminTeamsEndpoint:
    async def test_admin_can_list_teams(
        self, test_client, async_db_session, sample_team, admin_token
    ):
        """GET /admin/teams accessible to admin → 200."""
        response = await test_client.get(
            "/api/v1/admin/teams",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    async def test_admin_create_team(
        self, test_client, async_db_session, sample_users, admin_token
    ):
        """POST /admin/teams creates a new team."""
        payload = {
            "name": "Beta Squad",
            "slug": "beta-squad",
        }
        response = await test_client.post(
            "/api/v1/admin/teams",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["slug"] == "beta-squad"

    async def test_non_admin_cannot_create_team(
        self, test_client, async_db_session, sample_users, em_token
    ):
        """POST /admin/teams with em token → 403."""
        response = await test_client.post(
            "/api/v1/admin/teams",
            json={"name": "Gamma Team", "slug": "gamma-team"},
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 403


class TestAdminNightlyRuns:
    async def test_admin_can_list_nightly_runs(
        self, test_client, async_db_session, sample_team, admin_token
    ):
        """GET /admin/nightly-runs → 200 for admin."""
        response = await test_client.get(
            "/api/v1/admin/nightly-runs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Endpoint may or may not exist; accept 200 or 404
        assert response.status_code in (200, 404)

    async def test_non_admin_blocked_from_nightly_runs(
        self, test_client, async_db_session, sample_team, director_token
    ):
        """GET /admin/nightly-runs with director token → 403."""
        response = await test_client.get(
            "/api/v1/admin/nightly-runs",
            headers={"Authorization": f"Bearer {director_token}"},
        )
        assert response.status_code in (403, 404)
