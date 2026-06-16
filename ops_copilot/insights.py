from __future__ import annotations

import json
import math
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from html import escape
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from ops_copilot.data_loader import OperationalDataset


InsightCategoryKey = Literal[
    "anomalies",
    "worrying_trends",
    "benchmarking",
    "correlations",
    "opportunities",
]
Severity = Literal["critical", "high", "medium", "low"]


CATEGORY_TITLES: dict[InsightCategoryKey, str] = {
    "anomalies": "Anomalies",
    "worrying_trends": "Worrying trends",
    "benchmarking": "Benchmarking",
    "correlations": "Correlations",
    "opportunities": "General opportunities",
}

SEVERITY_RANK: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

CORRELATION_PAIRS = [
    ("lead_penetration", "perfect_orders"),
    ("lead_penetration", "restaurants_ss_to_atc_cvr"),
    ("lead_penetration", "restaurants_sst_to_ss_cvr"),
    ("lead_penetration", "pro_adoption_last_week_status"),
    ("lead_penetration", "orders"),
    ("perfect_orders", "orders"),
    ("restaurants_ss_to_atc_cvr", "orders"),
]

OPPORTUNITY_METRICS = {
    "gross_profit_ue",
    "lead_penetration",
    "orders",
    "perfect_orders",
    "restaurants_ss_to_atc_cvr",
    "restaurants_sst_to_ss_cvr",
    "turbo_adoption",
}
MARKDOWN_FINDINGS_PER_CATEGORY = 1
HTML_FINDINGS_PER_CATEGORY = 1
COUNTRY_POINTS = {
    "AR": {"label": "Argentina", "lat": -38.4, "lng": -63.6},
    "BR": {"label": "Brazil", "lat": -14.2, "lng": -51.9},
    "CL": {"label": "Chile", "lat": -35.7, "lng": -71.5},
    "CO": {"label": "Colombia", "lat": 4.6, "lng": -74.1},
    "CR": {"label": "Costa Rica", "lat": 9.9, "lng": -84.1},
    "EC": {"label": "Ecuador", "lat": -1.8, "lng": -78.2},
    "MX": {"label": "Mexico", "lat": 23.6, "lng": -102.5},
    "PE": {"label": "Peru", "lat": -9.2, "lng": -75.0},
    "UY": {"label": "Uruguay", "lat": -32.5, "lng": -55.8},
}
CITY_POINTS = {
    "AR|buenos aires": {"label": "Buenos Aires", "lat": -34.6037, "lng": -58.3816},
    "BR|belo horizonte": {"label": "Belo Horizonte", "lat": -19.9167, "lng": -43.9345},
    "BR|campinas": {"label": "Campinas", "lat": -22.9056, "lng": -47.0608},
    "BR|cascavel": {"label": "Cascavel", "lat": -24.9555, "lng": -53.4552},
    "BR|jundiai": {"label": "Jundiai", "lat": -23.1857, "lng": -46.8978},
    "BR|mogi das cruzes": {"label": "Mogi das Cruzes", "lat": -23.5204, "lng": -46.1859},
    "BR|natal": {"label": "Natal", "lat": -5.7793, "lng": -35.2009},
    "BR|porto alegre": {"label": "Porto Alegre", "lat": -30.0346, "lng": -51.2177},
    "BR|rio de janeiro": {"label": "Rio de Janeiro", "lat": -22.9068, "lng": -43.1729},
    "CL|rancagua": {"label": "Rancagua", "lat": -34.1708, "lng": -70.7406},
    "CO|duitama": {"label": "Duitama", "lat": 5.8269, "lng": -73.0203},
    "CO|florencia": {"label": "Florencia", "lat": 1.6144, "lng": -75.6062},
    "CR|alajuela": {"label": "Alajuela", "lat": 10.0163, "lng": -84.2116},
    "CR|cartago": {"label": "Cartago", "lat": 9.8644, "lng": -83.9194},
    "CR|san jose": {"label": "San Jose", "lat": 9.9281, "lng": -84.0907},
    "EC|machala": {"label": "Machala", "lat": -3.2581, "lng": -79.9554},
    "MX|ciudad guzman": {"label": "Ciudad Guzman", "lat": 19.7047, "lng": -103.4617},
    "MX|cordoba": {"label": "Cordoba", "lat": 18.8847, "lng": -96.9256},
    "MX|orizaba": {"label": "Orizaba", "lat": 18.8499, "lng": -97.1036},
    "MX|san cristobal de las casas": {
        "label": "San Cristobal de las Casas",
        "lat": 16.737,
        "lng": -92.6376,
    },
    "MX|tecate": {"label": "Tecate", "lat": 32.5668, "lng": -116.6251},
    "PE|ica": {"label": "Ica", "lat": -14.0678, "lng": -75.7286},
    "PE|mancora": {"label": "Mancora", "lat": -4.1078, "lng": -81.0475},
}


class InsightFinding(BaseModel):
    id: str
    category: InsightCategoryKey
    severity: Severity
    title: str
    summary: str
    recommendation: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class InsightCategory(BaseModel):
    key: InsightCategoryKey
    title: str
    findings: list[InsightFinding]


class InsightReport(BaseModel):
    report_id: str
    generated_at: str
    source: str
    period_label: str
    executive_summary: list[InsightFinding]
    categories: list[InsightCategory]
    markdown: str
    data_caveats: list[str] = Field(default_factory=list)


def generate_executive_insight_report(
    dataset: OperationalDataset, *, source: str = "api"
) -> InsightReport:
    facts = _fact_frame(dataset)
    catalog = _metric_catalog(dataset)

    anomalies = _anomaly_findings(facts, catalog)
    trends = _trend_findings(facts, catalog)
    benchmarks = _benchmark_findings(facts, catalog)
    correlations = _correlation_findings(facts, catalog)
    opportunities = _opportunity_findings(facts, catalog)

    categories = [
        InsightCategory(key="anomalies", title=CATEGORY_TITLES["anomalies"], findings=anomalies),
        InsightCategory(
            key="worrying_trends",
            title=CATEGORY_TITLES["worrying_trends"],
            findings=trends,
        ),
        InsightCategory(
            key="benchmarking",
            title=CATEGORY_TITLES["benchmarking"],
            findings=benchmarks,
        ),
        InsightCategory(
            key="correlations",
            title=CATEGORY_TITLES["correlations"],
            findings=correlations,
        ),
        InsightCategory(
            key="opportunities",
            title=CATEGORY_TITLES["opportunities"],
            findings=opportunities,
        ),
    ]
    executive_summary = _executive_summary(categories)
    report = InsightReport(
        report_id=str(uuid.uuid4()),
        generated_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        period_label="L0W latest available week, compared with L1W-L8W relative history",
        executive_summary=executive_summary,
        categories=categories,
        markdown="",
        data_caveats=[
            "The dataset uses relative weeks. L0W is the latest available week, not a calendar date.",
            "Rate metrics are simple stored values. The workbook does not provide denominators for weighted averages.",
            "Lead Penetration contains outliers above normal rate ranges; correlation logic excludes values above 1 for that metric.",
            "Recommendations are operational hypotheses from observed metric patterns, not causal proof.",
        ],
    )
    report.markdown = render_report_markdown(report)
    return report


def render_report_markdown(report: InsightReport) -> str:
    lines = [
        "# Rappi Ops Executive Insight Report",
        "",
        "## Executive summary",
        "",
    ]
    if report.executive_summary:
        for index, finding in enumerate(report.executive_summary, start=1):
            lines.extend(
                [
                    f"{index}. **[{finding.severity.upper()}] {finding.title}**",
                    f"   - {finding.summary}",
                    f"   - Action: {finding.recommendation}",
                ]
            )
    else:
        lines.append("No critical findings were detected with the current thresholds.")

    lines.extend(
        [
            "",
            "## Detail by insight category",
            "",
            (
                "Showing the most material finding per required category. "
                "The JSON endpoint keeps the full generated result."
            ),
        ]
    )

    for category in report.categories:
        lines.extend(["", f"### {category.title}", ""])
        if not category.findings:
            lines.append("No findings detected for this category.")
            continue
        for finding in category.findings[:MARKDOWN_FINDINGS_PER_CATEGORY]:
            lines.extend(
                [
                    f"- **[{finding.severity.upper()}] {finding.title}**",
                    f"  - Insight: {finding.summary}",
                    f"  - Action: {finding.recommendation}",
                ]
            )
            evidence = _evidence_text(finding.evidence)
            if evidence:
                lines.append(f"  - Evidence: {evidence}")

    lines.extend(["", "## Data caveats", ""])
    for caveat in report.data_caveats[:2]:
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def render_report_html(report: InsightReport) -> str:
    displayed_findings = sum(
        min(len(category.findings), HTML_FINDINGS_PER_CATEGORY) for category in report.categories
    )
    summary_items = "\n".join(
        _finding_summary_card(finding, index)
        for index, finding in enumerate(report.executive_summary[:5], start=1)
    ) or '<p class="empty-state">No critical findings were detected with the current thresholds.</p>'

    category_sections = "\n".join(_category_detail_section(category) for category in report.categories)
    caveats = "\n".join(f"<li>{_html(caveat)}</li>" for caveat in report.data_caveats)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rappi Ops Executive Insight Report</title>
  <style>
    :root {{
      --ink: #101114;
      --muted: #5f6673;
      --line: #dfe4ea;
      --panel: #ffffff;
      --soft: #f5f7fa;
      --blue: #1677a8;
      --green: #16834f;
      --orange: #bd6b12;
      --red: #c73a31;
      --shadow: 0 18px 60px rgba(24, 32, 44, 0.10);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      background: #eef2f6;
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}

    main {{
      width: min(1060px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 40px;
    }}

    .report-hero {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: linear-gradient(135deg, #111318, #1f2933);
      color: #fff;
      padding: 22px 24px;
      box-shadow: var(--shadow);
    }}

    .eyebrow {{
      margin: 0 0 8px;
      color: rgba(255, 255, 255, 0.66);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}

    h1, h2, h3, p {{ margin: 0; }}

    h1 {{
      max-width: 740px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1;
      letter-spacing: -0.02em;
    }}

    .section {{
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .section-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
      padding: 16px 18px;
    }}

    .section-header h2 {{
      font-size: 18px;
      line-height: 1.1;
    }}

    .section-header span {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }}

    .brief-note {{
      border-bottom: 1px solid var(--line);
      background: #fff;
      color: var(--muted);
      font-size: 13px;
      padding: 12px 18px;
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 12px;
      padding: 16px;
    }}

    .finding-card {{
      position: relative;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      padding: 14px;
      padding-left: 16px;
    }}

    .finding-card h3 {{
      margin-bottom: 4px;
      font-size: 14px;
      line-height: 1.25;
    }}

    .finding-card p {{
      color: var(--muted);
      font-size: 12px;
    }}

    .finding-card::before {{
      position: absolute;
      top: 14px;
      bottom: 14px;
      left: 0;
      width: 4px;
      border-radius: 999px;
      background: var(--blue);
      content: "";
    }}

    .finding-card.severity-critical::before {{ background: var(--red); }}
    .finding-card.severity-high::before {{ background: var(--orange); }}
    .finding-card.severity-medium::before {{ background: var(--blue); }}
    .finding-card.severity-low::before {{ background: var(--green); }}

    .severity-pill {{
      display: inline-flex;
      margin-bottom: 9px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--ink);
      font-size: 10px;
      font-weight: 900;
      letter-spacing: 0.06em;
      padding: 4px 7px;
      text-transform: uppercase;
    }}

    .finding-detail {{
      display: grid;
      gap: 12px;
      padding: 16px;
    }}

    .finding-detail article {{
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      padding: 14px;
      page-break-inside: avoid;
    }}

    .finding-detail h3 {{
      margin-bottom: 8px;
      font-size: 15px;
      line-height: 1.25;
    }}

    .finding-detail p {{
      margin-top: 7px;
      color: var(--muted);
      font-size: 13px;
    }}

    .finding-detail ul {{
      margin: 0;
      padding-left: 18px;
    }}

    .finding-detail li {{
      margin: 5px 0;
      color: var(--muted);
      font-size: 13px;
    }}

    .signal-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 10px;
    }}

    .signal-row span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--soft);
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
      padding: 4px 8px;
    }}

    .empty-state {{
      padding: 16px;
      color: var(--muted);
      font-size: 13px;
    }}

    .caveats {{
      padding: 16px 28px;
      color: var(--muted);
      font-size: 13px;
    }}

    @media (max-width: 760px) {{
      main {{
        width: min(100% - 20px, 1120px);
        padding: 18px 0 28px;
      }}

    }}

    @media print {{
      body {{
        background: #fff;
      }}

      main {{
        width: 100%;
        padding: 0;
      }}

      .report-hero, .section {{
        box-shadow: none;
      }}

      .section {{
        page-break-inside: avoid;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="report-hero">
      <p class="eyebrow">Automatic insights</p>
      <h1>Rappi Ops Executive Insight Report</h1>
    </header>

    <section class="section">
      <div class="section-header">
        <h2>Executive summary</h2>
        <span>Top 3-5 findings</span>
      </div>
      <div class="summary-grid">
        {summary_items}
      </div>
    </section>

    {category_sections}

    <section class="section">
      <div class="section-header">
        <h2>Data caveats</h2>
        <span>{displayed_findings} findings shown</span>
      </div>
      <p class="brief-note">This executive version shows the most material finding per required category. The API JSON keeps the complete generated result for audit and follow-up analysis.</p>
      <ul class="caveats">
        {caveats}
      </ul>
    </section>
  </main>
</body>
</html>
"""


def _fact_frame(dataset: OperationalDataset) -> pd.DataFrame:
    metric_facts = dataset.metric_facts[
        ["zone_id", "metric_key", "week_offset", "week_label", "value"]
    ].copy()
    order_facts = dataset.order_facts[
        ["zone_id", "week_offset", "week_label", "orders"]
    ].copy()
    order_facts["metric_key"] = "orders"
    order_facts = order_facts.rename(columns={"orders": "value"})
    order_facts = order_facts[["zone_id", "metric_key", "week_offset", "week_label", "value"]]

    facts = pd.concat([metric_facts, order_facts], ignore_index=True)
    facts["value"] = pd.to_numeric(facts["value"], errors="coerce")
    facts = facts.dropna(subset=["value"])
    facts = facts.drop_duplicates(subset=["zone_id", "metric_key", "week_offset"])
    facts = facts.merge(dataset.zones, on="zone_id", how="left")
    facts = facts.merge(
        dataset.metrics[
            [
                "metric_key",
                "metric_name",
                "default_direction",
                "value_kind",
                "outlier_policy",
            ]
        ],
        on="metric_key",
        how="left",
    )
    return facts


def _metric_catalog(dataset: OperationalDataset) -> dict[str, dict[str, str]]:
    return {
        str(row["metric_key"]): {
            "metric_name": str(row["metric_name"]),
            "default_direction": str(row["default_direction"]),
            "value_kind": str(row["value_kind"]),
            "outlier_policy": str(row["outlier_policy"]),
        }
        for row in dataset.metrics.to_dict(orient="records")
    }


def _anomaly_findings(
    facts: pd.DataFrame, catalog: dict[str, dict[str, str]]
) -> list[InsightFinding]:
    latest = facts[facts["week_offset"].isin([0, 1])].copy()
    pivot = latest.pivot_table(
        index=[
            "zone_id",
            "country",
            "city",
            "zone",
            "zone_type",
            "metric_key",
            "metric_name",
            "default_direction",
            "value_kind",
        ],
        columns="week_offset",
        values="value",
        aggfunc="mean",
    ).reset_index()
    if 0 not in pivot.columns or 1 not in pivot.columns:
        return []

    pivot = pivot.rename(columns={0: "current_value", 1: "previous_value"}).dropna(
        subset=["current_value", "previous_value"]
    )
    pivot = pivot[
        pivot.apply(
            lambda row: abs(float(row["previous_value"]))
            >= _minimum_baseline(str(row["value_kind"])),
            axis=1,
        )
    ]
    pivot["delta"] = pivot["current_value"] - pivot["previous_value"]
    pivot["change_score"] = pivot.apply(
        lambda row: _scaled_change(
            float(row["current_value"]),
            float(row["previous_value"]),
            str(row["value_kind"]),
        ),
        axis=1,
    )
    pivot = pivot[pivot["change_score"].abs() >= 0.10]
    pivot["severity_abs"] = pivot["change_score"].abs()
    pivot = pivot.sort_values("severity_abs", ascending=False).head(8)

    findings = []
    for index, row in enumerate(pivot.to_dict(orient="records"), start=1):
        direction = row["default_direction"]
        change_score = float(row["change_score"])
        movement = _movement_label(direction, float(row["delta"]))
        metric_name = str(row["metric_name"])
        value_kind = str(row["value_kind"])
        title = f"{metric_name} {movement} in {row['zone']}, {row['city']} ({row['country']})"
        if value_kind == "currency_per_order":
            summary = (
                f"{metric_name} changed by {_signed_number(row['delta'])} week-over-week, "
                f"from {_value(row['previous_value'], value_kind)} in L1W to "
                f"{_value(row['current_value'], value_kind)} in L0W."
            )
        else:
            summary = (
                f"{metric_name} moved {_pct(change_score)} week-over-week, from "
                f"{_value(row['previous_value'], value_kind)} in L1W to "
                f"{_value(row['current_value'], value_kind)} in L0W."
            )
        recommendation = (
            "Audit the local operating changes behind the improvement and decide whether they can be replicated."
            if movement == "improved"
            else "Inspect local supply, funnel, and execution changes immediately; this crossed the 10% week-over-week threshold."
        )
        findings.append(
            InsightFinding(
                id=_finding_id("anomaly", title, index),
                category="anomalies",
                severity=_severity_from_pct(abs(change_score)),
                title=title,
                summary=summary,
                recommendation=recommendation,
                evidence={
                    "country": row["country"],
                    "city": row["city"],
                    "zone": row["zone"],
                    "zone_type": row["zone_type"],
                    "metric": metric_name,
                    "previous_week": "L1W",
                    "current_week": "L0W",
                    "previous_value": _safe_float(row["previous_value"]),
                    "current_value": _safe_float(row["current_value"]),
                    "delta": _safe_float(row["delta"]),
                    "change_score": _safe_float(change_score),
                    "direction": direction,
                    "outlier_policy": catalog.get(row["metric_key"], {}).get("outlier_policy"),
                },
            )
        )
    return findings


def _trend_findings(
    facts: pd.DataFrame, catalog: dict[str, dict[str, str]]
) -> list[InsightFinding]:
    directional = facts[
        (facts["week_offset"].isin([0, 1, 2, 3]))
        & (facts["default_direction"].isin(["higher_better", "lower_better"]))
    ].copy()
    pivot = directional.pivot_table(
        index=[
            "zone_id",
            "country",
            "city",
            "zone",
            "zone_type",
            "metric_key",
            "metric_name",
            "default_direction",
            "value_kind",
        ],
        columns="week_offset",
        values="value",
        aggfunc="mean",
    ).reset_index()
    if not all(offset in pivot.columns for offset in [0, 1, 2, 3]):
        return []

    pivot = pivot.dropna(subset=[0, 1, 2, 3])
    higher = pivot["default_direction"] == "higher_better"
    lower = pivot["default_direction"] == "lower_better"
    deteriorating = (higher & (pivot[3] > pivot[2]) & (pivot[2] > pivot[1]) & (pivot[1] > pivot[0])) | (
        lower & (pivot[3] < pivot[2]) & (pivot[2] < pivot[1]) & (pivot[1] < pivot[0])
    )
    pivot = pivot[deteriorating].copy()
    if pivot.empty:
        return []
    pivot = pivot[
        pivot.apply(
            lambda row: abs(float(row[3])) >= _minimum_baseline(str(row["value_kind"])),
            axis=1,
        )
    ]
    if pivot.empty:
        return []

    pivot["relative_deterioration"] = pivot.apply(
        lambda row: _relative_deterioration(
            float(row[3]), float(row[0]), str(row["default_direction"])
        ),
        axis=1,
    )
    pivot = pivot.sort_values("relative_deterioration", ascending=False).head(8)

    findings = []
    for index, row in enumerate(pivot.to_dict(orient="records"), start=1):
        metric_name = str(row["metric_name"])
        value_kind = str(row["value_kind"])
        values = {
            f"L{offset}W": _safe_float(row[offset])
            for offset in [3, 2, 1, 0]
        }
        title = f"{metric_name} deteriorated for 3 consecutive weeks in {row['zone']}"
        summary = (
            f"{metric_name} has worsened each week from L3W to L0W in "
            f"{row['zone']}, {row['city']} ({row['country']}). Latest value: "
            f"{_value(row[0], value_kind)}."
        )
        findings.append(
            InsightFinding(
                id=_finding_id("trend", title, index),
                category="worrying_trends",
                severity=_severity_from_score(float(row["relative_deterioration"])),
                title=title,
                summary=summary,
                recommendation=(
                    "Create a recovery owner for this zone and review weekly drivers before the deterioration becomes the new baseline."
                ),
                evidence={
                    "country": row["country"],
                    "city": row["city"],
                    "zone": row["zone"],
                    "zone_type": row["zone_type"],
                    "metric": metric_name,
                    "values": values,
                    "relative_deterioration": _safe_float(row["relative_deterioration"]),
                    "direction": catalog.get(row["metric_key"], {}).get("default_direction"),
                },
            )
        )
    return findings


def _benchmark_findings(
    facts: pd.DataFrame, catalog: dict[str, dict[str, str]]
) -> list[InsightFinding]:
    current = facts[
        (facts["week_offset"] == 0)
        & (facts["default_direction"].isin(["higher_better", "lower_better"]))
    ].copy()
    peer_stats = (
        current.groupby(["country", "zone_type", "metric_key"], dropna=False)
        .agg(
            peer_median=("value", "median"),
            peer_p25=("value", lambda series: series.quantile(0.25)),
            peer_p75=("value", lambda series: series.quantile(0.75)),
            peer_n=("zone_id", "nunique"),
        )
        .reset_index()
    )
    current = current.merge(peer_stats, on=["country", "zone_type", "metric_key"], how="left")
    current = current[(current["peer_n"] >= 5)]
    current["gap_value"] = current["value"] - current["peer_median"]
    current["peer_scale"] = current.apply(
        lambda row: _benchmark_scale(
            float(row["peer_median"]),
            float(row["peer_p75"] - row["peer_p25"]),
            str(row["value_kind"]),
        ),
        axis=1,
    )
    current = current[current["peer_scale"] > 0]
    current["gap_score"] = current["gap_value"] / current["peer_scale"]
    current["underperformance_score"] = current.apply(
        lambda row: -float(row["gap_score"])
        if row["default_direction"] == "higher_better"
        else float(row["gap_score"]),
        axis=1,
    )
    current = current[current["underperformance_score"] >= 0.15]
    current = current.sort_values("underperformance_score", ascending=False).head(8)

    findings = []
    for index, row in enumerate(current.to_dict(orient="records"), start=1):
        metric_name = str(row["metric_name"])
        value_kind = str(row["value_kind"])
        zone_type = str(row["zone_type"] or "untyped")
        title = f"{row['zone']} trails {row['country']} {zone_type} peers on {metric_name}"
        if value_kind == "currency_per_order":
            summary = (
                f"{row['zone']} is {_signed_number(row['gap_value'])} versus the "
                f"same-country, same-type peer median for {metric_name}."
            )
        else:
            summary = (
                f"{row['zone']} is {_pct(row['underperformance_score'])} worse than the "
                f"same-country, same-type peer median for {metric_name}."
            )
        findings.append(
            InsightFinding(
                id=_finding_id("benchmark", title, index),
                category="benchmarking",
                severity=_severity_from_pct(float(row["underperformance_score"])),
                title=title,
                summary=summary,
                recommendation=(
                    "Compare staffing, merchant coverage, and funnel practices against the stronger peer zones in the same benchmark group."
                ),
                evidence={
                    "country": row["country"],
                    "city": row["city"],
                    "zone": row["zone"],
                    "zone_type": row["zone_type"],
                    "metric": metric_name,
                    "current_value": _safe_float(row["value"]),
                    "peer_median": _safe_float(row["peer_median"]),
                    "peer_n": int(row["peer_n"]),
                    "gap_value": _safe_float(row["gap_value"]),
                    "gap_score": _safe_float(row["gap_score"]),
                    "underperformance_score": _safe_float(row["underperformance_score"]),
                    "current_value_label": _value(row["value"], value_kind),
                    "peer_median_label": _value(row["peer_median"], value_kind),
                    "direction": catalog.get(row["metric_key"], {}).get("default_direction"),
                },
            )
        )
    return findings


def _correlation_findings(
    facts: pd.DataFrame, catalog: dict[str, dict[str, str]]
) -> list[InsightFinding]:
    current = facts[facts["week_offset"] == 0].copy()
    current.loc[
        (current["metric_key"] == "lead_penetration") & (current["value"] > 1),
        "value",
    ] = math.nan
    pivot = current.pivot_table(
        index=["zone_id", "country", "city", "zone", "zone_type"],
        columns="metric_key",
        values="value",
        aggfunc="mean",
    ).reset_index()

    rows = []
    for metric_x, metric_y in CORRELATION_PAIRS:
        if metric_x not in pivot.columns or metric_y not in pivot.columns:
            continue
        pair = pivot[["zone_id", "country", "city", "zone", metric_x, metric_y]].dropna()
        if len(pair) < 25:
            continue
        corr = pair[metric_x].corr(pair[metric_y])
        if pd.isna(corr):
            continue
        x_p25 = pair[metric_x].quantile(0.25)
        y_p25 = pair[metric_y].quantile(0.25)
        low_low = pair[(pair[metric_x] <= x_p25) & (pair[metric_y] <= y_p25)]
        rows.append(
            {
                "metric_x": metric_x,
                "metric_y": metric_y,
                "corr": float(corr),
                "n_zones": int(len(pair)),
                "low_low_count": int(len(low_low)),
                "x_p25": float(x_p25),
                "y_p25": float(y_p25),
            }
        )
    rows = sorted(rows, key=lambda item: abs(item["corr"]), reverse=True)[:5]

    findings = []
    for index, row in enumerate(rows, start=1):
        metric_x = _metric_name(catalog, row["metric_x"])
        metric_y = _metric_name(catalog, row["metric_y"])
        relationship = "move together" if row["corr"] >= 0 else "move in opposite directions"
        title = f"{metric_x} and {metric_y} {relationship}"
        summary = (
            f"Across {row['n_zones']} zones, Pearson correlation is "
            f"{row['corr']:.2f}. {row['low_low_count']} zones sit in the bottom quartile of both metrics."
        )
        findings.append(
            InsightFinding(
                id=_finding_id("correlation", title, index),
                category="correlations",
                severity=_severity_from_correlation(abs(row["corr"]), row["low_low_count"]),
                title=title,
                summary=summary,
                recommendation=(
                    "Use the low-low zone list as a diagnostic queue and test whether improving the upstream metric lifts the downstream conversion or quality metric."
                ),
                evidence={
                    "metric_x": metric_x,
                    "metric_y": metric_y,
                    "pearson_correlation": _safe_float(row["corr"]),
                    "n_zones": row["n_zones"],
                    "low_low_count": row["low_low_count"],
                    "metric_x_p25": _safe_float(row["x_p25"]),
                    "metric_y_p25": _safe_float(row["y_p25"]),
                },
            )
        )
    return findings


def _opportunity_findings(
    facts: pd.DataFrame, catalog: dict[str, dict[str, str]]
) -> list[InsightFinding]:
    current = facts[
        (facts["week_offset"] == 0)
        & (facts["metric_key"].isin(OPPORTUNITY_METRICS))
        & (facts["default_direction"].isin(["higher_better", "lower_better"]))
    ].copy()
    if current.empty:
        return []

    current["percentile"] = current.groupby("metric_key")["value"].rank(pct=True)
    current["metric_risk"] = current.apply(
        lambda row: 1 - float(row["percentile"])
        if row["default_direction"] == "higher_better"
        else float(row["percentile"]),
        axis=1,
    )
    zone_risk = (
        current.groupby(["zone_id", "country", "city", "zone", "zone_type", "zone_prioritization"])
        .agg(avg_metric_risk=("metric_risk", "mean"), max_metric_risk=("metric_risk", "max"))
        .reset_index()
    )

    deterioration = _latest_deterioration_by_zone(facts)
    trend_counts = _trend_count_by_zone(facts)
    zone_risk = zone_risk.merge(deterioration, on="zone_id", how="left")
    zone_risk = zone_risk.merge(trend_counts, on="zone_id", how="left")
    zone_risk["max_deterioration_pct"] = zone_risk["max_deterioration_pct"].fillna(0)
    zone_risk["trend_count"] = zone_risk["trend_count"].fillna(0)
    priority_boost = zone_risk["zone_prioritization"].map(
        {"High Priority": 0.15, "Prioritized": 0.08}
    ).fillna(0)
    zone_risk["opportunity_score"] = (
        zone_risk["avg_metric_risk"]
        + priority_boost
        + zone_risk["max_deterioration_pct"].clip(upper=0.6) * 0.30
        + zone_risk["trend_count"].clip(upper=3) * 0.05
    )
    zone_risk = zone_risk.sort_values("opportunity_score", ascending=False).head(6)

    findings = []
    for index, row in enumerate(zone_risk.to_dict(orient="records"), start=1):
        weak_metrics = _weak_metrics_for_zone(current, str(row["zone_id"]), catalog)
        weak_labels = ", ".join(item["metric"] for item in weak_metrics[:3])
        title = f"{row['zone']} is a high-priority intervention candidate"
        summary = (
            f"{row['zone']}, {row['city']} ({row['country']}) has a composite opportunity "
            f"score of {float(row['opportunity_score']):.2f}. Weakest metrics: {weak_labels}."
        )
        findings.append(
            InsightFinding(
                id=_finding_id("opportunity", title, index),
                category="opportunities",
                severity=_severity_from_score(float(row["opportunity_score"])),
                title=title,
                summary=summary,
                recommendation=(
                    "Assign a short intervention plan focused on the weakest metric cluster, then re-check L0W versus L1W after the next refresh."
                ),
                evidence={
                    "country": row["country"],
                    "city": row["city"],
                    "zone": row["zone"],
                    "zone_type": row["zone_type"],
                    "zone_prioritization": row["zone_prioritization"],
                    "opportunity_score": _safe_float(row["opportunity_score"]),
                    "avg_metric_risk": _safe_float(row["avg_metric_risk"]),
                    "max_deterioration_pct": _safe_float(row["max_deterioration_pct"]),
                    "trend_count": int(row["trend_count"]),
                    "weak_metrics": weak_metrics,
                },
            )
        )
    return findings


def _latest_deterioration_by_zone(facts: pd.DataFrame) -> pd.DataFrame:
    latest = facts[
        (facts["week_offset"].isin([0, 1]))
        & (facts["default_direction"].isin(["higher_better", "lower_better"]))
    ].copy()
    pivot = latest.pivot_table(
        index=["zone_id", "metric_key", "default_direction", "value_kind"],
        columns="week_offset",
        values="value",
        aggfunc="mean",
    ).reset_index()
    if 0 not in pivot.columns or 1 not in pivot.columns:
        return pd.DataFrame(columns=["zone_id", "max_deterioration_pct"])
    pivot = pivot.dropna(subset=[0, 1])
    pivot = pivot[
        pivot.apply(
            lambda row: abs(float(row[1])) >= _minimum_baseline(str(row["value_kind"])),
            axis=1,
        )
    ]
    pivot["change_score"] = pivot.apply(
        lambda row: _scaled_change(float(row[0]), float(row[1]), str(row["value_kind"])),
        axis=1,
    )
    pivot["deterioration_pct"] = pivot.apply(
        lambda row: max(0.0, -float(row["change_score"]))
        if row["default_direction"] == "higher_better"
        else max(0.0, float(row["change_score"])),
        axis=1,
    )
    return (
        pivot.groupby("zone_id")
        .agg(max_deterioration_pct=("deterioration_pct", "max"))
        .reset_index()
    )


def _trend_count_by_zone(facts: pd.DataFrame) -> pd.DataFrame:
    directional = facts[
        (facts["week_offset"].isin([0, 1, 2, 3]))
        & (facts["default_direction"].isin(["higher_better", "lower_better"]))
    ].copy()
    pivot = directional.pivot_table(
        index=["zone_id", "metric_key", "default_direction"],
        columns="week_offset",
        values="value",
        aggfunc="mean",
    ).reset_index()
    if not all(offset in pivot.columns for offset in [0, 1, 2, 3]):
        return pd.DataFrame(columns=["zone_id", "trend_count"])
    pivot = pivot.dropna(subset=[0, 1, 2, 3])
    higher = pivot["default_direction"] == "higher_better"
    lower = pivot["default_direction"] == "lower_better"
    deteriorating = (higher & (pivot[3] > pivot[2]) & (pivot[2] > pivot[1]) & (pivot[1] > pivot[0])) | (
        lower & (pivot[3] < pivot[2]) & (pivot[2] < pivot[1]) & (pivot[1] < pivot[0])
    )
    return (
        pivot[deteriorating]
        .groupby("zone_id")
        .size()
        .rename("trend_count")
        .reset_index()
    )


def _weak_metrics_for_zone(
    current: pd.DataFrame, zone_id: str, catalog: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    rows = current[current["zone_id"] == zone_id].sort_values("metric_risk", ascending=False)
    weak_metrics = []
    for row in rows.head(3).to_dict(orient="records"):
        metric_key = str(row["metric_key"])
        weak_metrics.append(
            {
                "metric": _metric_name(catalog, metric_key),
                "value": _safe_float(row["value"]),
                "risk": _safe_float(row["metric_risk"]),
            }
        )
    return weak_metrics


def _executive_summary(categories: list[InsightCategory]) -> list[InsightFinding]:
    preferred: list[InsightFinding] = []
    by_category = {category.key: category.findings for category in categories}
    for key in ["opportunities", "anomalies", "worrying_trends", "benchmarking", "correlations"]:
        if by_category.get(key):
            preferred.append(by_category[key][0])

    all_findings = [finding for category in categories for finding in category.findings]
    all_findings = sorted(
        all_findings,
        key=lambda finding: (SEVERITY_RANK[finding.severity], finding.title),
        reverse=True,
    )
    seen = set()
    selected = []
    for finding in preferred + all_findings:
        if finding.id in seen:
            continue
        selected.append(finding)
        seen.add(finding.id)
        if len(selected) == 5:
            break
    return selected[:5]


def _movement_label(direction: str, pct_change: float) -> str:
    if direction == "higher_better":
        return "improved" if pct_change > 0 else "deteriorated"
    if direction == "lower_better":
        return "improved" if pct_change < 0 else "deteriorated"
    return "changed"


def _relative_deterioration(start_value: float, end_value: float, direction: str) -> float:
    if abs(start_value) < 1e-9:
        return 0.0
    pct = (end_value - start_value) / abs(start_value)
    return max(0.0, -pct) if direction == "higher_better" else max(0.0, pct)


def _scaled_change(current_value: float, previous_value: float, value_kind: str) -> float:
    scale = abs(previous_value)
    if value_kind == "currency_per_order":
        scale = max(scale, 1.0)
    else:
        scale = max(scale, _minimum_baseline(value_kind))
    if scale <= 0:
        return 0.0
    return (current_value - previous_value) / scale


def _benchmark_scale(peer_median: float, peer_iqr: float, value_kind: str) -> float:
    if value_kind == "currency_per_order":
        return max(abs(peer_median), abs(peer_iqr), 1.0)
    return max(abs(peer_median), _minimum_baseline(value_kind))


def _minimum_baseline(value_kind: str) -> float:
    if value_kind == "count":
        return 1.0
    if value_kind == "currency_per_order":
        return 0.10
    if value_kind == "rate":
        return 0.01
    return 0.01


def _metric_name(catalog: dict[str, dict[str, str]], metric_key: str) -> str:
    return catalog.get(metric_key, {}).get("metric_name", metric_key.replace("_", " ").title())


def _severity_from_pct(value: float) -> Severity:
    if value >= 0.40:
        return "critical"
    if value >= 0.25:
        return "high"
    if value >= 0.10:
        return "medium"
    return "low"


def _severity_from_score(value: float) -> Severity:
    if value >= 0.85:
        return "critical"
    if value >= 0.70:
        return "high"
    if value >= 0.55:
        return "medium"
    return "low"


def _severity_from_correlation(abs_corr: float, low_low_count: int) -> Severity:
    if abs_corr >= 0.55 and low_low_count >= 20:
        return "high"
    if abs_corr >= 0.35 and low_low_count >= 10:
        return "medium"
    return "low"


def _finding_id(prefix: str, title: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:56]
    return f"{prefix}-{index}-{slug}"


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _pct(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:+.1%}"


def _value(value: Any, value_kind: str | None = None) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    if value_kind == "count":
        return f"{number:,.0f}"
    if value_kind == "currency_per_order":
        return f"{number:,.2f}"
    if value_kind == "rate" and 0 <= number <= 1:
        return f"{number:.1%}"
    if abs(number) >= 100:
        return f"{number:,.0f}"
    if abs(number) >= 10:
        return f"{number:,.2f}"
    return f"{number:.3f}"


def _signed_number(value: Any) -> str:
    number = _safe_float(value)
    if number is None:
        return "n/a"
    return f"{number:+.2f}"


def _evidence_text(evidence: dict[str, Any]) -> str:
    ordered_keys = [
        "country",
        "city",
        "zone",
        "zone_type",
        "metric",
        "change_score",
        "underperformance_score",
        "pearson_correlation",
        "low_low_count",
        "opportunity_score",
        "trend_count",
    ]
    chunks = []
    for key in ordered_keys:
        if key not in evidence or evidence[key] is None:
            continue
        value = evidence[key]
        if isinstance(value, float):
            value = f"{value:.3g}"
        chunks.append(f"{key}: {value}")
    return "; ".join(chunks)


def _findings_for(report: InsightReport, key: InsightCategoryKey) -> list[InsightFinding]:
    for category in report.categories:
        if category.key == key:
            return category.findings
    return []


def _category_count_chart(report: InsightReport) -> str:
    colors_by_category = {
        "anomalies": "#c73a31",
        "worrying_trends": "#bd6b12",
        "benchmarking": "#1677a8",
        "correlations": "#635bff",
        "opportunities": "#16834f",
    }
    rows = [
        {
            "label": category.title,
            "value": len(category.findings),
            "value_label": str(len(category.findings)),
            "color": colors_by_category[category.key],
        }
        for category in report.categories
    ]
    return _chart_card(
        "Findings by category",
        "Coverage across the required insight categories.",
        _horizontal_bars_svg(rows),
    )


def _severity_mix_chart(findings: list[InsightFinding]) -> str:
    severity_colors = {
        "critical": "#c73a31",
        "high": "#bd6b12",
        "medium": "#1677a8",
        "low": "#16834f",
    }
    rows = []
    for severity in ["critical", "high", "medium", "low"]:
        count = sum(1 for finding in findings if finding.severity == severity)
        rows.append(
            {
                "label": severity.title(),
                "value": count,
                "value_label": str(count),
                "color": severity_colors[severity],
            }
        )
    return _chart_card(
        "Severity mix",
        "Risk distribution across the generated report.",
        _horizontal_bars_svg(rows),
    )


def _geo_risk_map_chart(findings: list[InsightFinding]) -> str:
    locations: dict[str, dict[str, Any]] = {}
    for finding in findings:
        code = str(finding.evidence.get("country") or "")
        if code not in COUNTRY_POINTS:
            continue
        city = str(finding.evidence.get("city") or "")
        city_point = CITY_POINTS.get(_location_key(code, city)) if city else None
        point = city_point or COUNTRY_POINTS[code]
        location_id = f"{code}:{_normalize_location_name(city)}" if city_point else code
        label = f"{point['label']}, {code}" if city_point else str(point["label"])
        current = locations.setdefault(
            location_id,
            {
                "code": code,
                "count": 0,
                "critical": 0,
                "high": 0,
                "id": location_id,
                "label": label,
                "lat": point["lat"],
                "lng": point["lng"],
                "risk": 0,
                "top_finding": finding.title,
            },
        )
        severity_score = SEVERITY_RANK[finding.severity]
        current["count"] += 1
        current["critical"] += 1 if finding.severity == "critical" else 0
        current["high"] += 1 if finding.severity == "high" else 0
        current["risk"] += severity_score
        if severity_score > current.get("top_score", 0):
            current["top_score"] = severity_score
            current["top_finding"] = finding.title

    rows = sorted(locations.values(), key=lambda row: row["risk"], reverse=True)
    return _chart_card(
        "Operational risk map",
        "Real map tiles with city-level risk markers where coordinates are available.",
        _geo_map_embed(rows),
        class_name="chart-card-wide",
    )


def _anomaly_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        change = _number_from_evidence(finding, "change_score")
        if change is None:
            continue
        direction = str(finding.evidence.get("direction") or "")
        impact = -change if direction == "lower_better" else change
        rows.append(
            {
                "label": _zone_metric_label(finding),
                "value": impact,
                "value_label": _pct(impact),
                "color": "#16834f" if impact >= 0 else "#c73a31",
            }
        )
    return _chart_card(
        "Week-over-week anomalies",
        "Signed impact after metric direction is applied.",
        _horizontal_bars_svg(rows, signed=True),
    )


def _trend_path_chart(findings: list[InsightFinding]) -> str:
    series = []
    for finding in findings[:3]:
        values = finding.evidence.get("values")
        if not isinstance(values, dict):
            continue
        start = _safe_float(values.get("L3W"))
        if start is None or abs(start) < 1e-9:
            continue
        direction = str(finding.evidence.get("direction") or "")
        points = []
        for week in ["L3W", "L2W", "L1W", "L0W"]:
            raw = _safe_float(values.get(week))
            if raw is None:
                continue
            deterioration = (
                (raw - start) / abs(start)
                if direction == "lower_better"
                else (start - raw) / abs(start)
            )
            health = (1 - max(0.0, deterioration)) * 100
            points.append((week, _clamp(health, 0, 125)))
        if len(points) == 4:
            series.append(
                {
                    "label": _zone_metric_label(finding),
                    "points": points,
                }
            )
    return _chart_card(
        "Worrying trend paths",
        "Normalized health index for 3+ consecutive weeks of deterioration.",
        _line_series_svg(series),
        class_name="chart-card-wide",
    )


def _trend_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        deterioration = _number_from_evidence(finding, "relative_deterioration")
        if deterioration is None:
            continue
        rows.append(
            {
                "label": _zone_metric_label(finding),
                "value": deterioration,
                "value_label": _pct(deterioration),
                "color": "#bd6b12",
            }
        )
    return _chart_card(
        "3-week deterioration",
        "Largest consistent deteriorations from L3W to L0W.",
        _horizontal_bars_svg(rows),
    )


def _benchmark_index_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:5]:
        underperformance = _number_from_evidence(finding, "underperformance_score")
        if underperformance is None:
            continue
        zone = (1 - max(0.0, underperformance)) * 100
        rows.append(
            {
                "label": _zone_metric_label(finding),
                "peer": 100,
                "zone": _clamp(zone, 0, 130),
            }
        )
    return _chart_card(
        "Benchmark gap index",
        "Zone performance versus same-country/type peer median indexed to 100.",
        _paired_index_svg(rows),
    )


def _benchmark_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        underperformance = _number_from_evidence(finding, "underperformance_score")
        if underperformance is None:
            continue
        rows.append(
            {
                "label": _zone_metric_label(finding),
                "value": underperformance,
                "value_label": _pct(underperformance),
                "color": "#1677a8",
            }
        )
    return _chart_card(
        "Peer benchmark gaps",
        "Underperformance versus same-country and same-type peer medians.",
        _horizontal_bars_svg(rows),
    )


def _correlation_scatter_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        corr = _number_from_evidence(finding, "pearson_correlation")
        low_low = _number_from_evidence(finding, "low_low_count")
        if corr is None or low_low is None:
            continue
        rows.append(
            {
                "label": _compact_label(
                    f"{finding.evidence.get('metric_x')} / {finding.evidence.get('metric_y')}",
                    40,
                ),
                "corr": corr,
                "low_low": low_low,
            }
        )
    return _chart_card(
        "Correlation quadrant",
        "Relationship strength versus zones low on both metrics.",
        _scatter_svg(rows),
    )


def _correlation_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        correlation = _number_from_evidence(finding, "pearson_correlation")
        if correlation is None:
            continue
        rows.append(
            {
                "label": _compact_label(f"{finding.evidence.get('metric_x')} / {finding.evidence.get('metric_y')}", 44),
                "value": correlation,
                "value_label": f"{correlation:+.2f}",
                "color": "#16834f" if correlation >= 0 else "#bd6b12",
            }
        )
    return _chart_card(
        "Metric correlations",
        "Pearson relationships across zones in the latest week.",
        _horizontal_bars_svg(rows, signed=True),
    )


def _opportunity_driver_chart(findings: list[InsightFinding]) -> str:
    if not findings:
        return _chart_card(
            "Opportunity drivers",
            "Top zone's weakest metrics. Higher risk is worse.",
            "",
        )
    weak_metrics = findings[0].evidence.get("weak_metrics")
    rows = []
    if isinstance(weak_metrics, list):
        for item in weak_metrics[:5]:
            if not isinstance(item, dict):
                continue
            risk = _safe_float(item.get("risk"))
            metric = item.get("metric")
            if risk is None or metric is None:
                continue
            rows.append(
                {
                    "label": _compact_label(str(metric), 28),
                    "value": _clamp(risk, 0, 1),
                    "value_label": f"{_clamp(risk, 0, 1):.0%}",
                    "color": "#16834f",
                }
            )
    return _chart_card(
        "Opportunity drivers",
        f"Weakest metrics for {_zone_metric_label(findings[0], include_metric=False)}. Higher risk is worse.",
        _horizontal_bars_svg(rows),
    )


def _opportunity_chart(findings: list[InsightFinding]) -> str:
    rows = []
    for finding in findings[:6]:
        score = _number_from_evidence(finding, "opportunity_score")
        if score is None:
            continue
        rows.append(
            {
                "label": _zone_metric_label(finding, include_metric=False),
                "value": score,
                "value_label": f"{score:.2f}",
                "color": "#16834f",
            }
        )
    return _chart_card(
        "Opportunity ranking",
        "Composite intervention score by zone.",
        _horizontal_bars_svg(rows),
    )


def _finding_summary_card(finding: InsightFinding, index: int) -> str:
    return f"""<article class="finding-card severity-{_html(finding.severity)}">
  <span class="severity-pill">{index}. {_html(finding.severity)}</span>
  <h3>{_html(finding.title)}</h3>
  <p>{_html(finding.recommendation)}</p>
</article>"""


def _category_detail_section(category: InsightCategory) -> str:
    if not category.findings:
        findings_html = '<p class="empty-state">No findings detected for this category.</p>'
    else:
        findings_html = "\n".join(
            _finding_detail_card(finding)
            for finding in category.findings[:HTML_FINDINGS_PER_CATEGORY]
        )
    shown_count = min(len(category.findings), HTML_FINDINGS_PER_CATEGORY)
    return f"""<section class="section">
  <div class="section-header">
    <h2>{_html(category.title)}</h2>
    <span>{shown_count} of {len(category.findings)} shown</span>
  </div>
  <div class="finding-detail">
    {findings_html}
  </div>
</section>"""


def _finding_detail_card(finding: InsightFinding) -> str:
    evidence_badges = _evidence_badges(finding)
    badge_row = (
        f'<div class="signal-row">{"".join(f"<span>{_html(item)}</span>" for item in evidence_badges)}</div>'
        if evidence_badges
        else ""
    )
    return f"""<article>
  <span class="severity-pill">{_html(finding.severity)}</span>
  <h3>{_html(finding.title)}</h3>
  <p>{_html(finding.summary)}</p>
  <p><strong>Action:</strong> {_html(finding.recommendation)}</p>
  {badge_row}
</article>"""


def _evidence_badges(finding: InsightFinding) -> list[str]:
    evidence = finding.evidence
    badges: list[str] = []
    zone = str(evidence.get("zone") or "")
    city = str(evidence.get("city") or "")
    metric = str(evidence.get("metric") or "")
    location = ", ".join(part for part in [zone, city] if part)
    if location:
        badges.append(location)
    if metric:
        badges.append(metric)

    if finding.category == "anomalies":
        change = _safe_float(evidence.get("change_score"))
        if change is not None:
            direction = str(evidence.get("direction") or "")
            impact = -change if direction == "lower_better" else change
            badges.append(f"WoW impact {_pct(impact)}")
        previous_value = evidence.get("previous_value")
        current_value = evidence.get("current_value")
        if previous_value is not None and current_value is not None:
            badges.append(f"L1W {_value(previous_value)} -> L0W {_value(current_value)}")

    elif finding.category == "worrying_trends":
        deterioration = _safe_float(evidence.get("relative_deterioration"))
        if deterioration is not None:
            badges.append(f"Deterioration {_pct(deterioration)}")
        values = evidence.get("values")
        if isinstance(values, dict):
            start = values.get("L3W")
            end = values.get("L0W")
            if start is not None and end is not None:
                badges.append(f"L3W {_value(start)} -> L0W {_value(end)}")

    elif finding.category == "benchmarking":
        score = _safe_float(evidence.get("underperformance_score"))
        if score is not None:
            badges.append(f"Gap {_pct(score)}")
        current_label = evidence.get("current_value_label")
        peer_label = evidence.get("peer_median_label")
        if current_label and peer_label:
            badges.append(f"Zone {current_label} vs peer {peer_label}")

    elif finding.category == "correlations":
        metric_x = str(evidence.get("metric_x") or "")
        metric_y = str(evidence.get("metric_y") or "")
        if metric_x and metric_y:
            badges.append(_compact_label(f"{metric_x} / {metric_y}", 46))
        corr = _safe_float(evidence.get("pearson_correlation"))
        if corr is not None:
            badges.append(f"r={corr:+.2f}")
        low_low = evidence.get("low_low_count")
        zones = evidence.get("n_zones")
        if low_low is not None and zones is not None:
            badges.append(f"{low_low}/{zones} low-low zones")

    elif finding.category == "opportunities":
        score = _safe_float(evidence.get("opportunity_score"))
        if score is not None:
            badges.append(f"Score {score:.2f}")
        trend_count = evidence.get("trend_count")
        if trend_count is not None:
            badges.append(f"{trend_count} worsening trends")
        weak_metrics = evidence.get("weak_metrics")
        if isinstance(weak_metrics, list) and weak_metrics:
            names = [
                str(item.get("metric"))
                for item in weak_metrics
                if isinstance(item, dict) and item.get("metric")
            ]
            if names:
                badges.append(_compact_label("Weakest: " + ", ".join(names[:2]), 48))

    return badges[:5]


def _chart_card(title: str, description: str, svg: str, *, class_name: str = "") -> str:
    chart = svg or '<p class="empty-state">Not enough structured evidence for this chart.</p>'
    classes = " ".join(part for part in ["chart-card", class_name] if part)
    return f"""<article class="{_html(classes)}">
  <h3>{_html(title)}</h3>
  <p>{_html(description)}</p>
  {chart}
</article>"""


def _horizontal_bars_svg(rows: list[dict[str, Any]], *, signed: bool = False) -> str:
    rows = [row for row in rows if _safe_float(row.get("value")) is not None]
    if not rows:
        return ""

    width = 720
    row_height = 42
    top = 24
    label_x = 16
    label_width = 214
    plot_x = 238
    plot_width = 396
    value_x = 652
    height = top + len(rows) * row_height + 14
    max_abs = max(abs(float(row["value"])) for row in rows) or 1
    max_value = max(float(row["value"]) for row in rows) or 1

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Chart">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#f8fafc" />',
    ]
    if signed:
        center = plot_x + plot_width / 2
        parts.append(
            f'<line x1="{center:.1f}" y1="12" x2="{center:.1f}" y2="{height - 10}" '
            'stroke="#cfd7df" stroke-width="1" />'
        )

    for index, row in enumerate(rows):
        value = float(row["value"])
        y = top + index * row_height
        label = _compact_label(str(row["label"]), 32)
        value_label = str(row.get("value_label") or _value(value))
        color = str(row.get("color") or "#1677a8")
        parts.append(
            f'<text x="{label_x}" y="{y + 16}" fill="#27313d" font-size="12" '
            f'font-weight="700">{_html(label)}</text>'
        )
        parts.append(
            f'<line x1="{plot_x}" y1="{y + 25}" x2="{plot_x + plot_width}" y2="{y + 25}" '
            'stroke="#e7ecf1" stroke-width="1" />'
        )
        if signed:
            center = plot_x + plot_width / 2
            bar_width = max(4, (abs(value) / max_abs) * (plot_width / 2 - 10))
            x = center if value >= 0 else center - bar_width
        else:
            bar_width = max(4, (abs(value) / max(max_value, 1e-9)) * plot_width)
            x = plot_x
        parts.append(
            f'<rect x="{x:.1f}" y="{y + 12}" width="{bar_width:.1f}" height="18" '
            f'rx="5" fill="{_html(color)}" />'
        )
        parts.append(
            f'<text x="{value_x}" y="{y + 26}" fill="#5f6673" font-size="12" '
            f'font-weight="800" text-anchor="end">{_html(value_label)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _geo_map_embed(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    max_risk = max(float(row["risk"]) for row in rows) or 1
    markers = [
        {
            "critical": int(row["critical"]),
            "count": int(row["count"]),
            "high": int(row["high"]),
            "label": str(row["label"]),
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "risk": float(row["risk"]),
            "topFinding": str(row["top_finding"]),
        }
        for row in rows
    ]
    data_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    for marker in markers:
        risk = float(marker["risk"])
        marker["radius"] = 7 + min(13, risk / max_risk * 13)
    stats = []
    for row in rows[:4]:
        high_risk = int(row["critical"]) + int(row["high"])
        stats.append(
            f"""<article>
  <strong>{_html(str(row["label"]))}</strong>
  <span>{int(row["count"])} findings, {high_risk} high risk</span>
  <p>{_html(_compact_label(str(row["top_finding"]), 48))}</p>
</article>"""
        )
    return f"""<div class="geo-map-embed">
  <div class="geo-map-frame">
    <div id="geo-risk-map" class="geo-map-canvas" aria-label="Operational risk map"></div>
  </div>
  <div class="geo-stat-list">
    {"".join(stats)}
  </div>
  <script type="application/json" id="geo-risk-map-data">{data_json}</script>
</div>"""


def _leaflet_report_script() -> str:
    return """<script>
(function () {
  function initGeoRiskMap() {
    var mapElement = document.getElementById("geo-risk-map");
    var dataElement = document.getElementById("geo-risk-map-data");
    if (!mapElement || !dataElement || !window.L) {
      return;
    }

    var points = [];
    try {
      points = JSON.parse(dataElement.textContent || "[]");
    } catch (_error) {
      points = [];
    }
    if (!points.length) {
      return;
    }

    var map = L.map(mapElement, {
      attributionControl: false,
      dragging: true,
      maxBounds: [[-60, -125], [36, -32]],
      maxZoom: 6,
      minZoom: 2,
      scrollWheelZoom: false,
      zoomControl: true
    }).setView([-14, -68], 3);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 6,
      minZoom: 2
    }).addTo(map);
    L.control.attribution({ prefix: false }).addAttribution("© OpenStreetMap").addTo(map);

    var group = L.featureGroup().addTo(map);
    points.forEach(function (point) {
      var highRisk = Number(point.critical || 0) + Number(point.high || 0);
      var size = Math.max(18, Math.round(Number(point.radius || 10) * 2));
      var marker = L.marker([point.lat, point.lng], {
        icon: L.divIcon({
          className: "geo-risk-div-marker" + (Number(point.critical || 0) > 0 ? "" : " geo-risk-warning"),
          iconSize: [size, size],
          iconAnchor: [size / 2, size / 2]
        })
      }).addTo(group);
      marker.bindTooltip(
        point.label + ": " + point.count + " findings, " + highRisk + " high risk",
        { direction: "top", opacity: 0.96 }
      );
    });

    if (points.length > 1) {
      map.fitBounds(group.getBounds(), { maxZoom: 4, padding: [44, 44] });
    } else {
      map.setView([points[0].lat, points[0].lng], 4);
    }
    window.setTimeout(function () { map.invalidateSize(); }, 0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGeoRiskMap);
  } else {
    initGeoRiskMap();
  }
})();
</script>"""


def _location_key(country: str, city: str) -> str:
    return f"{country}|{_normalize_location_name(city)}"


def _normalize_location_name(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def _line_series_svg(series: list[dict[str, Any]]) -> str:
    if not series:
        return ""
    width = 720
    height = 270
    plot_x = 70
    plot_y = 28
    plot_width = 560
    plot_height = 160
    colors = ["#bd6b12", "#c73a31", "#1677a8"]
    weeks = ["L3W", "L2W", "L1W", "L0W"]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Trend paths">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#f8fafc" />',
    ]
    for value in [100, 80, 60]:
        y = plot_y + (120 - value) / 70 * plot_height
        parts.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_width}" y2="{y:.1f}" '
            'stroke="#e1e7ee" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{plot_x - 10}" y="{y + 4:.1f}" text-anchor="end" '
            'fill="#6b7280" font-size="11">{value}</text>'
        )
    for index, week in enumerate(weeks):
        x = plot_x + index * (plot_width / (len(weeks) - 1))
        parts.append(
            f'<text x="{x:.1f}" y="{plot_y + plot_height + 24}" text-anchor="middle" '
            f'fill="#6b7280" font-size="12">{week}</text>'
        )
    for index, item in enumerate(series):
        color = colors[index % len(colors)]
        point_attrs = []
        for week, value in item["points"]:
            x = plot_x + weeks.index(week) * (plot_width / (len(weeks) - 1))
            y = plot_y + (120 - float(value)) / 70 * plot_height
            point_attrs.append(f"{x:.1f},{y:.1f}")
        parts.append(
            f'<polyline points="{" ".join(point_attrs)}" fill="none" stroke="{color}" '
            'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        )
        last_x, last_y = point_attrs[-1].split(",")
        parts.append(
            f'<circle cx="{last_x}" cy="{last_y}" r="4" fill="{color}" />'
        )
        parts.append(
            f'<text x="{plot_x}" y="{218 + index * 17}" fill="{color}" font-size="12" '
            f'font-weight="700">{_html(_compact_label(str(item["label"]), 62))}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _paired_index_svg(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    width = 720
    row_height = 50
    plot_x = 232
    plot_width = 350
    value_x = 650
    height = 32 + row_height * len(rows) + 14
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Benchmark index">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#f8fafc" />',
        f'<line x1="{plot_x + plot_width * 100 / 130:.1f}" y1="16" '
        f'x2="{plot_x + plot_width * 100 / 130:.1f}" y2="{height - 12}" '
        'stroke="#cfd7df" stroke-width="1" />',
    ]
    for index, row in enumerate(rows):
        y = 26 + index * row_height
        zone = _safe_float(row["zone"]) or 0
        label = _compact_label(str(row["label"]), 32)
        zone_width = max(4, zone / 130 * plot_width)
        peer_width = 100 / 130 * plot_width
        parts.append(
            f'<text x="16" y="{y + 16}" fill="#27313d" font-size="12" '
            f'font-weight="700">{_html(label)}</text>'
        )
        parts.append(
            f'<rect x="{plot_x}" y="{y + 4}" width="{peer_width:.1f}" height="11" '
            'rx="4" fill="#d4dce5" />'
        )
        parts.append(
            f'<rect x="{plot_x}" y="{y + 20}" width="{zone_width:.1f}" height="14" '
            'rx="5" fill="#1677a8" />'
        )
        parts.append(
            f'<text x="{value_x}" y="{y + 31}" fill="#5f6673" font-size="12" '
            f'font-weight="800" text-anchor="end">{zone:.0f} index</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _scatter_svg(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    width = 720
    height = 270
    plot_x = 70
    plot_y = 30
    plot_width = 540
    plot_height = 170
    max_low_low = max(float(row["low_low"]) for row in rows) or 1
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Correlation quadrant">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="12" fill="#f8fafc" />',
        f'<line x1="{plot_x}" y1="{plot_y + plot_height}" x2="{plot_x + plot_width}" '
        f'y2="{plot_y + plot_height}" stroke="#cfd7df" />',
        f'<line x1="{plot_x + plot_width / 2:.1f}" y1="{plot_y}" '
        f'x2="{plot_x + plot_width / 2:.1f}" y2="{plot_y + plot_height}" stroke="#cfd7df" />',
    ]
    for row in rows:
        corr = float(row["corr"])
        low_low = float(row["low_low"])
        x = plot_x + (corr + 1) / 2 * plot_width
        y = plot_y + (1 - low_low / max_low_low) * plot_height
        color = "#635bff" if corr >= 0 else "#bd6b12"
        radius = 8 + low_low / max_low_low * 12
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            'fill-opacity="0.72" />'
        )
        parts.append(
            f'<text x="{x + radius + 4:.1f}" y="{y + 4:.1f}" fill="#27313d" '
            f'font-size="11">{_html(str(row["label"]))}</text>'
        )
    parts.append(
        f'<text x="{plot_x}" y="{height - 22}" fill="#6b7280" font-size="12">-1.0 correlation</text>'
    )
    parts.append(
        f'<text x="{plot_x + plot_width}" y="{height - 22}" fill="#6b7280" font-size="12" '
        'text-anchor="end">+1.0 correlation</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _number_from_evidence(finding: InsightFinding, key: str) -> float | None:
    return _safe_float(finding.evidence.get(key))


def _zone_metric_label(finding: InsightFinding, *, include_metric: bool = True) -> str:
    zone = str(finding.evidence.get("zone") or "")
    city = str(finding.evidence.get("city") or "")
    metric = str(finding.evidence.get("metric") or "")
    location = ", ".join(part for part in [zone, city] if part)
    if include_metric and metric and location:
        return _compact_label(f"{location} - {metric}", 48)
    return _compact_label(location or finding.title, 48)


def _compact_label(value: str, limit: int = 48) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 1)].rstrip()}..."


def _html(value: Any) -> str:
    return escape(str(value), quote=True)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
