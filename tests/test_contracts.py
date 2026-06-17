from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from ops_copilot.api import _clean_read_only_sql
from ops_copilot.data_loader import load_workbook
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
