"""Render module — writes the final Markdown output and updates history.

Output file: ``output/YYYY-MM-DD_{ticker}.md``
The file appends a section with the other top-3 candidates and their reasons.
After writing the file, ``state/history.json`` is updated.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .selection import SelectionResult
from .symbols import SymbolInfo

logger = logging.getLogger(__name__)

_HISTORY_FILE = "state/history.json"
_OUTPUT_DIR = "output"

# EMA smoothing factor kept in sync with src/news.py.
_EMA_ALPHA: float = 0.3


def _ema_update(current: float, new_value: int) -> float:
    """Exponential moving average for the news baseline."""
    if current <= 0:
        return float(new_value)
    return _EMA_ALPHA * new_value + (1 - _EMA_ALPHA) * current


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def load_history(history_path: str = _HISTORY_FILE) -> Dict[str, Any]:
    """Load history.json; return empty dict if file is missing or empty."""
    path = Path(history_path)
    if not path.exists():
        return {}
    try:
        content = path.read_text(encoding="utf-8").strip()
        return json.loads(content) if content else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read history at %s: %s", history_path, exc)
        return {}


def save_history(history: Dict[str, Any], history_path: str = _HISTORY_FILE) -> None:
    """Persist history dict to JSON."""
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def update_history(
    history: Dict[str, Any],
    src_symbol: str,
    analyzed_date: date,
    news_count: int,
) -> Dict[str, Any]:
    """Return updated history dict with the new analysis record.

    Updates ``last_analyzed`` and the EMA ``news_avg_count`` baseline.
    """
    entry = history.get(src_symbol, {})
    old_baseline = float(entry.get("news_avg_count", 0.0))
    new_baseline = _ema_update(old_baseline, news_count)

    history[src_symbol] = {
        "last_analyzed": analyzed_date.isoformat(),
        "news_avg_count": round(new_baseline, 4),
    }
    return history


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

def _format_top3_section(result: SelectionResult) -> str:
    """Build the 'Other candidates' section appended to the note."""
    lines = [
        "",
        "---",
        "",
        "## Otras candidatas del top-3",
        "",
    ]
    for score in result.top3:
        is_selected = score.src_symbol == result.selected.src_symbol
        prefix = "**[SELECCIONADA]** " if is_selected else ""
        lines.append(
            f"- {prefix}`{score.src_symbol}` — score: {score.total_score:.3f} "
            f"— señal: {score.reason}"
        )
    return "\n".join(lines)


def write_output(
    analysis_text: str,
    result: SelectionResult,
    symbol_info: SymbolInfo,
    as_of: date,
    output_dir: str = _OUTPUT_DIR,
) -> Path:
    """Write the analysis Markdown file.

    Appends the top-3 candidates section, then writes to
    ``output/YYYY-MM-DD_{ticker}.md``.

    Returns the path of the written file.
    """
    date_str = as_of.strftime("%Y-%m-%d")
    ticker = symbol_info.ticker
    filename = f"{date_str}_{ticker}.md"
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        logger.warning(
            "Output file '%s' already exists and will be overwritten. "
            "If this is unexpected check for duplicate runs.",
            output_path,
        )

    top3_section = _format_top3_section(result)
    full_content = analysis_text.rstrip() + "\n" + top3_section + "\n"

    output_path.write_text(full_content, encoding="utf-8")
    logger.info("Analysis written to %s", output_path)
    return output_path
