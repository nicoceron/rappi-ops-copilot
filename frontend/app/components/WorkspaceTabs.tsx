"use client";

import { useState } from "react";
import {
  BarChart3,
  BotMessageSquare,
  Database,
  Gauge,
  LineChart,
  MapPinned,
  Network,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import { ExecutiveInsights } from "./ExecutiveInsights";
import { N8nChat } from "./N8nChat";

type WorkspaceTabsProps = {
  webhookUrl: string;
};

type TabKey = "chat" | "insights" | "context";

const prompts = [
  "Which Mexican zones have the weakest Perfect Orders this week?",
  "Rank countries by Lead Penetration for the last 8 weeks.",
  "Compare defect rate between high and low priority zones.",
  "Diagnose the biggest drivers behind problematic zones.",
];

const metrics = [
  { label: "Perfect Orders", value: "Quality", accent: "blue" },
  { label: "Lead Penetration", value: "Growth", accent: "green" },
  { label: "Defect Rate", value: "Reliability", accent: "orange" },
  { label: "C/R", value: "Conversion", accent: "white" },
];

const stackItems = [
  {
    icon: Database,
    title: "Ops API",
    detail: "Deterministic query layer",
  },
  {
    icon: Workflow,
    title: "n8n agent",
    detail: "Workflow orchestration",
  },
  {
    icon: MapPinned,
    title: "Zone lens",
    detail: "Country, city, zone, and segment filters",
  },
];

const tabs = [
  { key: "chat", label: "Chat", icon: BotMessageSquare },
  { key: "insights", label: "Insights", icon: BarChart3 },
  { key: "context", label: "Context", icon: MapPinned },
] satisfies Array<{ key: TabKey; label: string; icon: typeof BotMessageSquare }>;

export function WorkspaceTabs({ webhookUrl }: WorkspaceTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("chat");

  return (
    <section className="mono-hero-tabs" id="workspace" aria-label="Operations workspace">
      <video
        className="hero-video-bg"
        src="https://framerusercontent.com/assets/iWlVr4qV5BuFxjhc6g7QcPK5o.mp4"
        autoPlay
        muted
        loop
        playsInline
        aria-hidden="true"
      />
      <div className="hero-video-scrim" aria-hidden="true" />

      <div className="mono-hero-content">
        <div className="workspace-command-bar">
          <div className="mono-hero-title">
            <h2>
              Ask <span>Rappi Ops Copilot</span>
            </h2>
            <p>
              Weak zones, KPI rankings, trend diagnostics, charts, CSV exports, and PDF summaries.
            </p>
          </div>

          <div className="workspace-tab-list" role="tablist" aria-label="Workspace tabs">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const selected = activeTab === tab.key;
              return (
                <button
                  aria-controls={`${tab.key}-panel`}
                  aria-selected={selected}
                  className={selected ? "workspace-tab workspace-tab-active" : "workspace-tab"}
                  id={`${tab.key}-tab`}
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  role="tab"
                  type="button"
                >
                  <Icon size={16} />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        <div className="workspace-tab-panel-shell">
          {activeTab === "chat" ? (
            <section
              aria-labelledby="chat-tab"
              className="chat-panel tab-chat-panel"
              id="chat-panel"
              role="tabpanel"
            >
              <div className="chat-header">
                <div>
                  <p className="eyebrow">Custom trigger UI</p>
                  <h2>Ask the workflow</h2>
                </div>
                <span className="webhook-pill">local n8n</span>
              </div>
              <div className="chat-frame">
                <N8nChat webhookUrl={webhookUrl} />
              </div>
            </section>
          ) : null}

          {activeTab === "insights" ? (
            <div
              aria-labelledby="insights-tab"
              className="tab-report-panel"
              id="insights-panel"
              role="tabpanel"
            >
              <ExecutiveInsights />
            </div>
          ) : null}

          {activeTab === "context" ? (
            <aside
              aria-labelledby="context-tab"
              className="ops-panel tab-context-panel"
              id="context-panel"
              role="tabpanel"
            >
              <OpsContext />
            </aside>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function OpsContext() {
  return (
    <>
      <div className="context-summary">
        <div>
          <ShieldCheck size={18} />
          <strong>Grounded answers</strong>
          <span>Backed by the operations API</span>
        </div>
        <div>
          <Gauge size={18} />
          <strong>Live refresh</strong>
          <span>Manual report generation</span>
        </div>
        <div>
          <Network size={18} />
          <strong>Structured output</strong>
          <span>Tables, charts, CSV, and PDF</span>
        </div>
      </div>

      <div className="panel-section status-section">
        <p className="section-label">Live stack</p>
        <div className="status-list">
          {stackItems.map((item) => {
            const Icon = item.icon;
            return (
              <div className="status-row" key={item.title}>
                <span className="status-icon">
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.detail}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel-section visual-section" aria-label="Operations map">
        <div className="ops-map">
          <span className="route route-one" />
          <span className="route route-two" />
          <span className="route route-three" />
          <span className="pin pin-one" />
          <span className="pin pin-two" />
          <span className="pin pin-three" />
          <span className="pin pin-four" />
          <div className="ops-map-status">
            <span>Live zones</span>
            <strong>LATAM performance graph</strong>
          </div>
        </div>
      </div>

      <div className="panel-section">
        <p className="section-label">Tracked metrics</p>
        <div className="metric-grid">
          {metrics.map((metric) => (
            <div className={`metric-card metric-${metric.accent}`} key={metric.label}>
              <BarChart3 size={18} />
              <strong>{metric.label}</strong>
              <span>{metric.value}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="panel-section">
        <p className="section-label">Suggested asks</p>
        <div className="prompt-list">
          {prompts.map((prompt) => (
            <div className="prompt-row" key={prompt}>
              <LineChart size={16} />
              <span>{prompt}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
