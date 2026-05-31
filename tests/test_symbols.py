"""Tests for src/symbols.py — written first (TDD)."""
from __future__ import annotations

import yaml

import pytest

from src.symbols import SYMBOL_TABLE, SymbolInfo, get_symbol_info


# ---------------------------------------------------------------------------
# Basic table lookups
# ---------------------------------------------------------------------------

class TestGetSymbolInfo:
    def test_returns_none_for_unknown(self):
        assert get_symbol_info("DOESNOTEXIST.X") is None

    def test_returns_symbol_info(self):
        info = get_symbol_info("ADBE.O")
        assert info is not None
        assert isinstance(info, SymbolInfo)

    def test_adbe_is_us_filer(self):
        info = get_symbol_info("ADBE.O")
        assert info.us_filer is True
        assert info.ticker == "ADBE"
        assert info.cik is not None

    def test_evolution_is_not_us_filer(self):
        info = get_symbol_info("EVOG.ST")
        assert info.us_filer is False
        assert info.cik is None

    def test_nvda_cik_format(self):
        info = get_symbol_info("NVDA.O")
        assert info.cik == "0001045810"
        # 10-digit zero-padded
        assert len(info.cik) == 10
        assert info.cik.isdigit()

    def test_all_us_filers_have_cik(self):
        for sym, info in SYMBOL_TABLE.items():
            if info.us_filer:
                assert info.cik is not None, f"{sym} is us_filer but has no CIK"

    def test_all_non_us_have_no_cik(self):
        for sym, info in SYMBOL_TABLE.items():
            if not info.us_filer:
                assert info.cik is None, f"{sym} is not us_filer but has a CIK"

    def test_all_us_ciks_are_10_digits(self):
        for sym, info in SYMBOL_TABLE.items():
            if info.us_filer and info.cik:
                assert len(info.cik) == 10, f"{sym} CIK is not 10 digits: {info.cik!r}"
                assert info.cik.isdigit(), f"{sym} CIK is not all digits: {info.cik!r}"

    def test_filings_dir_populated_for_all(self):
        for sym, info in SYMBOL_TABLE.items():
            assert info.filings_dir, f"{sym} has empty filings_dir"

    def test_name_populated_for_all(self):
        for sym, info in SYMBOL_TABLE.items():
            assert info.name, f"{sym} has empty name"

    def test_ticker_populated_for_all(self):
        for sym, info in SYMBOL_TABLE.items():
            assert info.ticker, f"{sym} has empty ticker"


# ---------------------------------------------------------------------------
# Consistency with universe.yaml
# ---------------------------------------------------------------------------

class TestUniverseConsistency:
    """Verify that every src_symbol in universe.yaml has a SYMBOL_TABLE entry
    and that the us_filer flag is consistent between both files."""

    @pytest.fixture(scope="class")
    def universe(self):
        with open("config/universe.yaml", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("universe", [])

    def test_all_universe_symbols_in_table(self, universe):
        missing = [
            entry["src_symbol"]
            for entry in universe
            if entry["src_symbol"] not in SYMBOL_TABLE
        ]
        assert missing == [], f"Symbols in universe.yaml but not in SYMBOL_TABLE: {missing}"

    def test_us_filer_flag_matches(self, universe):
        mismatches = []
        for entry in universe:
            sym = entry["src_symbol"]
            info = SYMBOL_TABLE.get(sym)
            if info and info.us_filer != entry.get("us_filer", False):
                mismatches.append(
                    f"{sym}: universe={entry.get('us_filer')} table={info.us_filer}"
                )
        assert mismatches == [], f"us_filer mismatches: {mismatches}"
