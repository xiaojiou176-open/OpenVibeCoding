import { createDesktopApiClient, type RequestControlOptions } from "@openvibecoding/frontend-api-client";
import type { PmSessionSort } from "@openvibecoding/frontend-api-contract";
import type {
  AgentCatalogPayload,
  AgentStatusPayload,
  CommandTowerAlertsPayload,
  CommandTowerOverviewPayload,
  ContractRecord,
  ExecutionPlanReport,
  EventRecord,
  FlightPlanCopilotBrief,
  JsonValue,
  OperatorCopilotBrief,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
  PmSessionStatus,
  PmSessionSummary,
  QueueItemRecord,
  ReportRecord,
  RunDetailPayload,
  RunSummary,
  RoleConfigApplyResponse,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
  ToolCallRecord,
  TaskPackManifest,
  WorkflowDetailPayload,
  WorkflowRecord,
} from "./types";
import { resolveDesktopApiBase, resolveDesktopApiToken, resolveDesktopOperatorRoleEnv } from "./env";

export type EventsStream = {
  onopen: ((this: EventsStream, ev: Event) => void) | null;
  onmessage: ((this: EventsStream, ev: MessageEvent) => void) | null;
  onerror: ((this: EventsStream, ev: Event) => void) | null;
  close: () => void;
};

type FrontendStream = ReturnType<ReturnType<typeof createDesktopApiClient>["openEventsStream"]>;

function normalizeAbortTimeoutError(error: unknown): Error {
  if (!(error instanceof Error)) {
    return new Error(String(error));
  }
  if (/AbortError/i.test(error.message) || error.message.endsWith(": aborted")) {
    error.name = "AbortError";
    return error;
  }
  if (/timeout/i.test(error.message)) {
    error.name = "TimeoutError";
    return error;
  }
  return error;
}

function dynamicFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  return globalThis.fetch(input, init);
}

async function desktopPostJson<T>(path: string, payload: Record<string, JsonValue>, errorLabel: string): Promise<T> {
  const token = resolveDesktopApiToken();
  const response = await dynamicFetch(`${resolveDesktopApiBase()}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    credentials: "same-origin",
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`${errorLabel}: ${response.status}`);
  }
  return (await response.json()) as T;
}

class DynamicEventSource {
  constructor(url: string | URL, init?: EventSourceInit) {
    return new globalThis.EventSource(url, init);
  }
}

async function withNormalizedError<T>(factory: () => Promise<T>): Promise<T> {
  try {
    return await factory();
  } catch (error) {
    throw normalizeAbortTimeoutError(error);
  }
}

const desktopApiClient = createDesktopApiClient({
  baseUrl: resolveDesktopApiBase(),
  resolveToken: () => {
    const token = resolveDesktopApiToken();
    return token || undefined;
  },
  resolveMutationRole: resolveDesktopOperatorRole,
  fetchImpl: dynamicFetch,
  eventSourceCtor: DynamicEventSource as unknown as typeof EventSource,
});

function resolveDesktopOperatorRole(): string | undefined {
  const role = resolveDesktopOperatorRoleEnv();
  return role ? role.toUpperCase() : undefined;
}

export function mutationExecutionCapability(): { executable: boolean; operatorRole: string | null } {
  const operatorRole = resolveDesktopOperatorRole();
  return {
    executable: Boolean(operatorRole),
    operatorRole: operatorRole || null,
  };
}

/* ─── Runs ─── */
export async function fetchRuns() {
  return withNormalizedError(() => desktopApiClient.fetchRuns() as Promise<RunSummary[]>);
}

export async function fetchRun(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchRun(runId) as Promise<RunDetailPayload>);
}

export type FetchEventsOptions = RequestControlOptions & { since?: string; limit?: number; tail?: boolean };

export async function fetchEvents(runId: string, options: FetchEventsOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchEvents(runId, options) as Promise<EventRecord[]>);
}

export function openEventsStream(runId: string, options: FetchEventsOptions = {}): EventsStream {
  return desktopApiClient.openEventsStream(runId, options) as FrontendStream as EventsStream;
}

export async function fetchDiff(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchDiff(runId) as Promise<{ diff: string }>);
}

export async function fetchReports(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchReports(runId) as Promise<ReportRecord[]>);
}

export async function fetchArtifact(runId: string, name: string) {
  return withNormalizedError(() => desktopApiClient.fetchArtifact(runId, name) as Promise<{ name: string; data: JsonValue }>);
}

export async function fetchRunSearch(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchRunSearch(runId) as Promise<Record<string, JsonValue>>);
}

export async function promoteEvidence(runId: string) {
  return withNormalizedError(() => desktopApiClient.promoteEvidence(runId) as Promise<{ ok: boolean; bundle?: JsonValue }>);
}

export async function rollbackRun(runId: string) {
  return withNormalizedError(() => desktopApiClient.rollbackRun(runId) as Promise<Record<string, JsonValue>>);
}

export async function rejectRun(runId: string) {
  return withNormalizedError(() => desktopApiClient.rejectRun(runId) as Promise<Record<string, JsonValue>>);
}

export async function replayRun(runId: string, baselineRunId?: string) {
  return withNormalizedError(() => desktopApiClient.replayRun(runId, baselineRunId) as Promise<Record<string, JsonValue>>);
}

export async function fetchOperatorCopilotBrief(runId: string) {
  return withNormalizedError(() =>
    desktopPostJson<OperatorCopilotBrief>(
      `/api/runs/${encodeURIComponent(runId)}/copilot-brief`,
      {},
      "Operator copilot failed",
    ),
  );
}

export async function fetchToolCalls(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchToolCalls(runId) as Promise<{ name: string; data: ToolCallRecord[] }>);
}

export async function fetchChainSpec(runId: string) {
  return withNormalizedError(() => desktopApiClient.fetchChainSpec(runId) as Promise<{ name: string; data: Record<string, JsonValue> | null }>);
}

/* ─── Contracts ─── */
export async function fetchContracts() {
  return withNormalizedError(() => desktopApiClient.fetchContracts() as Promise<ContractRecord[]>);
}

/* ─── Events (global) ─── */
export async function fetchAllEvents() {
  return withNormalizedError(() => desktopApiClient.fetchAllEvents() as Promise<EventRecord[]>);
}

/* ─── Diff Gate ─── */
export async function fetchDiffGate() {
  return withNormalizedError(() => desktopApiClient.fetchDiffGate() as Promise<Array<Record<string, JsonValue>>>);
}

/* ─── Reviews / Tests ─── */
export async function fetchReviews() {
  return withNormalizedError(() => desktopApiClient.fetchReviews() as Promise<Array<Record<string, JsonValue>>>);
}

export async function fetchTests() {
  return withNormalizedError(() => desktopApiClient.fetchTests() as Promise<Array<Record<string, JsonValue>>>);
}

/* ─── Agents ─── */
export async function fetchAgents() {
  return withNormalizedError(() => desktopApiClient.fetchAgents() as Promise<AgentCatalogPayload>);
}

export async function fetchAgentStatus(runId?: string) {
  return withNormalizedError(() => desktopApiClient.fetchAgentStatus(runId) as Promise<AgentStatusPayload>);
}

export async function fetchRoleConfig(role: string) {
  return withNormalizedError(() => desktopApiClient.fetchRoleConfig(role) as Promise<RoleConfigSurface>);
}

export async function previewRoleConfig(role: string, payload: Record<string, JsonValue>) {
  return withNormalizedError(() => desktopApiClient.previewRoleConfig(role, payload) as Promise<RoleConfigPreviewResponse>);
}

export async function applyRoleConfig(role: string, payload: Record<string, JsonValue>) {
  return withNormalizedError(() => desktopApiClient.applyRoleConfig(role, payload) as Promise<RoleConfigApplyResponse>);
}

/* ─── Policies ─── */
export async function fetchPolicies() {
  return withNormalizedError(() => desktopApiClient.fetchPolicies() as Promise<Record<string, JsonValue>>);
}

/* ─── Locks ─── */
export async function fetchLocks() {
  return withNormalizedError(() => desktopApiClient.fetchLocks() as Promise<Array<Record<string, JsonValue>>>);
}

/* ─── Worktrees ─── */
export async function fetchWorktrees() {
  return withNormalizedError(() => desktopApiClient.fetchWorktrees() as Promise<Array<Record<string, JsonValue>>>);
}

/* ─── Workflows ─── */
export async function fetchWorkflows() {
  return withNormalizedError(() => desktopApiClient.fetchWorkflows() as Promise<WorkflowRecord[]>);
}

export async function fetchWorkflow(workflowId: string) {
  return withNormalizedError(() => desktopApiClient.fetchWorkflow(workflowId) as Promise<WorkflowDetailPayload>);
}

export async function fetchQueue(workflowId?: string, status?: string) {
  return withNormalizedError(() => desktopApiClient.fetchQueue(workflowId, status) as Promise<QueueItemRecord[]>);
}

export async function enqueueRunQueue(runId: string, payload: Record<string, JsonValue> = {}) {
  return withNormalizedError(() => desktopApiClient.enqueueRunQueue(runId, payload) as Promise<Record<string, JsonValue>>);
}

export async function runNextQueue(payload: Record<string, JsonValue> = {}) {
  return withNormalizedError(() => desktopApiClient.runNextQueue(payload) as Promise<Record<string, JsonValue>>);
}

/* ─── PM Sessions ─── */
export type FetchPmSessionsOptions = RequestControlOptions & {
  status?: PmSessionStatus | PmSessionStatus[];
  ownerPm?: string;
  projectKey?: string;
  sort?: PmSessionSort;
  limit?: number;
  offset?: number;
};

export async function fetchPmSessions(options: FetchPmSessionsOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchPmSessions(options) as Promise<PmSessionSummary[]>);
}

export async function fetchPmSession(pmSessionId: string, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchPmSession(pmSessionId, options) as Promise<PmSessionDetailPayload>);
}

export type FetchPmSessionEventsOptions = FetchEventsOptions & { types?: string[]; runIds?: string[] };

export async function fetchPmSessionEvents(pmSessionId: string, options: FetchPmSessionEventsOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchPmSessionEvents(pmSessionId, options) as Promise<EventRecord[]>);
}

export async function fetchPmSessionConversationGraph(
  pmSessionId: string,
  window: "30m" | "2h" | "24h" = "30m",
  options: RequestControlOptions = {},
) {
  return withNormalizedError(
    () => desktopApiClient.fetchPmSessionConversationGraph(pmSessionId, window, options) as Promise<PmSessionConversationGraphPayload>,
  );
}

export async function fetchPmSessionMetrics(pmSessionId: string, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchPmSessionMetrics(pmSessionId, options) as Promise<PmSessionMetricsPayload>);
}

/* ─── Command Tower ─── */
export async function fetchCommandTowerOverview(options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchCommandTowerOverview(options) as Promise<CommandTowerOverviewPayload>);
}

export async function fetchCommandTowerAlerts(options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.fetchCommandTowerAlerts(options) as Promise<CommandTowerAlertsPayload>);
}

export async function fetchTaskPacks() {
  return withNormalizedError(() => desktopApiClient.fetchTaskPacks() as Promise<TaskPackManifest[]>);
}

/* ─── Intake ─── */
export async function createIntake(payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.createIntake(payload, options) as Promise<Record<string, JsonValue>>);
}

export async function previewIntake(payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.previewIntake(payload, options) as Promise<ExecutionPlanReport>);
}

export async function answerIntake(intakeId: string, payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.answerIntake(intakeId, payload, options) as Promise<Record<string, JsonValue>>);
}

export async function runIntake(intakeId: string, payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return withNormalizedError(() => desktopApiClient.runIntake(intakeId, payload, options) as Promise<Record<string, JsonValue>>);
}

export async function fetchWorkflowOperatorCopilotBrief(workflowId: string) {
  return withNormalizedError(() =>
    desktopPostJson<OperatorCopilotBrief>(
      `/api/workflows/${encodeURIComponent(workflowId)}/copilot-brief`,
      {},
      "Workflow copilot failed",
    ),
  );
}

/* ─── PM Session Messages ─── */
export async function postPmSessionMessage(pmSessionId: string, payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return withNormalizedError(
    () => desktopApiClient.postPmSessionMessage(pmSessionId, payload, options) as Promise<Record<string, JsonValue>>,
  );
}

/* ─── God Mode ─── */
export async function fetchPendingApprovals() {
  return withNormalizedError(() => desktopApiClient.fetchPendingApprovals() as Promise<Array<Record<string, JsonValue>>>);
}

export async function approveGodMode(runId: string) {
  return withNormalizedError(() => desktopApiClient.approveGodMode(runId) as Promise<Record<string, JsonValue>>);
}

export async function fetchWorkflowCopilotBrief(workflowId: string) {
  return fetchWorkflowOperatorCopilotBrief(workflowId);
}

export async function fetchFlightPlanCopilotBrief(executionPlanPreview: ExecutionPlanReport) {
  return withNormalizedError(() =>
    desktopPostJson<FlightPlanCopilotBrief>(
      "/api/intake/preview/copilot-brief",
      executionPlanPreview as unknown as Record<string, JsonValue>,
      "Flight Plan copilot failed",
    ),
  );
}

export async function previewFlightPlanCopilotBrief(
  executionPlanPreview: ExecutionPlanReport,
  _intakeId = "",
) {
  return fetchFlightPlanCopilotBrief(executionPlanPreview);
}

/* ─── Legacy aliases (used by useDesktopData) ─── */
export type DesktopOverviewPayload = CommandTowerOverviewPayload;
export type DesktopSessionSummary = { pm_session_id: string; status?: string; current_step?: string; owner_pm?: string };
export type DesktopAlert = { code?: string; severity?: "info" | "warning" | "critical"; message?: string };
export type DesktopAlertsPayload = { alerts?: DesktopAlert[] };
export type DesktopPmMessageRequest = { message: string; strict_acceptance?: boolean };
export type DesktopPmMessageResponse = { pm_session_id?: string; message?: string; status?: string };
export type DesktopPmMessageRequestOptions = RequestControlOptions | AbortSignal;

export function fetchDesktopOverview(signal?: AbortSignal): Promise<DesktopOverviewPayload> {
  return withNormalizedError(() => desktopApiClient.fetchDesktopOverview(signal) as Promise<DesktopOverviewPayload>);
}

export function fetchDesktopSessions(signal?: AbortSignal): Promise<DesktopSessionSummary[]> {
  return withNormalizedError(() => desktopApiClient.fetchDesktopSessions(signal) as Promise<DesktopSessionSummary[]>);
}

export function fetchDesktopAlerts(signal?: AbortSignal): Promise<DesktopAlertsPayload> {
  return withNormalizedError(() => desktopApiClient.fetchDesktopAlerts(signal) as Promise<DesktopAlertsPayload>);
}

export async function postDesktopPmMessage(
  sessionId: string,
  payload: DesktopPmMessageRequest,
  options?: DesktopPmMessageRequestOptions,
): Promise<DesktopPmMessageResponse> {
  try {
    return await withNormalizedError(
      () =>
        desktopApiClient.postDesktopPmMessage(sessionId, payload as Record<string, JsonValue>, options) as Promise<DesktopPmMessageResponse>,
    );
  } catch (error) {
    throw normalizeAbortTimeoutError(error);
  }
}
