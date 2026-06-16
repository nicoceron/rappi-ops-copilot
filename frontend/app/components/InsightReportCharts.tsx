"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard, ChartContainer, ChartTooltipContent, type ChartConfig } from "./ChartKit";
import type { CategoryKey, Finding, InsightReport, Severity } from "./insightTypes";

type BarDatum = {
  fill: string;
  id: string;
  label: string;
  value: number;
};

const CATEGORY_COLORS: Record<CategoryKey, string> = {
  anomalies: "#ff6b5c",
  worrying_trends: "#f2b76c",
  benchmarking: "#7ec4e3",
  correlations: "#b9a7ff",
  opportunities: "#7eea9b",
};

const SEVERITY_COLORS: Record<Severity, string> = {
  critical: "#ff6b5c",
  high: "#f2b76c",
  medium: "#7ec4e3",
  low: "#7eea9b",
};

const AXIS_TICK = { fill: "rgba(250,250,250,0.62)", fontSize: 11 };
const GRID_STROKE = "rgba(255,255,255,0.08)";

export function InsightReportCharts({ report }: { report: InsightReport }) {
  const categoryData = report.categories.map((category) => ({
    fill: CATEGORY_COLORS[category.key],
    id: category.key,
    label: category.title,
    value: category.findings.length,
  }));
  const severityData = buildSeverityData(report);
  const anomalyData = buildAnomalyData(findingsFor(report, "anomalies"));
  const trendData = buildScoreData(findingsFor(report, "worrying_trends"), {
    color: CATEGORY_COLORS.worrying_trends,
    key: "relative_deterioration",
    percent: true,
  });
  const benchmarkData = buildScoreData(findingsFor(report, "benchmarking"), {
    color: CATEGORY_COLORS.benchmarking,
    key: "underperformance_score",
    percent: true,
  });
  const correlationData = buildScoreData(findingsFor(report, "correlations"), {
    color: CATEGORY_COLORS.correlations,
    key: "pearson_correlation",
    percent: false,
    signed: true,
  });
  const opportunityData = buildScoreData(findingsFor(report, "opportunities"), {
    color: CATEGORY_COLORS.opportunities,
    key: "opportunity_score",
    percent: false,
  });

  return (
    <div className="insight-chart-grid" aria-label="Executive insight charts">
      <ChartCard
        title="Category coverage"
        description="Findings generated for each required insight class."
      >
        <HorizontalBars data={categoryData} formatter={formatInteger} />
      </ChartCard>

      <ChartCard title="Severity mix" description="Risk profile across the automatic report.">
        <HorizontalBars data={severityData} formatter={formatInteger} />
      </ChartCard>

      <ChartCard title="Opportunity ranking" description="Composite intervention score by zone.">
        <HorizontalBars data={opportunityData} formatter={formatScore} />
      </ChartCard>

      <ChartCard title="WoW anomaly impact" description="Signed change after metric direction.">
        <HorizontalBars data={anomalyData} formatter={formatPercent} signed />
      </ChartCard>

      <ChartCard title="3-week deterioration" description="Largest consistent declines to L0W.">
        <HorizontalBars data={trendData} formatter={formatPercent} />
      </ChartCard>

      <ChartCard title="Peer benchmark gaps" description="Distance from same-country/type median.">
        <HorizontalBars data={benchmarkData} formatter={formatPercent} />
      </ChartCard>

      <ChartCard title="Metric correlations" description="Latest-week Pearson relationships.">
        <HorizontalBars data={correlationData} formatter={formatCorrelation} signed />
      </ChartCard>
    </div>
  );
}

function HorizontalBars({
  data,
  formatter,
  signed = false,
}: {
  data: BarDatum[];
  formatter: (value: number) => string;
  signed?: boolean;
}) {
  const config: ChartConfig = {
    value: {
      color: "var(--blue)",
      label: "Value",
      valueFormatter: (value) => (typeof value === "number" ? formatter(value) : "n/a"),
    },
  };

  if (!data.length) {
    return <div className="insight-chart-empty">Not enough structured evidence yet.</div>;
  }

  return (
    <ChartContainer>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 6, right: 18, bottom: 0, left: 8 }}
        >
          <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
          <XAxis
            axisLine={false}
            domain={signed ? ["dataMin", "dataMax"] : [0, "dataMax"]}
            tick={AXIS_TICK}
            tickFormatter={(value) => formatter(Number(value))}
            tickLine={false}
            type="number"
          />
          <YAxis
            axisLine={false}
            dataKey="label"
            interval={0}
            tick={AXIS_TICK}
            tickLine={false}
            type="category"
            width={112}
          />
          {signed ? <ReferenceLine stroke="rgba(255,255,255,0.24)" x={0} /> : null}
          <Tooltip content={<ChartTooltipContent config={config} />} cursor={false} />
          <Bar barSize={15} dataKey="value" radius={[0, 5, 5, 0]}>
            {data.map((item) => (
              <Cell fill={item.fill} key={item.id} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

function buildSeverityData(report: InsightReport): BarDatum[] {
  const findings = report.categories.flatMap((category) => category.findings);
  return (["critical", "high", "medium", "low"] satisfies Severity[]).map((severity) => ({
    fill: SEVERITY_COLORS[severity],
    id: severity,
    label: severity,
    value: findings.filter((finding) => finding.severity === severity).length,
  }));
}

function buildAnomalyData(findings: Finding[]): BarDatum[] {
  return findings
    .slice(0, 6)
    .map((finding) => {
      const change = numberEvidence(finding, "change_score");
      if (change === null) {
        return null;
      }
      const direction = stringEvidence(finding, "direction");
      const impact = direction === "lower_better" ? -change : change;
      return {
        fill: impact >= 0 ? CATEGORY_COLORS.opportunities : CATEGORY_COLORS.anomalies,
        id: finding.id,
        label: findingLabel(finding),
        value: impact,
      };
    })
    .filter(Boolean) as BarDatum[];
}

function buildScoreData(
  findings: Finding[],
  options: { color: string; key: string; percent?: boolean; signed?: boolean },
): BarDatum[] {
  return findings
    .slice(0, 6)
    .map((finding) => {
      const value = numberEvidence(finding, options.key);
      if (value === null) {
        return null;
      }
      return {
        fill: options.signed && value < 0 ? CATEGORY_COLORS.worrying_trends : options.color,
        id: finding.id,
        label:
          options.key === "pearson_correlation"
            ? compactLabel(
                `${stringEvidence(finding, "metric_x") || "Metric A"} / ${
                  stringEvidence(finding, "metric_y") || "Metric B"
                }`,
              )
            : findingLabel(finding, options.key !== "opportunity_score"),
        value,
      };
    })
    .filter(Boolean) as BarDatum[];
}

function findingsFor(report: InsightReport, categoryKey: CategoryKey) {
  return report.categories.find((category) => category.key === categoryKey)?.findings ?? [];
}

function findingLabel(finding: Finding, includeMetric = true) {
  const zone = stringEvidence(finding, "zone");
  const city = stringEvidence(finding, "city");
  const metric = stringEvidence(finding, "metric");
  const location = [zone, city].filter(Boolean).join(", ");
  if (includeMetric && metric && location) {
    return compactLabel(`${location} - ${metric}`);
  }
  return compactLabel(location || finding.title);
}

function compactLabel(value: string, maxLength = 28) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  return cleaned.length > maxLength ? `${cleaned.slice(0, maxLength - 1).trim()}...` : cleaned;
}

function numberEvidence(finding: Finding, key: string) {
  const value = finding.evidence?.[key];
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringEvidence(finding: Finding, key: string) {
  const value = finding.evidence?.[key];
  return typeof value === "string" ? value : "";
}

function formatInteger(value: number) {
  return value.toLocaleString();
}

function formatPercent(value: number) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatScore(value: number) {
  return value.toFixed(2);
}

function formatCorrelation(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}
