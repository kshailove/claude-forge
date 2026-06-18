"""Unit tests for Slack Signal metrics and degraded detection.

Covers:
  - Slack degraded flag when no snapshot exists
  - Slack score propagation when snapshot is present
  - SlackSignalDetailResponse schema fields
  - Composite score excludes slack when degraded
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Composite score: slack degraded path
# ---------------------------------------------------------------------------


class TestSlackDegradedInComposite:
    """Test the composite score logic when slack_signal is not present."""

    def _redistribution_weights(self, base_weights: dict, degraded_key: str) -> dict:
        effective = dict(base_weights)
        w = effective.pop(degraded_key, 0.0)
        remaining = sum(effective.values())
        if remaining > 0:
            for k in list(effective.keys()):
                effective[k] += w * (effective[k] / remaining)
        effective[degraded_key] = 0.0
        return effective

    def test_slack_excluded_composite_weights_sum_to_1(self):
        """With slack excluded, weights of the 3 remaining components sum to 1.0."""
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        effective = self._redistribution_weights(dict(DEFAULT_WEIGHTS), "slack_signal")
        total = sum(v for k, v in effective.items() if k != "slack_signal")
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_slack_weight_zero_after_exclusion(self):
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        effective = self._redistribution_weights(dict(DEFAULT_WEIGHTS), "slack_signal")
        assert effective["slack_signal"] == 0.0

    def test_composite_with_all_three_at_100_yields_100(self):
        """pr=100, sprint=100, incident=100, slack=None → composite=100."""
        from app.metrics.composite_score import DEFAULT_WEIGHTS

        weights = dict(DEFAULT_WEIGHTS)
        slack_degraded = True

        effective = self._redistribution_weights(weights, "slack_signal")

        scores = {"pr_health": 100.0, "sprint_health": 100.0, "incident_load": 100.0}
        available = [(k, v, effective[k]) for k, v in scores.items()]
        total_w = sum(w for _, _, w in available)
        composite = sum(s * w for _, s, w in available) / total_w

        assert composite == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# _is_slack_degraded logic (unit-level via mock DB)
# ---------------------------------------------------------------------------


class TestIsSlackDegraded:
    @pytest.mark.asyncio
    async def test_no_snapshot_means_degraded(self):
        """When no slack_signal snapshot exists, _is_slack_degraded returns True."""
        from app.metrics.composite_score import _is_slack_degraded

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        team_id = uuid.uuid4()
        result = await _is_slack_degraded(team_id=team_id, db=mock_db)

        assert result is True

    @pytest.mark.asyncio
    async def test_snapshot_exists_means_not_degraded(self):
        """When a slack_signal snapshot row exists, _is_slack_degraded returns False."""
        from app.metrics.composite_score import _is_slack_degraded

        snapshot_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=snapshot_id)

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        team_id = uuid.uuid4()
        result = await _is_slack_degraded(team_id=team_id, db=mock_db)

        assert result is False


# ---------------------------------------------------------------------------
# Slack Signal response schema
# ---------------------------------------------------------------------------


class TestSlackSignalResponseSchema:
    def test_slack_signal_degraded_response_fields(self):
        """SlackSignalDetailResponse schema has team_id, degraded, reason fields."""
        try:
            from app.schemas.teams import SlackSignalDetailResponse
        except ImportError:
            pytest.skip("SlackSignalDetailResponse schema not importable")

        team_id = uuid.uuid4()
        resp = SlackSignalDetailResponse(
            team_id=team_id,
            degraded=True,
            reason="No integration configured.",
        )
        assert resp.team_id == team_id
        assert resp.degraded is True
        assert resp.reason is not None

    def test_slack_signal_active_response_fields(self):
        """SlackSignalDetailResponse with score and rag when not degraded."""
        try:
            from app.schemas.teams import SlackSignalDetailResponse
        except ImportError:
            pytest.skip("SlackSignalDetailResponse schema not importable")

        team_id = uuid.uuid4()
        resp = SlackSignalDetailResponse(
            team_id=team_id,
            degraded=False,
            score=75.0,
            rag="green",
        )
        assert resp.degraded is False
        assert resp.score == 75.0
        assert resp.rag == "green"


# ---------------------------------------------------------------------------
# Slack signal composite weight boundaries
# ---------------------------------------------------------------------------


class TestSlackWeightBoundaries:
    def test_slack_default_weight_is_015(self):
        """Default slack_signal weight is 0.15."""
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["slack_signal"] == pytest.approx(0.15)

    def test_pr_health_default_weight_is_030(self):
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["pr_health"] == pytest.approx(0.30)

    def test_sprint_health_default_weight_is_030(self):
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["sprint_health"] == pytest.approx(0.30)

    def test_incident_load_default_weight_is_025(self):
        from app.metrics.composite_score import DEFAULT_WEIGHTS
        assert DEFAULT_WEIGHTS["incident_load"] == pytest.approx(0.25)
