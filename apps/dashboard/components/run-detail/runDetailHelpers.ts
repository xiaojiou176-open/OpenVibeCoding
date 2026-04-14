import type { EventRecord, ReportRecord } from "../../lib/types";
import type { StatusVariant } from "@openvibecoding/frontend-shared/statusPresentation";

export type LifecycleSnapshot = {
  required_path?: string[];
  observed_path?: string[];
  workers?: { ok?: boolean; observed?: number; required?: number };
  reviewers?: { ok?: boolean; pass?: number; quorum?: number };
  tests?: { ok?: boolean; pass?: number };
  return_to_pm?: { ok?: boolean };
};

export type LifecycleBadge = {
  key: string;
  label: string;
  status: "ok" | "running" | "failed";
  detail: string;
};

export type LiveMode = "running" | "backoff" | "stopped" | "paused";
export type LiveTransport = "sse" | "polling";

export const LIVE_BASE_INTERVAL_MS = 1500;
export const LIVE_MAX_INTERVAL_MS = 8000;
export const LIVE_REPORT_REFRESH_CYCLE = 3;
export const LIVE_EVENT_LIMIT = 200;
export const LIVE_EVENT_WINDOW = 800;
export const LIVE_SSE_FAILURE_LIMIT = 3;

const TERMINAL_STATUSES = new Set(["SUCCESS", "DONE", "PASSED", "FAILED", "FAILURE", "ERROR", "CANCELLED"]);

export function lifecycleBadges(lifecycle: LifecycleSnapshot | null): LifecycleBadge[] {
  if (!lifecycle) {
    return [];
  }

  const observedPath = Array.isArray(lifecycle.observed_path) ? lifecycle.observed_path : [];
  const roleCount = (role: string) => observedPath.filter((item) => String(item).toUpperCase() === role).length;
  const hasRole = (role: string) => roleCount(role) > 0;

  const workersObserved = Number(lifecycle.workers?.observed || 0);
  const workersRequired = Number(lifecycle.workers?.required || 0);
  const reviewerPass = Number(lifecycle.reviewers?.pass || 0);
  const reviewerQuorum = Number(lifecycle.reviewers?.quorum || 0);
  const testsPass = Number(lifecycle.tests?.pass || 0);

  return [
    {
      key: "pm-start",
      label: "PM",
      status: hasRole("PM") ? "ok" : "running",
      detail: hasRole("PM") ? "Entered the run pipeline" : "Waiting for PM start",
    },
    {
      key: "tl-plan",
      label: "TL",
      status: hasRole("TECH_LEAD") ? "ok" : "running",
      detail: hasRole("TECH_LEAD") ? "Technical breakdown recorded" : "Waiting for TL breakdown",
    },
    {
      key: "workers",
      label: "Worker agents",
      status: lifecycle.workers?.ok ? "ok" : workersObserved > 0 ? "running" : "failed",
      detail: `Completed ${workersObserved}/${workersRequired || 0}`,
    },
    {
      key: "reviewers",
      label: "Review agents",
      status: lifecycle.reviewers?.ok ? "ok" : reviewerPass > 0 ? "running" : "failed",
      detail: `Passed ${reviewerPass}/${reviewerQuorum || 0}`,
    },
    {
      key: "testing",
      label: "Tests",
      status: lifecycle.tests?.ok ? "ok" : testsPass > 0 ? "running" : "failed",
      detail: testsPass > 0 ? `Passed ${testsPass}` : "No PASS signal detected",
    },
    {
      key: "tl-signoff",
      label: "TL→PM",
      status: roleCount("TECH_LEAD") >= 2 ? "ok" : "running",
      detail: roleCount("TECH_LEAD") >= 2 ? "TL handoff recorded" : "Waiting for final TL handoff",
    },
    {
      key: "pm-final",
      label: "PM closeout",
      status: lifecycle.return_to_pm?.ok ? "ok" : "failed",
      detail: lifecycle.return_to_pm?.ok ? "Returned to PM closeout" : "Not returned to PM",
    },
  ];
}

export function badgeVariantForStage(status: LifecycleBadge["status"]): StatusVariant {
  if (status === "ok") {
    return "success";
  }
  if (status === "failed") {
    return "failed";
  }
  return "running";
}

export function normalizedStatus(raw: unknown): string {
  if (typeof raw !== "string") {
    return "";
  }
  return raw.trim().toUpperCase();
}

export function isTerminalStatus(raw: unknown): boolean {
  return TERMINAL_STATUSES.has(normalizedStatus(raw));
}

export function eventTimestamp(event: EventRecord): string {
  const ts = event.ts;
  if (typeof ts === "string" && ts.trim()) {
    return ts;
  }
  const fallback = event["_ts"];
  if (typeof fallback === "string" && fallback.trim()) {
    return fallback;
  }
  return "";
}

export function eventIdentity(event: EventRecord): string {
  return `${eventTimestamp(event)}|${toStringOr(event.event, "")}|${JSON.stringify(toObject(event.context))}`;
}

export function sortEvents(events: EventRecord[]): EventRecord[] {
  return [...events].sort((left, right) => {
    const leftTs = eventTimestamp(left);
    const rightTs = eventTimestamp(right);
    if (leftTs === rightTs) {
      return eventIdentity(left).localeCompare(eventIdentity(right));
    }
    return leftTs.localeCompare(rightTs);
  });
}

export function mergeEvents(prev: EventRecord[], incoming: EventRecord[]): EventRecord[] {
  const mergedMap = new Map<string, EventRecord>();
  for (const item of prev) {
    mergedMap.set(eventIdentity(item), item);
  }
  for (const item of incoming) {
    mergedMap.set(eventIdentity(item), item);
  }
  const merged = sortEvents(Array.from(mergedMap.values()));
  if (merged.length <= LIVE_EVENT_WINDOW) {
    return merged;
  }
  return merged.slice(merged.length - LIVE_EVENT_WINDOW);
}

export function latestEventTimestamp(events: EventRecord[]): string {
  if (!events.length) {
    return "";
  }
  return eventTimestamp(events[events.length - 1]);
}

export function deriveTerminalStatus(runStatus: unknown, reports: ReportRecord[]): string {
  const chainStatus = (reports.find((item) => item.name === "chain_report.json")?.data as Record<string, unknown> | undefined)?.status;
  const taskStatus = (reports.find((item) => item.name === "task_result.json")?.data as Record<string, unknown> | undefined)?.status;
  const reportStatus = normalizedStatus(chainStatus || taskStatus);
  if (reportStatus) {
    return reportStatus;
  }
  return normalizedStatus(runStatus);
}

export function liveBadgeVariant(mode: LiveMode): StatusVariant {
  if (mode === "stopped") {
    return "success";
  }
  if (mode === "backoff") {
    return "failed";
  }
  return "running";
}

export function liveLabel(mode: LiveMode): string {
  if (mode === "paused") {
    return "Paused";
  }
  if (mode === "backoff") {
    return "Retry backoff";
  }
  if (mode === "stopped") {
    return "Terminal snapshot";
  }
  return "Live refresh active";
}

export function toStringOr(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined || value === null) {
    return fallback;
  }
  return String(value);
}

export function toDisplayText(value: unknown): string {
  const text = toStringOr(value, "");
  return text ? text : "-";
}

export function toArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

export function toObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}
