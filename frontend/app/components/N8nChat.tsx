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
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
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

type ChartKind = "bar" | "line" | "scatter" | "area" | "pie" | "donut" | "histogram" | "bubble" | "combo";
type ChartMode = "grouped" | "stacked";

type ChartSpec = {
  id: string;
  type: ChartKind;
  title: string;
  xKey: string;
  yKeys: string[];
  zKey?: string;
  mode?: ChartMode;
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
  suggestions?: string[];
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
  "¿Cuáles son las 5 zonas con mayor % Lead Penetration esta semana?",
  "Compara el Perfect Order entre zonas Wealthy y Non Wealthy en México",
  "Muestra la evolución de Gross Profit UE en Chapinero últimas 8 semanas",
  "¿Cuál es el promedio de Lead Penetration por país?",
  "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Order?",
  "¿Cuáles son las zonas que más crecen en órdenes en las últimas 5 semanas y qué podría explicar el crecimiento?",
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
  const isArea = chart.type === "area";
  const isCombo = chart.type === "combo";
  const isPie = chart.type === "pie" || chart.type === "donut";
  const isScatter = chart.type === "scatter" || chart.type === "bubble";
  const primaryYKey = chart.yKeys[0];
  const tooltipStyle = {
    background: "#111111",
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: 8,
    color: "#fafafa",
  };

  return (
    <section className="chart-card">
      <div className="result-card-title">
        <BarChart3 size={16} />
        <strong>{chart.title}</strong>
      </div>
      <div className="chart-canvas">
        <ResponsiveContainer width="100%" height="100%">
          {isPie ? (
            <PieChart>
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              <Legend wrapperStyle={{ color: "#ffffff99", fontSize: 11 }} />
              <Pie
                data={chart.data}
                dataKey={primaryYKey}
                nameKey={chart.xKey}
                innerRadius={chart.type === "donut" ? "45%" : 0}
                outerRadius="78%"
                paddingAngle={chart.type === "donut" ? 2 : 1}
              >
                {chart.data.map((_, pointIndex) => (
                  <Cell key={`${chart.id}-slice-${pointIndex}`} fill={CHART_COLORS[pointIndex % CHART_COLORS.length]} />
                ))}
              </Pie>
            </PieChart>
          ) : isScatter ? (
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
              {chart.type === "bubble" && chart.zKey ? <ZAxis dataKey={chart.zKey} range={[55, 320]} /> : null}
              <Tooltip
                contentStyle={tooltipStyle}
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
          ) : isArea ? (
            <AreaChart data={chart.data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={chart.xKey} tick={{ fill: "#ffffff99", fontSize: 11 }} />
              <YAxis tick={{ fill: "#ffffff99", fontSize: 11 }} width={42} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              {chart.yKeys.length > 1 ? <Legend wrapperStyle={{ color: "#ffffff99", fontSize: 11 }} /> : null}
              {chart.yKeys.map((key, index) => (
                <Area
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[index % CHART_COLORS.length]}
                  fill={CHART_COLORS[index % CHART_COLORS.length]}
                  fillOpacity={0.24}
                  stackId={chart.mode === "stacked" ? "stack" : undefined}
                />
              ))}
            </AreaChart>
          ) : isCombo ? (
            <ComposedChart data={chart.data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={chart.xKey} tick={{ fill: "#ffffff99", fontSize: 11 }} />
              <YAxis tick={{ fill: "#ffffff99", fontSize: 11 }} width={42} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              <Legend wrapperStyle={{ color: "#ffffff99", fontSize: 11 }} />
              <Bar dataKey={primaryYKey} fill={CHART_COLORS[0]} radius={[5, 5, 0, 0]} />
              {chart.yKeys.slice(1).map((key, index) => (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={CHART_COLORS[(index + 1) % CHART_COLORS.length]}
                  strokeWidth={2.4}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                />
              ))}
            </ComposedChart>
          ) : isLine ? (
            <LineChart data={chart.data} margin={{ top: 8, right: 18, bottom: 6, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
              <XAxis dataKey={chart.xKey} tick={{ fill: "#ffffff99", fontSize: 11 }} />
              <YAxis tick={{ fill: "#ffffff99", fontSize: 11 }} width={42} />
              <Tooltip
                contentStyle={tooltipStyle}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              {chart.yKeys.length > 1 ? <Legend wrapperStyle={{ color: "#ffffff99", fontSize: 11 }} /> : null}
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
                contentStyle={tooltipStyle}
                itemStyle={{ color: "#fafafa" }}
                labelStyle={{ color: "#ffffff99" }}
              />
              {chart.yKeys.length > 1 ? <Legend wrapperStyle={{ color: "#ffffff99", fontSize: 11 }} /> : null}
              {chart.yKeys.map((key, index) => (
                <Bar
                  key={key}
                  dataKey={key}
                  radius={chart.mode === "stacked" ? [0, 0, 0, 0] : [5, 5, 0, 0]}
                  stackId={chart.mode === "stacked" ? "stack" : undefined}
                >
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
  const embeddedJsonObjects = extractEmbeddedJsonObjects(text);
  const candidates = [jsonText, fencedJson, ...embeddedJsonObjects, payloadObject].filter(isRecord);

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
  const tables = normalizeTables(candidate.table ?? candidate.tables ?? candidate.rows);
  const explicitCharts = normalizeCharts(candidate.chart ?? candidate.charts);
  const charts =
    explicitCharts.length > 0
      ? explicitCharts
      : (tables.map((table) => chartFromTable(table, null)).filter(Boolean) as ChartSpec[]);
  const exports = normalizeExports(candidate.exports ?? candidate.exportLinks ?? candidate.files);
  const suggestions = normalizeSuggestions(
    candidate.suggestions ?? candidate.suggested_followups ?? candidate.followups ?? candidate.follow_ups,
  );

  if (
    !answer &&
    tables.length === 0 &&
    charts.length === 0 &&
    exports.length === 0 &&
    suggestions.length === 0
  ) {
    return null;
  }

  return {
    answer,
    tables,
    charts,
    exports,
    suggestions,
  };
}

function buildMessagePresentation(message: ChatMessage) {
  const structured = message.structured ?? parseStructuredContent(message.text, null);
  const textSource = structured?.answer || message.text;
  const markdownTables = parseMarkdownTables(textSource);
  const structuredTables = structured?.tables ?? [];
  const tables = [...structuredTables, ...markdownTables.tables];
  const structuredCharts = structured?.charts ?? [];
  const requestedChartType = inferRequestedChartType(message.text);
  const heuristicCharts = tables
    .map((table) => chartFromTable(table, requestedChartType))
    .filter(Boolean) as ChartSpec[];
  const exports = [
    ...(structured?.exports ?? []),
    ...extractExportLinks(message.text),
  ];
  const charts = structuredCharts.length > 0 ? structuredCharts : heuristicCharts;
  const text = ensureSuggestionSection(markdownTables.textWithoutTables || textSource, {
    enabled:
      message.sender === "bot" &&
      message.status !== "error" &&
      (tables.length > 0 || charts.length > 0),
    suggestions: structured?.suggestions,
  });

  return {
    text,
    tables,
    charts,
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

function chartFromTable(table: ParsedTable, requestedType: ChartKind | null = null): ChartSpec | null {
  if (table.rows.length < 2 || table.headers.length < 2) {
    return null;
  }

  const headers = table.headers.filter((header) => header !== "#");
  const isSegmentComparison = isSmallSegmentComparisonTable(table, headers);

  if ((requestedType === "scatter" || requestedType === "bubble") && !isSegmentComparison) {
    return scatterChartFromTable(table, headers, requestedType === "bubble" ? "bubble" : "scatter");
  }

  const timeKey = selectTimeKey(headers);
  if ((requestedType === "line" || requestedType === "area" || timeKey) && timeKey) {
    return lineChartFromTable(table, headers, timeKey, requestedType === "area" ? "area" : "line");
  }

  const xKey = selectCategoryKey(headers, table.rows);
  const yKeys = selectPlottableMetricKeys(headers, table.rows, xKey).slice(
    0,
    isSegmentComparison ? 1 : 2,
  );

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
  const type =
    requestedType && ["area", "pie", "donut", "histogram", "combo"].includes(requestedType)
      ? requestedType
      : requestedType === "line" || isTrend
        ? "line"
        : "bar";

  return {
    id: createId("chart"),
    type,
    title,
    xKey,
    yKeys,
    data,
  };
}

function lineChartFromTable(
  table: ParsedTable,
  headers: string[],
  xKey: string,
  type: Extract<ChartKind, "line" | "area"> = "line",
): ChartSpec | null {
  const yKey = selectPlottableMetricKeys(headers, table.rows, xKey)[0];
  if (!yKey) {
    return null;
  }

  const seriesKey = selectSeriesKey(headers, xKey, yKey);
  if (!seriesKey) {
    const data = table.rows
      .map((row) => {
        const value = parseMetricValue(row[yKey]);
        if (value === null) {
          return null;
        }

        return {
          [xKey]: stripMarkdown(row[xKey] || ""),
          [yKey]: value,
        };
      })
      .filter((row): row is Record<string, string | number> => Boolean(row));

    if (data.length < 2) {
      return null;
    }

    return {
      id: createId("chart"),
      type,
      title: `Trend: ${yKey}`,
      xKey,
      yKeys: [yKey],
      data: sortLineData(data, xKey),
    };
  }

  const xLabels = orderedLabels(table.rows.map((row) => stripMarkdown(row[xKey] || "")));
  const seriesLabels = orderedLabels(table.rows.map((row) => stripMarkdown(row[seriesKey] || ""))).slice(0, 10);
  const pointsByX = new Map<string, Record<string, string | number>>();
  xLabels.forEach((label) => {
    pointsByX.set(label, { [xKey]: label });
  });

  table.rows.forEach((row) => {
    const xLabel = stripMarkdown(row[xKey] || "");
    const seriesLabel = stripMarkdown(row[seriesKey] || "");
    const value = parseMetricValue(row[yKey]);
    if (!xLabel || !seriesLabel || value === null || !seriesLabels.includes(seriesLabel)) {
      return;
    }

    const point = pointsByX.get(xLabel);
    if (point) {
      point[seriesLabel] = value;
    }
  });

  const data = Array.from(pointsByX.values()).filter((point) =>
    seriesLabels.some((seriesLabel) => typeof point[seriesLabel] === "number"),
  );

  if (data.length < 2 || seriesLabels.length === 0) {
    return null;
  }

  return {
    id: createId("chart"),
    type,
    title: `Trend: ${yKey} by ${seriesKey}`,
    xKey,
    yKeys: seriesLabels,
    data,
  };
}

function scatterChartFromTable(
  table: ParsedTable,
  headers: string[],
  type: Extract<ChartKind, "scatter" | "bubble"> = "scatter",
): ChartSpec | null {
  const numericKeys = headers.filter((header) =>
    table.rows.some((row) => parseMetricValue(row[header]) !== null),
  );

  if (numericKeys.length < 2) {
    return null;
  }

  const xKey = numericKeys.find(isCountLikeKey) ?? numericKeys[0];
  const yKey =
    selectPrimaryMetricKeys(numericKeys, table.rows, xKey)[0] ??
    numericKeys.find((key) => key !== xKey);
  const zKey = type === "bubble" ? numericKeys.find((key) => key !== xKey && key !== yKey) : undefined;

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
      if (zKey) {
        const zValue = parseMetricValue(row[zKey]);
        if (zValue !== null) {
          point[zKey] = zValue;
        }
      }

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
    type,
    title: `Scatter: ${yKey} by ${xKey}`,
    xKey,
    yKeys: [yKey],
    zKey,
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

function selectTimeKey(headers: string[]): string | null {
  return headers.find((header) => /week_label|semana|week|fecha|date/i.test(header)) ?? null;
}

function selectSeriesKey(headers: string[], xKey: string, yKey: string): string | null {
  const candidates = headers.filter((header) => header !== xKey && header !== yKey);
  for (const pattern of [/^zone$/i, /zona/i, /zone_type/i, /city|ciudad/i, /country|pa[ií]s/i, /segment/i, /metric|m[eé]trica/i]) {
    const match = candidates.find((header) => pattern.test(header));
    if (match) {
      return match;
    }
  }
  return null;
}

function selectPrimaryMetricKeys(
  headers: string[],
  rows: Record<string, string>[],
  xKey: string,
): string[] {
  return headers
    .filter((header) => header !== xKey)
    .filter((header) => rows.some((row) => parseMetricValue(row[header]) !== null))
    .filter((header) => !isCountLikeKey(header) && !isMinMaxLikeKey(header))
    .filter((header) => !/variaci[oó]n|orders total|total órdenes/i.test(header))
    .sort((left, right) => metricColumnPriority(left) - metricColumnPriority(right));
}

function selectPlottableMetricKeys(
  headers: string[],
  rows: Record<string, string>[],
  xKey: string,
): string[] {
  const primary = selectPrimaryMetricKeys(headers, rows, xKey);
  if (primary.length > 0) {
    return primary;
  }

  return headers
    .filter((header) => header !== xKey)
    .filter((header) => rows.some((row) => parseMetricValue(row[header]) !== null))
    .filter((header) => !isMinMaxLikeKey(header))
    .sort((left, right) => metricColumnPriority(left) - metricColumnPriority(right));
}

function metricColumnPriority(key: string): number {
  const normalized = key.toLowerCase();
  if (/^(avg|average|promedio|mean)_/.test(normalized) || normalized === "value") {
    return 0;
  }
  if (/penetration|perfect|gross_profit|profit|order|rate|pct|percent/.test(normalized)) {
    return 1;
  }
  return 2;
}

function isSmallSegmentComparisonTable(table: ParsedTable, headers: string[]): boolean {
  if (table.rows.length > 6) {
    return false;
  }

  return headers.some((header) => /zone_type|segment|tipo|wealthy/i.test(header));
}

function orderedLabels(values: string[]): string[] {
  const labels = values.filter(Boolean);
  const unique = Array.from(new Set(labels));
  if (unique.every((label) => /^L\d+W$/i.test(label))) {
    return unique.sort((left, right) => Number(right.slice(1, -1)) - Number(left.slice(1, -1)));
  }
  return unique;
}

function sortLineData(data: Record<string, string | number>[], xKey: string) {
  const labels = orderedLabels(data.map((row) => String(row[xKey] ?? "")));
  const order = new Map(labels.map((label, index) => [label, index]));
  return [...data].sort(
    (left, right) =>
      (order.get(String(left[xKey] ?? "")) ?? Number.MAX_SAFE_INTEGER) -
      (order.get(String(right[xKey] ?? "")) ?? Number.MAX_SAFE_INTEGER),
  );
}

function normalizeTables(value: unknown): ParsedTable[] {
  const rawTables = Array.isArray(value) ? value : value ? [value] : [];

  return rawTables.flatMap((item, index) => {
    if (Array.isArray(item)) {
      return tableFromRows(item, `structured-table-${index}`);
    }

    if (isRecord(item)) {
      const rows = item.rows ?? item.data;
      const headers = item.headers ?? item.header ?? item.columns;
      if (Array.isArray(headers) && Array.isArray(rows)) {
        return tableFromMatrix(headers, rows, `structured-table-${index}`);
      }
      if (Array.isArray(rows)) {
        return tableFromRows(rows, `structured-table-${index}`);
      }
    }

    return [];
  });
}

function tableFromMatrix(headersInput: unknown[], rows: unknown[], id: string): ParsedTable[] {
  const headers = headersInput.map((header) => String(header ?? "")).filter(Boolean);
  if (headers.length === 0 || rows.length === 0) {
    return [];
  }

  const normalizedRows = rows
    .map((row) => {
      if (Array.isArray(row)) {
        return Object.fromEntries(
          headers.map((header, cellIndex) => [header, String(row[cellIndex] ?? "")]),
        );
      }

      if (isRecord(row)) {
        return Object.fromEntries(headers.map((header) => [header, String(row[header] ?? "")]));
      }

      return null;
    })
    .filter((row): row is Record<string, string> => Boolean(row));

  return normalizedRows.length > 0 ? [{ id, headers, rows: normalizedRows }] : [];
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

    const rawType = firstString(item.type, item.kind, item.chartType, item.visualization);
    const type = normalizeChartType(rawType);
    const extracted = extractChartData(item, type);

    if (!extracted) {
      return [];
    }

    const rows = extracted.data
      .map((row) => normalizeChartRow(row, extracted.xKey, extracted.yKeys, type, extracted.zKey))
      .filter((row) => {
        if (!isNumericPointChart(type)) {
          return true;
        }

        return typeof row[extracted.xKey] === "number" && typeof row[extracted.yKeys[0]] === "number";
      });
    const yKeys = extracted.yKeys.filter((key) =>
      rows.some((row) => typeof row[key] === "number"),
    );

    if (rows.length === 0 || yKeys.length === 0) {
      return [];
    }

    return [
      {
        id: `structured-chart-${index}`,
        type,
        title: firstString(item.title, item.name, item.label) || defaultChartTitle(type),
        xKey: extracted.xKey,
        yKeys,
        zKey: extracted.zKey,
        mode: normalizeChartMode(item, rawType),
        data: rows,
      },
    ];
  });
}

type ExtractedChartData = {
  data: Record<string, unknown>[];
  xKey: string;
  yKeys: string[];
  zKey?: string;
};

function extractChartData(item: Record<string, unknown>, type: ChartKind): ExtractedChartData | null {
  const labelDatasetRows = extractLabelDatasetRows(item);
  if (labelDatasetRows) {
    return labelDatasetRows;
  }

  const labelValueRows = extractLabelValueRows(item);
  if (labelValueRows) {
    return labelValueRows;
  }

  const xyRows = extractXyRows(item);
  if (xyRows) {
    return xyRows;
  }

  const histogramRows = extractHistogramRows(item, type);
  if (histogramRows) {
    return histogramRows;
  }

  const rawRows = rawChartRows(item);
  if (rawRows.length === 0) {
    return null;
  }

  const xKey = firstString(item.xKey, item.x, item.category, item.nameKey, item.labelKey) || inferChartXKey(rawRows, type);
  if (!xKey) {
    return null;
  }

  let zKey = firstString(item.zKey, item.sizeKey, item.radiusKey);
  let yKeys = explicitYKeys(item);
  if (yKeys.length === 0) {
    yKeys = inferChartYKeys(rawRows, xKey, zKey, type);
  }
  if (!zKey && type === "bubble") {
    zKey = inferBubbleZKey(rawRows, xKey, yKeys[0]);
  }

  return yKeys.length > 0 ? { data: rawRows, xKey, yKeys, zKey } : null;
}

function extractLabelDatasetRows(item: Record<string, unknown>): ExtractedChartData | null {
  for (const source of chartObjectSources(item)) {
    const labels = arrayValue(source.labels) ?? arrayValue(source.categories);
    const datasets = arrayValue(source.datasets) ?? arrayValue(source.series);
    const datasetRecords = datasets?.filter(isRecord) ?? [];
    if (!labels || labels.length === 0 || datasetRecords.length === 0) {
      continue;
    }

    const xKey = firstString(item.xKey, item.x, item.category, item.nameKey, item.labelKey) || "label";
    const rows = labels.map((label) => ({ [xKey]: label }));
    const yKeys: string[] = [];

    datasetRecords.forEach((dataset, datasetIndex) => {
      const yKey =
        firstString(dataset.label, dataset.name, dataset.key, dataset.metric, dataset.yKey) ||
        `value_${datasetIndex + 1}`;
      const values = arrayValue(dataset.data) ?? arrayValue(dataset.values);
      if (!values || values.length === 0) {
        return;
      }

      yKeys.push(yKey);
      values.forEach((value, valueIndex) => {
        if (rows[valueIndex]) {
          rows[valueIndex][yKey] = chartPointValue(value, yKey);
        }
      });
    });

    if (yKeys.length > 0) {
      return { data: rows, xKey, yKeys };
    }
  }

  return null;
}

function extractLabelValueRows(item: Record<string, unknown>): ExtractedChartData | null {
  for (const source of chartObjectSources(item)) {
    const labels = arrayValue(source.labels) ?? arrayValue(source.categories);
    const values = arrayValue(source.values) ?? arrayValue(source.y);
    if (!labels || !values || labels.length === 0 || values.length === 0) {
      continue;
    }

    const xKey = firstString(item.xKey, item.x, item.category, item.nameKey, item.labelKey) || "label";
    const yKey = firstString(item.yKey, item.metric, item.valueKey) || "value";
    const rows = labels.map((label, index) => ({
      [xKey]: label,
      [yKey]: chartPointValue(values[index], yKey),
    }));
    return { data: rows, xKey, yKeys: [yKey] };
  }

  return null;
}

function extractXyRows(item: Record<string, unknown>): ExtractedChartData | null {
  const xValues = arrayValue(item.x);
  const yValues = arrayValue(item.y);
  if (!xValues || !yValues || xValues.length === 0 || yValues.length === 0) {
    return null;
  }

  const xKey = firstString(item.xKey, item.category, item.nameKey, item.labelKey) || "x";
  const yKey = firstString(item.yKey, item.metric, item.valueKey) || "y";
  const rows = xValues.map((xValue, index) => ({
    [xKey]: xValue,
    [yKey]: chartPointValue(yValues[index], yKey),
  }));

  return { data: rows, xKey, yKeys: [yKey] };
}

function extractHistogramRows(item: Record<string, unknown>, type: ChartKind): ExtractedChartData | null {
  if (type !== "histogram") {
    return null;
  }

  const rawValues = arrayValue(item.values) ?? arrayValue(item.data);
  const values = (rawValues ?? [])
    .map((value) => parseMetricValue(value))
    .filter((value): value is number => value !== null);
  if (values.length < 2) {
    return null;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    return {
      data: [{ bin: String(min), count: values.length }],
      xKey: "bin",
      yKeys: ["count"],
    };
  }

  const binCount = Math.min(10, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const width = (max - min) / binCount;
  const bins = Array.from({ length: binCount }, (_, index) => ({
    start: min + index * width,
    end: index === binCount - 1 ? max : min + (index + 1) * width,
    count: 0,
  }));

  values.forEach((value) => {
    const index = Math.min(binCount - 1, Math.floor((value - min) / width));
    bins[index].count += 1;
  });

  return {
    data: bins.map((bin) => ({
      bin: `${formatCompactNumber(bin.start)}-${formatCompactNumber(bin.end)}`,
      count: bin.count,
    })),
    xKey: "bin",
    yKeys: ["count"],
  };
}

function rawChartRows(item: Record<string, unknown>): Record<string, unknown>[] {
  const data = arrayValue(item.data);
  if (data) {
    const rows = data.filter(isRecord);
    if (rows.length > 0) {
      return rows;
    }
  }

  const points = arrayValue(item.points);
  return points?.filter(isRecord) ?? [];
}

function chartObjectSources(item: Record<string, unknown>): Record<string, unknown>[] {
  const sources: Record<string, unknown>[] = [item];
  if (isRecord(item.data)) {
    sources.push(item.data);
  }
  if (isRecord(item.chartjs) && isRecord(item.chartjs.data)) {
    sources.push(item.chartjs.data);
  }
  return sources;
}

function explicitYKeys(item: Record<string, unknown>): string[] {
  const candidate = item.yKeys ?? item.yKey ?? item.metric ?? item.valueKey;
  if (Array.isArray(candidate)) {
    return candidate.filter((key): key is string => typeof key === "string" && key.trim().length > 0);
  }
  if (typeof candidate === "string" && candidate.trim()) {
    return [candidate.trim()];
  }
  if (typeof item.y === "string" && item.y.trim()) {
    return [item.y.trim()];
  }
  return [];
}

function inferChartXKey(rows: Record<string, unknown>[], type: ChartKind): string | null {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  if (keys.length === 0) {
    return null;
  }

  const preferred =
    type === "scatter" || type === "bubble"
      ? ["x"]
      : ["label", "name", "category", "x", "week_label", "week", "date", "zone", "city", "country"];
  for (const key of preferred) {
    const match = keys.find((candidate) => candidate.toLowerCase() === key);
    if (match) {
      return match;
    }
  }

  return keys.find((key) => rows.some((row) => parseMetricValue(row[key]) === null)) ?? keys[0];
}

function inferChartYKeys(
  rows: Record<string, unknown>[],
  xKey: string,
  zKey: string | undefined,
  type: ChartKind,
): string[] {
  const numericKeys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
    .filter((key) => key !== xKey && key !== zKey)
    .filter((key) => rows.some((row) => parseMetricValue(row[key]) !== null));

  if ((type === "scatter" || type === "bubble") && numericKeys.includes("y")) {
    return ["y"];
  }
  if (numericKeys.includes("value")) {
    return ["value"];
  }
  return numericKeys.slice(0, type === "line" || type === "area" || type === "combo" ? 8 : 4);
}

function inferBubbleZKey(
  rows: Record<string, unknown>[],
  xKey: string,
  yKey: string | undefined,
): string | undefined {
  const preferred = ["z", "size", "radius", "volume", "count", "n", "orders"];
  const numericKeys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
    .filter((key) => key !== xKey && key !== yKey)
    .filter((key) => rows.some((row) => parseMetricValue(row[key]) !== null));
  for (const key of preferred) {
    const match = numericKeys.find((candidate) => candidate.toLowerCase() === key);
    if (match) {
      return match;
    }
  }
  return numericKeys[0];
}

function chartPointValue(value: unknown, key: string): unknown {
  if (!isRecord(value)) {
    return value;
  }

  return value[key] ?? value.y ?? value.value ?? value.count ?? value.total ?? value.x ?? "";
}

function arrayValue(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

function isNumericPointChart(type: ChartKind): boolean {
  return type === "scatter" || type === "bubble";
}

function normalizeChartMode(item: Record<string, unknown>, rawType?: string): ChartMode | undefined {
  const text = `${rawType ?? ""} ${firstString(item.mode, item.variant, item.layout) ?? ""}`
    .toLowerCase()
    .replace(/[_-]+/g, " ");
  if (item.stacked === true || /\bstack(?:ed)?\b/.test(text)) {
    return "stacked";
  }
  if (/\bgroup(?:ed)?\b/.test(text)) {
    return "grouped";
  }
  return undefined;
}

function normalizeSuggestions(value: unknown): string[] {
  const rawSuggestions = Array.isArray(value) ? value : value ? [value] : [];

  return rawSuggestions
    .flatMap((item) => {
      if (typeof item !== "string") {
        return [];
      }

      return item
        .split(/\n|(?=\s*[1-3][.)]\s+)/)
        .map((suggestion) =>
          suggestion
            .replace(/^\s*(?:[-*]|\d+[.)])\s*/, "")
            .trim(),
        )
        .filter(Boolean);
    })
    .slice(0, 3);
}

function normalizeChartRow(
  row: Record<string, unknown>,
  xKey: string,
  yKeys: string[],
  type: ChartKind,
  zKey?: string,
) {
  const parsedX = parseMetricValue(row[xKey]);
  const normalized: Record<string, string | number> = {
    [xKey]: isNumericPointChart(type) && parsedX !== null ? parsedX : String(row[xKey] ?? ""),
  };

  yKeys.forEach((key) => {
    const parsed = parseMetricValue(row[key]);
    if (parsed !== null) {
      normalized[key] = parsed;
    }
  });
  if (zKey) {
    const parsed = parseMetricValue(row[zKey]);
    if (parsed !== null) {
      normalized[zKey] = parsed;
    }
  }

  return normalized;
}

function inferRequestedChartType(text: string): ChartKind | null {
  if (/\b(bubble|burbuja)\b/i.test(text)) {
    return "bubble";
  }

  if (/\b(scatter|dispersi[oó]n)\b/i.test(text)) {
    return "scatter";
  }

  if (/\b(area|área)\b/i.test(text)) {
    return "area";
  }

  if (/\b(line|l[ií]nea|trend|tendencia|time series|serie temporal|evoluci[oó]n)\b/i.test(text)) {
    return "line";
  }

  if (/\b(pie|pastel|torta)\b/i.test(text)) {
    return "pie";
  }

  if (/\b(donut|doughnut|dona)\b/i.test(text)) {
    return "donut";
  }

  if (/\b(histogram|histograma|distribution|distribuci[oó]n)\b/i.test(text)) {
    return "histogram";
  }

  if (/\b(combo|combined|combinad[ao]|mixed|mixt[ao])\b/i.test(text)) {
    return "combo";
  }

  if (/\b(bar|barra|column|columna)\b/i.test(text)) {
    return "bar";
  }

  return null;
}

function normalizeChartType(value: unknown): ChartKind {
  if (typeof value !== "string") {
    return "bar";
  }

  const normalized = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  if (["scatter", "scatterplot", "scatter_plot", "dispersion", "dispersion_plot"].includes(normalized)) {
    return "scatter";
  }
  if (["bubble", "bubble_chart"].includes(normalized)) {
    return "bubble";
  }
  if (["line", "line_chart", "trend", "timeseries", "time_series"].includes(normalized)) {
    return "line";
  }
  if (["area", "area_chart", "stacked_area"].includes(normalized)) {
    return "area";
  }
  if (["pie", "pie_chart"].includes(normalized)) {
    return "pie";
  }
  if (["donut", "doughnut", "donut_chart", "doughnut_chart"].includes(normalized)) {
    return "donut";
  }
  if (["histogram", "histograma", "distribution"].includes(normalized)) {
    return "histogram";
  }
  if (["combo", "combined", "composed", "mixed", "dual_axis"].includes(normalized)) {
    return "combo";
  }

  return "bar";
}

function defaultChartTitle(type: ChartKind): string {
  const titles: Record<ChartKind, string> = {
    area: "Area chart",
    bar: "Bar chart",
    bubble: "Bubble chart",
    combo: "Combo chart",
    donut: "Donut chart",
    histogram: "Histogram",
    line: "Line chart",
    pie: "Pie chart",
    scatter: "Scatter chart",
  };
  return titles[type];
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
        label:
          kind === "file"
            ? firstString(item.label, item.name) || labelForKind(kind)
            : labelForKind(kind),
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
  const cleaned = text
    .split(/\r?\n/)
    .map((line) => line.replace(/<\/?div[^>]*>/gi, "").trim())
    .filter((line) => line && !/^<\/?[a-z][^>]*>$/i.test(line))
    .join("\n");

  return normalizeSuggestionMarkdown(cleaned);
}

function ensureSuggestionSection(
  text: string,
  options: { enabled: boolean; suggestions?: string[] },
): string {
  const normalizedText = normalizeSuggestionMarkdown(text);

  if (!options.enabled || hasSuggestionSection(normalizedText)) {
    return normalizedText;
  }

  const heading = isSpanishText(normalizedText) ? "Sugerencias" : "Suggestions";
  const suggestions =
    options.suggestions && options.suggestions.length > 0
      ? options.suggestions
      : defaultSuggestions(heading);
  const suggestionBlock = suggestions
    .slice(0, 3)
    .map((suggestion, index) => `${index + 1}. ${suggestion}`)
    .join("\n");

  return [normalizedText.trimEnd(), `### ${heading}\n${suggestionBlock}`]
    .filter(Boolean)
    .join("\n\n");
}

function hasSuggestionSection(text: string): boolean {
  return /(?:^|\n)#{1,4}\s+(?:Sugerencias|Suggestions)\b/i.test(text);
}

function defaultSuggestions(heading: "Sugerencias" | "Suggestions"): string[] {
  if (heading === "Sugerencias") {
    return [
      "Ver la tendencia de este resultado en las ultimas 8 semanas.",
      "Comparar el resultado por pais, ciudad o tipo de zona.",
      "Exportar este resultado a CSV o PDF.",
    ];
  }

  return [
    "View this result as an 8-week trend.",
    "Compare the result by country, city, or zone type.",
    "Export this result to CSV or PDF.",
  ];
}

function isSpanishText(text: string): boolean {
  return /\b(las|los|zonas|semana|actual|mexico|colombia|argentina|pais|exportar|comparar|tendencia|ultimas|outliers)\b/i.test(
    stripAccents(text),
  );
}

function stripAccents(value: string): string {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function normalizeSuggestionMarkdown(text: string): string {
  const marker = /\b(Sugerencias|Suggestions):\s*/i.exec(text);
  if (!marker) {
    return text;
  }

  const before = text.slice(0, marker.index).trimEnd();
  const heading = marker[1].toLowerCase().startsWith("suger")
    ? "Sugerencias"
    : "Suggestions";
  const remainder = text.slice(marker.index + marker[0].length).trim();
  const items = Array.from(
    remainder.matchAll(/(?:^|\s)([1-3])[.)]\s+([\s\S]*?)(?=\s[1-3][.)]\s+|$)/g),
  ).map((match) => `${match[1]}. ${match[2].trim()}`);

  if (items.length < 2) {
    return text;
  }

  return [before, `### ${heading}\n${items.join("\n")}`].filter(Boolean).join("\n\n");
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

function formatCompactNumber(value: number): string {
  if (!Number.isFinite(value)) {
    return "";
  }
  if (Math.abs(value) >= 1000) {
    return value.toLocaleString("en", { maximumFractionDigits: 0 });
  }
  if (Math.abs(value) >= 10) {
    return value.toLocaleString("en", { maximumFractionDigits: 1 });
  }
  return value.toLocaleString("en", { maximumFractionDigits: 2 });
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

function extractEmbeddedJsonObjects(text: string): Record<string, unknown>[] {
  const objects: Record<string, unknown>[] = [];

  for (let index = 0; index < text.length; index += 1) {
    if (text[index] !== "{") {
      continue;
    }

    const end = findJsonObjectEnd(text, index);
    if (end === -1) {
      continue;
    }

    const parsed = tryParseJson(text.slice(index, end + 1));
    if (isRecord(parsed)) {
      objects.push(parsed);
      index = end;
    }
  }

  return objects.sort((left, right) => structuredCandidateScore(right) - structuredCandidateScore(left));
}

function findJsonObjectEnd(text: string, start: number): number {
  let depth = 0;
  let inString = false;
  let escaped = false;

  for (let index = start; index < text.length; index += 1) {
    const char = text[index];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === "\"") {
        inString = false;
      }
      continue;
    }

    if (char === "\"") {
      inString = true;
      continue;
    }

    if (char === "{") {
      depth += 1;
      continue;
    }

    if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }

  return -1;
}

function structuredCandidateScore(candidate: Record<string, unknown>): number {
  let score = 0;
  if ("answer" in candidate) score += 8;
  if ("tables" in candidate || "table" in candidate || "rows" in candidate) score += 4;
  if ("charts" in candidate || "chart" in candidate) score += 3;
  if ("exports" in candidate || "exportLinks" in candidate || "files" in candidate) score += 2;
  if ("suggestions" in candidate || "suggested_followups" in candidate) score += 1;
  return score;
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
