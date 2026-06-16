export type CategoryKey =
  | "anomalies"
  | "worrying_trends"
  | "benchmarking"
  | "correlations"
  | "opportunities";

export type Severity = "critical" | "high" | "medium" | "low";

export type Finding = {
  id: string;
  category: CategoryKey;
  severity: Severity;
  title: string;
  summary: string;
  recommendation: string;
  evidence: Record<string, unknown>;
};

export type InsightCategory = {
  key: CategoryKey;
  title: string;
  findings: Finding[];
};

export type InsightReport = {
  report_id: string;
  generated_at: string;
  source: string;
  period_label: string;
  executive_summary: Finding[];
  categories: InsightCategory[];
  data_caveats?: string[];
};
