import { Badge, type BadgeVariant } from "../ui/badge";
import { Card } from "../ui/card";
import type { EventRecord, JsonValue } from "../../lib/types";

type SessionTimelineProps = {
  events: EventRecord[];
};

function eventName(event: EventRecord): string {
  return String(event.event || event.event_type || "UNKNOWN_EVENT");
}

function eventTs(event: EventRecord): string {
  return String(event.ts || event["_ts"] || "");
}

function eventBadgeVariant(name: string): BadgeVariant {
  const normalized = name.toUpperCase();
  if (normalized.includes("ERROR") || normalized.includes("FAIL") || normalized.includes("REJECT")) {
    return "failed";
  }
  if (normalized.includes("WARN") || normalized.includes("BLOCK") || normalized.includes("APPROVAL")) {
    return "warning";
  }
  if (normalized.includes("SUCCESS") || normalized.includes("DONE") || normalized.includes("PASS")) {
    return "success";
  }
  return "running";
}

type EventPhase = {
  key: string;
  label: string;
  hint: string;
};

function eventPhase(name: string): EventPhase {
  const normalized = name.toUpperCase();
  if (normalized.includes("INTAKE") || normalized.includes("PLAN")) {
    return { key: "plan", label: "Planning", hint: "Requirement clarification and task breakdown" };
  }
  if (normalized.includes("HANDOFF") || normalized.includes("ASSIGN") || normalized.includes("ROUTE")) {
    return { key: "handoff", label: "Handoff", hint: "Role switches and responsibility transfer" };
  }
  if (normalized.includes("REVIEW") || normalized.includes("VERIFY") || normalized.includes("APPROVAL")) {
    return { key: "review", label: "Review", hint: "Acceptance and quality gates" };
  }
  if (
    normalized.includes("ERROR") ||
    normalized.includes("FAIL") ||
    normalized.includes("BLOCK") ||
    normalized.includes("RECOVER")
  ) {
    return { key: "risk", label: "Risk", hint: "Blockers, failures, or recovery actions" };
  }
  if (normalized.includes("SUCCESS") || normalized.includes("DONE") || normalized.includes("CLOSE")) {
    return { key: "close", label: "Closeout", hint: "Completion, closure, or archival" };
  }
  return { key: "execute", label: "Execution", hint: "Running work and producing intermediate results" };
}

function phaseBadgeVariant(phase: EventPhase): BadgeVariant {
  if (phase.key === "risk") {
    return "failed";
  }
  if (phase.key === "review" || phase.key === "handoff") {
    return "warning";
  }
  if (phase.key === "close") {
    return "success";
  }
  return "running";
}

function isKeyEvent(name: string): boolean {
  const normalized = name.toUpperCase();
  return (
    normalized.includes("ERROR") ||
    normalized.includes("FAIL") ||
    normalized.includes("BLOCK") ||
    normalized.includes("APPROVAL") ||
    normalized.includes("HANDOFF") ||
    normalized.includes("SUCCESS") ||
    normalized.includes("DONE") ||
    normalized.includes("START")
  );
}

function eventAccentClass(name: string): string {
  const variant = eventBadgeVariant(name);
  if (variant === "failed") {
    return "event-card--failed";
  }
  if (variant === "warning") {
    return "event-card--warning";
  }
  if (variant === "success") {
    return "event-card--success";
  }
  return "event-card--running";
}

function toAbsoluteTs(rawTs: string): string {
  if (!rawTs) {
    return "-";
  }
  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return rawTs;
  }
  return new Date(parsed).toLocaleString();
}

function toRelativeTs(rawTs: string): string {
  if (!rawTs) {
    return "-";
  }

  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return rawTs;
  }

  const diffSec = Math.round((Date.now() - parsed) / 1000);
  if (diffSec < 5) {
    return "just now";
  }
  if (diffSec < 60) {
    return `${diffSec}s ago`;
  }

  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) {
    return `${diffMin}m ago`;
  }

  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) {
    return `${diffHour}h ago`;
  }

  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}d ago`;
}

function valueToText(value: JsonValue): string {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return `Array(${value.length})`;
  }
  return "Object";
}

const REDACTED_TEXT = "[REDACTED]";
const SENSITIVE_KEY_PATTERN =
  /(^|_|-)(token|secret|password|bearer|cookie|key)(_|-|$)|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret/i;
const BEARER_TOKEN_PATTERN = /(bearer)\s+[a-z0-9-._~+/]+=*/gi;
const KEY_VALUE_PATTERN =
  /(token|secret|password|cookie|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)\s*[:=]\s*[^,\s;]+/gi;
const JWT_PATTERN = /[a-z0-9-_]+\.[a-z0-9-_]+\.[a-z0-9-_]+/gi;

function shouldRedactKey(key: string): boolean {
  return SENSITIVE_KEY_PATTERN.test(key);
}

function maskSensitiveText(value: string): string {
  return value
    .replace(BEARER_TOKEN_PATTERN, "$1 [REDACTED]")
    .replace(KEY_VALUE_PATTERN, "$1=[REDACTED]")
    .replace(JWT_PATTERN, REDACTED_TEXT);
}

function sanitizeJsonValue(value: JsonValue): JsonValue {
  if (typeof value === "string") {
    return maskSensitiveText(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeJsonValue(item));
  }
  if (value && typeof value === "object") {
    const sanitized: Record<string, JsonValue> = {};
    for (const [key, nestedValue] of Object.entries(value)) {
      sanitized[key] = shouldRedactKey(key) ? REDACTED_TEXT : sanitizeJsonValue(nestedValue as JsonValue);
    }
    return sanitized;
  }
  return value;
}

function sanitizeContext(context: Record<string, JsonValue> | undefined): Record<string, JsonValue> | undefined {
  if (!context) {
    return context;
  }
  const sanitized: Record<string, JsonValue> = {};
  for (const [key, value] of Object.entries(context)) {
    sanitized[key] = shouldRedactKey(key) ? REDACTED_TEXT : sanitizeJsonValue(value);
  }
  return sanitized;
}

function summarizeContext(context: Record<string, JsonValue> | undefined): string {
  if (!context || Object.keys(context).length === 0) {
    return "No context summary";
  }

  const preferredKeys = [
    "summary",
    "message",
    "reason",
    "error",
    "status",
    "from_role",
    "to_role",
    "tool",
    "cmd",
  ];

  const preferredParts: string[] = [];
  for (const key of preferredKeys) {
    const value = context[key];
    if (value !== undefined) {
      preferredParts.push(`${key}=${valueToText(value)}`);
    }
    if (preferredParts.length >= 3) {
      break;
    }
  }

  if (preferredParts.length > 0) {
    return preferredParts.join(" | ");
  }

  const fallbackKeys = Object.keys(context).slice(0, 3);
  return fallbackKeys.map((key) => `${key}=${valueToText(context[key])}`).join(" | ");
}

function gapSincePrevious(prevTs: string, currentTs: string): string {
  if (!prevTs || !currentTs) {
    return "-";
  }
  const prev = Date.parse(prevTs);
  const current = Date.parse(currentTs);
  if (Number.isNaN(prev) || Number.isNaN(current)) {
    return "-";
  }
  const diffSec = Math.abs(Math.round((prev - current) / 1000));
  if (diffSec < 60) {
    return `${diffSec}s`;
  }
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) {
    return `${diffMin}m`;
  }
  return `${Math.round(diffMin / 60)}h`;
}

export default function SessionTimeline({ events }: SessionTimelineProps) {
  const keyEvents = events.filter((event) => isKeyEvent(eventName(event))).length;
  const phaseCount = events.reduce<Record<string, number>>((acc, event) => {
    const phase = eventPhase(eventName(event));
    acc[phase.label] = (acc[phase.label] || 0) + 1;
    return acc;
  }, {});
  const latestEvent = events[0];
  const latestEventName = latestEvent ? eventName(latestEvent) : "-";
  const latestEventTs = latestEvent ? eventTs(latestEvent) : "";

  return (
    <section className="app-section" aria-label="Session timeline">
      <div className="section-header">
        <div>
          <h3>Session timeline</h3>
          <p>Cross-run event flow in time order, highlighting key nodes, phase transitions, and contextual traceability.</p>
        </div>
      </div>

      <Card aria-live="polite" aria-atomic="true">
        <div className="section-header">
          <div>
            <h4>Header summary</h4>
            <p>The main area shows the full timeline while the right drawer keeps live actions and context close at hand.</p>
          </div>
        </div>
        <div className="run-detail-chip-row run-detail-chip-row--flush">
          <Badge>Total events {events.length}</Badge>
          <Badge variant="warning">Key events {keyEvents}</Badge>
          {Object.entries(phaseCount).map(([phaseLabel, count]) => (
            <Badge key={phaseLabel} variant="running">
              {phaseLabel} {count}
            </Badge>
          ))}
        </div>
        <p className="mono muted">latest: {latestEventName} | {toAbsoluteTs(latestEventTs)}</p>
      </Card>

      <Card>
        <div className="section-header">
          <div>
            <h4>Event list</h4>
            <p>Events stay in time order so operators can locate the active problem chain quickly from the main workspace.</p>
          </div>
          <Badge>Rendered {events.length}</Badge>
        </div>

        {events.length === 0 ? (
          <div role="status" aria-live="polite" className="status-line">
            <p className="muted">No session events yet</p>
            <p className="mono muted">Send a message from the context drawer or resume live mode to repopulate the timeline.</p>
          </div>
        ) : (
          <div className="grid status-line" role="list" aria-label="Session event list">
            {events.map((event, idx) => {
              const name = eventName(event);
              const ts = eventTs(event);
              const context = sanitizeContext(event.context as Record<string, JsonValue> | undefined);
              const summary = summarizeContext(context);
              const phase = eventPhase(name);
              const runId = String(event._run_id || event.run_id || "-");
              const previousTs = idx > 0 ? eventTs(events[idx - 1]) : "";
              const fromRole = typeof context?.from_role === "string" ? context.from_role : "-";
              const toRole = typeof context?.to_role === "string" ? context.to_role : "-";
              const contextKeyCount = context ? Object.keys(context).length : 0;
              const keyNode = isKeyEvent(name);
              return (
                <Card key={`${name}-${ts}-${idx}`} asChild className={`event-card ${eventAccentClass(name)}`}>
                  <article role="listitem">
                    <div className="run-detail-chip-row">
                      <Badge variant={eventBadgeVariant(name)}>{name}</Badge>
                      <Badge variant={phaseBadgeVariant(phase)}>{phase.label}</Badge>
                      <Badge variant={keyNode ? "warning" : "default"}>{keyNode ? "Key event" : "Regular event"}</Badge>
                      <span className="mono">run: {runId}</span>
                      <span className="mono">
                        ts: {toRelativeTs(ts)} <span className="muted">({toAbsoluteTs(ts)})</span>
                      </span>
                    </div>

                    <p className="mono muted">phase: {phase.hint}</p>
                    <p className="mono muted">
                      handoff: {fromRole} → {toRole} | delta: {gapSincePrevious(previousTs, ts)} | context keys: {contextKeyCount}
                    </p>
                    <p className="mono">summary: {summary}</p>

                    <details>
                      <summary className="mono">Expand context JSON</summary>
                      <pre className="mono">{JSON.stringify(context || {}, null, 2)}</pre>
                    </details>
                  </article>
                </Card>
              );
            })}
          </div>
        )}
      </Card>
    </section>
  );
}
