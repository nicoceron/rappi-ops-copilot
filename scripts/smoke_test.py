#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops_copilot.data_loader import load_workbook
from ops_copilot.insights import generate_executive_insight_report
from ops_copilot.latex_report import render_query_result_latex
from ops_copilot.models import SemanticQuery
from ops_copilot.query_engine import QueryEngine
from ops_copilot.settings import default_data_file


EXPECTED_INSIGHT_CATEGORIES = {
    "anomalies",
    "worrying_trends",
    "benchmarking",
    "correlations",
    "opportunities",
}


def verify_insight_contract(report) -> dict[str, int]:
    category_map = {category.key: category for category in report.categories}
    category_counts = {
        key: len(category_map[key].findings)
        for key in sorted(category_map)
    }
    if set(category_map) != EXPECTED_INSIGHT_CATEGORIES:
        raise SystemExit(f"insights: unexpected categories {sorted(category_map)}")

    empty_categories = [
        key
        for key in EXPECTED_INSIGHT_CATEGORIES
        if not category_map[key].findings
    ]
    if empty_categories:
        raise SystemExit(f"insights: expected findings for categories {empty_categories}")

    summary_categories = {finding.category for finding in report.executive_summary}
    missing_summary_categories = EXPECTED_INSIGHT_CATEGORIES - summary_categories
    if missing_summary_categories:
        raise SystemExit(
            "insights: executive summary should surface every required category, "
            f"missing {sorted(missing_summary_categories)}"
        )

    for finding in category_map["anomalies"].findings:
        evidence = finding.evidence
        if abs(float(evidence.get("change_score", 0))) < 0.10:
            raise SystemExit("insights: anomaly below 10% week-over-week threshold")
        if evidence.get("previous_week") != "L1W" or evidence.get("current_week") != "L0W":
            raise SystemExit("insights: anomaly should compare L1W to L0W")

    for finding in category_map["worrying_trends"].findings:
        evidence = finding.evidence
        values = evidence.get("values", {})
        required_weeks = ["L3W", "L2W", "L1W", "L0W"]
        if not all(week in values for week in required_weeks):
            raise SystemExit("insights: trend missing 3-week deterioration history")
        ordered = [float(values[week]) for week in required_weeks]
        direction = evidence.get("direction")
        if direction == "higher_better" and not (ordered[0] > ordered[1] > ordered[2] > ordered[3]):
            raise SystemExit("insights: higher-is-better trend is not consistently deteriorating")
        if direction == "lower_better" and not (ordered[0] < ordered[1] < ordered[2] < ordered[3]):
            raise SystemExit("insights: lower-is-better trend is not consistently deteriorating")

    for finding in category_map["benchmarking"].findings:
        evidence = finding.evidence
        if int(evidence.get("peer_n", 0)) < 5:
            raise SystemExit("insights: benchmark should use a same-country/type peer group")
        if float(evidence.get("underperformance_score", 0)) < 0.15:
            raise SystemExit("insights: benchmark gap is below divergence threshold")
        if not evidence.get("country") or not evidence.get("zone_type"):
            raise SystemExit("insights: benchmark evidence must include country and zone type")

    correlations = category_map["correlations"].findings
    for finding in correlations:
        evidence = finding.evidence
        if int(evidence.get("n_zones", 0)) < 25:
            raise SystemExit("insights: correlation should be computed across enough zones")
        if "pearson_correlation" not in evidence:
            raise SystemExit("insights: correlation missing Pearson evidence")
        if int(evidence.get("low_low_count", 0)) <= 0:
            raise SystemExit("insights: correlation should include low-low zone count")
        if not evidence.get("low_low_examples"):
            raise SystemExit("insights: correlation should include low-low zone examples")

    has_lead_conversion_relationship = any(
        "Lead Penetration" in {
            finding.evidence.get("metric_x"),
            finding.evidence.get("metric_y"),
        }
        and any(
            token in str(finding.evidence.get(metric_name_key, ""))
            for metric_name_key in ["metric_x", "metric_y"]
            for token in ["CVR", "Conversion"]
        )
        for finding in correlations
    )
    if not has_lead_conversion_relationship:
        raise SystemExit("insights: expected Lead Penetration versus conversion correlation")

    for finding in category_map["opportunities"].findings:
        evidence = finding.evidence
        if float(evidence.get("opportunity_score", 0)) <= 0:
            raise SystemExit("insights: opportunity should include a positive score")
        if not evidence.get("weak_metrics"):
            raise SystemExit("insights: opportunity should include weakest metric cluster")

    for category in report.categories:
        if category.title not in report.markdown:
            raise SystemExit(f"insights: markdown missing section {category.title}")

    return category_counts


def main() -> None:
    engine = QueryEngine(load_workbook(default_data_file()))
    duplicate_metric_facts = engine.dataset.metric_facts.duplicated(
        ["zone_id", "metric_key", "week_offset"]
    ).sum()
    if duplicate_metric_facts:
        raise SystemExit(f"dataset: duplicate metric facts found: {duplicate_metric_facts}")
    quality = engine.dataset.data_quality
    if quality["metric_fact_duplicate_keys"] != 0:
        raise SystemExit("dataset: expected no duplicate metric fact keys after normalization")
    if quality["metric_duplicate_rows_removed"] < 1:
        raise SystemExit("dataset: expected duplicate metric source rows to be detected")
    if quality["outlier_cells_by_metric"].get("lead_penetration", 0) < 1:
        raise SystemExit("dataset: expected lead penetration outliers to be flagged")
    expected_city_aliases = {
        ("MX", "cdmx"): "Ciudad De Mexico",
        ("MX", "ciudad victoria"): "Cd. Victoria",
        ("MX", "cd guzman"): "Ciudad Guzman",
    }
    city_alias_lookup = {
        (row["country"], row["alias"]): row["city"]
        for row in engine.dataset.city_aliases.to_dict(orient="records")
    }
    for key, expected_city in expected_city_aliases.items():
        actual_city = city_alias_lookup.get(key)
        if actual_city != expected_city:
            raise SystemExit(
                f"dataset: city alias {key} expected {expected_city}, got {actual_city}"
            )

    cases = [
        (
            "top lead penetration",
            SemanticQuery(
                intent="rank",
                metrics=["Lead Penetration"],
                dimensions=["country", "city", "zone"],
                limit=5,
                visualization="bar",
            ),
        ),
        (
            "lead outlier flag mode",
            SemanticQuery(
                intent="rank",
                metrics=["Lead Penetration"],
                dimensions=["country", "city", "zone"],
                limit=1,
                visualization="bar",
                outlier_policy="flag",
            ),
        ),
        (
            "wealthy comparison mx",
            SemanticQuery(
                intent="compare",
                metrics=["Perfect Orders"],
                dimensions=["zone_type"],
                filters={"country": "Mexico"},
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "chapinero gp trend",
            SemanticQuery(
                intent="trend",
                metrics=["Gross Profit UE"],
                filters={"zone": "Chapinero"},
                period={"start_offset": 7, "end_offset": 0},
                aggregation="avg",
                visualization="line",
            ),
        ),
        (
            "lead avg country",
            SemanticQuery(
                intent="aggregate",
                metrics=["Lead Penetration"],
                dimensions=["country"],
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "n8n wrapped lead avg country",
            SemanticQuery(
                intent="aggregate",
                metrics={"values": ["Lead Penetration"]},
                dimensions={"values": ["country"]},
                sort={"values": []},
                diagnostic_metrics={"values": []},
                aggregation="avg",
                visualization="bar",
            ),
        ),
        (
            "high lead low perfect",
            SemanticQuery(
                intent="segment",
                metrics=["Lead Penetration", "Perfect Orders"],
                limit=10,
                visualization="scatter",
            ),
        ),
        (
            "orders growth diagnostics",
            SemanticQuery(
                intent="growth",
                metrics=["Orders"],
                period={"start_offset": 4, "end_offset": 0},
                include_diagnostics=True,
                diagnostic_metrics=["Lead Penetration", "Perfect Orders", "Gross Profit UE"],
                limit=10,
                visualization="bar",
            ),
        ),
        (
            "problem zones mx",
            SemanticQuery(
                intent="diagnose",
                metrics=[],
                filters={"country": "MX"},
                limit=10,
                visualization="bar",
            ),
        ),
        (
            "cdmx alias trend",
            SemanticQuery(
                intent="trend",
                metrics=["Perfect Orders"],
                dimensions=["city", "zone_type"],
                filters={"country": "MX", "city": ["CDMX", "Monterrey", "Guadalajara"]},
                period={"start_offset": 7, "end_offset": 0},
                aggregation="avg",
                limit=60,
                visualization="line",
            ),
        ),
        (
            "generated cd alias city filter",
            SemanticQuery(
                intent="trend",
                metrics=["Perfect Orders"],
                dimensions=["city"],
                filters={"country": "MX", "city": "cd guzman"},
                period={"start_offset": 7, "end_offset": 0},
                aggregation="avg",
                limit=8,
                visualization="line",
            ),
        ),
    ]

    for name, query in cases:
        result = engine.execute(query)
        if result.row_count < 1:
            raise SystemExit(f"{name}: expected at least one row")
        if name == "top lead penetration":
            if any(float(row["value"]) > 1 for row in result.rows):
                raise SystemExit("top lead penetration: default outlier policy should exclude values > 1")
        if name == "lead outlier flag mode":
            if not result.rows[0].get("is_outlier") or float(result.rows[0]["value"]) <= 1:
                raise SystemExit("lead outlier flag mode: expected flagged outlier row")
        if name == "cdmx alias trend":
            cities = {row["city"] for row in result.rows}
            if "Ciudad De Mexico" not in cities:
                raise SystemExit("cdmx alias trend: expected Ciudad De Mexico rows")
            if result.row_count != 48:
                raise SystemExit(f"cdmx alias trend: expected 48 rows, got {result.row_count}")
        if name == "generated cd alias city filter":
            cities = {row["city"] for row in result.rows}
            if cities != {"Ciudad Guzman"}:
                raise SystemExit(f"generated cd alias city filter: unexpected cities {cities}")
        if name == "wealthy comparison mx":
            latex = render_query_result_latex(result)
            if "\\documentclass" not in latex or "Rappi Ops Query Export" not in latex:
                raise SystemExit("query export: expected standalone LaTeX report")
        print(f"ok {name}: {result.row_count} rows ({result.answer_type})")

    report = generate_executive_insight_report(engine.dataset, source="smoke_test")
    category_counts = verify_insight_contract(report)
    if not report.executive_summary:
        raise SystemExit("insights: expected executive summary findings")
    if "# Rappi Ops Executive Insight Report" not in report.markdown:
        raise SystemExit("insights: expected markdown output")
    if report.data_quality.get("metric_fact_duplicate_keys") != 0:
        raise SystemExit("insights: report did not use duplicate-free cleaned metric facts")
    if report.data_quality.get("order_fact_duplicate_keys") != 0:
        raise SystemExit("insights: report did not use duplicate-free cleaned order facts")
    if report.data_quality.get("insight_outlier_exclusion_applied") is not True:
        raise SystemExit("insights: expected outlier exclusion marker on report")
    print(f"ok automatic insights: {category_counts}")


if __name__ == "__main__":
    main()
