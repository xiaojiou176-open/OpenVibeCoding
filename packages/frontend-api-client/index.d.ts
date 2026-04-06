import type {
  AgentCatalogPayload,
  AgentStatusPayload,
  ContractCatalogRecord,
  RoleConfigApplyResponse,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
} from "@cortexpilot/frontend-api-contract";

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type CortexPilotLogDomain = "runtime" | "api" | "ui" | "desktop" | "ci" | "e2e" | "test" | "governance";
export type CortexPilotLogSurface = "backend" | "dashboard" | "desktop" | "ci" | "tooling";
export type CortexPilotLogSourceKind = "app_log" | "test_log" | "ci_log" | "artifact_manifest" | "event_stream";

export type RequestControlOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type FrontendApiClientOptions = {
  baseUrl?: string;
  defaultTimeoutMs?: number;
  resolveToken?: () => string | undefined;
  resolveMutationRole?: () => string | undefined;
  fetchImpl?: typeof fetch;
  eventSourceCtor?: typeof EventSource;
  surface?: string;
  component?: string;
};

export type FrontendApiClient = {
  fetchRuns: () => Promise<unknown>;
  fetchRun: (runId: string) => Promise<unknown>;
  fetchEvents: (runId: string, options?: RequestControlOptions & { since?: string; limit?: number; tail?: boolean }) => Promise<unknown>;
  openEventsStream: (runId: string, options?: RequestControlOptions & { since?: string; limit?: number; tail?: boolean }) => EventSource | {
    onopen: ((this: unknown, ev: Event) => void) | null;
    onmessage: ((this: unknown, ev: MessageEvent) => void) | null;
    onerror: ((this: unknown, ev: Event) => void) | null;
    close: () => void;
  };
  fetchDiff: (runId: string) => Promise<unknown>;
  fetchReports: (runId: string) => Promise<unknown>;
  fetchArtifact: (runId: string, name: string) => Promise<unknown>;
  fetchRunSearch: (runId: string) => Promise<unknown>;
  promoteEvidence: (runId: string) => Promise<unknown>;
  rollbackRun: (runId: string) => Promise<unknown>;
  rejectRun: (runId: string) => Promise<unknown>;
  replayRun: (runId: string, baselineRunId?: string) => Promise<unknown>;
  fetchToolCalls: (runId: string) => Promise<unknown>;
  fetchChainSpec: (runId: string) => Promise<unknown>;
  fetchContracts: () => Promise<ContractCatalogRecord[]>;
  fetchAllEvents: () => Promise<unknown>;
  fetchDiffGate: () => Promise<unknown>;
  fetchReviews: () => Promise<unknown>;
  fetchTests: () => Promise<unknown>;
  fetchAgents: () => Promise<AgentCatalogPayload>;
  fetchAgentStatus: (runId?: string) => Promise<AgentStatusPayload>;
  fetchRoleConfig: (role: string) => Promise<RoleConfigSurface>;
  previewRoleConfig: (role: string, payload?: Record<string, JsonValue>) => Promise<RoleConfigPreviewResponse>;
  applyRoleConfig: (role: string, payload?: Record<string, JsonValue>) => Promise<RoleConfigApplyResponse>;
  fetchPolicies: () => Promise<unknown>;
  fetchLocks: () => Promise<unknown>;
  releaseLocks: (paths: string[]) => Promise<unknown>;
  fetchWorktrees: () => Promise<unknown>;
  fetchWorkflows: () => Promise<unknown>;
  fetchWorkflow: (workflowId: string) => Promise<unknown>;
  fetchQueue: (workflowId?: string, status?: string) => Promise<unknown>;
  enqueueRunQueue: (runId: string, payload?: Record<string, JsonValue>) => Promise<unknown>;
  previewEnqueueRunQueue: (runId: string, payload?: Record<string, JsonValue>) => Promise<unknown>;
  cancelQueueItem: (queueId: string, payload?: Record<string, JsonValue>) => Promise<unknown>;
  runNextQueue: (payload?: Record<string, JsonValue>) => Promise<unknown>;
  fetchPmSessions: (options?: RequestControlOptions & {
    status?: string | string[];
    ownerPm?: string;
    projectKey?: string;
    sort?: string;
    limit?: number;
    offset?: number;
  }) => Promise<unknown>;
  fetchPmSession: (pmSessionId: string, options?: RequestControlOptions) => Promise<unknown>;
  fetchPmSessionEvents: (pmSessionId: string, options?: RequestControlOptions & {
    since?: string;
    limit?: number;
    tail?: boolean;
    types?: string[];
    runIds?: string[];
  }) => Promise<unknown>;
  fetchPmSessionConversationGraph: (
    pmSessionId: string,
    options?: "30m" | "2h" | "24h" | { window?: "30m" | "2h" | "24h"; groupByRole?: boolean },
    requestOptions?: RequestControlOptions,
  ) => Promise<unknown>;
  fetchPmSessionMetrics: (pmSessionId: string, options?: RequestControlOptions) => Promise<unknown>;
  fetchCommandTowerOverview: (options?: RequestControlOptions) => Promise<unknown>;
  fetchCommandTowerAlerts: (options?: RequestControlOptions) => Promise<unknown>;
  fetchTaskPacks: () => Promise<unknown>;
  createIntake: (payload: Record<string, JsonValue>, options?: RequestControlOptions) => Promise<unknown>;
  previewIntake: (payload: Record<string, JsonValue>, options?: RequestControlOptions) => Promise<unknown>;
  answerIntake: (intakeId: string, payload: Record<string, JsonValue>, options?: RequestControlOptions) => Promise<unknown>;
  runIntake: (intakeId: string, payload: Record<string, JsonValue>, options?: RequestControlOptions) => Promise<unknown>;
  postPmSessionMessage: (pmSessionId: string, payload: Record<string, JsonValue>, options?: RequestControlOptions) => Promise<unknown>;
  fetchPendingApprovals: () => Promise<unknown>;
  approveGodMode: (runId: string) => Promise<unknown>;
  fetchDesktopOverview: (signal?: AbortSignal) => Promise<unknown>;
  fetchDesktopSessions: (signal?: AbortSignal) => Promise<unknown>;
  fetchDesktopAlerts: (signal?: AbortSignal) => Promise<unknown>;
  postDesktopPmMessage: (sessionId: string, payload: Record<string, JsonValue>, options?: RequestControlOptions | AbortSignal) => Promise<unknown>;
};

export declare function createFrontendApiClient(options?: FrontendApiClientOptions): FrontendApiClient;
export declare function createDashboardApiClient(options?: FrontendApiClientOptions): FrontendApiClient;
export declare function createDesktopApiClient(options?: FrontendApiClientOptions): FrontendApiClient;
export type ControlPlaneStarterBootstrap = {
  overview: unknown;
  agents: AgentCatalogPayload;
  contracts: ContractCatalogRecord[];
  roleConfig: RoleConfigSurface | null;
  role: string | null;
};

export type ControlPlaneStarterRoleWorkspace = {
  role: string;
  agents: AgentCatalogPayload;
  contracts: ContractCatalogRecord[];
  roleConfig: RoleConfigSurface;
};

export type ControlPlaneStarter = {
  fetchBootstrap: (options?: { role?: string; requestOptions?: RequestControlOptions }) => Promise<ControlPlaneStarterBootstrap>;
  fetchRoleWorkspace: (role: string) => Promise<ControlPlaneStarterRoleWorkspace>;
  previewRoleDefaults: (role: string, payload?: Record<string, JsonValue>) => Promise<RoleConfigPreviewResponse>;
  applyRoleDefaults: (role: string, payload?: Record<string, JsonValue>) => Promise<RoleConfigApplyResponse>;
  previewQueueEnqueue: (runId: string, payload?: Record<string, JsonValue>) => Promise<unknown>;
  cancelPendingQueueItem: (queueId: string, payload?: Record<string, JsonValue>) => Promise<unknown>;
};

export declare function createControlPlaneStarter(client: FrontendApiClient): ControlPlaneStarter;

export declare function createAuthCore(options?: { resolveToken?: () => string | undefined }): {
  authHeaders: (extra?: HeadersInit) => HeadersInit;
  authJsonHeaders: (extra?: HeadersInit) => HeadersInit;
};

export declare function createHttpCore(options: {
  baseUrl: string;
  auth: { authHeaders: (extra?: HeadersInit) => HeadersInit; authJsonHeaders: (extra?: HeadersInit) => HeadersInit };
  fetchImpl?: typeof fetch;
  defaultTimeoutMs?: number;
  resolveMutationRole?: () => string | undefined;
  surface?: string;
  component?: string;
}): {
  request: (method: string, path: string, requestOptions?: RequestInit & RequestControlOptions) => Promise<Response>;
  getJson: <T = unknown>(path: string, options?: RequestControlOptions) => Promise<T>;
  postJson: <T = unknown>(path: string, payload: Record<string, JsonValue>, errorFallback: string, options?: RequestControlOptions) => Promise<T>;
};

export type CortexPilotLogEvent = {
  ts: string;
  level: string;
  domain: CortexPilotLogDomain;
  surface: CortexPilotLogSurface;
  service: string;
  component: string;
  event: string;
  lane: "runtime" | "error" | "access" | "e2e" | "ci" | "governance";
  run_id: string;
  request_id: string;
  trace_id: string;
  session_id: string;
  test_id: string;
  source_kind: CortexPilotLogSourceKind;
  artifact_kind: string;
  correlation_kind: "run" | "session" | "test" | "request" | "trace" | "none";
  meta: Record<string, unknown>;
  redaction_version: "redaction.v1";
  schema_version: "log_event.v2";
};

export type CortexPilotLogEventInput = {
  level?: string;
  domain?: CortexPilotLogDomain;
  surface?: CortexPilotLogSurface;
  service?: string;
  component?: string;
  event: string;
  lane?: "runtime" | "error" | "access" | "e2e" | "ci" | "governance";
  run_id?: string | null;
  request_id?: string | null;
  trace_id?: string | null;
  session_id?: string | null;
  test_id?: string | null;
  source_kind?: CortexPilotLogSourceKind;
  artifact_kind?: string | null;
  correlation_kind?: "run" | "session" | "test" | "request" | "trace" | "none";
  meta?: Record<string, unknown>;
};

export declare function buildFrontendLogEvent(input: CortexPilotLogEventInput): CortexPilotLogEvent;
export declare function emitFrontendLogEvent(input: CortexPilotLogEventInput): CortexPilotLogEvent;

export declare function createSseCore(options: {
  baseUrl: string;
  auth: { authHeaders: (extra?: HeadersInit) => HeadersInit };
  fetchImpl?: typeof fetch;
  eventSourceCtor?: typeof EventSource;
}): {
  open: (
    path: string,
    query?: Record<string, string | number | boolean | undefined>,
    options?: { resolveToken?: () => string | undefined },
  ) => EventSource | {
    onopen: ((this: unknown, ev: Event) => void) | null;
    onmessage: ((this: unknown, ev: MessageEvent) => void) | null;
    onerror: ((this: unknown, ev: Event) => void) | null;
    close: () => void;
  };
};
