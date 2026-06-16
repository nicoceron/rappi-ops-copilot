# Rappi Ops Copilot

Conversational analytics assistant for Rappi operational metrics.

The project uses n8n orchestration, DeepSeek `deepseek-v4-pro`, and a deterministic data-query layer so non-technical users can ask natural-language questions about operational KPIs, trends, comparisons, and exports.

## Current Assets

- `data/`: source workbook with dummy operational metrics.
- `docs/n8n-rappi-ops-copilot-design.md`: architecture and workflow design for the n8n chatbot.

## Planned Implementation

1. Normalize workbook data into Postgres semantic tables.
2. Build n8n ingestion and chat workflows.
3. Add deterministic query tools for rankings, comparisons, trends, diagnostics, and exports.
4. Add chart and CSV/PDF export support.
