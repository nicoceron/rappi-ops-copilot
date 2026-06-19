from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, cast

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ops_copilot import __version__
from ops_copilot.charting import build_chart_spec
from ops_copilot.data_loader import load_workbook
from ops_copilot.insights import (
    InsightReport,
    generate_executive_insight_report,
    render_report_html,
    render_report_markdown,
)
from ops_copilot.latex_report import (
    LatexBuildError,
    compile_latex_pdf_with_repair,
    latex_repair_context,
    query_result_latex_context,
    render_query_result_latex,
    render_report_latex,
)
from ops_copilot.models import ChartSpec, ExportDownload, ExportFormat, QueryResult, SemanticQuery
from ops_copilot.postgres_loader import ensure_postgres_loaded
from ops_copilot.query_engine import QueryEngine, QueryValidationError
from ops_copilot.report_authoring import (
    ReportAuthoringError,
    ReportAuthoringMode,
    author_report_with_deepseek,
)
from ops_copilot.settings import default_data_file, export_dir, public_api_base_url

app = FastAPI(
    title="Rappi Ops Copilot API",
    version=__version__,
    description="Analytics API used by the n8n Rappi Ops Copilot workflow.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ENGINE: QueryEngine | None = None
_RESULT_CACHE: dict[str, QueryResult | "SqlQueryResult"] = {}
_INSIGHT_REPORT_CACHE: InsightReport | None = None
_WRITE_SQL_RE = re.compile(
    r"\b(alter|analyze|call|comment|copy|create|delete|do|drop|execute|grant|insert|"
    r"merge|refresh|reindex|revoke|truncate|update|vacuum)\b",
    re.IGNORECASE,
)


class SchemaRequest(BaseModel):
    include_examples: bool = True
    language: str = "es"


class SqlQueryRequest(BaseModel):
    question: str = ""
    sql: str
    limit: int = Field(default=200, ge=1, le=1000)
    visualization: str = "auto"


class SqlQueryResult(BaseModel):
    query_id: str
    question: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    visualization_hint: str
    chart: ChartSpec
    caveats: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    exports: list[ExportDownload] = Field(default_factory=list)


class ExportLinksResponse(BaseModel):
    query_id: str
    exports: list[ExportDownload]


class GenerateInsightsRequest(BaseModel):
    source: str = "api"
    persist: bool = True
    authoring_mode: ReportAuthoringMode = "auto"


@app.on_event("startup")
def startup_load_postgres() -> None:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        ensure_postgres_loaded(database_url, default_data_file())


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

    result.exports = _export_downloads(result.query_id)
    _RESULT_CACHE[result.query_id] = result
    return result


@app.post("/sql", response_model=SqlQueryResult)
def run_sql(request: SqlQueryRequest) -> SqlQueryResult:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured.")

    sql = _clean_read_only_sql(request.sql)
    wrapped_sql = f"select * from ({sql}) as model_query limit %s"

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="psycopg is not installed.") from exc

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute("set local statement_timeout = '20s'")
                cur.execute(wrapped_sql, (request.limit + 1,))
                fetched = cur.fetchall()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"SQL execution failed: {exc}") from exc

    rows = [jsonable_encoder(dict(row)) for row in fetched[: request.limit]]
    truncated = len(fetched) > request.limit
    columns = list(rows[0].keys()) if rows else []
    chart = build_chart_spec(rows, request.visualization, columns=columns)
    result = SqlQueryResult(
        query_id=str(uuid.uuid4()),
        question=request.question,
        sql=sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        visualization_hint=chart.type,
        chart=chart,
        caveats=[
            "SQL was generated by the model and executed read-only against Postgres.",
            "L0W is the most recent available week, not a calendar date.",
            "fact_metric_week.is_outlier marks source outliers; normal analytical SQL should exclude those rows unless inspecting outliers.",
        ],
        suggested_followups=[
            "Ask for the same analysis by city or zone.",
            "Ask for a trend over the last 8 weeks.",
            "Ask to export this result to CSV or PDF.",
        ],
    )
    result.exports = _export_downloads(result.query_id)
    _RESULT_CACHE[result.query_id] = result
    return result


@app.post("/insights/generate", response_model=InsightReport)
def generate_insights(request: GenerateInsightsRequest) -> InsightReport:
    return _generate_and_store_insights(
        source=request.source,
        persist=request.persist,
        authoring_mode=request.authoring_mode,
    )


@app.post("/insights/workflow/run", response_model=InsightReport)
def run_insights_workflow() -> InsightReport:
    _trigger_insights_workflow()
    report = _load_latest_insight_report()
    if report:
        return report
    if _INSIGHT_REPORT_CACHE:
        return _INSIGHT_REPORT_CACHE
    raise HTTPException(
        status_code=502,
        detail="The n8n insights workflow completed but no report was stored.",
    )


@app.get("/insights/latest", response_model=InsightReport)
def latest_insights() -> InsightReport:
    report = _load_latest_insight_report()
    if report:
        return report
    if _INSIGHT_REPORT_CACHE:
        return _INSIGHT_REPORT_CACHE
    return _generate_and_store_insights(
        source="api_on_demand",
        persist=True,
        authoring_mode="auto",
    )


@app.get("/insights/latest.md")
def latest_insights_markdown() -> Response:
    report = latest_insights()
    return Response(
        content=report.markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'inline; filename="{report.report_id}-executive-insights.md"'
        },
    )


@app.get("/insights/latest.html")
def latest_insights_html() -> Response:
    report = latest_insights()
    return Response(
        content=render_report_html(report),
        media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="{report.report_id}-executive-insights.html"'
        },
    )


@app.get("/insights/latest.tex")
def latest_insights_latex() -> Response:
    report = latest_insights()
    return Response(
        content=render_report_latex(report),
        media_type="application/x-tex",
        headers={
            "Content-Disposition": f'inline; filename="{report.report_id}-executive-insights.tex"'
        },
    )


@app.get("/insights/latest.pdf")
def latest_insights_pdf() -> Response:
    report = latest_insights()
    directory = export_dir() / "reports"
    pdf_path = directory / "latest-executive-insights.pdf"
    tex_source = render_report_latex(report)
    try:
        result = compile_latex_pdf_with_repair(
            tex_source,
            pdf_path,
            context=latex_repair_context(report),
        )
    except LatexBuildError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    (directory / "latest-executive-insights.tex").write_text(
        result.tex_source,
        encoding="utf-8",
    )
    _write_latex_repair_log(directory, result.repair_notes)
    _clear_latex_error(directory)

    return Response(
        content=result.pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{report.report_id}-executive-insights.pdf"'
            )
        },
    )


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
    directory = export_dir() / "query-exports"
    pdf_path = directory / f"{query_id}.pdf"
    tex_source = render_query_result_latex(result)
    try:
        compiled = compile_latex_pdf_with_repair(
            tex_source,
            pdf_path,
            context=query_result_latex_context(result),
        )
    except LatexBuildError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    (directory / f"{query_id}.tex").write_text(compiled.tex_source, encoding="utf-8")
    _write_query_export_latex_repair_log(directory, query_id, compiled.repair_notes)
    return Response(
        content=compiled.pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{query_id}.pdf"'},
    )


@app.get("/exports/{query_id}/links", response_model=ExportLinksResponse)
def export_links(query_id: str, format: str = "both") -> ExportLinksResponse:
    _cached_result(query_id)
    formats = _parse_export_formats(format)
    return ExportLinksResponse(query_id=query_id, exports=_export_downloads(query_id, formats))


def _engine() -> QueryEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = QueryEngine(load_workbook(default_data_file()))
    return _ENGINE


def _cached_result(query_id: str) -> QueryResult | SqlQueryResult:
    result = _RESULT_CACHE.get(query_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown query_id. Export is available only for results produced since API startup.",
        )
    return result


def _parse_export_formats(value: str) -> list[ExportFormat]:
    requested = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not requested or requested in (["all"], ["both"]):
        return ["csv", "pdf"]

    formats: list[ExportFormat] = []
    for item in requested:
        if item not in {"csv", "pdf"}:
            raise HTTPException(
                status_code=422,
                detail="Unsupported export format. Use csv, pdf, both, or a comma-separated list.",
            )
        formats.append(cast(ExportFormat, item))

    return formats


def _normalize_visualization_hint(value: str) -> str:
    text = re.sub(r"[\s-]+", "_", value.strip().lower())
    if text in {"none", "table", "bar", "line", "scatter"}:
        return text
    if text in {
        "bar_chart",
        "column",
        "columns",
        "column_chart",
        "grouped_bar",
        "stacked_bar",
        "horizontal_bar",
        "pie",
        "pie_chart",
        "donut",
        "doughnut",
        "donut_chart",
        "doughnut_chart",
        "histogram",
        "histograma",
        "distribution",
        "combo",
        "combined",
        "composed",
        "mixed",
        "dual_axis",
    }:
        return "bar"
    if text in {"line_chart", "trend", "timeseries", "time_series", "area", "area_chart", "stacked_area"}:
        return "line"
    if text in {"scatterplot", "scatter_plot", "bubble", "bubble_chart"}:
        return "scatter"
    return "table"


def _resolve_visualization_hint(value: str, rows: list[dict[str, Any]], columns: list[str]) -> str:
    hint = _normalize_visualization_hint(value)
    if hint in {"none", "table"}:
        return hint
    if not rows or not columns:
        return "table"
    if _is_small_segment_comparison(rows, columns):
        return "bar"
    if hint == "line":
        return "line" if _has_time_column(columns) and _plottable_numeric_columns(rows, columns) else "table"
    if hint == "scatter":
        if _has_scatter_shape(rows, columns):
            return "scatter"
        return "bar" if _has_bar_shape(rows, columns) else "table"
    if hint == "bar":
        return "bar" if _has_bar_shape(rows, columns) else "table"
    return "table"


def _has_time_column(columns: list[str]) -> bool:
    return any(re.search(r"week|semana|date|fecha", column, re.IGNORECASE) for column in columns)


def _has_bar_shape(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    return _preferred_category_column(rows, columns) is not None and bool(_plottable_numeric_columns(rows, columns))


def _has_scatter_shape(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    numeric = _numeric_columns(rows, columns)
    primary = [column for column in numeric if not _is_count_column(column) and not _is_minmax_column(column)]
    count_like = [column for column in numeric if _is_count_column(column)]
    return len(primary) >= 2 or (len(rows) > 2 and bool(primary) and bool(count_like))


def _is_small_segment_comparison(rows: list[dict[str, Any]], columns: list[str]) -> bool:
    return len(rows) <= 6 and any(
        re.search(r"zone_type|segment|tipo|wealthy", column, re.IGNORECASE)
        for column in columns
    )


def _preferred_category_column(rows: list[dict[str, Any]], columns: list[str]) -> str | None:
    numeric = set(_numeric_columns(rows, columns))
    for pattern in ["country", "city", "zone_type", "zone", "metric", "segment", "type", "label"]:
        for column in columns:
            if column not in numeric and pattern in column.lower():
                return column
    return next((column for column in columns if column not in numeric), None)


def _primary_numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    return [
        column
        for column in _numeric_columns(rows, columns)
        if not _is_count_column(column) and not _is_minmax_column(column)
    ]


def _plottable_numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    primary = _primary_numeric_columns(rows, columns)
    if primary:
        return primary
    return [
        column
        for column in _numeric_columns(rows, columns)
        if not _is_minmax_column(column)
    ]


def _numeric_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[str]:
    numeric = []
    for column in columns:
        values = [
            _to_float(row.get(column))
            for row in rows
            if row.get(column) is not None
        ]
        values = [value for value in values if value is not None]
        if values and len(values) >= max(1, min(3, len(rows) // 4)):
            numeric.append(column)
    return numeric


def _is_count_column(column: str) -> bool:
    lowered = column.lower()
    return (
        lowered in {"n", "count", "zones", "zonas", "n_zones", "n_zonas", "orders", "start_orders", "end_orders"}
        or lowered.startswith(("n_", "num_"))
        or lowered.endswith(("_count", "_orders"))
        or "count" in lowered
    )


def _is_minmax_column(column: str) -> bool:
    lowered = column.lower()
    return lowered.startswith(("min", "max")) or lowered.endswith(("_min", "_max"))


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _export_downloads(
    query_id: str,
    formats: list[ExportFormat] | None = None,
) -> list[ExportDownload]:
    selected = formats or ["csv", "pdf"]
    content_types = {
        "csv": "text/csv",
        "pdf": "application/pdf",
    }
    labels = {
        "csv": "CSV",
        "pdf": "PDF",
    }
    base_url = public_api_base_url()

    return [
        ExportDownload(
            format=format_name,
            label=labels[format_name],
            href=f"{base_url}/exports/{query_id}.{format_name}",
            browser_url=f"{base_url}/exports/{query_id}.{format_name}",
            api_path=f"/exports/{query_id}.{format_name}",
            content_type=content_types[format_name],
        )
        for format_name in selected
    ]


def _generate_and_store_insights(
    source: str, persist: bool, authoring_mode: ReportAuthoringMode = "auto"
) -> InsightReport:
    global _INSIGHT_REPORT_CACHE
    report = generate_executive_insight_report(_engine().dataset, source=source)
    report = _apply_report_authoring(report, authoring_mode)
    _INSIGHT_REPORT_CACHE = report
    _write_insight_report_files(report)
    if persist:
        _store_insight_report(report)
    return report


def _trigger_insights_workflow() -> None:
    webhook_url = os.getenv(
        "N8N_INSIGHTS_WEBHOOK_URL",
        "http://localhost:5678/webhook/rappi-ops-executive-insights/run",
    )
    payload = json.dumps({"source": "web_reload"}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise HTTPException(
            status_code=502,
            detail=f"n8n insights workflow failed with HTTP {exc.code}: {detail or exc.reason}",
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not trigger n8n insights workflow at {webhook_url}: {exc}",
        ) from exc


def _apply_report_authoring(
    report: InsightReport, authoring_mode: ReportAuthoringMode
) -> InsightReport:
    if authoring_mode == "deterministic":
        return report
    if authoring_mode == "auto" and not os.getenv("DEEPSEEK_API_KEY"):
        return report

    try:
        report.authored_report = author_report_with_deepseek(report)
        report.markdown = render_report_markdown(report)
    except ReportAuthoringError as exc:
        if authoring_mode == "llm":
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        report.data_caveats.append(
            "LLM narrative authoring failed; deterministic report text was used."
        )
        report.markdown = render_report_markdown(report)
    return report


def _store_insight_report(report: InsightReport) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError:
        return

    payload = report.model_dump(mode="json")
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into executive_insight_report (
                      report_id, source, period_label, report_markdown, report_json
                    )
                    values (%s, %s, %s, %s, %s::jsonb)
                    on conflict (report_id) do update set
                      source = excluded.source,
                      period_label = excluded.period_label,
                      report_markdown = excluded.report_markdown,
                      report_json = excluded.report_json
                    """,
                    (
                        report.report_id,
                        report.source,
                        report.period_label,
                        report.markdown,
                        Jsonb(jsonable_encoder(payload)),
                    ),
                )
            conn.commit()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not store insight report: {exc}") from exc


def _load_latest_insight_report() -> InsightReport | None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        return None

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select report_json
                    from executive_insight_report
                    order by created_at desc
                    limit 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        return None
    if not row:
        return None
    return InsightReport.model_validate(row["report_json"])


def _write_insight_report_files(report: InsightReport) -> None:
    directory = export_dir() / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    tex_source = render_report_latex(report)
    (directory / "latest-executive-insights.md").write_text(report.markdown, encoding="utf-8")
    (directory / "latest-executive-insights.html").write_text(
        render_report_html(report),
        encoding="utf-8",
    )
    (directory / "latest-executive-insights.tex").write_text(tex_source, encoding="utf-8")
    (directory / "latest-executive-insights.json").write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    try:
        result = compile_latex_pdf_with_repair(
            tex_source,
            directory / "latest-executive-insights.pdf",
            context=latex_repair_context(report),
        )
        (directory / "latest-executive-insights.tex").write_text(
            result.tex_source,
            encoding="utf-8",
        )
        _write_latex_repair_log(directory, result.repair_notes)
        _clear_latex_error(directory)
    except LatexBuildError as exc:
        (directory / "latest-executive-insights-pdf-error.txt").write_text(
            str(exc),
            encoding="utf-8",
        )


def _clean_read_only_sql(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="SQL is required.")
    cleaned = cleaned.rstrip(";").strip()
    if ";" in cleaned:
        raise HTTPException(status_code=422, detail="Only one SQL statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise HTTPException(status_code=422, detail="Only SELECT or WITH queries are allowed.")
    if _WRITE_SQL_RE.search(cleaned):
        raise HTTPException(status_code=422, detail="Write or administrative SQL is not allowed.")
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise HTTPException(status_code=422, detail="SQL comments are not allowed.")
    return cleaned


def _write_latex_repair_log(directory: Path, repair_notes: list[str]) -> None:
    log_path = directory / "latest-executive-insights-latex-repairs.txt"
    if repair_notes:
        log_path.write_text("\n\n".join(repair_notes), encoding="utf-8")
    elif log_path.exists():
        log_path.unlink()


def _clear_latex_error(directory: Path) -> None:
    error_path = directory / "latest-executive-insights-pdf-error.txt"
    if error_path.exists():
        error_path.unlink()


def _write_query_export_latex_repair_log(
    directory: Path,
    query_id: str,
    repair_notes: list[str],
) -> None:
    log_path = directory / f"{query_id}-latex-repairs.txt"
    if repair_notes:
        log_path.write_text("\n\n".join(repair_notes), encoding="utf-8")
    elif log_path.exists():
        log_path.unlink()
