import { emitFrontendLogEvent } from "@cortexpilot/frontend-api-client";

type UxTelemetryEventName = "pm_starter_prompt_used" | "pm_send_attempt" | "pm_send_blocked";

type UxTelemetryPayload = Record<string, string | number | boolean | null>;

type PmSendBlockedReason =
  | "workspace_missing"
  | "session_missing"
  | "offline"
  | "empty_message"
  | "generation_active"
  | "composer_over_limit"
  | "request_in_flight";

function emitUxTelemetry(event: UxTelemetryEventName, payload: UxTelemetryPayload) {
  emitFrontendLogEvent({
    domain: "desktop",
    surface: "desktop",
    component: "ux_telemetry",
    event,
    source_kind: "app_log",
    session_id: typeof payload.session_id === "string" ? payload.session_id : null,
    meta: { ...payload, emitted_at_ms: Date.now() },
  });
}

export function trackPmStarterPromptUsed(params: {
  promptIndex: number;
  promptLength: number;
  sessionId: string;
  workspaceId: string | null;
}) {
  emitUxTelemetry("pm_starter_prompt_used", {
    prompt_index: params.promptIndex,
    prompt_length: params.promptLength,
    session_id: params.sessionId,
    workspace_id: params.workspaceId,
  });
}

export function trackPmSendAttempt(params: {
  sessionId: string;
  workspaceId: string | null;
  isOffline: boolean;
  hasActiveGeneration: boolean;
  composerLength: number;
  isEmpty: boolean;
  isOverLimit: boolean;
}) {
  emitUxTelemetry("pm_send_attempt", {
    session_id: params.sessionId,
    workspace_id: params.workspaceId,
    is_offline: params.isOffline,
    has_active_generation: params.hasActiveGeneration,
    composer_length: params.composerLength,
    is_empty: params.isEmpty,
    is_over_limit: params.isOverLimit,
  });
}

export function trackPmSendBlocked(params: {
  sessionId: string;
  workspaceId: string | null;
  reason: PmSendBlockedReason;
}) {
  emitUxTelemetry("pm_send_blocked", {
    session_id: params.sessionId,
    workspace_id: params.workspaceId,
    reason: params.reason,
  });
}
