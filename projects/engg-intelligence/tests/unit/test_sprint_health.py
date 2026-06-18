"""Unit tests for the Sprint Health metric computation engine.

Covers:
  - setup_required flag returns score 0
  - Completion % scoring bands
  - Carry-over rate scoring
  - Blocked ticket scoring
  - Velocity trend direction scoring
  - Score always in [0, 100]
  - RAG boundaries
"""
from __future__ import annotations

import pytest

from app.metrics.sprint_health import (
    SprintHealthMetrics,
    _interpolate_score,
    _lerp,
    _rag_from_score,
    _velocity_trend_score,
    compute_sprint_health_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metrics(**kwargs) -> SprintHealthMetrics:
    defaults = dict(
        current_sprint_completion_pct=None,
        carry_over_rate_pct=None,
        scope_creep_pct=None,
        blocked_ticket_count=0,
        velocity_trend_points=[],
        setup_required=False,
    )
    defaults.update(kwargs)
    return SprintHealthMetrics(**defaults)


# ---------------------------------------------------------------------------
# Setup required
# ---------------------------------------------------------------------------


class TestSetupRequired:
    def test_setup_required_returns_zero_score(self):
        """When no sprints are configured, score must be 0.0."""
        metrics = _make_metrics(setup_required=True)
        score = compute_sprint_health_score(metrics)
        assert score == 0.0

    def test_no_sub_scores_returns_zero(self):
        """All metrics None and setup_required=False → score 0.0 (no sub-scores)."""
        metrics = _make_metrics()
        score = compute_sprint_health_score(metrics)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Completion % scoring
# ---------------------------------------------------------------------------


class TestCompletionPctScoring:
    def test_completion_80_pct_yields_100_sub_score(self):
        """≥80% completion → completion sub-score of 100."""
        metrics = _make_metrics(current_sprint_completion_pct=80.0)
        score = compute_sprint_health_score(metrics)
        assert score == pytest.approx(100.0)

    def test_completion_100_pct_yields_100(self):
        metrics = _make_metrics(current_sprint_completion_pct=100.0)
        assert compute_sprint_health_score(metrics) == pytest.approx(100.0)

    def test_completion_50_pct_yields_amber_sub_score(self):
        """50% completion → sub-score of 50 (boundary of green/amber interpolation)."""
        metrics = _make_metrics(current_sprint_completion_pct=50.0)
        score = compute_sprint_health_score(metrics)
        # Only completion contributes, score = 50
        assert score == pytest.approx(50.0)

    def test_completion_0_pct_yields_0(self):
        metrics = _make_metrics(current_sprint_completion_pct=0.0)
        score = compute_sprint_health_score(metrics)
        assert score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Carry-over rate
# ---------------------------------------------------------------------------


class TestCarryOverRate:
    def test_zero_carry_over_yields_100_sub_score(self):
        """0% carry-over → sub-score 100."""
        metrics = _make_metrics(carry_over_rate_pct=0.0)
        score = compute_sprint_health_score(metrics)
        assert score == pytest.approx(100.0)

    def test_low_carry_over_green(self):
        """≤10% carry-over → sub-score 100 (green threshold)."""
        metrics = _make_metrics(carry_over_rate_pct=8.0)
        score = compute_sprint_health_score(metrics)
        assert score == pytest.approx(100.0)

    def test_high_carry_over_lowers_score(self):
        """50% carry-over → lower score than 10%."""
        low = compute_sprint_health_score(_make_metrics(carry_over_rate_pct=5.0))
        high = compute_sprint_health_score(_make_metrics(carry_over_rate_pct=50.0))
        assert low > high


# ---------------------------------------------------------------------------
# Blocked ticket scoring
# ---------------------------------------------------------------------------


class TestBlockedTicketScoring:
    def test_no_blocked_tickets_yields_100_sub_score(self):
        metrics = _make_metrics(blocked_ticket_count=0, current_sprint_id="sprint-1")
        score = compute_sprint_health_score(metrics)
        assert score == pytest.approx(100.0)

    def test_one_blocked_ticket_lowers_score(self):
        none_blocked = compute_sprint_health_score(_make_metrics(blocked_ticket_count=0, current_sprint_id="sprint-1"))
        one_blocked = compute_sprint_health_score(_make_metrics(blocked_ticket_count=1, current_sprint_id="sprint-1"))
        assert one_blocked < none_blocked

    def test_many_blocked_tickets_near_zero(self):
        metrics = _make_metrics(blocked_ticket_count=10, current_sprint_id="sprint-1")
        score = compute_sprint_health_score(metrics)
        assert score < 20.0


# ---------------------------------------------------------------------------
# Velocity trend
# ---------------------------------------------------------------------------


class TestVelocityTrend:
    def test_velocity_trend_increasing_returns_100(self):
        """Last sprint velocity well above median → score 100."""
        points = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0]
        score = _velocity_trend_score(points)
        assert score == 100.0

    def test_velocity_trend_flat_returns_70(self):
        """Flat velocity (last ≈ median within 10%) → score 70."""
        points = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        score = _velocity_trend_score(points)
        assert score == pytest.approx(70.0)

    def test_velocity_trend_declining_returns_low(self):
        """Strongly declining velocity → score between 0 and 70."""
        points = [20.0, 20.0, 20.0, 10.0, 8.0, 2.0]
        score = _velocity_trend_score(points)
        assert 0.0 <= score < 70.0

    def test_velocity_trend_single_point_returns_70(self):
        """Single point → neutral score 70."""
        score = _velocity_trend_score([10.0])
        assert score == pytest.approx(70.0)

    def test_velocity_trend_empty_returns_70(self):
        """Empty list → neutral score 70."""
        score = _velocity_trend_score([])
        assert score == pytest.approx(70.0)

    def test_velocity_trend_zero_median_returns_70(self):
        """Zero median (all zeros) → neutral 70."""
        score = _velocity_trend_score([0.0, 0.0, 0.0])
        assert score == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------


class TestSprintHealthScoreRange:
    @pytest.mark.parametrize("completion,carry_over,scope_creep,blocked,velocity", [
        (100.0, 0.0, 0.0, 0, [10, 10, 12]),   # excellent
        (20.0, 60.0, 50.0, 8, [10, 8, 5]),    # poor
        (65.0, 20.0, 15.0, 2, [10, 10, 10]),  # medium
        (None, None, None, 0, []),              # no data
    ])
    def test_score_always_in_0_to_100(self, completion, carry_over, scope_creep, blocked, velocity):
        metrics = _make_metrics(
            current_sprint_completion_pct=completion,
            carry_over_rate_pct=carry_over,
            scope_creep_pct=scope_creep,
            blocked_ticket_count=blocked,
            velocity_trend_points=[float(v) for v in velocity],
        )
        score = compute_sprint_health_score(metrics)
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# RAG thresholds
# ---------------------------------------------------------------------------


class TestRAGThresholds:
    def test_rag_at_39_is_red(self):
        assert _rag_from_score(39.0) == "red"

    def test_rag_at_40_is_amber(self):
        assert _rag_from_score(40.0) == "amber"

    def test_rag_at_70_is_green(self):
        assert _rag_from_score(70.0) == "green"
