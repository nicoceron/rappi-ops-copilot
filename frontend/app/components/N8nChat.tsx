"use client";

import { useEffect, useId } from "react";

type N8nChatProps = {
  webhookUrl: string;
};

export function N8nChat({ webhookUrl }: N8nChatProps) {
  const reactId = useId();
  const targetId = `n8n-chat-${reactId.replaceAll(":", "")}`;

  useEffect(() => {
    if (!webhookUrl) {
      return;
    }

    const target = `#${targetId}`;
    let chat: { unmount?: () => void } | undefined;
    let cancelled = false;

    async function mountChat() {
      Object.assign(globalThis, {
        __VUE_OPTIONS_API__: true,
        __VUE_PROD_DEVTOOLS__: false,
        __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false,
      });

      const { createChat } = await import("@n8n/chat");

      if (cancelled) {
        return;
      }

      chat = createChat({
        webhookUrl,
        target,
        mode: "fullscreen",
        chatInputKey: "chatInput",
        chatSessionKey: "sessionId",
        loadPreviousSession: true,
        showWelcomeScreen: false,
        defaultLanguage: "en",
        metadata: {
          source: "rappi-ops-copilot-web",
        },
        initialMessages: [
          "Hi. I am Rappi Ops Copilot.",
          "Ask about rankings, trends, diagnostics, exports, or weak zones across the operations dataset.",
        ],
        i18n: {
          en: {
            title: "Rappi Ops Copilot",
            subtitle: "Operations analytics, powered by n8n",
            footer: "",
            getStarted: "New conversation",
            inputPlaceholder: "Ask about countries, cities, zones, or KPIs...",
            closeButtonTooltip: "Close chat",
          },
        },
      }) as { unmount?: () => void } | undefined;
    }

    mountChat();

    return () => {
      cancelled = true;
      chat?.unmount?.();
      document.querySelector(target)?.replaceChildren();
    };
  }, [targetId, webhookUrl]);

  if (!webhookUrl) {
    return (
      <div className="chat-empty">
        <h2>Missing chat webhook</h2>
        <p>Set NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL and restart the web app.</p>
      </div>
    );
  }

  return <div id={targetId} className="chat-mount" />;
}
