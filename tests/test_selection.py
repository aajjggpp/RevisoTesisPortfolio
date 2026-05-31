"""Tests for src/selection.py — written first (TDD)."""
from __future__ import annotations

import pytest

from src.scoring import StockScore
from src.selection import SelectionResult, select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_score(sym: str, total: float, reason: str = "test") -> StockScore:
    return StockScore(
        src_symbol=sym,
        total_score=total,
        results_component=0.0,
        news_component=0.0,
        staleness_component=0.0,
        in_cooldown=False,
        reason=reason,
    )


SCORES = [
    _make_score("NVDA.O",  0.9),
    _make_score("ADBE.O",  0.7),
    _make_score("MSFT.O",  0.5),
    _make_score("META.O",  0.4),
    _make_score("GOOG.O",  0.3),
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSelect:
    def test_no_pin_selects_highest_score(self):
        result = select(SCORES)
        assert result.selected.src_symbol == "NVDA.O"
        assert result.pin_used is False

    def test_top3_contains_three_entries(self):
        result = select(SCORES)
        assert len(result.top3) == 3

    def test_top3_sorted_descending(self):
        result = select(SCORES)
        totals = [s.total_score for s in result.top3]
        assert totals == sorted(totals, reverse=True)

    def test_pin_overrides_selection(self):
        result = select(SCORES, pin="ADBE.O")
        assert result.selected.src_symbol == "ADBE.O"
        assert result.pin_used is True

    def test_pin_with_low_score_still_selected(self):
        result = select(SCORES, pin="GOOG.O")
        assert result.selected.src_symbol == "GOOG.O"
        assert result.pin_used is True

    def test_pin_included_in_top3(self):
        # GOOG.O is 5th by score; pin should force it into top3
        result = select(SCORES, pin="GOOG.O")
        symbols = [s.src_symbol for s in result.top3]
        assert "GOOG.O" in symbols

    def test_top3_includes_at_most_three(self):
        result = select(SCORES, pin="GOOG.O")
        assert len(result.top3) <= 3

    def test_invalid_pin_raises_value_error(self):
        with pytest.raises(ValueError, match="not found"):
            select(SCORES, pin="UNKNOWN.X")

    def test_empty_scores_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            select([])

    def test_single_entry_returns_it(self):
        single = [_make_score("ONLY.X", 0.5)]
        result = select(single)
        assert result.selected.src_symbol == "ONLY.X"
        assert len(result.top3) == 1

    def test_top3_with_fewer_than_three_scores(self):
        two = SCORES[:2]
        result = select(two)
        assert len(result.top3) == 2

    def test_pin_none_treated_as_no_pin(self):
        result = select(SCORES, pin=None)
        assert result.selected.src_symbol == "NVDA.O"
        assert result.pin_used is False
