"use client";

import { useMemo, useState } from "react";
import type { EventRecord } from "../lib/types";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";

const EVENT_PRESETS = [
  { label: "All", value: "" },
  { label: "Tools", value: "TOOL_" },
  { label: "Diffs", value: "DIFF_" },
  { label: "Approvals", value: "HUMAN_APPROVAL" },
  { label: "Tests", value: "TEST_" },
  { label: "Gates", value: "gate_failed" },
] as const;

function eventStatusClass(event: string): string {
  const upper = (event || "").toUpperCase();
  if (upper.includes("FAIL") || upper.includes("ERROR") || upper.includes("REJECT")) return "event-card--failed";
  if (upper.includes("SUCCESS") || upper.includes("PASS") || upper.includes("DONE")) return "event-card--success";
  if (upper.includes("WARN") || upper.includes("APPROVAL") || upper.includes("GATE")) return "event-card--warning";
  return "event-card--running";
}

function eventActionLabel(eventName: string): string {
  const upper = eventName.toUpperCase();
  if (upper.startsWith("WORKTREE_")) return "Worktree change";
  if (upper.startsWith("MCP_")) return "Tool concurrency check";
  if (upper.startsWith("RUNNER_")) return "Runner decision";
  if (upper.startsWith("DIFF_")) return "Patch and diff";
  if (upper.startsWith("HUMAN_APPROVAL")) return "Human approval";
  if (upper.startsWith("TEST_")) return "Test execution";
  if (upper.includes("POLICY")) return "Policy check";
  return "System event";
}

function eventKeyFacts(eventName: string, context: Record<string, unknown>): string[] {
  const upper = eventName.toUpperCase();
  if (upper === "RUNNER_SELECTED") {
    const runner = String(context.runner || context.name || context.executor || "-");
    const provider = String(context.provider || "-");
    const model = String(context.model || context.runtime_model || "-");
    return [`Runner: ${runner}`, `Provider: ${provider}`, `Model: ${model}`];
  }
  if (upper === "WORKTREE_CREATED") {
    const worktree = String(context.worktree || context.path || context.dir || "-");
    const branch = String(context.branch || context.ref || "-");
    const base = String(context.base || context.base_branch || "-");
    return [`Worktree: ${worktree}`, `Branch: ${branch}`, `Baseline: ${base}`];
  }
  if (upper === "MCP_CONCURRENCY_CHECK") {
    const concurrency = String(context.max_concurrency || context.concurrency || context.limit || "-");
    const mode = String(context.mode || context.policy || "-");
    const toolset = String(context.toolset || context.scope || "-");
    return [`Concurrency limit: ${concurrency}`, `Policy mode: ${mode}`, `Scope: ${toolset}`];
  }

  const fallback = Object.entries(context)
    .filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return fallback.length > 0 ? fallback : ["No inspectable context fields"];
}

export default function EventTimeline({
  events,
  onEventInspect,
}: {
  events: EventRecord[];
  onEventInspect?: (event: EventRecord) => void;
}) {
  const [filter, setFilter] = useState("");
  const [selectedSourceIdx, setSelectedSourceIdx] = useState<number | null>(null);
  const [inspectNotice, setInspectNotice] = useState("");

  const filtered = useMemo(() => {
    const source = (events || []).map((ev, sourceIdx) => ({ ev, sourceIdx }));
    if (!filter.trim()) return source;
    const needle = filter.toLowerCase();
    return source.filter(({ ev }) => {
      const hay = `${ev.event || ""} ${JSON.stringify(ev)}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [events, filter]);

  if (!events || events.length === 0) {
    return (
      <Card>
        <div className="empty-state-stack">
          <span className="event-empty-text">No events yet</span>
        </div>
      </Card>
    );
  }

  const selectedEvent = selectedSourceIdx !== null ? events[selectedSourceIdx] || null : null;
  const selectedEventName = String(selectedEvent?.event || "UNKNOWN");
  const selectedEventContext = selectedEvent?.context && typeof selectedEvent.context === "object" ? selectedEvent.context : {};
  const selectedFacts = selectedEvent ? eventKeyFacts(selectedEventName, selectedEventContext) : [];
  const selectedAction = selectedEvent ? eventActionLabel(selectedEventName) : "";

  return (
    <div className="event-timeline">
      <div className="event-presets">
        {EVENT_PRESETS.map((preset) => (
          <Button
            key={preset.label}
            variant={filter === preset.value ? "default" : "ghost"}
            aria-pressed={filter === preset.value}
            onClick={() => setFilter(preset.value)}
          >
            {preset.label}
          </Button>
        ))}
      </div>

      <label className="input-label" htmlFor="event-filter-input">
        <span className="event-filter-label">
          Event filter
        </span>
        <Input
          id="event-filter-input"
          className="event-filter-input"
          placeholder="Search event name or context..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </label>

      <div className="event-filter-summary">
        Showing {filtered.length} / {events.length} events
      </div>
      <p className="mono muted" role="status" aria-live="polite" data-testid="event-selection-status">
        {selectedEvent ? `Selected: ${selectedEventName} · ${selectedAction}` : "Select an event to inspect context and action meaning"}
      </p>
      {inspectNotice ? (
        <p className="mono muted" role="status" aria-live="polite" data-testid="event-inspect-notice">
          {inspectNotice}
        </p>
      ) : null}

      {filtered.length === 0 ? (
        <Card>
          <div className="empty-state-stack">
            <span className="event-empty-text">No events match the current filters</span>
            <Button variant="ghost" onClick={() => setFilter("")}>
              Clear filters
            </Button>
          </div>
        </Card>
      ) : (
        <div className="event-list">
          {filtered.map(({ ev, sourceIdx }, idx) => {
            const eventName = String(ev.event || "UNKNOWN");
            const isSelected = selectedSourceIdx === sourceIdx;
            return (
              <Card
                key={`${ev.ts || "no-ts"}-${sourceIdx}-${idx}`}
                className={`event-card event-item ${eventStatusClass(ev.event || "")}${isSelected ? " is-selected" : ""}`}
                data-selected={isSelected ? "true" : "false"}
              >
                <Button
                  className="event-item-toggle"
                  data-testid={`event-name-${eventName}`}
                  onClick={() => {
                    setSelectedSourceIdx(sourceIdx);
                    onEventInspect?.(ev);
                    if (onEventInspect) {
                      setInspectNotice(`Refreshed the linked execution logs for ${eventName}`);
                    }
                  }}
                  aria-pressed={isSelected}
                >
                  <div className="event-item-header">
                    <strong className="event-item-title">
                      {eventName}
                    </strong>
                    <span className="mono muted event-item-ts">
                      {ev.ts || "-"}
                    </span>
                  </div>
                  {ev.trace_id && (
                    <div className="mono muted event-item-trace">
                      trace: {ev.trace_id}
                    </div>
                  )}
                  <div className="mono muted">
                    Action meaning: {eventActionLabel(eventName)}{isSelected ? " · selected" : ""}
                  </div>
                </Button>
              </Card>
            );
          })}
        </div>
      )}
      <Card className={`event-card${selectedEvent ? " is-selected" : ""}`} data-testid="event-selected-detail">
        <div className="event-item-summary">Event drilldown</div>
        {selectedEvent ? (
          <>
            <div className="mono muted" data-testid="event-drilldown-title">
              Event: {selectedEventName}
            </div>
            <div className="mono muted">Action meaning: {selectedAction}</div>
            <div className="mono muted">Time: {selectedEvent.ts || "-"}</div>
            {selectedEvent.trace_id ? <div className="mono muted">trace: {selectedEvent.trace_id}</div> : null}
            <div className="event-item-summary">Key facts</div>
            <ul className="mono muted">
              {selectedFacts.map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
            <details>
              <summary className="mono">Expand raw event JSON</summary>
              <pre className="mono event-item-json">{JSON.stringify(selectedEvent, null, 2)}</pre>
            </details>
            {onEventInspect ? (
              <Button
                variant="secondary"
                data-testid="event-drilldown-refresh"
                onClick={() => {
                  onEventInspect(selectedEvent);
                  setInspectNotice(`Refreshed the linked execution logs for ${selectedEventName}`);
                }}
              >
                Refresh linked execution logs
              </Button>
            ) : null}
          </>
        ) : (
          <div className="mono muted">Select an event on the left to inspect structured details and raw data.</div>
        )}
      </Card>
    </div>
  );
}
