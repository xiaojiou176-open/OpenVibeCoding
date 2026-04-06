import test from "node:test";
import assert from "node:assert/strict";
import { createAuthCore } from "../src/core/auth.js";
import { createSseCore } from "../src/core/sse.js";

test("sse core uses EventSource with contract credentials when token is absent", () => {
  const calls = [];
  class FakeEventSource {
    constructor(url, options) {
      this.url = url;
      this.options = options;
      this.close = () => {};
      calls.push({ url, options });
    }
  }

  const sse = createSseCore({
    baseUrl: "http://127.0.0.1:10000",
    auth: createAuthCore(),
    eventSourceCtor: FakeEventSource,
  });

  sse.open("/api/runs/r1/events/stream", { since: "abc" }, { resolveToken: () => undefined });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://127.0.0.1:10000/api/runs/r1/events/stream?since=abc");
  assert.deepEqual(calls[0].options, { withCredentials: true });
});

test("sse core falls back to fetch stream when token is present", async () => {
  const encoder = new TextEncoder();
  let authHeader;
  const fetchImpl = async (_url, init) => {
    authHeader = init.headers.Authorization;
    return {
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode("data: {\"ok\":true}\n\n"));
          controller.close();
        },
      }),
    };
  };

  const auth = createAuthCore({ resolveToken: () => "token-xyz" });
  const sse = createSseCore({
    baseUrl: "http://127.0.0.1:10000",
    auth,
    fetchImpl,
    eventSourceCtor: null,
  });

  const stream = sse.open("/api/runs/r2/events/stream", {}, { resolveToken: () => "token-xyz" });

  const payload = await new Promise((resolve, reject) => {
    stream.onerror = () => reject(new Error("unexpected error"));
    stream.onmessage = (event) => resolve(event.data);
  });

  assert.equal(payload, '{"ok":true}');
  assert.equal(authHeader, "Bearer token-xyz");
  stream.close();
});

test("sse fetch fallback does not emit error on normal EOF", async () => {
  const encoder = new TextEncoder();
  const fetchImpl = async () => ({
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode("data: done\n\n"));
        controller.close();
      },
    }),
  });

  const auth = createAuthCore({ resolveToken: () => "token-xyz" });
  const sse = createSseCore({
    baseUrl: "http://127.0.0.1:10000",
    auth,
    fetchImpl,
    eventSourceCtor: null,
  });

  const stream = sse.open("/api/runs/r3/events/stream", {}, { resolveToken: () => "token-xyz" });
  let errorCount = 0;
  stream.onerror = () => {
    errorCount += 1;
  };

  const payload = await new Promise((resolve) => {
    stream.onmessage = (event) => resolve(event.data);
  });

  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(payload, "done");
  assert.equal(errorCount, 0);
});
