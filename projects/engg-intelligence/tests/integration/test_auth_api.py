"""Integration tests for the /api/v1/auth endpoints.

Covers:
  - POST /auth/login — valid credentials → 200 with access + refresh tokens
  - POST /auth/login — wrong password → 401
  - POST /auth/login — unknown user → 401
  - POST /auth/refresh — valid refresh token → new access token
  - POST /auth/logout — revokes refresh token → subsequent refresh → 401
  - Protected endpoint without token → 401
  - GET /auth/me — returns current user profile
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from conftest import (
    ADMIN_USER_ID,
    EM_USER_ID,
    ENGINEER_USER_ID,
    SAMPLE_TEAM_ID,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLoginValidCredentials:
    async def test_login_valid_credentials_returns_tokens(
        self, test_client, async_db_session, sample_users
    ):
        """POST /auth/login with correct credentials returns 200 + access + refresh tokens."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "engineer_user", "password": "TestPass123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"] != ""
        assert data["refresh_token"] != ""

    async def test_login_returns_user_info(self, test_client, async_db_session, sample_users):
        """Login response includes user object with correct email and role."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "em_user", "password": "TestPass123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == "em@example.com"
        assert data["user"]["role"] == "em"

    async def test_login_returns_expires_in(self, test_client, async_db_session, sample_users):
        """Login response includes expires_in field."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "admin_user", "password": "TestPass123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "expires_in" in data
        assert data["expires_in"] > 0


class TestLoginInvalidPassword:
    async def test_login_invalid_password_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """POST /auth/login with wrong password → 401 INVALID_CREDENTIALS."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "engineer_user", "password": "WrongPassword!"},
        )
        assert response.status_code == 401

    async def test_login_invalid_password_error_code(
        self, test_client, async_db_session, sample_users
    ):
        """Error response contains INVALID_CREDENTIALS code."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "engineer_user", "password": "BadPass!"},
        )
        data = response.json()
        assert "error" in data["detail"]
        assert data["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


class TestLoginUnknownUser:
    async def test_login_unknown_user_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """POST /auth/login with non-existent username → 401."""
        response = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "ghost_user", "password": "SomePassword!"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token tests
# ---------------------------------------------------------------------------


class TestRefreshToken:
    async def test_refresh_valid_token_returns_new_access_token(
        self, test_client, async_db_session, sample_users
    ):
        """POST /auth/refresh with valid refresh token → new access_token."""
        # Login first to get tokens
        login_resp = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "engineer_user", "password": "TestPass123!"},
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]

        # Refresh
        response = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] != ""

    async def test_refresh_invalid_token_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """POST /auth/refresh with bogus token → 401."""
        response = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "totally-fake-refresh-token"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


class TestLogout:
    async def test_logout_invalidates_refresh_token(
        self, test_client, async_db_session, sample_users, engineer_token
    ):
        """After logout with a refresh token, using that token for refresh → 401."""
        # Login to get a fresh refresh token
        login_resp = await test_client.post(
            "/api/v1/auth/login",
            json={"username": "engineer_user", "password": "TestPass123!"},
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]
        access_token = login_resp.json()["access_token"]

        # Logout
        logout_resp = await test_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == 204

        # Attempt to refresh with the now-revoked token
        refresh_resp = await test_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected endpoint without token
# ---------------------------------------------------------------------------


class TestProtectedWithoutToken:
    async def test_protected_endpoint_without_token_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """Accessing a protected endpoint without a Bearer token → 401."""
        response = await test_client.get("/api/v1/overview")
        assert response.status_code == 401

    async def test_protected_endpoint_malformed_token_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """Accessing a protected endpoint with a malformed token → 401."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )
        assert response.status_code == 401

    async def test_protected_endpoint_missing_bearer_prefix_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """Token without 'Bearer ' prefix → 401."""
        response = await test_client.get(
            "/api/v1/overview",
            headers={"Authorization": "Token some-token"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


class TestMe:
    async def test_me_returns_current_user(
        self, test_client, async_db_session, sample_users, engineer_token
    ):
        """GET /auth/me with valid token → 200 with user info."""
        response = await test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {engineer_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "engineer@example.com"
        assert data["role"] == "engineer"

    async def test_me_without_token_returns_401(
        self, test_client, async_db_session, sample_users
    ):
        """GET /auth/me without token → 401."""
        response = await test_client.get("/api/v1/auth/me")
        assert response.status_code == 401
