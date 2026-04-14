import test from "node:test";
import assert from "node:assert/strict";

import { runControlPlaneStarterExample } from "../examples/control_plane_starter.local.mjs";

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

test("local starter example bootstraps the control-plane starter and optional preview", async () => {
  const calls = [];
  const result = await runControlPlaneStarterExample({
    baseUrl: "http://127.0.0.1:10000",
    role: "WORKER",
    previewPayload: {
      runtime_binding: {
        provider: "cliproxyapi",
        model: "gpt-5.4",
      },
    },
    mutationRole: "TECH_LEAD",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/api/command-tower/overview")) {
        return createJsonResponse({ overview: true });
      }
      if (url.endsWith("/api/agents")) {
        return createJsonResponse({ role_catalog: [{ role: "WORKER" }] });
      }
      if (url.endsWith("/api/contracts")) {
        return createJsonResponse([{ contract_id: "worker-v1" }]);
      }
      if (url.endsWith("/api/agents/roles/WORKER/config")) {
        return createJsonResponse({ authority: "repo-owned-role-config" });
      }
      if (url.endsWith("/api/agents/roles/WORKER/config/preview")) {
        return createJsonResponse({
          role: "WORKER",
          can_apply: true,
          preview_surface: { runtime_capability: { lane: "standard-provider-path" } },
        });
      }
      throw new Error(`Unexpected URL: ${url}`);
    },
  });

  assert.equal(result.role, "WORKER");
  assert.equal(result.boundary.execution_authority, "task_contract");
  assert.equal(result.applied, null);
  assert.deepEqual(result.bootstrap.contracts, [{ contract_id: "worker-v1" }]);
  assert.equal(result.preview.role, "WORKER");
  assert.deepEqual(
    calls.map((call) => call.url),
    [
      "http://127.0.0.1:10000/api/command-tower/overview",
      "http://127.0.0.1:10000/api/agents",
      "http://127.0.0.1:10000/api/contracts",
      "http://127.0.0.1:10000/api/agents/roles/WORKER/config",
      "http://127.0.0.1:10000/api/agents/roles/WORKER/config/preview",
    ],
  );
  assert.equal(calls.at(-1)?.init.headers["x-openvibecoding-role"], "TECH_LEAD");
});

test("local starter example only applies when explicitly enabled", async () => {
  const calls = [];
  const result = await runControlPlaneStarterExample({
    baseUrl: "http://127.0.0.1:10000",
    role: "WORKER",
    previewPayload: {
      runtime_binding: {
        provider: "cliproxyapi",
        model: "gpt-5.4",
      },
    },
    apply: true,
    mutationRole: "TECH_LEAD",
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (url.endsWith("/api/command-tower/overview")) {
        return createJsonResponse({ overview: true });
      }
      if (url.endsWith("/api/agents")) {
        return createJsonResponse({ role_catalog: [{ role: "WORKER" }] });
      }
      if (url.endsWith("/api/contracts")) {
        return createJsonResponse([{ contract_id: "worker-v1" }]);
      }
      if (url.endsWith("/api/agents/roles/WORKER/config")) {
        return createJsonResponse({ authority: "repo-owned-role-config" });
      }
      if (url.endsWith("/api/agents/roles/WORKER/config/preview")) {
        return createJsonResponse({ role: "WORKER", can_apply: true });
      }
      if (url.endsWith("/api/agents/roles/WORKER/config/apply")) {
        return createJsonResponse({ saved: true });
      }
      throw new Error(`Unexpected URL: ${url}`);
    },
  });

  assert.deepEqual(result.applied, { saved: true });
  assert.equal(calls.at(-1)?.url, "http://127.0.0.1:10000/api/agents/roles/WORKER/config/apply");
  assert.equal(calls.at(-1)?.init.headers["x-openvibecoding-role"], "TECH_LEAD");
});
