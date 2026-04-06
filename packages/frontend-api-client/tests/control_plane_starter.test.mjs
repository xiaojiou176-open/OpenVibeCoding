import test from "node:test";
import assert from "node:assert/strict";

import { createDashboardApiClient, createControlPlaneStarter } from "../index.js";

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

test("control plane starter bootstraps overview, agents, contracts, and optional role config", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/api/command-tower/overview")) {
        return createJsonResponse({ overview: true });
      }
      if (url.endsWith("/api/agents")) {
        return createJsonResponse({ roles: [] });
      }
      if (url.endsWith("/api/contracts")) {
        return createJsonResponse([{ contract_id: "worker-v1" }]);
      }
      if (url.endsWith("/api/agents/roles/WORKER/config")) {
        return createJsonResponse({ authority: "repo-owned-role-config" });
      }
      throw new Error(`Unexpected URL: ${url}`);
    },
  });

  const starter = createControlPlaneStarter(client);
  const payload = await starter.fetchBootstrap({ role: "WORKER" });

  assert.deepEqual(payload, {
    overview: { overview: true },
    agents: { roles: [] },
    contracts: [{ contract_id: "worker-v1" }],
    roleConfig: { authority: "repo-owned-role-config" },
    role: "WORKER",
  });
  assert.deepEqual(
    calls.map((call) => call.url),
    [
      "http://127.0.0.1:10000/api/command-tower/overview",
      "http://127.0.0.1:10000/api/agents",
      "http://127.0.0.1:10000/api/contracts",
      "http://127.0.0.1:10000/api/agents/roles/WORKER/config",
    ],
  );
});

test("control plane starter fetchRoleWorkspace reuses the existing read surfaces", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/api/agents")) {
        return createJsonResponse({ roles: ["WORKER"] });
      }
      if (url.endsWith("/api/contracts")) {
        return createJsonResponse([{ contract_id: "worker-v1" }]);
      }
      if (url.endsWith("/api/agents/roles/WORKER/config")) {
        return createJsonResponse({ authority: "repo-owned-role-config" });
      }
      throw new Error(`Unexpected URL: ${url}`);
    },
  });

  const starter = createControlPlaneStarter(client);
  const payload = await starter.fetchRoleWorkspace("WORKER");

  assert.equal(payload.role, "WORKER");
  assert.deepEqual(payload.agents, { roles: ["WORKER"] });
  assert.deepEqual(payload.contracts, [{ contract_id: "worker-v1" }]);
  assert.deepEqual(payload.roleConfig, { authority: "repo-owned-role-config" });
});

test("control plane starter forwards preview/apply role config mutations", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    resolveMutationRole: () => "tech_lead",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true, url });
    },
  });

  const starter = createControlPlaneStarter(client);
  const preview = await starter.previewRoleDefaults("WORKER", {
    runtime_binding: { provider: "cliproxyapi", model: "gpt-5.4" },
  });
  const applied = await starter.applyRoleDefaults("WORKER", {
    runtime_binding: { provider: "cliproxyapi", model: "gpt-5.4" },
  });

  assert.equal(
    calls[0].url,
    "http://127.0.0.1:10000/api/agents/roles/WORKER/config/preview",
  );
  assert.equal(
    calls[1].url,
    "http://127.0.0.1:10000/api/agents/roles/WORKER/config/apply",
  );
  assert.equal(calls[0].init.headers["x-cortexpilot-role"], "TECH_LEAD");
  assert.equal(calls[1].init.headers["x-cortexpilot-role"], "TECH_LEAD");
  assert.deepEqual(preview, {
    ok: true,
    url: "http://127.0.0.1:10000/api/agents/roles/WORKER/config/preview",
  });
  assert.deepEqual(applied, {
    ok: true,
    url: "http://127.0.0.1:10000/api/agents/roles/WORKER/config/apply",
  });
});

test("control plane starter forwards guarded queue helpers", async () => {
  const calls = [];
  const client = createDashboardApiClient({
    baseUrl: "http://127.0.0.1:10000",
    resolveMutationRole: () => "tech_lead",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return createJsonResponse({ ok: true, url });
    },
  });

  const starter = createControlPlaneStarter(client);
  const preview = await starter.previewQueueEnqueue("run/1", { priority: 3 });
  const cancelled = await starter.cancelPendingQueueItem("queue/1", { reason: "operator aborted pilot" });

  assert.equal(
    calls[0].url,
    "http://127.0.0.1:10000/api/queue/from-run/run%2F1/preview",
  );
  assert.equal(
    calls[1].url,
    "http://127.0.0.1:10000/api/queue/queue%2F1/cancel",
  );
  assert.equal(calls[0].init.headers["x-cortexpilot-role"], "TECH_LEAD");
  assert.equal(calls[1].init.headers["x-cortexpilot-role"], "TECH_LEAD");
  assert.deepEqual(preview, {
    ok: true,
    url: "http://127.0.0.1:10000/api/queue/from-run/run%2F1/preview",
  });
  assert.deepEqual(cancelled, {
    ok: true,
    url: "http://127.0.0.1:10000/api/queue/queue%2F1/cancel",
  });
});

test("control plane starter rejects incomplete clients early", () => {
  assert.throws(
    () => createControlPlaneStarter({ fetchAgents() {} }),
    /requires client\.fetchCommandTowerOverview\(\)/,
  );
});
