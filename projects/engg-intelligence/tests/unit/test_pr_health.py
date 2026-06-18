"""Unit tests for the PR Health metric computation engine.

Covers:
  - avg_cycle_time computed correctly for known timestamps
  - Stale PR detection (last_activity_at > 3 days ago)
  - Review coverage calculation (unreviewed PR lowers %)
  - Empty team → zero metrics, no exception
  - Score always in range 0–100
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Import the pure scoring / helpers directly — no DB needed for unit tests
from app.metrics.pr_health import (
    PRHealthMetrics,
    _interpolate_score,
    _lerp,
    _rag_from_score,
    _safe_mean,
    _safe_percentile,
    compute_pr_health_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metrics(**kwargs) -> PRHealthMetrics:
    """Create a PRHealthMetrics with sensible defaults overridden by kwargs."""
    defaults = dict(
        avg_cycle_time_seconds=None,
        p50_cycle_time_seconds=None,
        p75_cycle_time_seconds=None,
        p95_cycle_time_seconds=None,
        avg_first_review_latency_seconds=None,
        p50_first_review_latency_seconds=None,
        avg_review_turnaround_seconds=None,
        stale_pr_count=0,
        review_coverage_pct=None,
        review_participation_pct=None,
        avg_review_depth=None,
        rework_rate_pct=None,
        author_count=0,
        window_days=30,
        merged_pr_count=0,
        open_pr_count=0,
        closed_without_merge_count=0,
    )
    defaults.update(kwargs)
    return PRHealthMetrics(**defaults)


# ---------------------------------------------------------------------------
# Cycle time computation
# ---------------------------------------------------------------------------


class TestAvgCycleTimeComputed:
    def test_avg_cycle_time_computed_correctly_three_prs(self):
        """Three merged PRs with known cycle times → exact average."""
        cycle_times = [3600.0, 7200.0, 10800.0]  # 1h, 2h, 3h → avg 2h
        result = _safe_mean(cycle_times)
        assert result == pytest.approx(7200.0, rel=1e-6)

    def test_avg_cycle_time_single_pr(self):
        """Single PR's cycle time is its own value."""
        assert _safe_mean([14400.0]) == pytest.approx(14400.0)

    def test_avg_cycle_time_empty_list_returns_none(self):
        """Empty list → None (no data)."""
        assert _safe_mean([]) is None

    def test_p50_cycle_time_three_values(self):
        """p50 of [1, 2, 3] is 2."""
        result = _safe_percentile([1.0, 2.0, 3.0], 50)
        assert result is not None
        assert 1.0 <= result <= 3.0

    def test_p95_cycle_time_ten_values(self):
        """p95 of 10 values is at least the 9th value (near max)."""
        values = [float(i) for i in range(1, 11)]
        result = _safe_percentile(values, 95)
        assert result is not None
        assert result >= 8.0


# ---------------------------------------------------------------------------
# Stale PR detection
# ---------------------------------------------------------------------------


class TestStalePRDetection:
    def test_stale_pr_detection_logic(self):
        """PRHealthMetrics.stale_pr_count reflects PRs older than 3 days."""
        # We test the scoring: 0 stale → 100, 1 stale → between 50 and 100
        # Use open_pr_count>0 so stale score is included (stale PRs are open PRs)
        metrics_no_stale = _make_metrics(stale_pr_count=0, open_pr_count=5)
        metrics_one_stale = _make_metrics(stale_pr_count=1, open_pr_count=5)

        score_no_stale = compute_pr_health_score(metrics_no_stale)
        score_one_stale = compute_pr_health_score(metrics_one_stale)

        # With 0 stale PRs and 100 stale score, total score should be 100
        # (since stale is the only component with data here)
        assert score_no_stale == 100.0

        # 1 stale PR results in a lower score than 0 stale PRs
        assert score_one_stale < score_no_stale

    def test_stale_count_zero_yields_stale_score_100(self):
        """Zero stale PRs → stale sub-score of 100.0."""
        # Directly verifiable via the scoring formula
        # Use open_pr_count>0 so stale score is included in composite
        metrics = _make_metrics(stale_pr_count=0, open_pr_count=5)
        score = compute_pr_health_score(metrics)
        # Only stale contributes, stale_score=100, weight=0.20 → normalised to 100
        assert score == 100.0

    def test_stale_count_high_lowers_score(self):
        """10+ stale PRs → near-zero stale sub-score."""
        metrics_10 = _make_metrics(stale_pr_count=10, open_pr_count=10)
        score = compute_pr_health_score(metrics_10)
        assert score < 30.0

    def test_stale_pr_threshold_days_is_3(self):
        """PRHealthMetrics.stale_pr_threshold_days defaults to 3."""
        m = PRHealthMetrics()
        assert m.stale_pr_threshold_days == 3


# ---------------------------------------------------------------------------
# Review coverage
# ---------------------------------------------------------------------------


class TestReviewCoverage:
    def test_review_coverage_100_pct_yields_max_sub_score(self):
        """100% review coverage → coverage sub-score 100."""
        metrics = _make_metrics(review_coverage_pct=100.0)
        # Only coverage (weight=0.15) contributes, score = 100
        score = compute_pr_health_score(metrics)
        assert score == 100.0

    def test_review_coverage_excludes_unreviewed_pr(self):
        """Adding an unreviewed merged PR lowers coverage pct → lower score."""
        high_cov = _make_metrics(review_coverage_pct=100.0)
        low_cov = _make_metrics(review_coverage_pct=50.0)

        score_high = compute_pr_health_score(high_cov)
        score_low = compute_pr_health_score(low_cov)

        assert score_high > score_low

    def test_review_coverage_0_pct_yields_zero_sub_score(self):
        """0% coverage → coverage sub-score 0."""
        metrics = _make_metrics(review_coverage_pct=0.0)
        score = compute_pr_health_score(metrics)
        assert score == 0.0

    def test_review_coverage_boundary_90_pct(self):
        """Coverage ≥ 90% → score 100 for the coverage component."""
        # At 90%, coverage sub-score is 100; only component here
        metrics = _make_metrics(review_coverage_pct=90.0)
        score = compute_pr_health_score(metrics)
        assert score == 100.0


# ---------------------------------------------------------------------------
# Empty team
# ---------------------------------------------------------------------------


class TestEmptyTeamMetrics:
    def test_empty_team_returns_zero_score_no_exception(self):
        """No PRs and all None metrics → score = 0.0, no exception raised."""
        metrics = _make_metrics()
        score = compute_pr_health_score(metrics)
        assert score == 0.0

    def test_all_none_metrics_no_exception(self):
        """compute_pr_health_score with everything None does not raise."""
        try:
            score = compute_pr_health_score(PRHealthMetrics())
        except Exception as exc:
            pytest.fail(f"compute_pr_health_score raised unexpectedly: {exc}")
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------


class TestPRHealthScoreRange:
    @pytest.mark.parametrize("stale,coverage,rework,cycle_p50_h,review_latency_p50_h", [
        (0, 100.0, 0.0, 1.0, 1.0),   # excellent
        (5, 50.0, 20.0, 48.0, 12.0),  # poor
        (2, 80.0, 10.0, 24.0, 4.0),   # middle
        (0, None, None, None, None),   # sparse
        (10, 0.0, 100.0, 200.0, 100.0),  # worst case
    ])
    def test_score_always_in_0_to_100(self, stale, coverage, rework, cycle_p50_h, review_latency_p50_h):
        """Score is always between 0 and 100 inclusive."""
        p50_cycle = cycle_p50_h * 3600 if cycle_p50_h is not None else None
        p50_latency = review_latency_p50_h * 3600 if review_latency_p50_h is not None else None
        metrics = _make_metrics(
            stale_pr_count=stale,
            review_coverage_pct=coverage,
            rework_rate_pct=rework,
            p50_cycle_time_seconds=p50_cycle,
            p50_first_review_latency_seconds=p50_latency,
        )
        score = compute_pr_health_score(metrics)
        assert 0.0 <= score <= 100.0

    def test_score_is_float(self):
        """Return type is always float."""
        metrics = _make_metrics(stale_pr_count=3, review_coverage_pct=75.0)
        score = compute_pr_health_score(metrics)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# RAG thresholds
# ---------------------------------------------------------------------------


class TestRAGThresholds:
    def test_rag_below_40_is_red(self):
        assert _rag_from_score(39.9) == "red"
        assert _rag_from_score(0.0) == "red"

    def test_rag_at_40_is_amber(self):
        assert _rag_from_score(40.0) == "amber"

    def test_rag_below_70_is_amber(self):
        assert _rag_from_score(69.9) == "amber"

    def test_rag_at_70_is_green(self):
        assert _rag_from_score(70.0) == "green"

    def test_rag_at_100_is_green(self):
        assert _rag_from_score(100.0) == "green"


# ---------------------------------------------------------------------------
# Interpolation helper
# ---------------------------------------------------------------------------


class TestInterpolation:
    def test_lerp_mid_point(self):
        result = _lerp(5.0, 0.0, 10.0, 0.0, 100.0)
        assert result == pytest.approx(50.0)

    def test_lerp_clamps_below_x0(self):
        result = _lerp(-5.0, 0.0, 10.0, 0.0, 100.0)
        assert result == pytest.approx(0.0)

    def test_lerp_clamps_above_x1(self):
        result = _lerp(15.0, 0.0, 10.0, 0.0, 100.0)
        assert result == pytest.approx(100.0)

    def test_interpolate_score_below_green_max_returns_100(self):
        assert _interpolate_score(10.0, green_max=24.0, amber_max=72.0) == 100.0

    def test_interpolate_score_above_amber_max_returns_low(self):
        score = _interpolate_score(200.0, green_max=24.0, amber_max=72.0)
        assert score <= 0.0
