"""Tests for src/render.py — written first (TDD)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.render import (
    _format_top3_section,
    load_history,
    save_history,
    update_history,
    write_output,
)
from src.scoring import StockScore
from src.selection import SelectionResult
from src.symbols import SymbolInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_score(sym: str, total: float) -> StockScore:
    return StockScore(
        src_symbol=sym,
        total_score=total,
        results_component=0.5,
        news_component=0.3,
        staleness_component=0.2,
        in_cooldown=False,
        reason="resultados recientes",
    )


def _make_result(selected_sym="ADBE.O") -> SelectionResult:
    scores = [
        _make_score("ADBE.O", 0.8),
        _make_score("NVDA.O", 0.6),
        _make_score("MSFT.O", 0.4),
    ]
    selected = next(s for s in scores if s.src_symbol == selected_sym)
    return SelectionResult(selected=selected, top3=scores, pin_used=False)


def _make_symbol_info() -> SymbolInfo:
    return SymbolInfo(
        src_symbol="ADBE.O",
        name="Adobe Inc.",
        ticker="ADBE",
        us_filer=True,
        cik="0000796343",
        filings_dir="ADBE",
    )


# ---------------------------------------------------------------------------
# load_history / save_history
# ---------------------------------------------------------------------------

class TestHistory:
    def test_load_missing_returns_empty(self, tmp_path):
        result = load_history(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_load_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "history.json"
        f.write_text("", encoding="utf-8")
        assert load_history(str(f)) == {}

    def test_save_and_reload(self, tmp_path):
        f = tmp_path / "history.json"
        data = {"ADBE.O": {"last_analyzed": "2026-05-31", "news_avg_count": 5.0}}
        save_history(data, str(f))
        loaded = load_history(str(f))
        assert loaded["ADBE.O"]["last_analyzed"] == "2026-05-31"

    def test_save_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "nested" / "deep" / "history.json"
        save_history({"x": 1}, str(f))
        assert f.exists()


# ---------------------------------------------------------------------------
# update_history
# ---------------------------------------------------------------------------

class TestUpdateHistory:
    def test_creates_entry_for_new_symbol(self):
        history = {}
        result = update_history(history, "ADBE.O", date(2026, 5, 31), 10)
        assert "ADBE.O" in result
        assert result["ADBE.O"]["last_analyzed"] == "2026-05-31"

    def test_updates_last_analyzed(self):
        history = {"ADBE.O": {"last_analyzed": "2026-01-01", "news_avg_count": 5.0}}
        result = update_history(history, "ADBE.O", date(2026, 5, 31), 8)
        assert result["ADBE.O"]["last_analyzed"] == "2026-05-31"

    def test_updates_news_baseline_ema(self):
        history = {"ADBE.O": {"last_analyzed": "2026-01-01", "news_avg_count": 10.0}}
        result = update_history(history, "ADBE.O", date(2026, 5, 31), 20)
        # EMA α=0.3: 0.3*20 + 0.7*10 = 6+7 = 13
        assert result["ADBE.O"]["news_avg_count"] == pytest.approx(13.0)

    def test_does_not_modify_other_symbols(self):
        history = {"OTHER.X": {"last_analyzed": "2026-01-01", "news_avg_count": 5.0}}
        result = update_history(history, "ADBE.O", date(2026, 5, 31), 0)
        assert result["OTHER.X"]["last_analyzed"] == "2026-01-01"


# ---------------------------------------------------------------------------
# _format_top3_section
# ---------------------------------------------------------------------------

class TestFormatTop3Section:
    def test_contains_all_top3_symbols(self):
        result_obj = _make_result()
        text = _format_top3_section(result_obj)
        assert "ADBE.O" in text
        assert "NVDA.O" in text
        assert "MSFT.O" in text

    def test_marks_selected(self):
        result_obj = _make_result("ADBE.O")
        text = _format_top3_section(result_obj)
        assert "SELECCIONADA" in text

    def test_contains_score_values(self):
        result_obj = _make_result()
        text = _format_top3_section(result_obj)
        assert "0.8" in text

    def test_contains_reasons(self):
        result_obj = _make_result()
        text = _format_top3_section(result_obj)
        assert "resultados recientes" in text


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------

class TestWriteOutput:
    def test_creates_file_with_correct_name(self, tmp_path):
        result_obj = _make_result()
        sym = _make_symbol_info()
        path = write_output(
            "# Analysis\nContent here.",
            result_obj,
            sym,
            date(2026, 5, 31),
            output_dir=str(tmp_path),
        )
        assert path.name == "2026-05-31_ADBE.md"
        assert path.exists()

    def test_file_contains_analysis_text(self, tmp_path):
        result_obj = _make_result()
        sym = _make_symbol_info()
        path = write_output(
            "# My Analysis\nGreat content.",
            result_obj,
            sym,
            date(2026, 5, 31),
            output_dir=str(tmp_path),
        )
        content = path.read_text(encoding="utf-8")
        assert "My Analysis" in content
        assert "Great content" in content

    def test_file_contains_top3_section(self, tmp_path):
        result_obj = _make_result()
        sym = _make_symbol_info()
        path = write_output(
            "# Analysis",
            result_obj,
            sym,
            date(2026, 5, 31),
            output_dir=str(tmp_path),
        )
        content = path.read_text(encoding="utf-8")
        assert "candidatas" in content.lower() or "top" in content.lower()
        assert "NVDA.O" in content

    def test_creates_output_dir_if_missing(self, tmp_path):
        result_obj = _make_result()
        sym = _make_symbol_info()
        new_dir = tmp_path / "new_output"
        path = write_output(
            "# Analysis",
            result_obj,
            sym,
            date(2026, 5, 31),
            output_dir=str(new_dir),
        )
        assert path.exists()
