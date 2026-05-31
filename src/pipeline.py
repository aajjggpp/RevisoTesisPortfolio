"""Pipeline entry point.

Orchestrates the full flow:
  1. Load config + universe.
  2. Load history.
  3. For each universe entry: gather signals (filing date, news).
  4. Score all entries.
  5. Select the winner (pin or top-score).
  6. Fetch deterministic sources (EDGAR or local filings).
  7. Fetch news context for the selected ticker.
  8. Build the analysis (LLM or STUB).
  9. Write output Markdown.
 10. Update and persist history.json.

Run as:  python -m src.pipeline
"""
from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analysis import NO_PRIMARY_DOCUMENT, build_analysis
from .config import AppConfig, UniverseEntry, load_config, load_universe
from .news import count_recent_news, fetch_news, format_news_context
from .render import load_history, save_history, update_history, write_output
from .scoring import StockSignals, StockScore, compute_score
from .selection import select
from .symbols import SymbolInfo, get_symbol_info
from .sources.edgar import FilingInfo, get_filing_text, get_recent_filings
from .sources.filings import get_most_recent_filing, read_filing_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths (relative to the repo root — where the process is run from).
_CONFIG_PATH = "config/config.yaml"
_UNIVERSE_PATH = "config/universe.yaml"
_HISTORY_PATH = "state/history.json"
_FILINGS_BASE = "filings"

# Polite inter-request delays (SEC allows ≤10 req/s; Google News is best-effort).
_EDGAR_SCORING_DELAY: float = 0.12   # between get_recent_filings calls
_NEWS_SCORING_DELAY: float = 0.10    # between Google News RSS calls


# ---------------------------------------------------------------------------
# Signal collection helpers
# ---------------------------------------------------------------------------

def _get_deterministic_sources(
    symbol_info: SymbolInfo,
    cached_filings: Optional[List[FilingInfo]] = None,
) -> str:
    """Fetch filing text for the selected ticker.

    Uses *cached_filings* if provided (already fetched during scoring) to
    avoid a second EDGAR round-trip.  Falls back to a fresh fetch only when
    no cache is available (e.g. non-US tickers with no local documents).

    Returns extracted section text or the NO_PRIMARY_DOCUMENT marker.
    """
    if symbol_info.us_filer and symbol_info.cik:
        filings = cached_filings if cached_filings is not None else get_recent_filings(
            symbol_info.cik, max_results=1
        )
        if filings:
            text = get_filing_text(filings[0])
            if text:
                header = (
                    f"[{filings[0].form_type} — {filings[0].filing_date.isoformat()}]"
                    f" (CIK {symbol_info.cik})\n\n"
                )
                return header + text
        return NO_PRIMARY_DOCUMENT

    # Non-US: local document.
    local = get_most_recent_filing(_FILINGS_BASE, symbol_info.filings_dir)
    if local:
        text = read_filing_text(local)
        if text:
            header = (
                f"[Documento local — {local.modified.isoformat()}]"
                f" ({local.path.name})\n\n"
            )
            return header + text
    return NO_PRIMARY_DOCUMENT


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    config_path: str = _CONFIG_PATH,
    universe_path: str = _UNIVERSE_PATH,
    history_path: str = _HISTORY_PATH,
    as_of: Optional[date] = None,
) -> Path:
    """Execute the full analysis pipeline and return the output file path."""
    if as_of is None:
        as_of = date.today()

    logger.info("=== RevisoTesisPortfolio pipeline — %s ===", as_of.isoformat())

    # -- 1. Load config & universe ------------------------------------------
    config = load_config(config_path)
    universe = load_universe(universe_path)
    logger.info("Universe: %d entries", len(universe))

    # -- 2. Load history -------------------------------------------------------
    history: Dict[str, Any] = load_history(history_path)

    # -- 3–4. Gather signals (EDGAR + news for ALL tickers) and score ----------
    # Both caches are keyed by src_symbol and reused later to avoid double fetches.
    edgar_cache: Dict[str, List[FilingInfo]] = {}
    news_cache: Dict[str, list] = {}
    scores: List[StockScore] = []

    for entry in universe:
        sym = get_symbol_info(entry.src_symbol)
        if sym is None:
            logger.warning("No SymbolInfo for %s — skipping", entry.src_symbol)
            continue

        hist_entry = history.get(entry.src_symbol, {})
        last_analyzed: Optional[date] = None
        raw_la = hist_entry.get("last_analyzed")
        if raw_la:
            try:
                last_analyzed = date.fromisoformat(raw_la)
            except ValueError:
                pass
        news_baseline = float(hist_entry.get("news_avg_count", 0.0))

        # -- EDGAR filing date (with rate limiting between calls) --
        last_filing_date: Optional[date] = None
        if sym.us_filer and sym.cik:
            time.sleep(_EDGAR_SCORING_DELAY)
            filings = get_recent_filings(sym.cik, max_results=1)
            edgar_cache[entry.src_symbol] = filings
            if filings:
                last_filing_date = filings[0].filing_date
        else:
            local = get_most_recent_filing(_FILINGS_BASE, sym.filings_dir)
            if local:
                last_filing_date = local.modified

        # -- News count (real fetch for ALL tickers — powers the 30% news weight) --
        time.sleep(_NEWS_SCORING_DELAY)
        news_items = fetch_news(
            company_name=sym.name,
            ticker=sym.ticker,
            lookback_days=config.news_lookback_days,
            as_of=as_of,
            news_locale=config.news_locale,
        )
        news_cache[entry.src_symbol] = news_items
        recent_count = count_recent_news(news_items, config.news_lookback_days, as_of)

        signals = StockSignals(
            src_symbol=entry.src_symbol,
            last_filing_date=last_filing_date,
            recent_news_count=recent_count,
            news_baseline=news_baseline,
            last_analyzed=last_analyzed,
        )

        score = compute_score(
            signals=signals,
            as_of=as_of,
            weights_results=config.scoring_weights.results,
            weights_news=config.scoring_weights.news,
            weights_staleness=config.scoring_weights.staleness,
            results_decay_days=config.results_decay_days,
            cooldown_days=config.cooldown_days,
        )
        scores.append(score)
        logger.debug(
            "  %s → %.3f (res=%.2f news=%.2f stale=%.2f%s)",
            entry.src_symbol,
            score.total_score,
            score.results_component,
            score.news_component,
            score.staleness_component,
            " [COOLDOWN]" if score.in_cooldown else "",
        )

    if not scores:
        raise RuntimeError("No scoreable entries — check universe.yaml and symbols.py.")

    # -- 5. Select -------------------------------------------------------------
    result = select(scores, pin=config.pin)
    selected_sym = result.selected.src_symbol
    logger.info(
        "Selected: %s (score=%.3f, pin=%s)",
        selected_sym,
        result.selected.total_score,
        result.pin_used,
    )
    logger.info("Top-3: %s", [s.src_symbol for s in result.top3])

    sym_info = get_symbol_info(selected_sym)
    if sym_info is None:
        raise RuntimeError(
            f"No SymbolInfo for selected ticker '{selected_sym}'. "
            "Ensure it exists in symbols.py."
        )

    # -- 6. Deterministic sources (reuse cached EDGAR data — no second fetch) --
    logger.info("Fetching deterministic sources for %s…", selected_sym)
    det_sources = _get_deterministic_sources(
        sym_info, cached_filings=edgar_cache.get(selected_sym)
    )
    if det_sources == NO_PRIMARY_DOCUMENT:
        logger.warning("No primary document for %s", selected_sym)

    # -- 7. News context (reuse cached items — no second Google News call) -----
    news_items = news_cache.get(selected_sym, [])
    recent_count = count_recent_news(news_items, config.news_lookback_days, as_of)
    news_context = format_news_context(news_items)
    logger.info("News items for selected ticker: %d", recent_count)

    # -- 8. Build variables & analysis ----------------------------------------
    variables = {
        "COMPANY": sym_info.name,
        "TICKER": sym_info.ticker,
        "AS_OF_DATE": as_of.isoformat(),
        "OUTPUT_LANGUAGE": config.output_language,
        "SELECTION_REASON": result.selected.reason,
        "DETERMINISTIC_SOURCES": det_sources,
        "NEWS_CONTEXT": news_context,
        "MARKET_DATA": "[No entregados — añadir fuente determinista si disponible]",
    }

    prompt_path = config.prompt_path
    if not Path(prompt_path).exists():
        # Fallback: try prompt at repo root.
        fallback = Path("prompt_analisis.md")
        if fallback.exists():
            prompt_path = str(fallback)
            logger.warning("prompt_path not found; using fallback %s", prompt_path)
        else:
            raise RuntimeError(
                f"Prompt file not found at '{prompt_path}' (or fallback 'prompt_analisis.md'). "
                "Set prompt_path in config.yaml."
            )

    logger.info("Generating analysis…")
    analysis_text = build_analysis(prompt_path=prompt_path, variables=variables)

    # -- 9. Write output -------------------------------------------------------
    output_path = write_output(
        analysis_text=analysis_text,
        result=result,
        symbol_info=sym_info,
        as_of=as_of,
    )

    # -- 10. Update history ----------------------------------------------------
    history = update_history(
        history=history,
        src_symbol=selected_sym,
        analyzed_date=as_of,
        news_count=recent_count,
    )
    save_history(history, history_path)
    logger.info("History updated for %s", selected_sym)
    logger.info("=== Done. Output: %s ===", output_path)

    return output_path


if __name__ == "__main__":
    run()
