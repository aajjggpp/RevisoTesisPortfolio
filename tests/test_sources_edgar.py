"""Tests for src/sources/edgar.py — written first (TDD).
HTTP calls are mocked via unittest.mock.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.sources.edgar import (
    FilingInfo,
    _cik10,
    _accession_nodash,
    _html_to_text,
    get_recent_filings,
    get_filing_text,
    RELEVANT_FORMS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submissions(forms, dates, accessions, docs):
    return {
        "cik": "1045810",
        "name": "TEST CORP",
        "filings": {
            "recent": {
                "accessionNumber": accessions,
                "form": forms,
                "filingDate": dates,
                "primaryDocument": docs,
            }
        },
    }


# ---------------------------------------------------------------------------
# _cik10
# ---------------------------------------------------------------------------

class TestCik10:
    def test_already_padded(self):
        assert _cik10("0001045810") == "0001045810"

    def test_short_cik(self):
        assert _cik10("1045810") == "0001045810"

    def test_zero_stripped_then_repadded(self):
        # Round-trip: strip leading zeros then re-pad.
        assert len(_cik10("0000796343")) == 10

    def test_all_zeros_edge(self):
        # CIK=1 → "0000000001"
        assert _cik10("1") == "0000000001"


# ---------------------------------------------------------------------------
# _accession_nodash
# ---------------------------------------------------------------------------

class TestAccessionNodash:
    def test_removes_dashes(self):
        assert _accession_nodash("0001045810-24-000059") == "000104581024000059"

    def test_no_dashes_unchanged(self):
        assert _accession_nodash("000104581024000059") == "000104581024000059"


# ---------------------------------------------------------------------------
# _html_to_text
# ---------------------------------------------------------------------------

class TestHtmlToText:
    def test_strips_tags(self):
        html = "<html><body><p>Hello <b>World</b></p></body></html>"
        text = _html_to_text(html)
        assert "Hello" in text
        assert "World" in text
        assert "<" not in text

    def test_ignores_script(self):
        html = "<script>var x=1;</script><p>Visible</p>"
        text = _html_to_text(html)
        assert "var x" not in text
        assert "Visible" in text

    def test_ignores_style(self):
        html = "<style>.cls{color:red}</style><p>Text</p>"
        text = _html_to_text(html)
        assert ".cls" not in text
        assert "Text" in text


# ---------------------------------------------------------------------------
# get_recent_filings — mocked HTTP
# ---------------------------------------------------------------------------

class TestGetRecentFilings:
    def _mock_session(self, payload: dict) -> MagicMock:
        session = MagicMock()
        resp = MagicMock()
        resp.json.return_value = payload
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp
        return session

    def test_returns_matching_forms(self):
        payload = _make_submissions(
            forms=["10-K", "10-Q", "DEF 14A"],
            dates=["2026-02-15", "2026-05-10", "2026-03-01"],
            accessions=["0001045810-26-001", "0001045810-26-002", "0001045810-26-003"],
            docs=["form10k.htm", "form10q.htm", "def14a.htm"],
        )
        session = self._mock_session(payload)
        filings = get_recent_filings("0001045810", session=session)
        forms = [f.form_type for f in filings]
        assert "10-K" in forms
        assert "10-Q" in forms
        assert "DEF 14A" not in forms

    def test_returns_filing_info_fields(self):
        payload = _make_submissions(
            forms=["10-K"],
            dates=["2026-02-15"],
            accessions=["0001045810-26-001"],
            docs=["form10k.htm"],
        )
        session = self._mock_session(payload)
        filings = get_recent_filings("0001045810", session=session)
        assert len(filings) == 1
        f = filings[0]
        assert f.form_type == "10-K"
        assert f.filing_date == date(2026, 2, 15)
        assert f.accession_number == "0001045810-26-001"
        assert f.primary_document == "form10k.htm"

    def test_respects_max_results(self):
        payload = _make_submissions(
            forms=["10-Q"] * 5,
            dates=["2026-05-10", "2026-02-10", "2025-11-10", "2025-08-10", "2025-05-10"],
            accessions=[f"0001045810-26-00{i}" for i in range(5)],
            docs=[f"doc{i}.htm" for i in range(5)],
        )
        session = self._mock_session(payload)
        filings = get_recent_filings("0001045810", max_results=2, session=session)
        assert len(filings) == 2

    def test_network_error_returns_empty(self):
        session = MagicMock()
        session.get.side_effect = Exception("timeout")
        filings = get_recent_filings("0001045810", session=session)
        assert filings == []

    def test_invalid_date_skipped(self):
        payload = _make_submissions(
            forms=["10-K"],
            dates=["not-a-date"],
            accessions=["0001045810-26-001"],
            docs=["form10k.htm"],
        )
        session = self._mock_session(payload)
        filings = get_recent_filings("0001045810", session=session)
        assert filings == []


# ---------------------------------------------------------------------------
# get_filing_text — mocked HTTP
# ---------------------------------------------------------------------------

class TestGetFilingText:
    def _make_filing(self) -> FilingInfo:
        return FilingInfo(
            form_type="10-K",
            filing_date=date(2026, 2, 15),
            accession_number="0001045810-26-001",
            primary_document="form10k.htm",
            cik="0001045810",
        )

    def test_returns_plain_text_from_html(self):
        html = "<html><body><p>ITEM 7 Management Discussion</p><p>Revenue was strong.</p></body></html>"
        session = MagicMock()
        resp = MagicMock()
        resp.text = html
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        with patch("src.sources.edgar.time.sleep"):
            text = get_filing_text(self._make_filing(), session=session)

        assert "Management Discussion" in text
        assert "Revenue was strong" in text
        assert "<" not in text

    def test_network_error_returns_empty(self):
        session = MagicMock()
        session.get.side_effect = Exception("network error")
        with patch("src.sources.edgar.time.sleep"):
            text = get_filing_text(self._make_filing(), session=session)
        assert text == ""

    def test_plain_text_document_returned_as_is(self):
        session = MagicMock()
        resp = MagicMock()
        resp.text = "ITEM 7\nRevenue increased this quarter."
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp

        with patch("src.sources.edgar.time.sleep"):
            text = get_filing_text(self._make_filing(), session=session)

        assert "Revenue increased" in text
