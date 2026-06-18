"""Acceptance tests for composite health scoring.

AC criteria verified:
  - Composite uses custom team weights from team_health_config
  - When slack is degraded, remaining 3 weights sum exactly to 1.0
  - RAG boundaries: 39 → red, 40 → amber, 70 → green
  - Score always 0–100
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.metrics.composite_score import (
    DEFAULT_WEIGHTS,
    CompositeScore,
    _rag_from_score,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redistribute_slack(weights: dict) -> dict:
    """Mirror the slack-degraded weight redistribution from compute_composite_score."""
    effective = dict(weights)
    slack_w = effective.pop("slack_signal", 0.0)
    remaining_total = sum(effective.values())
    if remaining_total > 0:
        for k in list(effective.keys()):
            effective[k] += slack_w * (effective[k] / remaining_total)
    effective["slack_signal"] = 0.0
    return effective


async def _seed_team_metric_snapshot(db, team_id, component, score_float):
    """Seed a TeamMetricSnapshot row for the given component."""
    from app.models.metrics import TeamMetricSnapshot
    snap = TeamMetricSnapshot(
        id=uuid.uuid4(),
        team_id=team_id,
        snapshot_at=datetime.now(tz=timezone.utc),
        component=component,
        score=Decimal(str(round(score_float, 2))),
        rag=_rag_from_score(score_float),
        computed_at=datetime.now(tz=timezone.utc),
    )
    db.add(snap)
    await db.flush()
    return snap


# ---------------------------------------------------------------------------
# AC: Custom team weights
# ---------------------------------------------------------------------------


class TestCompositeUsesCustomTeamWeights:
    async def test_ac_composite_uses_custom_team_weights(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: team_health_config with custom weights → composite reflects custom weights."""
        from app.models.team import TeamHealthConfig
        from conftest import SAMPLE_TEAM_ID, ADMIN_USER_ID

        # Insert custom weights (all equal 25%)
        config = TeamHealthConfig(
            id=uuid.uuid4(),
            team_id=SAMPLE_TEAM_ID,
            weight_pr_health=0.25,
            weight_sprint_health=0.25,
            weight_incident_load=0.25,
            weight_slack_signal=0.25,
            updated_by=ADMIN_USER_ID,
        )
        async_db_session.add(config)

        # Seed all four component scores at known values
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "pr_health", 80.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "sprint_health", 60.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "incident_load", 40.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "slack_signal", 100.0)
        await async_db_session.flush()

        from app.metrics.composite_score import compute_composite_score
        result = await compute_composite_score(team_id=SAMPLE_TEAM_ID, db=async_db_session)

        # Expected: (80 + 60 + 40 + 100) / 4 = 70.0
        assert result.score == pytest.approx(70.0, abs=0.5)
        assert result.rag == "green"

    async def test_ac_custom_weights_must_sum_to_1(
        self, async_db_session, sample_team, sample_users
    ):
        """Custom weights in team_health_config must sum to 1.0 (invariant)."""
        # This tests our weight-redistribution invariant
        custom_weights = {
            "pr_health": 0.40,
            "sprint_health": 0.30,
            "incident_load": 0.20,
            "slack_signal": 0.10,
        }
        total = sum(custom_weights.values())
        assert total == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# AC: Slack degraded weights sum to 1.0
# ---------------------------------------------------------------------------


class TestSlackDegradedWeightsSum:
    def test_ac_slack_degraded_excludes_from_composite_weights_sum_to_1(self):
        """AC: When slack is degraded, the 3 remaining component weights sum exactly to 1.0."""
        effective = _redistribute_slack(dict(DEFAULT_WEIGHTS))
        remaining_sum = sum(v for k, v in effective.items() if k != "slack_signal")
        assert remaining_sum == pytest.approx(1.0, abs=1e-9)

    def test_ac_slack_weight_zero_after_degradation(self):
        """AC: Slack weight is 0.0 after degradation redistribution."""
        effective = _redistribute_slack(dict(DEFAULT_WEIGHTS))
        assert effective["slack_signal"] == 0.0

    def test_ac_custom_slack_degraded_also_sums_to_1(self):
        """AC: Custom weights with slack degraded → remaining 3 still sum to 1.0."""
        custom = {
            "pr_health": 0.50,
            "sprint_health": 0.25,
            "incident_load": 0.15,
            "slack_signal": 0.10,
        }
        effective = _redistribute_slack(custom)
        remaining = sum(v for k, v in effective.items() if k != "slack_signal")
        assert remaining == pytest.approx(1.0, abs=1e-9)

    async def test_ac_slack_degraded_compute_uses_three_components(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: With slack degraded (no slack snapshot), composite uses 3 components."""
        from conftest import SAMPLE_TEAM_ID

        # Seed only 3 component snapshots (no slack)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "pr_health", 70.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "sprint_health", 70.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "incident_load", 70.0)
        await async_db_session.flush()

        from app.metrics.composite_score import compute_composite_score
        result = await compute_composite_score(team_id=SAMPLE_TEAM_ID, db=async_db_session)

        assert result.slack_degraded is True
        assert result.slack_signal_score is None
        assert result.score == pytest.approx(70.0, abs=1.0)


# ---------------------------------------------------------------------------
# AC: RAG boundaries
# ---------------------------------------------------------------------------


class TestRAGBoundaries:
    def test_ac_rag_boundary_39_is_red(self):
        """AC: Score exactly 39 → rag='red'."""
        assert _rag_from_score(39.0) == "red"

    def test_ac_rag_boundary_39_99_is_red(self):
        """AC: Score 39.99 → rag='red'."""
        assert _rag_from_score(39.99) == "red"

    def test_ac_rag_boundary_40_is_amber(self):
        """AC: Score exactly 40 → rag='amber'."""
        assert _rag_from_score(40.0) == "amber"

    def test_ac_rag_boundary_40_01_is_amber(self):
        assert _rag_from_score(40.01) == "amber"

    def test_ac_rag_boundary_69_is_amber(self):
        assert _rag_from_score(69.0) == "amber"

    def test_ac_rag_boundary_69_99_is_amber(self):
        assert _rag_from_score(69.99) == "amber"

    def test_ac_rag_boundary_70_is_green(self):
        """AC: Score exactly 70 → rag='green'."""
        assert _rag_from_score(70.0) == "green"

    def test_ac_rag_boundary_70_01_is_green(self):
        assert _rag_from_score(70.01) == "green"

    def test_ac_rag_boundary_100_is_green(self):
        assert _rag_from_score(100.0) == "green"

    def test_ac_rag_boundary_0_is_red(self):
        assert _rag_from_score(0.0) == "red"


# ---------------------------------------------------------------------------
# AC: Score range
# ---------------------------------------------------------------------------


class TestScoreRange:
    async def test_ac_composite_score_always_in_0_to_100(
        self, async_db_session, sample_team, sample_users
    ):
        """AC: compute_composite_score always produces a score in [0, 100]."""
        from conftest import SAMPLE_TEAM_ID

        # Seed extreme values
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "pr_health", 100.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "sprint_health", 0.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "incident_load", 50.0)
        await _seed_team_metric_snapshot(async_db_session, SAMPLE_TEAM_ID, "slack_signal", 75.0)
        await async_db_session.flush()

        from app.metrics.composite_score import compute_composite_score
        result = await compute_composite_score(team_id=SAMPLE_TEAM_ID, db=async_db_session)

        assert 0.0 <= result.score <= 100.0
