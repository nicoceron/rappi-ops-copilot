import {
  Activity,
  ArrowUpRight,
  BarChart3,
  BotMessageSquare,
  Database,
  LineChart,
  MapPinned,
  Workflow,
} from "lucide-react";
import { N8nChat } from "./components/N8nChat";

const DEFAULT_WEBHOOK_URL =
  "http://localhost:5678/webhook/b2a0878f-58c7-4f89-a98b-2dc29cd637a8/chat";

export const dynamic = "force-dynamic";

const prompts = [
  "Which Mexican zones have the weakest Perfect Orders this week?",
  "Rank countries by Lead Penetration for the last 8 weeks.",
  "Compare defect rate between high and low priority zones.",
  "Diagnose the biggest drivers behind problematic zones.",
];

const metrics = [
  { label: "Perfect Orders", value: "Quality" },
  { label: "Lead Penetration", value: "Growth" },
  { label: "Defect Rate", value: "Reliability" },
  { label: "C/R", value: "Conversion" },
];

export default function Home() {
  const webhookUrl =
    process.env.NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL || DEFAULT_WEBHOOK_URL;

  return (
    <main className="app-shell">
      <section className="topbar" aria-label="Application summary">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true">
            <BotMessageSquare size={22} />
          </span>
          <div>
            <p className="eyebrow">Rappi operations analytics</p>
            <h1>Rappi Ops Copilot</h1>
          </div>
        </div>

        <div className="topbar-actions">
          <a href="http://localhost:5678" target="_blank" rel="noreferrer">
            <Workflow size={16} />
            n8n
            <ArrowUpRight size={14} />
          </a>
          <a href="http://localhost:8000/health" target="_blank" rel="noreferrer">
            <Activity size={16} />
            API
            <ArrowUpRight size={14} />
          </a>
        </div>
      </section>

      <section className="workspace-grid">
        <aside className="ops-panel" aria-label="Operational context">
          <div className="panel-section status-section">
            <p className="section-label">Live stack</p>
            <div className="status-list">
              <div className="status-row">
                <span className="status-icon">
                  <Database size={18} />
                </span>
                <div>
                  <strong>Ops API</strong>
                  <span>Deterministic query layer</span>
                </div>
              </div>
              <div className="status-row">
                <span className="status-icon">
                  <Workflow size={18} />
                </span>
                <div>
                  <strong>n8n agent</strong>
                  <span>DeepSeek workflow orchestration</span>
                </div>
              </div>
              <div className="status-row">
                <span className="status-icon">
                  <MapPinned size={18} />
                </span>
                <div>
                  <strong>City and zone lens</strong>
                  <span>Country, city, zone, and segment filters</span>
                </div>
              </div>
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
            </div>
          </div>

          <div className="panel-section">
            <p className="section-label">Tracked metrics</p>
            <div className="metric-grid">
              {metrics.map((metric) => (
                <div className="metric-card" key={metric.label}>
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
        </aside>

        <section className="chat-panel" aria-label="n8n embedded chat">
          <div className="chat-header">
            <div>
              <p className="eyebrow">Embedded Chat Trigger</p>
              <h2>Ask the workflow</h2>
            </div>
            <span className="webhook-pill">local n8n</span>
          </div>
          <div className="chat-frame">
            <N8nChat webhookUrl={webhookUrl} />
          </div>
        </section>
      </section>
    </main>
  );
}
