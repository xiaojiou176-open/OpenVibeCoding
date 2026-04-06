import test from "node:test";
import assert from "node:assert/strict";
import { createAuthCore } from "../src/core/auth.js";
import { createHttpCore } from "../src/core/http.js";

test("http core injects auth + contract headers and parses json", async () => {
  let received;
  const fetchImpl = async (url, init) => {
    received = { url, init };
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return { ok: true };
      },
    };
  };

  const auth = createAuthCore({ resolveToken: () => "token-1" });
  const http = createHttpCore({ baseUrl: "http://localhost:10000", auth, fetchImpl, defaultTimeoutMs: 2000 });

  const data = await http.getJson("/api/runs");
  assert.deepEqual(data, { ok: true });
  assert.equal(received.url, "http://localhost:10000/api/runs");
  assert.equal(received.init.credentials, "include");
  assert.equal(received.init.headers.Authorization, "Bearer token-1");
  assert.ok(received.init.headers["x-request-id"]);
  assert.ok(received.init.headers["x-trace-id"]);
  assert.ok(received.init.headers.traceparent);
});

test("http core keeps browser read-only GET headers simple when token is absent", async () => {
  let received;
  const fetchImpl = async (url, init) => {
    received = { url, init };
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return { ok: true };
      },
    };
  };

  const auth = createAuthCore();
  const http = createHttpCore({ baseUrl: "http://localhost:10000", auth, fetchImpl, defaultTimeoutMs: 2000 });

  const data = await http.getJson("/api/diff-gate");
  assert.deepEqual(data, { ok: true });
  assert.equal(received.url, "http://localhost:10000/api/diff-gate");
  assert.deepEqual(received.init.headers, {});
});

test("http core returns timeout error on abort", async () => {
  const fetchImpl = async (_url, init) => {
    await new Promise((resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
      setTimeout(resolve, 30);
    });
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return { ok: true };
      },
    };
  };

  const auth = createAuthCore();
  const http = createHttpCore({ baseUrl: "http://localhost", auth, fetchImpl, defaultTimeoutMs: 1 });

  await assert.rejects(() => http.getJson("/api/slow"), /timeout/);
});

test("http core injects operator role only for mutation methods", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return { ok: true };
      },
    };
  };

  const auth = createAuthCore();
  const http = createHttpCore({
    baseUrl: "http://localhost",
    auth,
    fetchImpl,
    resolveMutationRole: () => "ops",
  });

  await http.getJson("/api/runs");
  await http.postJson("/api/runs/run-1/reject", {}, "Reject failed");

  assert.equal(calls.length, 2);
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers["x-cortexpilot-role"], undefined);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers["x-cortexpilot-role"], "OPS");
  assert.equal(http.canExecuteMutations(), true);
  assert.equal(http.getMutationRole(), "OPS");
});

test("http core injects run correlation header when provided", async () => {
  let received;
  const fetchImpl = async (url, init) => {
    received = { url, init };
    return {
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      async json() {
        return { ok: true };
      },
    };
  };
  const auth = createAuthCore();
  const http = createHttpCore({ baseUrl: "http://localhost", auth, fetchImpl });
  await http.getJson("/api/runs/run-1", { runId: "run-1" });
  assert.equal(received.init.headers["x-cortexpilot-run-id"], "run-1");
});
