# Chatbot Capability Verification

| Field | Value |
|-------|-------|
| Date | 2026-06-16 |
| App URL | http://localhost:3000 |
| API URL | http://localhost:8000 |
| Scope | Tables, charts, CSV/PDF export, complex analytics questions, business context, proactive suggestions, and conversational memory |

## Current Result

Mostly working, but not complete from the chatbot surface.

| Capability | Result | Evidence |
|------------|--------|----------|
| Tables | Pass | Live chat renders structured HTML tables for aggregation and trend answers. |
| Charts | Pass in UI / partial in API | Live chat rendered a bar chart for Lead Penetration by country and a trend chart for Gross Profit UE. The `/sql` API still returned `visualization: null` when called with `"visualization": "bar"`. |
| CSV export | Partial | API export returned HTTP 200 and a 259-byte CSV. Chat request "Exporta este resultado en CSV y PDF" failed with no links. |
| PDF export | Partial | API export returned HTTP 200 and a 2416-byte PDF. Chat request "Exporta este resultado en CSV y PDF" failed with no links. |
| Filtering query | Pass in deterministic suite | `top lead penetration`: 5 rows. |
| Comparison query | Pass in deterministic suite | `wealthy comparison mx`: 2 rows. |
| Time-trend query | Pass in live chat and deterministic suite | Live query for Chapinero Gross Profit UE returned 8 weeks plus rendered trend chart in about 5 seconds. |
| Aggregation query | Pass in live chat and deterministic suite | Live country Lead Penetration query rendered table and chart; deterministic suite returned 9 rows. |
| Multivariable query | Pass in deterministic suite | `high lead low perfect`: 10 rows. |
| Inference/growth query | Pass in deterministic suite | `orders growth diagnostics`: 10 rows. |
| Business context | Pass in deterministic suite | `problem zones mx`: 10 rows, interpreting problematic zones as deteriorated metrics. |
| Proactive suggestions | Pass | Live answers included suggested follow-up analyses and export prompts. |
| Conversational memory | Pass in current live check | Follow-up "¿Y sin Ecuador?" reused the prior country aggregation context and answered in about 15 seconds. |

## Checks Run

- `docker compose ps`: all services up: `web`, `ops-api`, `n8n`, and `postgres`.
- `curl http://localhost:8000/health`: returned `{"status":"ok","version":"0.1.0"}`.
- `curl http://localhost:3000`: frontend responded.
- `docker compose exec -T ops-api python scripts/smoke_test.py`: passed all deterministic analytics checks.
- Live chat UI:
  - "¿Y sin Ecuador?" after a country Lead Penetration answer: passed memory, table, chart.
  - "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas": passed trend table and chart.
  - "Exporta este resultado en CSV y PDF": failed with `Agent stopped due to max iterations.` and no links.
- API export check:
  - Query ID: `3a1319ce-a9b6-4754-a586-699d8413b9d9`.
  - CSV: HTTP 200, 259 bytes.
  - PDF: HTTP 200, 2416 bytes.

## Blocking Gap

The main gap is chat-level export. The backend can export CSV/PDF, but the chatbot does not currently complete a conversational export request. For the stated requirement, this should be treated as partial rather than pass until the chat returns usable CSV/PDF links or attachments.

## Secondary Gap

The UI can render charts, but the API response does not return a visualization object/spec even when a visualization is requested. If downstream clients depend on API-generated chart metadata, that still needs implementation.
