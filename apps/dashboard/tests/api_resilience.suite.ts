import { afterEach, describe, expect, it, vi } from "vitest";

import {
  answerIntake,
  approveGodMode,
  createIntake,
  fetchPmSession,
  fetchRuns,
  openEventsStream,
  postPmSessionMessage,
  promoteEvidence,
  rejectRun,
  replayRun,
  rollbackRun,
  runIntake,
} from "../lib/api";
import { extractCall, jsonResponse } from "./api_test_helpers";

describe("dashboard api resilience", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws clear errors for POST wrappers on non-ok responses", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ failed: true }, 503));
    vi.stubGlobal("fetch", fetchMock);
    const cases: Array<{ name: string; invoke: () => Promise<unknown>; msg: string }> = [
      { name: "promoteEvidence", invoke: () => promoteEvidence("run-1"), msg: "Promote failed: 503" },
      { name: "rollbackRun", invoke: () => rollbackRun("run-1"), msg: "Rollback failed: 503" },
      { name: "rejectRun", invoke: () => rejectRun("run-1"), msg: "Reject failed: 503" },
      { name: "createIntake", invoke: () => createIntake({ topic: "x" }), msg: "Intake create failed: 503" },
      { name: "answerIntake", invoke: () => answerIntake("intake-1", { answer: "x" }), msg: "Intake answer failed: 503" },
      { name: "runIntake", invoke: () => runIntake("intake-1", { dry_run: true }), msg: "Intake run failed: 503" },
      { name: "postPmSessionMessage", invoke: () => postPmSessionMessage("pm-1", { message: "hi" }), msg: "PM session message failed: 503" },
      { name: "approveGodMode", invoke: () => approveGodMode("run-1"), msg: "Approve failed: 503" },
      { name: "replayRun", invoke: () => replayRun("run-1"), msg: "Replay failed: 503" },
    ];
    for (const testCase of cases) {
      await expect(testCase.invoke(), testCase.name).rejects.toThrow(testCase.msg);
    }
  });

  it("surfaces backend detail.reason in POST wrapper errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ detail: { code: "INTAKE_CREATE_FAILED", reason: "custom browser policy requires privileged requester role" } }, 400),
      ),
    );
    await expect(createIntake({ topic: "x" })).rejects.toThrow(
      "Intake create failed: 400 (custom browser policy requires privileged requester role)",
    );
  });

  it("throws clear error when GET status is 500", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        headers: { get: () => "application/json" },
        json: async () => ({ message: "boom" }),
      })),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs failed: 500");
  });

  it("throws clear error when GET request times out", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("timeout");
      }),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs request failed: timeout");
  });

  it("aborts long-running requests on timeout option", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_: RequestInfo, init?: RequestInit) => {
        return new Promise((_, reject) => {
          const signal = init?.signal as AbortSignal | undefined;
          signal?.addEventListener("abort", () => {
            const abortError = new Error("aborted");
            (abortError as Error & { name: string }).name = "AbortError";
            reject(abortError);
          });
        });
      }),
    );
    await expect(fetchPmSession("session-timeout", { timeoutMs: 1 })).rejects.toThrow(
      "API /api/pm/sessions/session-timeout request failed: timeout",
    );
  });

  it("supports external abort signal for cancellable GET wrappers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_: RequestInfo, init?: RequestInit) => {
        return new Promise((_, reject) => {
          const signal = init?.signal as AbortSignal | undefined;
          signal?.addEventListener("abort", () => {
            const abortError = new Error("aborted");
            (abortError as Error & { name: string }).name = "AbortError";
            reject(abortError);
          });
        });
      }),
    );
    const controller = new AbortController();
    const request = fetchPmSession("session-abort", { signal: controller.signal, timeoutMs: 5000 });
    controller.abort();
    await expect(request).rejects.toThrow("API /api/pm/sessions/session-abort request failed: aborted");
  });

  it("throws clear error when GET body is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => "text/plain" },
        text: async () => "",
      })),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs returned empty response");
  });

  it("throws clear error when GET body is non-json", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => "text/plain" },
        text: async () => "not-json",
      })),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs returned non-JSON response");
  });

  it("covers pre-aborted signal, timeout=0 and missing text() branch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_: RequestInfo, init?: RequestInit) => {
        const signal = init?.signal as AbortSignal | undefined;
        if (signal?.aborted) {
          const abortError = new Error("already aborted");
          (abortError as Error & { name: string }).name = "AbortError";
          throw abortError;
        }
        return {
          ok: true,
          status: 200,
          headers: { get: () => "application/json" },
          json: async () => ({ ok: true }),
        };
      }),
    );

    const aborted = new AbortController();
    aborted.abort();
    await expect(fetchPmSession("session-pre-abort", { signal: aborted.signal })).rejects.toThrow(
      "API /api/pm/sessions/session-pre-abort request failed: aborted",
    );
    await expect(fetchPmSession("session-no-timeout", { timeoutMs: 0 })).resolves.toEqual({ ok: true });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: { get: () => "text/plain" },
        json: undefined,
      })),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs returned empty response");
  });

  it("covers non-Error network failure branch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw "string-failure";
      }),
    );
    await expect(fetchRuns()).rejects.toThrow("API /api/runs request failed: string-failure");
  });

  it("keeps browser read-only GET headers simple and stream query without access_token", async () => {
    vi.resetModules();
    const api = await import("../lib/api");
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    class MockEventSourceWithToken {
      url: string;
      constructor(url: string) {
        this.url = url;
      }
      close() {
        return undefined;
      }
    }
    global.EventSource = MockEventSourceWithToken as unknown as typeof EventSource;

    await api.fetchRuns();
    const { init } = extractCall(fetchMock.mock.calls as unknown[][], 0);
    expect(init.headers).toEqual({});
    expect(init.credentials).toBe("include");

    const stream = api.openEventsStream("run-token", { limit: 0, tail: true }) as unknown as { url: string };
    expect(stream.url).toContain("/api/runs/run-token/events/stream?tail=1");
    expect(stream.url).not.toContain("access_token=");
    expect(stream.url).not.toContain("limit=");
  });

  it("keeps openEventsStream import reachable for suite boundaries", () => {
    expect(typeof openEventsStream).toBe("function");
  });
});
