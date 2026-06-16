# Rappi Ops Copilot
<img width="4112" height="2412" alt="Screenshot 2026-06-16 at 12 41 06 PM" src="https://github.com/user-attachments/assets/38e48930-9f32-401e-b870-e682e7e16957" />

Conversational analytics assistant for Rappi operational metrics.

The project uses n8n orchestration, DeepSeek `deepseek-v4-pro`, and model-generated read-only SQL so non-technical users can ask natural-language questions about operational KPIs, trends, comparisons, and exports.

## Current Assets

- `data/`: source workbook with dummy operational metrics.
- `docs/n8n-rappi-ops-copilot-design.md`: architecture and workflow design for the n8n chatbot.
- `frontend/`: Next.js embedded chat UI for the n8n Chat Trigger.
- `ops_copilot/`: analytics API, workbook loader, Postgres loader, and SQL execution guardrails.
- `workflows/`: n8n importable chat-agent and automatic insight-report workflows.
- `db/schema.sql`: Postgres semantic schema.
- `scripts/`: ingestion and smoke-test scripts.

## Local Quickstart

Create a local environment file:

```bash
cp .env.example .env
```

Start Postgres, the analytics API, n8n, and the Next.js web UI:

```bash
docker compose up --build
```

Open n8n:

```text
http://localhost:5678
```

Open the embedded chat UI:

```text
http://localhost:3000
```

Import:

```bash
python3 scripts/setup_n8n.py --activate
```

This imports or updates the n8n credentials and workflows from `.env` without
committing secrets. You can also import `workflows/rappi_ops_chat_agent.json`
and `workflows/rappi_ops_automatic_insights.json` manually and create the
credentials described in `workflows/README.md`.

The web UI embeds the workflow's public Chat Trigger through
`NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL`. The local default points to the committed
workflow webhook ID:

```text
http://localhost:5678/webhook/b2a0878f-58c7-4f89-a98b-2dc29cd637a8/chat
```

## Analytics API

Health check:

```bash
curl http://localhost:8000/health
```

Schema:

```bash
curl http://localhost:8000/schema
```

Generate or read the automatic executive insight report:

```bash
curl -X POST http://localhost:8000/insights/generate \
  -H 'Content-Type: application/json' \
  -d '{"source":"manual","persist":true}'

curl http://localhost:8000/insights/latest
curl http://localhost:8000/insights/latest.md
```

The n8n workflow `Rappi Ops Copilot - Automatic Insights Report` runs the same
generation endpoint on a Monday 07:00 `America/Bogota` schedule. The Next.js app
loads `/insights/latest` and links to the Markdown output.

Example model-facing SQL query endpoint:

```bash
curl -X POST http://localhost:8000/sql \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Compara Perfect Orders entre zonas Wealthy y Non Wealthy en México",
    "sql": "select z.zone_type, avg(f.value) as perfect_orders, count(distinct z.zone_id) as n_zones from fact_metric_week f join dim_zone z on z.zone_id = f.zone_id where f.metric_key = '\''perfect_orders'\'' and f.week_offset = 0 and z.country = '\''MX'\'' group by z.zone_type order by perfect_orders desc",
    "limit": 50,
    "visualization": "bar"
  }'
```

The response includes a `query_id`; export it with:

```bash
curl -OJ http://localhost:8000/exports/<query_id>.csv
curl -OJ http://localhost:8000/exports/<query_id>.pdf
```

## Data Ingestion

Dry-run workbook normalization:

```bash
python3 scripts/ingest_workbook.py --dry-run
```

Load Postgres:

```bash
DATABASE_URL=postgresql://rappi:rappi@localhost:5432/rappi_ops \
python3 scripts/ingest_workbook.py
```

The API currently reads the workbook directly for a zero-config demo. The Postgres schema and ingestion path are included so the data layer can be moved fully into Postgres as the workflow hardens.

## Validation

Run deterministic smoke tests against the workbook:

```bash
python3 scripts/smoke_test.py
```

This covers rankings, comparisons, trends, country aggregation, high/low segmentation, growth diagnostics, and problematic-zone scoring.
