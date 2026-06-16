"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Download,
  FileCheck2,
  GitCompareArrows,
  Info,
  ListChecks,
  Loader2,
  Network,
  RefreshCw,
  Target,
  TrendingDown,
  Workflow,
} from "lucide-react";
import { InsightReportCharts } from "./InsightReportCharts";
import type { CategoryKey, Finding, InsightReport, Severity } from "./insightTypes";

const DEFAULT_API_URL = "http://localhost:8000";
const FINDING_LIMIT_PER_CATEGORY = 8;

const categoryIcons = {
  anomalies: AlertTriangle,
  worrying_trends: TrendingDown,
  benchmarking: GitCompareArrows,
  correlations: Network,
  opportunities: Target,
} satisfies Record<CategoryKey, typeof AlertTriangle>;

const severityOrder: Severity[] = ["critical", "high", "medium", "low"];
const severityShortLabels = {
  critical: "Crit",
  high: "High",
  medium: "Med",
  low: "Low",
} satisfies Record<Severity, string>;

const evidenceLabels: Record<string, string> = {
  avg_metric_risk: "Avg risk",
  change_score: "Change",
  city: "City",
  country: "Country",
  current_value: "Current",
  current_value_label: "Current",
  gap_score: "Gap score",
  gap_value: "Gap",
  low_low_count: "Low-low zones",
  max_deterioration_pct: "Max deterioration",
  metric: "Metric",
  metric_x: "Metric X",
  metric_y: "Metric Y",
  opportunity_score: "Opportunity score",
  pearson_correlation: "Correlation",
  peer_median: "Peer median",
  peer_median_label: "Peer median",
  peer_n: "Peer count",
  previous_value: "Previous",
  relative_deterioration: "Deterioration",
  trend_count: "Trend count",
  underperformance_score: "Underperformance",
  values: "Trend path",
  weak_metrics: "Weak metrics",
  zone: "Zone",
  zone_prioritization: "Priority",
  zone_type: "Zone type",
};

const preferredEvidenceKeys: Record<CategoryKey, string[]> = {
  anomalies: [
    "country",
    "city",
    "zone",
    "metric",
    "previous_value",
    "current_value",
    "change_score",
  ],
  worrying_trends: ["country", "city", "zone", "metric", "values", "relative_deterioration"],
  benchmarking: [
    "country",
    "city",
    "zone",
    "zone_type",
    "metric",
    "current_value_label",
    "peer_median_label",
    "underperformance_score",
  ],
  correlations: [
    "metric_x",
    "metric_y",
    "pearson_correlation",
    "low_low_count",
    "n_zones",
  ],
  opportunities: [
    "country",
    "city",
    "zone",
    "zone_type",
    "opportunity_score",
    "trend_count",
    "weak_metrics",
  ],
};

export function ExecutiveInsights() {
  const apiBase = useMemo(
    () => (process.env.NEXT_PUBLIC_OPS_API_URL || DEFAULT_API_URL).replace(/\/$/, ""),
    [],
  );
  const [report, setReport] = useState<InsightReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadReport = useMemo(
    () => async (options?: { showInitialLoading?: boolean }) => {
      if (options?.showInitialLoading) {
        setLoading(true);
      }
      setRefreshing(!options?.showInitialLoading);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/insights/latest`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        setReport((await response.json()) as InsightReport);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load report");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [apiBase],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadInitialReport() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/insights/latest`, { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`API returned ${response.status}`);
        }
        const payload = (await response.json()) as InsightReport;
        if (!cancelled) {
          setReport(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load report");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadInitialReport();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  async function refreshReport() {
    await loadReport();
  }

  return (
    <section className="report-panel" aria-label="Automatic executive insights">
      <div className="report-header">
        <div>
          <p className="eyebrow">Automatic insights</p>
          <h2>Executive report</h2>
        </div>
        <div className="report-actions">
          <button type="button" onClick={refreshReport} disabled={refreshing}>
            {refreshing ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
            Reload
          </button>
          <a href={`${apiBase}/insights/latest.pdf`} target="_blank" rel="noreferrer">
            <Download size={16} />
            PDF
            <ArrowUpRight size={14} />
          </a>
        </div>
      </div>

      {loading ? (
        <div className="report-state">Loading latest report...</div>
      ) : error ? (
        <div className="report-state report-error">{error}</div>
      ) : report ? (
        <div className="report-scroll">
          <ReportOverview report={report} />

          <ExecutiveSummary findings={report.executive_summary} />

          <InsightReportCharts report={report} />

          <CategoryDetail report={report} />

          <DataCaveats caveats={report.data_caveats ?? []} />
        </div>
      ) : (
        <div className="report-state">No report available.</div>
      )}
    </section>
  );
}

function ReportOverview({ report }: { report: InsightReport }) {
  const totalFindings = report.categories.reduce(
    (total, category) => total + category.findings.length,
    0,
  );
  const severityCounts = report.categories
    .flatMap((category) => category.findings)
    .reduce(
      (counts, finding) => {
        counts[finding.severity] += 1;
        return counts;
      },
      { critical: 0, high: 0, medium: 0, low: 0 } satisfies Record<Severity, number>,
    );
  const sourceLabel = formatSource(report.source);

  return (
    <div className="report-overview" aria-label="Report run metadata">
      <div className="report-run-card report-run-primary">
        <div>
          <span className="run-card-icon">
            <Workflow size={17} />
          </span>
          <p>Source</p>
        </div>
        <strong>{sourceLabel}</strong>
        <small>{report.report_id.slice(0, 8)}</small>
      </div>

      <div className="report-run-card">
        <div>
          <span className="run-card-icon">
            <Clock3 size={17} />
          </span>
          <p>Generated</p>
        </div>
        <strong>{formatDateTime(report.generated_at)}</strong>
        <small>{report.period_label}</small>
      </div>

      <div className="report-run-card">
        <div>
          <span className="run-card-icon">
            <FileCheck2 size={17} />
          </span>
          <p>Findings</p>
        </div>
        <strong>{totalFindings}</strong>
        <small>{report.categories.length} categories covered</small>
      </div>

      <div className="severity-overview">
        {severityOrder.map((severity) => (
          <div className="severity-count" key={severity}>
            <span className={`severity-dot-inline severity-${severity}`} />
            <strong>{severityCounts[severity]}</strong>
            <small>{severityShortLabels[severity]}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExecutiveSummary({ findings }: { findings: Finding[] }) {
  return (
    <section className="executive-summary-section" aria-label="Executive summary">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Top findings</p>
          <h3>Executive summary</h3>
        </div>
        <span>{findings.length} top findings</span>
      </div>
      <div className="summary-strip">
        {findings.slice(0, 5).map((finding, index) => (
          <article className="summary-item" key={finding.id}>
            <span className={`severity-dot severity-${finding.severity}`} />
            <span className="summary-rank">{index + 1}</span>
            <strong>{finding.title}</strong>
            <p>{finding.summary}</p>
            <small>{finding.recommendation}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function CategoryDetail({ report }: { report: InsightReport }) {
  return (
    <section className="category-detail-section" aria-label="Insight detail by category">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Required categories</p>
          <h3>Insight detail</h3>
        </div>
        <span>
          {report.categories.reduce((total, category) => total + category.findings.length, 0)}{" "}
          findings
        </span>
      </div>

      <div className="category-grid">
        {report.categories.map((category) => {
          const Icon = categoryIcons[category.key];
          const displayedFindings = category.findings.slice(0, FINDING_LIMIT_PER_CATEGORY);
          return (
            <section className="category-block" key={category.key}>
              <div className="category-heading">
                <Icon size={17} />
                <strong>{category.title}</strong>
                <span>{category.findings.length}</span>
              </div>
              <div className="finding-list">
                {displayedFindings.map((finding) => (
                  <FindingRow finding={finding} key={finding.id} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const highlights = evidenceHighlights(finding);

  return (
    <article className="finding-row">
      <div className="finding-title-row">
        <span className={`severity-label severity-${finding.severity}`}>{finding.severity}</span>
        <strong>{finding.title}</strong>
      </div>
      <p>{finding.summary}</p>
      <div className="finding-action">
        <CheckCircle2 size={15} />
        <span>{finding.recommendation}</span>
      </div>
      {highlights.length > 0 ? (
        <dl className="evidence-grid" aria-label="Finding evidence">
          {highlights.map((item) => (
            <div key={item.key}>
              <dt>{item.label}</dt>
              <dd>{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

function DataCaveats({ caveats }: { caveats: string[] }) {
  if (!caveats.length) {
    return null;
  }

  return (
    <section className="data-caveats" aria-label="Data caveats">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Caveats</p>
          <h3>Data notes</h3>
        </div>
        <Info size={17} />
      </div>
      <ul>
        {caveats.map((caveat) => (
          <li key={caveat}>
            <ListChecks size={15} />
            <span>{caveat}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function evidenceHighlights(finding: Finding) {
  const evidence = finding.evidence ?? {};
  const preferred = preferredEvidenceKeys[finding.category] ?? [];
  const selected = preferred
    .map((key) => [key, evidence[key]] as const)
    .filter(([, value]) => isRenderableEvidence(value));

  if (selected.length < 6) {
    for (const [key, value] of Object.entries(evidence)) {
      if (selected.some(([selectedKey]) => selectedKey === key) || !isRenderableEvidence(value)) {
        continue;
      }
      selected.push([key, value]);
      if (selected.length >= 6) {
        break;
      }
    }
  }

  return selected.slice(0, 6).map(([key, value]) => ({
    key,
    label: evidenceLabels[key] ?? titleize(key),
    value: formatEvidenceValue(key, value),
  }));
}

function isRenderableEvidence(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return false;
  }
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length > 0;
  }
  return true;
}

function formatEvidenceValue(key: string, value: unknown): string {
  if (typeof value === "number") {
    return formatNumber(value);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    if (key === "weak_metrics") {
      return value
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }
          const metric = (item as Record<string, unknown>).metric;
          const metricValue = (item as Record<string, unknown>).value;
          return typeof metric === "string"
            ? `${metric}${typeof metricValue === "number" ? ` ${formatNumber(metricValue)}` : ""}`
            : null;
        })
        .filter(Boolean)
        .slice(0, 3)
        .join(", ");
    }
    return `${value.length} items`;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const weekEntries = ["L3W", "L2W", "L1W", "L0W"]
      .filter((week) => typeof record[week] === "number")
      .map((week) => `${week} ${formatNumber(record[week] as number)}`);
    if (weekEntries.length) {
      return weekEntries.join(" -> ");
    }
    return Object.entries(record)
      .slice(0, 3)
      .map(
        ([entryKey, entryValue]) =>
          `${titleize(entryKey)} ${formatEvidenceValue(entryKey, entryValue)}`,
      )
      .join(", ");
  }
  return String(value);
}

function formatNumber(value: number) {
  const absolute = Math.abs(value);
  const maximumFractionDigits = absolute >= 100 ? 0 : absolute >= 10 ? 1 : absolute >= 1 ? 2 : 3;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits,
    signDisplay: value < 0 ? "auto" : "never",
  }).format(value);
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatSource(source: string) {
  return source.replaceAll("_", " ");
}

function titleize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
