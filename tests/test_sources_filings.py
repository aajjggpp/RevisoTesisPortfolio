"""Tests for src/sources/filings.py — written first (TDD).
Uses temporary directories to avoid filesystem side-effects.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.sources.filings import (
    LocalFiling,
    get_most_recent_filing,
    list_local_filings,
    read_filing_text,
)


# ---------------------------------------------------------------------------
# list_local_filings
# ---------------------------------------------------------------------------

class TestListLocalFilings:
    def test_missing_dir_returns_empty(self, tmp_path):
        result = list_local_filings(str(tmp_path), "NONEXISTENT")
        assert result == []

    def test_empty_dir_returns_empty(self, tmp_path):
        (tmp_path / "TICKER").mkdir()
        result = list_local_filings(str(tmp_path), "TICKER")
        assert result == []

    def test_unsupported_extension_ignored(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        (d / "notes.xlsx").write_text("data")
        result = list_local_filings(str(tmp_path), "TICKER")
        assert result == []

    def test_txt_file_listed(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        (d / "annual_report.txt").write_text("content")
        result = list_local_filings(str(tmp_path), "TICKER")
        assert len(result) == 1
        assert result[0].path.suffix == ".txt"

    def test_md_file_listed(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        (d / "report.md").write_text("# Title")
        result = list_local_filings(str(tmp_path), "TICKER")
        assert len(result) == 1

    def test_pdf_file_listed(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        (d / "filing.pdf").write_bytes(b"%PDF-1.4 fake")
        result = list_local_filings(str(tmp_path), "TICKER")
        assert len(result) == 1

    def test_sorted_newest_first(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        old = d / "old.txt"
        new = d / "new.txt"
        old.write_text("old")
        new.write_text("new")
        # Force mtime difference.
        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))

        result = list_local_filings(str(tmp_path), "TICKER")
        assert result[0].path.name == "new.txt"
        assert result[1].path.name == "old.txt"


# ---------------------------------------------------------------------------
# get_most_recent_filing
# ---------------------------------------------------------------------------

class TestGetMostRecentFiling:
    def test_returns_none_when_empty(self, tmp_path):
        (tmp_path / "TICKER").mkdir()
        assert get_most_recent_filing(str(tmp_path), "TICKER") is None

    def test_returns_most_recent(self, tmp_path):
        d = tmp_path / "TICKER"
        d.mkdir()
        f1 = d / "a.txt"
        f2 = d / "b.txt"
        f1.write_text("old")
        f2.write_text("new")
        os.utime(f1, (1_000_000, 1_000_000))
        os.utime(f2, (2_000_000, 2_000_000))

        result = get_most_recent_filing(str(tmp_path), "TICKER")
        assert result is not None
        assert result.path.name == "b.txt"


# ---------------------------------------------------------------------------
# read_filing_text
# ---------------------------------------------------------------------------

class TestReadFilingText:
    def _local_filing(self, path: Path) -> LocalFiling:
        from datetime import date
        return LocalFiling(path=path, modified=date(2026, 1, 1), size_bytes=path.stat().st_size)

    def test_reads_txt_file(self, tmp_path):
        fpath = tmp_path / "report.txt"
        fpath.write_text("Annual report content here.", encoding="utf-8")
        filing = self._local_filing(fpath)
        text = read_filing_text(filing)
        assert "Annual report content" in text

    def test_reads_md_file(self, tmp_path):
        fpath = tmp_path / "report.md"
        fpath.write_text("# Title\nSome content.", encoding="utf-8")
        filing = self._local_filing(fpath)
        text = read_filing_text(filing)
        assert "Some content" in text

    def test_unsupported_extension_returns_empty(self, tmp_path):
        fpath = tmp_path / "data.xlsx"
        fpath.write_bytes(b"binary")
        filing = self._local_filing(fpath)
        text = read_filing_text(filing)
        assert text == ""

    def test_large_file_truncated(self, tmp_path):
        fpath = tmp_path / "big.txt"
        fpath.write_text("A" * 50_000, encoding="utf-8")
        filing = self._local_filing(fpath)
        text = read_filing_text(filing)
        assert len(text) <= 40_000
