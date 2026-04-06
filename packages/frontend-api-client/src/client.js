import { FRONTEND_API_CONTRACT } from "@cortexpilot/frontend-api-contract";
import { createAuthCore } from "./core/auth.js";
import { createHttpCore } from "./core/http.js";
import { createSseCore } from "./core/sse.js";

function encodeRunId(runId) {
  return encodeURIComponent(runId);
}

function appendRepeated(params, key, values) {
  if (!Array.isArray(values)) return;
  for (const raw of values) {
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;
    params.append(key, value);
  }
}

function buildPmSessionQuery(options = {}) {
  const params = new URLSearchParams();
  const query = FRONTEND_API_CONTRACT.query;

  if (typeof options.status === "string" && options.status.trim()) {
    const value = options.status.trim();
    params.set(query.status, value);
    params.set(query.statusArray, value);
  }
  if (Array.isArray(options.status)) {
    appendRepeated(params, query.status, options.status);
    appendRepeated(params, query.statusArray, options.status);
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
  return params;
}

function buildEventQuery(options = {}) {
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
  return params;
}

function buildPmSessionEventQuery(options = {}) {
  const params = buildEventQuery(options);
  const query = FRONTEND_API_CONTRACT.query;
  appendRepeated(params, query.types, options.types);
  appendRepeated(params, query.typesArray, options.types);
  appendRepeated(params, query.runIds, options.runIds);
  appendRepeated(params, query.runIdsArray, options.runIds);
  return params;
}

function withQuery(path, params) {
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function fillPathTemplate(pathTemplate, replacements = {}) {
  let nextPath = pathTemplate;
  for (const [key, rawValue] of Object.entries(replacements)) {
    nextPath = nextPath.replace(`{${key}}`, encodeURIComponent(String(rawValue)));
  }
  return nextPath;
}

function createClient(options = {}) {
  const baseUrl = options.baseUrl || FRONTEND_API_CONTRACT.defaultApiBase;
  const resolveMutationRole =
    typeof options.resolveMutationRole === "function" ? options.resolveMutationRole : () => undefined;
  const auth = createAuthCore({
    resolveToken: options.resolveToken,
  });
  const http = createHttpCore({
    baseUrl,
    auth,
    fetchImpl: options.fetchImpl,
    defaultTimeoutMs: options.defaultTimeoutMs,
    resolveMutationRole,
    surface: options.surface,
    component: options.component,
  });
  const sse = createSseCore({
    baseUrl,
    auth,
    fetchImpl: options.fetchImpl,
    eventSourceCtor: options.eventSourceCtor,
  });

  const paths = FRONTEND_API_CONTRACT.paths;

  async function fetchRuns() {
    return http.getJson(paths.runs);
  }

  async function fetchRun(runId) {
    return http.getJson(fillPathTemplate(paths.runDetail, { run_id: runId }), { runId });
  }

  async function fetchEvents(runId, optionsArg = {}) {
    return http.getJson(
      withQuery(fillPathTemplate(paths.runEvents, { run_id: runId }), buildEventQuery(optionsArg)),
      { ...optionsArg, runId },
    );
  }

  function openEventsStream(runId, optionsArg = {}) {
    return sse.open(fillPathTemplate(paths.runEventsStream, { run_id: runId }), buildEventQuery(optionsArg), {
      resolveToken: options.resolveToken,
    });
  }

  async function fetchDiff(runId) {
    return http.getJson(fillPathTemplate(paths.runDiff, { run_id: runId }), { runId });
  }

  async function fetchReports(runId) {
    return http.getJson(fillPathTemplate(paths.runReports, { run_id: runId }), { runId });
  }

  async function fetchArtifact(runId, name) {
    return http.getJson(`/api/runs/${encodeRunId(runId)}/artifacts?name=${encodeURIComponent(name)}`, { runId });
  }

  async function fetchRunSearch(runId) {
    return http.getJson(`/api/runs/${encodeRunId(runId)}/search`, { runId });
  }

  async function promoteEvidence(runId) {
    return http.postJson(`/api/runs/${encodeRunId(runId)}/evidence/promote`, {}, "Promote failed", { runId });
  }

  async function rollbackRun(runId) {
    return http.postJson(`/api/runs/${encodeRunId(runId)}/rollback`, {}, "Rollback failed", { runId });
  }

  async function rejectRun(runId) {
    return http.postJson(`/api/runs/${encodeRunId(runId)}/reject`, {}, "Reject failed", { runId });
  }

  async function replayRun(runId, baselineRunId) {
    const payload = {};
    if (typeof baselineRunId === "string" && baselineRunId.trim()) {
      payload.baseline_run_id = baselineRunId.trim();
    }
    return http.postJson(`/api/runs/${encodeRunId(runId)}/replay`, payload, "Replay failed", { runId });
  }

  async function fetchToolCalls(runId) {
    return http.getJson(`/api/runs/${encodeRunId(runId)}/artifacts?name=tool_calls.jsonl`, { runId });
  }

  async function fetchChainSpec(runId) {
    return http.getJson(`/api/runs/${encodeRunId(runId)}/artifacts?name=chain.json`, { runId });
  }

  async function fetchContracts() {
    return http.getJson(paths.contracts);
  }

  async function fetchAllEvents() {
    return http.getJson("/api/events");
  }

  async function fetchDiffGate() {
    return http.getJson("/api/diff-gate");
  }

  async function fetchReviews() {
    return http.getJson("/api/reviews");
  }

  async function fetchTests() {
    return http.getJson("/api/tests");
  }

  async function fetchAgents() {
    return http.getJson(paths.agents);
  }

  async function fetchAgentStatus(runId) {
    const normalizedRunId = typeof runId === "string" ? runId.trim() : "";
    const params = new URLSearchParams();
    if (normalizedRunId) {
      params.set("run_id", normalizedRunId);
    }
    return http.getJson(withQuery(paths.agentStatus, params), normalizedRunId ? { runId: normalizedRunId } : {});
  }

  async function fetchRoleConfig(role) {
    return http.getJson(fillPathTemplate(paths.roleConfig, { role }));
  }

  async function previewRoleConfig(role, payload = {}) {
    return http.postJson(
      fillPathTemplate(paths.roleConfigPreview, { role }),
      payload,
      "Role config preview failed",
    );
  }

  async function applyRoleConfig(role, payload = {}) {
    return http.postJson(
      fillPathTemplate(paths.roleConfigApply, { role }),
      payload,
      "Role config apply failed",
    );
  }

  async function fetchPolicies() {
    return http.getJson("/api/policies");
  }

  async function fetchLocks() {
    return http.getJson("/api/locks");
  }

  async function releaseLocks(paths) {
    return http.postJson("/api/locks/release", { paths }, "Release locks failed");
  }

  async function fetchWorktrees() {
    return http.getJson("/api/worktrees");
  }

  async function fetchWorkflows() {
    return http.getJson(paths.workflows);
  }

  async function fetchWorkflow(workflowId) {
    return http.getJson(fillPathTemplate(paths.workflowDetail, { workflow_id: workflowId }));
  }

  async function fetchQueue(workflowId, status) {
    const params = new URLSearchParams();
    if (typeof workflowId === "string" && workflowId.trim()) {
      params.set("workflow_id", workflowId.trim());
    }
    if (typeof status === "string" && status.trim()) {
      params.set("status", status.trim());
    }
    return http.getJson(withQuery(paths.queue, params));
  }

  async function enqueueRunQueue(runId, payload = {}) {
    return http.postJson(`/api/queue/from-run/${encodeRunId(runId)}`, payload, "Queue enqueue failed", { runId });
  }

  async function previewEnqueueRunQueue(runId, payload = {}) {
    return http.postJson(
      FRONTEND_API_CONTRACT.paths.queueEnqueuePreview.replace("{run_id}", encodeRunId(runId)),
      payload,
      "Queue enqueue preview failed",
      { runId },
    );
  }

  async function cancelQueueItem(queueId, payload = {}) {
    return http.postJson(
      FRONTEND_API_CONTRACT.paths.queueCancel.replace("{queue_id}", encodeURIComponent(queueId)),
      payload,
      "Queue cancel failed",
    );
  }

  async function runNextQueue(payload = {}) {
    return http.postJson("/api/queue/run-next", payload, "Queue run-next failed");
  }

  async function fetchPmSessions(optionsArg = {}) {
    return http.getJson(withQuery(paths.pmSessions, buildPmSessionQuery(optionsArg)), optionsArg);
  }

  async function fetchPmSession(pmSessionId, optionsArg = {}) {
    return http.getJson(`${paths.pmSessions}/${encodeURIComponent(pmSessionId)}`, optionsArg);
  }

  async function fetchPmSessionEvents(pmSessionId, optionsArg = {}) {
    return http.getJson(
      withQuery(`${paths.pmSessions}/${encodeURIComponent(pmSessionId)}/events`, buildPmSessionEventQuery(optionsArg)),
      optionsArg,
    );
  }

  async function fetchPmSessionConversationGraph(pmSessionId, optionsArg = "30m", requestOptions = {}) {
    const params = new URLSearchParams();
    if (typeof optionsArg === "string") {
      params.set("window", optionsArg);
    } else {
      if (typeof optionsArg.window === "string" && optionsArg.window.trim()) {
        params.set("window", optionsArg.window.trim());
      }
      if (optionsArg.groupByRole) {
        params.set("group_by_role", "1");
      }
    }
    return http.getJson(
      `${paths.pmSessions}/${encodeURIComponent(pmSessionId)}/conversation-graph?${params.toString()}`,
      requestOptions,
    );
  }

  async function fetchPmSessionMetrics(pmSessionId, optionsArg = {}) {
    return http.getJson(`${paths.pmSessions}/${encodeURIComponent(pmSessionId)}/metrics`, optionsArg);
  }

  async function fetchCommandTowerOverview(optionsArg = {}) {
    return http.getJson(paths.commandTowerOverview, optionsArg);
  }

  async function fetchCommandTowerAlerts(optionsArg = {}) {
    return http.getJson(paths.commandTowerAlerts, optionsArg);
  }

  async function fetchTaskPacks() {
    return http.getJson("/api/pm/task-packs");
  }

  async function createIntake(payload, optionsArg = {}) {
    return http.postJson("/api/pm/intake", payload, "Intake create failed", optionsArg);
  }

  async function previewIntake(payload, optionsArg = {}) {
    return http.postJson("/api/pm/intake/preview", payload, "Intake preview failed", optionsArg);
  }

  async function answerIntake(intakeId, payload, optionsArg = {}) {
    return http.postJson(`/api/pm/intake/${encodeURIComponent(intakeId)}/answer`, payload, "Intake answer failed", optionsArg);
  }

  async function runIntake(intakeId, payload, optionsArg = {}) {
    return http.postJson(`/api/pm/intake/${encodeURIComponent(intakeId)}/run`, payload, "Intake run failed", optionsArg);
  }

  async function postPmSessionMessage(pmSessionId, payload, optionsArg = {}) {
    const messagePath = paths.pmSessionMessages.replace("{pm_session_id}", encodeURIComponent(pmSessionId));
    return http.postJson(messagePath, payload, "PM session message failed", optionsArg);
  }

  async function fetchPendingApprovals() {
    return http.getJson("/api/god-mode/pending");
  }

  async function approveGodMode(runId) {
    return http.postJson("/api/god-mode/approve", { run_id: runId }, "Approve failed");
  }

  function fetchDesktopOverview(signal) {
    return fetchCommandTowerOverview({ signal });
  }

  function fetchDesktopSessions(signal) {
    return fetchPmSessions({ limit: 10, sort: "updated_desc", signal });
  }

  function fetchDesktopAlerts(signal) {
    return fetchCommandTowerAlerts({ signal });
  }

  async function postDesktopPmMessage(sessionId, payload, optionsArg = {}) {
    const requestOptions =
      optionsArg && typeof optionsArg === "object" && "aborted" in optionsArg
        ? { signal: optionsArg }
        : optionsArg;
    return postPmSessionMessage(sessionId, payload, requestOptions);
  }

  function canExecuteMutations() {
    return http.canExecuteMutations();
  }

  function getMutationRole() {
    return http.getMutationRole();
  }

  return {
    fetchRuns,
    fetchRun,
    fetchEvents,
    openEventsStream,
    fetchDiff,
    fetchReports,
    fetchArtifact,
    fetchRunSearch,
    promoteEvidence,
    rollbackRun,
    rejectRun,
    replayRun,
    fetchToolCalls,
    fetchChainSpec,
    fetchContracts,
    fetchAllEvents,
    fetchDiffGate,
    fetchReviews,
    fetchTests,
    fetchAgents,
    fetchAgentStatus,
    fetchRoleConfig,
    previewRoleConfig,
    applyRoleConfig,
    fetchPolicies,
    fetchLocks,
    releaseLocks,
    fetchWorktrees,
    fetchWorkflows,
    fetchWorkflow,
    fetchQueue,
    enqueueRunQueue,
    previewEnqueueRunQueue,
    cancelQueueItem,
    runNextQueue,
    fetchPmSessions,
    fetchPmSession,
    fetchPmSessionEvents,
    fetchPmSessionConversationGraph,
    fetchPmSessionMetrics,
    fetchCommandTowerOverview,
    fetchCommandTowerAlerts,
    fetchTaskPacks,
    createIntake,
    previewIntake,
    answerIntake,
    runIntake,
    postPmSessionMessage,
    fetchPendingApprovals,
    approveGodMode,
    fetchDesktopOverview,
    fetchDesktopSessions,
    fetchDesktopAlerts,
    postDesktopPmMessage,
    canExecuteMutations,
    getMutationRole,
  };
}

export function createFrontendApiClient(options = {}) {
  return createClient(options);
}

export function createDashboardApiClient(options = {}) {
  return createClient({ ...options, surface: "dashboard", component: "dashboard_api_client" });
}

export function createDesktopApiClient(options = {}) {
  return createClient({ ...options, surface: "desktop", component: "desktop_api_client" });
}
