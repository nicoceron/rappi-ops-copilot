import { ArrowUpRight, Workflow } from "lucide-react";
import { WorkspaceTabs } from "./components/WorkspaceTabs";

const DEFAULT_WEBHOOK_URL =
  "http://localhost:5678/webhook/b2a0878f-58c7-4f89-a98b-2dc29cd637a8/chat";

export const dynamic = "force-dynamic";

export default function Home() {
  const webhookUrl =
    process.env.NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL || DEFAULT_WEBHOOK_URL;

  return (
    <main className="app-shell">
      <div className="ambient-grid" aria-hidden="true" />

      <a
        className="floating-n8n-link"
        href="http://localhost:5678"
        target="_blank"
        rel="noreferrer"
      >
        <Workflow size={16} />
        n8n
        <ArrowUpRight size={14} />
      </a>

      <WorkspaceTabs webhookUrl={webhookUrl} />
    </main>
  );
}
