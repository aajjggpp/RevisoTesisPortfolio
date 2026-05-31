"""EDGAR client for US SEC filers.

Fetches filing metadata and document text from EDGAR's public REST API.
All requests include a descriptive User-Agent as required by SEC fair-access
policy (https://www.sec.gov/developer).

Supported form types
--------------------
US domestic: 10-K, 10-Q
Foreign private issuers: 20-F, 40-F

Rate limiting: SEC allows up to 10 req/s. We add a short delay between
requests when fetching document text to stay well under that limit.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import List, Optional, Tuple

import os

import requests

logger = logging.getLogger(__name__)

# Public EDGAR endpoints.
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{doc}"

# Form types we consider as "recent results / earnings filing".
RELEVANT_FORMS: Tuple[str, ...] = ("10-K", "10-Q", "20-F", "40-F")

# Sections to extract from filing text (regex patterns, case-insensitive).
_SECTION_PATTERNS = [
    r"(?:item\s*7[^a-z]|management.{0,10}discussion)",   # MD&A
    r"item\s*1a[^a-z]|risk\s+factors",                   # Risk Factors
    r"item\s*8[^a-z]|financial\s+statements",             # Financial Statements
    r"item\s*7a[^a-z]|quantitative.{0,20}market\s+risk", # Market Risk
]

# Maximum characters of filing text to include in the prompt context.
_MAX_TEXT_CHARS: int = 40_000

# SEC requires a descriptive User-Agent with a real contact email.
# Set the EDGAR_USER_AGENT environment variable to your actual contact:
#   export EDGAR_USER_AGENT="MyApp/1.0 myemail@domain.com"
# The SEC may block requests if a fake/placeholder email is detected.
_USER_AGENT: str = os.environ.get(
    "EDGAR_USER_AGENT",
    "RevisoTesisPortfolio research-bot contact@example.com",
)

if "contact@example.com" in _USER_AGENT:
    import warnings
    warnings.warn(
        "EDGAR_USER_AGENT uses the placeholder 'contact@example.com'. "
        "Set the EDGAR_USER_AGENT environment variable to a real email address "
        "to comply with SEC fair-access policy and avoid being blocked.",
        UserWarning,
        stacklevel=2,
    )

# Polite inter-request delay (seconds).
_REQUEST_DELAY: float = 0.15


@dataclass
class FilingInfo:
    form_type: str
    filing_date: date
    accession_number: str  # raw with dashes e.g. "0001045810-24-000059"
    primary_document: str  # filename of the main document
    cik: str               # raw CIK as provided (may have leading zeros)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cik10(cik: str) -> str:
    """Zero-pad a CIK string to 10 digits."""
    return str(int(cik)).zfill(10)


def _accession_nodash(accession: str) -> str:
    """Remove dashes from accession number for use in URL paths."""
    return accession.replace("-", "")


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML → plain-text converter."""

    def __init__(self):
        super().__init__()
        self._texts: List[str] = []
        self._skip_tags = {"script", "style"}
        self._current_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._current_skip += 1

    def handle_endtag(self, tag):
        if tag in self._skip_tags and self._current_skip > 0:
            self._current_skip -= 1

    def handle_data(self, data):
        if self._current_skip == 0:
            stripped = data.strip()
            if stripped:
                self._texts.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._texts)


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _extract_relevant_sections(text: str) -> str:
    """Best-effort extraction of key sections from plain-text filings.

    Looks for MD&A, Risk Factors, Financial Statements and Market Risk.
    Falls back to the first _MAX_TEXT_CHARS characters if no sections found.
    """
    lines = text.splitlines()
    n = len(lines)
    section_starts: List[int] = []

    combined_pattern = re.compile(
        "|".join(_SECTION_PATTERNS),
        re.IGNORECASE,
    )

    for i, line in enumerate(lines):
        if combined_pattern.search(line):
            section_starts.append(i)

    if not section_starts:
        # No structured sections found — return truncated full text.
        return text[:_MAX_TEXT_CHARS]

    # Collect up to 3000 lines per section, deduplicating overlapping windows.
    parts: List[str] = []
    seen_starts: set = set()
    for start in section_starts:
        if start in seen_starts:
            continue
        end = min(n, start + 3000)
        parts.append("\n".join(lines[start:end]))
        seen_starts.update(range(start, end))

    extracted = "\n\n---\n\n".join(parts)
    return extracted[:_MAX_TEXT_CHARS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_recent_filings(
    cik: str,
    form_types: Optional[List[str]] = None,
    session: Optional[requests.Session] = None,
    max_results: int = 5,
) -> List[FilingInfo]:
    """Fetch recent filings metadata for a CIK from EDGAR submissions API.

    Parameters
    ----------
    cik:
        EDGAR CIK (zero-padded or raw).
    form_types:
        Filter to these form types.  Defaults to ``RELEVANT_FORMS``.
    session:
        Optional requests.Session for testing (mock HTTP).
    max_results:
        Maximum number of matching filings to return (newest first).

    Returns
    -------
    List of FilingInfo sorted newest-first.
    """
    if form_types is None:
        form_types = list(RELEVANT_FORMS)

    cik10 = _cik10(cik)
    url = _SUBMISSIONS_URL.format(cik10=cik10)
    headers = {"User-Agent": _USER_AGENT}

    requester = session or requests
    try:
        resp = requester.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("EDGAR submissions fetch failed for CIK %s: %s", cik, exc)
        return []

    recent = data.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])

    results: List[FilingInfo] = []
    for acc, form, fd, pdoc in zip(accessions, forms, filing_dates, primary_docs):
        if form not in form_types:
            continue
        try:
            parsed_date = date.fromisoformat(fd)
        except (ValueError, TypeError):
            continue
        results.append(
            FilingInfo(
                form_type=form,
                filing_date=parsed_date,
                accession_number=acc,
                primary_document=pdoc,
                cik=cik,
            )
        )
        if len(results) >= max_results:
            break

    return results


def get_filing_text(
    filing: FilingInfo,
    session: Optional[requests.Session] = None,
) -> str:
    """Download and extract plain text from a filing's primary document.

    Returns extracted section text (MD&A, Risk Factors, etc.) truncated to
    ``_MAX_TEXT_CHARS`` characters.  Returns an empty string on failure.
    """
    requester = session or requests
    try:
        cik_int = str(int(filing.cik))  # inside try so invalid CIK is caught cleanly
        acc_nodash = _accession_nodash(filing.accession_number)
        url = _ARCHIVE_URL.format(
            cik_int=cik_int,
            accession_nodash=acc_nodash,
            doc=filing.primary_document,
        )
        headers = {"User-Agent": _USER_AGENT}
        time.sleep(_REQUEST_DELAY)
        resp = requester.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        raw = resp.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("EDGAR document fetch failed (CIK=%s): %s", filing.cik, exc)
        return ""

    # Convert HTML to plain text if needed (case-insensitive to catch <HTML>, <Html>, etc.).
    if re.search(r"<html|<!DOCTYPE", raw[:500], re.IGNORECASE):
        plain = _html_to_text(raw)
    else:
        plain = raw

    return _extract_relevant_sections(plain)
