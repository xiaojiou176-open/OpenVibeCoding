import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./OverviewPage";
import { PoliciesPage } from "./PoliciesPage";

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchRuns: vi.fn(),
  fetchAllEvents: vi.fn(),
  fetchPolicies: vi.fn(),
}));

import {
  fetchCommandTowerOverview,
  fetchRuns,
  fetchAllEvents,
  fetchPolicies,
} from "../lib/api";

describe("overview + policies low-branch coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("covers OverviewPage danger/success cards, exception fallback action, and run navigation", async () => {
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 6,
      active_sessions: 1,
      failed_ratio: 0.22,
      blocked_sessions: 1,
    } as any);
    vi.mocked(fetchRuns).mockResolvedValue([
      { run_id: "run-running-001", task_id: "task-a", status: "running", created_at: "2026-03-01T00:00:00Z" },
      { run_id: "run-failed-001", task_id: "task-b", status: "failed", created_at: "2026-03-01T01:00:00Z" },
      { run_id: "run-rejected-001", task_id: "task-c", status: "rejected", created_at: "2026-03-01T02:00:00Z" },
    ] as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([
      { event_type: "BLOCKED_STEP", level: "WARN", _run_id: "evt-run-001", ts: "2026-03-01T03:00:00Z" },
      { event: "RISK_NOTICE", level: "WARN", ts: "2026-03-01T03:10:00Z" },
    ] as any);

    render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} />);

    expect(await screen.findByRole("heading", { name: "Operator overview" })).toBeInTheDocument();
    const failedRatio = await screen.findByText("22.0%");
    expect(failedRatio.className).toContain("metric-value--danger");
    const failedRunLink = await screen.findByRole("button", { name: /run-failed-/ });
    expect(failedRunLink).toBeInTheDocument();
    const failedRow = failedRunLink.closest("tr");
    expect(failedRow?.className).toContain("session-row--failed");
    const runningRunLink = screen.getByRole("button", { name: /run-running-/ });
    const runningRow = runningRunLink.closest("tr");
    expect(runningRow?.className).toContain("session-row--running");

    fireEvent.click(failedRunLink);
    expect(onNavigateToRun).toHaveBeenCalledWith("run-failed-001");

    const exceptionsSection = screen.getByRole("region", { name: "Recent exceptions" });
    const runButtons = within(exceptionsSection).getAllByRole("button", { name: "View Run" });
    fireEvent.click(runButtons[0]);
    expect(onNavigateToRun).toHaveBeenCalledWith("run-failed-001");
    expect(within(exceptionsSection).getByText("Open event stream")).toBeInTheDocument();
  });

  it("covers OverviewPage full fallback when all data APIs fail", async () => {
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    vi.mocked(fetchCommandTowerOverview).mockRejectedValue(new Error("overview failed"));
    vi.mocked(fetchRuns).mockRejectedValue(new Error("runs failed"));
    vi.mocked(fetchAllEvents).mockRejectedValue(new Error("events failed"));

    render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} />);
    expect(await screen.findByRole("heading", { name: "Operator overview" })).toBeInTheDocument();

    expect(await screen.findByText("Total sessions")).toBeInTheDocument();
    expect(screen.getAllByText("No runs yet. Start your first request from the PM entrypoint.").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("No exception signals yet. Failed runs and risk events will appear here after tasks start running.")).toBeInTheDocument();
  });

  it("covers OverviewPage non-array fallback and token-based blocked-event detection", async () => {
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 2,
      active_sessions: 0,
      failed_ratio: 0.05,
      blocked_sessions: 0,
    } as any);
    vi.mocked(fetchRuns).mockResolvedValue({ invalid: true } as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([
      { event: "DENY_ACCESS", level: "INFO", run_id: "" },
      { event_type: "", level: undefined },
      { event: "NOISE_ONLY", level: "INFO" },
    ] as any);

    render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} />);
    expect(await screen.findByRole("heading", { name: "Operator overview" })).toBeInTheDocument();

    const failedRatio = await screen.findByText("5.0%");
    expect(failedRatio.className).toContain("metric-value--success");
    expect(screen.getAllByText("No runs yet. Start your first request from the PM entrypoint.").length).toBeGreaterThanOrEqual(2);

    const exceptionsSection = screen.getByRole("region", { name: "Recent exceptions" });
    expect(within(exceptionsSection).getByText("DENY_ACCESS")).toBeInTheDocument();
    expect(within(exceptionsSection).getByText("Open event stream")).toBeInTheDocument();
  });

  it("renders locale-aware overview labels when zh-CN is requested", async () => {
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 2,
      active_sessions: 1,
      failed_ratio: 0,
      blocked_sessions: 0,
    } as any);
    vi.mocked(fetchRuns).mockResolvedValue([
      { run_id: "run-zh-001", task_id: "task-zh", status: "failed", created_at: "2026-03-01T00:00:00Z" },
    ] as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([
      { event: "BLOCKED_STEP", level: "WARN", _run_id: "evt-run-zh", ts: "2026-03-01T03:00:00Z" },
    ] as any);

    render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} locale="zh-CN" />);

    expect(await screen.findByRole("heading", { name: "新手起步" })).toBeInTheDocument();
    expect(screen.getByText("主步骤")).toBeInTheDocument();
    expect(screen.getByText("当前进展")).toBeInTheDocument();
    expect(screen.getAllByText("运行中").length).toBeGreaterThan(0);
    expect(screen.getByText("最近异常")).toBeInTheDocument();
    expect(screen.getByText("任务 task-zh 需要关注")).toBeInTheDocument();
    expect(screen.getByText("级别 WARN · Run evt-run-zh")).toBeInTheDocument();
  });

  it("renders zh-CN overview copy and locale-aware recent exception labels", async () => {
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 3,
      active_sessions: 1,
      failed_ratio: 0.1,
      blocked_sessions: 0,
    } as any);
    vi.mocked(fetchRuns).mockResolvedValue([
      { run_id: "run-zh-001", task_id: "task-zh", status: "failed", created_at: "2026-03-01T01:00:00Z" },
    ] as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([
      { event_type: "BLOCKED_STEP", level: "WARN", _run_id: "evt-run-zh", ts: "2026-03-01T03:00:00Z" },
    ] as any);

    render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} locale="zh-CN" />);

    expect(await screen.findByRole("heading", { name: "新手起步" })).toBeInTheDocument();
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("任务 task-zh 需要关注")).toBeInTheDocument();
    expect(screen.getByText(/级别 WARN · Run evt-run-zh/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看全部运行" })).toBeInTheDocument();
  });

  it("covers PoliciesPage data rendering branches and refresh after non-Error failure", async () => {
    let resolvePolicies: ((value: any) => void) | null = null;
    vi.mocked(fetchPolicies)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePolicies = resolve;
          }) as any
      )
      .mockRejectedValueOnce(new Error("policies error"))
      .mockResolvedValueOnce({
        control_plane_runtime_policy: { completion_governance: { components: ["dod_checker", "reply_auditor", "continuation_policy"] } },
        agent_registry: "ALLOW_ALL",
        command_allowlist: { commands: ["run"] },
        forbidden_actions: null,
        tool_registry: 0,
      } as any);

    render(<PoliciesPage />);
    expect(document.querySelector(".skeleton-stack-lg")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Refreshing..." })).toBeDisabled();
    const resolvePoliciesFn = resolvePolicies as ((value: any) => void) | null;
    if (resolvePoliciesFn) resolvePoliciesFn({});
    await waitFor(() => {
      expect(screen.queryByText("policies error")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    const errorBanner = await screen.findByRole("alert");
    expect(errorBanner).toHaveAttribute("aria-live", "assertive");
    expect(errorBanner).toHaveTextContent("policies error");

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(screen.queryByText("policies error")).not.toBeInTheDocument();
      expect(screen.getByText("Control-plane runtime policy")).toBeInTheDocument();
      expect(screen.getByText("ALLOW_ALL")).toBeInTheDocument();
      expect(screen.getByText(/"completion_governance": \{/)).toBeInTheDocument();
      expect(screen.getByText(/"commands": \[/)).toBeInTheDocument();
      expect(screen.getAllByText("No data").length).toBeGreaterThanOrEqual(2);
    });
  });
});
