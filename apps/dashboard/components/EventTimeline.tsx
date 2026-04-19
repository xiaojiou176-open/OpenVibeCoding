"use client";

import { useMemo, useState } from "react";
import type { EventRecord } from "../lib/types";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import type { UiLocale } from "../lib/statusPresentation";

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

function eventPresetLabel(locale: UiLocale, value: string): string {
  if (locale !== "zh-CN") {
    return value;
  }
  if (value === "All") return "全部";
  if (value === "Tools") return "工具";
  if (value === "Diffs") return "差异";
  if (value === "Approvals") return "审批";
  if (value === "Tests") return "测试";
  if (value === "Gates") return "门禁";
  return value;
}

function eventActionLabel(eventName: string, locale: UiLocale): string {
  const upper = eventName.toUpperCase();
  if (locale === "zh-CN") {
    if (upper.startsWith("WORKTREE_")) return "工作树变更";
    if (upper.startsWith("MCP_")) return "工具并发检查";
    if (upper.startsWith("RUNNER_")) return "执行器决策";
    if (upper.startsWith("DIFF_")) return "补丁与差异";
    if (upper.startsWith("HUMAN_APPROVAL")) return "人工审批";
    if (upper.startsWith("TEST_")) return "测试执行";
    if (upper.includes("POLICY")) return "策略检查";
    return "系统事件";
  }
  if (upper.startsWith("WORKTREE_")) return "Worktree change";
  if (upper.startsWith("MCP_")) return "Tool concurrency check";
  if (upper.startsWith("RUNNER_")) return "Runner decision";
  if (upper.startsWith("DIFF_")) return "Patch and diff";
  if (upper.startsWith("HUMAN_APPROVAL")) return "Human approval";
  if (upper.startsWith("TEST_")) return "Test execution";
  if (upper.includes("POLICY")) return "Policy check";
  return "System event";
}

function eventKeyFacts(eventName: string, context: Record<string, unknown>, locale: UiLocale): string[] {
  const upper = eventName.toUpperCase();
  const labels = locale === "zh-CN"
    ? {
        runner: "执行器",
        provider: "提供方",
        model: "模型",
        worktree: "工作树",
        branch: "分支",
        base: "基线",
        concurrency: "并发上限",
        mode: "策略模式",
        toolset: "范围",
        noContext: "当前没有可展示的上下文字段",
      }
    : {
        runner: "Runner",
        provider: "Provider",
        model: "Model",
        worktree: "Worktree",
        branch: "Branch",
        base: "Baseline",
        concurrency: "Concurrency limit",
        mode: "Policy mode",
        toolset: "Scope",
        noContext: "No inspectable context fields",
      };
  if (upper === "RUNNER_SELECTED") {
    const runner = String(context.runner || context.name || context.executor || "-");
    const provider = String(context.provider || "-");
    const model = String(context.model || context.runtime_model || "-");
    return [`${labels.runner}: ${runner}`, `${labels.provider}: ${provider}`, `${labels.model}: ${model}`];
  }
  if (upper === "WORKTREE_CREATED") {
    const worktree = String(context.worktree || context.path || context.dir || "-");
    const branch = String(context.branch || context.ref || "-");
    const base = String(context.base || context.base_branch || "-");
    return [`${labels.worktree}: ${worktree}`, `${labels.branch}: ${branch}`, `${labels.base}: ${base}`];
  }
  if (upper === "MCP_CONCURRENCY_CHECK") {
    const concurrency = String(context.max_concurrency || context.concurrency || context.limit || "-");
    const mode = String(context.mode || context.policy || "-");
    const toolset = String(context.toolset || context.scope || "-");
    return [`${labels.concurrency}: ${concurrency}`, `${labels.mode}: ${mode}`, `${labels.toolset}: ${toolset}`];
  }

  const fallback = Object.entries(context)
    .filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`);
  return fallback.length > 0 ? fallback : [labels.noContext];
}

export default function EventTimeline({
  events,
  locale = "en",
  onEventInspect,
}: {
  events: EventRecord[];
  locale?: UiLocale;
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
          <span className="event-empty-text">{locale === "zh-CN" ? "暂时还没有事件" : "No events yet"}</span>
        </div>
      </Card>
    );
  }

  const selectedEvent = selectedSourceIdx !== null ? events[selectedSourceIdx] || null : null;
  const selectedEventName = String(selectedEvent?.event || "UNKNOWN");
  const selectedEventContext = selectedEvent?.context && typeof selectedEvent.context === "object" ? selectedEvent.context : {};
  const selectedFacts = selectedEvent ? eventKeyFacts(selectedEventName, selectedEventContext, locale) : [];
  const selectedAction = selectedEvent ? eventActionLabel(selectedEventName, locale) : "";

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
            {eventPresetLabel(locale, preset.label)}
          </Button>
        ))}
      </div>

      <label className="input-label" htmlFor="event-filter-input">
        <span className="event-filter-label">
          {locale === "zh-CN" ? "事件筛选" : "Event filter"}
        </span>
        <Input
          id="event-filter-input"
          className="event-filter-input"
          placeholder={locale === "zh-CN" ? "搜索事件名称或上下文..." : "Search event name or context..."}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </label>

      <div className="event-filter-summary">
        {locale === "zh-CN" ? `显示 ${filtered.length} / ${events.length} 条事件` : `Showing ${filtered.length} / ${events.length} events`}
      </div>
      <p className="mono muted" role="status" aria-live="polite" data-testid="event-selection-status">
        {selectedEvent
          ? locale === "zh-CN"
            ? `已选：${selectedEventName} · ${selectedAction}`
            : `Selected: ${selectedEventName} · ${selectedAction}`
          : locale === "zh-CN"
            ? "请选择一个事件来查看上下文和动作含义"
            : "Select an event to inspect context and action meaning"}
      </p>
      {inspectNotice ? (
        <p className="mono muted" role="status" aria-live="polite" data-testid="event-inspect-notice">
          {inspectNotice}
        </p>
      ) : null}

      {filtered.length === 0 ? (
        <Card>
          <div className="empty-state-stack">
            <span className="event-empty-text">{locale === "zh-CN" ? "当前筛选下没有匹配事件" : "No events match the current filters"}</span>
            <Button variant="ghost" onClick={() => setFilter("")}>
              {locale === "zh-CN" ? "清空筛选" : "Clear filters"}
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
                      setInspectNotice(locale === "zh-CN" ? `已刷新 ${eventName} 关联的执行日志` : `Refreshed the linked execution logs for ${eventName}`);
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
                    {locale === "zh-CN"
                      ? `动作含义：${eventActionLabel(eventName, locale)}${isSelected ? " · 已选中" : ""}`
                      : `Action meaning: ${eventActionLabel(eventName, locale)}${isSelected ? " · selected" : ""}`}
                  </div>
                </Button>
              </Card>
            );
          })}
        </div>
      )}
      <Card className={`event-card${selectedEvent ? " is-selected" : ""}`} data-testid="event-selected-detail">
        <div className="event-item-summary">{locale === "zh-CN" ? "事件下钻" : "Event drilldown"}</div>
        {selectedEvent ? (
          <>
            <div className="mono muted" data-testid="event-drilldown-title">
              {locale === "zh-CN" ? `事件：${selectedEventName}` : `Event: ${selectedEventName}`}
            </div>
            <div className="mono muted">{locale === "zh-CN" ? `动作含义：${selectedAction}` : `Action meaning: ${selectedAction}`}</div>
            <div className="mono muted">{locale === "zh-CN" ? `时间：${selectedEvent.ts || "-"}` : `Time: ${selectedEvent.ts || "-"}`}</div>
            {selectedEvent.trace_id ? <div className="mono muted">{locale === "zh-CN" ? `追踪：${selectedEvent.trace_id}` : `trace: ${selectedEvent.trace_id}`}</div> : null}
            <div className="event-item-summary">{locale === "zh-CN" ? "关键事实" : "Key facts"}</div>
            <ul className="mono muted">
              {selectedFacts.map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
            <details>
              <summary className="mono">{locale === "zh-CN" ? "展开原始事件 JSON" : "Expand raw event JSON"}</summary>
              <pre className="mono event-item-json">{JSON.stringify(selectedEvent, null, 2)}</pre>
            </details>
            {onEventInspect ? (
              <Button
                variant="secondary"
                data-testid="event-drilldown-refresh"
                onClick={() => {
                  onEventInspect(selectedEvent);
                  setInspectNotice(locale === "zh-CN" ? `已刷新 ${selectedEventName} 关联的执行日志` : `Refreshed the linked execution logs for ${selectedEventName}`);
                }}
              >
                {locale === "zh-CN" ? "刷新关联执行日志" : "Refresh linked execution logs"}
              </Button>
            ) : null}
          </>
        ) : (
          <div className="mono muted">
            {locale === "zh-CN"
              ? "请选择左侧的事件，查看结构化详情和原始数据。"
              : "Select an event on the left to inspect structured details and raw data."}
          </div>
        )}
      </Card>
    </div>
  );
}
