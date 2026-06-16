# Rappi Ops Copilot Web

Next.js wrapper for the n8n Chat Trigger workflow.

## Local development

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The app reads the embedded n8n chat URL from:

```bash
NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL=http://localhost:5678/webhook/b2a0878f-58c7-4f89-a98b-2dc29cd637a8/chat
```

The n8n workflow must be imported and active, and the Chat Trigger must be publicly available in embedded mode.
