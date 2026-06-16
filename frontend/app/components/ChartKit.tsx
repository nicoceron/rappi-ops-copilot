"use client";

import { ReactNode } from "react";

type ChartValue = string | number | null | undefined;

type ChartPayloadItem = {
  color?: string;
  dataKey?: string | number;
  fill?: string;
  name?: string | number;
  value?: ChartValue;
};

export type ChartConfig = Record<
  string,
  {
    color: string;
    label: string;
    valueFormatter?: (value: ChartValue) => string;
  }
>;

type ChartCardProps = {
  children: ReactNode;
  className?: string;
  description?: string;
  footer?: ReactNode;
  title: string;
};

type ChartTooltipContentProps = {
  active?: boolean;
  config?: ChartConfig;
  label?: ChartValue;
  payload?: ChartPayloadItem[];
  valueFormatter?: (value: ChartValue) => string;
};

export function ChartCard({ children, className = "", description, footer, title }: ChartCardProps) {
  return (
    <section className={`insight-chart-card ${className}`.trim()}>
      <div className="insight-chart-header">
        <div>
          <strong>{title}</strong>
          {description ? <span>{description}</span> : null}
        </div>
      </div>
      <div className="insight-chart-body">{children}</div>
      {footer ? <div className="insight-chart-footer">{footer}</div> : null}
    </section>
  );
}

export function ChartContainer({ children }: { children: ReactNode }) {
  return <div className="insight-chart-container">{children}</div>;
}

export function ChartTooltipContent({
  active,
  config,
  label,
  payload,
  valueFormatter,
}: ChartTooltipContentProps) {
  if (!active || !payload?.length) {
    return null;
  }

  const rows = payload.filter((item) => item.value !== null && item.value !== undefined);

  return (
    <div className="chart-tooltip">
      {label ? <div className="chart-tooltip-label">{label}</div> : null}
      {rows.map((item) => {
        const key = String(item.dataKey ?? item.name ?? "");
        const itemConfig = config?.[key];
        const color = item.color || item.fill || itemConfig?.color || "var(--blue)";
        const formatValue = itemConfig?.valueFormatter || valueFormatter || defaultFormatter;

        return (
          <div className="chart-tooltip-row" key={key}>
            <span className="chart-tooltip-dot" style={{ background: color }} />
            <span className="chart-tooltip-name">{itemConfig?.label || item.name || key}</span>
            <span className="chart-tooltip-value">{formatValue(item.value)}</span>
          </div>
        );
      })}
    </div>
  );
}

function defaultFormatter(value: ChartValue) {
  if (typeof value === "number") {
    return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
  }
  return value ? String(value) : "n/a";
}
