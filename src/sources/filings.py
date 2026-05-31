"""Local filings ingestion for non-US companies.

The user drops primary-document files (PDF, TXT, MD) into
``filings/{filings_dir}/``.  This module lists available documents, returns
the most recent one (by file modification time), and reads its text content.

PDF extraction requires ``pdfminer.six`` (optional dependency).  If not
installed, PDF files are skipped with a warning and plain text files are used
instead.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Supported file extensions (in priority order for text extraction).
_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
_PDF_EXTENSIONS = {".pdf"}
_SUPPORTED = _TEXT_EXTENSIONS | _PDF_EXTENSIONS

# Maximum characters to return from a local filing.
_MAX_TEXT_CHARS: int = 40_000


@dataclass
class LocalFiling:
    path: Path
    modified: date  # file modification date (proxy for filing date)
    size_bytes: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mtime_as_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return ""


def _read_pdf_file(path: Path) -> str:
    try:
        from pdfminer.high_level import extract_text  # type: ignore
        text = extract_text(str(path))
        return (text or "")[:_MAX_TEXT_CHARS]
    except ImportError:
        logger.warning(
            "pdfminer.six not installed — skipping PDF %s. "
            "Install with: pip install pdfminer.six",
            path,
        )
        return ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF extraction failed for %s: %s", path, exc)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_local_filings(filings_base: str, filings_dir: str) -> List[LocalFiling]:
    """List all supported documents under ``filings_base/filings_dir/``.

    Returns a list sorted newest-first by modification time.
    Returns an empty list if the directory does not exist.
    """
    dir_path = Path(filings_base) / filings_dir
    if not dir_path.exists():
        return []

    filings: List[LocalFiling] = []
    for fpath in dir_path.iterdir():
        if fpath.is_file() and fpath.suffix.lower() in _SUPPORTED:
            filings.append(
                LocalFiling(
                    path=fpath,
                    modified=_mtime_as_date(fpath),
                    size_bytes=fpath.stat().st_size,
                )
            )

    filings.sort(key=lambda f: f.modified, reverse=True)
    return filings


def get_most_recent_filing(filings_base: str, filings_dir: str) -> Optional[LocalFiling]:
    """Return the most recently modified filing, or None if none exist."""
    filings = list_local_filings(filings_base, filings_dir)
    return filings[0] if filings else None


def read_filing_text(filing: LocalFiling) -> str:
    """Read and return the text content of a local filing.

    Handles .txt/.md (UTF-8) and .pdf (via pdfminer.six if available).
    Returns an empty string on failure.
    """
    suffix = filing.path.suffix.lower()
    if suffix in _TEXT_EXTENSIONS:
        return _read_text_file(filing.path)
    if suffix in _PDF_EXTENSIONS:
        return _read_pdf_file(filing.path)
    logger.warning("Unsupported filing format: %s", filing.path)
    return ""
