import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandTowerPage } from "./CommandTowerPage";

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchCommandTowerAlerts: vi.fn(),
  fetchPmSessions: vi.fn(),
}));

import { fetchCommandTowerOverview, fetchCommandTowerAlerts, fetchPmSessions } from "../lib/api";

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function mockHealthyData() {
  vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
    total_sessions: 2,
    active_sessions: 1,
    failed_sessions: 1,
    blocked_sessions: 1,
    failed_ratio: 0.5,
    generated_at: "2026-02-20T00:00:00Z",
    top_blockers: [],
  } as any);
  vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({ status: "healthy", alerts: [] } as any);
  vi.mocked(fetchPmSessions).mockResolvedValue([
    {
      pm_session_id: "pm-1",
      status: "active",
      objective: "obj-1",
      run_count: 2,
      running_runs: 1,
      failed_runs: 0,
      success_runs: 1,
      blocked_runs: 0,
      updated_at: "2026-02-20T00:00:00Z",
    },
    {
      pm_session_id: "pm-2",
      status: "failed",
      objective: "obj-2",
      run_count: 2,
      running_runs: 0,
      failed_runs: 1,
      success_runs: 1,
      blocked_runs: 0,
      updated_at: "2026-02-20T00:00:00Z",
    },
  ] as any);
}

describe("CommandTowerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHealthyData();
    vi.spyOn(window, "open").mockImplementation(() => null);
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("renders empty-state when applied filters have no hit", async () => {
    vi.mocked(fetchPmSessions).mockImplementation(async (params: any) => {
      if (params?.projectKey === "proj-a") return [] as any;
      return [
        {
          pm_session_id: "pm-1",
          status: "active",
          objective: "obj-1",
          run_count: 2,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 1,
          blocked_runs: 0,
          updated_at: "2026-02-20T00:00:00Z",
        },
      ] as any;
    });

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    await user.click(screen.getByRole("checkbox", { name: "active" }));
    await user.type(screen.getByPlaceholderText("cortexpilot"), "proj-a");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(await screen.findByText("No sessions match the current filters.")).toBeInTheDocument();
  });

  it("renders focus-empty branch and can reset to all", async () => {
    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    await user.click(screen.getByRole("button", { name: /^Blocked/ }));
    expect(await screen.findByText("No sessions match the current focus mode.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View all" }));
    expect(screen.queryByText("No sessions match the current focus mode.")).not.toBeInTheDocument();
  });

  it("enters backoff mode on partial failure and shows section status", async () => {
    vi.mocked(fetchPmSessions).mockRejectedValueOnce(new Error("sessions failed"));

    const user = userEvent.setup();
    render(<CommandTowerPage />);

    expect(await screen.findByText("Backoff")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show advanced detail" }));

    expect(screen.getAllByText("Partial refresh succeeded (2/3)").length).toBeGreaterThan(0);
    expect(screen.getByText(/sessions failed/)).toBeInTheDocument();
    expect(screen.getAllByText("Sessions Issue").length).toBeGreaterThan(0);
  });

  it("handles quick actions + shortcuts + clipboard failure branch", async () => {
    const user = userEvent.setup();
    const onNavigateToSession = vi.fn();
    render(<CommandTowerPage onNavigateToSession={onNavigateToSession} />);

    expect(await screen.findByRole("heading", { name: "Command Tower" })).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Resume work" }));
    expect(onNavigateToSession).toHaveBeenCalledWith("pm-1");

    await user.click(screen.getByRole("button", { name: "Open web deep analysis" }));
    expect(window.open).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Show advanced detail" }));
    await user.click(screen.getByRole("button", { name: "Close drawer" }));
    expect(screen.queryByRole("complementary", { name: "Command Tower context drawer" })).not.toBeInTheDocument();

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "f" });
    expect(screen.getByPlaceholderText("cortexpilot")).toHaveFocus();

    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: () => Promise.reject(new Error("copy fail")) },
    });
    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "c" });

    await waitFor(() => {
      expect(screen.getByText("Copy failed.")).toBeInTheDocument();
    });
  });

  it("applies and resets filters by keyboard, and ignores shortcut when typing", async () => {
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-10",
        status: "active",
        objective: "obj-10",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        updated_at: "2026-02-20T00:00:00Z",
      },
    ] as any);

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    const projectInput = screen.getByPlaceholderText("cortexpilot");
    await user.type(projectInput, "  project-x  ");
    fireEvent.keyDown(projectInput, { key: "Enter" });

    await waitFor(() => {
      expect(vi.mocked(fetchPmSessions)).toHaveBeenCalledWith(
        expect.objectContaining({
          projectKey: "project-x",
          sort: "updated_desc",
          status: undefined,
        }),
      );
    });

    fireEvent.keyDown(projectInput, { key: "Escape" });
    await waitFor(() => {
      expect(projectInput).toHaveValue("");
    });

    fireEvent.keyDown(projectInput, { altKey: true, shiftKey: true, key: "f" });
    expect(screen.queryByText("Focused the project key input.")).not.toBeInTheDocument();
  });

  it("shows full-chain failure, then recovers after retry", async () => {
    vi.mocked(fetchCommandTowerOverview)
      .mockRejectedValueOnce(new Error("overview down"))
      .mockResolvedValue({
        total_sessions: 1,
        active_sessions: 1,
        failed_sessions: 0,
        blocked_sessions: 0,
        failed_ratio: 0,
        generated_at: "2026-02-20T00:00:00Z",
        top_blockers: [],
      } as any);
    vi.mocked(fetchPmSessions)
      .mockRejectedValueOnce(new Error("sessions down"))
      .mockResolvedValue([
        {
          pm_session_id: "pm-recover",
          status: "active",
          objective: "recovered",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 1,
          blocked_runs: 0,
          updated_at: "2026-02-20T00:00:00Z",
        },
      ] as any);
    vi.mocked(fetchCommandTowerAlerts)
      .mockRejectedValueOnce(new Error("alerts down"))
      .mockResolvedValue({ status: "healthy", alerts: [] } as any);

    const user = userEvent.setup();
    render(<CommandTowerPage />);

    await waitFor(() => {
      expect(screen.getByText(/Full pipeline refresh failed/)).toBeInTheDocument();
    });
    expect(screen.getByText("Backoff")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show advanced detail" }));
    await user.click(screen.getByRole("button", { name: "Retry refresh" }));
    expect((await screen.findAllByText("Full refresh succeeded")).length).toBeGreaterThan(0);
  });

  it("renders alerts fallback fields and row keyboard navigation", async () => {
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({
      status: "critical",
      alerts: [
        {
          severity: "critical",
          code: "CPU_SPIKE",
          message: "CPU usage > 95%",
          suggested_action: "Scale up workers",
        },
        {
          severity: "",
          code: "",
          message: "",
        },
      ],
    } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-keyboard",
        status: "active",
        objective: "obj-keyboard",
        run_count: 3,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 3,
        blocked_runs: 0,
        updated_at: "2026-02-20T00:00:00Z",
      },
    ] as any);

    const onNavigateToSession = vi.fn();
    const user = userEvent.setup();
    render(<CommandTowerPage onNavigateToSession={onNavigateToSession} />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    expect(screen.getByText("SLO: critical")).toBeInTheDocument();
    expect(screen.getByText("Scale up workers")).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN_CODE")).toBeInTheDocument();
    expect(screen.getByText("No alert details.")).toBeInTheDocument();

    const openSessionButton = screen.getByRole("button", { name: "Open session pm-keyboard" });
    openSessionButton.focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{Space}");

    expect(onNavigateToSession).toHaveBeenNthCalledWith(1, "pm-keyboard");
    expect(onNavigateToSession).toHaveBeenNthCalledWith(2, "pm-keyboard");
  });

  it("covers success shortcuts (export/copy/live/focus) and drawer quick actions", async () => {
    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "e" });
    expect(await screen.findByText("Exported failed sessions.")).toBeInTheDocument();

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "c" });
    expect(await screen.findByText("Copied the current view settings.")).toBeInTheDocument();

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "l" });
    await waitFor(() => {
      expect(screen.getByText("Live refresh paused.")).toBeInTheDocument();
      expect(screen.getAllByText("Paused").length).toBeGreaterThan(0);
    });

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "1" });
    expect(await screen.findByText("Focus: all.")).toBeInTheDocument();
    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "2" });
    expect(await screen.findByText("Focus: high risk.")).toBeInTheDocument();
    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "4" });
    expect(await screen.findByText("Focus: running.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resume auto-refresh" }));
    expect(await screen.findByRole("button", { name: "Pause auto-refresh" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pause auto-refresh" }));
    expect(await screen.findByRole("button", { name: "Resume auto-refresh" })).toBeInTheDocument();

    const quickCopyButtons = screen.getAllByRole("button", { name: /^Copy/ });
    const quickCopy = quickCopyButtons[quickCopyButtons.length - 1];
    await user.click(quickCopy);
    expect(await screen.findByText("Copied the current view settings.")).toBeInTheDocument();

    expect(screen.getByText("Alt+Shift+R")).toBeInTheDocument();
    expect(screen.getByText("Alt+Shift+L")).toBeInTheDocument();
    expect(screen.getByText("Alt+Shift+E")).toBeInTheDocument();
    expect(screen.getByText("Alt+Shift+C")).toBeInTheDocument();
  });

  it("renders warning alerts, top blockers and empty sessions fallback actions", async () => {
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 0,
      active_sessions: 0,
      failed_sessions: 0,
      blocked_sessions: 0,
      failed_ratio: 0,
      generated_at: "2026-02-20T00:00:00Z",
      top_blockers: [{ pm_session_id: "pm-blocker", status: "paused", objective: "" }],
    } as any);
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({
      status: "degraded",
      alerts: [{ severity: "warning", code: "WARN_1", message: "warn message" }],
    } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([] as any);

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    expect(screen.getByText("SLO: degraded")).toBeInTheDocument();
    expect(screen.getByText("WARNING")).toBeInTheDocument();
    expect(screen.getByText("warn message")).toBeInTheDocument();
    expect(screen.getByText("Blocking hotspots")).toBeInTheDocument();
    expect(screen.getByText("pm-blocker")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();

    expect(screen.getByText("No sessions yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View all sessions" }));
    expect(screen.getByText("No sessions yet.")).toBeInTheDocument();
  });

  it("supports sort switching and error-banner pause action", async () => {
    vi.mocked(fetchPmSessions).mockImplementation(async (params: any) => {
      if (params?.sort === "failed_desc") {
        return [
          {
            pm_session_id: "pm-failed-sort",
            status: "failed",
            objective: "sorted",
            run_count: 2,
            running_runs: 0,
            failed_runs: 2,
            success_runs: 0,
            blocked_runs: 1,
            updated_at: "2026-02-20T00:00:00Z",
          },
        ] as any;
      }
      return [
        {
          pm_session_id: "pm-default",
          status: "active",
          objective: "default",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 1,
          blocked_runs: 0,
          updated_at: "2026-02-20T00:00:00Z",
        },
      ] as any;
    });
    vi.mocked(fetchCommandTowerOverview).mockRejectedValue(new Error("overview unavailable"));

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    await user.selectOptions(screen.getByRole("combobox"), "failed_desc");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(vi.mocked(fetchPmSessions)).toHaveBeenCalledWith(
        expect.objectContaining({ sort: "failed_desc" }),
      );
    });

    expect(await screen.findByText(/overview unavailable/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pause live triage" }));
    await waitFor(() => {
      expect(screen.getAllByText("Paused").length).toBeGreaterThan(0);
    });
  });

  it("prevents stale polling response from overriding newer manual refresh result", async () => {
    const oldSessionsDeferred = createDeferred<any>();
    const oldOverviewDeferred = createDeferred<any>();
    const oldAlertsDeferred = createDeferred<any>();

    let overviewCalls = 0;
    let sessionsCalls = 0;
    let alertsCalls = 0;

    vi.mocked(fetchCommandTowerOverview).mockImplementation(async () => {
      overviewCalls += 1;
      if (overviewCalls === 1) {
        return {
          total_sessions: 1,
          active_sessions: 1,
          failed_sessions: 0,
          blocked_sessions: 0,
          failed_ratio: 0,
          generated_at: "2026-02-20T00:00:00Z",
          top_blockers: [],
        } as any;
      }
      if (overviewCalls === 2) {
        return oldOverviewDeferred.promise;
      }
      return {
        total_sessions: 1,
        active_sessions: 1,
        failed_sessions: 0,
        blocked_sessions: 0,
        failed_ratio: 0,
        generated_at: "2026-02-20T00:00:00Z",
        top_blockers: [],
      } as any;
    });

    vi.mocked(fetchPmSessions).mockImplementation(async () => {
      sessionsCalls += 1;
      if (sessionsCalls === 1) {
        return [
          {
            pm_session_id: "pm-initial",
            status: "active",
            objective: "initial",
            run_count: 1,
            running_runs: 1,
            failed_runs: 0,
            success_runs: 1,
            blocked_runs: 0,
            updated_at: "2026-02-20T00:00:00Z",
          },
        ] as any;
      }
      if (sessionsCalls === 2) {
        return oldSessionsDeferred.promise;
      }
      return [
        {
          pm_session_id: "pm-newer",
          status: "active",
          objective: "manual",
          run_count: 2,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 2,
          blocked_runs: 0,
          updated_at: "2026-02-20T00:00:00Z",
        },
      ] as any;
    });

    vi.mocked(fetchCommandTowerAlerts).mockImplementation(async () => {
      alertsCalls += 1;
      if (alertsCalls === 1) {
        return { status: "healthy", alerts: [] } as any;
      }
      if (alertsCalls === 2) {
        return oldAlertsDeferred.promise;
      }
      return { status: "healthy", alerts: [] } as any;
    });

    const user = userEvent.setup();
    render(<CommandTowerPage onNavigateToSession={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    expect(await screen.findByText("pm-initial")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(vi.mocked(fetchPmSessions)).toHaveBeenCalledTimes(2);
      },
      { timeout: 5000 },
    );

    await user.click(screen.getByRole("button", { name: "Refresh progress" }));
    expect(await screen.findByText("pm-newer")).toBeInTheDocument();

    await act(async () => {
      oldOverviewDeferred.resolve({
        total_sessions: 1,
        active_sessions: 1,
        failed_sessions: 0,
        blocked_sessions: 0,
        failed_ratio: 0,
        generated_at: "2026-02-20T00:00:00Z",
        top_blockers: [],
      });
      oldAlertsDeferred.resolve({ status: "healthy", alerts: [] });
      oldSessionsDeferred.resolve([
        {
          pm_session_id: "pm-stale",
          status: "active",
          objective: "stale",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 1,
          blocked_runs: 0,
          updated_at: "2026-02-20T00:00:00Z",
        },
      ]);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByText("pm-newer")).toBeInTheDocument();
    });
    expect(screen.queryByText("pm-stale")).not.toBeInTheDocument();
  });

  it("covers no-session primary action, status toggle and keyboard shortcut branches", async () => {
    vi.mocked(fetchPmSessions).mockResolvedValue([] as any);

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    expect(screen.getByRole("button", { name: "Resume work" })).toBeDisabled();

    const activeStatusCheckbox = screen.getByRole("checkbox", { name: "active" });
    await user.click(activeStatusCheckbox);
    await user.click(activeStatusCheckbox);

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "r" });
    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "d" });
    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "3" });

    await waitFor(() => {
      expect(
        screen.getAllByText(/Triggered refresh now\.|Collapsed the right drawer\.|Expanded the right drawer\.|Focus: blocked\./).length,
      ).toBeGreaterThan(0);
    });
  });

  it("covers alerts rejection first-error branch", async () => {
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 1,
      active_sessions: 1,
      failed_sessions: 0,
      blocked_sessions: 0,
      failed_ratio: 0,
      generated_at: "2026-02-20T00:00:00Z",
      top_blockers: [],
    } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-alert-fail",
        status: "active",
        objective: "obj-alert-fail",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        updated_at: "2026-02-20T00:00:00Z",
      },
    ] as any);
    vi.mocked(fetchCommandTowerAlerts).mockRejectedValue("alerts-down");

    const user = userEvent.setup();
    render(<CommandTowerPage />);
    await user.click(await screen.findByRole("button", { name: "Show advanced detail" }));

    await waitFor(() => {
      expect(screen.getByText(/alerts-down/)).toBeInTheDocument();
    });
  });

  it("covers freshness minute and hour branches", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-20T00:05:00Z"));
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 1,
      active_sessions: 1,
      failed_sessions: 0,
      blocked_sessions: 0,
      failed_ratio: 0,
      generated_at: "2026-02-20T00:00:00Z",
      top_blockers: [],
    } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-freshness",
        status: "active",
        objective: "obj-freshness",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        updated_at: "2026-02-20T00:00:00Z",
      },
    ] as any);
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({ status: "healthy", alerts: [] } as any);

    try {
      render(<CommandTowerPage />);
      await act(async () => {
        vi.runOnlyPendingTimers();
        await Promise.resolve();
      });
      expect(screen.getByRole("heading", { name: "Command Tower" })).toBeInTheDocument();
      expect(screen.getAllByText(/Refreshed 0s ago/).length).toBeGreaterThan(0);

      vi.setSystemTime(new Date("2026-02-20T02:05:00Z"));
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Pause auto-refresh" }));
        await Promise.resolve();
      });
      expect(screen.getAllByText(/Refreshed 2h ago/).length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });
});
