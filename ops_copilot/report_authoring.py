from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Literal

from pydantic import ValidationError

from ops_copilot.insights import (
    AuthoredInsightReport,
    AuthoredReportFinding,
    AuthoredReportSection,
    InsightCategory,
    InsightFinding,
    InsightReport,
)


ReportAuthoringMode = Literal["auto", "deterministic", "llm"]


class ReportAuthoringError(RuntimeError):
    """Raised when the LLM narrative layer cannot be generated."""


def author_report_with_deepseek(report: InsightReport) -> AuthoredInsightReport:
    """Ask DeepSeek for a structured narrative layer over deterministic findings."""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ReportAuthoringError("DEEPSEEK_API_KEY is not configured.")

    prompt = _authoring_prompt(report)
    payload = {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write concise executive operations reports for Rappi. "
                    "You only use the evidence provided by the analytics system. "
                    "Return strict JSON only. Do not write LaTeX, Markdown, or prose outside JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise ReportAuthoringError(f"DeepSeek report authoring failed: {detail}") from exc
    except Exception as exc:
        raise ReportAuthoringError(f"DeepSeek report authoring failed: {exc}") from exc

    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ReportAuthoringError(
            "DeepSeek report authoring returned an unexpected response."
        ) from exc

    try:
        authored = AuthoredInsightReport.model_validate_json(_extract_json(str(content)))
    except (ValidationError, ValueError) as exc:
        raise ReportAuthoringError(
            f"DeepSeek report authoring returned invalid JSON: {exc}"
        ) from exc

    return normalize_authored_report(report, authored)


def normalize_authored_report(
    report: InsightReport, authored: AuthoredInsightReport
) -> AuthoredInsightReport:
    """Keep the model's prose but force finding/category references back to known evidence."""

    findings_by_id = _findings_by_id(report)
    category_findings = {
        category.key: {finding.id for finding in category.findings}
        for category in report.categories
    }

    summary_items = [
        _clean_authored_finding(item, findings_by_id[item.finding_id])
        for item in authored.executive_summary
        if item.finding_id in findings_by_id
    ]
    if not summary_items:
        summary_items = [
            _fallback_authored_finding(finding)
            for finding in report.executive_summary[:5]
        ]

    sections_by_key = {section.key: section for section in authored.sections}
    sections: list[AuthoredReportSection] = []
    for category in report.categories:
        source_section = sections_by_key.get(category.key)
        allowed_ids = category_findings[category.key]
        source_findings = source_section.findings if source_section else []
        section_findings = [
            _clean_authored_finding(item, findings_by_id[item.finding_id])
            for item in source_findings
            if item.finding_id in allowed_ids and item.finding_id in findings_by_id
        ]
        if not section_findings:
            section_findings = [
                _fallback_authored_finding(finding)
                for finding in category.findings[:3]
            ]
        sections.append(
            AuthoredReportSection(
                key=category.key,
                title=_clean_text(source_section.title if source_section else category.title)
                or category.title,
                narrative=(
                    _clean_text(source_section.narrative if source_section else "")
                    or _fallback_section_narrative(category)
                ),
                findings=section_findings,
            )
        )

    return AuthoredInsightReport(
        title=_clean_text(authored.title) or "Rappi Ops Executive Insight Report",
        subtitle=_clean_text(authored.subtitle) or report.period_label,
        opening_note=_clean_text(authored.opening_note)
        or (
            "This report summarizes the highest-priority operating signals from the "
            "latest data refresh."
        ),
        executive_summary=summary_items[:5],
        sections=sections,
        closing_note=_clean_text(authored.closing_note),
    )


def fallback_authored_report(report: InsightReport) -> AuthoredInsightReport:
    return normalize_authored_report(
        report,
        AuthoredInsightReport(
            subtitle=report.period_label,
            opening_note=(
                "This report summarizes the highest-priority operating signals from the latest "
                "deterministic analytics run."
            ),
            executive_summary=[
                _fallback_authored_finding(finding)
                for finding in report.executive_summary[:5]
            ],
            sections=[
                AuthoredReportSection(
                    key=category.key,
                    title=category.title,
                    narrative=_fallback_section_narrative(category),
                    findings=[
                        _fallback_authored_finding(finding)
                        for finding in category.findings[:3]
                    ],
                )
                for category in report.categories
            ],
        ),
    )


def _authoring_prompt(report: InsightReport) -> str:
    factsheet = _factsheet(report)
    schema = AuthoredInsightReport.model_json_schema()
    business_context = os.getenv(
        "INSIGHTS_BUSINESS_CONTEXT",
        (
            "Rappi Ops Copilot is an internal operations analytics workflow. "
            "L0W is the latest available week. L1W-L8W are relative historical weeks. "
            "The report audience is operations leadership reviewing zones, countries, "
            "city-level execution, KPI anomalies, trend deterioration, benchmark gaps, "
            "metric correlations, and intervention opportunities."
        ),
    )
    return (
        "Create the narrative JSON layer for an executive operations report.\n\n"
        "Rules:\n"
        "- Return one JSON object that validates against the provided JSON Schema.\n"
        "- Do not generate LaTeX. The application renders LaTeX from your JSON.\n"
        "- Use only the provided finding_id values. Do not create new IDs.\n"
        "- Do not invent numbers, countries, cities, zones, metric names, or causal claims.\n"
        "- If you quote a number, use a number already present in the finding summary "
        "or evidence.\n"
        "- Keep the tone direct and operational. Avoid generic filler.\n"
        "- Include 3-5 executive_summary items and one section for each category key.\n"
        "- Each section should include 1-3 findings from that section's provided findings.\n\n"
        f"Business context:\n{business_context}\n\n"
        f"JSON Schema:\n{json.dumps(schema, ensure_ascii=True)}\n\n"
        f"Factsheet:\n{json.dumps(factsheet, ensure_ascii=True, indent=2)}\n"
    )


def _factsheet(report: InsightReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "period_label": report.period_label,
        "generated_at": report.generated_at,
        "source": report.source,
        "data_quality": report.data_quality,
        "data_caveats": report.data_caveats,
        "executive_summary_finding_ids": [finding.id for finding in report.executive_summary],
        "categories": [
            {
                "key": category.key,
                "title": category.title,
                "findings": [_finding_payload(finding) for finding in category.findings[:5]],
            }
            for category in report.categories
        ],
    }


def _finding_payload(finding: InsightFinding) -> dict[str, Any]:
    return {
        "finding_id": finding.id,
        "category": finding.category,
        "severity": finding.severity,
        "title": finding.title,
        "summary": finding.summary,
        "recommendation": finding.recommendation,
        "evidence": _compact_evidence(finding.evidence),
    }


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = [
        "country",
        "city",
        "zone",
        "zone_type",
        "zone_prioritization",
        "metric",
        "previous_week",
        "current_week",
        "previous_value",
        "current_value",
        "delta",
        "change_score",
        "direction",
        "values",
        "relative_deterioration",
        "peer_median",
        "peer_n",
        "gap_value",
        "underperformance_score",
        "current_value_label",
        "peer_median_label",
        "metric_x",
        "metric_y",
        "pearson_correlation",
        "n_zones",
        "low_low_count",
        "low_low_examples",
        "opportunity_score",
        "avg_metric_risk",
        "max_deterioration_pct",
        "trend_count",
        "weak_metrics",
    ]
    return {key: evidence[key] for key in allowed_keys if key in evidence}


def _extract_json(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    if "```" in stripped:
        for part in stripped.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[len("json") :].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise ValueError("No JSON object found in model response.")


def _findings_by_id(report: InsightReport) -> dict[str, InsightFinding]:
    return {
        finding.id: finding
        for category in report.categories
        for finding in category.findings
    }


def _clean_authored_finding(
    item: AuthoredReportFinding, source: InsightFinding
) -> AuthoredReportFinding:
    return AuthoredReportFinding(
        finding_id=source.id,
        headline=_clean_text(item.headline) or source.title,
        insight=_clean_text(item.insight) or source.summary,
        recommendation=_clean_text(item.recommendation) or source.recommendation,
    )


def _fallback_authored_finding(finding: InsightFinding) -> AuthoredReportFinding:
    return AuthoredReportFinding(
        finding_id=finding.id,
        headline=finding.title,
        insight=finding.summary,
        recommendation=finding.recommendation,
    )


def _fallback_section_narrative(category: InsightCategory) -> str:
    if not category.findings:
        return (
            f"No material {category.title.lower()} findings were detected with the "
            "current thresholds."
        )
    return (
        f"{category.title} contains {len(category.findings)} material finding"
        f"{'' if len(category.findings) == 1 else 's'} from the latest analytics run."
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())
