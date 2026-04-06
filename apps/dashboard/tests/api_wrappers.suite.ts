import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { createElement } from "react";
import * as dashboardApi from "../lib/api";
import DiffGatePanel from "../components/DiffGatePanel";
import LocksPage from "../app/locks/page";
import CommandTowerSessionPage from "../app/command-tower/sessions/[id]/page";

import {
  answerIntake,
  approveGodMode,
  createIntake,
  previewIntake,
  fetchAgentStatus,
  fetchAgents,
  fetchAllEvents,
  fetchArtifact,
  fetchChainSpec,
  fetchCommandTowerAlerts,
  fetchCommandTowerOverview,
  fetchContracts,
  fetchDiff,
  fetchDiffGate,
  fetchEvents,
  fetchLocks,
  fetchPendingApprovals,
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
  fetchPmSessions,
  fetchPolicies,
  fetchReports,
  fetchReviews,
  fetchQueue,
  releaseLocks,
  fetchRun,
  fetchRuns,
  fetchRunSearch,
  fetchTests,
  fetchToolCalls,
  fetchWorkflow,
  fetchWorkflows,
  fetchWorktrees,
  openEventsStream,
  postPmSessionMessage,
  promoteEvidence,
  rejectRun,
  replayRun,
  rollbackRun,
  runNextQueue,
  runIntake,
} from "../lib/api";
import type { PmSessionStatus } from "../lib/types";
import { API_BASE, extractCall, jsonResponse } from "./api_test_helpers";

describe("dashboard api wrappers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("covers all GET wrappers with expected routes", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const getCases: Array<{
      name: string;
      path: string;
      invoke: () => Promise<unknown>;
    }> = [
      { name: "fetchRuns", path: "/api/runs", invoke: () => fetchRuns() },
      { name: "fetchRun", path: "/api/runs/run-1", invoke: () => fetchRun("run-1") },
      { name: "fetchEvents", path: "/api/runs/run-1/events", invoke: () => fetchEvents("run-1") },
      {
        name: "fetchEvents(with options)",
        path: "/api/runs/run-1/events?since=2026-02-09T08%3A00%3A00Z&limit=25&tail=1",
        invoke: () => fetchEvents("run-1", { since: "2026-02-09T08:00:00Z", limit: 25, tail: true }),
      },
      { name: "fetchDiff", path: "/api/runs/run-1/diff", invoke: () => fetchDiff("run-1") },
      { name: "fetchReports", path: "/api/runs/run-1/reports", invoke: () => fetchReports("run-1") },
      {
        name: "fetchArtifact",
        path: "/api/runs/run-1/artifacts?name=tool%20calls.jsonl",
        invoke: () => fetchArtifact("run-1", "tool calls.jsonl"),
      },
      { name: "fetchRunSearch", path: "/api/runs/run-1/search", invoke: () => fetchRunSearch("run-1") },
      { name: "fetchContracts", path: "/api/contracts", invoke: () => fetchContracts() },
      { name: "fetchAllEvents", path: "/api/events", invoke: () => fetchAllEvents() },
      { name: "fetchDiffGate", path: "/api/diff-gate", invoke: () => fetchDiffGate() },
      { name: "fetchReviews", path: "/api/reviews", invoke: () => fetchReviews() },
      { name: "fetchTests", path: "/api/tests", invoke: () => fetchTests() },
      { name: "fetchAgents", path: "/api/agents", invoke: () => fetchAgents() },
      { name: "fetchAgentStatus(empty)", path: "/api/agents/status", invoke: () => fetchAgentStatus() },
      {
        name: "fetchAgentStatus(runId)",
        path: "/api/agents/status?run_id=run+id",
        invoke: () => fetchAgentStatus("run id"),
      },
      { name: "fetchPolicies", path: "/api/policies", invoke: () => fetchPolicies() },
      { name: "fetchLocks", path: "/api/locks", invoke: () => fetchLocks() },
      { name: "fetchWorktrees", path: "/api/worktrees", invoke: () => fetchWorktrees() },
      { name: "fetchQueue", path: "/api/queue", invoke: () => fetchQueue() },
      { name: "fetchWorkflows", path: "/api/workflows", invoke: () => fetchWorkflows() },
      { name: "fetchWorkflow", path: "/api/workflows/wf%2F1", invoke: () => fetchWorkflow("wf/1") },
      { name: "fetchCommandTowerOverview", path: "/api/command-tower/overview", invoke: () => fetchCommandTowerOverview() },
      { name: "fetchCommandTowerAlerts", path: "/api/command-tower/alerts", invoke: () => fetchCommandTowerAlerts() },
      { name: "fetchTaskPacks", path: "/api/pm/task-packs", invoke: () => dashboardApi.fetchTaskPacks() },
      { name: "fetchPmSessions", path: "/api/pm/sessions", invoke: () => fetchPmSessions() },
      {
        name: "fetchPmSessions(options)",
        path: "/api/pm/sessions?status=active&status%5B%5D=active&owner_pm=pm-1&limit=5&offset=1",
        invoke: () => fetchPmSessions({ status: "active", ownerPm: "pm-1", limit: 5, offset: 1 }),
      },
      {
        name: "fetchPmSessions(status[] + project + sort)",
        path: "/api/pm/sessions?status%5B%5D=active&status=active&status%5B%5D=failed&status=failed&project_key=cortexpilot&sort=blocked_desc",
        invoke: () => fetchPmSessions({ status: ["active", "failed"], projectKey: "cortexpilot", sort: "blocked_desc" }),
      },
      { name: "fetchPmSession", path: "/api/pm/sessions/session%2F1", invoke: () => fetchPmSession("session/1") },
      {
        name: "fetchPmSessionEvents",
        path: "/api/pm/sessions/session%2F1/events?since=2026-02-09T08%3A00%3A00Z&limit=30&tail=1&types%5B%5D=CHAIN_HANDOFF&types=CHAIN_HANDOFF&types%5B%5D=MCP_CALL&types=MCP_CALL&run_ids%5B%5D=run-a&run_ids=run-a&run_ids%5B%5D=run-b&run_ids=run-b",
        invoke: () =>
          fetchPmSessionEvents("session/1", {
            since: "2026-02-09T08:00:00Z",
            limit: 30,
            tail: true,
            types: ["CHAIN_HANDOFF", "MCP_CALL"],
            runIds: ["run-a", "run-b"],
          }),
      },
      {
        name: "fetchPmSessionConversationGraph",
        path: "/api/pm/sessions/session%2F1/conversation-graph?window=24h",
        invoke: () => fetchPmSessionConversationGraph("session/1", "24h"),
      },
      {
        name: "fetchPmSessionConversationGraph(options)",
        path: "/api/pm/sessions/session%2F1/conversation-graph?window=24h&group_by_role=1",
        invoke: () => fetchPmSessionConversationGraph("session/1", { window: "24h", groupByRole: true }),
      },
      {
        name: "fetchPmSessionMetrics",
        path: "/api/pm/sessions/session%2F1/metrics",
        invoke: () => fetchPmSessionMetrics("session/1"),
      },
      {
        name: "fetchToolCalls",
        path: "/api/runs/run%2F1/artifacts?name=tool_calls.jsonl",
        invoke: () => fetchToolCalls("run/1"),
      },
      {
        name: "fetchChainSpec",
        path: "/api/runs/run%2F1/artifacts?name=chain.json",
        invoke: () => fetchChainSpec("run/1"),
      },
      {
        name: "fetchPendingApprovals",
        path: "/api/god-mode/pending",
        invoke: () => fetchPendingApprovals(),
      },
    ];

    const calls = fetchMock.mock.calls as unknown[][];
    for (let index = 0; index < getCases.length; index += 1) {
      const testCase = getCases[index];
      await expect(testCase.invoke()).resolves.toEqual({ ok: true });
      const call = extractCall(calls, index);
      expect(call.url, testCase.name).toBe(`${API_BASE}${testCase.path}`);
      expect(call.init, testCase.name).toMatchObject({ cache: "no-store", credentials: "include" });
    }
    expect(fetchMock).toHaveBeenCalledTimes(getCases.length);
  });

  it("builds EventSource URL for realtime stream", () => {
    const created: Array<{ url: string; init?: EventSourceInit }> = [];
    class MockEventSource {
      url: string;
      constructor(url: string, init?: EventSourceInit) {
        this.url = url;
        created.push({ url, init });
      }
      close() {
        return undefined;
      }
    }
    global.EventSource = MockEventSource as unknown as typeof EventSource;
    const stream = openEventsStream("run/1", { since: "2026-02-09T08:00:00Z", limit: 50, tail: true });
    expect(stream).toBeInstanceOf(MockEventSource);
    expect(created[0]?.url).toBe(
      `${API_BASE}/api/runs/run%2F1/events/stream?since=2026-02-09T08%3A00%3A00Z&limit=50&tail=1`,
    );
    expect(created[0]?.init).toMatchObject({ withCredentials: true });
  });

  it("covers POST wrappers with method, body and route assertions", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await promoteEvidence("run/1");
    await rollbackRun("run/1");
    await rejectRun("run/1");
    await createIntake({ topic: "intake" });
    await previewIntake({ topic: "intake-preview" });
    await answerIntake("intake/1", { answer: "yes" });
    await runIntake("intake/1", { dry_run: false });
    await postPmSessionMessage("session/1", { message: "need update", from_role: "PM" });
    await approveGodMode("run-2");
    await replayRun("run/1");
    await replayRun("run/1", " baseline-9 ");
    await runNextQueue();
    await releaseLocks(["apps/dashboard", "apps/desktop"]);

    const calls = fetchMock.mock.calls as unknown[][];
    const call0 = extractCall(calls, 0);
    expect(call0.url).toBe(`${API_BASE}/api/runs/run%2F1/evidence/promote`);
    expect(call0.init).toMatchObject({ method: "POST", headers: {} });

    const call1 = extractCall(calls, 1);
    expect(call1.url).toBe(`${API_BASE}/api/runs/run%2F1/rollback`);
    expect(call1.init).toMatchObject({ method: "POST", headers: {} });

    const call2 = extractCall(calls, 2);
    expect(call2.url).toBe(`${API_BASE}/api/runs/run%2F1/reject`);
    expect(call2.init).toMatchObject({ method: "POST", headers: {} });

    const call3 = extractCall(calls, 3);
    expect(call3.url).toBe(`${API_BASE}/api/pm/intake`);
    expect(call3.init).toMatchObject({ method: "POST", headers: { "Content-Type": "application/json" } });
    expect(JSON.parse(String(call3.init.body))).toEqual({ topic: "intake" });

    const call4 = extractCall(calls, 4);
    expect(call4.url).toBe(`${API_BASE}/api/pm/intake/preview`);
    expect(JSON.parse(String(call4.init.body))).toEqual({ topic: "intake-preview" });

    const call5 = extractCall(calls, 5);
    expect(call5.url).toBe(`${API_BASE}/api/pm/intake/intake%2F1/answer`);
    expect(JSON.parse(String(call5.init.body))).toEqual({ answer: "yes" });

    const call6 = extractCall(calls, 6);
    expect(call6.url).toBe(`${API_BASE}/api/pm/intake/intake%2F1/run`);
    expect(JSON.parse(String(call6.init.body))).toEqual({ dry_run: false });

    const call7 = extractCall(calls, 7);
    expect(call7.url).toBe(`${API_BASE}/api/pm/sessions/session%2F1/messages`);
    expect(JSON.parse(String(call7.init.body))).toEqual({ message: "need update", from_role: "PM" });

    const call8 = extractCall(calls, 8);
    expect(call8.url).toBe(`${API_BASE}/api/god-mode/approve`);
    expect(JSON.parse(String(call8.init.body))).toEqual({ run_id: "run-2" });

    const call9 = extractCall(calls, 9);
    expect(call9.url).toBe(`${API_BASE}/api/runs/run%2F1/replay`);
    expect(JSON.parse(String(call9.init.body))).toEqual({});

    const call10 = extractCall(calls, 10);
    expect(call10.url).toBe(`${API_BASE}/api/runs/run%2F1/replay`);
    expect(JSON.parse(String(call10.init.body))).toEqual({ baseline_run_id: "baseline-9" });

    const call11 = extractCall(calls, 11);
    expect(call11.url).toBe(`${API_BASE}/api/queue/run-next`);
    expect(JSON.parse(String(call11.init.body))).toEqual({});

    const call12 = extractCall(calls, 12);
    expect(call12.url).toBe(`${API_BASE}/api/locks/release`);
    expect(JSON.parse(String(call12.init.body))).toEqual({ paths: ["apps/dashboard", "apps/desktop"] });
  });

  it("covers queue enqueue route", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await dashboardApi.enqueueRunQueue("run/1", { priority: 3 });
    const call = extractCall(fetchMock.mock.calls as unknown[][], 0);
    expect(call.url).toBe(`${API_BASE}/api/queue/from-run/run%2F1`);
    expect(JSON.parse(String(call.init.body))).toEqual({ priority: 3 });
  });

  it("covers PM sessions/events parameter filters with invalid entries", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await fetchPmSessions({
      status: ["active", "", "  "] as unknown as PmSessionStatus[],
      ownerPm: "",
      projectKey: "",
      sort: "" as unknown as "updated_desc",
      limit: -1,
      offset: -2,
    });
    await fetchPmSessionEvents("pm-1", {
      since: "",
      limit: 0,
      tail: false,
      types: ["", "CHAIN_HANDOFF"],
      runIds: ["", "run-1"],
    });

    const calls = fetchMock.mock.calls as unknown[][];
    const pmSessionsUrl = String(calls[0]?.[0] || "");
    const pmEventsUrl = String(calls[1]?.[0] || "");
    expect(pmSessionsUrl).toContain("/api/pm/sessions?status%5B%5D=active");
    expect(pmSessionsUrl).not.toContain("owner_pm=");
    expect(pmSessionsUrl).not.toContain("project_key=");
    expect(pmSessionsUrl).not.toContain("limit=");
    expect(pmSessionsUrl).not.toContain("offset=");
    expect(pmEventsUrl).toContain("types%5B%5D=CHAIN_HANDOFF");
    expect(pmEventsUrl).toContain("run_ids%5B%5D=run-1");
    expect(pmEventsUrl).not.toContain("since=");
    expect(pmEventsUrl).not.toContain("limit=");
  });

  it("asserts DiffGate run-list links in error, empty and list states", async () => {
    vi.spyOn(dashboardApi, "fetchDiffGate").mockRejectedValueOnce(new Error("load failed"));
    render(createElement(DiffGatePanel));
    const errorState = await screen.findByTestId("diff-gate-error-state");
    expect(errorState).toBeInTheDocument();
    expect(within(errorState).getByRole("link", { name: "Open runs list for investigation" })).toHaveAttribute(
      "href",
      "/runs",
    );

    vi.spyOn(dashboardApi, "fetchDiffGate").mockResolvedValueOnce([]);
    render(createElement(DiffGatePanel));
    const emptyState = await screen.findByTestId("diff-gate-no-items");
    expect(emptyState).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open runs list" })).toHaveAttribute("href", "/runs");

    vi.spyOn(dashboardApi, "fetchDiffGate").mockResolvedValueOnce([
      { run_id: "run-1", status: "FAILED", allowed_paths: [] },
    ] as Array<Record<string, unknown>> as Awaited<ReturnType<typeof dashboardApi.fetchDiffGate>>);
    render(createElement(DiffGatePanel));
    const listPanel = await screen.findByTestId("diff-gate-panel");
    expect(listPanel).toBeInTheDocument();
    expect(within(listPanel).getByRole("link", { name: "Open runs list" })).toHaveAttribute("href", "/runs");
  });

  it("asserts locks refresh action link target on locks page", async () => {
    const fetchMock = vi.fn(async () => jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    render(createElement(LocksPage));

    await screen.findByTestId("locks-empty-state");
    expect(screen.getByRole("button", { name: "Refresh lock list" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to runs" })).toHaveAttribute("href", "/runs");
    expect(screen.getByRole("region", { name: "Lock record list" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("asserts command tower session overview navigation link target", async () => {
    vi.spyOn(dashboardApi, "fetchPmSession").mockResolvedValue({
      session: {
        pm_session_id: "pm-session-1",
        status: "active",
        run_count: 0,
        running_runs: 0,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
      run_ids: [],
      runs: [],
      blockers: [],
    } as Awaited<ReturnType<typeof dashboardApi.fetchPmSession>>);
    vi.spyOn(dashboardApi, "fetchPmSessionEvents").mockResolvedValue([]);
    vi.spyOn(dashboardApi, "fetchPmSessionConversationGraph").mockResolvedValue({
      pm_session_id: "pm-session-1",
      window: "24h",
      nodes: [],
      edges: [],
      stats: { node_count: 0, edge_count: 0 },
    } as Awaited<ReturnType<typeof dashboardApi.fetchPmSessionConversationGraph>>);
    vi.spyOn(dashboardApi, "fetchPmSessionMetrics").mockResolvedValue({
      pm_session_id: "pm-session-1",
      run_count: 0,
      running_runs: 0,
      failed_runs: 0,
      success_runs: 0,
      blocked_runs: 0,
      failure_rate: 0,
      blocked_ratio: 0,
      avg_duration_seconds: 0,
      avg_recovery_seconds: 0,
      cycle_time_seconds: 0,
      mttr_seconds: 0,
    } as Awaited<ReturnType<typeof dashboardApi.fetchPmSessionMetrics>>);

    render(await CommandTowerSessionPage({ params: Promise.resolve({ id: "pm-session-1" }) }));

    const quickNav = screen.getByRole("navigation", { name: "Session page quick navigation" });
    const overviewLink = within(quickNav).getByRole("link", { name: "Return to Command Tower home" });
    expect(overviewLink).toHaveAttribute("href", "/command-tower");
    expect(overviewLink).toHaveTextContent("Back to session overview");
  });

  it("parses JSON via text() fallback when fetch response omits json()", async () => {
    const fetchMock = vi.fn(async () =>
      ({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: async () => '{"ok":true}',
      }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchRuns()).resolves.toEqual({ ok: true });
  });

  it("fails loud when text() fallback returns empty or non-json payload", async () => {
    const emptyTextFetch = vi.fn(async () =>
      ({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: async () => "   ",
      }) as unknown as Response,
    );
    vi.stubGlobal("fetch", emptyTextFetch);
    await expect(fetchRuns()).rejects.toThrow("API /api/runs returned empty response");

    const nonJsonFetch = vi.fn(async () =>
      ({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: async () => "not-json",
      }) as unknown as Response,
    );
    vi.stubGlobal("fetch", nonJsonFetch);
    await expect(fetchRuns()).rejects.toThrow("API /api/runs returned non-JSON response");
  });

  it("throws deterministic error when fetch implementation is unavailable", async () => {
    const originalFetch = globalThis.fetch;
    vi.stubGlobal("fetch", undefined);
    try {
      await expect(fetchRuns()).rejects.toThrow("fetch implementation is required");
    } finally {
      vi.stubGlobal("fetch", originalFetch);
    }
  });
});
