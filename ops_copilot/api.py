from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ops_copilot import __version__
from ops_copilot.data_loader import load_workbook
from ops_copilot.models import QueryResult, SemanticQuery
from ops_copilot.query_engine import QueryEngine, QueryValidationError
from ops_copilot.settings import default_data_file

app = FastAPI(
    title="Rappi Ops Copilot API",
    version=__version__,
    description="Deterministic analytics API used by the n8n Rappi Ops Copilot workflow.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ENGINE: QueryEngine | None = None
_RESULT_CACHE: dict[str, QueryResult] = {}


class SchemaRequest(BaseModel):
    include_examples: bool = True
    language: str = "es"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/schema")
def schema_get(include_examples: bool = True) -> dict[str, Any]:
    return _engine().schema(include_examples=include_examples)


@app.post("/schema")
def schema_post(request: SchemaRequest) -> dict[str, Any]:
    return _engine().schema(include_examples=request.include_examples)


@app.post("/query", response_model=QueryResult)
def query(request: SemanticQuery) -> QueryResult:
    try:
        result = _engine().execute(request)
    except QueryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _RESULT_CACHE[result.query_id] = result
    return result


@app.get("/exports/{query_id}.csv")
def export_csv(query_id: str) -> Response:
    result = _cached_result(query_id)
    frame = pd.DataFrame(result.rows)
    csv_text = frame.to_csv(index=False)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{query_id}.csv"'},
    )


@app.get("/exports/{query_id}.pdf")
def export_pdf(query_id: str) -> Response:
    result = _cached_result(query_id)
    payload = _build_pdf(result)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{query_id}.pdf"'},
    )


def _engine() -> QueryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = QueryEngine(load_workbook(default_data_file()))
    return _ENGINE


def _cached_result(query_id: str) -> QueryResult:
    result = _RESULT_CACHE.get(query_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown query_id. Export is available only for results produced since API startup.",
        )
    return result


def _build_pdf(result: QueryResult) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="Rappi Ops Copilot Result")
    styles = getSampleStyleSheet()
    story: list[Any] = [
        Paragraph("Rappi Ops Copilot Result", styles["Title"]),
        Paragraph(f"Query ID: {result.query_id}", styles["Normal"]),
        Paragraph(f"Answer type: {result.answer_type}", styles["Normal"]),
        Paragraph(f"Period: {result.period_label}", styles["Normal"]),
        Spacer(1, 12),
    ]

    if result.caveats:
        story.append(Paragraph("Caveats", styles["Heading2"]))
        for caveat in result.caveats:
            story.append(Paragraph(f"- {caveat}", styles["Normal"]))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Rows", styles["Heading2"]))
    rows = result.rows[:40]
    if not rows:
        story.append(Paragraph("No rows returned.", styles["Normal"]))
    else:
        columns = list(rows[0].keys())[:8]
        table_data = [columns]
        for row in rows:
            table_data.append([_pdf_cell(row.get(column)) for column in columns])
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


def _pdf_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)[:80]
