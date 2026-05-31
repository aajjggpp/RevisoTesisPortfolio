"""Analysis generation module.

Loads ``prompts/prompt_analisis.md``, injects pipeline variables, then
either calls the LLM API (if ``LLM_API_KEY`` is set) or returns a
well-formed STUB note for end-to-end testing without a key.

LLM API
-------
Compatible with any OpenAI-format chat-completions endpoint.
Environment variables:
  LLM_API_KEY   – required for live mode (secret in GitHub Actions).
  LLM_BASE_URL  – base URL (default: https://api.openai.com/v1).
  LLM_MODEL     – model name (default: gpt-4o).

Prompt format
-------------
The prompt file contains two sections delimited by ``## SYSTEM`` and
``## USER``.  The USER section is the template with ``{{VARIABLE}}``
placeholders.  Only the text between ``## USER`` and the trailing code-block
fence is used as the user message.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"
_MAX_TOKENS_OUT = 2000
_TEMPERATURE = 0.3

# Marker for missing primary source.
NO_PRIMARY_DOCUMENT = "[SIN_DOCUMENTO_PRIMARIO]"


# ---------------------------------------------------------------------------
# Prompt loading & variable injection
# ---------------------------------------------------------------------------

def _load_prompt_sections(prompt_path: str) -> tuple[str, str]:
    """Return (system_prompt, user_template) from the prompt markdown file."""
    text = Path(prompt_path).read_text(encoding="utf-8")

    # Extract SYSTEM section.
    system_match = re.search(
        r"##\s*SYSTEM\s*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.IGNORECASE
    )
    system_prompt = system_match.group(1).strip() if system_match else ""

    # Extract USER template (content inside the triple-backtick block under ## USER).
    user_match = re.search(
        r"##\s*USER.*?```\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
    )
    user_template = user_match.group(1).strip() if user_match else ""

    return system_prompt, user_template


def _inject_variables(template: str, variables: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` placeholders in *template* with values from *variables*."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", value)
    return result


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def _call_llm_with_retry(
    system_prompt: str,
    user_message: str,
    api_key: str,
    base_url: str,
    model: str,
    session: Optional[requests.Session],
    retries: int = 3,
) -> str:
    """Call the LLM with exponential-backoff retries before raising."""
    last_exc: Exception = RuntimeError("unknown")
    for attempt in range(retries):
        try:
            return _call_llm(system_prompt, user_message, api_key, base_url, model, session)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s…
                logger.warning(
                    "LLM attempt %d/%d failed (%s) — retrying in %ds…",
                    attempt + 1, retries, exc, wait,
                )
                import time
                time.sleep(wait)
    raise last_exc


def _call_llm(
    system_prompt: str,
    user_message: str,
    api_key: str,
    base_url: str,
    model: str,
    session: Optional[requests.Session],
) -> str:
    """Call the LLM chat-completions endpoint and return the assistant message."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": _MAX_TOKENS_OUT,
        "temperature": _TEMPERATURE,
    }

    requester = session or requests
    resp = requester.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# STUB mode
# ---------------------------------------------------------------------------

def _stub_note(variables: dict[str, str]) -> str:
    """Return a well-formed example analysis note for stub/testing mode."""
    company = variables.get("COMPANY", "Empresa de Ejemplo")
    ticker = variables.get("TICKER", "EJM")
    as_of = variables.get("AS_OF_DATE", "2026-01-01")
    reason = variables.get("SELECTION_REASON", "sin señal específica")
    has_source = variables.get("DETERMINISTIC_SOURCES", NO_PRIMARY_DOCUMENT)

    if NO_PRIMARY_DOCUMENT in has_source:
        return f"""# {company} ({ticker}) — Nota limitada por ausencia de documento primario

*Fecha de corte: {as_of} | Modo: STUB*

---

## Por qué aparece esta empresa hoy

{reason}

## Advertencia importante

No hay documento primario disponible para {company} en la carpeta `filings/`.
Sin un filing o informe de resultados verificable, no es posible realizar un
análisis fundamental completo con cifras trazables.

Para activar el análisis completo, deposita el informe de resultados más
reciente o el informe anual en formato `.pdf` o `.txt` en la carpeta
`filings/{ticker}/`.

---

*Este análisis fue generado en **modo STUB** (sin LLM_API_KEY configurada).
No constituye asesoramiento de inversión.*
"""

    return f"""# {company} ({ticker}): ¿Momento de prestar atención?

*Fecha de corte: {as_of} | Modo: STUB — ejemplo de formato*

---

## El negocio en breve

{company} opera en su sector con un modelo de negocio que genera flujos de
caja recurrentes. [Esta sección sería completada por el LLM con datos reales
del filing.]

## Por qué ahora

{reason}

El mercado parece estar descontando un escenario excesivamente negativo.
La percepción variante: los fundamentales más recientes muestran resiliencia
que el consenso no está reflejando completamente.

## Los números que importan

*[En modo live, el LLM extraería aquí cifras reales del documento primario:
ingresos, márgenes EBIT, FCF, ratio deuda/EBITDA, valoración EV/EBIT, etc.
Solo se incluirían números con referencia de fuente, p.ej. `[10-Q Q1-2026]`.]*

Los datos de mercado entregados:
{variables.get("MARKET_DATA", "[Sin datos de mercado]")}

## El caso bajista y los riesgos clave

El contraargumento principal: si el ciclo macro se deteriora más de lo
esperado, los múltiplos actuales podrían comprimirse adicionalmente.
Los riesgos regulatorios y de tipo de cambio también merecen seguimiento.

## Qué vigilar / catalizadores

- Próxima presentación de resultados trimestrales.
- Evolución del guidance para el ejercicio completo.
- Noticias recientes: {variables.get("NEWS_CONTEXT", "[Sin contexto de noticias]")[:200]}

## Conclusión

Asimetría razonable si los fundamentales se confirman en el próximo trimestre.
La tesis requiere revisión ante cualquier deterioro del guidance.

---

*Este documento ha sido generado en **modo STUB** (variable `LLM_API_KEY`
no configurada). Es un ejemplo de formato, no un análisis real.*

**Descargo:** Este contenido es puramente informativo y no constituye
asesoramiento de inversión. El autor puede tener o no posiciones en los
valores mencionados. Consulte siempre con un asesor financiero cualificado
antes de tomar decisiones de inversión.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_analysis(
    prompt_path: str,
    variables: dict[str, str],
    session: Optional[requests.Session] = None,
) -> str:
    """Generate the analysis note.

    In live mode (``LLM_API_KEY`` set) calls the LLM API.
    In stub mode returns a formatted example note for pipeline testing.

    Parameters
    ----------
    prompt_path:
        Path to ``prompts/prompt_analisis.md``.
    variables:
        Dict with keys: COMPANY, TICKER, AS_OF_DATE, OUTPUT_LANGUAGE,
        SELECTION_REASON, DETERMINISTIC_SOURCES, NEWS_CONTEXT, MARKET_DATA.
    session:
        Optional requests.Session for testing.

    Returns
    -------
    Markdown string of the analysis note.
    """
    api_key = os.environ.get("LLM_API_KEY", "").strip()

    if not api_key:
        logger.info("LLM_API_KEY not set — running in STUB mode.")
        return _stub_note(variables)

    system_prompt, user_template = _load_prompt_sections(prompt_path)
    user_message = _inject_variables(user_template, variables)

    base_url = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL).strip()
    model = os.environ.get("LLM_MODEL", _DEFAULT_MODEL).strip()

    logger.info("Calling LLM (%s) for %s…", model, variables.get("TICKER", "?"))
    try:
        return _call_llm_with_retry(
            system_prompt=system_prompt,
            user_message=user_message,
            api_key=api_key,
            base_url=base_url,
            model=model,
            session=session,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM call failed after retries: %s — falling back to STUB.", exc)
        return _stub_note(variables)
