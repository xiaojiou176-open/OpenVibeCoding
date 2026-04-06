import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  answerIntake,
  approveGodMode,
  createIntake,
  fetchTaskPacks,
  fetchAgentStatus,
  fetchAgents,
  fetchAllEvents,
  fetchArtifact,
  fetchChainSpec,
  fetchCommandTowerAlerts,
  fetchCommandTowerOverview,
  fetchContracts,
  fetchDesktopAlerts,
  fetchDesktopOverview,
  fetchDiff,
  fetchDiffGate,
  fetchEvents,
  fetchLocks,
  fetchPendingApprovals,
  fetchPmSessionEvents,
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionMetrics,
  fetchPmSessions,
  fetchPolicies,
  fetchQueue,
  fetchReports,
  fetchRun,
  fetchRuns,
  fetchRunSearch,
  fetchDesktopSessions,
  fetchReviews,
  fetchTests,
  fetchToolCalls,
  fetchWorkflow,
  fetchWorkflows,
  fetchWorktrees,
  enqueueRunQueue,
  openEventsStream,
  postPmSessionMessage,
  promoteEvidence,
  rejectRun,
  replayRun,
  rollbackRun,
  runNextQueue,
  runIntake,
  postDesktopPmMessage
} from "./api";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

describe("desktop api client", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST") {
          return jsonResponse({ pm_session_id: "pm-1", message: "ok" });
        }
        if (raw.includes("/api/command-tower/overview")) {
          return jsonResponse({ active_sessions: 3 });
        }
        if (raw.includes("/api/pm/sessions")) {
          return jsonResponse([{ pm_session_id: "pm-1" }]);
        }
        if (raw.includes("/api/command-tower/alerts")) {
          return jsonResponse({ alerts: [{ code: "A" }] });
        }
        return jsonResponse({}, 404);
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("fetches overview payload", async () => {
    await expect(fetchDesktopOverview()).resolves.toMatchObject({ active_sessions: 3 });
  });

  it("fetches session payload", async () => {
    await expect(fetchDesktopSessions()).resolves.toHaveLength(1);
  });

  it("fetches alerts payload", async () => {
    await expect(fetchDesktopAlerts()).resolves.toMatchObject({ alerts: [{ code: "A" }] });
  });

  it("fetches task packs payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (raw.includes("/api/pm/task-packs")) {
          return jsonResponse([{ pack_id: "news_digest", task_template: "news_digest" }]);
        }
        return jsonResponse({}, 404);
      }),
    );
    await expect(fetchTaskPacks()).resolves.toHaveLength(1);
  });

  it("throws on non-200 response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({}, 500)));
    await expect(fetchDesktopOverview()).rejects.toThrow("failed: 500");
  });

  it("posts pm session message", async () => {
    await expect(postDesktopPmMessage("pm-1", { message: "hello", strict_acceptance: true })).resolves.toMatchObject({
      pm_session_id: "pm-1",
      message: "ok"
    });
    const fetchCalls = vi.mocked(fetch).mock.calls;
    const messageCall = fetchCalls.find(([input, init]) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return raw.includes("/api/pm/sessions/") && raw.includes("/messages") && init?.method === "POST";
    });
    expect(messageCall?.[1]).toMatchObject({ method: "POST" });
    const payload = JSON.parse(String(messageCall?.[1]?.body || "{}")) as Record<string, unknown>;
    expect(payload.message).toBe("hello");
    expect(payload.content).toBeUndefined();
  });

  it("opens event stream without access_token query", () => {
    class MockEventSource {
      url: string;
      constructor(url: string) {
        this.url = url;
      }
      close() {
        return undefined;
      }
    }
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
    const stream = openEventsStream("run-1", { tail: true }) as unknown as { url: string };
    expect(stream.url).toContain("/api/runs/run-1/events/stream?tail=1");
    expect(stream.url).not.toContain("access_token=");
  });

  it("encodes runId in run detail and events endpoints", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ ok: true })),
    );
    await fetchRun("run/1");
    await fetchEvents("run/1", { tail: true });
    const urls = vi.mocked(fetch).mock.calls.map(([input]) =>
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
    );
    expect(urls.some((url) => url.includes("/api/runs/run%2F1"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/runs/run%2F1/events?tail=1"))).toBe(true);
  });

  it("serializes status filter with scalar and array aliases", async () => {
    await expect(fetchPmSessions({ status: ["active", "failed"] })).resolves.toHaveLength(1);
    const fetchCalls = vi.mocked(fetch).mock.calls;
    const sessionCall = fetchCalls.find(([input]) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return raw.includes("/api/pm/sessions?");
    });
    const sessionUrl = new URL(String(sessionCall?.[0] ?? "http://127.0.0.1"));
    expect(sessionUrl.searchParams.getAll("status")).toEqual(["active", "failed"]);
    expect(sessionUrl.searchParams.getAll("status[]")).toEqual(["active", "failed"]);
  });

  it("serializes event types filter with scalar and array aliases", async () => {
    await expect(fetchPmSessionEvents("pm-1", { types: ["CHAIN_HANDOFF"] })).resolves.toHaveLength(1);
    const fetchCalls = vi.mocked(fetch).mock.calls;
    const eventCall = fetchCalls.find(([input]) => {
      const raw = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return raw.includes("/api/pm/sessions/pm-1/events");
    });
    const eventUrl = new URL(String(eventCall?.[0] ?? "http://127.0.0.1"));
    expect(eventUrl.searchParams.getAll("types")).toEqual(["CHAIN_HANDOFF"]);
    expect(eventUrl.searchParams.getAll("types[]")).toEqual(["CHAIN_HANDOFF"]);
  });

  it("parses rollback error reason from api detail payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: { code: "ROLLBACK_FAILED", reason: "worktree_ref missing" } }, 422)),
    );
    await expect(rollbackRun("run-1")).rejects.toThrow("Rollback failed: 422 (worktree_ref missing)");
  });

  it("uses bearer header for SSE stream when desktop api token is present", async () => {
    const previousToken = process.env.VITE_CORTEXPILOT_API_TOKEN;
    process.env.VITE_CORTEXPILOT_API_TOKEN = "desktop-token";
    vi.resetModules();

    const fetchSpy = vi.fn(async () => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("data: {\"event\":\"PING\"}\n\n"));
          controller.close();
        },
      });
      return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchSpy);

    const api = await import("./api");
    const stream = api.openEventsStream("run-1", { tail: true });
    stream.close();

    const fetchCalls = fetchSpy.mock.calls as unknown as Array<[unknown, RequestInit | undefined]>;
    expect(fetchCalls.length).toBeGreaterThanOrEqual(1);
    const firstCall = fetchCalls[0] as [unknown, RequestInit | undefined];
    const init = firstCall[1];
    expect(init?.headers).toMatchObject({ Authorization: "Bearer desktop-token" });
    expect(String(firstCall[0] || "")).toContain("/api/runs/run-1/events/stream?tail=1");

    if (previousToken === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    else process.env.VITE_CORTEXPILOT_API_TOKEN = previousToken;
  });

  it("uses refreshed bearer token after env rotation within same module instance", async () => {
    const previousToken = process.env.VITE_CORTEXPILOT_API_TOKEN;
    process.env.VITE_CORTEXPILOT_API_TOKEN = "desktop-token-old";
    vi.resetModules();

    const fetchSpy = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchSpy);
    const api = await import("./api");

    await api.fetchDesktopOverview();

    process.env.VITE_CORTEXPILOT_API_TOKEN = "desktop-token-new";
    await api.fetchDesktopSessions();

    const fetchCalls = fetchSpy.mock.calls as unknown as Array<[unknown, RequestInit | undefined]>;
    const authHeaders = fetchCalls.map(([, init]) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      return headers.Authorization;
    });
    expect(authHeaders).toEqual(["Bearer desktop-token-old", "Bearer desktop-token-new"]);

    if (previousToken === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    else process.env.VITE_CORTEXPILOT_API_TOKEN = previousToken;
  });

  it("treats remote stream EOF as normal completion without fallback error", async () => {
    const previousToken = process.env.VITE_CORTEXPILOT_API_TOKEN;
    process.env.VITE_CORTEXPILOT_API_TOKEN = "desktop-token";
    vi.resetModules();

    const fetchSpy = vi.fn(async () => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.close();
        },
      });
      return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchSpy);

    const api = await import("./api");
    const stream = api.openEventsStream("run-1", { tail: true });
    const onError = vi.fn();
    stream.onerror = onError;

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(onError).not.toHaveBeenCalled();
    stream.close();

    if (previousToken === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    else process.env.VITE_CORTEXPILOT_API_TOKEN = previousToken;
  });

  it("serializes scalar session filters and optional paging fields", async () => {
    await fetchPmSessions({
      status: "active",
      ownerPm: "owner-1",
      projectKey: "project-A",
      sort: "updated_desc",
      limit: 20,
      offset: 0,
    });
    const firstCall = vi.mocked(fetch).mock.calls[0];
    const raw = typeof firstCall[0] === "string" ? firstCall[0] : firstCall[0] instanceof URL ? firstCall[0].toString() : firstCall[0].url;
    const url = new URL(raw);
    expect(url.searchParams.getAll("status")).toEqual(["active"]);
    expect(url.searchParams.getAll("status[]")).toEqual(["active"]);
    expect(url.searchParams.get("owner_pm")).toBe("owner-1");
    expect(url.searchParams.get("project_key")).toBe("project-A");
    expect(url.searchParams.get("sort")).toBe("updated_desc");
    expect(url.searchParams.get("limit")).toBe("20");
    expect(url.searchParams.get("offset")).toBe("0");
  });

  it("serializes run_ids aliases for session events", async () => {
    await fetchPmSessionEvents("pm-1", { runIds: ["run-1", " run-2 "] });
    const firstCall = vi.mocked(fetch).mock.calls[0];
    const raw = typeof firstCall[0] === "string" ? firstCall[0] : firstCall[0] instanceof URL ? firstCall[0].toString() : firstCall[0].url;
    const url = new URL(raw);
    expect(url.searchParams.getAll("run_ids")).toEqual(["run-1", "run-2"]);
    expect(url.searchParams.getAll("run_ids[]")).toEqual(["run-1", "run-2"]);
  });

  it("appends run_id only when fetchAgentStatus is called with value", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
    await fetchAgentStatus();
    await fetchAgentStatus("run-1");
    const urls = vi.mocked(fetch).mock.calls.map(([input]) =>
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
    );
    expect(urls[0]).toContain("/api/agents/status");
    expect(urls[0]).not.toContain("run_id=");
    expect(urls[1]).toContain("/api/agents/status?run_id=run-1");
  });

  it("uses contract-backed role-config paths and desktop operator role for mutations", async () => {
    const previousRole = process.env.VITE_CORTEXPILOT_OPERATOR_ROLE;
    process.env.VITE_CORTEXPILOT_OPERATOR_ROLE = "ops";
    vi.resetModules();

    const fetchSpy = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchSpy);

    const api = await import("./api");
    await api.fetchRoleConfig("worker");
    await api.previewRoleConfig("worker", { system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md" } as any);
    await api.applyRoleConfig("worker", { system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md" } as any);

    const calls = fetchSpy.mock.calls as unknown as Array<[unknown, RequestInit | undefined]>;
    const urls = calls.map(([input]) => {
      if (typeof input === "string") {
        return input;
      }
      if (input instanceof URL) {
        return input.toString();
      }
      return typeof input === "object" && input !== null && "url" in input
        ? String((input as { url?: unknown }).url || "")
        : String(input);
    });
    expect(urls[0]).toContain("/api/agents/roles/worker/config");
    expect(urls[1]).toContain("/api/agents/roles/worker/config/preview");
    expect(urls[2]).toContain("/api/agents/roles/worker/config/apply");
    expect((calls[1][1]?.headers as Record<string, string>)["x-cortexpilot-role"]).toBe("OPS");
    expect((calls[2][1]?.headers as Record<string, string>)["x-cortexpilot-role"]).toBe("OPS");
    expect(api.mutationExecutionCapability()).toEqual({ executable: true, operatorRole: "OPS" });

    if (previousRole === undefined) delete process.env.VITE_CORTEXPILOT_OPERATOR_ROLE;
    else process.env.VITE_CORTEXPILOT_OPERATOR_ROLE = previousRole;
  });

  it("includes trimmed baseline_run_id in replay payload when provided", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
    await replayRun("run-1", " baseline-1 ");
    const firstCall = vi.mocked(fetch).mock.calls[0] as [unknown, RequestInit | undefined];
    const payload = JSON.parse(String(firstCall[1]?.body || "{}")) as Record<string, unknown>;
    expect(payload).toMatchObject({ baseline_run_id: "baseline-1" });
  });

  it("omits baseline_run_id in replay payload when empty", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
    await replayRun("run-1", "   ");
    const firstCall = vi.mocked(fetch).mock.calls[0] as [unknown, RequestInit | undefined];
    const payload = JSON.parse(String(firstCall[1]?.body || "{}")) as Record<string, unknown>;
    expect(payload.baseline_run_id).toBeUndefined();
  });

  it("surfaces text response reason when non-json api error occurs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("plain failure", { status: 400, headers: { "Content-Type": "text/plain" } })),
    );
    await expect(fetchDesktopOverview()).rejects.toThrow("API /api/command-tower/overview failed: 400 (plain failure)");
  });

  it("throws endpoint specific errors for failed promote/reject/approve operations", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({}, 503)));
    await expect(promoteEvidence("run-1")).rejects.toThrow("Promote failed: 503");
    await expect(rejectRun("run-1")).rejects.toThrow("Reject failed: 503");
    await expect(approveGodMode("run-1")).rejects.toThrow("Approve failed: 503");
  });

  it("uses EventSource branch when token is absent and keeps query params", () => {
    const previousToken = process.env.VITE_CORTEXPILOT_API_TOKEN;
    delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    vi.resetModules();
    class MockEventSource {
      url: string;
      constructor(url: string) {
        this.url = url;
      }
      close() {
        return undefined;
      }
    }
    globalThis.EventSource = MockEventSource as unknown as typeof EventSource;
    const stream = openEventsStream("run-1", { since: "abc", limit: 20 }) as unknown as { url: string };
    expect(stream.url).toContain("/api/runs/run-1/events/stream?since=abc&limit=20");
    if (previousToken === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    else process.env.VITE_CORTEXPILOT_API_TOKEN = previousToken;
  });

  it("consumes SSE data payloads in fetch-based stream mode", async () => {
    const previousToken = process.env.VITE_CORTEXPILOT_API_TOKEN;
    process.env.VITE_CORTEXPILOT_API_TOKEN = "desktop-token";
    vi.resetModules();
    const fetchSpy = vi.fn(async () => {
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode("data: line1\n"));
          controller.enqueue(new TextEncoder().encode("data: line2\n\n"));
          controller.close();
        },
      });
      return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const api = await import("./api");
    const stream = api.openEventsStream("run-1", { tail: true });
    const onOpen = vi.fn();
    const onMessage = vi.fn();
    stream.onopen = onOpen;
    stream.onmessage = onMessage;
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onMessage).toHaveBeenCalledTimes(1);
    expect(String(onMessage.mock.calls[0][0].data)).toBe("line1\nline2");
    stream.close();
    if (previousToken === undefined) delete process.env.VITE_CORTEXPILOT_API_TOKEN;
    else process.env.VITE_CORTEXPILOT_API_TOKEN = previousToken;
  });

  it("maps json detail.message for intake errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: { message: "schema invalid" } }, 422)),
    );
    await expect(createIntake({ title: "demo" })).rejects.toThrow("Intake create failed: 422 (schema invalid)");
  });

  it("maps json code when reason/message are absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ code: "RATE_LIMITED" }, 429)),
    );
    await expect(answerIntake("intake-1", { answer: "ok" })).rejects.toThrow("Intake answer failed: 429 (RATE_LIMITED)");
  });

  it("maps network non-abort errors to unified api request message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("socket hang up");
      }),
    );
    await expect(fetchDesktopOverview()).rejects.toThrow("API /api/command-tower/overview request failed: socket hang up");
  });

  it("treats abort-like string errors as AbortError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw "AbortError: synthetic";
      }),
    );
    await expect(fetchDesktopOverview()).rejects.toMatchObject({ name: "AbortError" });
  });

  it("aborts immediately when parent signal is already aborted", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: string | URL | Request, init?: RequestInit) => {
        if (init?.signal?.aborted) {
          throw new DOMException("Aborted", "AbortError");
        }
        return jsonResponse({ ok: true });
      }),
    );
    const controller = new AbortController();
    controller.abort();
    await expect(fetchDesktopOverview(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    vi.useRealTimers();
  });

  it("filters invalid optional query params in events and pm session events", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
    await fetchEvents("run-1", { since: "", limit: 0, tail: false });
    await fetchPmSessionEvents("pm-1", {
      since: "",
      limit: -1,
      tail: false,
      types: ["", " TYPE_A ", "   "],
      runIds: ["", " run-2 "],
    });
    const urls = vi.mocked(fetch).mock.calls.map(([input]) =>
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
    );
    expect(urls[0]).toContain("/api/runs/run-1/events");
    expect(urls[0]).not.toContain("?");
    const eventUrl = new URL(urls[1]);
    expect(eventUrl.searchParams.getAll("types")).toEqual(["TYPE_A"]);
    expect(eventUrl.searchParams.getAll("types[]")).toEqual(["TYPE_A"]);
    expect(eventUrl.searchParams.getAll("run_ids")).toEqual(["run-2"]);
    expect(eventUrl.searchParams.getAll("run_ids[]")).toEqual(["run-2"]);
    expect(eventUrl.searchParams.get("since")).toBeNull();
    expect(eventUrl.searchParams.get("limit")).toBeNull();
    expect(eventUrl.searchParams.get("tail")).toBeNull();
  });

  it("covers default and explicit options for pm sessions and conversation graph", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
    await fetchPmSessions({ status: [], ownerPm: "  ", projectKey: " ", limit: 0, offset: -1 });
    await fetchPmSessionConversationGraph("pm/1");
    await fetchPmSessionConversationGraph("pm/1", "24h");
    const urls = vi.mocked(fetch).mock.calls.map(([input]) =>
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
    );
    expect(urls[0]).toContain("/api/pm/sessions");
    expect(urls[0]).not.toContain("?");
    expect(urls[1]).toContain("/api/pm/sessions/pm%2F1/conversation-graph?window=30m");
    expect(urls[2]).toContain("/api/pm/sessions/pm%2F1/conversation-graph?window=24h");
  });

  it("hits additional exported api endpoints for function coverage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ ok: true })));
    await fetchRuns();
    await fetchDiff("run/1");
    await fetchReports("run/1");
    await fetchArtifact("run/1", "artifact with space");
    await fetchRunSearch("run/1");
    await fetchToolCalls("run/1");
    await fetchChainSpec("run/1");
    await fetchContracts();
    await fetchAllEvents();
    await fetchDiffGate();
    await fetchReviews();
    await fetchTests();
    await fetchAgents();
    await fetchPolicies();
    await fetchLocks();
    await fetchWorktrees();
    await fetchQueue();
    await fetchWorkflows();
    await fetchWorkflow("wf/1");
    await enqueueRunQueue("run/1", { priority: 3 });
    await runNextQueue();
    await fetchPmSession("pm/1");
    await fetchPmSessionMetrics("pm/1");
    await fetchCommandTowerOverview();
    await fetchCommandTowerAlerts();
    await runIntake("intake/1", { run: true });
    await postPmSessionMessage("pm/1", { message: "hello" });
    await fetchPendingApprovals();
    const urls = vi.mocked(fetch).mock.calls.map(([input]) =>
      typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
    );
    expect(urls.some((url) => url.includes("/api/runs/run%2F1/diff"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/runs/run%2F1/artifacts?name=artifact%20with%20space"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/queue"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/queue/from-run/run%2F1"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/queue/run-next"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/workflows/wf%2F1"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/pm/sessions/pm%2F1"))).toBe(true);
    expect(urls.some((url) => url.includes("/api/pm/intake/intake%2F1/run"))).toBe(true);
  });
});
