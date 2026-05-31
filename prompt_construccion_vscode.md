# Prompt de construcción para VS Code — `prompt_construccion_vscode.md`

> Pega este texto completo en tu agente de programación de VS Code (Claude Code, Copilot
> Agent, Cursor, etc.). Es la especificación completa de la aplicación. Construye con
> TDD: tests primero, después implementación.

---

## CONTEXTO Y OBJETIVO

Quiero construir una aplicación en **Python** que, mediante un **GitHub Action por cron**
(por defecto cada 2 días, configurable), seleccione automáticamente **una** acción de una
lista curada, genere un **análisis fundamental profundo** de esa empresa y publique la
salida como un **fichero Markdown** estilo Substack profesional (referencia editorial:
los Substacks de *Yet Another Value Podcast*).

El sistema es **stateless entre ejecuciones**: todo el estado vive como ficheros en el
propio repositorio y se edita por commit.

## PRINCIPIO RECTOR — DISCIPLINA DE DATOS (no negociable)

Modelo **híbrido**:
- **Hard data (cifras, hechos):** SOLO de fuentes deterministas → EDGAR (filers de la
  SEC) o el documento primario que el usuario deja en `filings/{ticker}/` (presentación
  de resultados, informe anual, hecho relevante) para las empresas no estadounidenses.
- **Web abierta / noticias:** SOLO para *contexto* y *para puntuar la selección*. NUNCA
  como fuente de cifras en el análisis.
- Si para una empresa no hay documento primario, el sistema **no inventa**: marca la
  fuente como `[SIN_DOCUMENTO_PRIMARIO]` y el análisis lo declara abiertamente.

Esta separación debe estar reflejada **en el código**: lo que se pasa al prompt como
"hechos" proviene exclusivamente de las fuentes deterministas; las noticias se pasan
etiquetadas como contexto.

## STACK Y ENTORNO

- Python 3.11+, desarrollo en VS Code.
- Ejecución programada vía **GitHub Actions** (cron).
- Secretos vía **GitHub Actions secrets** (la API key del LLM llegará más adelante:
  variable de entorno `LLM_API_KEY`). **Mientras no exista la key, funciona en modo
  STUB** y debe poder probarse el pipeline entero de punta a punta.
- Fuentes de datos **gratuitas**: EDGAR (API oficial), y para noticias un feed gratuito
  (Google News RSS por nombre de empresa y/o Finnhub free tier). Sin servicios de pago.

## ESTRUCTURA DE REPO PROPUESTA

```
.
├── config/
│   ├── config.yaml          # cadencia, pesos del scoring, idioma de salida, pin opcional
│   └── universe.yaml         # lista de acciones sembrada (ver SEED abajo)
├── filings/
│   └── {ticker}/             # documentos primarios que el usuario deja (no-US). .pdf/.txt
├── state/
│   └── history.json          # qué se analizó y cuándo (last_analyzed por ticker)
├── prompts/
│   └── prompt_analisis.md    # el prompt de análisis editable (ya existe, NO lo generes)
├── output/
│   └── YYYY-MM-DD_{ticker}.md # análisis publicados
├── src/
│   ├── config.py             # carga y valida config + universe
│   ├── symbols.py            # mapeo símbolo Refinitiv -> fuente (ver nota de símbolos)
│   ├── sources/
│   │   ├── edgar.py          # cliente EDGAR para filers US
│   │   └── filings.py        # ingesta de documentos de filings/{ticker}/
│   ├── news.py               # feed de noticias (solo selección)
│   ├── scoring.py            # motor de puntuación
│   ├── selection.py          # topología A: elige #1, respeta pin, top-3 con razones
│   ├── analysis.py           # carga prompt, inyecta inputs, llama al LLM (o stub)
│   ├── render.py             # escribe el Markdown de salida
│   └── pipeline.py           # orquesta todo (entry point)
├── tests/                    # tests unitarios (TDD)
├── .github/workflows/
│   └── analyze.yml           # cron + ejecución del pipeline
├── requirements.txt
└── README.md
```

## CONFIG (esquema)

`config/config.yaml`:
```yaml
cadence_days: 2                # frecuencia del cron (informativo; el cron real va en el workflow)
output_language: "es"          # idioma del análisis
pin: null                      # si se pone un TICKER, fuerza analizar ese; si null, manda el score
cooldown_days: 14              # no repetir una acción analizada hace menos de esto
scoring_weights:
  results: 0.4                 # w_res
  news: 0.3                    # w_news
  staleness: 0.3               # w_stale
results_decay_days: 40         # ventana de decaimiento de la señal "resultados recientes"
news_lookback_days: 14         # ventana para contar noticias
prompt_path: "prompts/prompt_analisis.md"
```

## MOTOR DE PUNTUACIÓN (`scoring.py`)

Para cada acción del universo, calcula un score normalizado:

```
Score = w_res · Resultados + w_news · Noticias + w_stale · Antigüedad − Penalización_cooldown
```

- **Resultados** ∈ [0,1]: 1.0 el día que aparece una presentación/earnings/filing nuevo,
  decae linealmente a 0 en `results_decay_days`. Fuente de la fecha: para US, fecha del
  último filing relevante en EDGAR; para no-US, *timestamp del documento más reciente* en
  `filings/{ticker}/`.
- **Noticias** ∈ [0,1]: **medida RELATIVA a la línea base de cada acción**, no en
  absoluto. Compara el volumen/recencia de noticias en `news_lookback_days` contra la
  media histórica de esa misma acción. Una micro-cap que pasa de 0→3 noticias debe
  puntuar como un gigante que pasa de 40→80. **La ausencia de noticias NO penaliza**
  (contribuye 0, no negativo). Esto es crítico: evita que el feed favorezca
  sistemáticamente a las grandes US y vacíe de la selección a los small caps
  internacionales.
- **Antigüedad** ∈ [0,1]: crece con el tiempo desde `last_analyzed` (de `history.json`).
  Cuanto más tiempo sin analizar, más sube.
- **Penalización_cooldown**: si `last_analyzed` está dentro de `cooldown_days`, hunde el
  score (p. ej. multiplícalo por un factor pequeño o réstale un valor grande) para no
  repetir.

Normaliza cada señal a [0,1] antes de ponderar. Documenta la fórmula en docstrings.

## SELECCIÓN (`selection.py`) — Topología A

- Si `config.pin` tiene un ticker válido → se analiza ese.
- Si no → se analiza el de **mayor score**.
- En ambos casos, calcula el **top-3** por score y genera una breve **justificación por
  qué cada una fue candidata** (qué señal la empujó: resultados recientes / repunte de
  noticias / lleva mucho sin analizarse). Esto se incluye en la salida.
- Es totalmente automático: no hay verja humana en mitad de la ejecución.

## GENERACIÓN DEL ANÁLISIS (`analysis.py`)

1. Carga `prompts/prompt_analisis.md`.
2. Reúne las **fuentes deterministas** de la acción elegida (EDGAR o `filings/{ticker}/`).
   Recorta a las secciones relevantes (MD&A, riesgos, guidance, estados financieros)
   antes de inyectar, para controlar tokens de entrada. Si no hay documento → marca
   `[SIN_DOCUMENTO_PRIMARIO]`.
3. Reúne el **contexto de noticias** (etiquetado como contexto, no como hechos).
4. Inyecta las variables del prompt (`COMPANY`, `TICKER`, `AS_OF_DATE`,
   `OUTPUT_LANGUAGE`, `SELECTION_REASON`, `DETERMINISTIC_SOURCES`, `NEWS_CONTEXT`,
   `MARKET_DATA`).
5. Llama al LLM si `LLM_API_KEY` existe; si no, usa **modo STUB** que devuelve una nota
   de ejemplo bien formada (título + secciones + ~1000 palabras + descargo) para poder
   probar el pipeline sin la key.

## SALIDA (`render.py`)

- Markdown estilo Substack, ~900–1200 palabras (≈2 A4).
- Escribe en `output/YYYY-MM-DD_{ticker}.md`.
- Añade al final un bloque con las **otras 2–3 candidatas del top-3 y su porqué**.
- El Action hace commit del fichero de salida y del `state/history.json` actualizado de
  vuelta al repo (esto requiere permisos de escritura del workflow / un token; configúralo
  y documenta el requisito en el README).
- Inicialmente la salida es **solo Markdown**. No publiques en ninguna plataforma todavía.

## NOTA SOBRE LOS SÍMBOLOS

La lista de origen usa **formato Refinitiv/LSEG** (`ADBE.O`, `EVOG.ST`, `MBR.WA`, `.K`,
etc.), que NO coincide con el formato de las fuentes gratuitas. Construye en `symbols.py`
una tabla de mapeo de símbolo de origen → identificador de la fuente (CIK de EDGAR para
US; nombre/ticker para el feed de noticias y la carpeta `filings/`). Marca cada acción
con `us_filer: true/false` para enrutar EDGAR vs. documento primario.

## GITHUB ACTION (`.github/workflows/analyze.yml`)

- `on: schedule` con cron equivalente a cada 2 días + `workflow_dispatch` para disparo
  manual.
- Instala dependencias, ejecuta `python -m src.pipeline`, hace commit de la salida y del
  estado.
- `LLM_API_KEY` como secret (puede no existir aún → modo stub).

## TDD — ORDEN DE CONSTRUCCIÓN

Escribe tests primero para los componentes deterministas, que son los fáciles de fijar:
1. `scoring.py`: dadas fechas y volúmenes de noticias mock, el score sale como se espera;
   verifica la normalización relativa de noticias y el cooldown.
2. `symbols.py`: el mapeo Refinitiv→fuente y el flag `us_filer`.
3. `selection.py`: pin manda; sin pin manda el score; top-3 y razones correctas.
4. `news.py`: parseo del feed y cálculo de la línea base por acción (mockea la red).
5. `sources/`: EDGAR (mockea HTTP) y la ingesta de `filings/{ticker}/`.
6. `analysis.py`: el modo STUB produce una nota válida; la inyección de variables es
   correcta; el caso `[SIN_DOCUMENTO_PRIMARIO]` se maneja.
7. `render.py`: el Markdown se escribe con el nombre y formato correctos.
8. `pipeline.py`: test de integración end-to-end en modo stub.

## GUARDARRAÍLES (impleméntalos explícitamente)

- Nunca fabricar cifras: solo se pasan como "hechos" las fuentes deterministas.
- Si falta documento primario → nota limitada y honesta, no análisis falso.
- El output incluye descargo de "no es asesoramiento de inversión".
- Sin servicios de pago; sin claves hardcodeadas; secretos solo vía entorno.

## SEED — universo inicial (`config/universe.yaml`)

Siembra el universo con estas empresas. `us_filer: true` → ruta EDGAR; `false` → requiere
documento en `filings/{ticker}/`. (He deduplicado Adobe y Wheaton del listado original;
para Wheaton uso la cotización de NYSE, que es filer de la SEC.)

```yaml
universe:
  - {name: "Adobe",                    src_symbol: "ADBE.O",   us_filer: true}
  - {name: "SK Hynix",                 src_symbol: "HY9Hy.F",  us_filer: false}
  - {name: "Minera Alamos",            src_symbol: "MAI.V",    us_filer: false}
  - {name: "Pan American Silver",      src_symbol: "PAAS.TO",  us_filer: true}   # 40-F en SEC
  - {name: "Wheaton Precious Metals",  src_symbol: "WPM",      us_filer: true}   # 40-F en SEC
  - {name: "Mitie",                    src_symbol: "MTO.L",    us_filer: false}
  - {name: "VersaBank",                src_symbol: "VBNK.O",   us_filer: true}
  - {name: "Andean Precious Metals",   src_symbol: "APM.TO",   us_filer: false}
  - {name: "Carlisle",                 src_symbol: "CSL",      us_filer: true}
  - {name: "Alphabet C",               src_symbol: "GOOG.O",   us_filer: true}
  - {name: "Nagarro SE",               src_symbol: "NA9n.DE",  us_filer: false}
  - {name: "Valeura Energy",           src_symbol: "VLE.TO",   us_filer: false}
  - {name: "West African Resources",   src_symbol: "WAF.AX",   us_filer: false}
  - {name: "Titan America",            src_symbol: "TTAM.K",   us_filer: true}
  - {name: "Santander",                src_symbol: "SAN",      us_filer: true}   # 20-F en SEC
  - {name: "Brookfield",               src_symbol: "BN",       us_filer: true}
  - {name: "goeasy",                   src_symbol: "GSY.TO",   us_filer: false}
  - {name: "Saturn Oil",               src_symbol: "SOIL.TO",  us_filer: false}
  - {name: "NVIDIA",                   src_symbol: "NVDA.O",   us_filer: true}
  - {name: "Titan Cement",             src_symbol: "TITC.BR",  us_filer: false}
  - {name: "Watches of Switzerland",   src_symbol: "WOSG.L",   us_filer: false}
  - {name: "Bloober",                  src_symbol: "BLOP.WA",  us_filer: false}
  - {name: "Mid-America Apartment",    src_symbol: "MAA",      us_filer: true}
  - {name: "Optima Health",            src_symbol: "OPT.L",    us_filer: false}
  - {name: "Teleperformance",          src_symbol: "TEPRF.PA", us_filer: false}
  - {name: "Alexandria RE",            src_symbol: "ARE",      us_filer: true}
  - {name: "Verallia",                 src_symbol: "VRLA.PA",  us_filer: false}
  - {name: "Mader Group",              src_symbol: "MAD.AX",   us_filer: false}
  - {name: "Big Yellow",               src_symbol: "BYG.L",    us_filer: false}
  - {name: "Evolution AB",             src_symbol: "EVOG.ST",  us_filer: false}
  - {name: "Georgia Capital",          src_symbol: "CGEO.L",   us_filer: false}
  - {name: "Linea Directa",            src_symbol: "LDA.MC",   us_filer: false}
  - {name: "Newprinces",               src_symbol: "NWLF.MI",  us_filer: false}
  - {name: "Clarus",                   src_symbol: "CLAR.O",   us_filer: true}
  - {name: "Eurofins Scientific",      src_symbol: "EUFI.PA",  us_filer: false}
  - {name: "Concentrix",               src_symbol: "CNXC.O",   us_filer: true}
  - {name: "Brookfield Asset Mgmt",    src_symbol: "BAM",      us_filer: true}
  - {name: "Kelly Partners",           src_symbol: "KPG.AX",   us_filer: false}
  - {name: "Endava",                   src_symbol: "DAVA.K",   us_filer: true}   # 20-F en SEC
  - {name: "Colliers International",   src_symbol: "CIGI.O",   us_filer: true}
  - {name: "Copart",                   src_symbol: "CPRT.O",   us_filer: true}
  - {name: "Mo-Bruk SA",               src_symbol: "MBR.WA",   us_filer: false}
  - {name: "Pool",                     src_symbol: "POOL.O",   us_filer: true}
  - {name: "SDI Group",                src_symbol: "SDIS.L",   us_filer: false}
  - {name: "TransUnion",               src_symbol: "TRU",      us_filer: true}
  - {name: "Microsoft",                src_symbol: "MSFT.O",   us_filer: true}
  - {name: "Meta Platforms",           src_symbol: "META.O",   us_filer: true}
  - {name: "Macfarlane Group",         src_symbol: "MACF.L",   us_filer: false}
  - {name: "Storskogen AB",            src_symbol: "STORb.ST", us_filer: false}
  - {name: "Auto Partner",             src_symbol: "APR.WA",   us_filer: false}
```

## NOTA FINAL PARA EL AGENTE

El fichero `prompts/prompt_analisis.md` **ya existe** (lo aporta el usuario): no lo
generes, solo cárgalo. Verifica los flags `us_filer` y el mapeo de símbolos contra
EDGAR durante la implementación, porque algunos extranjeros (Santander, Endava, Pan
American, Wheaton) cotizan en EE. UU. como 20-F/40-F y conviene confirmar su CIK real.
Empieza por los tests del motor de scoring.
