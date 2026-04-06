import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MockEventSource,
  RunDetail,
  flushPromises,
  mockFetchFactory,
  setupRunDetailTestEnv,
  teardownRunDetailTestEnv,
} from "./rundetail.shared";

describe("RunDetail core flows", () => {
  beforeEach(() => {
    setupRunDetailTestEnv();
  });

  afterEach(() => {
    teardownRunDetailTestEnv();
  });

  it("renders tabs and refreshes replay evidence", async () => {
    const run = {
      run_id: "run_1",
      task_id: "task_1",
      status: "SUCCESS",
      allowed_paths: ["README.md"],
      contract: { task_id: "task_1" },
      manifest: { chain_id: "chain_1" },
    };
    const events = [
      { ts: "t1", event: "CODEX_CMD", context: { cmd: "echo ok" } },
      { ts: "t2", event: "CHAIN_HANDOFF", context: { from: "a", to: "b" } },
    ];
    const reports = [
      { name: "test_report.json", data: { result: "pass" } },
      { name: "review_report.json", data: { verdict: "approve" } },
      { name: "task_result.json", data: { status: "success" } },
      { name: "replay_report.json", data: { evidence_hashes: { mismatched: [], missing: [], extra: [] } } },
      { name: "chain_report.json", data: { chain_id: "chain_1", status: "SUCCESS", steps: [] } },
    ];
    const chainSpec = { steps: [] };
    const availableRuns = [{ run_id: "baseline_run" }];
    const fetchMock = mockFetchFactory({ events, reports, chainSpec, availableRuns });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={events} diff="diff --git a/a b/b" reports={reports} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByText("Run ID: run_1")).toBeInTheDocument();
    const diffTab = screen.getByRole("tab", { name: "Diff" });
    const logsTab = screen.getByRole("tab", { name: "Logs" });
    const reportsTab = screen.getByRole("tab", { name: "Reports" });
    expect(diffTab).toHaveAttribute("tabindex", "0");
    expect(logsTab).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(diffTab, { key: "ArrowRight" });
    await waitFor(() => {
      expect(logsTab).toHaveAttribute("aria-selected", "true");
      expect(logsTab).toHaveAttribute("tabindex", "0");
    });
    fireEvent.keyDown(logsTab, { key: "End" });
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Chain" })).toHaveAttribute("aria-selected", "true");
    });
    fireEvent.keyDown(reportsTab, { key: "Home" });
    await waitFor(() => {
      expect(diffTab).toHaveAttribute("aria-selected", "true");
    });

    fireEvent.click(screen.getByText("Logs"));
    await waitFor(() => {
      expect(screen.getAllByText(/CODEX_CMD/).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText("Reports"));
    expect(screen.getByText(/Review report/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Run replay comparison"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/replay"),
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.click(screen.getByText("Chain"));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/artifacts?name=chain.json"),
        expect.anything(),
      );
    });
  }, 45_000);

  it("keeps replay successful when only one evidence refresh branch fails", async () => {
    const run = {
      run_id: "run_partial_refresh",
      task_id: "task_partial_refresh",
      status: "SUCCESS",
      allowed_paths: ["README.md"],
      contract: { task_id: "task_partial_refresh" },
      manifest: {},
    };
    const events = [{ ts: "t1", event: "CODEX_CMD", context: { cmd: "echo ok" } }];
    const fetchMock = mockFetchFactory({ events, reports: [], reportsOk: false, availableRuns: [{ run_id: "baseline_run" }] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={events} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    fireEvent.click(screen.getByText("Reports"));
    fireEvent.click(screen.getByTestId("replay-compare-button"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/replay"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(screen.queryByText(/Replay refresh failed/)).not.toBeInTheDocument();
  });

  it("supports live polling toggle and backoff state", async () => {
    vi.useFakeTimers();
    const run = {
      run_id: "run_live",
      task_id: "task_live",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const fetchMock = mockFetchFactory({ eventsOk: false, events: [], reports: [], availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={[]} diff="" reports={[]} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });

    expect(screen.getByText("Retry backoff")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Pause live refresh|Pause Live/i }));
    expect(screen.getByText(/Paused/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Resume live refresh|Resume Live/i }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(screen.getByText("Retry backoff")).toBeInTheDocument();

    vi.useRealTimers();
  });

  it("renders the role binding read model in the status and contract card", async () => {
    const run = {
      run_id: "run_binding",
      task_id: "task_binding",
      status: "RUNNING",
      allowed_paths: ["apps/dashboard"],
      contract: {},
      manifest: {},
      role_binding_read_model: {
        authority: "contract-derived-read-model",
        source: "persisted from contract",
        execution_authority: "task_contract",
        skills_bundle_ref: {
          status: "registry-backed",
          ref: "registry://skills/worker",
          bundle_id: "worker_delivery_core_v1",
          resolved_skill_set: ["contract_alignment"],
          validation: "fail-closed",
        },
        mcp_bundle_ref: {
          status: "registry-backed",
          ref: "registry://mcp/worker-readonly",
          resolved_mcp_tool_set: ["codex"],
          validation: "fail-closed",
        },
        runtime_binding: {
          status: "contract-derived",
          authority_scope: "contract-derived-read-model",
          source: {
            runner: "runtime_options.runner",
            provider: "runtime_options.provider",
            model: "role_contract.runtime_binding.model",
          },
          summary: { runner: "agents", provider: "cliproxyapi", model: "gpt-5.4" },
          capability: {
            status: "previewable",
            lane: "standard-provider-path",
            compat_api_mode: "responses",
            provider_status: "allowlisted",
            provider_inventory_id: "cliproxyapi",
            tool_execution: "provider-path-required",
            notes: [
              "Chat-style compatibility may differ from tool-execution capability.",
              "Execution authority remains task_contract even when role defaults change.",
            ],
          },
        },
      },
    };
    const fetchMock = mockFetchFactory({ events: [], reports: [], availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run as any} events={[]} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByText("Role binding read model")).toBeInTheDocument();
    expect(screen.getByText("Authority: contract-derived-read-model")).toBeInTheDocument();
    expect(screen.getByText("Execution authority: task_contract")).toBeInTheDocument();
    expect(screen.getByText("Skills bundle: worker_delivery_core_v1 (registry-backed)")).toBeInTheDocument();
    expect(screen.getByText("MCP bundle: registry://mcp/worker-readonly (registry-backed)")).toBeInTheDocument();
    expect(screen.getByText("Runtime binding: agents / cliproxyapi / gpt-5.4")).toBeInTheDocument();
    expect(screen.getByText("Runtime capability: standard-provider-path")).toBeInTheDocument();
    expect(screen.getByText("Tool execution: standard-provider-path / provider-path-required")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Read-only note: this mirrors the persisted binding summary. task_contract still owns execution authority.",
      ),
    ).toBeInTheDocument();
  });

  it("uses SSE transport and consumes stream events", async () => {
    const run = {
      run_id: "run_sse",
      task_id: "task_sse",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const fetchMock = mockFetchFactory({ events: [], reports: [], availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;
    (globalThis as unknown as { EventSource?: unknown }).EventSource = MockEventSource;

    render(<RunDetail run={run} events={[]} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    expect(MockEventSource.instances.length).toBeGreaterThan(0);
    const source = MockEventSource.instances[0];

    await act(async () => {
      source.emitOpen();
      source.emitMessage({ ts: "2024-01-01T00:00:01Z", event: "MCP_CALL", context: {} });
      source.emitMessage({ ts: "2024-01-01T00:00:02Z", event: "MCP_CALL", context: {} });
      source.emitMessage({ ts: "2024-01-01T00:00:03Z", event: "MCP_CALL", context: {} });
      await flushPromises();
    });

    expect(screen.getByText("Live transport: sse")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Logs"));
    expect(screen.getAllByText(/MCP_CALL/).length).toBeGreaterThan(0);
  });

  it("falls back to polling after repeated SSE errors", async () => {
    vi.useFakeTimers();
    const run = {
      run_id: "run_sse_fallback",
      task_id: "task_sse_fallback",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const fetchMock = mockFetchFactory({ eventsOk: false, events: [], reports: [], availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;
    (globalThis as unknown as { EventSource?: unknown }).EventSource = MockEventSource;

    render(<RunDetail run={run} events={[]} diff="" reports={[]} />);

    await act(async () => {
      await Promise.resolve();
    });

    expect(MockEventSource.instances.length).toBeGreaterThan(0);

    await act(async () => {
      MockEventSource.instances[0].emitError();
      await vi.advanceTimersByTimeAsync(3000);
      expect(MockEventSource.instances.length).toBeGreaterThan(1);
      MockEventSource.instances[1].emitError();
      await vi.advanceTimersByTimeAsync(6000);
      expect(MockEventSource.instances.length).toBeGreaterThan(2);
      MockEventSource.instances[2].emitError();
    });

    expect(screen.getByText(/polling/i)).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8100);
    });

    expect(screen.getByText("Retry backoff")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/runs/run_sse_fallback/events"))).toBe(true);

    vi.useRealTimers();
  });

  it("stops live polling for terminal status", async () => {
    vi.useFakeTimers();
    const run = {
      run_id: "run_terminal",
      task_id: "task_terminal",
      status: "SUCCESS",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const fetchMock = mockFetchFactory({ events: [], reports: [], availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={[]} diff="" reports={[]} />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText("Terminal snapshot")).toBeInTheDocument();
    const eventCalls = fetchMock.mock.calls.filter(([input]) => String(input).includes("/events"));
    expect(eventCalls.length).toBe(0);

    vi.useRealTimers();
  });

  it("shows lifecycle rail and god mode shortcut when approval is pending", async () => {
    const run = {
      run_id: "run_lifecycle",
      task_id: "task_lifecycle",
      status: "RUNNING",
      allowed_paths: ["apps/"],
      contract: {},
      manifest: { chain_id: "chain_lifecycle" },
    };
    const events = [{ ts: "t1", event: "HUMAN_APPROVAL_REQUIRED", context: { reason: "oauth" } }];
    const reports = [
      {
        name: "chain_report.json",
        data: {
          chain_id: "chain_lifecycle",
          status: "RUNNING",
          lifecycle: {
            enforce: true,
            required_path: ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "TECH_LEAD", "PM"],
            observed_path: ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"],
            missing_required_roles: [],
            is_complete: false,
            workers: { required: 2, observed: 1, ok: false },
            reviewers: {
              required: 2,
              observed: 1,
              quorum: 2,
              pass: 1,
              fail: 0,
              blocked: 0,
              unknown: 0,
              quorum_met: false,
              ok: false,
            },
            tests: { require_test_stage: true, observed: 1, pass: 1, ok: true },
            return_to_pm: { required: true, ok: false },
          },
        },
      },
    ];
    const fetchMock = mockFetchFactory({ events, reports, availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={events} diff="" reports={reports} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByText(/Lifecycle rail/)).toBeInTheDocument();
    expect(screen.getByText(/Worker agents: Completed 1\/2/)).toBeInTheDocument();
    expect(screen.getByText(/Detected 1 HUMAN_APPROVAL_REQUIRED event/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Open manual approvals" });
    expect(link).toHaveAttribute("href", "/god-mode");
  });

  it("opens logs drill-down and refreshes tool calls when key timeline events are clicked", async () => {
    const run = {
      run_id: "run_event_drilldown",
      task_id: "task_event_drilldown",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const events = [
      { ts: "t1", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w1" } },
      { ts: "t2", event: "MCP_CONCURRENCY_CHECK", context: { concurrency: 4 } },
      { ts: "t3", event: "RUNNER_SELECTED", context: { runner: "codex" } },
    ];
    const fetchMock = mockFetchFactory({
      events,
      reports: [],
      availableRuns: [],
      toolCalls: [{ tool: "shell", status: "ok", task_id: "task_event_drilldown" }],
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run as any} events={events as any} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(screen.getByTestId("run-detail-active-tab-state")).toHaveTextContent("Logs");
    expect(screen.getByTestId("run-detail-event-inspect-feedback")).toHaveTextContent(
      "Inspecting WORKTREE_CREATED"
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/runs/run_event_drilldown/artifacts?name=tool_calls.jsonl"),
        expect.anything(),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId("run-detail-event-inspect-feedback")).toHaveTextContent("Found 1 related execution log entry");
    });

    fireEvent.click(screen.getByTestId("event-name-MCP_CONCURRENCY_CHECK"));
    fireEvent.click(screen.getByTestId("event-name-RUNNER_SELECTED"));
    expect(screen.getByTestId("run-detail-active-tab-state")).toHaveTextContent("Logs");
  });

  it("keeps logs panel stable with contextual feedback when WORKTREE_CREATED has no tool calls", async () => {
    const run = {
      run_id: "run_event_empty",
      task_id: "task_event_empty",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const events = [{ ts: "t1", event: "WORKTREE_CREATED", context: { worktree: "/tmp/w-empty" } }];
    const fetchMock = mockFetchFactory({
      events,
      reports: [],
      availableRuns: [],
      toolCalls: [],
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run as any} events={events as any} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    fireEvent.click(screen.getByTestId("event-name-WORKTREE_CREATED"));
    expect(screen.getByTestId("run-detail-active-tab-state")).toHaveTextContent("Logs");
    expect(screen.getByTestId("run-detail-event-inspect-feedback")).toHaveTextContent(
      "Inspecting WORKTREE_CREATED"
    );

    await waitFor(() => {
      expect(screen.getByTestId("run-detail-event-inspect-feedback")).toHaveTextContent(
        "No related tool calls were found. The current event context is still available."
      );
    });
    expect(screen.getByText("No tool calls yet")).toBeInTheDocument();
    expect(screen.getByText("Tool events")).toBeInTheDocument();
  });

  it("treats derived FAILED terminal status as non-live even when run.status is RUNNING", async () => {
    const run = {
      run_id: "run_derived_failed",
      task_id: "task_derived_failed",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const reports = [{ name: "task_result.json", data: { status: "failed" } }];
    const fetchMock = mockFetchFactory({ events: [], reports, availableRuns: [] });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run as any} events={[]} diff="" reports={reports as any} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByText("Terminal snapshot")).toBeInTheDocument();
    expect(screen.getByTestId("failed-terminal-actions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pause live refresh|Pause Live/i })).toBeNull();
  });

  it("shows empty diff, no tool events, and empty chain report", async () => {
    const run = {
      run_id: "run_empty",
      task_id: "task_empty",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: { chain_id: "chain_missing" },
    };
    const events = [{ ts: "t1", event: "RUN_CREATED", context: {} }];
    const fetchMock = mockFetchFactory({
      events,
      reports: [],
      availableRuns: [],
      chainOk: false,
      runsOk: false,
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={events} diff="" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByText("No code changes are available yet.")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Logs"));
    expect(screen.getByText("No tool calls yet")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Chain"));
    expect(screen.getByText("No chain report yet")).toBeInTheDocument();
  });

  it("shows loading states before tool calls and baseline runs resolve", async () => {
    const run = {
      run_id: "run_loading",
      task_id: "task_loading",
      status: "RUNNING",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const never = new Promise<never>(() => {});
    const fetchMock = vi.fn((input: RequestInfo) => {
      const url = String(input);
      if (url.includes("/api/runs/") && url.includes("/events")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }
      if (url.includes("/api/runs/") && url.endsWith("/reports")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => [] });
      }
      if (url.includes("/api/runs/") && url.includes("/artifacts?name=tool_calls.jsonl")) {
        return never;
      }
      if (url.includes("/api/runs") && !url.includes("/api/runs/")) {
        return never;
      }
      if (url.includes("/api/agents/status")) {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ agents: [] }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ data: null }) });
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={[]} diff="" reports={[]} />);

    fireEvent.click(screen.getByText("Logs"));
    expect(screen.getByText("Loading tool calls...")).toBeInTheDocument();
    expect(screen.queryByText("No tool calls yet")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Reports"));
    expect(screen.getAllByText("Loading baseline run IDs...").length).toBeGreaterThan(0);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });

  it("renders evidence diff summary and handles replay error", async () => {
    const run = {
      run_id: "run_err",
      task_id: "task_err",
      status: "FAILED",
      allowed_paths: ["apps/"],
      contract: {},
      manifest: {},
    };
    const reports = [
      {
        name: "replay_report.json",
        data: {
          evidence_hashes: {
            mismatched: [
              { key: "reports/test_report.json", baseline: "a", current: "b" },
              { key: "other.txt", baseline: "x", current: "y" },
            ],
            missing: ["events.jsonl"],
            extra: ["reports/review_report.json"],
          },
        },
      },
    ];
    const fetchMock = mockFetchFactory({
      events: [],
      reports,
      availableRuns: [],
      replayOk: false,
      replayStatus: 500,
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={[]} diff="diff --git a/a b/b" reports={reports} />);
    await act(async () => {
      await flushPromises();
    });

    expect(screen.getByTestId("failed-terminal-actions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Pause live refresh|Pause Live/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open execution logs" }));
    expect(screen.getByTestId("run-detail-active-tab-state")).toHaveTextContent("Logs");
    expect(screen.getByTestId("failed-terminal-action-feedback")).toHaveTextContent(
      "Switched to the logs tab below. Continue with the execution log."
    );
    expect(screen.getByRole("tab", { name: "Logs" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Open diagnostic report" }));
    expect(screen.getByTestId("run-detail-active-tab-state")).toHaveTextContent("Reports");
    expect(screen.getByTestId("failed-terminal-action-feedback")).toHaveTextContent(
      "Switched to the reports tab below. Continue with the diagnostic report."
    );
    expect(screen.getByRole("tab", { name: "Reports" })).toHaveFocus();

    fireEvent.click(screen.getByText("Reports"));
    expect(screen.getByText("Evidence hash differences")).toBeInTheDocument();
    expect(screen.getByText("Difference summary")).toBeInTheDocument();
    expect(screen.getAllByText(/reports\/test_report.json/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Missing: events.jsonl/)).toBeInTheDocument();
    expect(screen.getByText(/Extra: reports\/review_report.json/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Run replay comparison"));
    await waitFor(() => {
      expect(screen.getByText("Replay comparison failed")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Replay comparison failed");
  });

  it("includes baseline run_id in replay payload", async () => {
    const run = {
      run_id: "run_payload",
      task_id: "task_payload",
      status: "SUCCESS",
      allowed_paths: [],
      contract: {},
      manifest: {},
    };
    const fetchMock = mockFetchFactory({
      events: [],
      reports: [],
      availableRuns: [{ run_id: "baseline-1" }],
    });
    // @ts-expect-error test override
    global.fetch = fetchMock;

    render(<RunDetail run={run} events={[]} diff="diff --git a/a b/b" reports={[]} />);
    await act(async () => {
      await flushPromises();
    });

    fireEvent.click(screen.getByText("Reports"));

    await waitFor(() => {
      expect(screen.getByText("baseline-1")).toBeInTheDocument();
    });
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "baseline-1" } });
    await waitFor(() => {
      expect(select).toHaveValue("baseline-1");
    });
    fireEvent.click(screen.getByText("Run replay comparison"));

    await waitFor(() => {
      const calls = fetchMock.mock.calls.filter(([input]) => String(input).includes("/replay"));
      expect(calls.length).toBeGreaterThan(0);
      const body = String(calls[0][1]?.body || "");
      expect(body).toContain("baseline_run_id");
      expect(body).toContain("baseline-1");
    });
  });
});
