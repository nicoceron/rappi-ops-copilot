"use client";

import { useState } from "react";
import {
  ArrowUpRight,
  BarChart3,
  BotMessageSquare,
  Workflow,
} from "lucide-react";
import { ExecutiveInsights } from "./ExecutiveInsights";
import { N8nChat } from "./N8nChat";

type WorkspaceTabsProps = {
  webhookUrl: string;
};

type TabKey = "chat" | "insights";

const tabs = [
  { key: "chat", label: "Chat", icon: BotMessageSquare },
  { key: "insights", label: "Insights", icon: BarChart3 },
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
          <div className="workspace-brand" aria-label="Rappi Ops Copilot">
            <img src="/brand/rappi-ops-lockup.svg" alt="Rappi Ops Copilot" />
          </div>

          <div className="mono-hero-title">
            <h2>
              Ask <span>operations data</span>
            </h2>
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

          <a
            className="workspace-n8n-link"
            href="http://localhost:5678"
            target="_blank"
            rel="noreferrer"
          >
            <Workflow size={16} />
            n8n
            <ArrowUpRight size={14} />
          </a>
        </div>

        <div className="workspace-tab-panel-shell">
          {activeTab === "chat" ? (
            <section
              aria-labelledby="chat-tab"
              className="chat-panel tab-chat-panel"
              id="chat-panel"
              role="tabpanel"
            >
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
        </div>
      </div>
    </section>
  );
}
