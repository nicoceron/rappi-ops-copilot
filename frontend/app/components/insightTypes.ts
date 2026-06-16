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

export type AuthoredReportFinding = {
  finding_id: string;
  headline: string;
  insight: string;
  recommendation: string;
};

export type AuthoredReportSection = {
  key: CategoryKey;
  title: string;
  narrative: string;
  findings: AuthoredReportFinding[];
};

export type AuthoredInsightReport = {
  title: string;
  subtitle: string;
  opening_note: string;
  executive_summary: AuthoredReportFinding[];
  sections: AuthoredReportSection[];
  closing_note?: string;
};

export type InsightReport = {
  report_id: string;
  generated_at: string;
  source: string;
  period_label: string;
  executive_summary: Finding[];
  categories: InsightCategory[];
  authored_report?: AuthoredInsightReport | null;
  data_quality?: Record<string, unknown>;
  data_caveats?: string[];
};
