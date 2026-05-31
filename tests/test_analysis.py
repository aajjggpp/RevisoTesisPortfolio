"""Tests for src/analysis.py — written first (TDD)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analysis import (
    NO_PRIMARY_DOCUMENT,
    _inject_variables,
    _load_prompt_sections,
    _stub_note,
    build_analysis,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROMPT_CONTENT = """
## SYSTEM

You are a helpful analyst.

## USER (template)

```
EMPRESA: {{COMPANY}}  ({{TICKER}})
FECHA: {{AS_OF_DATE}}
IDIOMA: {{OUTPUT_LANGUAGE}}
SELECCIÓN: {{SELECTION_REASON}}
FUENTES: {{DETERMINISTIC_SOURCES}}
NOTICIAS: {{NEWS_CONTEXT}}
MERCADO: {{MARKET_DATA}}
```
"""

SAMPLE_VARS = {
    "COMPANY": "Adobe Inc.",
    "TICKER": "ADBE",
    "AS_OF_DATE": "2026-05-31",
    "OUTPUT_LANGUAGE": "es",
    "SELECTION_REASON": "resultados recientes",
    "DETERMINISTIC_SOURCES": "[10-K FY25] Revenue: $21.5B",
    "NEWS_CONTEXT": "- Adobe beats estimates",
    "MARKET_DATA": "[Sin datos]",
}


# ---------------------------------------------------------------------------
# _load_prompt_sections
# ---------------------------------------------------------------------------

class TestLoadPromptSections:
    def test_extracts_system_and_user(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text(PROMPT_CONTENT, encoding="utf-8")
        system, user = _load_prompt_sections(str(f))
        assert "helpful analyst" in system
        assert "{{COMPANY}}" in user

    def test_system_without_user_returns_empty_user(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text("## SYSTEM\nHello.\n", encoding="utf-8")
        system, user = _load_prompt_sections(str(f))
        assert "Hello" in system
        assert user == ""

    def test_missing_file_raises(self):
        with pytest.raises((FileNotFoundError, OSError)):
            _load_prompt_sections("nonexistent/path.md")


# ---------------------------------------------------------------------------
# _inject_variables
# ---------------------------------------------------------------------------

class TestInjectVariables:
    def test_all_variables_replaced(self):
        template = "Company: {{COMPANY}} Ticker: {{TICKER}}"
        result = _inject_variables(template, {"COMPANY": "Adobe", "TICKER": "ADBE"})
        assert result == "Company: Adobe Ticker: ADBE"

    def test_unknown_variable_left_as_is(self):
        template = "{{UNKNOWN}} {{COMPANY}}"
        result = _inject_variables(template, {"COMPANY": "Adobe"})
        assert "{{UNKNOWN}}" in result
        assert "Adobe" in result

    def test_empty_variables(self):
        template = "Hello {{COMPANY}}"
        result = _inject_variables(template, {})
        assert result == "Hello {{COMPANY}}"


# ---------------------------------------------------------------------------
# _stub_note
# ---------------------------------------------------------------------------

class TestStubNote:
    def test_returns_string(self):
        note = _stub_note(SAMPLE_VARS)
        assert isinstance(note, str)
        assert len(note) > 100

    def test_contains_disclaimer(self):
        note = _stub_note(SAMPLE_VARS)
        lower = note.lower()
        assert "asesoramiento" in lower or "descargo" in lower or "stub" in lower.lower()

    def test_contains_company_name(self):
        note = _stub_note(SAMPLE_VARS)
        assert "Adobe" in note

    def test_no_primary_document_produces_limited_note(self):
        vars_no_doc = {**SAMPLE_VARS, "DETERMINISTIC_SOURCES": NO_PRIMARY_DOCUMENT}
        note = _stub_note(vars_no_doc)
        assert "SIN_DOCUMENTO_PRIMARIO" in note or "sin_documento" in note.lower() or "primario" in note.lower()

    def test_stub_note_markdown_has_heading(self):
        note = _stub_note(SAMPLE_VARS)
        assert note.strip().startswith("#")


# ---------------------------------------------------------------------------
# build_analysis
# ---------------------------------------------------------------------------

class TestBuildAnalysis:
    def test_stub_mode_when_no_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        f = tmp_path / "prompt.md"
        f.write_text(PROMPT_CONTENT, encoding="utf-8")
        result = build_analysis(str(f), SAMPLE_VARS)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_live_mode_calls_llm(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")

        f = tmp_path / "prompt.md"
        f.write_text(PROMPT_CONTENT, encoding="utf-8")

        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "# Análisis\nContenido del análisis."}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_session.post.return_value = mock_resp

        result = build_analysis(str(f), SAMPLE_VARS, session=mock_session)
        assert "Análisis" in result
        assert mock_session.post.called

    def test_llm_failure_falls_back_to_stub(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        f = tmp_path / "prompt.md"
        f.write_text(PROMPT_CONTENT, encoding="utf-8")

        mock_session = MagicMock()
        mock_session.post.side_effect = Exception("LLM timeout")

        result = build_analysis(str(f), SAMPLE_VARS, session=mock_session)
        # Should fall back gracefully to stub.
        assert isinstance(result, str)
        assert len(result) > 50

    def test_variable_injection_reaches_llm(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
        f = tmp_path / "prompt.md"
        f.write_text(PROMPT_CONTENT, encoding="utf-8")

        captured_payload = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            resp.raise_for_status = MagicMock()
            return resp

        mock_session = MagicMock()
        mock_session.post.side_effect = fake_post

        build_analysis(str(f), SAMPLE_VARS, session=mock_session)

        messages = captured_payload.get("messages", [])
        user_content = next(
            (m["content"] for m in messages if m["role"] == "user"), ""
        )
        # The injected company name should appear in the user message.
        assert "Adobe" in user_content
        # No unresolved placeholders.
        assert "{{COMPANY}}" not in user_content
