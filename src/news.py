"""News feed client.

Fetches headlines from Google News RSS (no API key required) for each
company and computes:
  - recent_count  : number of articles in the last ``lookback_days``.
  - updated baseline: exponential moving average stored in history.json.

The news signal is intentionally RELATIVE (see scoring.py) so small-caps
are not systematically disadvantaged versus large-caps with more coverage.

Design constraint: news data is used ONLY for scoring and as colour context.
It is never passed as a source of quantitative facts to the LLM.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import quote_plus

import feedparser
import requests

logger = logging.getLogger(__name__)

# EMA smoothing factor for updating the news baseline (α = 0.3).
_EMA_ALPHA: float = 0.3

# Timeout for HTTP requests in seconds.
_HTTP_TIMEOUT: int = 15

# Google News RSS search URL template.
# The locale triple (hl, gl, ceid) controls which edition is served.
# Override at call time by passing a `locale` argument to fetch_news.
_GNEWS_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
)
_DEFAULT_NEWS_HL: str = "en"   # language
_DEFAULT_NEWS_GL: str = "US"   # country


@dataclass
class NewsItem:
    title: str
    published: Optional[date]   # None if date could not be parsed
    summary: str = ""


def _parse_published(entry) -> Optional[date]:
    """Extract the published date from a feedparser entry."""
    # feedparser normalises to published_parsed (time.struct_time in UTC).
    ts = getattr(entry, "published_parsed", None)
    if ts is None:
        return None
    try:
        return date(ts.tm_year, ts.tm_mon, ts.tm_mday)
    except (ValueError, AttributeError):
        return None


def fetch_news(
    company_name: str,
    ticker: str,
    lookback_days: int,
    as_of: Optional[date] = None,
    session: Optional[requests.Session] = None,
    news_locale: str = "en-US",
) -> List[NewsItem]:
    """Fetch recent news items for a company from Google News RSS.

    Parameters
    ----------
    company_name:
        Full company name used as the primary search query.
    ticker:
        Clean ticker symbol used as a fallback / additional query term.
    lookback_days:
        Only items published within this many days of *as_of* are returned.
    as_of:
        Reference date (defaults to today).
    session:
        Optional requests.Session — injected in tests to mock HTTP.
    news_locale:
        Google News locale string in ``"hl-GL"`` format (e.g. ``"en-US"``,
        ``"es-ES"``, ``"de-DE"``).  Determines which edition of Google News
        is queried.  Non-English locales improve coverage for non-US companies.

    Returns
    -------
    List of NewsItem objects sorted newest-first.  Returns an empty list on
    network errors (non-blocking: the pipeline continues with zero news score).
    """
    if as_of is None:
        as_of = date.today()

    parts = news_locale.split("-", 1)
    hl = parts[0].lower()
    gl = (parts[1] if len(parts) > 1 else parts[0]).upper()

    query = quote_plus(f'"{company_name}" OR "{ticker}"')
    url = _GNEWS_URL.format(query=query, hl=hl, gl=gl)

    try:
        if session is not None:
            resp = session.get(url, timeout=_HTTP_TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
        else:
            feed = feedparser.parse(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("News fetch failed for %s: %s", company_name, exc)
        return []

    cutoff = as_of - timedelta(days=lookback_days)
    items: List[NewsItem] = []
    for entry in feed.entries:
        pub = _parse_published(entry)
        # Include items whose date is within the window OR whose date is unknown
        # (we err on the side of inclusion for undated items).
        if pub is None or pub >= cutoff:
            items.append(
                NewsItem(
                    title=getattr(entry, "title", ""),
                    published=pub,
                    summary=getattr(entry, "summary", ""),
                )
            )

    items.sort(key=lambda i: i.published or date.min, reverse=True)
    return items


def count_recent_news(items: List[NewsItem], lookback_days: int, as_of: date) -> int:
    """Count items published within ``lookback_days`` of ``as_of``."""
    cutoff = as_of - timedelta(days=lookback_days)
    return sum(1 for item in items if item.published is not None and item.published >= cutoff)


def update_baseline(current_baseline: float, new_count: int) -> float:
    """Update the rolling news baseline using an exponential moving average.

    α = 0.3: recent observations carry more weight while retaining history.
    A baseline of 0.0 (first observation) is bootstrapped to *new_count*.
    """
    if current_baseline <= 0:
        return float(new_count)
    return _EMA_ALPHA * new_count + (1 - _EMA_ALPHA) * current_baseline


def format_news_context(items: List[NewsItem], max_items: int = 10) -> str:
    """Format dated news items as a short context block for the LLM prompt.

    Items without a known publication date are excluded: they may be
    arbitrarily old and could mislead the model about recency.
    """
    dated = [i for i in items if i.published is not None]
    if not dated:
        return "[Sin noticias recientes con fecha disponibles]"
    lines = []
    for item in dated[:max_items]:
        lines.append(f"- [{item.published.isoformat()}] {item.title}")
    return "\n".join(lines)
