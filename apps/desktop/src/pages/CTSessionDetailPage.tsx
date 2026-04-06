import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EventRecord, JsonValue } from "../lib/types";
import {
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessionConversationGraph,
  fetchPmSessionMetrics,
  type EventsStream,
  postPmSessionMessage,
  openEventsStream,
} from "../lib/api";
import { badgeClass, statusLabelZh } from "../lib/statusPresentation";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card, CardHeader, CardTitle } from "../components/ui/Card";
import { Input, Textarea } from "../components/ui/Input";

/* ── constants ── */
const BASE_INTERVAL = 1500;
const MAX_INTERVAL = 8000;
const SSE_FAIL_LIMIT = 3;
const SSE_MERGE_WINDOW = 800;
const REQUEST_TIMEOUT_MS = 6000;

/* ── types ── */
type Transport = "sse" | "polling";
type LiveMode = "running" | "paused" | "stopped" | "backoff";

function statusLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  const labels: Record<string, string> = {
    active: "Active",
    archived: "Archived",
    blocked: "Blocked",
    done: "Done",
    failed: "Failed",
    paused: "Paused",
    running: "Running",
    success: "Success",
  };
  return labels[normalized] || statusLabelZh(status);
}

function isTerminal(status: string) {
  const s = (status || "").toLowerCase();
  return ["completed", "failed", "cancelled", "rejected", "stopped", "done", "archived"].includes(s);
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException &&
    error.name === "AbortError"
  );
}

function toEventTimestampMs(event: EventRecord): number {
  const raw = event.ts;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const numeric = Number(raw);
    if (Number.isFinite(numeric)) return numeric;
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

function resolveSessionStatus(payload: Record<string, JsonValue>): string {
  const session = payload.session;
  if (!session || typeof session !== "object" || Array.isArray(session)) return "";
  const status = (session as Record<string, JsonValue>).status;
  return typeof status === "string" ? status : "";
}

function isBlockedFlag(value: JsonValue): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return false;
    if (["false", "0", "no", "off", "none", "null"].includes(normalized)) return false;
    return ["true", "1", "yes", "on", "blocked"].includes(normalized);
  }
  return false;
}

/* ── component ── */
export function CTSessionDetailPage({
  sessionId,
  onBack,
}: {
  sessionId: string;
  onBack: () => void;
}) {
  const sessionIdSlug = sessionId.replace(/[^a-zA-Z0-9_-]/g, "-") || "session";
  const liveStatusId = `ct-session-live-status-${sessionIdSlug}`;
  const runTableCaptionId = `ct-session-run-table-caption-${sessionIdSlug}`;
  const messageComposerLabelId = `ct-session-message-label-${sessionIdSlug}`;
  const messageComposerHintId = `ct-session-message-hint-${sessionIdSlug}`;

  /* state */
  const [detail, setDetail] = useState<Record<string, JsonValue> | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [graph, setGraph] = useState<Record<string, JsonValue> | null>(null);
  const [metrics, setMetrics] = useState<Record<string, JsonValue> | null>(null);
  const [liveMode, setLiveMode] = useState<LiveMode>("running");
  const [transport, setTransport] = useState<Transport>("polling");
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  /* PM messaging */
  const [msgDraft, setMsgDraft] = useState("");
  const [msgSending, setMsgSending] = useState(false);
  const [msgStatus, setMsgStatus] = useState("");
  const msgRef = useRef<HTMLTextAreaElement>(null);
  const msgSendingRef = useRef(false);

  /* refs */
  const intervalRef = useRef(BASE_INTERVAL);
  const sseFailRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const sseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSseTs = useRef(0);
  const refreshRequestIdRef = useRef(0);

  /* derived */
  const session = (detail as Record<string, JsonValue>)?.session as Record<string, JsonValue> | undefined;
  const runs = Array.isArray((detail as Record<string, JsonValue>)?.runs) ? (detail as Record<string, JsonValue>).runs as Array<Record<string, JsonValue>> : [];
  const sessionStatus = String(session?.status || "");
  const terminal = isTerminal(sessionStatus);
  const latestRunId = String(session?.latest_run_id || "").trim();

  /* ── refresh ── */
  const refreshAll = useCallback(async () => {
    const requestId = refreshRequestIdRef.current + 1;
    refreshRequestIdRef.current = requestId;
    setRefreshing(true);
    const ctrl = new AbortController();
    abortRef.current?.abort();
    abortRef.current = ctrl;
    try {
      const [d, e, g, m] = await Promise.allSettled([
        fetchPmSession(sessionId, { signal: ctrl.signal, timeoutMs: REQUEST_TIMEOUT_MS }),
        fetchPmSessionEvents(sessionId, { limit: 500, tail: true, signal: ctrl.signal, timeoutMs: REQUEST_TIMEOUT_MS }),
        fetchPmSessionConversationGraph(sessionId, "24h", { signal: ctrl.signal, timeoutMs: REQUEST_TIMEOUT_MS }),
        fetchPmSessionMetrics(sessionId, { signal: ctrl.signal, timeoutMs: REQUEST_TIMEOUT_MS }),
      ]);
      if (refreshRequestIdRef.current !== requestId) return;
      if (d.status === "fulfilled") setDetail(d.value);
      if (e.status === "fulfilled") setEvents(Array.isArray(e.value) ? e.value : []);
      if (g.status === "fulfilled") setGraph(g.value);
      if (m.status === "fulfilled") setMetrics(m.value);

      const failures = [d, e, g, m].filter((r) => r.status === "rejected");
      const nextTerminal = d.status === "fulfilled" ? isTerminal(resolveSessionStatus(d.value as Record<string, JsonValue>)) : terminal;
      const resolvedLiveMode: LiveMode = !liveEnabled
        ? "paused"
        : nextTerminal
          ? "stopped"
          : failures.length > 0
            ? "backoff"
            : "running";
      if (failures.length === 4) throw new Error("All requests failed");
      if (failures.length > 0) {
        setError(`Partial refresh degraded (${failures.length}/4 failed)`);
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL);
        setLiveMode(resolvedLiveMode);
      } else {
        setError("");
        intervalRef.current = BASE_INTERVAL;
        setLiveMode(resolvedLiveMode);
      }
    } catch (err) {
      if (refreshRequestIdRef.current !== requestId || isAbortError(err)) return;
      setError(err instanceof Error ? err.message : String(err));
      intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL);
      setLiveMode(liveEnabled ? "backoff" : "paused");
    } finally {
      if (refreshRequestIdRef.current !== requestId) return;
      setRefreshing(false);
    }
  }, [liveEnabled, sessionId, terminal]);

  /* ── polling ── */
  useEffect(() => {
    if (transport !== "polling" || !liveEnabled || terminal) {
      if (!liveEnabled) setLiveMode("paused");
      if (terminal) setLiveMode("stopped");
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (cancelled) return;
      await refreshAll();
      if (!cancelled) timer = setTimeout(tick, intervalRef.current);
    };
    timer = setTimeout(tick, intervalRef.current);
    return () => { cancelled = true; if (timer) clearTimeout(timer); abortRef.current?.abort(); };
  }, [transport, liveEnabled, terminal, refreshAll]);

  /* ── SSE ── */
  useEffect(() => {
    if (!liveEnabled || terminal || !latestRunId) { setTransport("polling"); return; }
    let stream: EventsStream | null = null;
    let cancelled = false;
    const scheduleRefresh = () => {
      if (sseTimerRef.current) return;
      const elapsed = Date.now() - lastSseTs.current;
      const delay = elapsed >= SSE_MERGE_WINDOW ? 0 : SSE_MERGE_WINDOW - elapsed;
      sseTimerRef.current = setTimeout(() => {
        sseTimerRef.current = null;
        lastSseTs.current = Date.now();
        if (!cancelled) void refreshAll();
      }, delay);
    };
    try {
      stream = openEventsStream(latestRunId, { limit: 100, tail: true });
      setTransport("sse");
    } catch { setTransport("polling"); return; }
    stream.onopen = () => { sseFailRef.current = 0; setTransport("sse"); };
    stream.onmessage = () => { if (!cancelled) scheduleRefresh(); };
    stream.onerror = () => {
      sseFailRef.current++;
      if (sseFailRef.current >= SSE_FAIL_LIMIT) { setTransport("polling"); stream?.close(); }
    };
    return () => { cancelled = true; stream?.close(); if (sseTimerRef.current) { clearTimeout(sseTimerRef.current); sseTimerRef.current = null; } };
  }, [latestRunId, liveEnabled, terminal, refreshAll]);

  /* ── send PM message ── */
  async function handleSend() {
    if (msgSendingRef.current) {
      return;
    }
    const msg = msgDraft.trim();
    if (!msg) return;
    msgSendingRef.current = true;
    setMsgSending(true); setMsgStatus("");
    try {
      await postPmSessionMessage(sessionId, { message: msg, from_role: "PM", to_role: "TECH_LEAD", kind: "chat" });
      setMsgDraft(""); setMsgStatus("Message sent.");
      void refreshAll();
    } catch (err) { setMsgStatus(err instanceof Error ? err.message : "Send failed."); }
    finally {
      msgSendingRef.current = false;
      setMsgSending(false);
    }
  }

  /* ── keyboard shortcuts ── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const k = e.key.toLowerCase();
      const inEdit = ["INPUT", "TEXTAREA", "SELECT"].includes((e.target as HTMLElement)?.tagName);
      if (k === "m") { e.preventDefault(); msgRef.current?.focus(); return; }
      if (inEdit) return;
      if (k === "l") { e.preventDefault(); setLiveEnabled((p) => !p); }
      else if (k === "r") { e.preventDefault(); void refreshAll(); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [refreshAll]);

  /* ── initial load ── */
  useEffect(() => { void refreshAll(); }, [refreshAll]);

  /* ── metrics helpers ── */
  const m = metrics as Record<string, JsonValue> | null;
  const metricItems = m ? [
    { label: "Run count", value: m.run_count },
    { label: "Running", value: m.running_runs },
    { label: "Failed", value: m.failed_runs },
    { label: "Blocked", value: m.blocked_runs },
    { label: "Failure rate", value: `${(Number(m.failure_rate || 0) * 100).toFixed(1)}%` },
    { label: "Avg recovery (s)", value: Number(m.mttr_seconds || 0).toFixed(1) },
  ] : [];

  /* ── conversation graph helpers ── */
  const graphNodes = Array.isArray((graph as Record<string, JsonValue>)?.nodes)
    ? ((graph as Record<string, JsonValue>).nodes as Array<Record<string, JsonValue>>)
    : [];
  const graphEdges = Array.isArray((graph as Record<string, JsonValue>)?.edges)
    ? ((graph as Record<string, JsonValue>).edges as Array<Record<string, JsonValue>>)
    : [];

  /* ── event timeline helpers ── */
  const [evtFilter, setEvtFilter] = useState("");
  const [expandedEvtKey, setExpandedEvtKey] = useState<string | null>(null);
  const eventFilterInputId = `ct-session-event-filter-${sessionIdSlug}`;
  const sortedEvents = useMemo(() => {
    const next = [...events];
    next.sort((a, b) => toEventTimestampMs(b) - toEventTimestampMs(a));
    return next;
  }, [events]);
  const filteredEvents = useMemo(() => {
    if (!evtFilter.trim()) return sortedEvents;
    const needle = evtFilter.toLowerCase();
    return sortedEvents.filter((ev) => JSON.stringify(ev).toLowerCase().includes(needle));
  }, [sortedEvents, evtFilter]);
  const openWebSessionAnalysis = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    const { protocol, hostname, port } = window.location;
    const webPort = port === "1420" ? "3000" : port;
    const webUrl = `${protocol}//${hostname}${webPort ? `:${webPort}` : ""}/command-tower/sessions/${encodeURIComponent(sessionId)}`;
    window.open(webUrl, "_blank", "noopener,noreferrer");
  }, [sessionId]);

  /* ── render ── */
  return (
    <div className="content">
      {/* Header */}
      <div className="section-header">
        <div>
          <Button className="mb-2" onClick={onBack}>
            {"<"} Back to session overview
          </Button>
          <h1 className="page-title">Session detail</h1>
          <p className="page-subtitle">Single-session shell for live trace review, role handoff visibility, and exception convergence.</p>
          <p className="mono muted text-xs">Hotkeys: Alt+L toggle live, Alt+R refresh, Alt+M focus the message box</p>
        </div>
        <div className="row-start-gap-2">
          <Badge className="mono">{sessionId.slice(0, 16)}</Badge>
          <Badge variant={liveMode === "running" ? "success" : liveMode === "paused" ? "muted" : liveMode === "backoff" ? "warning" : "muted"}>
            {liveMode === "running" ? "Live" : liveMode === "paused" ? "Paused" : liveMode === "backoff" ? "Degraded" : "Stopped"}
          </Badge>
          <span className="mono muted text-xs">{transport.toUpperCase()}</span>
        </div>
      </div>

      <p id={liveStatusId} className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        Live state {liveMode}, transport {transport}, session status {sessionStatus || "unknown"}.
      </p>
      {error && (
        <div className="alert alert-danger" role="alert" aria-live="assertive">
          {error}
        </div>
      )}
      {refreshing && (
        <p className="mono muted text-xs" role="status" aria-live="polite">
          Refreshing...
        </p>
      )}

      {/* Toolbar */}
      <div className="row-gap-2 mb-4">
        <Button variant={liveEnabled ? "primary" : "secondary"} onClick={() => setLiveEnabled((p) => !p)}>{liveEnabled ? "Pause live" : "Resume live"}</Button>
        <Button onClick={() => void refreshAll()}>Refresh now</Button>
        <Button variant="ghost" onClick={openWebSessionAnalysis}>Open web session analysis</Button>
      </div>

      {/* Metrics grid */}
      {metricItems.length > 0 && (
        <div className="stats-grid mb-5">
          {metricItems.map((item) => (
            <article key={item.label} className="metric-card">
              <p className="metric-label">{item.label}</p>
              <p className="metric-value">{String(item.value ?? "-")}</p>
            </article>
          ))}
        </div>
      )}

      {/* Runs table */}
      <Card className="table-card mb-5">
        <CardHeader><CardTitle>Runs in this session</CardTitle></CardHeader>
        <table className="run-table">
          <caption id={runTableCaptionId} className="sr-only">Run status list for the current session</caption>
          <thead><tr><th>Run ID</th><th>Status</th><th>Failure reason</th><th>Role</th><th>Blocked</th></tr></thead>
          <tbody>
            {runs.length === 0 ? <tr><td colSpan={5} className="muted">No runs recorded yet.</td></tr> : runs.map((run, i) => (
              <tr key={String(run.run_id || i)}>
                <td className="mono">{String(run.run_id || "-").slice(0, 16)}</td>
                <td><Badge className={badgeClass(String(run.status || ""))}>{statusLabel(String(run.status || ""))}</Badge></td>
                <td className="muted max-w-200-ellipsis">{String(run.failure_reason || "-")}</td>
                <td className="mono">{String(run.current_role || run.role_step || "-")}</td>
                <td>{isBlockedFlag(run.blocked as JsonValue) ? <Badge variant="failed">Blocked</Badge> : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Conversation graph */}
      {(graphNodes.length > 0 || graphEdges.length > 0) && (
        <Card className="p-4 mb-5">
          <h3 className="text-base fw-600 mb-3">Conversation flow</h3>
          <div className="row-gap-4">
            <div className="flex-1 min-w-0">
              <h4 className="muted text-sm mb-2">Nodes ({graphNodes.length})</h4>
              <div className="row-wrap-gap-1-5">
                {graphNodes.map((node, idx) => (
                  <span key={idx} className="chip">{String(node.role || node.id || idx)}: {String(node.message_count || node.count || "?")}</span>
                ))}
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="muted text-sm mb-2">Edges ({graphEdges.length})</h4>
              <div className="row-wrap-gap-1-5">
                {graphEdges.map((edge, idx) => (
                  <span key={idx} className="chip">{String(edge.from || edge.source || "?")} -{">"} {String(edge.to || edge.target || "?")}</span>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Event timeline */}
      <Card className="p-4 mb-5">
        <h3 className="text-base fw-600 mb-3">Event timeline</h3>
        <label htmlFor={eventFilterInputId} className="sr-only">Filter events</label>
        <Input
          id={eventFilterInputId}
          className="ct-filter-input max-w-360 mb-2"
          placeholder="Filter events..."
          value={evtFilter}
          onChange={(e) => setEvtFilter(e.target.value)}
        />
        <p className="muted text-xs mb-2">{filteredEvents.length} / {events.length} events</p>
        <div className="ct-session-event-list">
          {filteredEvents.length === 0 ? <p className="muted">No events yet.</p> : filteredEvents.map((ev, idx) => {
            const evStr = String(ev.event || "");
            const isErr = /fail|error|reject/i.test(evStr);
            const isOk = /success|pass|done/i.test(evStr);
            const eventKey = `${String(ev.ts || "")}:${evStr || "UNKNOWN"}:${idx}`;
            const eventDetailsId = `ct-session-event-details-${idx}`;
            const expanded = expandedEvtKey === eventKey;
            return (
              <Fragment key={eventKey}>
                <Button
                  data-testid="ct-session-event-button"
                  className={`ct-session-event-item ${isErr ? "is-error" : isOk ? "is-success" : ""}`.trim()}
                  onClick={() => setExpandedEvtKey((current) => current === eventKey ? null : eventKey)}
                  aria-expanded={expanded}
                  aria-controls={eventDetailsId}
                  aria-label={`View event details ${evStr || "UNKNOWN"}`}
                >
                  <div className="ct-session-event-head">
                    <strong className={`ct-session-event-title ${isErr ? "is-error" : isOk ? "is-success" : ""}`.trim()}>{evStr || "UNKNOWN"}</strong>
                    <span className="mono muted">{String(ev.ts || "")}</span>
                  </div>
                </Button>
                {expanded && (
                  <pre id={eventDetailsId} className="mono text-xs mt-2">{JSON.stringify(ev, null, 2)}</pre>
                )}
              </Fragment>
            );
          })}
        </div>
      </Card>

      {/* PM message composer */}
      <Card className="p-4">
        <h3 className="text-base fw-600 mb-3">Message PM</h3>
        <label htmlFor={messageComposerLabelId} className="sr-only">Message for PM</label>
        <Textarea
          ref={msgRef}
          id={messageComposerLabelId}
          className="ct-message-textarea"
          placeholder="Send a message to PM (Alt+M focus, Enter send)"
          aria-describedby={messageComposerHintId}
          value={msgDraft}
          onChange={(e) => setMsgDraft(e.target.value)}
          onKeyDown={(e) => {
            if ((e.nativeEvent as { isComposing?: boolean }).isComposing) {
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
        />
        <p id={messageComposerHintId} className="mono muted text-xs">
          Alt+M focuses the input, Enter sends, Shift+Enter inserts a new line.
        </p>
        <div className="row-start-gap-2 mt-2">
          <Button variant="primary" disabled={msgSending || !msgDraft.trim()} onClick={handleSend}>{msgSending ? "Sending..." : "Send"}</Button>
          {msgStatus && (
            <span
              role="status"
              aria-live="polite"
              className={`mono text-sm ${/fail|error/i.test(msgStatus) ? "text-danger" : "text-success"}`}
            >
              {msgStatus}
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}
