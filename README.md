<p align="center">
  <img src="docs/assets/rappi-ops-readme-hero.svg" alt="Rappi Ops Copilot" width="900">
</p>

# Rappi Ops Copilot

Rappi Ops Copilot is a reproducible conversational analytics prototype for operational KPI analysis. It combines a deterministic FastAPI analytics service, importable n8n workflows, DeepSeek-powered natural-language orchestration, and a Next.js web interface for asking questions, reviewing executive insights, and exporting results.

The solution is designed for an operations user who wants to ask questions such as "Which zones have the lowest Perfect Orders?", "Compare wealthy vs non-wealthy zones in Mexico", or "Show the latest executive insight report" without writing SQL.

## What This Project Delivers

- A local Docker Compose stack with Postgres, FastAPI, n8n, and Next.js.
- A normalized analytics layer built from the provided dummy operations workbook,
  including city-alias lookup, source duplicate removal, and explicit outlier flags.
- Read-only SQL execution guardrails for model-generated queries.
- CSV and LaTeX-generated PDF report exports for query results.
- An automatic executive insights report with deterministic facts, optional LLM-authored
  structured narrative JSON, Markdown, HTML, LaTeX, PDF, API, and UI access.
- Importable n8n workflow JSON files for the chat agent and scheduled insights job.
- Deterministic smoke tests that validate the core analytics behavior.

## How It Works

1. The source workbook in `data/` is normalized by `ops_copilot.data_loader`.
   City aliases are materialized separately, so user-facing labels such as `CDMX`
   can resolve to workbook values such as `Ciudad De Mexico`.
   Metric rows also carry `is_outlier` so unsafe rate values such as extreme
   Lead Penetration can be excluded by default without deleting the raw source value.
2. On API startup, the workbook is loaded into Postgres when `DATABASE_URL` is available.
3. The FastAPI service exposes schema context, semantic query helpers, guarded SQL execution, exports, and executive insights endpoints.
4. The n8n chat workflow uses DeepSeek `deepseek-v4-pro` to translate natural-language requests into read-only analytical queries and API calls.
5. The executive insights workflow computes facts deterministically, can ask DeepSeek for
   a structured narrative layer, and renders the final PDF from a deterministic LaTeX template.
6. The Next.js app embeds the public n8n Chat Trigger and displays the latest generated executive insight report.
7. The scheduled n8n workflow refreshes the executive report every Monday at 07:00 in `America/Bogota`.

The model can generate SQL, but the API only accepts a single `SELECT` or `WITH` statement, strips trailing semicolons, blocks write/admin keywords, rejects comments, executes through a read-only Postgres connection, and wraps the query with a server-side row limit.

## Repository Structure

```text
.
|-- data/                         # Source dummy operations workbook
|-- db/schema.sql                 # Postgres semantic schema
|-- docs/                         # Design notes and brand prompts
|-- frontend/                     # Next.js embedded chat and insights UI
|-- ops_copilot/                  # FastAPI app, loaders, query engine, insights logic
|-- scripts/                      # n8n setup, ingestion, and smoke-test scripts
|-- workflows/                    # Importable n8n workflow exports
|-- docker-compose.yml            # Reproducible local stack
|-- Dockerfile                    # Analytics API image
|-- pyproject.toml                # Python package metadata and dependencies
`-- README.md                     # Project setup and reproducibility guide
```

## Prerequisites

- Docker and Docker Compose.
- Python 3.11+ for local scripts.
- A DeepSeek API key for live chat answers through n8n and for LLM-authored scheduled reports.
- Optional for non-Docker API hosts: `tectonic`, `latexmk`, `xelatex`, or `pdflatex` to
  compile the LaTeX executive report into PDF. The included API Docker image installs the
  required TeX Live packages. If compilation fails and `DEEPSEEK_API_KEY` is available to
  the API service, the report retries with an LLM-based LaTeX repair loop.

The deterministic API, ingestion, and smoke tests can run without a DeepSeek key. The n8n
chat agent and `authoring_mode: "llm"` scheduled insights report need `DEEPSEEK_API_KEY`
to call the model.

## Estimated API Cost

This project uses the paid DeepSeek API only for the n8n chat agent and optional
LLM-authored report text. The configured model is `deepseek-v4-pro`.

Based on DeepSeek's published V4 Pro pricing of `$0.435` per 1M uncached input
tokens, `$0.003625` per 1M cached input tokens, and `$0.87` per 1M output tokens,
a typical 10-question analytics chat session is estimated at about `$0.10`.
That estimate assumes roughly 150k uncached input tokens and 30k output tokens
across the session, including tool-planning prompts, schema context, SQL results,
and final answers. Short sessions or cache hits cost less; longer answers,
retries, or very large result context cost more.

Generating the scheduled executive insight narrative usually adds about `$0.01`
to `$0.02` per report, plus a similar amount only if the optional LLM LaTeX
repair loop is triggered. Deterministic API calls, ingestion, smoke tests, CSV
exports, and deterministic PDF rendering do not call paid APIs.

Check the official DeepSeek pricing page before production use because token
prices can change: https://api-docs.deepseek.com/quick_start/pricing

## Local Quickstart

Create the local environment file:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
POSTGRES_PASSWORD=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-pro
LATEX_REPAIR_ATTEMPTS=2
N8N_ENCRYPTION_KEY=
```

Use `openssl rand -base64 32` to generate local values for `POSTGRES_PASSWORD`
and `N8N_ENCRYPTION_KEY`, then paste the generated values into `.env`.

Install the local Python package before running repository scripts from the host:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Start Postgres, the analytics API, n8n, and the web app:

```bash
docker compose up --build
```

Open the local services:

```text
Web app: http://localhost:3000
n8n:     http://localhost:5678
API:     http://localhost:8000/health
```

Import and activate the n8n workflows:

```bash
python3 scripts/setup_n8n.py --activate
```

The setup script imports or updates:

- `workflows/rappi_ops_chat_agent.json`
- `workflows/rappi_ops_automatic_insights.json`
- `DeepSeek account` n8n credential from `DEEPSEEK_API_KEY`
- `Rappi Ops Postgres` n8n credential for the local Postgres service

After activation, the web app uses the committed Chat Trigger webhook by default:

```text
http://localhost:5678/webhook/b2a0878f-58c7-4f89-a98b-2dc29cd637a8/chat
```

## Manual n8n Import

If you do not use `scripts/setup_n8n.py`, import these files manually in n8n:

- `workflows/rappi_ops_chat_agent.json`
- `workflows/rappi_ops_automatic_insights.json`

Then create these credentials:

- `DeepSeek account`: DeepSeek API credential with your API key.
- `Rappi Ops Postgres`: Postgres credential using host `postgres`, port `5432`, database `rappi_ops`, user `rappi`, and the `POSTGRES_PASSWORD` value from `.env`.

Activate both workflows. The automatic insights workflow calls:

```text
POST http://ops-api:8000/insights/generate
GET  http://ops-api:8000/insights/latest.pdf
```

It also exposes a production reload webhook used by the web UI through the Ops API wrapper:

```text
POST http://localhost:8000/insights/workflow/run
POST http://localhost:5678/webhook/rappi-ops-executive-insights/run
```

The imported automatic insights workflow sends `authoring_mode: "llm"`, so the API asks
DeepSeek for validated report narrative JSON before rendering LaTeX/PDF. Use
`authoring_mode: "deterministic"` for a model-free report or `authoring_mode: "auto"` to
use DeepSeek when `DEEPSEEK_API_KEY` is configured and otherwise fall back to deterministic
copy.

See `workflows/README.md` for the workflow-specific import notes.

## API Usage

Health check:

```bash
curl http://localhost:8000/health
```

Schema:

```bash
curl http://localhost:8000/schema
```

Generate or read the latest executive insight report:

```bash
curl -X POST http://localhost:8000/insights/generate \
  -H 'Content-Type: application/json' \
  -d '{"source":"manual","persist":true,"authoring_mode":"auto"}'

curl -X POST http://localhost:8000/insights/workflow/run
curl http://localhost:8000/insights/latest
curl http://localhost:8000/insights/latest.md
curl http://localhost:8000/insights/latest.html
curl http://localhost:8000/insights/latest.tex
curl -OJ http://localhost:8000/insights/latest.pdf
```

The report JSON is the source of truth. When `authoring_mode` is `llm`, DeepSeek writes
only the structured narrative fields; Python still owns metrics, evidence, chart data, and
LaTeX rendering. Insight generation validates the cleaned `load_workbook` dataset first:
duplicate fact keys must be gone, invalid rate values must be flagged as outliers, and
flagged source outliers are excluded from scoring before the LLM sees the factsheet. The
LaTeX source is always generated from that JSON. The PDF endpoint compiles the source when
a local TeX compiler is available. If compilation fails, the API sends the compiler log,
generated LaTeX, and structured report context to DeepSeek, asks for a corrected full
`.tex` document, and retries up to `LATEX_REPAIR_ATTEMPTS`. The final repaired source is
written back to `outputs/reports/latest-executive-insights.tex`, with repair notes beside it.

Run a guarded model-facing SQL query:

```bash
curl -X POST http://localhost:8000/sql \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Compare Perfect Orders between wealthy and non-wealthy zones in Mexico",
    "sql": "select z.zone_type, avg(f.value) as perfect_orders, count(distinct z.zone_id) as n_zones from fact_metric_week f join dim_zone z on z.zone_id = f.zone_id where f.metric_key = '\''perfect_orders'\'' and f.week_offset = 0 and z.country = '\''MX'\'' group by z.zone_type order by perfect_orders desc",
    "limit": 50,
    "visualization": "bar"
  }'
```

The response includes a `query_id`. Export that result during the same API runtime:

```bash
curl -OJ http://localhost:8000/exports/<query_id>.csv
curl -OJ http://localhost:8000/exports/<query_id>.pdf
```

The SQL and semantic query responses also include an `exports` array with browser-safe
download URLs. The n8n export tool uses the same metadata endpoint:

```bash
curl http://localhost:8000/exports/<query_id>/links?format=both
```

The query PDF export is rendered from deterministic LaTeX and compiled by the API.
The matching `.tex` source and PDF are written under `outputs/query-exports/`.

## Data Ingestion

Dry-run workbook normalization:

```bash
python3 scripts/ingest_workbook.py --dry-run
```

The dry run prints a data-quality status and warnings. Current known source-data
warnings are exact duplicate metric rows removed before fact generation, order-only
zones labeled `Unknown` for missing segment metadata, and flagged Lead Penetration
outliers.

Load the workbook into local Postgres:

```bash
set -a
source .env
set +a
DATABASE_URL="postgresql://${POSTGRES_USER:-rappi}:${POSTGRES_PASSWORD}@localhost:5432/${POSTGRES_DB:-rappi_ops}" \
python3 scripts/ingest_workbook.py
```

The API reads the workbook directly for a zero-configuration demo and also loads Postgres on startup when `DATABASE_URL` is configured. The schema and ingestion path are included so the data layer can be hardened without changing the n8n workflow contract.

## Validation

Run deterministic smoke tests against the workbook:

```bash
python3 scripts/smoke_test.py
```

The smoke test covers rankings, comparisons, trends, country aggregation, high/low segmentation, growth diagnostics, problematic-zone scoring, and automatic executive insight generation.

For frontend validation:

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

## Code and Reproducibility

This repository includes everything needed to reproduce the prototype locally:

- Source workbook committed under `data/`.
- API, UI, database, and n8n services declared in `docker-compose.yml`.
- Python dependencies declared in `pyproject.toml`.
- Frontend dependencies locked in `frontend/package-lock.json`.
- Environment template in `.env.example`.
- n8n workflow exports committed under `workflows/`.
- n8n import automation in `scripts/setup_n8n.py`.
- Deterministic validation in `scripts/smoke_test.py`.

Reproducible setup sequence:

```bash
cp .env.example .env
# Fill POSTGRES_PASSWORD, DEEPSEEK_API_KEY, and N8N_ENCRYPTION_KEY in .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
docker compose up --build
python3 scripts/setup_n8n.py --activate
python3 scripts/smoke_test.py
```

If the DeepSeek account has no available balance, the API and deterministic smoke tests still work, but the live n8n chat workflow will return a model-provider error until billing is available.

## Troubleshooting

- If `scripts/setup_n8n.py` fails, confirm that `docker compose up --build` is running and that `.env` contains `DEEPSEEK_API_KEY`.
- If the web chat says the workflow failed, open n8n at `http://localhost:5678` and inspect the latest execution.
- If the Chat Trigger URL changes after manual import, update `NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL` in `.env` and restart the `web` service.
- If exports return `404`, rerun the query first. Export IDs are cached in memory for the current API process.
- If PDF exports return `503`, confirm the API host has `tectonic`, `latexmk`, `xelatex`, or `pdflatex`. The Docker API image includes the required TeX packages.
