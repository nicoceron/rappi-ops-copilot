"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { Map as LeafletMap } from "leaflet";
import { ChartCard, ChartContainer, ChartTooltipContent, type ChartConfig } from "./ChartKit";
import type { CategoryKey, Finding, InsightReport } from "./insightTypes";

type BarDatum = {
  fill: string;
  id: string;
  label: string;
  value: number;
};

type BenchmarkDatum = {
  currentValue: string;
  gapValue: string;
  id: string;
  label: string;
  peerMedian: string;
  value: number;
};

type CorrelationDatum = {
  corr: number;
  fill: string;
  id: string;
  label: string;
  lowLow: number;
  zones: number | null;
};

type GeoDatum = {
  code: string;
  count: number;
  critical: number;
  high: number;
  id: string;
  lat: number;
  label: string;
  lng: number;
  risk: number;
  topFinding: string;
};

type OpportunityDatum = {
  fill: string;
  id: string;
  label: string;
  weakMetrics: string[];
  value: number;
};

type TrendSeries = {
  color: string;
  id: string;
  label: string;
  values: Record<WeekKey, number>;
};

type TrendPoint = {
  week: WeekKey;
} & Record<string, number | string>;

type TooltipPayload<T> = Array<{ payload?: T }>;

type WeekKey = "L3W" | "L2W" | "L1W" | "L0W";

const WEEK_KEYS: WeekKey[] = ["L3W", "L2W", "L1W", "L0W"];

const CATEGORY_COLORS: Record<CategoryKey, string> = {
  anomalies: "#ff6b5c",
  worrying_trends: "#f2b76c",
  benchmarking: "#7ec4e3",
  correlations: "#b9a7ff",
  opportunities: "#7eea9b",
};

const AXIS_TICK = { fill: "rgba(250,250,250,0.62)", fontSize: 11 };
const GRID_STROKE = "rgba(255,255,255,0.08)";
const MUTED_STROKE = "rgba(255,255,255,0.24)";

const COUNTRY_POINTS: Record<string, { label: string; lat: number; lng: number }> = {
  AR: { label: "Argentina", lat: -38.4, lng: -63.6 },
  BR: { label: "Brazil", lat: -14.2, lng: -51.9 },
  CL: { label: "Chile", lat: -35.7, lng: -71.5 },
  CO: { label: "Colombia", lat: 4.6, lng: -74.1 },
  CR: { label: "Costa Rica", lat: 9.9, lng: -84.1 },
  EC: { label: "Ecuador", lat: -1.8, lng: -78.2 },
  MX: { label: "Mexico", lat: 23.6, lng: -102.5 },
  PE: { label: "Peru", lat: -9.2, lng: -75.0 },
  UY: { label: "Uruguay", lat: -32.5, lng: -55.8 },
};

const CITY_POINTS: Record<string, { label: string; lat: number; lng: number }> = {
  "AR|buenos aires": { label: "Buenos Aires", lat: -34.6037, lng: -58.3816 },
  "BR|belo horizonte": { label: "Belo Horizonte", lat: -19.9167, lng: -43.9345 },
  "BR|campinas": { label: "Campinas", lat: -22.9056, lng: -47.0608 },
  "BR|cascavel": { label: "Cascavel", lat: -24.9555, lng: -53.4552 },
  "BR|jundiai": { label: "Jundiai", lat: -23.1857, lng: -46.8978 },
  "BR|mogi das cruzes": { label: "Mogi das Cruzes", lat: -23.5204, lng: -46.1859 },
  "BR|natal": { label: "Natal", lat: -5.7793, lng: -35.2009 },
  "BR|porto alegre": { label: "Porto Alegre", lat: -30.0346, lng: -51.2177 },
  "BR|rio de janeiro": { label: "Rio de Janeiro", lat: -22.9068, lng: -43.1729 },
  "CL|rancagua": { label: "Rancagua", lat: -34.1708, lng: -70.7406 },
  "CO|duitama": { label: "Duitama", lat: 5.8269, lng: -73.0203 },
  "CO|florencia": { label: "Florencia", lat: 1.6144, lng: -75.6062 },
  "CR|alajuela": { label: "Alajuela", lat: 10.0163, lng: -84.2116 },
  "CR|cartago": { label: "Cartago", lat: 9.8644, lng: -83.9194 },
  "CR|san jose": { label: "San Jose", lat: 9.9281, lng: -84.0907 },
  "EC|machala": { label: "Machala", lat: -3.2581, lng: -79.9554 },
  "MX|ciudad guzman": { label: "Ciudad Guzman", lat: 19.7047, lng: -103.4617 },
  "MX|cordoba": { label: "Cordoba", lat: 18.8847, lng: -96.9256 },
  "MX|orizaba": { label: "Orizaba", lat: 18.8499, lng: -97.1036 },
  "MX|san cristobal de las casas": {
    label: "San Cristobal de las Casas",
    lat: 16.737,
    lng: -92.6376,
  },
  "MX|tecate": { label: "Tecate", lat: 32.5668, lng: -116.6251 },
  "PE|ica": { label: "Ica", lat: -14.0678, lng: -75.7286 },
  "PE|mancora": { label: "Mancora", lat: -4.1078, lng: -81.0475 },
};

export function InsightReportCharts({ report }: { report: InsightReport }) {
  const geoData = buildGeoData(report);
  const anomalyData = buildAnomalyData(findingsFor(report, "anomalies"));
  const trendSeries = buildTrendSeries(findingsFor(report, "worrying_trends"));
  const benchmarkData = buildBenchmarkData(findingsFor(report, "benchmarking"));
  const correlationData = buildCorrelationData(findingsFor(report, "correlations"));
  const opportunityData = buildOpportunityData(findingsFor(report, "opportunities"));

  return (
    <div className="insight-command-center" aria-label="Executive insight charts">
      <div className="insight-chart-grid">
        <ChartCard
          className="chart-wide"
          title="Operational risk map"
          description="Real map tiles with city-level risk markers where coordinates are available."
        >
          <GeoRiskMap data={geoData} />
        </ChartCard>

        <ChartCard
          title="Opportunity scores"
          description="Top intervention candidates. Higher score is more urgent."
        >
          <OpportunityScores data={opportunityData} />
        </ChartCard>

        <ChartCard
          title="WoW anomaly score"
          description="Direction-adjusted change score. Positive is favorable."
        >
          <HorizontalBars
            data={anomalyData}
            formatter={formatSignedScore}
            signed
            valueLabel="Impact score"
          />
        </ChartCard>

        <ChartCard
          className="chart-wide"
          title="Worrying trend paths"
          description="Normalized health index for 3+ consecutive weeks of deterioration."
        >
          <TrendLineChart series={trendSeries} />
        </ChartCard>

        <ChartCard
          title="Peer benchmark gaps"
          description="Normalized underperformance versus same-country/type peers. Higher is worse."
        >
          <BenchmarkGapChart data={benchmarkData} />
        </ChartCard>

        <ChartCard
          title="Metric correlations"
          description="Correlation strength versus low-low zone concentration."
        >
          <CorrelationScatter data={correlationData} />
        </ChartCard>
      </div>
    </div>
  );
}

function GeoRiskMap({ data }: { data: GeoDatum[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const dataKey = useMemo(
    () => data.map((item) => `${item.id}:${item.risk}:${item.count}`).join("|"),
    [data],
  );

  useEffect(() => {
    let disposed = false;

    async function mountMap() {
      if (!containerRef.current || !data.length) {
        return;
      }

      const L = await import("leaflet");
      if (disposed || !containerRef.current) {
        return;
      }

      mapRef.current?.remove();

      const map = L.map(containerRef.current, {
        attributionControl: false,
        dragging: true,
        maxBounds: [
          [-60, -125],
          [36, -32],
        ],
        maxZoom: 6,
        minZoom: 2,
        scrollWheelZoom: false,
        zoomControl: true,
      }).setView([-14, -68], 3);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 6,
        minZoom: 2,
      }).addTo(map);

      L.control.attribution({ prefix: false }).addAttribution("© OpenStreetMap").addTo(map);

      const maxRisk = Math.max(...data.map((item) => item.risk), 1);
      const markerLayers = data.map((item) => {
        const highRisk = item.critical + item.high;
        const color = item.critical > 0 ? CATEGORY_COLORS.anomalies : CATEGORY_COLORS.worrying_trends;
        const marker = L.circleMarker([item.lat, item.lng], {
          color: "rgba(255,255,255,0.86)",
          fillColor: color,
          fillOpacity: 0.74,
          opacity: 1,
          radius: 8 + (item.risk / maxRisk) * 14,
          weight: 1.4,
        });

        const tooltip = document.createElement("div");
        tooltip.className = "geo-map-tooltip";
        tooltip.textContent = `${item.label}: ${item.count} findings, ${highRisk} high risk`;
        marker.bindTooltip(tooltip, { direction: "top", opacity: 0.96 });
        return marker;
      });

      const markerGroup = L.featureGroup(markerLayers).addTo(map);
      if (markerLayers.length > 1) {
        map.fitBounds(markerGroup.getBounds(), { maxZoom: 4, padding: [44, 44] });
      } else if (data[0]) {
        map.setView([data[0].lat, data[0].lng], 4);
      }

      mapRef.current = map;
      window.setTimeout(() => map.invalidateSize(), 0);
    }

    mountMap();

    return () => {
      disposed = true;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [data, dataKey]);

  if (!data.length) {
    return <EmptyChart />;
  }

  return (
    <div className="geo-map-shell" aria-label="City-level risk map">
      <div className="geo-map" ref={containerRef} role="img" aria-label="Operational risk map" />
      <div className="geo-risk-list">
        {data.slice(0, 4).map((item) => (
          <article key={item.id}>
            <strong>{item.label}</strong>
            <span>
              {item.count} findings, {item.critical + item.high} high risk
            </span>
            <p>{item.topFinding}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function HorizontalBars({
  data,
  formatter,
  signed = false,
  valueLabel = "Value",
}: {
  data: BarDatum[];
  formatter: (value: number) => string;
  signed?: boolean;
  valueLabel?: string;
}) {
  const config: ChartConfig = {
    value: {
      color: "var(--blue)",
      label: valueLabel,
      valueFormatter: (value) => (typeof value === "number" ? formatter(value) : "n/a"),
    },
  };

  if (!data.length) {
    return <EmptyChart />;
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
          {signed ? <ReferenceLine stroke={MUTED_STROKE} x={0} /> : null}
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

function TrendLineChart({ series }: { series: TrendSeries[] }) {
  if (!series.length) {
    return <EmptyChart />;
  }

  const data = WEEK_KEYS.map((week) => {
    const point: TrendPoint = { week };
    for (const item of series) {
      point[item.id] = item.values[week];
    }
    return point;
  });
  const config = Object.fromEntries(
    series.map((item) => [
      item.id,
      {
        color: item.color,
        label: item.label,
        valueFormatter: (value: unknown) =>
          typeof value === "number" ? formatIndex(value) : "n/a",
      },
    ]),
  ) as ChartConfig;

  return (
    <ChartContainer>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} />
          <XAxis axisLine={false} dataKey="week" tick={AXIS_TICK} tickLine={false} />
          <YAxis
            axisLine={false}
            domain={[0, 125]}
            tick={AXIS_TICK}
            tickFormatter={(value) => formatIndex(Number(value))}
            tickLine={false}
            width={48}
          />
          <ReferenceLine stroke={MUTED_STROKE} y={100} />
          <Tooltip content={<ChartTooltipContent config={config} />} />
          {series.map((item) => (
            <Line
              activeDot={{ r: 5 }}
              dataKey={item.id}
              dot={{ r: 3 }}
              key={item.id}
              name={item.label}
              stroke={item.color}
              strokeWidth={2.5}
              type="monotone"
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

function BenchmarkGapChart({ data }: { data: BenchmarkDatum[] }) {
  if (!data.length) {
    return <EmptyChart />;
  }

  return (
    <ChartContainer>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          barGap={3}
          data={data}
          layout="vertical"
          margin={{ top: 6, right: 18, bottom: 0, left: 8 }}
        >
          <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
          <XAxis
            axisLine={false}
            domain={[0, "dataMax"]}
            tick={AXIS_TICK}
            tickFormatter={(value) => formatScore(Number(value))}
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
          <Tooltip content={<BenchmarkGapTooltip />} cursor={false} />
          <Bar barSize={15} dataKey="value" fill={CATEGORY_COLORS.benchmarking} radius={[0, 5, 5, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

function BenchmarkGapTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload<BenchmarkDatum>;
}) {
  const item = payload?.[0]?.payload;
  if (!active || !item) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{item.label}</div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: CATEGORY_COLORS.benchmarking }} />
        <span className="chart-tooltip-name">Gap score</span>
        <span className="chart-tooltip-value">{formatScore(item.value)}</span>
      </div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: CATEGORY_COLORS.anomalies }} />
        <span className="chart-tooltip-name">Zone value</span>
        <span className="chart-tooltip-value">{item.currentValue}</span>
      </div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: MUTED_STROKE }} />
        <span className="chart-tooltip-name">Peer median</span>
        <span className="chart-tooltip-value">{item.peerMedian}</span>
      </div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: "rgba(250,250,250,0.42)" }} />
        <span className="chart-tooltip-name">Gap</span>
        <span className="chart-tooltip-value">{item.gapValue}</span>
      </div>
    </div>
  );
}

function CorrelationScatter({ data }: { data: CorrelationDatum[] }) {
  if (!data.length) {
    return <EmptyChart />;
  }

  return (
    <ChartContainer>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 10, right: 18, bottom: 10, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} />
          <XAxis
            axisLine={false}
            dataKey="corr"
            domain={[-1, 1]}
            name="Correlation"
            tick={AXIS_TICK}
            tickFormatter={(value) => formatCorrelation(Number(value))}
            tickLine={false}
            type="number"
          />
          <YAxis
            axisLine={false}
            dataKey="lowLow"
            name="Low-low zones"
            tick={AXIS_TICK}
            tickLine={false}
            type="number"
            width={42}
          />
          <ZAxis dataKey="lowLow" range={[72, 210]} />
          <ReferenceLine stroke={MUTED_STROKE} x={0} />
          <Tooltip content={<CorrelationTooltip />} cursor={{ stroke: MUTED_STROKE }} />
          <Scatter data={data} name="Metric pair">
            {data.map((item) => (
              <Cell fill={item.fill} key={item.id} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

function CorrelationTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload<CorrelationDatum>;
}) {
  const item = payload?.[0]?.payload;
  if (!active || !item) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{item.label}</div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: item.fill }} />
        <span className="chart-tooltip-name">Correlation</span>
        <span className="chart-tooltip-value">{formatCorrelation(item.corr)}</span>
      </div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: CATEGORY_COLORS.anomalies }} />
        <span className="chart-tooltip-name">Low-low zones</span>
        <span className="chart-tooltip-value">
          {item.zones === null ? item.lowLow : `${item.lowLow}/${item.zones}`}
        </span>
      </div>
    </div>
  );
}

function OpportunityScores({ data }: { data: OpportunityDatum[] }) {
  if (!data.length) {
    return <EmptyChart />;
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
            domain={[0, "dataMax"]}
            tick={AXIS_TICK}
            tickFormatter={(value) => formatScore(Number(value))}
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
          <Tooltip content={<OpportunityTooltip />} cursor={false} />
          <Bar barSize={15} dataKey="value" fill={CATEGORY_COLORS.opportunities} radius={[0, 5, 5, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartContainer>
  );
}

function OpportunityTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayload<OpportunityDatum>;
}) {
  const item = payload?.[0]?.payload;
  if (!active || !item) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{item.label}</div>
      <div className="chart-tooltip-row">
        <span className="chart-tooltip-dot" style={{ background: CATEGORY_COLORS.opportunities }} />
        <span className="chart-tooltip-name">Opportunity score</span>
        <span className="chart-tooltip-value">{formatScore(item.value)}</span>
      </div>
      {item.weakMetrics.length ? (
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: "rgba(250,250,250,0.42)" }} />
          <span className="chart-tooltip-name">Weak metrics</span>
          <span className="chart-tooltip-value">{item.weakMetrics.join(", ")}</span>
        </div>
      ) : null}
    </div>
  );
}

function EmptyChart() {
  return <div className="insight-chart-empty">Not enough structured evidence yet.</div>;
}

function buildGeoData(report: InsightReport): GeoDatum[] {
  const rows = new Map<string, GeoDatum>();
  for (const finding of report.categories.flatMap((category) => category.findings)) {
    if (!isMapRiskFinding(finding)) {
      continue;
    }
    const code = stringEvidence(finding, "country");
    if (!code || !COUNTRY_POINTS[code]) {
      continue;
    }
    const city = stringEvidence(finding, "city");
    const cityPoint = city ? CITY_POINTS[locationKey(code, city)] : undefined;
    const point = cityPoint ?? COUNTRY_POINTS[code];
    const id = cityPoint ? `${code}:${normalizeLocationName(city)}` : code;
    const label = cityPoint ? `${cityPoint.label}, ${code}` : point.label;
    const current = rows.get(id) ?? {
      code,
      count: 0,
      critical: 0,
      high: 0,
      id,
      label,
      lat: point.lat,
      lng: point.lng,
      risk: 0,
      topFinding: finding.title,
    };
    const severityScore = severityWeight(finding.severity);
    rows.set(id, {
      ...current,
      count: current.count + 1,
      critical: current.critical + (finding.severity === "critical" ? 1 : 0),
      high: current.high + (finding.severity === "high" ? 1 : 0),
      risk: current.risk + severityScore,
      topFinding: severityScore > severityWeightFromAggregate(current) ? finding.title : current.topFinding,
    });
  }

  return Array.from(rows.values()).sort((a, b) => b.risk - a.risk);
}

function isMapRiskFinding(finding: Finding) {
  if (finding.category === "anomalies") {
    const change = numberEvidence(finding, "change_score");
    if (change === null) {
      return false;
    }
    const direction = stringEvidence(finding, "direction");
    const impact = direction === "lower_better" ? -change : change;
    return impact < 0;
  }
  return ["worrying_trends", "benchmarking", "opportunities"].includes(finding.category);
}

function locationKey(country: string, city: string) {
  return `${country}|${normalizeLocationName(city)}`;
}

function normalizeLocationName(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function severityWeight(severity: Finding["severity"]) {
  if (severity === "critical") return 4;
  if (severity === "high") return 3;
  if (severity === "medium") return 2;
  return 1;
}

function severityWeightFromAggregate(item: Pick<GeoDatum, "critical" | "high">) {
  if (item.critical > 0) return 4;
  if (item.high > 0) return 3;
  return 0;
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
    .filter((item): item is BarDatum => item !== null);
}

function buildTrendSeries(findings: Finding[]): TrendSeries[] {
  const colors = [CATEGORY_COLORS.worrying_trends, CATEGORY_COLORS.anomalies, CATEGORY_COLORS.benchmarking];
  return findings
    .slice(0, 3)
    .map((finding, index) => {
      const rawValues = finding.evidence?.values;
      if (!isRecord(rawValues)) {
        return null;
      }
      const start = toNumber(rawValues.L3W);
      if (start === null || Math.abs(start) < 1e-9) {
        return null;
      }
      const direction = stringEvidence(finding, "direction");
      const values = Object.fromEntries(
        WEEK_KEYS.map((week) => {
          const raw = toNumber(rawValues[week]);
          const deterioration =
            raw === null
              ? null
              : direction === "lower_better"
                ? (raw - start) / Math.abs(start)
                : (start - raw) / Math.abs(start);
          const health = deterioration === null ? null : (1 - Math.max(0, deterioration)) * 100;
          return [week, clamp(health ?? 0, 0, 125)];
        }),
      ) as Record<WeekKey, number>;

      return {
        color: colors[index % colors.length],
        id: `trend_${index}`,
        label: findingLabel(finding),
        values,
      };
    })
    .filter((item): item is TrendSeries => item !== null);
}

function buildBenchmarkData(findings: Finding[]): BenchmarkDatum[] {
  return findings
    .slice(0, 5)
    .map((finding) => {
      const underperformance = numberEvidence(finding, "underperformance_score");
      if (underperformance === null || !Number.isFinite(underperformance)) {
        return null;
      }
      const currentValue =
        stringEvidence(finding, "current_value_label") || formatRawEvidence(finding, "current_value");
      const peerMedian =
        stringEvidence(finding, "peer_median_label") || formatRawEvidence(finding, "peer_median");
      return {
        currentValue,
        gapValue: formatSignedRawEvidence(finding, "gap_value"),
        id: finding.id,
        label: findingLabel(finding),
        peerMedian,
        value: underperformance,
      };
    })
    .filter((item): item is BenchmarkDatum => item !== null);
}

function buildCorrelationData(findings: Finding[]): CorrelationDatum[] {
  return findings
    .slice(0, 6)
    .map((finding) => {
      const corr = numberEvidence(finding, "pearson_correlation");
      const lowLow = numberEvidence(finding, "low_low_count");
      if (corr === null || lowLow === null) {
        return null;
      }
      return {
        corr,
        fill: corr >= 0 ? CATEGORY_COLORS.correlations : CATEGORY_COLORS.worrying_trends,
        id: finding.id,
        label: compactLabel(
          `${stringEvidence(finding, "metric_x") || "Metric A"} / ${
            stringEvidence(finding, "metric_y") || "Metric B"
          }`,
          38,
        ),
        lowLow,
        zones: numberEvidence(finding, "n_zones"),
      };
    })
    .filter((item): item is CorrelationDatum => item !== null);
}

function buildOpportunityData(findings: Finding[]): OpportunityDatum[] {
  return findings
    .slice(0, 5)
    .map((finding) => {
      const score = numberEvidence(finding, "opportunity_score");
      if (score === null) {
        return null;
      }
      const weakMetrics = Array.isArray(finding.evidence?.weak_metrics)
        ? finding.evidence.weak_metrics
            .filter(isRecord)
            .map((item) => (typeof item.metric === "string" ? item.metric : ""))
            .filter(Boolean)
            .slice(0, 3)
        : [];
      return {
        fill: CATEGORY_COLORS.opportunities,
        id: finding.id,
        label: findingLabel(finding, false),
        value: score,
        weakMetrics,
      };
    })
    .filter((item): item is OpportunityDatum => item !== null);
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
  return toNumber(finding.evidence?.[key]);
}

function stringEvidence(finding: Finding, key: string) {
  const value = finding.evidence?.[key];
  return typeof value === "string" ? value : "";
}

function toNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function formatInteger(value: number) {
  return value.toLocaleString();
}

function formatPercent(value: number) {
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function formatPercentUnit(value: number) {
  return `${(value * 100).toFixed(0)}%`;
}

function formatScore(value: number) {
  if (Math.abs(value) >= 10) {
    return value.toFixed(1);
  }
  return value.toFixed(2);
}

function formatSignedScore(value: number) {
  return `${value > 0 ? "+" : ""}${formatScore(value)}`;
}

function formatIndex(value: number) {
  return `${value.toFixed(0)}`;
}

function formatCorrelation(value: number) {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatRawEvidence(finding: Finding, key: string) {
  const value = numberEvidence(finding, key);
  if (value === null) {
    return "n/a";
  }
  return Math.abs(value) >= 10 ? value.toFixed(2) : value.toFixed(3);
}

function formatSignedRawEvidence(finding: Finding, key: string) {
  const value = numberEvidence(finding, key);
  if (value === null) {
    return "n/a";
  }
  const formatted = Math.abs(value) >= 10 ? value.toFixed(2) : value.toFixed(3);
  return `${value > 0 ? "+" : ""}${formatted}`;
}
