"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  FileText,
  GitCompareArrows,
  Loader2,
  Network,
  RefreshCw,
  Target,
  TrendingDown,
} from "lucide-react";
import { InsightReportCharts } from "./InsightReportCharts";
import type { CategoryKey, InsightReport } from "./insightTypes";

const DEFAULT_API_URL = "http://localhost:8000";

const categoryIcons = {
  anomalies: AlertTriangle,
  worrying_trends: TrendingDown,
  benchmarking: GitCompareArrows,
  correlations: Network,
  opportunities: Target,
} satisfies Record<CategoryKey, typeof AlertTriangle>;

export function ExecutiveInsights() {
  const apiBase = useMemo(
    () => (process.env.NEXT_PUBLIC_OPS_API_URL || DEFAULT_API_URL).replace(/\/$/, ""),
    [],
  );
  const [report, setReport] = useState<InsightReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadReport() {
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

    loadReport();
    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  async function refreshReport() {
    setRefreshing(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/insights/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: "nextjs_manual_refresh", persist: true }),
      });
      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }
      setReport((await response.json()) as InsightReport);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not refresh report");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
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
            Refresh
          </button>
          <a href={`${apiBase}/insights/latest.md`} target="_blank" rel="noreferrer">
            <FileText size={16} />
            Markdown
            <ArrowUpRight size={14} />
          </a>
          <a href={`${apiBase}/insights/latest.html`} target="_blank" rel="noreferrer">
            <FileText size={16} />
            HTML
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
          <div className="report-meta">
            <span>{formatGeneratedAt(report.generated_at)}</span>
            <span>{report.source}</span>
            <span>{report.period_label}</span>
          </div>

          <InsightReportCharts report={report} />

          <div className="summary-strip">
            {report.executive_summary.slice(0, 5).map((finding) => (
              <article className="summary-item" key={finding.id}>
                <span className={`severity-dot severity-${finding.severity}`} />
                <strong>{finding.title}</strong>
                <p>{finding.recommendation}</p>
              </article>
            ))}
          </div>

          <div className="category-grid">
            {report.categories.map((category) => {
              const Icon = categoryIcons[category.key];
              return (
                <section className="category-block" key={category.key}>
                  <div className="category-heading">
                    <Icon size={17} />
                    <strong>{category.title}</strong>
                    <span>{category.findings.length}</span>
                  </div>
                  <div className="finding-list">
                    {category.findings.slice(0, 3).map((finding) => (
                      <article className="finding-row" key={finding.id}>
                        <div>
                          <span className={`severity-label severity-${finding.severity}`}>
                            {finding.severity}
                          </span>
                          <strong>{finding.title}</strong>
                        </div>
                        <p>{finding.summary}</p>
                        <small>{finding.recommendation}</small>
                      </article>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="report-state">No report available.</div>
      )}
    </section>
  );
}

function formatGeneratedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
