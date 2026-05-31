"""Scoring engine for the universe of stocks.

Score formula
-------------
    Score = w_res * results_score
           + w_news * news_score
           + w_stale * staleness_score
           − cooldown_penalty

Each signal is normalised to [0, 1] before weighting.

Cooldown penalty: if ``last_analyzed`` is within ``cooldown_days``, the raw
score is multiplied by COOLDOWN_FACTOR (near-zero) to prevent repetition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

# Factor applied to the score when a ticker is inside the cooldown window.
COOLDOWN_FACTOR: float = 0.05

# Default cap for the staleness signal (days without analysis → full score).
_DEFAULT_MAX_STALENESS_DAYS: int = 180


@dataclass
class StockSignals:
    """Input signals for a single stock."""

    src_symbol: str
    last_filing_date: Optional[date]  # None if no filing found
    recent_news_count: int            # articles in last news_lookback_days window
    news_baseline: float              # historical avg count per lookback window (0 = unknown)
    last_analyzed: Optional[date]     # None if never analyzed


@dataclass
class StockScore:
    """Scored output for a single stock."""

    src_symbol: str
    total_score: float
    results_component: float   # ∈ [0, 1]
    news_component: float      # ∈ [0, 1]
    staleness_component: float # ∈ [0, 1]
    in_cooldown: bool
    reason: str                # human-readable explanation of the leading signal(s)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _results_score(
    last_filing_date: Optional[date],
    as_of: date,
    decay_days: int,
) -> float:
    """Linear decay: 1.0 on the filing day, 0.0 after ``decay_days`` days."""
    if last_filing_date is None:
        return 0.0
    days_since = (as_of - last_filing_date).days
    if days_since < 0 or days_since >= decay_days:
        return 0.0
    return 1.0 - days_since / decay_days


def _news_score(recent_count: int, baseline: float) -> float:
    """Relative news score normalised to [0, 1].

    Compares *recent_count* to *baseline* (historical avg articles per lookback
    window).  The signal is intentionally relative so that a micro-cap going
    0 → 3 articles scores the same as a large-cap going 40 → 80.

    Rules:
    - Zero articles → 0.0 (no news never penalises, per spec).
    - Unknown baseline (≤ 0) → any news is a positive signal, capped at 1.0.
    - At 2× baseline → 1.0; at baseline → 0.5; below baseline → ≥ 0.0.
    """
    if recent_count == 0:
        return 0.0
    if baseline <= 0:
        # No history: 3 articles = full signal; scale linearly up to 1.0.
        return min(1.0, recent_count / 3.0)
    ratio = recent_count / baseline
    # ratio=2.0 → 1.0; ratio=1.0 → 0.5; ratio=0 → 0.0 (clamped).
    return max(0.0, min(1.0, ratio / 2.0))


def _staleness_score(
    last_analyzed: Optional[date],
    as_of: date,
    max_days: int = _DEFAULT_MAX_STALENESS_DAYS,
) -> float:
    """Grows with time since last analysis, capped at 1.0.

    Never analysed → 1.0 (maximum priority).
    Analysed today  → 0.0.
    """
    if last_analyzed is None:
        return 1.0
    days_since = (as_of - last_analyzed).days
    if days_since <= 0:
        return 0.0
    return min(1.0, days_since / max_days)


def _in_cooldown(
    last_analyzed: Optional[date],
    as_of: date,
    cooldown_days: int,
) -> bool:
    if last_analyzed is None:
        return False
    return (as_of - last_analyzed).days < cooldown_days


def _build_reason(
    results: float,
    news: float,
    staleness: float,
    in_cd: bool,
) -> str:
    parts = []
    if results > 0.5:
        parts.append("resultados recientes")
    elif results > 0.0:
        parts.append("filing reciente")
    if news > 0.6:
        parts.append("repunte de noticias")
    elif news > 0.3:
        parts.append("actividad de noticias moderada")
    if staleness > 0.7:
        parts.append("lleva mucho sin analizarse")
    elif staleness > 0.3:
        parts.append("tiempo razonable sin análisis")
    if in_cd:
        parts.append("[EN COOLDOWN]")
    return ", ".join(parts) if parts else "sin señal destacada"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_score(
    signals: StockSignals,
    as_of: date,
    weights_results: float,
    weights_news: float,
    weights_staleness: float,
    results_decay_days: int,
    cooldown_days: int,
    max_staleness_days: int = _DEFAULT_MAX_STALENESS_DAYS,
) -> StockScore:
    """Compute the selection score for a single stock.

    Parameters
    ----------
    signals:
        Raw input signals for the stock.
    as_of:
        Reference date (today in production; injected for testing).
    weights_*:
        Scoring weights from ``config.scoring_weights``.
    results_decay_days:
        From ``config.results_decay_days``.
    cooldown_days:
        From ``config.cooldown_days``.
    max_staleness_days:
        Days after which staleness saturates at 1.0 (defaults to 180).

    Returns
    -------
    StockScore with total_score and all components.
    """
    r = _results_score(signals.last_filing_date, as_of, results_decay_days)
    n = _news_score(signals.recent_news_count, signals.news_baseline)
    s = _staleness_score(signals.last_analyzed, as_of, max_staleness_days)

    raw = weights_results * r + weights_news * n + weights_staleness * s

    in_cd = _in_cooldown(signals.last_analyzed, as_of, cooldown_days)
    total = raw * COOLDOWN_FACTOR if in_cd else raw

    return StockScore(
        src_symbol=signals.src_symbol,
        total_score=total,
        results_component=r,
        news_component=n,
        staleness_component=s,
        in_cooldown=in_cd,
        reason=_build_reason(r, n, s, in_cd),
    )
