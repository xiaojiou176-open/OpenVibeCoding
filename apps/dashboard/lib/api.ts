import { createAuthCore, createDashboardApiClient, createHttpCore } from "@openvibecoding/frontend-api-client";
import { FRONTEND_API_CONTRACT } from "@openvibecoding/frontend-api-contract";
import type { PmSessionSort } from "@openvibecoding/frontend-api-contract";
import type {
  AgentCatalogPayload,
  AgentStatusPayload,
  CommandTowerAlertsPayload,
  CommandTowerOverviewPayload,
  ContractRecord,
  ExecutionPlanReport,
  EventRecord,
  JsonValue,
  OperatorCopilotBrief,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
  PmSessionStatus,
  PmSessionSummary,
  ReportRecord,
  RoleConfigApplyResponse,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
  RunDetailPayload,
  RunSummary,
  QueueItemRecord,
  ToolCallRecord,
  TaskPackManifest,
  WorkflowDetailPayload,
  WorkflowRecord,
} from "./types";
import { resolveDashboardApiBase, resolveDashboardOperatorRoleEnv } from "./env";

const API_BASE = resolveDashboardApiBase();
const DEFAULT_REQUEST_TIMEOUT_MS = 10000;
const API_PATHS = FRONTEND_API_CONTRACT.paths;
const API_QUERY = FRONTEND_API_CONTRACT.query;

type RequestControlOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

function resolveServerApiToken(): string | undefined {
  if (typeof window !== "undefined") {
    return undefined;
  }
  if (typeof process === "undefined" || !process.env) {
    return undefined;
  }
  const primary = process.env.OPENVIBECODING_API_TOKEN?.trim();
  if (primary) {
    return primary;
  }
  const fallback = process.env.OPENVIBECODING_E2E_API_TOKEN?.trim();
  return fallback || undefined;
}

function resolveDashboardOperatorRole(): string | undefined {
  const role = resolveDashboardOperatorRoleEnv();
  return role ? role.toUpperCase() : undefined;
}

export function mutationExecutionCapability(): { executable: boolean; operatorRole: string | null } {
  const operatorRole = resolveDashboardOperatorRole();
  return {
    executable: Boolean(operatorRole),
    operatorRole: operatorRole || null,
  };
}

function resolveRequestPath(input: RequestInfo | URL): string {
  let candidate = "";
  if (typeof input === "string") {
    candidate = input;
  } else if (input instanceof URL) {
    candidate = input.toString();
  } else if (typeof Request !== "undefined" && input instanceof Request) {
    candidate = input.url;
  } else {
    const maybeUrl = (input as { url?: unknown }).url;
    candidate = typeof maybeUrl === "string" ? maybeUrl : String(input);
  }

  try {
    const resolved = new URL(candidate, API_BASE);
    return `${resolved.pathname}${resolved.search}`;
  } catch {
    return candidate;
  }
}

function attachJsonCompat(response: Response, path: string): Response {
  const target = response as Response & {
    json?: () => Promise<unknown>;
    text?: () => Promise<string>;
  };
  if (typeof target.json === "function") {
    return response;
  }

  target.json = async () => {
    if (typeof target.text !== "function") {
      throw new Error(`API ${path} returned empty response`);
    }
    const body = await target.text();
    if (!body.trim()) {
      throw new Error(`API ${path} returned empty response`);
    }
    try {
      return JSON.parse(body) as unknown;
    } catch {
      throw new Error(`API ${path} returned non-JSON response`);
    }
  };

  return response;
}

const dynamicFetchCompat: typeof fetch = async (input, init) => {
  const activeFetch = globalThis.fetch;
  if (typeof activeFetch !== "function") {
    throw new Error("fetch implementation is required");
  }
  const response = (await activeFetch(input, init)) as Response;
  return attachJsonCompat(response, resolveRequestPath(input));
};

const dynamicEventSourceCtor = function (url: string | URL, init?: EventSourceInit): EventSource {
  const EventSourceCtor = globalThis.EventSource as unknown as {
    new (value: string | URL, options?: EventSourceInit): EventSource;
  };
  return new EventSourceCtor(url, init);
} as unknown as typeof EventSource;

const sharedDashboardApi = createDashboardApiClient({
  baseUrl: API_BASE,
  defaultTimeoutMs: DEFAULT_REQUEST_TIMEOUT_MS,
  resolveToken: resolveServerApiToken,
  fetchImpl: dynamicFetchCompat,
  eventSourceCtor: dynamicEventSourceCtor,
  resolveMutationRole: resolveDashboardOperatorRole,
} as Parameters<typeof createDashboardApiClient>[0]);

const sharedDashboardHttp = createHttpCore({
  baseUrl: API_BASE,
  auth: createAuthCore({ resolveToken: resolveServerApiToken }),
  fetchImpl: dynamicFetchCompat,
  defaultTimeoutMs: DEFAULT_REQUEST_TIMEOUT_MS,
  resolveMutationRole: resolveDashboardOperatorRole,
} as Parameters<typeof createHttpCore>[0]);

async function delegateApi<T>(call: () => Promise<unknown>): Promise<T> {
  return (await call()) as T;
}

async function delegateGetApi<T>(call: () => Promise<unknown>): Promise<T> {
  try {
    return (await call()) as T;
  } catch (error) {
    if (error instanceof Error) {
      const match = error.message.match(/^(API\s+\/api\/\S+\sfailed:\s\d+)\s\(.+\)$/);
      if (match) {
        throw new Error(match[1]);
      }
      throw error;
    }
    throw error;
  }
}

export async function fetchRuns() {
  return delegateGetApi<RunSummary[]>(() => sharedDashboardApi.fetchRuns());
}

export async function fetchRun(runId: string) {
  return delegateGetApi<RunDetailPayload>(() => sharedDashboardApi.fetchRun(runId));
}

export type FetchEventsOptions = RequestControlOptions & {
  since?: string;
  limit?: number;
  tail?: boolean;
};

export async function fetchEvents(runId: string, options: FetchEventsOptions = {}) {
  return delegateGetApi<EventRecord[]>(() => sharedDashboardApi.fetchEvents(runId, options));
}

export function openEventsStream(runId: string, options: FetchEventsOptions = {}): EventSource {
  return sharedDashboardApi.openEventsStream(runId, options) as EventSource;
}

export async function fetchDiff(runId: string) {
  return delegateGetApi<{ diff: string }>(() => sharedDashboardApi.fetchDiff(runId));
}

export async function fetchReports(runId: string) {
  return delegateGetApi<ReportRecord[]>(() => sharedDashboardApi.fetchReports(runId));
}

export async function fetchArtifact(runId: string, name: string) {
  return delegateGetApi<{ name: string; data: JsonValue }>(() => sharedDashboardApi.fetchArtifact(runId, name));
}

export async function fetchRunSearch(runId: string) {
  return delegateGetApi<Record<string, JsonValue>>(() => sharedDashboardApi.fetchRunSearch(runId));
}

export async function promoteEvidence(runId: string) {
  return delegateApi<{ ok: boolean; bundle?: JsonValue }>(() => sharedDashboardApi.promoteEvidence(runId));
}

export async function fetchContracts() {
  return delegateGetApi<ContractRecord[]>(() => sharedDashboardApi.fetchContracts());
}

export async function fetchAllEvents() {
  return delegateGetApi<EventRecord[]>(() => sharedDashboardApi.fetchAllEvents());
}

export async function fetchDiffGate() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchDiffGate());
}

export async function rollbackRun(runId: string) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.rollbackRun(runId));
}

export async function rejectRun(runId: string) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.rejectRun(runId));
}

export async function fetchReviews() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchReviews());
}

export async function fetchTests() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchTests());
}

export async function fetchAgents() {
  return delegateGetApi<AgentCatalogPayload>(() => sharedDashboardApi.fetchAgents());
}

export async function fetchAgentStatus(runId?: string) {
  return delegateGetApi<AgentStatusPayload>(() => sharedDashboardApi.fetchAgentStatus(runId));
}

export async function fetchRoleConfig(role: string) {
  return delegateGetApi<RoleConfigSurface>(() => sharedDashboardApi.fetchRoleConfig(role));
}

export async function previewRoleConfig(role: string, payload: Record<string, JsonValue>) {
  return delegateApi<RoleConfigPreviewResponse>(() => sharedDashboardApi.previewRoleConfig(role, payload));
}

export async function applyRoleConfig(role: string, payload: Record<string, JsonValue>) {
  return delegateApi<RoleConfigApplyResponse>(() => sharedDashboardApi.applyRoleConfig(role, payload));
}

export async function fetchPolicies() {
  return delegateGetApi<Record<string, JsonValue>>(() => sharedDashboardApi.fetchPolicies());
}

export async function fetchLocks() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchLocks());
}

export async function releaseLocks(paths: string[]) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.releaseLocks(paths));
}

export async function fetchWorktrees() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchWorktrees());
}

export async function fetchWorkflows() {
  return delegateGetApi<WorkflowRecord[]>(() => sharedDashboardApi.fetchWorkflows());
}

export async function fetchWorkflow(workflowId: string) {
  return delegateGetApi<WorkflowDetailPayload>(() => sharedDashboardApi.fetchWorkflow(workflowId));
}

export async function fetchQueue(workflowId?: string, status?: string) {
  return delegateGetApi<QueueItemRecord[]>(() => sharedDashboardApi.fetchQueue(workflowId, status));
}

export async function enqueueRunQueue(runId: string, payload: Record<string, JsonValue> = {}) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.enqueueRunQueue(runId, payload));
}

export async function runNextQueue(payload: Record<string, JsonValue> = {}) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.runNextQueue(payload));
}

export type FetchPmSessionsOptions = RequestControlOptions & {
  status?: PmSessionStatus | PmSessionStatus[];
  ownerPm?: string;
  projectKey?: string;
  sort?: PmSessionSort;
  limit?: number;
  offset?: number;
};

export async function fetchPmSessions(options: FetchPmSessionsOptions = {}) {
  const params = new URLSearchParams();
  if (typeof options.status === "string" && options.status.trim()) {
    const value = options.status.trim();
    params.set(API_QUERY.status, value);
    params.set(API_QUERY.statusArray, value);
  } else if (Array.isArray(options.status)) {
    for (const statusItem of options.status) {
      if (typeof statusItem === "string" && statusItem.trim()) {
        const value = statusItem.trim();
        params.append(API_QUERY.statusArray, value);
        params.append(API_QUERY.status, value);
      }
    }
  }
  if (typeof options.ownerPm === "string" && options.ownerPm.trim()) {
    params.set("owner_pm", options.ownerPm.trim());
  }
  if (typeof options.projectKey === "string" && options.projectKey.trim()) {
    params.set("project_key", options.projectKey.trim());
  }
  if (typeof options.sort === "string" && options.sort.trim()) {
    params.set("sort", options.sort.trim());
  }
  if (typeof options.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    params.set("limit", String(Math.floor(options.limit)));
  }
  if (typeof options.offset === "number" && Number.isFinite(options.offset) && options.offset >= 0) {
    params.set("offset", String(Math.floor(options.offset)));
  }
  const qs = params.toString();
  const path = qs ? `${API_PATHS.pmSessions}?${qs}` : API_PATHS.pmSessions;
  return delegateGetApi<PmSessionSummary[]>(() => sharedDashboardHttp.getJson(path, options));
}

export async function fetchPmSession(pmSessionId: string, options: RequestControlOptions = {}) {
  return delegateGetApi<PmSessionDetailPayload>(() => sharedDashboardApi.fetchPmSession(pmSessionId, options));
}

export type FetchPmSessionEventsOptions = FetchEventsOptions & {
  types?: string[];
  runIds?: string[];
};

export async function fetchPmSessionEvents(pmSessionId: string, options: FetchPmSessionEventsOptions = {}) {
  const encoded = encodeURIComponent(pmSessionId);
  const params = new URLSearchParams();
  if (typeof options.since === "string" && options.since.trim()) {
    params.set("since", options.since.trim());
  }
  if (typeof options.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    params.set("limit", String(Math.floor(options.limit)));
  }
  if (options.tail) {
    params.set("tail", "1");
  }
  if (Array.isArray(options.types)) {
    for (const type of options.types) {
      if (typeof type === "string" && type.trim()) {
        const value = type.trim();
        params.append(API_QUERY.typesArray, value);
        params.append(API_QUERY.types, value);
      }
    }
  }
  if (Array.isArray(options.runIds)) {
    for (const runId of options.runIds) {
      if (typeof runId === "string" && runId.trim()) {
        const value = runId.trim();
        params.append(API_QUERY.runIdsArray, value);
        params.append(API_QUERY.runIds, value);
      }
    }
  }
  const qs = params.toString();
  const path = qs
    ? `${API_PATHS.pmSessions}/${encoded}/events?${qs}`
    : `${API_PATHS.pmSessions}/${encoded}/events`;
  return delegateGetApi<EventRecord[]>(() => sharedDashboardHttp.getJson(path, options));
}

export type FetchPmSessionConversationGraphOptions = {
  window?: "30m" | "2h" | "24h";
  groupByRole?: boolean;
};

export async function fetchPmSessionConversationGraph(
  pmSessionId: string,
  options: FetchPmSessionConversationGraphOptions | "30m" | "2h" | "24h" = "30m",
  requestOptions: RequestControlOptions = {},
) {
  return delegateGetApi<PmSessionConversationGraphPayload>(() =>
    sharedDashboardApi.fetchPmSessionConversationGraph(pmSessionId, options, requestOptions),
  );
}

export async function fetchPmSessionMetrics(pmSessionId: string, options: RequestControlOptions = {}) {
  return delegateGetApi<PmSessionMetricsPayload>(() => sharedDashboardApi.fetchPmSessionMetrics(pmSessionId, options));
}

export async function fetchCommandTowerOverview(options: RequestControlOptions = {}) {
  return delegateGetApi<CommandTowerOverviewPayload>(() => sharedDashboardApi.fetchCommandTowerOverview(options));
}

export async function fetchCommandTowerAlerts(options: RequestControlOptions = {}) {
  return delegateGetApi<CommandTowerAlertsPayload>(() => sharedDashboardApi.fetchCommandTowerAlerts(options));
}

export async function fetchTaskPacks() {
  return delegateGetApi<TaskPackManifest[]>(() => sharedDashboardApi.fetchTaskPacks());
}

export async function createIntake(payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.createIntake(payload, options));
}

export async function previewIntake(payload: Record<string, JsonValue>, options: RequestControlOptions = {}) {
  return delegateApi<ExecutionPlanReport>(() => sharedDashboardApi.previewIntake(payload, options));
}

export async function answerIntake(
  intakeId: string,
  payload: Record<string, JsonValue>,
  options: RequestControlOptions = {},
) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.answerIntake(intakeId, payload, options));
}

export async function runIntake(
  intakeId: string,
  payload: Record<string, JsonValue>,
  options: RequestControlOptions = {},
) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.runIntake(intakeId, payload, options));
}

export async function postPmSessionMessage(
  pmSessionId: string,
  payload: Record<string, JsonValue>,
  options: RequestControlOptions = {},
) {
  return delegateApi<Record<string, JsonValue>>(() =>
    sharedDashboardApi.postPmSessionMessage(pmSessionId, payload, options),
  );
}

export async function fetchPendingApprovals() {
  return delegateGetApi<Array<Record<string, JsonValue>>>(() => sharedDashboardApi.fetchPendingApprovals());
}

export async function approveGodMode(runId: string) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.approveGodMode(runId));
}

export async function fetchToolCalls(runId: string) {
  return delegateGetApi<{ name: string; data: ToolCallRecord[] }>(() => sharedDashboardApi.fetchToolCalls(runId));
}

export async function fetchChainSpec(runId: string) {
  return delegateGetApi<{ name: string; data: Record<string, JsonValue> | null }>(() =>
    sharedDashboardApi.fetchChainSpec(runId),
  );
}

export async function replayRun(runId: string, baselineRunId?: string) {
  return delegateApi<Record<string, JsonValue>>(() => sharedDashboardApi.replayRun(runId, baselineRunId));
}

export async function fetchOperatorCopilotBrief(runId: string) {
  return delegateApi<OperatorCopilotBrief>(() =>
    sharedDashboardHttp.postJson(`/api/runs/${encodeURIComponent(runId)}/copilot-brief`, {}, "Operator copilot failed"),
  );
}

export async function fetchWorkflowCopilotBrief(workflowId: string) {
  return delegateApi<OperatorCopilotBrief>(() =>
    sharedDashboardHttp.postJson(
      `/api/workflows/${encodeURIComponent(workflowId)}/copilot-brief`,
      {},
      "Workflow copilot failed",
    ),
  );
}

export async function fetchFlightPlanCopilotBrief(preview: ExecutionPlanReport, intakeId = "") {
  return delegateApi<OperatorCopilotBrief>(() =>
    sharedDashboardHttp.postJson(
      "/api/pm/intake/preview/copilot-brief",
      {
        ...(preview as Record<string, JsonValue>),
        intake_id: intakeId,
      },
      "Flight Plan copilot failed",
    ),
  );
}

export const fetchWorkflowOperatorCopilotBrief = fetchWorkflowCopilotBrief;
export function previewFlightPlanCopilotBrief(
  executionPlanPreview: ExecutionPlanReport,
  intakeId = "",
) {
  return fetchFlightPlanCopilotBrief(executionPlanPreview, intakeId);
}
