import { mapBadgeByToken } from "@cortexpilot/frontend-api-contract";

const STATUS_BADGE_FALLBACK = { tone: "warning", label: "Needs review" } as const;

const SESSION_STATUS_MAPPING = {
  running: { tone: "running", label: "Running" },
  active: { tone: "running", label: "Running" },
  blocked: { tone: "warning", label: "Blocked" },
  warning: { tone: "warning", label: "Blocked" },
  completed: { tone: "completed", label: "Completed" },
  done: { tone: "completed", label: "Completed" },
  archived: { tone: "completed", label: "Completed" },
  critical: { tone: "critical", label: "Critical" },
  failed: { tone: "critical", label: "Critical" },
  error: { tone: "critical", label: "Critical" },
} as const;

const ALERT_SEVERITY_MAPPING = {
  critical: { tone: "critical", label: "Critical" },
  error: { tone: "critical", label: "Critical" },
  failed: { tone: "critical", label: "Critical" },
  warning: { tone: "warning", label: "Warning" },
  info: { tone: "running", label: "Info" },
  running: { tone: "running", label: "Info" },
  active: { tone: "running", label: "Info" },
} as const;

export function sessionStatusToBadge(status?: string): { tone: string; label: string } {
  return mapBadgeByToken(status, SESSION_STATUS_MAPPING, STATUS_BADGE_FALLBACK, "running");
}

export function alertSeverityToBadge(severity?: string): { tone: string; label: string } {
  return mapBadgeByToken(severity, ALERT_SEVERITY_MAPPING, STATUS_BADGE_FALLBACK, "warning");
}
