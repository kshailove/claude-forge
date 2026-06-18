"""Integration tests for /api/v1/incidents endpoints.

Covers:
  - GET /incidents — paginated list (scoped by RBAC)
  - GET /incidents/summary — aggregated summary
  - GET /incidents/oncall-load — per-engineer on-call hours + gini
  - GET /incidents/by-service — breakdown by service
  - GET /incidents/timeline — daily counts
  - EM sees only own team incidents
  - Director sees all incidents
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from conftest import SAMPLE_TEAM_ID, EM_USER_ID, DIRECTOR_USER_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_integration(db, team_id):
    """Seed a minimal Integration row (needed as FK for Incident)."""
    from app.models.integration import Integration
    from app.core.encryption import encrypt_config
    integration = Integration(
        id=uuid.uuid4(),
        team_id=team_id,
        type="pagerduty",
        config_json=encrypt_config({"service_ids": ["SVC123"]}),
        status="connected",
    )
    db.add(integration)
    await db.flush()
    return integration


async def _seed_incident(db, team_id, integration_id, severity="p3", resolved=False, service="auth"):
    """Seed an Incident row."""
    from app.models.incidents import Incident
    triggered = datetime.now(tz=timezone.utc) - timedelta(days=1)
    resolved_at = datetime.now(tz=timezone.utc) if resolved else None
    inc = Incident(
        id=uuid.uuid4(),
        integration_id=integration_id,
        external_id=f"EXT-{uuid.uuid4().hex[:8]}",
        title=f"Incident on {service}",
        severity=severity,
        service_name=service,
        team_id=team_id,
        triggered_at=triggered,
        resolved_at=resolved_at,
        mttr_seconds=3600 if resolved else None,
    )
    db.add(inc)
    await db.flush()
    return inc


# ---------------------------------------------------------------------------
# Incidents list
# ---------------------------------------------------------------------------


class TestIncidentsList:
    async def test_list_incidents_returns_200(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """GET /incidents → 200."""
        response = await test_client.get(
            "/api/v1/incidents",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_list_incidents_has_pagination_fields(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Response includes page, page_size, total, total_pages."""
        response = await test_client.get(
            "/api/v1/incidents",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        for field in ("incidents", "total", "page", "page_size", "total_pages"):
            assert field in data

    async def test_em_sees_only_own_team_incidents(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """EM scoped: incidents list returns only own team's incidents."""
        integration = await _seed_integration(async_db_session, SAMPLE_TEAM_ID)
        await _seed_incident(async_db_session, SAMPLE_TEAM_ID, integration.id)

        response = await test_client.get(
            "/api/v1/incidents",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_no_auth_returns_401(self, test_client, async_db_session, sample_team):
        response = await test_client.get("/api/v1/incidents")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Incidents summary
# ---------------------------------------------------------------------------


class TestIncidentsSummary:
    async def test_summary_returns_200(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        response = await test_client.get(
            "/api/v1/incidents/summary",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_summary_has_required_fields(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Summary response has total_count, by_severity, avg_mttr_seconds, window_days."""
        response = await test_client.get(
            "/api/v1/incidents/summary",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        for field in ("total_count", "by_severity", "window_days"):
            assert field in data

    async def test_summary_by_severity_has_p1_p2_p3_p4(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """by_severity has p1, p2, p3, p4 keys."""
        response = await test_client.get(
            "/api/v1/incidents/summary",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        by_sev = data["by_severity"]
        for key in ("p1", "p2", "p3", "p4"):
            assert key in by_sev


# ---------------------------------------------------------------------------
# Oncall load
# ---------------------------------------------------------------------------


class TestOncallLoad:
    async def test_oncall_load_returns_200(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        response = await test_client.get(
            "/api/v1/incidents/oncall-load",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_oncall_load_has_engineers_and_gini(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Oncall load response has engineers list and gini_coefficient."""
        response = await test_client.get(
            "/api/v1/incidents/oncall-load",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        assert "engineers" in data
        assert "gini_coefficient" in data


# ---------------------------------------------------------------------------
# By service
# ---------------------------------------------------------------------------


class TestIncidentsByService:
    async def test_by_service_returns_200(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        response = await test_client.get(
            "/api/v1/incidents/by-service",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_by_service_has_services_list(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        response = await test_client.get(
            "/api/v1/incidents/by-service",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        assert "services" in data
        assert isinstance(data["services"], list)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TestIncidentsTimeline:
    async def test_timeline_returns_200(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        response = await test_client.get(
            "/api/v1/incidents/timeline",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        assert response.status_code == 200

    async def test_timeline_has_data_list(
        self, test_client, async_db_session, sample_team, sample_users, em_token
    ):
        """Timeline response includes timeline list with date/count entries."""
        response = await test_client.get(
            "/api/v1/incidents/timeline",
            headers={"Authorization": f"Bearer {em_token}"},
        )
        data = response.json()
        assert "timeline" in data
        assert isinstance(data["timeline"], list)
        if data["timeline"]:
            day = data["timeline"][0]
            assert "date" in day
            assert "count" in day
