"""Tests for src/news.py — written first (TDD).
Network calls are mocked via unittest.mock so tests are deterministic.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.news import (
    NewsItem,
    _parse_published,
    count_recent_news,
    fetch_news,
    format_news_context,
    update_baseline,
)


# ---------------------------------------------------------------------------
# _parse_published
# ---------------------------------------------------------------------------

class TestParsePublished:
    def test_valid_published_parsed(self):
        import time
        entry = MagicMock()
        entry.published_parsed = time.strptime("2026-01-15", "%Y-%m-%d")
        result = _parse_published(entry)
        assert result == date(2026, 1, 15)

    def test_none_published_parsed_returns_none(self):
        entry = MagicMock()
        entry.published_parsed = None
        assert _parse_published(entry) is None

    def test_missing_attribute_returns_none(self):
        entry = object()  # no attributes
        assert _parse_published(entry) is None


# ---------------------------------------------------------------------------
# count_recent_news
# ---------------------------------------------------------------------------

class TestCountRecentNews:
    _AS_OF = date(2026, 5, 31)

    def _item(self, days_ago: int) -> NewsItem:
        return NewsItem(title="t", published=self._AS_OF - timedelta(days=days_ago))

    def test_all_within_window(self):
        items = [self._item(0), self._item(5), self._item(13)]
        assert count_recent_news(items, 14, self._AS_OF) == 3

    def test_some_outside_window(self):
        items = [self._item(0), self._item(15), self._item(30)]
        assert count_recent_news(items, 14, self._AS_OF) == 1

    def test_none_in_window(self):
        items = [self._item(20), self._item(50)]
        assert count_recent_news(items, 14, self._AS_OF) == 0

    def test_item_with_none_date_not_counted(self):
        items = [NewsItem(title="undated", published=None)]
        assert count_recent_news(items, 14, self._AS_OF) == 0

    def test_empty_list(self):
        assert count_recent_news([], 14, self._AS_OF) == 0


# ---------------------------------------------------------------------------
# update_baseline
# ---------------------------------------------------------------------------

class TestUpdateBaseline:
    def test_zero_baseline_bootstraps_to_count(self):
        assert update_baseline(0.0, 5) == pytest.approx(5.0)

    def test_ema_update(self):
        # α=0.3: 0.3 * 10 + 0.7 * 20 = 3 + 14 = 17
        result = update_baseline(20.0, 10)
        assert result == pytest.approx(17.0)

    def test_negative_baseline_treated_as_zero(self):
        result = update_baseline(-1.0, 4)
        assert result == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# fetch_news — mocked
# ---------------------------------------------------------------------------

class TestFetchNews:
    def _make_feed(self, titles_dates: list) -> MagicMock:
        """Return a mock feedparser result with entries."""
        import time
        entries = []
        for title, days_ago in titles_dates:
            e = MagicMock()
            e.title = title
            e.summary = ""
            if days_ago is not None:
                d = date(2026, 5, 31) - timedelta(days=days_ago)
                e.published_parsed = time.strptime(d.isoformat(), "%Y-%m-%d")
            else:
                e.published_parsed = None
            entries.append(e)
        feed = MagicMock()
        feed.entries = entries
        return feed

    @patch("src.news.feedparser.parse")
    def test_returns_items_within_window(self, mock_parse):
        mock_parse.return_value = self._make_feed([
            ("Recent news", 5),
            ("Old news", 30),
        ])
        items = fetch_news("Test Co", "TEST", 14, as_of=date(2026, 5, 31))
        assert len(items) == 1
        assert items[0].title == "Recent news"

    @patch("src.news.feedparser.parse")
    def test_returns_empty_on_network_error(self, mock_parse):
        mock_parse.side_effect = Exception("network error")
        items = fetch_news("Test Co", "TEST", 14, as_of=date(2026, 5, 31))
        assert items == []

    @patch("src.news.feedparser.parse")
    def test_items_sorted_newest_first(self, mock_parse):
        mock_parse.return_value = self._make_feed([
            ("Older", 10),
            ("Newest", 1),
            ("Middle", 5),
        ])
        items = fetch_news("Test Co", "TEST", 14, as_of=date(2026, 5, 31))
        dates = [i.published for i in items if i.published]
        assert dates == sorted(dates, reverse=True)

    @patch("src.news.feedparser.parse")
    def test_undated_items_included(self, mock_parse):
        mock_parse.return_value = self._make_feed([
            ("Undated", None),
            ("Recent", 2),
        ])
        items = fetch_news("Test Co", "TEST", 14, as_of=date(2026, 5, 31))
        assert len(items) == 2


# ---------------------------------------------------------------------------
# format_news_context
# ---------------------------------------------------------------------------

class TestFormatNewsContext:
    def test_empty_returns_placeholder(self):
        result = format_news_context([])
        assert "Sin noticias" in result

    def test_formats_items(self):
        items = [
            NewsItem(title="Big Deal", published=date(2026, 5, 30)),
            NewsItem(title="Earnings Beat", published=date(2026, 5, 28)),
        ]
        result = format_news_context(items)
        assert "Big Deal" in result
        assert "Earnings Beat" in result
        assert "2026-05-30" in result

    def test_truncates_to_max_items(self):
        items = [
            NewsItem(title=f"Article {i}", published=date(2026, 5, 1))
            for i in range(20)
        ]
        result = format_news_context(items, max_items=5)
        lines = [l for l in result.splitlines() if l.strip().startswith("-")]
        assert len(lines) == 5
