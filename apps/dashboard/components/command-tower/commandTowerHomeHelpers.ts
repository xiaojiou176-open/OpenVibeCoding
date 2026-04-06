import type { CommandTowerAlertsPayload, PmSessionStatus } from "../../lib/types";
import type { StatusVariant } from "@cortexpilot/frontend-shared/statusPresentation";

export type LiveMode = "running" | "backoff" | "paused";
export type SortMode = "updated_desc" | "created_desc" | "failed_desc" | "blocked_desc";
export type FocusMode = "all" | "high_risk" | "blocked" | "running";
export type SectionFetchStatus = "ok" | "error";
export type QuickActionId =
  | "refresh"
  | "live"
  | "export"
  | "copy"
  | "focus-filter"
  | "apply-filter"
  | "toggle-drawer"
  | "toggle-pin";

export const STATUS_OPTIONS: PmSessionStatus[] = ["active", "paused", "done", "failed", "archived"];
export const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: "updated_desc", label: "Last updated" },
  { value: "created_desc", label: "Newest first" },
  { value: "failed_desc", label: "Most failures" },
  { value: "blocked_desc", label: "Most blocked" },
];
export const FOCUS_OPTIONS: Array<{ value: FocusMode; label: string }> = [
  { value: "all", label: "All" },
  { value: "high_risk", label: "High risk" },
  { value: "blocked", label: "Blocked" },
  { value: "running", label: "Running" },
];

export function classifyErrorMessage(message: string): { type: "network" | "auth" | "server"; label: string } {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("failed to fetch") ||
    normalized.includes("network") ||
    normalized.includes("timed out") ||
    normalized.includes("aborted")
  ) {
    return { type: "network", label: "Network issue" };
  }
  if (
    normalized.includes("401") ||
    normalized.includes("403") ||
    normalized.includes("token") ||
    normalized.includes("auth")
  ) {
    return { type: "auth", label: "Auth issue" };
  }
  return { type: "server", label: "Service issue" };
}

export function homeLiveBadgeVariant(mode: LiveMode): StatusVariant {
  if (mode === "backoff") {
    return "failed";
  }
  if (mode === "paused") {
    return "warning";
  }
  return "running";
}

export function homeLiveBadgeText(mode: LiveMode): string {
  if (mode === "paused") {
    return "Paused";
  }
  if (mode === "backoff") {
    return "Backoff";
  }
  return "Live";
}

export function alertsBadgeVariant(status: CommandTowerAlertsPayload["status"]): StatusVariant {
  if (status === "critical") {
    return "failed";
  }
  if (status === "degraded") {
    return "warning";
  }
  return "running";
}

export function sectionStatusBadgeVariant(status: SectionFetchStatus): StatusVariant {
  return status === "ok" ? "success" : "failed";
}

export function sectionStatusLabel(status: SectionFetchStatus): string {
  return status === "ok" ? "Healthy" : "Issue";
}
