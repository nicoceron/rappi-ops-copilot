"use client";

import {
  BarChart3,
  Download,
  FileText,
  LoaderCircle,
  RefreshCw,
  Send,
  Table2,
  User,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type N8nChatProps = {
  webhookUrl: string;
};

type ChatSender = "bot" | "user";

type ChatMessage = {
  id: string;
  sender: ChatSender;
  text: string;
  createdAt: number;
  status?: "error";
  structured?: StructuredContent | null;
};

type ParsedTable = {
  id: string;
  headers: string[];
  rows: Record<string, string>[];
};

type ChartSpec = {
  id: string;
  type: "bar" | "line" | "scatter";
  title: string;
  xKey: string;
  yKeys: string[];
  data: Record<string, string | number>[];
};

type ExportLink = {
  label: string;
  href: string;
  kind: "csv" | "pdf" | "file";
};

type StructuredContent = {
  answer?: string;
  tables?: ParsedTable[];
  charts?: ChartSpec[];
  exports?: ExportLink[];
};

const SESSION_STORAGE_KEY = "rappi-ops-copilot-session-id";
const HISTORY_STORAGE_KEY = "rappi-ops-copilot-chat-history";
const MAX_STORED_MESSAGES = 30;
const DEFAULT_OPS_API_URL = "http://localhost:8000";
const OPS_API_BASE_URL = (process.env.NEXT_PUBLIC_OPS_API_URL || DEFAULT_OPS_API_URL).replace(
  /\/$/,
  "",
);
const PLACEHOLDER_EXPORT_HOSTS = new Set([
  "tu-dominio.com",
  "www.tu-dominio.com",
  "example.com",
  "www.example.com",
  "your-domain.com",
  "www.your-domain.com",
]);
const CHART_COLORS = ["#7ec4e3", "#7eea9b", "#f2b76c", "#fafafa"];
const quickPrompts = [
  "¿Cuál es el promedio de Lead Penetration por país?",
  "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas",
  "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México",
];

const initialMessages: ChatMessage[] = [
  {
    id: "welcome-1",
    sender: "bot",
    text: "Hi. I am Rappi Ops Copilot.\n\nAsk about rankings, trends, diagnostics, exports, or weak zones across the operations dataset.",
    createdAt: Date.now(),
  },
];

export function N8nChat({ webhookUrl }: N8nChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const storedSession = window.localStorage.getItem(SESSION_STORAGE_KEY);
    const nextSession = storedSession || createId("session");
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSession);
    setSessionId(nextSession);

    const storedHistory = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (storedHistory) {
      try {
        const parsed = JSON.parse(storedHistory) as ChatMessage[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      } catch {
        window.localStorage.removeItem(HISTORY_STORAGE_KEY);
      }
    }

    setIsHydrated(true);
  }, []);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isSending]);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }

    const compactHistory = messages.slice(-MAX_STORED_MESSAGES);
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(compactHistory));
  }, [isHydrated, messages]);

  const canSend = Boolean(webhookUrl && sessionId && input.trim() && !isSending);
  const showQuickPrompts = !messages.some((message) => message.sender === "user");

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const question = input.trim();
    await submitQuestion(question);
  }

  async function submitQuestion(question: string) {
    if (!question || !sessionId || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createId("user"),
      sender: "user",
      text: question,
      createdAt: Date.now(),
    };

    setMessages((current) => [...current, userMessage]);
    setInput("");
    setIsSending(true);

    try {
      const response = await fetch(webhookUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json, text/plain",
        },
        body: JSON.stringify({
          action: "sendMessage",
          sessionId,
          chatInput: question,
          metadata: {
            source: "rappi-ops-copilot-custom-ui",
            renderer: "react-analytics-chat",
          },
        }),
      });

      const payload = await readWebhookPayload(response);

      if (!response.ok) {
        throw new Error(extractResponseText(payload) || `n8n returned ${response.status}`);
      }

      const answerText = extractResponseText(payload);
      const structured = parseStructuredContent(answerText, payload);

      setMessages((current) => [
        ...current,
        {
          id: createId("bot"),
          sender: "bot",
          text: answerText || "The workflow completed but did not return a readable answer.",
          structured,
          createdAt: Date.now(),
        },
      ]);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "The workflow did not return a readable response.";
      setMessages((current) => [
        ...current,
        {
          id: createId("bot-error"),
          sender: "bot",
          text: `I could not complete that request.\n\n${message}`,
          createdAt: Date.now(),
          status: "error",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  function startNewConversation() {
    const nextSession = createId("session");
    window.localStorage.setItem(SESSION_STORAGE_KEY, nextSession);
    window.localStorage.removeItem(HISTORY_STORAGE_KEY);
    setSessionId(nextSession);
    setMessages(initialMessages.map((message) => ({ ...message, createdAt: Date.now() })));
    setInput("");
  }

  if (!webhookUrl) {
    return (
      <div className="chat-empty">
        <h2>Missing chat webhook</h2>
        <p>Set NEXT_PUBLIC_N8N_CHAT_WEBHOOK_URL and restart the web app.</p>
      </div>
    );
  }

  return (
    <div className="analytics-chat">
      <div className="analytics-chat-toolbar">
        <div className="analytics-chat-brand">
          <span>{sessionId ? `Session ${sessionId.slice(-8)}` : "Preparing session"}</span>
        </div>
        <button type="button" onClick={startNewConversation} title="Start new conversation">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="analytics-chat-messages" aria-live="polite">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {isSending ? (
          <div className="message-row message-row-bot">
            <span className="message-avatar message-avatar-bot">
              <img src="/brand/rappi-ops-mark.svg" alt="" />
            </span>
            <div className="message-bubble message-bubble-bot message-bubble-loading">
              <LoaderCircle className="spin" size={16} />
              <span>Reading operations data...</span>
            </div>
          </div>
        ) : null}
        <div ref={messageEndRef} />
      </div>

      {showQuickPrompts ? (
        <div className="quick-prompt-row" aria-label="Suggested prompts">
          {quickPrompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => submitQuestion(prompt)}
              disabled={!sessionId || isSending}
            >
              {prompt}
            </button>
          ))}
        </div>
      ) : null}

      <form className="analytics-chat-input" onSubmit={sendMessage}>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder="Ask about countries, cities, zones, KPIs, or exports..."
          rows={2}
        />
        <button type="submit" disabled={!canSend} title="Send message">
          {isSending ? <LoaderCircle className="spin" size={18} /> : <Send size={18} />}
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const parsed = useMemo(() => buildMessagePresentation(message), [message]);
  const isBot = message.sender === "bot";

  return (
    <div className={`message-row ${isBot ? "message-row-bot" : "message-row-user"}`}>
      <span className={isBot ? "message-avatar message-avatar-bot" : "message-avatar"}>
        {isBot ? <img src="/brand/rappi-ops-mark.svg" alt="" /> : <User size={16} />}
      </span>
      <article
        className={`message-bubble ${isBot ? "message-bubble-bot" : "message-bubble-user"} ${
          message.status === "error" ? "message-bubble-error" : ""
        }`}
      >
        <RenderedText text={parsed.text} />

        {parsed.tables.length > 0 ? (
          <div className="rich-result-stack">
            {parsed.tables.map((table) => (
              <ResultTable key={table.id} table={table} />
            ))}
          </div>
        ) : null}

        {parsed.charts.length > 0 ? (
          <div className="rich-result-stack">
            {parsed.charts.map((chart) => (
              <ChartCard key={chart.id} chart={chart} />
            ))}
          </div>
        ) : null}

        {parsed.exports.length > 0 ? <ExportLinks exports={parsed.exports} /> : null}
      </article>
    </div>
  );
}

function ResultTable({ table }: { table: ParsedTable }) {
  return (
    <section className="result-table-card">
      <div className="result-card-title">
        <Table2 size={16} />
        <strong>Table</strong>
      </div>
      <div className="result-table-scroll">
        <table>
          <thead>
            <tr>
              {table.headers.map((header) => (
                <th key={header}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={`${table.id}-${rowIndex}`}>
                {table.headers.map((header) => (
                  <td key={header}>{row[header]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ChartCard({ chart }: { chart: ChartSpec }) {
  const isLine = chart.type === "line";
  const isScatter = chart.type === "scatter";
  const primaryYKey = chart.yKeys[0];

  return (
    <section className="chart-card">
      <div className="result-card-title">
        <BarChart3 size={16} />
        <strong>{chart.title}</strong>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          {isScatter ? (
            <ScatterChart margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis
                dataKey={chart.xKey}
                name={chart.xKey}
                tick={{ fill: "#ffffff99", fontSize: 11 }}
                type="number"
              />
              <YAxis
                dataKey={primaryYKey}
                name={primaryYKey}
                tick={{ fill: "#ffffff99", fontSize: 11 }}
                type="number"
                width={42}
              />
              <Tooltip
                contentStyle={{
                  background: "#111111",
                  border: "1px solid rgba(255,255,255,0.14)",
                  borderRadius: 8,
                  color: "#fafafa",
                }}
                cursor={{ stroke: "rgba(255,255,255,0.28)" }}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              <Scatter data={chart.data} name={`${primaryYKey} by ${chart.xKey}`}>
                {chart.data.map((_, pointIndex) => (
                  <Cell key={`${chart.id}-point-${pointIndex}`} fill={CHART_COLORS[pointIndex % CHART_COLORS.length]} />
                ))}
              </Scatter>
            </ScatterChart>
          ) : isLine ? (
            <LineChart data={chart.data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={chart.xKey} tick={{ fill: "#ffffff99", fontSize: 11 }} />
              <YAxis tick={{ fill: "#ffffff99", fontSize: 11 }} width={42} />
              <Tooltip
                contentStyle={{
                  background: "#111111",
                  border: "1px solid rgba(255,255,255,0.14)",
                  borderRadius: 8,
                  color: "#fafafa",
                }}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              {chart.yKeys.map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  strokeWidth={2.4}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart data={chart.data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={chart.xKey} tick={{ fill: "#ffffff99", fontSize: 11 }} />
              <YAxis tick={{ fill: "#ffffff99", fontSize: 11 }} width={42} />
              <Tooltip
                contentStyle={{
                  background: "#111111",
                  border: "1px solid rgba(255,255,255,0.14)",
                  borderRadius: 8,
                  color: "#fafafa",
                }}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              {chart.yKeys.map((key, index) => (
                <Bar key={key} dataKey={key} radius={[5, 5, 0, 0]}>
                  {chart.data.map((_, cellIndex) => (
                    <Cell
                      key={`${key}-${cellIndex}`}
                      fill={CHART_COLORS[(index + cellIndex) % CHART_COLORS.length]}
                    />
                  ))}
                </Bar>
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ExportLinks({ exports }: { exports: ExportLink[] }) {
  return (
    <div className="export-link-row">
      {exports.map((exportLink) => (
        <a
          key={`${exportLink.kind}-${exportLink.href}`}
          href={exportLink.href}
          target="_blank"
          rel="noreferrer"
        >
          {exportLink.kind === "pdf" ? <FileText size={15} /> : <Download size={15} />}
          {exportLink.label}
        </a>
      ))}
    </div>
  );
}

function RenderedText({ text }: { text: string }) {
  const blocks = useMemo(() => splitTextBlocks(cleanDisplayText(text)), [text]);

  return (
    <div className="rendered-message">
      {blocks.map((block) => {
        if (block.kind === "heading") {
          return (
            <h3 key={block.id} className={`rendered-heading rendered-heading-${block.level}`}>
              {renderInline(block.text)}
            </h3>
          );
        }

        if (block.kind === "list") {
          return (
            <ul key={block.id}>
              {block.items.map((item, index) => (
                <li key={`${block.id}-${index}`}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }

        if (block.kind === "code") {
          return <pre key={block.id}>{block.text}</pre>;
        }

        if (block.kind === "rule") {
          return <hr key={block.id} />;
        }

        return <p key={block.id}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);

  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }

    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

async function readWebhookPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  const parsed = tryParseJson(text);
  return parsed ?? text;
}

function extractResponseText(payload: unknown): string {
  if (typeof payload === "string") {
    return payload;
  }

  if (!payload || typeof payload !== "object") {
    return "";
  }

  const record = payload as Record<string, unknown>;
  const candidates = [record.output, record.text, record.message, record.answer, record.result];

  for (const candidate of candidates) {
    if (typeof candidate === "string") {
      return candidate;
    }

    if (candidate && typeof candidate === "object") {
      const nested = candidate as Record<string, unknown>;
      if (typeof nested.text === "string") {
        return nested.text;
      }
      if (typeof nested.output === "string") {
        return nested.output;
      }
    }
  }

  return JSON.stringify(payload, null, 2);
}

function parseStructuredContent(text: string, payload: unknown): StructuredContent | null {
  const payloadObject = isRecord(payload) ? payload : null;
  const jsonText = tryParseJson(text);
  const fencedJson = extractFencedJson(text);
  const candidates = [payloadObject, jsonText, fencedJson].filter(isRecord);

  for (const candidate of candidates) {
    const normalized = normalizeStructuredCandidate(candidate);
    if (normalized) {
      return normalized;
    }
  }

  return null;
}

function normalizeStructuredCandidate(candidate: Record<string, unknown>): StructuredContent | null {
  const answer = firstString(candidate.answer, candidate.summary, candidate.output, candidate.text);
  const tables = normalizeTables(candidate.table ?? candidate.tables);
  const charts = normalizeCharts(candidate.chart ?? candidate.charts);
  const exports = normalizeExports(candidate.exports ?? candidate.exportLinks ?? candidate.files);

  if (!answer && tables.length === 0 && charts.length === 0 && exports.length === 0) {
    return null;
  }

  return {
    answer,
    tables,
    charts,
    exports,
  };
}

function buildMessagePresentation(message: ChatMessage) {
  const textSource = message.structured?.answer || message.text;
  const markdownTables = parseMarkdownTables(textSource);
  const structuredTables = message.structured?.tables ?? [];
  const tables = [...structuredTables, ...markdownTables.tables];
  const structuredCharts = message.structured?.charts ?? [];
  const requestedChartType = inferRequestedChartType(message.text);
  const heuristicCharts = tables
    .map((table) => chartFromTable(table, requestedChartType))
    .filter(Boolean) as ChartSpec[];
  const exports = [
    ...(message.structured?.exports ?? []),
    ...extractExportLinks(message.text),
  ];
  const text = markdownTables.textWithoutTables || textSource;

  return {
    text,
    tables,
    charts: [...structuredCharts, ...heuristicCharts],
    exports: dedupeExports(exports),
  };
}

function parseMarkdownTables(text: string): { tables: ParsedTable[]; textWithoutTables: string } {
  const lines = normalizeInlineMarkdownTables(text).split(/\r?\n/);
  const tables: ParsedTable[] = [];
  const outputLines: string[] = [];
  let index = 0;

  while (index < lines.length) {
    const current = lines[index];
    const next = lines[index + 1];

    if (isMarkdownTableRow(current) && isMarkdownTableSeparator(next)) {
      const headers = splitMarkdownTableRow(current);
      const rows: Record<string, string>[] = [];
      index += 2;

      while (index < lines.length && isMarkdownTableRow(lines[index])) {
        const cells = splitMarkdownTableRow(lines[index]);
        const row: Record<string, string> = {};
        headers.forEach((header, cellIndex) => {
          row[header] = cells[cellIndex] ?? "";
        });
        rows.push(row);
        index += 1;
      }

      if (headers.length > 1 && rows.length > 0) {
        tables.push({
          id: createId("table"),
          headers,
          rows,
        });
      }
      continue;
    }

    outputLines.push(current);
    index += 1;
  }

  return {
    tables,
    textWithoutTables: outputLines.join("\n").trim(),
  };
}

function normalizeInlineMarkdownTables(text: string): string {
  return text
    .split(/\r?\n/)
    .flatMap((line) => {
      if (!hasInlineMarkdownTable(line)) {
        return [line];
      }

      return line
        .replace(/\|\s+(?=\|)/g, "|\n")
        .split(/\n/)
        .map((row) => row.trim())
        .filter(Boolean);
    })
    .join("\n");
}

function hasInlineMarkdownTable(line: string): boolean {
  return /\|\s+\|\s*:?-{3,}/.test(line);
}

function chartFromTable(table: ParsedTable, requestedType: ChartSpec["type"] | null = null): ChartSpec | null {
  if (table.rows.length < 2 || table.headers.length < 2) {
    return null;
  }

  const headers = table.headers.filter((header) => header !== "#");

  if (requestedType === "scatter") {
    return scatterChartFromTable(table, headers);
  }

  const xKey = selectCategoryKey(headers, table.rows);
  const yKeys = headers
    .filter((header) => header !== xKey)
    .filter((header) => table.rows.some((row) => parseMetricValue(row[header]) !== null))
    .filter((header) => !/variaci[oó]n|mín|max|zonas|orders total|total órdenes/i.test(header))
    .slice(0, 2);

  if (!xKey || yKeys.length === 0) {
    return null;
  }

  const data = table.rows
    .map((row) => {
      const point: Record<string, string | number> = {
        [xKey]: stripMarkdown(row[xKey] || ""),
      };
      yKeys.forEach((key) => {
        const value = parseMetricValue(row[key]);
        if (value !== null) {
          point[key] = value;
        }
      });
      return point;
    })
    .filter((row) => yKeys.some((key) => typeof row[key] === "number"));

  if (data.length < 2) {
    return null;
  }

  const isTrend = /semana|week|fecha|date/i.test(xKey);
  const title = isTrend ? `Trend: ${yKeys.join(", ")}` : `Chart: ${yKeys.join(", ")} by ${xKey}`;

  return {
    id: createId("chart"),
    type: requestedType === "line" || isTrend ? "line" : "bar",
    title,
    xKey,
    yKeys,
    data,
  };
}

function scatterChartFromTable(table: ParsedTable, headers: string[]): ChartSpec | null {
  const numericKeys = headers.filter((header) =>
    table.rows.some((row) => parseMetricValue(row[header]) !== null),
  );

  if (numericKeys.length < 2) {
    return null;
  }

  const xKey = numericKeys.find(isCountLikeKey) ?? numericKeys[0];
  const yKey =
    numericKeys.find((key) => key !== xKey && !isCountLikeKey(key) && !isMinMaxLikeKey(key)) ??
    numericKeys.find((key) => key !== xKey);

  if (!yKey) {
    return null;
  }

  const labelKey = headers.find((header) => !numericKeys.includes(header));
  const data = table.rows
    .map((row) => {
      const xValue = parseMetricValue(row[xKey]);
      const yValue = parseMetricValue(row[yKey]);
      if (xValue === null || yValue === null) {
        return null;
      }

      const point: Record<string, string | number> = {
        [xKey]: xValue,
        [yKey]: yValue,
      };

      if (labelKey) {
        point[labelKey] = stripMarkdown(row[labelKey] || "");
      }

      return point;
    })
    .filter((point): point is Record<string, string | number> => Boolean(point));

  if (data.length < 2) {
    return null;
  }

  return {
    id: createId("chart"),
    type: "scatter",
    title: `Scatter: ${yKey} by ${xKey}`,
    xKey,
    yKeys: [yKey],
    data,
  };
}

function selectCategoryKey(headers: string[], rows: Record<string, string>[]): string {
  const preferred = headers.find((header) => /zona|pa[ií]s|country|semana|week|ciudad|city|m[eé]trica/i.test(header));
  if (preferred) {
    return preferred;
  }

  return headers.find((header) => rows.some((row) => parseMetricValue(row[header]) === null)) || headers[0];
}

function normalizeTables(value: unknown): ParsedTable[] {
  const rawTables = Array.isArray(value) ? value : value ? [value] : [];

  return rawTables.flatMap((item, index) => {
    if (Array.isArray(item)) {
      return tableFromRows(item, `structured-table-${index}`);
    }

    if (isRecord(item)) {
      const rows = item.rows ?? item.data;
      if (Array.isArray(rows)) {
        return tableFromRows(rows, `structured-table-${index}`);
      }
    }

    return [];
  });
}

function tableFromRows(rows: unknown[], id: string): ParsedTable[] {
  const records = rows.filter(isRecord);
  if (records.length === 0) {
    return [];
  }

  const headers = Array.from(new Set(records.flatMap((row) => Object.keys(row))));
  return [
    {
      id,
      headers,
      rows: records.map((row) =>
        Object.fromEntries(headers.map((header) => [header, String(row[header] ?? "")])),
      ),
    },
  ];
}

function normalizeCharts(value: unknown): ChartSpec[] {
  const rawCharts = Array.isArray(value) ? value : value ? [value] : [];

  return rawCharts.flatMap((item, index) => {
    if (!isRecord(item)) {
      return [];
    }

    const data = Array.isArray(item.data) ? item.data.filter(isRecord) : [];
    const xKey = firstString(item.xKey, item.x, item.category);
    const yCandidate = item.yKeys ?? item.yKey ?? item.y ?? item.metric;
    const yKeys = Array.isArray(yCandidate)
      ? yCandidate.filter((key): key is string => typeof key === "string")
      : typeof yCandidate === "string"
        ? [yCandidate]
        : [];
    const type = normalizeChartType(item.type);

    if (!xKey || yKeys.length === 0 || data.length === 0) {
      return [];
    }

    const rows = data
      .map((row) => normalizeChartRow(row, xKey, yKeys, type))
      .filter((row) => {
        if (type !== "scatter") {
          return true;
        }

        return typeof row[xKey] === "number" && typeof row[yKeys[0]] === "number";
      });

    if (rows.length === 0) {
      return [];
    }

    return [
      {
        id: `structured-chart-${index}`,
        type,
        title: firstString(item.title) || "Chart",
        xKey,
        yKeys,
        data: rows,
      },
    ];
  });
}

function normalizeChartRow(
  row: Record<string, unknown>,
  xKey: string,
  yKeys: string[],
  type: ChartSpec["type"],
) {
  const parsedX = parseMetricValue(row[xKey]);
  const normalized: Record<string, string | number> = {
    [xKey]: type === "scatter" && parsedX !== null ? parsedX : String(row[xKey] ?? ""),
  };

  yKeys.forEach((key) => {
    const parsed = parseMetricValue(row[key]);
    if (parsed !== null) {
      normalized[key] = parsed;
    }
  });

  return normalized;
}

function inferRequestedChartType(text: string): ChartSpec["type"] | null {
  if (/\b(scatter|dispersi[oó]n|bubble|burbuja)\b/i.test(text)) {
    return "scatter";
  }

  if (/\b(line|l[ií]nea|trend|tendencia|area|time series|serie temporal|evoluci[oó]n)\b/i.test(text)) {
    return "line";
  }

  if (/\b(bar|barra|column|columna|histogram|histograma|pie|donut|dona)\b/i.test(text)) {
    return "bar";
  }

  return null;
}

function normalizeChartType(value: unknown): ChartSpec["type"] {
  if (typeof value !== "string") {
    return "bar";
  }

  const normalized = value.trim().toLowerCase();
  if (normalized === "scatter" || normalized === "bubble") {
    return "scatter";
  }
  if (normalized === "line" || normalized === "area" || normalized === "trend") {
    return "line";
  }

  return "bar";
}

function isCountLikeKey(key: string): boolean {
  return /zonas|zones|count|cantidad|n_|num|total/i.test(key);
}

function isMinMaxLikeKey(key: string): boolean {
  return /mín|min|max|máx/i.test(key);
}

function normalizeExports(value: unknown): ExportLink[] {
  const rawExports = Array.isArray(value) ? value : value ? [value] : [];

  return rawExports.flatMap((item) => {
    if (typeof item === "string") {
      const link = linkFromUrl(item);
      return link ? [link] : [];
    }

    if (!isRecord(item)) {
      return [];
    }

    const href = normalizeExportHref(
      firstString(item.href, item.browser_url, item.downloadUrl, item.url, item.api_path),
    );
    if (!href) {
      return [];
    }

    const kind = inferExportKind(href);
    return [
      {
        href,
        kind,
        label: firstString(item.label, item.name) || labelForKind(kind),
      },
    ];
  });
}

function extractExportLinks(text: string): ExportLink[] {
  const matches =
    text.match(/(?:https?:\/\/|\/)[^\s)\]]+?\.(?:csv|pdf)(?:\?[^\s)\]]*)?/gi) ?? [];
  return matches.map(linkFromUrl).filter((link): link is ExportLink => Boolean(link));
}

function dedupeExports(exports: ExportLink[]): ExportLink[] {
  const seen = new Set<string>();
  return exports.filter((exportLink) => {
    if (seen.has(exportLink.href)) {
      return false;
    }
    seen.add(exportLink.href);
    return true;
  });
}

function linkFromUrl(rawHref: string): ExportLink | null {
  const href = normalizeExportHref(rawHref);
  if (!href) {
    return null;
  }

  const kind = inferExportKind(href);
  return {
    href,
    kind,
    label: labelForKind(kind),
  };
}

function normalizeExportHref(rawHref: string | undefined): string | null {
  if (!rawHref) {
    return null;
  }

  const href = rawHref.trim().replace(/^["'`(<]+|[>"'`),.]+$/g, "");
  if (!href) {
    return null;
  }

  if (href.startsWith("/")) {
    return supportedExportPath(href) ? `${OPS_API_BASE_URL}${href}` : null;
  }

  try {
    const url = new URL(href);
    const hostname = url.hostname.toLowerCase();

    if (PLACEHOLDER_EXPORT_HOSTS.has(hostname)) {
      return null;
    }

    if (!supportedExportPath(url.pathname)) {
      return null;
    }

    if (hostname === "ops-api") {
      return `${OPS_API_BASE_URL}${url.pathname}${url.search}`;
    }

    return url.toString();
  } catch {
    return null;
  }
}

function supportedExportPath(pathname: string): boolean {
  return /^\/exports\/[^/?#]+\.(?:csv|pdf)$/i.test(pathname);
}

function inferExportKind(href: string): ExportLink["kind"] {
  if (/\.csv(?:\?|$)/i.test(href)) {
    return "csv";
  }
  if (/\.pdf(?:\?|$)/i.test(href)) {
    return "pdf";
  }
  return "file";
}

function labelForKind(kind: ExportLink["kind"]): string {
  if (kind === "csv") {
    return "CSV";
  }
  if (kind === "pdf") {
    return "PDF";
  }
  return "Download";
}

function splitTextBlocks(text: string) {
  const lines = text.split(/\r?\n/);
  const blocks: Array<
    | { id: string; kind: "heading"; level: 2 | 3 | 4; text: string }
    | { id: string; kind: "paragraph"; text: string }
    | { id: string; kind: "list"; items: string[] }
    | { id: string; kind: "code"; text: string }
    | { id: string; kind: "rule" }
  > = [];
  let paragraph: string[] = [];
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let inCode = false;

  function flushParagraph() {
    if (paragraph.length > 0) {
      blocks.push({ id: createId("paragraph"), kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length > 0) {
      blocks.push({ id: createId("list"), kind: "list", items: listItems });
      listItems = [];
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (line.startsWith("```")) {
      if (inCode) {
        blocks.push({ id: createId("code"), kind: "code", text: codeLines.join("\n") });
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      return;
    }

    if (inCode) {
      codeLines.push(rawLine);
      return;
    }

    if (!line) {
      flushParagraph();
      flushList();
      return;
    }

    if (/^---+$/.test(line)) {
      flushParagraph();
      flushList();
      blocks.push({ id: createId("rule"), kind: "rule" });
      return;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({
        id: createId("heading"),
        kind: "heading",
        level: Math.min(4, heading[1].length + 1) as 2 | 3 | 4,
        text: heading[2],
      });
      return;
    }

    const list = /^(?:[-*]|\d+[.)])\s+(.+)$/.exec(line);
    if (list) {
      flushParagraph();
      listItems.push(list[1]);
      return;
    }

    flushList();
    paragraph.push(line);
  });

  flushParagraph();
  flushList();

  if (codeLines.length > 0) {
    blocks.push({ id: createId("code"), kind: "code", text: codeLines.join("\n") });
  }

  return blocks;
}

function cleanDisplayText(text: string): string {
  return text
    .split(/\r?\n/)
    .map((line) => line.replace(/<\/?div[^>]*>/gi, "").trim())
    .filter((line) => line && !/^<\/?[a-z][^>]*>$/i.test(line))
    .join("\n");
}

function isMarkdownTableRow(line = ""): boolean {
  const trimmed = line.trim();
  return trimmed.includes("|") && trimmed.replaceAll("|", "").trim().length > 0;
}

function isMarkdownTableSeparator(line = ""): boolean {
  const trimmed = line.trim();
  return /^\|?[\s:-]+\|[\s|:-]+\|?$/.test(trimmed) && trimmed.includes("-");
}

function splitMarkdownTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => stripMarkdown(cell.trim()));
}

function stripMarkdown(value: string): string {
  return value
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/<[^>]+>/g, "")
    .trim();
}

function parseMetricValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value !== "string") {
    return null;
  }

  const cleaned = value
    .replace(/\*\*/g, "")
    .replace(/[$,%]/g, "")
    .replace(/[^\d.,\-]/g, "")
    .replace(/,/g, "");

  if (!cleaned || cleaned === "-" || cleaned === "." || cleaned === "-.") {
    return null;
  }

  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function tryParseJson(value: unknown): unknown | null {
  if (typeof value !== "string") {
    return null;
  }

  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function extractFencedJson(text: string): unknown | null {
  const match = /```(?:json)?\s*([\s\S]*?)```/i.exec(text);
  return match ? tryParseJson(match[1]) : null;
}

function firstString(...values: unknown[]): string | undefined {
  return values.find((value): value is string => typeof value === "string" && value.length > 0);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function createId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
