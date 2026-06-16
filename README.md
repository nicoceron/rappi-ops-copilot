# Rappi Ops Copilot

Conversational analytics assistant for Rappi operational metrics.

The project uses n8n orchestration, DeepSeek `deepseek-v4-pro`, and model-generated read-only SQL so non-technical users can ask natural-language questions about operational KPIs, trends, comparisons, and exports.

## Current Assets

- `data/`: source workbook with dummy operational metrics.
- `docs/n8n-rappi-ops-copilot-design.md`: architecture and workflow design for the n8n chatbot.
- `ops_copilot/`: analytics API, workbook loader, Postgres loader, and SQL execution guardrails.
- `workflows/`: n8n importable chat-agent workflow template.
- `db/schema.sql`: Postgres semantic schema.
- `scripts/`: ingestion and smoke-test scripts.

## Local Quickstart

Create a local environment file:

```bash
cp .env.example .env
```

Start Postgres, the analytics API, and n8n:

```bash
docker compose up --build
```

Open n8n:

```text
http://localhost:5678
```

Import:

```bash
python3 scripts/setup_n8n.py --activate
```

This imports or updates the n8n credentials and workflow from `.env` without
committing secrets. You can also import `workflows/rappi_ops_chat_agent.json`
manually and create the credentials described in `workflows/README.md`.

## Analytics API

Health check:

```bash
curl http://localhost:8000/health
```

Schema:

```bash
curl http://localhost:8000/schema
```

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
