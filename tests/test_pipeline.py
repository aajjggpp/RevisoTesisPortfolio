"""Integration test for the full pipeline in STUB mode.

Runs the pipeline end-to-end without LLM_API_KEY and without real
network calls (EDGAR + news are mocked). Validates that:
  - An output Markdown file is created.
  - history.json is updated with the selected ticker.
  - The pipeline does not crash.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline import run


# ---------------------------------------------------------------------------
# Fixture: minimal repo layout in a temp directory
# ---------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path):
    """Set up a minimal repo structure in *tmp_path* and chdir into it."""
    # Config files.
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(
        "cadence_days: 2\n"
        "output_language: es\n"
        "pin: null\n"
        "cooldown_days: 14\n"
        "scoring_weights:\n"
        "  results: 0.4\n"
        "  news: 0.3\n"
        "  staleness: 0.3\n"
        "results_decay_days: 40\n"
        "news_lookback_days: 14\n"
        "prompt_path: prompts/prompt_analisis.md\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "universe.yaml").write_text(
        "universe:\n"
        "  - {name: 'Adobe', src_symbol: 'ADBE.O', us_filer: true}\n"
        "  - {name: 'Evolution AB', src_symbol: 'EVOG.ST', us_filer: false}\n",
        encoding="utf-8",
    )

    # Prompt.
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "prompt_analisis.md").write_text(
        "## SYSTEM\nYou are an analyst.\n\n"
        "## USER (template)\n\n"
        "```\n"
        "EMPRESA: {{COMPANY}} ({{TICKER}})\n"
        "FECHA: {{AS_OF_DATE}}\n"
        "IDIOMA: {{OUTPUT_LANGUAGE}}\n"
        "SELECCIÓN: {{SELECTION_REASON}}\n"
        "FUENTES: {{DETERMINISTIC_SOURCES}}\n"
        "NOTICIAS: {{NEWS_CONTEXT}}\n"
        "MERCADO: {{MARKET_DATA}}\n"
        "```\n",
        encoding="utf-8",
    )

    # State.
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "history.json").write_text("{}", encoding="utf-8")

    # Directories.
    (tmp_path / "output").mkdir()
    (tmp_path / "filings").mkdir()

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# Helpers to mock network calls
# ---------------------------------------------------------------------------

def _empty_submissions():
    """Return a minimal empty EDGAR submissions response."""
    return {
        "cik": "0000796343",
        "name": "ADOBE INC",
        "filings": {
            "recent": {
                "accessionNumber": [],
                "form": [],
                "filingDate": [],
                "primaryDocument": [],
            }
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_pipeline_runs_stub_mode(self, repo, monkeypatch):
        """End-to-end run in stub mode — no API key, mocked network."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        # Mock EDGAR submissions (returns empty filings).
        edgar_resp = MagicMock()
        edgar_resp.json.return_value = _empty_submissions()
        edgar_resp.raise_for_status = MagicMock()

        # Mock news feed (returns empty feed).
        empty_feed = MagicMock()
        empty_feed.entries = []

        with (
            patch("src.sources.edgar.requests.get", return_value=edgar_resp),
            patch("src.news.feedparser.parse", return_value=empty_feed),
            patch("src.sources.edgar.time.sleep"),
            patch("src.pipeline.time.sleep"),
        ):
            output_path = run(
                config_path="config/config.yaml",
                universe_path="config/universe.yaml",
                history_path="state/history.json",
                as_of=date(2026, 5, 31),
            )

        assert output_path.exists()
        assert output_path.suffix == ".md"
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 100

    def test_pipeline_updates_history(self, repo, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        edgar_resp = MagicMock()
        edgar_resp.json.return_value = _empty_submissions()
        edgar_resp.raise_for_status = MagicMock()
        empty_feed = MagicMock()
        empty_feed.entries = []

        with (
            patch("src.sources.edgar.requests.get", return_value=edgar_resp),
            patch("src.news.feedparser.parse", return_value=empty_feed),
            patch("src.sources.edgar.time.sleep"),
            patch("src.pipeline.time.sleep"),
        ):
            run(
                config_path="config/config.yaml",
                universe_path="config/universe.yaml",
                history_path="state/history.json",
                as_of=date(2026, 5, 31),
            )

        history = json.loads(Path("state/history.json").read_text(encoding="utf-8"))
        # At least one ticker should have been recorded.
        assert len(history) >= 1
        analyzed_dates = [v["last_analyzed"] for v in history.values()]
        assert "2026-05-31" in analyzed_dates

    def test_output_filename_format(self, repo, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        edgar_resp = MagicMock()
        edgar_resp.json.return_value = _empty_submissions()
        edgar_resp.raise_for_status = MagicMock()
        empty_feed = MagicMock()
        empty_feed.entries = []

        with (
            patch("src.sources.edgar.requests.get", return_value=edgar_resp),
            patch("src.news.feedparser.parse", return_value=empty_feed),
            patch("src.sources.edgar.time.sleep"),
            patch("src.pipeline.time.sleep"),
        ):
            output_path = run(
                config_path="config/config.yaml",
                universe_path="config/universe.yaml",
                history_path="state/history.json",
                as_of=date(2026, 5, 31),
            )

        # Filename must match YYYY-MM-DD_{TICKER}.md
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2}_[A-Z0-9]+\.md", output_path.name)

    def test_output_contains_top3_section(self, repo, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        edgar_resp = MagicMock()
        edgar_resp.json.return_value = _empty_submissions()
        edgar_resp.raise_for_status = MagicMock()
        empty_feed = MagicMock()
        empty_feed.entries = []

        with (
            patch("src.sources.edgar.requests.get", return_value=edgar_resp),
            patch("src.news.feedparser.parse", return_value=empty_feed),
            patch("src.sources.edgar.time.sleep"),
            patch("src.pipeline.time.sleep"),
        ):
            output_path = run(
                config_path="config/config.yaml",
                universe_path="config/universe.yaml",
                history_path="state/history.json",
                as_of=date(2026, 5, 31),
            )

        content = output_path.read_text(encoding="utf-8")
        assert "candidatas" in content.lower() or "top" in content.lower()

    def test_pin_forces_selection(self, repo, monkeypatch, tmp_path):
        """When config.pin is set, that ticker is analysed regardless of score."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)

        # Update config to pin Evolution AB.
        (Path("config") / "config.yaml").write_text(
            "cadence_days: 2\n"
            "output_language: es\n"
            "pin: 'EVOG.ST'\n"
            "cooldown_days: 14\n"
            "scoring_weights:\n"
            "  results: 0.4\n"
            "  news: 0.3\n"
            "  staleness: 0.3\n"
            "results_decay_days: 40\n"
            "news_lookback_days: 14\n"
            "prompt_path: prompts/prompt_analisis.md\n",
            encoding="utf-8",
        )

        edgar_resp = MagicMock()
        edgar_resp.json.return_value = _empty_submissions()
        edgar_resp.raise_for_status = MagicMock()
        empty_feed = MagicMock()
        empty_feed.entries = []

        with (
            patch("src.sources.edgar.requests.get", return_value=edgar_resp),
            patch("src.news.feedparser.parse", return_value=empty_feed),
            patch("src.sources.edgar.time.sleep"),
            patch("src.pipeline.time.sleep"),
        ):
            output_path = run(
                config_path="config/config.yaml",
                universe_path="config/universe.yaml",
                history_path="state/history.json",
                as_of=date(2026, 5, 31),
            )

        # Evolution AB ticker is EVO → file should contain "EVO"
        assert "EVO" in output_path.name
