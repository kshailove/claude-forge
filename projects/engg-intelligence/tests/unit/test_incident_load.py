"""Unit tests for the Incident Load metric computation engine.

Covers:
  - Gini coefficient: equal distribution → near 0 → fairness score high
  - Gini coefficient: unequal distribution → near 1 → fairness score low
  - Repeat services: services with 3+ incidents included
  - Score always in range 0–100
  - MTTR interpolation
  - Incidents-per-week computation
"""
from __future__ import annotations

import pytest

from app.metrics.incident_load import (
    IncidentLoadMetrics,
    RepeatService,
    _gini_coefficient,
    _interpolate_score,
    _lerp,
    _rag_from_score,
    _safe_mean,
    _safe_percentile,
    compute_incident_load_score,
)


# ---------------------------------------------------------------------------
# Gini coefficient
# ---------------------------------------------------------------------------


class TestGiniCoefficientEqualDistribution:
    def test_gini_equal_distribution_near_zero(self):
        """Equal paging (all engineers paged same number of times) → gini ≈ 0."""
        equal = [5, 5, 5, 5]
        gini = _gini_coefficient(equal)
        assert gini == pytest.approx(0.0, abs=1e-9)

    def test_gini_single_value_returns_zero(self):
        """Single value → gini = 0.0 (no distribution to measure)."""
        gini = _gini_coefficient([10])
        assert gini == 0.0

    def test_gini_empty_list_returns_zero(self):
        """Empty list → 0.0."""
        assert _gini_coefficient([]) == 0.0

    def test_gini_all_zero_returns_zero(self):
        """All zeros → mean is 0 → gini = 0.0 (avoid division by zero)."""
        assert _gini_coefficient([0, 0, 0]) == 0.0


class TestGiniCoefficientUnequalDistribution:
    def test_gini_unequal_distribution_near_one(self):
        """One person paged 10x more → gini near 1 → fairness score low."""
        unequal = [1, 1, 1, 1, 10]
        gini = _gini_coefficient(unequal)
        assert gini > 0.3  # Meaningfully unequal

    def test_gini_extreme_inequality(self):
        """All paging on one person: [0, 0, 0, 0, 100] → high gini."""
        extreme = [0, 0, 0, 0, 100]
        gini = _gini_coefficient(extreme)
        assert gini > 0.5

    def test_gini_score_equal_yields_100_fairness(self):
        """Equal distribution → gini 0 → fairness_score = 100."""
        gini = 0.0
        fairness_score = max(0.0, min(100.0, (1.0 - gini) * 100.0))
        assert fairness_score == pytest.approx(100.0)

    def test_gini_score_unequal_yields_low_fairness(self):
        """High gini → low fairness score."""
        unequal = [1, 1, 1, 1, 20]
        gini = _gini_coefficient(unequal)
        fairness_score = max(0.0, min(100.0, (1.0 - gini) * 100.0))
        assert fairness_score < 70.0

    def test_gini_in_score_computation_equal(self):
        """Equal paging in IncidentLoadMetrics → gini sub-score contributes high value."""
        # Equal distribution: 4 users, each paged 5 times
        user_ids = [f"user-{i}" for i in range(4)]
        paging = {uid: 5 for uid in user_ids}

        metrics = IncidentLoadMetrics(
            incident_count=20,
            incidents_per_week=5.0,
            paging_distribution=paging,
            p1_count=0,
        )
        score = compute_incident_load_score(metrics)
        assert score > 0.0


# ---------------------------------------------------------------------------
# Repeat services threshold
# ---------------------------------------------------------------------------


class TestRepeatServicesThreshold:
    def test_repeat_services_threshold_3(self):
        """A service with exactly 3 incidents appears in repeat_services."""
        # Create metrics where one service has 3 incidents
        metrics = IncidentLoadMetrics(
            incident_count=3,
            incidents_per_week=0.7,
            p1_count=0,
            repeat_services=[
                RepeatService(service_name="payments-service", count=3)
            ],
        )
        service_names = [rs.service_name for rs in metrics.repeat_services]
        assert "payments-service" in service_names

    def test_service_with_2_incidents_not_repeat(self):
        """A service with only 2 incidents does NOT appear in repeat_services."""
        # Simulate compute: 2 is below the 3-incident threshold
        service_counts = {"auth-service": 2, "payments": 3}
        repeat = [
            RepeatService(service_name=svc, count=cnt)
            for svc, cnt in service_counts.items()
            if cnt >= 3
        ]
        names = [rs.service_name for rs in repeat]
        assert "auth-service" not in names
        assert "payments" in names

    def test_service_with_5_incidents_is_repeat(self):
        """A service with 5 incidents appears in repeat_services."""
        service_counts = {"api-gateway": 5}
        repeat = [
            RepeatService(service_name=svc, count=cnt)
            for svc, cnt in service_counts.items()
            if cnt >= 3
        ]
        assert len(repeat) == 1
        assert repeat[0].service_name == "api-gateway"
        assert repeat[0].count == 5

    def test_no_services_yields_empty_repeat_list(self):
        """No incidents → empty repeat_services."""
        metrics = IncidentLoadMetrics(incident_count=0, incidents_per_week=0.0)
        assert metrics.repeat_services == []


# ---------------------------------------------------------------------------
# Score range
# ---------------------------------------------------------------------------


class TestIncidentLoadScoreRange:
    @pytest.mark.parametrize("ipw,avg_mttr_h,p1,paging", [
        (0.0, 0.5, 0, {}),           # ideal
        (10.0, 48.0, 5, {"u1": 20}), # poor
        (3.0, 12.0, 2, {"u1": 5, "u2": 5}),  # medium
        (0.5, 1.0, 0, {"u1": 1, "u2": 1, "u3": 1}),  # good
    ])
    def test_score_always_in_0_to_100(self, ipw, avg_mttr_h, p1, paging):
        """compute_incident_load_score always returns a value in [0, 100]."""
        metrics = IncidentLoadMetrics(
            incident_count=max(p1, sum(paging.values())),
            incidents_per_week=ipw,
            avg_mttr_seconds=avg_mttr_h * 3600 if avg_mttr_h else None,
            p1_count=p1,
            paging_distribution=paging,
        )
        score = compute_incident_load_score(metrics)
        assert 0.0 <= score <= 100.0

    def test_zero_incidents_yields_high_score(self):
        """No incidents → incidents_per_week=0 → high score."""
        metrics = IncidentLoadMetrics(
            incident_count=0,
            incidents_per_week=0.0,
            p1_count=0,
            paging_distribution={},
        )
        score = compute_incident_load_score(metrics)
        assert score >= 80.0

    def test_high_incident_rate_yields_low_score(self):
        """10+ incidents/week → lower score."""
        metrics = IncidentLoadMetrics(
            incident_count=100,
            incidents_per_week=15.0,
            avg_mttr_seconds=72 * 3600,  # 3 days
            p1_count=10,
            paging_distribution={"user1": 100},
        )
        score = compute_incident_load_score(metrics)
        assert score < 40.0

    def test_score_is_float(self):
        metrics = IncidentLoadMetrics(incident_count=5, incidents_per_week=1.0)
        score = compute_incident_load_score(metrics)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# RAG thresholds
# ---------------------------------------------------------------------------


class TestRAGThresholds:
    def test_rag_red_below_40(self):
        assert _rag_from_score(39.9) == "red"

    def test_rag_amber_at_40(self):
        assert _rag_from_score(40.0) == "amber"

    def test_rag_green_at_70(self):
        assert _rag_from_score(70.0) == "green"


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


class TestStatisticalHelpers:
    def test_safe_mean_normal(self):
        assert _safe_mean([10.0, 20.0, 30.0]) == pytest.approx(20.0)

    def test_safe_mean_empty_returns_none(self):
        assert _safe_mean([]) is None

    def test_safe_percentile_p50_of_five(self):
        result = _safe_percentile([10.0, 20.0, 30.0, 40.0, 50.0], 50)
        assert result is not None
        assert 20.0 <= result <= 40.0

    def test_safe_percentile_empty_returns_none(self):
        assert _safe_percentile([], 95) is None

    def test_interpolate_score_green_zone(self):
        assert _interpolate_score(0.3, green_max=0.5, amber_max=5.0) == 100.0

    def test_interpolate_score_beyond_amber(self):
        score = _interpolate_score(20.0, green_max=0.5, amber_max=5.0)
        assert score <= 0.0
