from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ops_copilot.api import _clean_read_only_sql
from ops_copilot.charting import build_chart_spec
from ops_copilot.data_loader import load_workbook
from ops_copilot.latex_report import render_query_result_latex
from ops_copilot.models import SemanticQuery
from ops_copilot.query_engine import QueryEngine
from ops_copilot.settings import default_data_file


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def engine() -> QueryEngine:
    return QueryEngine(load_workbook(default_data_file()))


def _workflow(name: str) -> dict:
    return json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8"))


def test_workbook_normalization_removes_duplicates_and_keeps_aliases(engine: QueryEngine) -> None:
    duplicate_facts = engine.dataset.metric_facts.duplicated(
        ["zone_id", "metric_key", "week_offset"]
    ).sum()
    assert duplicate_facts == 0
    assert engine.dataset.data_quality["metric_fact_duplicate_keys"] == 0
    assert engine.dataset.data_quality["metric_duplicate_rows_removed"] >= 1
    assert engine.dataset.data_quality["outlier_cells_by_metric"]["lead_penetration"] >= 1

    aliases = {
        (row["country"], row["alias"]): row["city"]
        for row in engine.dataset.city_aliases.to_dict(orient="records")
    }
    assert aliases[("MX", "cdmx")] == "Ciudad De Mexico"
    assert aliases[("MX", "cd guzman")] == "Ciudad Guzman"


def test_semantic_query_accepts_n8n_wrapped_lists(engine: QueryEngine) -> None:
    query = SemanticQuery(
        intent="aggregate",
        metrics={"values": ["Lead Penetration"]},
        dimensions={"values": ["country"]},
        sort={"values": []},
        diagnostic_metrics={"values": []},
        aggregation="avg",
        visualization="bar",
    )

    result = engine.execute(query)

    assert result.answer_type == "aggregation"
    assert result.chart.type == "bar"
    assert result.row_count >= 1
    assert {"metric", "country", "value", "n_zones"}.issubset(result.rows[0])


def test_default_outlier_policy_excludes_invalid_lead_penetration(engine: QueryEngine) -> None:
    result = engine.execute(
        SemanticQuery(
            intent="rank",
            metrics=["Lead Penetration"],
            dimensions=["country", "city", "zone"],
            limit=5,
            visualization="bar",
        )
    )

    assert result.answer_type == "ranking"
    assert result.chart.type == "bar"
    assert result.rows
    assert all(float(row["value"]) <= 1 for row in result.rows)


def test_chart_spec_uses_count_column_when_it_is_the_only_measure() -> None:
    rows = [
        {"country": "MX", "zones": 331},
        {"country": "CO", "zones": 135},
        {"country": "AR", "zones": 98},
    ]

    chart = build_chart_spec(rows, "bar", columns=["country", "zones"])

    assert chart.type == "bar"
    assert chart.xKey == "country"
    assert chart.yKeys == ["zones"]


def test_read_only_sql_guardrails() -> None:
    assert _clean_read_only_sql(" select 1; ") == "select 1"
    assert _clean_read_only_sql("WITH rows AS (select 1) select * from rows") == (
        "WITH rows AS (select 1) select * from rows"
    )

    blocked_sql = [
        "",
        "update fact_metric_week set value = 0",
        "select 1; select 2",
        "select * from dim_zone -- comment",
        "select * from dim_zone /* comment */",
        "delete from dim_zone",
    ]
    for sql in blocked_sql:
        with pytest.raises(HTTPException):
            _clean_read_only_sql(sql)


def test_latex_export_falls_back_to_chart_for_chartable_table_results() -> None:
    rows = [
        {"zone": "TLX CHIAUTEMPAN", "city": "Tlaxcala", "country": "MX", "lead_penetration": 0.9326},
        {"zone": "GUA_SUR", "city": "Guanajuato", "country": "MX", "lead_penetration": 0.9220},
        {"zone": "ZAC Tres Cruces", "city": "Zacatecas", "country": "MX", "lead_penetration": 0.8079},
        {"zone": "Gonnet", "city": "La Plata", "country": "AR", "lead_penetration": 0.7912},
        {"zone": "Pinares Sur", "city": "Pereira", "country": "CO", "lead_penetration": 0.6954},
    ]
    result = SimpleNamespace(
        query_id="latex-chart-fallback",
        answer_type="model_sql",
        question="Top 5 Lead Penetration",
        sql="select ...",
        columns=list(rows[0]),
        rows=rows,
        row_count=len(rows),
        truncated=False,
        visualization_hint="table",
        chart=SimpleNamespace(recommended=False, type="table"),
        caveats=[],
        suggested_followups=[],
    )

    latex = render_query_result_latex(result)

    assert "\\section*{Chart}" in latex
    assert "\\begin{figure}" in latex
    assert "Bar chart" in latex


@pytest.mark.parametrize(
    ("chart", "expected_caption"),
    [
        (
            {
                "type": "bar",
                "title": "Chat Bar",
                "xKey": "zone",
                "yKeys": ["lead_penetration"],
                "data": [
                    {"zone": "TLX CHIAUTEMPAN", "lead_penetration": 0.9326},
                    {"zone": "GUA_SUR", "lead_penetration": 0.9220},
                    {"zone": "ZAC Tres Cruces", "lead_penetration": 0.8079},
                ],
            },
            "Chat Bar",
        ),
        (
            {
                "type": "line",
                "title": "Chat Line",
                "xKey": "week_label",
                "yKeys": ["orders"],
                "data": [
                    {"week_label": "L2W", "orders": 120},
                    {"week_label": "L1W", "orders": 135},
                    {"week_label": "L0W", "orders": 150},
                ],
            },
            "Chat Line",
        ),
        (
            {
                "type": "scatter",
                "title": "Chat Scatter",
                "xKey": "lead_penetration",
                "yKeys": ["perfect_orders"],
                "data": [
                    {"zone": "A", "lead_penetration": 0.91, "perfect_orders": 0.88},
                    {"zone": "B", "lead_penetration": 0.74, "perfect_orders": 0.81},
                    {"zone": "C", "lead_penetration": 0.86, "perfect_orders": 0.67},
                ],
            },
            "Chat Scatter",
        ),
        (
            {
                "type": "area",
                "title": "Chat Area",
                "xKey": "week_label",
                "yKeys": ["orders"],
                "data": [
                    {"week_label": "L2W", "orders": 120},
                    {"week_label": "L1W", "orders": 135},
                    {"week_label": "L0W", "orders": 150},
                ],
            },
            "Chat Area",
        ),
        (
            {
                "type": "donut",
                "title": "Chat Donut",
                "labels": ["MX", "AR", "CO"],
                "values": [3, 1, 1],
            },
            "Chat Donut",
        ),
        (
            {
                "type": "pie",
                "title": "ChartJS Pie",
                "data": {
                    "labels": ["MX", "AR", "CO"],
                    "datasets": [{"label": "zones", "data": [3, 1, 1]}],
                },
            },
            "ChartJS Pie",
        ),
        (
            {
                "type": "histogram",
                "title": "Chat Histogram",
                "values": [0.51, 0.55, 0.58, 0.64, 0.72, 0.79, 0.81, 0.91],
            },
            "Chat Histogram",
        ),
        (
            {
                "type": "bubble",
                "title": "Chat Bubble",
                "points": [
                    {"x": 0.91, "y": 0.88, "size": 22},
                    {"x": 0.74, "y": 0.81, "size": 14},
                    {"x": 0.86, "y": 0.67, "size": 18},
                ],
                "zKey": "size",
            },
            "Chat Bubble",
        ),
        (
            {
                "type": "combo",
                "title": "Chat Combo",
                "labels": ["L2W", "L1W", "L0W"],
                "datasets": [
                    {"label": "orders", "data": [120, 135, 150]},
                    {"label": "lead_penetration", "data": [0.71, 0.75, 0.79]},
                ],
            },
            "Chat Combo",
        ),
        (
            {
                "type": "stacked_bar",
                "title": "Chat Stacked",
                "xKey": "country",
                "yKeys": ["wealthy", "non_wealthy"],
                "data": [
                    {"country": "MX", "wealthy": 7, "non_wealthy": 11},
                    {"country": "AR", "wealthy": 3, "non_wealthy": 5},
                    {"country": "CO", "wealthy": 4, "non_wealthy": 6},
                ],
            },
            "Chat Stacked",
        ),
    ],
)
def test_latex_export_renders_chat_chart_payloads(
    chart: dict[str, object],
    expected_caption: str,
) -> None:
    rows = chart.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        rows = [
            {"label": "MX", "value": 3},
            {"label": "AR", "value": 1},
            {"label": "CO", "value": 1},
        ]
    result = SimpleNamespace(
        query_id=f"latex-{chart['type']}-payload",
        answer_type="model_sql",
        question="Chart payload",
        sql="select ...",
        columns=list(rows[0]),
        rows=rows,
        row_count=len(rows),
        truncated=False,
        visualization_hint="table",
        chart=chart,
        caveats=[],
        suggested_followups=[],
    )

    latex = render_query_result_latex(result)

    assert "\\section*{Chart}" in latex
    assert "\\begin{figure}" in latex
    assert expected_caption in latex


def test_chat_workflow_uses_deepseek_v4_pro_and_required_api_tools() -> None:
    workflow = _workflow("rappi_ops_chat_agent.json")
    nodes = workflow["nodes"]

    model_nodes = [
        node
        for node in nodes
        if node["type"] == "@n8n/n8n-nodes-langchain.lmChatDeepSeek"
    ]
    assert len(model_nodes) == 1
    assert model_nodes[0]["parameters"]["model"] == "=deepseek-v4-pro"

    tool_urls = {
        node["parameters"].get("url")
        for node in nodes
        if node["type"] == "@n8n/n8n-nodes-langchain.toolHttpRequest"
    }
    assert "http://ops-api:8000/schema" in tool_urls
    assert "http://ops-api:8000/sql" in tool_urls
    assert "http://ops-api:8000/exports/{query_id}/links?format={format}" in tool_urls


def test_automatic_insights_workflow_generates_llm_report_and_fetches_pdf() -> None:
    workflow = _workflow("rappi_ops_automatic_insights.json")
    nodes = workflow["nodes"]

    request_bodies = [
        node["parameters"].get("jsonBody", "")
        for node in nodes
        if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert any('"authoring_mode": "llm"' in body for body in request_bodies)
    assert any(
        node["parameters"].get("url") == "http://ops-api:8000/insights/latest.pdf"
        for node in nodes
    )
    assert any(
        node["parameters"].get("rule", {})
        .get("interval", [{}])[0]
        .get("expression")
        == "0 7 * * 1"
        for node in nodes
    )
