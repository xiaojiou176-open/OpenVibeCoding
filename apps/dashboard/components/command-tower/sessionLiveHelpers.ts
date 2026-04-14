import type { EventRecord } from "../../lib/types";
import type { StatusVariant } from "@openvibecoding/frontend-shared/statusPresentation";

export const BASE_INTERVAL_MS = 1500;
export const MAX_INTERVAL_MS = 8000;
export const SSE_FAILURE_LIMIT = 3;
export const EVENT_WINDOW_SIZE = 800;
export const FULL_EVENT_LIMIT = 800;
export const DELTA_EVENT_LIMIT = 200;
export const SSE_MERGE_WINDOW_MS = 350;
export const REQUEST_TIMEOUT_MS = 7000;

const TERMINAL_SESSION_STATUS = new Set(["done", "failed", "archived"]);

export type LiveMode = "running" | "backoff" | "stopped" | "paused";
export type LiveTransport = "sse" | "polling";
export type LiveErrorKind = "network" | "auth" | "server" | "unknown";

export function eventTsValue(event: EventRecord): string {
  return String(event.ts || event["_ts"] || "");
}

export function lastEventTs(events: EventRecord[]): string {
  if (events.length === 0) {
    return "";
  }
  return eventTsValue(events[events.length - 1]);
}

export function eventName(event: EventRecord): string {
  return String(event.event || event.event_type || "UNKNOWN_EVENT");
}

export function eventFingerprint(event: EventRecord): string {
  return [eventTsValue(event), eventName(event), String(event._run_id || event.run_id || ""), JSON.stringify(event.context || {})].join("|");
}

export function mergeEventWindow(existing: EventRecord[], incoming: EventRecord[]): EventRecord[] {
  if (incoming.length === 0) {
    return existing.slice(-EVENT_WINDOW_SIZE);
  }

  const dedup = new Map<string, EventRecord>();
  for (const item of existing) {
    dedup.set(eventFingerprint(item), item);
  }
  for (const item of incoming) {
    dedup.set(eventFingerprint(item), item);
  }

  const merged = Array.from(dedup.values()).sort((left, right) => {
    return eventTsValue(left).localeCompare(eventTsValue(right));
  });

  if (merged.length <= EVENT_WINDOW_SIZE) {
    return merged;
  }
  return merged.slice(merged.length - EVENT_WINDOW_SIZE);
}

export function isTerminalStatus(status: string): boolean {
  return TERMINAL_SESSION_STATUS.has(String(status || "").toLowerCase());
}

export function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && typeof error.message === "string" && error.message.trim()) {
    return error.message;
  }
  return String(error || "unknown error");
}

export function classifyError(message: string): LiveErrorKind {
  const normalized = String(message || "").toLowerCase();
  if (
    normalized.includes("timeout") ||
    normalized.includes("aborted") ||
    normalized.includes("network") ||
    normalized.includes("failed to fetch")
  ) {
    return "network";
  }
  if (normalized.includes("401") || normalized.includes("403") || normalized.includes("unauthorized") || normalized.includes("forbidden")) {
    return "auth";
  }
  if (normalized.includes("500") || normalized.includes("502") || normalized.includes("503") || normalized.includes("504") || normalized.includes("server")) {
    return "server";
  }
  return "unknown";
}

export function errorKindLabel(kind: LiveErrorKind): string {
  if (kind === "network") {
    return "Network error";
  }
  if (kind === "auth") {
    return "Auth error";
  }
  if (kind === "server") {
    return "Service error";
  }
  return "Unknown error";
}

export function sessionLiveBadgeVariant(mode: LiveMode): StatusVariant {
  if (mode === "backoff") {
    return "failed";
  }
  return "running";
}

export function sessionLiveBadgeText(mode: LiveMode): string {
  if (mode === "paused") {
    return "Paused";
  }
  if (mode === "stopped") {
    return "Stopped";
  }
  if (mode === "backoff") {
    return "Backoff";
  }
  return "Live";
}
