import test from "node:test";
import assert from "node:assert/strict";
import { FRONTEND_API_CONTRACT } from "@openvibecoding/frontend-api-contract";
import { createDashboardApiClient, createDesktopApiClient } from "../index.js";

function createJsonResponse(body) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => "application/json" },
    async json() {
      return body;
    },
  };
}

test("dashboard client sends auth + trace headers and hits runs endpoint", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    resolveToken: () => "token-dashboard",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  const payload = await client.fetchRuns();
  assert.deepEqual(payload, { ok: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runs}`);
  assert.equal(calls[0].init.headers.Authorization, "Bearer token-dashboard");
  assert.equal(typeof calls[0].init.headers["x-request-id"], "string");
  assert.equal(typeof calls[0].init.headers["x-trace-id"], "string");
  assert.equal(typeof calls[0].init.headers.traceparent, "string");
});

test("dashboard client openEventsStream builds stream url and forwards credentials option", () => {
  const eventSourceCalls = [];
  class FakeEventSource {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      eventSourceCalls.push({ url, options });
    }
    close() {}
  }

  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    eventSourceCtor: FakeEventSource,
    fetchImpl: null,
  });

  const stream = client.openEventsStream("run-1", {
    since: "cursor-1",
    limit: 5,
    tail: true,
  });
  assert.ok(stream);
  assert.equal(eventSourceCalls.length, 1);
  assert.equal(
    eventSourceCalls[0].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runEventsStream.replace("{run_id}", "run-1")}?since=cursor-1&limit=5&tail=1`,
  );
  assert.deepEqual(eventSourceCalls[0].options, { withCredentials: true });
});

test("dashboard client uses contract-backed run detail routes", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchRun("run/1");
  await client.fetchEvents("run/1", { tail: true });
  await client.fetchDiff("run/1");
  await client.fetchReports("run/1");

  assert.equal(
    calls[0].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runDetail.replace("{run_id}", "run%2F1")}`,
  );
  assert.equal(
    calls[1].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runEvents.replace("{run_id}", "run%2F1")}?tail=1`,
  );
  assert.equal(
    calls[2].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runDiff.replace("{run_id}", "run%2F1")}`,
  );
  assert.equal(
    calls[3].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.runReports.replace("{run_id}", "run%2F1")}`,
  );
});

test("dashboard client uses PM endpoints contract for list + message posting", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchPmSessions({ status: ["blocked", "running"], limit: 2, offset: 1, projectKey: "OPS_DEMO" });
  await client.postPmSessionMessage("pm session", { message: "hello" });

  const pmListUrl = new URL(calls[0].url);
  assert.equal(pmListUrl.origin, "http://127.0.0.1:10000");
  assert.equal(pmListUrl.pathname, "/api/pm/sessions");
  assert.deepEqual(pmListUrl.searchParams.getAll("status"), ["blocked", "running"]);
  assert.deepEqual(pmListUrl.searchParams.getAll("status[]"), ["blocked", "running"]);
  assert.equal(pmListUrl.searchParams.get("project_key"), "OPS_DEMO");
  assert.equal(pmListUrl.searchParams.get("limit"), "2");
  assert.equal(pmListUrl.searchParams.get("offset"), "1");
  assert.equal(calls[1].url, "http://127.0.0.1:10000/api/pm/sessions/pm%20session/messages");
  assert.equal(calls[1].init.method, "POST");
});

test("desktop client fetchDesktopSessions uses PM session list defaults", async () => {
  const calls = [];
  const client = createDesktopApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ sessions: [] });
    },
  });

  const payload = await client.fetchDesktopSessions();
  assert.deepEqual(payload, { sessions: [] });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:10000/api/pm/sessions?sort=updated_desc&limit=10");
});

test("dashboard client uses contract workflow and queue paths", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchWorkflows();
  await client.fetchWorkflow("wf/1");
  await client.fetchQueue("wf/1", "running");
  await client.previewEnqueueRunQueue("run/1", { priority: 3 });
  await client.cancelQueueItem("queue/1", { reason: "operator aborted pilot" });

  const workflowPath = FRONTEND_API_CONTRACT.paths.workflows;
  const queuePath = FRONTEND_API_CONTRACT.paths.queue;
  assert.equal(calls[0].url, `http://127.0.0.1:10000${workflowPath}`);
  assert.equal(
    calls[1].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.workflowDetail.replace("{workflow_id}", "wf%2F1")}`,
  );
  const queueUrl = new URL(calls[2].url);
  assert.equal(queueUrl.origin, "http://127.0.0.1:10000");
  assert.equal(queueUrl.pathname, queuePath);
  assert.equal(queueUrl.searchParams.get("workflow_id"), "wf/1");
  assert.equal(queueUrl.searchParams.get("status"), "running");
  assert.equal(
    calls[3].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.queueEnqueuePreview.replace("{run_id}", "run%2F1")}`,
  );
  assert.equal(
    calls[4].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.queueCancel.replace("{queue_id}", "queue%2F1")}`,
  );
});

test("dashboard client uses contract-backed agents and contracts paths", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchAgents();
  await client.fetchAgentStatus();
  await client.fetchAgentStatus("run/1");
  await client.fetchContracts();

  assert.equal(calls[0].url, `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.agents}`);
  assert.equal(calls[1].url, `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.agentStatus}`);
  assert.equal(calls[2].url, `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.agentStatus}?run_id=run%2F1`);
  assert.equal(calls[3].url, `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.contracts}`);
});

test("dashboard client uses contract-backed role-config paths", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    resolveMutationRole: () => "tech_lead",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchRoleConfig("worker");
  await client.previewRoleConfig("worker", { system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md" });
  await client.applyRoleConfig("worker", { system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md" });

  assert.equal(
    calls[0].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.roleConfig.replace("{role}", "worker")}`,
  );
  assert.equal(
    calls[1].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.roleConfigPreview.replace("{role}", "worker")}`,
  );
  assert.equal(
    calls[2].url,
    `http://127.0.0.1:10000${FRONTEND_API_CONTRACT.paths.roleConfigApply.replace("{role}", "worker")}`,
  );
  assert.equal(calls[1].init.headers["x-openvibecoding-role"], "TECH_LEAD");
  assert.equal(calls[2].init.headers["x-openvibecoding-role"], "TECH_LEAD");
});

test("dashboard client attaches operator role only for mutation requests", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    resolveMutationRole: () => "tech_lead",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true });
    },
  });

  await client.fetchRuns();
  await client.rollbackRun("run-1");

  assert.equal(calls.length, 2);
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers["x-openvibecoding-role"], undefined);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers["x-openvibecoding-role"], "TECH_LEAD");
  assert.equal(calls[1].init.headers["x-openvibecoding-run-id"], "run-1");
  assert.equal(client.canExecuteMutations(), true);
  assert.equal(client.getMutationRole(), "TECH_LEAD");
});
