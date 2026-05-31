"""Loads and validates config/config.yaml and config/universe.yaml."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

_WEIGHT_SUM_TOLERANCE: float = 0.01  # warn if |sum - 1.0| > this


@dataclass
class ScoringWeights:
    results: float = 0.4
    news: float = 0.3
    staleness: float = 0.3


@dataclass
class AppConfig:
    cadence_days: int
    output_language: str
    pin: Optional[str]
    cooldown_days: int
    scoring_weights: ScoringWeights
    results_decay_days: int
    news_lookback_days: int
    prompt_path: str
    news_locale: str = "en-US"  # Google News locale (hl-GL format, e.g. "es-ES", "de-DE")


@dataclass
class UniverseEntry:
    name: str
    src_symbol: str
    us_filer: bool


def load_config(config_path: str = "config/config.yaml") -> AppConfig:
    """Load and return AppConfig from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    w = data.get("scoring_weights", {})
    weights = ScoringWeights(
        results=float(w.get("results", 0.4)),
        news=float(w.get("news", 0.3)),
        staleness=float(w.get("staleness", 0.3)),
    )
    weight_sum = weights.results + weights.news + weights.staleness
    if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
        logger.warning(
            "Scoring weights sum to %.4f (expected 1.0). "
            "Scores will not be in [0,1]. Review scoring_weights in config.yaml.",
            weight_sum,
        )
    return AppConfig(
        cadence_days=int(data.get("cadence_days", 2)),
        output_language=str(data.get("output_language", "es")),
        pin=data.get("pin") or None,
        cooldown_days=int(data.get("cooldown_days", 14)),
        scoring_weights=weights,
        results_decay_days=int(data.get("results_decay_days", 40)),
        news_lookback_days=int(data.get("news_lookback_days", 14)),
        prompt_path=str(data.get("prompt_path", "prompts/prompt_analisis.md")),
        news_locale=str(data.get("news_locale", "en-US")),
    )


def load_universe(universe_path: str = "config/universe.yaml") -> List[UniverseEntry]:
    """Load and return the list of universe entries from YAML file."""
    path = Path(universe_path)
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {universe_path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    entries: List[UniverseEntry] = []
    for item in data.get("universe", []):
        entries.append(
            UniverseEntry(
                name=str(item["name"]),
                src_symbol=str(item["src_symbol"]),
                us_filer=bool(item.get("us_filer", False)),
            )
        )
    return entries
