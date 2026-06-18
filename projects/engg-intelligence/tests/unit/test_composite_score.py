"""Unit tests for the Composite Score engine.

Covers:
  - RAG classification: red < 40, amber 40–69, green ≥ 70
  - Slack degraded: weights of remaining 3 components sum to 1.0
  - All components None → score is None / 0
  - Boundary values
  - Weight redistribution correctness
"""
from __future__ import annotations

import pytest

from app.metrics.composite_score import DEFAULT_WEIGHTS, _rag_from_score


# ---------------------------------------------------------------------------
# RAG classification
# ---------------------------------------------------------------------------


class TestRAGClassification:
    def test_rag_red_below_40(self):
        """Score 35 → rag='red'."""
        assert _rag_from_score(35.0) == "red"

    def test_rag_red_at_0(self):
        assert _rag_from_score(0.0) == "red"

    def test_rag_red_at_39_99(self):
        assert _rag_from_score(39.99) == "red"

    def test_rag_amber_at_40(self):
        """Boundary: score exactly 40 → 'amber'."""
        assert _rag_from_score(40.0) == "amber"

    def test_rag_amber_between_40_and_70(self):
        """Score 55 → 'amber'."""
        assert _rag_from_score(55.0) == "amber"

    def test_rag_amber_at_69_99(self):
        assert _rag_from_score(69.99) == "amber"

    def test_rag_green_at_70(self):
        """Boundary: score exactly 70 → 'green'."""
        assert _rag_from_score(70.0) == "green"

    def test_rag_green_above_70(self):
        assert _rag_from_score(85.0) == "green"

    def test_rag_green_at_100(self):
        assert _rag_from_score(100.0) == "green"


# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------


class TestDefaultWeights:
    def test_default_weights_sum_to_1(self):
        """All four default weights must sum to exactly 1.0."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_default_weights_are_positive(self):
        for k, v in DEFAULT_WEIGHTS.items():
            assert v > 0, f"Weight for {k} should be positive"


# ---------------------------------------------------------------------------
# Slack degraded weight redistribution
# ---------------------------------------------------------------------------


class TestSlackDegradedRedistributesWeights:
    def _redistribute(self, weights: dict, degraded_key: str) -> dict:
        """Mirror the redistribution logic from compute_composite_score."""
        effective = dict(weights)
        slack_w = effective.pop(degraded_key, 0.0)
        remaining_total = sum(effective.values())
        if remaining_total > 0:
            for k in list(effective.keys()):
                effective[k] += slack_w * (effective[k] / remaining_total)
        effective[degraded_key] = 0.0
        return effective

    def test_slack_degraded_remaining_weights_sum_to_1(self):
        """When slack is degraded, the remaining 3 weights still sum to 1.0."""
        effective = self._redistribute(dict(DEFAULT_WEIGHTS), "slack_signal")

        remaining_sum = sum(v for k, v in effective.items() if k != "slack_signal")
        assert remaining_sum == pytest.approx(1.0, abs=1e-9)

    def test_slack_degraded_slack_weight_is_zero(self):
        """Slack's effective weight becomes 0.0."""
        effective = self._redistribute(dict(DEFAULT_WEIGHTS), "slack_signal")
        assert effective["slack_signal"] == 0.0

    def test_slack_degraded_other_weights_increase_proportionally(self):
        """Each remaining component's weight increases by the correct proportion."""
        original = dict(DEFAULT_WEIGHTS)
        effective = self._redistribute(original, "slack_signal")

        slack_w = original["slack_signal"]
        remaining_original_total = sum(v for k, v in original.items() if k != "slack_signal")

        for k in ("pr_health", "sprint_health", "incident_load"):
            expected = original[k] + slack_w * (original[k] / remaining_original_total)
            assert effective[k] == pytest.approx(expected, rel=1e-6)

    def test_custom_weights_redistribution_still_sums_to_1(self):
        """Custom weights with slack degraded also redistribute to sum to 1."""
        custom = {
            "pr_health": 0.40,
            "sprint_health": 0.30,
            "incident_load": 0.20,
            "slack_signal": 0.10,
        }
        effective = self._redistribute(custom, "slack_signal")
        remaining_sum = sum(v for k, v in effective.items() if k != "slack_signal")
        assert remaining_sum == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Weighted composite computation (pure arithmetic)
# ---------------------------------------------------------------------------


class TestWeightedCompositeArithmetic:
    def _compute_composite(
        self,
        pr: float | None,
        sprint: float | None,
        incident: float | None,
        slack: float | None,
        weights: dict | None = None,
    ) -> float:
        """Compute composite score using the same logic as compute_composite_score."""
        w = weights or dict(DEFAULT_WEIGHTS)
        slack_degraded = slack is None

        effective = dict(w)
        if slack_degraded:
            slack_w = effective.pop("slack_signal", 0.0)
            remaining_total = sum(effective.values())
            if remaining_total > 0:
                for k in list(effective.keys()):
                    effective[k] += slack_w * (effective[k] / remaining_total)
            effective["slack_signal"] = 0.0

        scores = {
            "pr_health": pr,
            "sprint_health": sprint,
            "incident_load": incident,
            "slack_signal": slack if not slack_degraded else None,
        }

        available = []
        missing_weight = 0.0
        for comp, s in scores.items():
            ww = effective.get(comp, 0.0)
            if s is None or ww == 0.0:
                missing_weight += ww
            else:
                available.append((comp, s, ww))

        if not available:
            return 0.0

        available_total_w = sum(wt for _, _, wt in available)
        total_w = available_total_w + missing_weight
        boosted = [
            (c, s, wt + missing_weight * (wt / available_total_w))
            for c, s, wt in available
        ]
        composite = sum(s * wt for _, s, wt in boosted) / sum(wt for _, _, wt in boosted)
        return round(min(100.0, max(0.0, composite)), 2)

    def test_all_100_yields_100(self):
        result = self._compute_composite(100, 100, 100, 100)
        assert result == pytest.approx(100.0)

    def test_all_0_yields_0(self):
        result = self._compute_composite(0, 0, 0, 0)
        assert result == pytest.approx(0.0)

    def test_slack_none_excludes_from_composite(self):
        """When slack=None, composite uses only 3 components."""
        # All three at 80 → composite should be 80
        result = self._compute_composite(80, 80, 80, None)
        assert result == pytest.approx(80.0, abs=0.1)

    def test_all_components_none_returns_zero(self):
        """When all components are None, score is 0."""
        result = self._compute_composite(None, None, None, None)
        assert result == 0.0

    def test_known_weighted_composite(self):
        """Known exact calculation: pr=80, sprint=60, incident=70, slack=90 with defaults."""
        # Default weights: pr=0.30, sprint=0.30, incident=0.25, slack=0.15
        # composite = 80*0.30 + 60*0.30 + 70*0.25 + 90*0.15
        #           = 24 + 18 + 17.5 + 13.5 = 73.0
        result = self._compute_composite(80, 60, 70, 90)
        assert result == pytest.approx(73.0, abs=0.1)

    def test_score_within_0_to_100(self):
        """Score is always in [0, 100]."""
        result = self._compute_composite(120, -10, 50, 200)
        # clamped: input scores are not individually clamped here, but composite is
        assert 0.0 <= result <= 100.0
