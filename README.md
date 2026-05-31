# RevisoTesisPortfolio

Automated equity-analysis pipeline that selects one stock from a curated universe every two days, generates a deep-fundamental note in Markdown (Substack-ready style), and commits it back to this repository via GitHub Actions.

---

## Architecture overview

```
config/universe.yaml  →  scoring engine  →  selection  →  EDGAR / local filings  →  LLM  →  output/
                                                                  ↑
                                                         state/history.json
```

| Layer | Module | Role |
|---|---|---|
| Configuration | `src/config.py` | Loads `config/config.yaml` + `config/universe.yaml` |
| Symbol mapping | `src/symbols.py` | Refinitiv symbol → EDGAR CIK or local folder |
| Data – US | `src/sources/edgar.py` | EDGAR REST API (10-K, 10-Q, 20-F, 40-F) |
| Data – non-US | `src/sources/filings.py` | Local files dropped into `filings/{ticker}/` |
| News | `src/news.py` | Google News RSS (no key required) |
| Scoring | `src/scoring.py` | Weighted signal formula |
| Selection | `src/selection.py` | Top-score or pin override |
| Analysis | `src/analysis.py` | Prompt injection + LLM call (or STUB) |
| Render | `src/render.py` | Markdown output + history update |
| Pipeline | `src/pipeline.py` | Orchestrator / entry point |

---

## Data discipline

**Hard data (facts/numbers):** exclusively from EDGAR filings or the user's primary documents in `filings/`.  
**News / web:** used only for scoring and as contextual colour — never as a source of figures.  
If no primary document exists for a non-US company, the pipeline emits a limited, honest note marked `[SIN_DOCUMENTO_PRIMARIO]`.

---

## Quick start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Run the pipeline in STUB mode (no API key needed)
python -m src.pipeline

# 3. Find the output
ls output/
```

## Running tests

```bash
pytest -v
```

All tests are deterministic — network calls are mocked.

---

## Configuration

### `config/config.yaml`

| Key | Default | Description |
|---|---|---|
| `cadence_days` | `2` | Informational — actual cadence is the cron in the workflow |
| `output_language` | `es` | Language for the analysis note |
| `pin` | `null` | Force a specific `src_symbol` (overrides scoring) |
| `cooldown_days` | `14` | Minimum days between re-analyses of the same ticker |
| `scoring_weights.results` | `0.4` | Weight for recent-filing signal |
| `scoring_weights.news` | `0.3` | Weight for relative news activity |
| `scoring_weights.staleness` | `0.3` | Weight for time-since-last-analysis |
| `results_decay_days` | `40` | Days until filing signal fully decays |
| `news_lookback_days` | `14` | Window for counting news activity |
| `news_locale` | `en-US` | Google News edition (`hl-GL` format, e.g. `es-ES`, `de-DE`) |
| `prompt_path` | `prompts/prompt_analisis.md` | Path to the editable analysis prompt |

### `config/universe.yaml`

Add or remove entries freely. Each entry:
```yaml
- {name: "Company Name", src_symbol: "TICK.EX", us_filer: true}
```
- `us_filer: true` → routed to EDGAR (requires a valid CIK in `src/symbols.py`).
- `us_filer: false` → expects documents in `filings/{filings_dir}/`.

---

## Adding a non-US company's documents

1. Find the `filings_dir` for the company in `src/symbols.py`.
2. Drop the most recent annual report or earnings release (`.pdf` or `.txt`) into `filings/{filings_dir}/`.
3. The pipeline will pick it up automatically on the next run.

---

## LLM configuration

Set these as **GitHub Actions secrets** (`Settings → Secrets and variables → Actions`):

| Secret | Required | Description | Default |
|---|---|---|---|
| `LLM_API_KEY` | No | Your API key (OpenAI-compatible). If absent, pipeline runs in STUB mode. | — |
| `LLM_BASE_URL` | No | Base URL for the LLM API | `https://api.openai.com/v1` |
| `LLM_MODEL` | No | Model name | `gpt-4o` |
| `EDGAR_USER_AGENT` | **Yes** | User-Agent header sent to SEC EDGAR — must contain a real contact email. | — |

**STUB mode** (no key) produces a well-formed example note so you can test the full pipeline without incurring LLM costs.

### EDGAR User-Agent (obligatorio en producción)

The SEC [requires](https://www.sec.gov/developer) every automated client to identify itself with a descriptive User-Agent that includes a valid contact e-mail. Using a fake address may result in your IP being blocked.

```
# Formato esperado
NombreApp/versión nombre@tudominio.com

# Ejemplo
RevisoTesisPortfolio/1.0 antonio@tudominio.com
```

Steps to configure it:

1. Go to **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `EDGAR_USER_AGENT`
3. Value: `RevisoTesisPortfolio/1.0 tu@email.com`  ← replace with your actual e-mail.

> **Locally:** export the variable before running the pipeline so the warning disappears:
> ```bash
> export EDGAR_USER_AGENT="RevisoTesisPortfolio/1.0 tu@email.com"
> python -m src.pipeline
> ```
> On Windows:
> ```powershell
> $env:EDGAR_USER_AGENT = "RevisoTesisPortfolio/1.0 tu@email.com"
> python -m src.pipeline
> ```

---

## GitHub Actions requirements

The workflow (`analyze.yml`) commits the output file and `state/history.json` back to the repository.  
This requires the workflow to have **write permissions** on repository contents.

- For most public repos: `Settings → Actions → General → Workflow permissions → Read and write`.
- For org repos with stricter policies: create a fine-grained PAT with `Contents: Write`, store it as a secret `PAT_TOKEN`, and update the checkout step to use `token: ${{ secrets.PAT_TOKEN }}`.

---

## Scoring formula

```
Score = w_res × Results + w_news × News + w_stale × Staleness
```

Where:
- **Results** ∈ [0,1]: linear decay from 1.0 on filing day to 0 after `results_decay_days`.
- **News** ∈ [0,1]: *relative* measure — `recent_count / (2 × baseline)`. A micro-cap going 0→3 articles scores identically to a large-cap going 40→80. Zero news contributes 0, never negative.
- **Staleness** ∈ [0,1]: grows with days since last analysis; saturates at 1.0 after 180 days (or immediately if never analysed).
- **Cooldown penalty**: if last analysed within `cooldown_days`, multiply total by 0.05 (near-zero).

---

## CIK verification

Several US-filer CIKs in `src/symbols.py` are marked `# VERIFY`.  
Confirm them at: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=NAME&type=&owner=include&count=10`

---

## Disclaimer

All generated analyses are for **informational purposes only** and do not constitute investment advice.
