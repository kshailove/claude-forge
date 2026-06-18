"""
Load test for engg-intelligence API.

Target: p95 < 500ms, error rate < 1% at 50 concurrent users.

Usage:
    locust -f locustfile.py --headless -u 50 -r 10 --run-time 5m --host http://localhost:8000

Environment variables (override test credentials):
    LOAD_TEST_EMAIL     — default: loadtest@yourcompany.com
    LOAD_TEST_PASSWORD  — default: LoadTest1234!
"""
from __future__ import annotations

import logging
import os
import random
from typing import Optional

from locust import HttpUser, between, task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test credentials — override via environment variables in CI
# ---------------------------------------------------------------------------
TEST_EMAIL = os.getenv("LOAD_TEST_EMAIL", "loadtest@yourcompany.com")
TEST_PASSWORD = os.getenv("LOAD_TEST_PASSWORD", "LoadTest1234!")


class EnggIntelligenceUser(HttpUser):
    """Simulated user session for the engg-intelligence API.

    Weighted task mix mirrors realistic dashboard usage patterns:
    - Overview page hits most frequently (weight=3)
    - Team list and team detail are common navigation paths (weight=2 each)
    - Engineers list and incidents summary are less frequent (weight=1 each)
    """

    wait_time = between(1, 3)  # seconds between task executions

    # State per virtual user
    _token: Optional[str] = None
    _team_ids: list[str]

    def on_start(self) -> None:
        """Authenticate and store the JWT token for all subsequent requests."""
        self._team_ids = []
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            name="/api/v1/auth/login",
        )
        if response.status_code == 200:
            data = response.json()
            self._token = data.get("access_token")
            logger.debug("Load test user authenticated successfully")
        else:
            logger.error(
                "Load test login failed: %s %s",
                response.status_code,
                response.text[:200],
            )
            # Stop this virtual user if authentication fails — no point proceeding
            self.environment.runner.quit()

    def on_stop(self) -> None:
        """Log out and invalidate the session token."""
        if self._token:
            self.client.post(
                "/api/v1/auth/logout",
                headers=self._auth_headers(),
                name="/api/v1/auth/logout",
            )
            self._token = None
            logger.debug("Load test user logged out")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """Return Authorization header with current JWT token."""
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    # ------------------------------------------------------------------
    # Tasks — ordered by descending weight (heaviest first for clarity)
    # ------------------------------------------------------------------

    @task(3)
    def view_overview(self) -> None:
        """GET /api/v1/overview — engineering overview dashboard."""
        self.client.get(
            "/api/v1/overview",
            headers=self._auth_headers(),
            name="/api/v1/overview",
        )

    @task(2)
    def view_teams(self) -> None:
        """GET /api/v1/teams — team list; cache team IDs for detail requests."""
        response = self.client.get(
            "/api/v1/teams",
            headers=self._auth_headers(),
            name="/api/v1/teams",
        )
        if response.status_code == 200:
            data = response.json()
            # Store team IDs so view_team_detail can pick a random one
            items = data if isinstance(data, list) else data.get("teams", [])
            self._team_ids = [
                str(t.get("id") or t.get("team_id", ""))
                for t in items
                if t.get("id") or t.get("team_id")
            ]

    @task(2)
    def view_team_detail(self) -> None:
        """GET /api/v1/teams/{team_id} — random team detail page."""
        if not self._team_ids:
            # Fall back to overview if we haven't fetched the team list yet
            self.view_teams()
            return

        team_id = random.choice(self._team_ids)
        self.client.get(
            f"/api/v1/teams/{team_id}",
            headers=self._auth_headers(),
            # Use a static name so Locust aggregates all team detail requests together
            name="/api/v1/teams/[team_id]",
        )

    @task(1)
    def view_engineers(self) -> None:
        """GET /api/v1/engineers — engineer list."""
        self.client.get(
            "/api/v1/engineers",
            headers=self._auth_headers(),
            name="/api/v1/engineers",
        )

    @task(1)
    def view_incidents(self) -> None:
        """GET /api/v1/incidents/summary — incident summary statistics."""
        self.client.get(
            "/api/v1/incidents/summary",
            headers=self._auth_headers(),
            name="/api/v1/incidents/summary",
        )
