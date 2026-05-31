"""Tests for src/scoring.py — written first (TDD)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.scoring import (
    COOLDOWN_FACTOR,
    StockSignals,
    _in_cooldown,
    _news_score,
    _results_score,
    _staleness_score,
    compute_score,
)


# ---------------------------------------------------------------------------
# _results_score
# ---------------------------------------------------------------------------

class TestResultsScore:
    def test_none_filing_returns_zero(self):
        assert _results_score(None, date(2026, 1, 15), 40) == 0.0

    def test_day_zero_returns_one(self):
        d = date(2026, 1, 15)
        assert _results_score(d, d, 40) == pytest.approx(1.0)

    def test_half_decay(self):
        filing = date(2026, 1, 1)
        as_of = date(2026, 1, 21)  # 20 days later; decay=40 → 0.5
        assert _results_score(filing, as_of, 40) == pytest.approx(0.5)

    def test_full_decay_returns_zero(self):
        filing = date(2026, 1, 1)
        as_of = date(2026, 1, 1) + timedelta(days=40)
        assert _results_score(filing, as_of, 40) == pytest.approx(0.0)

    def test_past_decay_returns_zero(self):
        filing = date(2025, 1, 1)
        as_of = date(2026, 1, 1)  # well past decay window
        assert _results_score(filing, as_of, 40) == pytest.approx(0.0)

    def test_future_filing_returns_zero(self):
        # filing date in the future should not produce a positive score
        filing = date(2026, 2, 1)
        as_of = date(2026, 1, 15)
        assert _results_score(filing, as_of, 40) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _news_score  — relative, never negative
# ---------------------------------------------------------------------------

class TestNewsScore:
    def test_zero_news_returns_zero(self):
        assert _news_score(0, 10.0) == pytest.approx(0.0)

    def test_zero_news_zero_baseline(self):
        assert _news_score(0, 0.0) == pytest.approx(0.0)

    def test_no_baseline_small_count(self):
        # 3 articles with no history → 1.0
        assert _news_score(3, 0.0) == pytest.approx(1.0)

    def test_no_baseline_fewer_than_three(self):
        result = _news_score(1, 0.0)
        assert 0.0 < result < 1.0

    def test_at_baseline_returns_half(self):
        # ratio=1.0 → 1.0/2.0 = 0.5
        assert _news_score(10, 10.0) == pytest.approx(0.5)

    def test_double_baseline_returns_one(self):
        assert _news_score(20, 10.0) == pytest.approx(1.0)

    def test_more_than_double_capped_at_one(self):
        assert _news_score(100, 10.0) == pytest.approx(1.0)

    def test_below_baseline_still_positive(self):
        # 5 articles, baseline=10 → ratio=0.5 → score=0.25
        result = _news_score(5, 10.0)
        assert result == pytest.approx(0.25)
        assert result >= 0.0

    def test_relative_micro_cap_vs_large_cap(self):
        # micro-cap: 0→3 (baseline≈0)
        micro = _news_score(3, 0.0)
        # large-cap: 40→80 (ratio=2.0)
        large = _news_score(80, 40.0)
        # Both should score at maximum (1.0)
        assert micro == pytest.approx(1.0)
        assert large == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _staleness_score
# ---------------------------------------------------------------------------

class TestStalenessScore:
    def test_never_analyzed_returns_one(self):
        assert _staleness_score(None, date(2026, 1, 1)) == pytest.approx(1.0)

    def test_analyzed_today_returns_zero(self):
        d = date(2026, 1, 1)
        assert _staleness_score(d, d) == pytest.approx(0.0)

    def test_analyzed_in_future_returns_zero(self):
        # Edge case: last_analyzed is in the future
        future = date(2026, 2, 1)
        assert _staleness_score(future, date(2026, 1, 1)) == pytest.approx(0.0)

    def test_half_max_days(self):
        last = date(2026, 1, 1)
        as_of = date(2026, 1, 1) + timedelta(days=90)  # 90/180 = 0.5
        result = _staleness_score(last, as_of, max_days=180)
        assert result == pytest.approx(0.5)

    def test_saturates_at_one(self):
        last = date(2024, 1, 1)
        as_of = date(2026, 1, 1)  # > 180 days
        assert _staleness_score(last, as_of, max_days=180) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _in_cooldown
# ---------------------------------------------------------------------------

class TestInCooldown:
    def test_never_analyzed_not_in_cooldown(self):
        assert _in_cooldown(None, date(2026, 1, 1), 14) is False

    def test_analyzed_yesterday_in_cooldown(self):
        yesterday = date(2026, 1, 14)
        assert _in_cooldown(yesterday, date(2026, 1, 15), 14) is True

    def test_analyzed_exactly_cooldown_days_ago_not_in_cooldown(self):
        last = date(2026, 1, 1)
        as_of = date(2026, 1, 1) + timedelta(days=14)
        assert _in_cooldown(last, as_of, 14) is False

    def test_analyzed_long_ago_not_in_cooldown(self):
        last = date(2025, 1, 1)
        assert _in_cooldown(last, date(2026, 1, 1), 14) is False


# ---------------------------------------------------------------------------
# compute_score — integration
# ---------------------------------------------------------------------------

class TestComputeScore:
    _AS_OF = date(2026, 5, 31)
    _WEIGHTS = dict(
        weights_results=0.4,
        weights_news=0.3,
        weights_staleness=0.3,
        results_decay_days=40,
        cooldown_days=14,
    )

    def _signals(self, **kwargs) -> StockSignals:
        defaults = dict(
            src_symbol="TEST",
            last_filing_date=None,
            recent_news_count=0,
            news_baseline=0.0,
            last_analyzed=None,
        )
        defaults.update(kwargs)
        return StockSignals(**defaults)

    def test_never_analyzed_no_news_no_filing(self):
        sig = self._signals()
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        # staleness=1.0, rest=0 → raw=0.3
        assert score.total_score == pytest.approx(0.3)
        assert score.in_cooldown is False

    def test_fresh_filing_bumps_results(self):
        sig = self._signals(last_filing_date=self._AS_OF)
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        # results=1.0, staleness=1.0, news=0 → 0.4+0.3=0.7
        assert score.total_score == pytest.approx(0.7)

    def test_cooldown_reduces_score(self):
        yesterday = self._AS_OF - timedelta(days=1)
        sig = self._signals(last_analyzed=yesterday)
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        assert score.in_cooldown is True
        assert score.total_score < 0.1  # near-zero

    def test_cooldown_factor_applied(self):
        yesterday = self._AS_OF - timedelta(days=1)
        sig = self._signals(last_analyzed=yesterday, last_filing_date=self._AS_OF)
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        raw = 0.4 * 1.0 + 0.3 * 0.0 + 0.3 * 0.0  # staleness≈0 (analyzed yesterday)
        expected = raw * COOLDOWN_FACTOR
        assert score.total_score == pytest.approx(expected, abs=0.01)

    def test_normalisation_relative_news(self):
        sig = self._signals(recent_news_count=20, news_baseline=10.0)
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        # news_score=1.0 → news contribution = 0.3; staleness=1.0 → 0.3; total=0.6
        assert score.news_component == pytest.approx(1.0)
        assert score.staleness_component == pytest.approx(1.0)
        assert score.total_score == pytest.approx(0.6)

    def test_score_capped_below_one(self):
        sig = self._signals(
            last_filing_date=self._AS_OF,
            recent_news_count=100,
            news_baseline=1.0,
            last_analyzed=None,
        )
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        assert score.total_score <= 1.0 + 1e-9

    def test_reason_populated(self):
        sig = self._signals(last_filing_date=self._AS_OF)
        score = compute_score(sig, self._AS_OF, **self._WEIGHTS)
        assert len(score.reason) > 0
