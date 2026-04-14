import type { EventRecord, ExecutionPlanReport, NewsDigestTimeRange, PmSessionSummary, TaskPackManifest } from "../../../lib/types";

export type BrowserPreset = "safe" | "balanced" | "aggressive" | "custom";
export type ChatRole = "PM" | "OpenVibeCoding Command Tower";
export type PMLayoutMode = "dialog" | "split" | "chain" | "focus";
export type ChatItemKind = "message" | "decision" | "delegation" | "progress" | "report" | "alert";
export type PMTaskTemplate = string;
export type { NewsDigestTimeRange };
export type { ExecutionPlanReport };
export type { TaskPackManifest };

export type ChatCardOption = {
  label: string;
  description: string;
  recommended?: boolean;
};

export type ChatCardPayload = {
  title: string;
  subtitle?: string;
  bullets?: string[];
  options?: ChatCardOption[];
  actions?: string[];
};

export type ChatItem = {
  id: string;
  role: ChatRole;
  text: string;
  createdAt: string;
  kind: ChatItemKind;
  origin: "local" | "remote";
  card?: ChatCardPayload;
};

export type ChainRole = "PM" | "TECH_LEAD" | "WORKER" | "REVIEWER" | "TEST_RUNNER";

export type ChainNode = {
  role: ChainRole;
  label: string;
  hint: string;
  state: "idle" | "active" | "done";
};

export type PMCopyVariant = "a" | "b";

export const DEFAULT_ALLOWED_PATHS = ["apps/dashboard", "apps/orchestrator/src"];
export const DEFAULT_MCP_TOOL_SET = ["codex"];
export const DEFAULT_ACCEPTANCE_TESTS = [
  {
    name: "repo_hygiene",
    cmd: "bash scripts/check_repo_hygiene.sh",
    must_pass: true,
  },
];
export const PM_INTAKE_REQUEST_TIMEOUT_MS = 180_000;
export const PRIVILEGED_CUSTOM_ROLES = new Set(["TECH_LEAD", "OPS", "OWNER", "ARCHITECT"]);
export const CHAIN_ORDER: ChainRole[] = ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"];
export const DRAFT_SESSION_ID = "__draft__";
const LEGACY_NO_EXECUTABLE_INTAKE_DETAIL = "\u5f53\u524d\u6ca1\u6709\u53ef\u6267\u884c\u7684 intake";
export const LAYOUT_MODE_LABELS: Record<PMLayoutMode, string> = {
  dialog: "Chat-first",
  split: "Split",
  chain: "Chain-first",
  focus: "Focus chat",
};

export function resolvePmCopyVariant(rawVariant: string | undefined): PMCopyVariant {
  return rawVariant?.trim().toLowerCase() === "b" ? "b" : "a";
}

export function isNearBottom(node: HTMLElement, threshold = 120): boolean {
  return node.scrollHeight - node.scrollTop - node.clientHeight <= threshold;
}

export function normalizeChainRole(rawRole: string): ChainRole | null {
  const normalized = rawRole.trim().toUpperCase();
  if (normalized === "PM") return "PM";
  if (normalized === "TECH_LEAD") return "TECH_LEAD";
  if (normalized === "WORKER") return "WORKER";
  if (normalized === "REVIEWER") return "REVIEWER";
  if (normalized === "TEST_RUNNER" || normalized === "TESTER") return "TEST_RUNNER";
  return null;
}

export function splitLines(raw: string): string[] {
  return raw
    .split(/\r?\n|,/g)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function errorDetail(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "");
}

export function sanitizeErrorMessage(error: unknown, fallback: string): string {
  const detail = errorDetail(error).trim();
  if (!detail) {
    return fallback;
  }
  if (detail.includes("Custom browser policy JSON is invalid")) {
    return "Custom browser policy JSON is invalid";
  }
  if (detail.includes(LEGACY_NO_EXECUTABLE_INTAKE_DETAIL) || detail.includes("No executable intake is available yet")) {
    return "No executable intake is available yet; the session has not been created.";
  }
  if (detail.includes("custom browser policy requires privileged requester role")) {
    return "Custom browser policy requires a privileged role (TECH_LEAD / OPS / OWNER / ARCHITECT).";
  }
  if (detail.toLowerCase().includes("network") || detail.toLowerCase().includes("fetch")) {
    return `${fallback}: network error, please try again.`;
  }
  if (detail.includes("401") || detail.includes("403") || detail.toLowerCase().includes("auth")) {
    return `${fallback}: authentication or permission error, please confirm your session.`;
  }
  return fallback;
}

export function isRequestAborted(error: unknown): boolean {
  return errorDetail(error).toLowerCase().includes("aborted");
}

function eventToChatItem(event: EventRecord, index: number): ChatItem | null {
  const context = event.context;
  if (!context || typeof context !== "object") {
    return null;
  }
  const message = String(context.message || "").trim();
  if (!message) {
    return null;
  }
  const fromRole = String(context.from_role || context.role || "").trim().toUpperCase();
  const role: ChatRole = fromRole === "PM" ? "PM" : "OpenVibeCoding Command Tower";
  const ts = typeof event.ts === "string" ? event.ts : new Date().toISOString();
  return { id: `${ts}-${index}-${fromRole || "SYS"}`, role, text: message, createdAt: ts, kind: "message", origin: "remote" };
}

export function buildChatTimeline(events: EventRecord[]): ChatItem[] {
  const timeline: ChatItem[] = [];
  for (let index = 0; index < events.length; index += 1) {
    const chatItem = eventToChatItem(events[index], index);
    if (chatItem) {
      timeline.push(chatItem);
    }
  }
  return timeline;
}

function chatIdentity(item: Pick<ChatItem, "role" | "text" | "createdAt">): string {
  return `${item.createdAt}::${item.role}::${item.text}`;
}

function isSameChatSequence(left: ChatItem[], right: ChatItem[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  for (let index = 0; index < left.length; index += 1) {
    if (
      chatIdentity(left[index]) !== chatIdentity(right[index]) ||
      left[index].kind !== right[index].kind ||
      left[index].origin !== right[index].origin
    ) {
      return false;
    }
  }
  return true;
}

function parseTs(raw: string): number | null {
  const value = Date.parse(raw);
  return Number.isFinite(value) ? value : null;
}

function isLikelyEchoDuplicate(left: ChatItem, right: ChatItem): boolean {
  if (left.kind !== "message" || right.kind !== "message") {
    return false;
  }
  if (left.origin === right.origin) {
    return false;
  }
  if (left.role !== right.role || left.text !== right.text) {
    return false;
  }
  const leftTs = parseTs(left.createdAt);
  const rightTs = parseTs(right.createdAt);
  if (leftTs === null || rightTs === null) {
    return false;
  }
  return Math.abs(leftTs - rightTs) <= 45 * 1000;
}

export function mergeChatTimeline(local: ChatItem[], remote: ChatItem[]): ChatItem[] {
  if (remote.length === 0) {
    return local;
  }

  const seen = new Set<string>();
  const merged: ChatItem[] = [];
  for (const item of local) {
    const key = chatIdentity(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(item);
  }

  for (const item of remote) {
    const key = chatIdentity(item);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(item);
  }

  merged.sort((a, b) => {
    const left = Date.parse(a.createdAt);
    const right = Date.parse(b.createdAt);
    if (!Number.isFinite(left) || !Number.isFinite(right)) {
      return a.createdAt.localeCompare(b.createdAt);
    }
    return left - right;
  });

  const compacted: ChatItem[] = [];
  for (const item of merged) {
    const previous = compacted[compacted.length - 1];
    if (previous && isLikelyEchoDuplicate(previous, item)) {
      if (previous.origin === "local" && item.origin === "remote") {
        compacted[compacted.length - 1] = item;
      }
      continue;
    }
    compacted.push(item);
  }

  return isSameChatSequence(local, compacted) ? local : compacted;
}

export function chatItemLinkRole(item: ChatItem, fallbackRole: string): ChainRole | null {
  if (item.kind === "delegation") {
    return "TECH_LEAD";
  }
  if (item.kind === "progress") {
    return "WORKER";
  }
  if (item.kind === "report") {
    return "REVIEWER";
  }
  if (item.kind === "alert") {
    return "REVIEWER";
  }
  if (item.kind === "decision") {
    return "PM";
  }
  if (item.role === "PM") {
    return "PM";
  }
  return normalizeChainRole(fallbackRole);
}

export function summarizeSession(session: PmSessionSummary): string {
  const status = typeof session.status === "string" ? session.status : "unknown";
  const step = typeof session.current_step === "string" ? session.current_step : "-";
  const updated = typeof session.updated_at === "string" ? session.updated_at.replace("T", " ").slice(0, 16) : "-";
  return `${status} · ${step} · ${updated}`;
}

export function inferActiveRole(events: EventRecord[], fallbackRole: string): string {
  for (let idx = events.length - 1; idx >= 0; idx -= 1) {
    const event = events[idx];
    const context = event.context;
    if (!context || typeof context !== "object") {
      continue;
    }
    const roleCandidate = String(
      (context.current_role as string | undefined) ||
        (context.to_role as string | undefined) ||
        (context.assigned_role as string | undefined) ||
        "",
    )
      .trim()
      .toUpperCase();
    if (roleCandidate) {
      return roleCandidate;
    }
  }
  return fallbackRole.trim().toUpperCase();
}

function roleLabel(rawRole: string): string {
  const normalized = rawRole.trim().toUpperCase();
  if (normalized === "PM") return "PM";
  if (normalized === "TECH_LEAD") return "TL";
  if (normalized === "WORKER") return "Worker";
  if (normalized === "REVIEWER") return "Reviewer";
  if (normalized === "TEST_RUNNER") return "Test";
  return normalized || "System";
}

export function shortTime(raw: string | undefined): string {
  if (!raw) return "--:--";
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return "--:--";
  }
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function buildProgressFeed(events: EventRecord[]): string[] {
  const lines: string[] = [];
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    const context = event.context && typeof event.context === "object" ? event.context : null;
    const message = context ? asString(context.message) || asString(context.summary) || asString(context.detail) : "";
    const status = context ? asString(context.status) || asString(context.state) : "";
    const activeRole = context
      ? asString(context.current_role) || asString(context.to_role) || asString(context.from_role)
      : "";
    const eventName = asString(event.event || event.event_type).replaceAll("_", " ").trim();
    const body = message || status || eventName;
    if (!body) {
      continue;
    }
    lines.push(`${shortTime(event.ts)} ${roleLabel(activeRole)} · ${body}`);
    if (lines.length >= 6) {
      break;
    }
  }
  return lines.reverse();
}

export function buildChainNodes(activeRole: string, sessionStatus: string): ChainNode[] {
  const status = sessionStatus.trim().toLowerCase();
  const activeIndex = CHAIN_ORDER.indexOf(activeRole as ChainRole);
  const isTerminal = status === "done" || status === "failed" || status === "archived";

  return CHAIN_ORDER.map((role, index) => {
    let state: ChainNode["state"] = "idle";
    if (isTerminal) {
      state = "done";
    } else if (activeIndex >= 0 && index < activeIndex) {
      state = "done";
    } else if (activeIndex >= 0 && index === activeIndex) {
      state = "active";
    }

    const labelMap: Record<ChainRole, string> = {
      PM: "PM",
      TECH_LEAD: "TL",
      WORKER: "Worker pool",
      REVIEWER: "Review",
      TEST_RUNNER: "Test",
    };

    const hintMap: Record<ChainRole, string> = {
      PM: "Your only conversation entrypoint",
      TECH_LEAD: "Task breakdown and routing",
      WORKER: "Execute code and produce artifacts",
      REVIEWER: "Quality review",
      TEST_RUNNER: "Regression and acceptance",
    };

    return {
      role,
      label: labelMap[role],
      hint: hintMap[role],
      state,
    };
  });
}

export function buildSessionMiniChain(session: PmSessionSummary): Array<"done" | "active" | "idle" | "failed"> {
  const status = String(session.status || "").toLowerCase();
  const currentRole = String(session.current_role || "").trim().toUpperCase();
  const activeIndex = CHAIN_ORDER.indexOf(currentRole as ChainRole);
  const fallbackActiveIndex = activeIndex >= 0 ? activeIndex : 0;

  return CHAIN_ORDER.map((_role, index) => {
    if (status === "failed") {
      if (index < fallbackActiveIndex) {
        return "done";
      }
      if (index === fallbackActiveIndex) {
        return "failed";
      }
      return "idle";
    }
    if (status === "done" || status === "archived") {
      return "done";
    }
    if (status === "active" || status === "paused") {
      if (index < fallbackActiveIndex) {
        return "done";
      }
      if (index === fallbackActiveIndex) {
        return "active";
      }
      return "idle";
    }
    return "idle";
  });
}
