import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  baseAlerts,
  baseOverview,
  baseSessionSummary,
  createDeferred,
  getCommandTowerAsyncMocks,
  setupCommandTowerAsyncDefaultMocks,
  teardownCommandTowerAsyncMocks,
} from "./command_tower_async.shared";
import CommandTowerHomeLive from "../components/command-tower/CommandTowerHomeLive";
import type { CommandTowerAlertsPayload, CommandTowerOverviewPayload } from "../lib/types";

describe("command tower async hardening (home)", () => {
  const mocks = getCommandTowerAsyncMocks();
  const { mockFetchCommandTowerOverview, mockFetchPmSessions, mockFetchCommandTowerAlerts } = mocks;
  const pauseLiveButtonName = /Pause auto-refresh|Pause Live/i;
  const resumeLiveButtonName = /Resume auto-refresh|Resume Live/i;
  const focusToggleGroupName = /Focus view switcher|focus/i;
  const drawerRegionName = /Command Tower context panel|Context and filters/i;
  const statusContains = (pattern: RegExp): boolean =>
    screen.getAllByRole("status").some((node) => pattern.test(node.textContent || ""));
  const querySessionLink = (sessionId: string): HTMLAnchorElement | null =>
    document.querySelector(`a[href="/command-tower/sessions/${sessionId}"]`);
  const hasBackoffSignal = (): boolean =>
    statusContains(/退避重试|backoff/i) || screen.queryAllByText(/退避重试|backoff/i).length > 0;
  const ensureDrawerOpen = async () => {
    if (screen.queryByRole("region", { name: drawerRegionName })) {
      return;
    }
    await act(async () => {
      fireEvent.keyDown(window, { key: "d", altKey: true, shiftKey: true });
    });
    expect(screen.getByRole("region", { name: drawerRegionName })).toBeInTheDocument();
  };
  const advanceRetryWindow = async () => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });
  };
  const focusButtons = (): HTMLButtonElement[] =>
    within(screen.getByRole("group", { name: focusToggleGroupName })).getAllByRole("button") as HTMLButtonElement[];

  beforeEach(() => {
    vi.useRealTimers();
    setupCommandTowerAsyncDefaultMocks(mocks);
  });

  afterEach(() => {
    teardownCommandTowerAsyncMocks();
  });

  it("backs off on home live partial failure and exposes classified error", async () => {
    const previousUrl = window.location.href;
    mockFetchCommandTowerOverview.mockRejectedValue(new Error("Failed to fetch"));
    mockFetchPmSessions.mockResolvedValue([baseSessionSummary("active")]);
    mockFetchCommandTowerAlerts.mockResolvedValue(baseAlerts());

    try {
      window.history.pushState({}, "", "/command-tower");
      render(
        <CommandTowerHomeLive
          initialOverview={baseOverview()}
          initialSessions={[baseSessionSummary("active")]}
        />,
      );

      await waitFor(
        () => {
          expect(hasBackoffSignal()).toBe(true);
        },
        { timeout: 5000 },
      );
      await ensureDrawerOpen();
      expect(screen.getByText(/Current issue:\s*Network issue/i)).toBeInTheDocument();
    } finally {
      window.history.pushState({}, "", previousUrl);
    }
  });

  it("applies status/project/sort filters into live polling query", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await ensureDrawerOpen();
    const failedCheckbox = screen.getByRole("checkbox", { name: "failed" });
    fireEvent.click(failedCheckbox);
    fireEvent.click(failedCheckbox);
    fireEvent.click(failedCheckbox);
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i), {
      target: { value: "cortexpilot" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "failed_desc" },
    });
    fireEvent.click(
      within(screen.getByRole("region", { name: /Filter console|Filters/i })).getByRole("button", { name: /Apply filters|Apply/i }),
    );

    await waitFor(() => {
      const lastCall = mockFetchPmSessions.mock.calls.at(-1)?.[0] as
        | {
            status?: string[];
            projectKey?: string;
            sort?: string;
          }
        | undefined;

      expect(lastCall).not.toBeUndefined();
      expect(lastCall?.status).toEqual(["failed"]);
      expect(lastCall?.projectKey).toBe("cortexpilot");
      expect(lastCall?.sort).toBe("failed_desc");
    });
  });

  it("hydrates filters/live/focus from URL search params on first load", async () => {
    const previousUrl = window.location.href;
    try {
      window.history.pushState(
        {},
        "",
        "/command-tower?status[]=failed&project_key=cortexpilot&sort=failed_desc&focus=blocked&live=0",
      );

      render(
        <CommandTowerHomeLive
          initialOverview={baseOverview()}
          initialSessions={[baseSessionSummary("active")]}
        />,
      );

      await waitFor(() => {
        const lastCall = mockFetchPmSessions.mock.calls.at(-1)?.[0] as
          | {
              status?: string[];
              projectKey?: string;
              sort?: string;
            }
          | undefined;
        expect(lastCall?.status).toEqual(["failed"]);
        expect(lastCall?.projectKey).toBe("cortexpilot");
        expect(lastCall?.sort).toBe("failed_desc");
      });

      await ensureDrawerOpen();
      const [, , blockedButton] = focusButtons();
      expect(blockedButton).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: resumeLiveButtonName })).toBeInTheDocument();
    } finally {
      window.history.pushState({}, "", previousUrl);
    }
  });

  it("resets applied filters through drawer reset action", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await ensureDrawerOpen();
    const filterRegion = screen.getByRole("region", { name: /Filter console|Filters/i });
    const projectInput = screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i);
    fireEvent.change(projectInput, { target: { value: "cortexpilot" } });

    fireEvent.click(within(filterRegion).getByRole("button", { name: /Apply filters|Apply/i }));
    await waitFor(() => {
      const lastCall = mockFetchPmSessions.mock.calls.at(-1)?.[0] as { projectKey?: string } | undefined;
      expect(lastCall?.projectKey).toBe("cortexpilot");
    });

    fireEvent.click(within(filterRegion).getByRole("button", { name: /Reset filters|Reset/i }));
    await waitFor(() => {
      const lastCall = mockFetchPmSessions.mock.calls.at(-1)?.[0] as { projectKey?: string } | undefined;
      expect(lastCall?.projectKey).toBeUndefined();
    });
    expect(projectInput).toHaveValue("");
  });

  it("supports focus view switching and focus-empty fallback", async () => {
    const activeSession = baseSessionSummary("active");
    const failedSession = {
      ...baseSessionSummary("failed"),
      pm_session_id: "pm-failed",
      running_runs: 0,
      failed_runs: 1,
      blocked_runs: 0,
    };
    mockFetchPmSessions.mockResolvedValue([activeSession, failedSession]);

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[activeSession, failedSession]}
      />,
    );

    await ensureDrawerOpen();
    const [allFocusButton, highRiskButton, blockedButton] = focusButtons();
    fireEvent.click(highRiskButton);
    expect(highRiskButton).toHaveAttribute("aria-pressed", "true");
    expect(querySessionLink("pm-failed")).toBeInTheDocument();
    expect(querySessionLink("pm-1")).toBeNull();

    fireEvent.click(blockedButton);
    expect(blockedButton).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => {
      expect(screen.getByText(/No sessions match the current focus (view|mode)|no match/i)).toBeInTheDocument();
    });

    fireEvent.click(allFocusButton);
    expect(allFocusButton).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => {
      expect(querySessionLink("pm-1")).toBeInTheDocument();
    });
  });

  it("toggles high-risk focus with real refresh requests and explicit rollback path", async () => {
    vi.useFakeTimers();
    const activeSession = baseSessionSummary("active");
    const failedSession = {
      ...baseSessionSummary("failed"),
      pm_session_id: "pm-risk-toggle",
      running_runs: 0,
      failed_runs: 1,
      blocked_runs: 0,
    };
    mockFetchPmSessions.mockResolvedValue([activeSession, failedSession]);

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[activeSession, failedSession]}
      />,
    );

    await ensureDrawerOpen();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    const toggleButton = screen.getByRole("button", { name: "Focus high-risk sessions" });
    const callsBeforeEnable = mockFetchPmSessions.mock.calls.length;
    await act(async () => {
      fireEvent.click(toggleButton);
      await Promise.resolve();
    });

    expect(mockFetchPmSessions.mock.calls.length).toBe(callsBeforeEnable + 1);
    expect(toggleButton).toHaveAttribute("aria-pressed", "true");
    expect(toggleButton.getAttribute("aria-label") || "").toMatch(/restore all sessions/i);
    expect(screen.getByText(/Only high-risk sessions are visible/i)).toBeInTheDocument();
    expect(statusContains(/Focus high-risk sessions|Only high-risk sessions are visible/i)).toBe(true);
    expect(statusContains(/Retry succeeded and the live overview is updated/i)).toBe(false);
    expect(querySessionLink("pm-risk-toggle")).toBeInTheDocument();
    expect(querySessionLink("pm-1")).toBeNull();

    const callsBeforeDisable = mockFetchPmSessions.mock.calls.length;
    await act(async () => {
      fireEvent.click(toggleButton);
      await Promise.resolve();
    });

    expect(mockFetchPmSessions.mock.calls.length).toBe(callsBeforeDisable + 1);
    expect(toggleButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText(/Only high-risk sessions are visible/i)).toBeNull();
    expect(querySessionLink("pm-1")).toBeInTheDocument();
  });

  it("toggles high-risk focus button and triggers live refresh chain", async () => {
    const activeSession = baseSessionSummary("active");
    const failedSession = {
      ...baseSessionSummary("failed"),
      pm_session_id: "pm-failed-toggle",
      running_runs: 0,
      failed_runs: 1,
      blocked_runs: 0,
    };
    mockFetchPmSessions.mockResolvedValue([activeSession, failedSession]);

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[activeSession, failedSession]}
      />,
    );

    await waitFor(() => {
      expect(mockFetchPmSessions.mock.calls.length).toBeGreaterThan(0);
    });

    const callsBeforeToggleOn = mockFetchPmSessions.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Focus high-risk sessions" }));
    await waitFor(() => {
      expect(mockFetchPmSessions.mock.calls.length).toBeGreaterThan(callsBeforeToggleOn);
    });
    expect(
      screen.getByRole("button", {
        name: /High-risk sessions are focused\. Click again to restore all sessions\.|High-risk focused/i,
      }),
    ).toHaveAttribute("aria-pressed", "true");

    const callsBeforeToggleOff = mockFetchPmSessions.mock.calls.length;
    fireEvent.click(
      screen.getByRole("button", {
        name: /High-risk sessions are focused\. Click again to restore all sessions\.|High-risk focused/i,
      }),
    );
    await waitFor(() => {
      expect(mockFetchPmSessions.mock.calls.length).toBeGreaterThan(callsBeforeToggleOff);
    });
    expect(screen.getByRole("button", { name: "Focus high-risk sessions" })).toHaveAttribute("aria-pressed", "false");
  });

  it("supports global shortcuts for focus switching and share link copy", async () => {
    const activeSession = baseSessionSummary("active");
    const failedSession = {
      ...baseSessionSummary("failed"),
      pm_session_id: "pm-failed",
      running_runs: 0,
      failed_runs: 1,
      blocked_runs: 0,
    };
    mockFetchPmSessions.mockResolvedValue([activeSession, failedSession]);

    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[activeSession, failedSession]}
      />,
    );

    await ensureDrawerOpen();
    fireEvent.keyDown(window, { key: "2", altKey: true, shiftKey: true });
    await waitFor(() => {
      const [, highRiskButton] = focusButtons();
      expect(highRiskButton).toHaveAttribute("aria-pressed", "true");
    });
    expect(querySessionLink("pm-failed")).toBeInTheDocument();
    expect(querySessionLink("pm-1")).toBeNull();

    fireEvent.keyDown(window, { key: "c", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledTimes(1);
      expect(writeText.mock.calls[0]?.[0]).toContain("focus=high_risk");
    });
    await waitFor(() => {
      expect(statusContains(/Copied the current view link|copied/i)).toBe(true);
    });
  });

  it("supports keyboard shortcuts and live toggle aria state", async () => {
    await act(async () => {
      render(
        <CommandTowerHomeLive
          initialOverview={baseOverview()}
          initialSessions={[baseSessionSummary("active")]}
        />,
      );
    });

    await ensureDrawerOpen();
    const projectInput = screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i);
    await act(async () => {
      fireEvent.change(projectInput, { target: { value: "tower" } });
    });
    await act(async () => {
      fireEvent.keyDown(projectInput, { key: "Enter" });
    });

    await waitFor(() => {
      const lastCall = mockFetchPmSessions.mock.calls.at(-1)?.[0] as
        | {
            projectKey?: string;
          }
        | undefined;
      expect(lastCall?.projectKey).toBe("tower");
    });

    const toggleLiveButton = screen.getByRole("button", { name: pauseLiveButtonName });
    await act(async () => {
      fireEvent.click(toggleLiveButton);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: resumeLiveButtonName })).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.keyDown(projectInput, { key: "Escape" });
    });
    expect(screen.getByPlaceholderText(/例如：cortexpilot|cortexpilot/)).toHaveValue("");
  });

  it("stops polling loop immediately after pausing live refresh", async () => {
    vi.useFakeTimers();

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await ensureDrawerOpen();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    const overviewCallsBeforePause = mockFetchCommandTowerOverview.mock.calls.length;
    const sessionsCallsBeforePause = mockFetchPmSessions.mock.calls.length;
    const alertsCallsBeforePause = mockFetchCommandTowerAlerts.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: pauseLiveButtonName }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(mockFetchCommandTowerOverview.mock.calls.length).toBe(overviewCallsBeforePause);
    expect(mockFetchPmSessions.mock.calls.length).toBe(sessionsCallsBeforePause);
    expect(mockFetchCommandTowerAlerts.mock.calls.length).toBe(alertsCallsBeforePause);
  });

  it("handles malformed alert severity without crashing", async () => {
    mockFetchCommandTowerAlerts.mockResolvedValue({
      generated_at: "2026-02-09T10:00:00Z",
      status: "degraded",
      alerts: [
        {
          code: null as unknown as string,
          severity: null as unknown as "info" | "warning" | "critical",
          message: null as unknown as string,
          suggested_action: "check api",
        },
      ],
    });

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await ensureDrawerOpen();
    const alertsList = await screen.findByRole("list", { name: /Alerts|alert/i });
    expect(within(alertsList).getByText(/^UNKNOWN$/)).toBeInTheDocument();
    expect(within(alertsList).getByText(/UNKNOWN_CODE/)).toBeInTheDocument();
    expect(within(alertsList).getByText(/No alert details/i)).toBeInTheDocument();
  });

  it("covers home export button, degraded SLO badge and no-suggested-action alert", async () => {
    const createUrl = vi.fn(() => "blob:mock-url");
    const revokeUrl = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL: createUrl,
      revokeObjectURL: revokeUrl,
    } as unknown as typeof URL);

    const clickSpy = vi.fn();
    const originalCreate = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const element = originalCreate(tagName);
      if (tagName.toLowerCase() === "a") {
        (element as HTMLAnchorElement).click = clickSpy;
      }
      return element;
    });

    mockFetchCommandTowerOverview.mockResolvedValue({
      ...baseOverview(),
      generated_at: "",
      failed_sessions: 3,
      blocked_sessions: 2,
    });
    mockFetchPmSessions.mockResolvedValue([baseSessionSummary("failed")]);
    mockFetchCommandTowerAlerts.mockResolvedValue({
      generated_at: "2026-02-09T10:00:00Z",
      status: "critical",
      alerts: [
        {
          code: "A1",
          severity: "critical",
          message: "critical alert",
        },
      ],
    });

    render(
      <CommandTowerHomeLive
        initialOverview={{ ...baseOverview(), generated_at: "" }}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await ensureDrawerOpen();
    await waitFor(() => {
      expect(screen.getAllByText(/SLO:\s*warning/i).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /Export(?:ed)? failed/i }));
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeUrl).toHaveBeenCalledTimes(1);
    expect(within(screen.getByRole("list", { name: /Alerts|alert/i })).queryByText(/Suggested action:/i)).toBeNull();
  });

  it("covers home all-failed fallback and paused state", async () => {
    vi.useFakeTimers();
    mockFetchCommandTowerOverview.mockRejectedValue("ov fail");
    mockFetchPmSessions.mockRejectedValue(new Error("network down"));
    mockFetchCommandTowerAlerts.mockRejectedValue("alerts fail");

    render(
      <CommandTowerHomeLive
        initialOverview={{ ...baseOverview(), generated_at: "" }}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await advanceRetryWindow();
    expect(hasBackoffSignal()).toBe(true);
    await ensureDrawerOpen();
    expect(screen.getByText(/Current issue:\s*Service issue\./i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: pauseLiveButtonName }));
    expect(screen.getByRole("button", { name: resumeLiveButtonName })).toBeInTheDocument();
  });

  it("covers home alerts fallback fields and generated_at fallback", async () => {
    vi.useFakeTimers();

    mockFetchCommandTowerOverview.mockResolvedValue({
      ...baseOverview(),
      generated_at: "",
      top_blockers: undefined as unknown as CommandTowerOverviewPayload["top_blockers"],
    });
    mockFetchPmSessions.mockResolvedValue([baseSessionSummary("active")]);
    mockFetchCommandTowerAlerts.mockResolvedValue({
      generated_at: "2026-02-09T10:00:00Z",
      status: "" as unknown as CommandTowerAlertsPayload["status"],
      alerts: undefined as unknown as any[],
    });

    render(
      <CommandTowerHomeLive
        initialOverview={{ ...baseOverview(), generated_at: "" }}
        initialSessions={[
          baseSessionSummary("active"),
          {
            ...baseSessionSummary("active"),
            pm_session_id: "pm-no-status",
            status: "" as any,
          },
        ]}
      />,
    );

    await ensureDrawerOpen();
    fireEvent.keyDown(screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i), { key: "x" });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });

    fireEvent.click(screen.getByRole("button", { name: /Export failed sessions|export/i }));

    expect(screen.getAllByText(/SLO:/).length).toBeGreaterThan(0);
    expect(screen.getByText(/System healthy\. No alerts( right now)?\./i)).toBeInTheDocument();
  });

  it("covers home partial failures with non-Error reasons", async () => {
    vi.useFakeTimers();

    mockFetchCommandTowerOverview.mockResolvedValue(baseOverview());
    mockFetchPmSessions.mockRejectedValue("sessions down");
    mockFetchCommandTowerAlerts.mockRejectedValue("alerts down");

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await advanceRetryWindow();
    expect(hasBackoffSignal()).toBe(true);
    await ensureDrawerOpen();
    expect(screen.getByText(/Current issue:\s*Service issue\./i)).toBeInTheDocument();
  });

  it("uses alerts failure as fallback error source", async () => {
    vi.useFakeTimers();

    mockFetchCommandTowerOverview.mockResolvedValue(baseOverview());
    mockFetchPmSessions.mockResolvedValue([baseSessionSummary("active")]);
    mockFetchCommandTowerAlerts.mockRejectedValue(new Error("alerts-only-down"));

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await advanceRetryWindow();
    expect(hasBackoffSignal()).toBe(true);
    await ensureDrawerOpen();
    expect(screen.getByText(/Current issue:\s*Service issue\./i)).toBeInTheDocument();
  });

  it("shows failure-events action in degraded snapshot card when failed sessions exist", async () => {
    const failedSession = {
      ...baseSessionSummary("failed"),
      pm_session_id: "pm-home-failed",
      failed_runs: 2,
    };
    mockFetchCommandTowerOverview.mockResolvedValue({
      ...baseOverview(),
      failed_sessions: 1,
      failed_ratio: 1,
    });
    mockFetchPmSessions.mockResolvedValue([failedSession]);
    mockFetchCommandTowerAlerts.mockRejectedValue(new Error("alerts-failure"));

    render(
      <CommandTowerHomeLive initialOverview={{ ...baseOverview(), failed_sessions: 1 }} initialSessions={[failedSession]} />,
    );

    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Degraded-state actions" })).toBeInTheDocument();
    });
    const actions = screen.getByRole("group", { name: "Degraded-state actions" });
    expect(within(actions).getByRole("link", { name: "Review failure events" })).toHaveAttribute("href", "/events");
    expect(within(actions).queryByRole("link", { name: "Review runs" })).toBeNull();
  });

  it("shows run-record action in degraded snapshot card when no failed or blocked sessions exist", async () => {
    const activeSession = baseSessionSummary("active");
    mockFetchCommandTowerOverview.mockResolvedValue(baseOverview());
    mockFetchPmSessions.mockResolvedValue([activeSession]);
    mockFetchCommandTowerAlerts.mockRejectedValue(new Error("alerts-temporary"));

    render(<CommandTowerHomeLive initialOverview={baseOverview()} initialSessions={[activeSession]} />);

    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Degraded-state actions" })).toBeInTheDocument();
    });
    const actions = screen.getByRole("group", { name: "Degraded-state actions" });
    expect(within(actions).getByRole("link", { name: "Review runs" })).toHaveAttribute("href", "/runs");
    expect(within(actions).queryByRole("link", { name: "Review failure events" })).toBeNull();
  });

  it("shows run-record action in full fallback card when live data is unavailable", async () => {
    mockFetchCommandTowerOverview.mockRejectedValue(new Error("overview-down"));
    mockFetchPmSessions.mockRejectedValue(new Error("sessions-down"));
    mockFetchCommandTowerAlerts.mockRejectedValue(new Error("alerts-down"));

    render(<CommandTowerHomeLive initialOverview={{ ...baseOverview(), total_sessions: 0 }} initialSessions={[]} />);

    await waitFor(() => {
      expect(screen.getByRole("group", { name: "Degraded-state primary actions" })).toBeInTheDocument();
    });
    const fallbackActions = screen.getByRole("group", { name: "Degraded-state primary actions" });
    expect(within(fallbackActions).getByRole("link", { name: "Review runs" })).toHaveAttribute("href", "/runs");
  });

  it("supports drawer layout controls and keyboard shortcuts with aria semantics", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    expect(screen.queryByRole("region", { name: drawerRegionName })).toBeNull();

    fireEvent.keyDown(window, { key: "d", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(statusContains(/Expanded the right context drawer/i)).toBe(true);
      expect(screen.getByRole("region", { name: drawerRegionName })).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Close panel|Close drawer/ })).toHaveAttribute("aria-keyshortcuts", "Alt+Shift+D");

    fireEvent.keyDown(window, { key: "p", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(statusContains(/Pinned the right drawer|Unpinned the right drawer/i)).toBe(true);
    });

    fireEvent.keyDown(window, { key: "d", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(statusContains(/Collapsed the right context drawer/i)).toBe(true);
      expect(screen.queryByRole("region", { name: drawerRegionName })).toBeNull();
    });
  });

  it("renders zh-CN live feedback copy when locale is provided", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
        locale="zh-CN"
      />,
    );

    fireEvent.keyDown(window, { key: "d", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(statusContains(/已展开右侧上下文抽屉/)).toBe(true);
    });

    fireEvent.keyDown(window, { key: "2", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(statusContains(/已切换到 高风险会话|高风险会话/)).toBe(true);
    });
  });

  it("surfaces refresh health summary and keeps quick action aria descriptions linked", async () => {
    vi.useFakeTimers();
    mockFetchCommandTowerOverview.mockResolvedValue(baseOverview());
    mockFetchPmSessions.mockResolvedValue([baseSessionSummary("active")]);
    mockFetchCommandTowerAlerts.mockRejectedValue(new Error("alerts-temp-down"));

    render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1800);
    });

    await ensureDrawerOpen();
    expect(screen.getByText(/Refresh is partially degraded|Refresh failed|Full refresh healthy/i)).toBeInTheDocument();
    expect(statusContains(/Refresh state|Last successful refresh|No successful refresh yet/i)).toBe(true);

    const quickRefreshButton = screen.getByRole("button", { name: /Refresh now/i });
    const describedBy = quickRefreshButton.getAttribute("aria-describedby");
    const describedByIds = (describedBy ?? "").split(" ").filter(Boolean);
    expect(describedByIds.length).toBeGreaterThan(0);
    for (const id of describedByIds) {
      expect(document.getElementById(id)).not.toBeNull();
    }
  });

  it("cancels in-flight success refresh updates after unmount", async () => {
    vi.useFakeTimers();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const overview = createDeferred<CommandTowerOverviewPayload>();
    const sessions = createDeferred<import("../lib/types").PmSessionSummary[]>();
    const alerts = createDeferred<CommandTowerAlertsPayload>();

    mockFetchCommandTowerOverview.mockImplementation(() => overview.promise);
    mockFetchPmSessions.mockImplementation(() => sessions.promise);
    mockFetchCommandTowerAlerts.mockImplementation(() => alerts.promise);

    const { unmount } = render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    unmount();

    await act(async () => {
      overview.resolve(baseOverview());
      sessions.resolve([baseSessionSummary("active")]);
      alerts.resolve(baseAlerts());
      await Promise.resolve();
    });

    expect(mockFetchCommandTowerOverview).toHaveBeenCalled();
    expect(mockFetchPmSessions).toHaveBeenCalled();
    expect(mockFetchCommandTowerAlerts).toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();

    consoleError.mockRestore();
  });

  it("cancels in-flight failed refresh updates after unmount", async () => {
    vi.useFakeTimers();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const overview = createDeferred<CommandTowerOverviewPayload>();
    const sessions = createDeferred<import("../lib/types").PmSessionSummary[]>();
    const alerts = createDeferred<CommandTowerAlertsPayload>();

    mockFetchCommandTowerOverview.mockImplementation(() => overview.promise);
    mockFetchPmSessions.mockImplementation(() => sessions.promise);
    mockFetchCommandTowerAlerts.mockImplementation(() => alerts.promise);

    const { unmount } = render(
      <CommandTowerHomeLive
        initialOverview={baseOverview()}
        initialSessions={[baseSessionSummary("active")]}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });

    unmount();

    await act(async () => {
      overview.reject(new Error("overview-down"));
      sessions.reject(new Error("sessions-down"));
      alerts.reject(new Error("alerts-down"));
      await Promise.resolve();
    });

    expect(mockFetchCommandTowerOverview).toHaveBeenCalled();
    expect(mockFetchPmSessions).toHaveBeenCalled();
    expect(mockFetchCommandTowerAlerts).toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();

    consoleError.mockRestore();
  });
});
