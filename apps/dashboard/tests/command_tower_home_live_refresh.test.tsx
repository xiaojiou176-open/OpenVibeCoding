import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CommandTowerHomeLive from "../components/command-tower/CommandTowerHomeLive";
import * as api from "../lib/api";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

function createDeferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeOverview(total: number, generatedAt: string) {
  return {
    generated_at: generatedAt,
    total_sessions: total,
    active_sessions: total,
    failed_sessions: 0,
    blocked_sessions: 0,
    top_blockers: [],
  } as any;
}

function makeSession(pmSessionId: string) {
  return {
    pm_session_id: pmSessionId,
    status: "active",
    run_count: 1,
    running_runs: 1,
    failed_runs: 0,
    success_runs: 0,
    blocked_runs: 0,
    current_role: "PM",
    current_step: "intake",
    objective: pmSessionId,
    updated_at: "2026-03-01T00:00:00Z",
  } as any;
}

const pauseLiveButtonName = /Pause auto-refresh|Pause Live|Pause live/;
const resumeLiveButtonName = /Resume auto-refresh|Resume Live|Resume live/;

async function ensureDrawerOpen() {
  const drawerRegionName = /Command Tower context panel|Context and filters/i;
  if (screen.queryByRole("region", { name: drawerRegionName })) {
    return;
  }
  fireEvent.keyDown(window, { key: "d", altKey: true, shiftKey: true });
  await waitFor(() => {
    expect(screen.getByRole("region", { name: drawerRegionName })).toBeInTheDocument();
  });
}

describe("CommandTowerHomeLive refresh sequencing", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("ignores stale polling response that resolves after a newer manual refresh", async () => {
    const pollOverview = createDeferred<any>();
    const pollSessions = createDeferred<any>();
    const pollAlerts = createDeferred<any>();
    const manualOverview = createDeferred<any>();
    const manualSessions = createDeferred<any>();
    const manualAlerts = createDeferred<any>();

    vi.spyOn(api, "fetchCommandTowerOverview")
      .mockImplementationOnce(() => pollOverview.promise)
      .mockImplementationOnce(() => manualOverview.promise)
      .mockResolvedValue(makeOverview(1, "2026-03-01T00:00:02Z"));
    vi.spyOn(api, "fetchPmSessions")
      .mockImplementationOnce(() => pollSessions.promise)
      .mockImplementationOnce(() => manualSessions.promise)
      .mockResolvedValue([makeSession("manual-new")]);
    vi.spyOn(api, "fetchCommandTowerAlerts")
      .mockImplementationOnce(() => pollAlerts.promise)
      .mockImplementationOnce(() => manualAlerts.promise)
      .mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(0, "2026-03-01T00:00:00Z")}
        initialSessions={[]}
      />,
    );

    await waitFor(() => {
      expect(api.fetchCommandTowerOverview).toHaveBeenCalledTimes(1);
    });

    await ensureDrawerOpen();
    fireEvent.click(screen.getByRole("button", { name: /Refresh now/i }));

    await act(async () => {
      manualOverview.resolve(makeOverview(1, "2026-03-01T00:00:01Z"));
      manualSessions.resolve([makeSession("manual-new")]);
      manualAlerts.resolve({ status: "healthy", alerts: [] } as any);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "manual-new" })).toBeInTheDocument();
    });

    await act(async () => {
      pollOverview.resolve(makeOverview(1, "2026-03-01T00:00:00Z"));
      pollSessions.resolve([makeSession("poll-old")]);
      pollAlerts.resolve({ status: "degraded", alerts: [] } as any);
      await Promise.resolve();
    });

    expect(screen.getByRole("link", { name: "manual-new" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "poll-old" })).toBeNull();
  }, 45000);

  it("covers drawer quick-action branches for copy/focus/apply", async () => {
    vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(0, "invalid-date"));
    vi.spyOn(api, "fetchPmSessions").mockResolvedValue([]);
    vi.spyOn(api, "fetchCommandTowerAlerts").mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(0, "invalid-date")}
        initialSessions={[]}
      />,
    );

    await ensureDrawerOpen();

    fireEvent.click(screen.getByRole("button", { name: /CopyC/i }));
    fireEvent.click(screen.getByRole("button", { name: /FocusF/i }));
    fireEvent.click(screen.getByRole("button", { name: /ApplyEnter/i }));

    await waitFor(() => {
      expect(
        screen.getAllByText(/Copied the current view link|Copy failed\. Copy the address bar link manually\.|Focused the project key input|Draft filters already match the applied state/)
          .length,
      ).toBeGreaterThan(0);
    });
  });

  it("covers freshness summary minute-level branch on render", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-03-01T00:05:00Z"));

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(0, "2026-03-01T00:03:00Z")}
        initialSessions={[]}
      />,
    );

    expect(screen.getByRole("button", { name: /Focus high-risk sessions/i })).toBeInTheDocument();
  });

  it("covers quick actions for apply-filter with draft and drawer pin/collapse toggles", async () => {
    vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(3, "2026-03-01T00:05:00Z"));
    vi.spyOn(api, "fetchPmSessions").mockResolvedValue([
      {
        ...makeSession("blocked-1"),
        running_runs: 0,
        failed_runs: 0,
        blocked_runs: 1,
      },
      {
        ...makeSession("idle-1"),
        running_runs: 0,
        failed_runs: 0,
        blocked_runs: 0,
      },
      {
        ...makeSession("running-1"),
        running_runs: 2,
        failed_runs: 0,
        blocked_runs: 0,
      },
    ]);
    vi.spyOn(api, "fetchCommandTowerAlerts").mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(3, "2026-03-01T00:05:00Z")}
        initialSessions={[makeSession("seed")]}
      />,
    );

    await ensureDrawerOpen();

    fireEvent.change(screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i), {
      target: { value: "cortexpilot" },
    });
    fireEvent.click(screen.getByRole("button", { name: /ApplyEnter/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/Applied draft filters \(\d+ items\)/).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /Pin|Unpin/ }));
    await waitFor(() => {
      expect(screen.getAllByText(/Pinned the right drawer|Unpinned the right drawer/).length).toBeGreaterThan(0);
    });

    fireEvent.keyDown(window, { key: "3", altKey: true, shiftKey: true });
    fireEvent.keyDown(window, { key: "4", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(screen.getAllByText(/Switched focus view to blocked|Switched focus view to running/).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /CollapseD/i }));
    await waitFor(() => {
      expect(screen.queryByRole("region", { name: /Command Tower context panel|Context and filters/i })).not.toBeInTheDocument();
    });
  });

  it("covers global shortcut branches for refresh/live/export/focus and same-mode focus feedback", async () => {
    vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(2, "2026-03-01T00:05:00Z"));
    vi.spyOn(api, "fetchPmSessions").mockResolvedValue([
      {
        ...makeSession("failed-1"),
        status: "failed",
        failed_runs: 1,
        running_runs: 0,
      },
      makeSession("running-1"),
    ] as any);
    vi.spyOn(api, "fetchCommandTowerAlerts").mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(2, "2026-03-01T00:05:00Z")}
        initialSessions={[]}
      />,
    );

    await ensureDrawerOpen();

    fireEvent.keyDown(window, { key: "r", altKey: true, shiftKey: true });
    fireEvent.keyDown(window, { key: "l", altKey: true, shiftKey: true });
    fireEvent.keyDown(window, { key: "e", altKey: true, shiftKey: true });
    fireEvent.keyDown(window, { key: "f", altKey: true, shiftKey: true });
    fireEvent.keyDown(window, { key: "1", altKey: true, shiftKey: true });

    await waitFor(() => {
      expect(
        screen.getAllByText(
          /Retry succeeded and the live overview is updated|Paused live refresh|Resumed live refresh|Exported failed sessions|Focused the project key input|Switched focus view to all/,
        ).length,
      ).toBeGreaterThan(0);
    });
    expect(screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i)).toHaveFocus();
  });

  it("ignores global shortcuts when target is contentEditable", async () => {
    const overviewSpy = vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(1, "2026-03-01T00:05:00Z"));
    vi.spyOn(api, "fetchPmSessions").mockResolvedValue([makeSession("editable-1")] as any);
    vi.spyOn(api, "fetchCommandTowerAlerts").mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(1, "2026-03-01T00:05:00Z")}
        initialSessions={[]}
      />,
    );

    await ensureDrawerOpen();
    await waitFor(() => {
      expect(overviewSpy.mock.calls.length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getByRole("button", { name: pauseLiveButtonName }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: resumeLiveButtonName })).toBeInTheDocument();
    });
    const beforeCalls = overviewSpy.mock.calls.length;
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    Object.defineProperty(editable, "isContentEditable", {
      configurable: true,
      value: true,
    });
    document.body.appendChild(editable);

    try {
      editable.focus();
      fireEvent.keyDown(editable, { key: "r", altKey: true, shiftKey: true });
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(screen.queryByText("Retry succeeded and the live overview is updated")).not.toBeInTheDocument();
      expect(overviewSpy.mock.calls.length).toBe(beforeCalls);
    } finally {
      document.body.removeChild(editable);
    }
  });

  it("covers high-risk shortcut and ignores incomplete or repeated key chords", async () => {
    const overviewSpy = vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(2, "2026-03-01T00:05:00Z"));
    vi.spyOn(api, "fetchPmSessions").mockResolvedValue([
      {
        ...makeSession("risk-1"),
        failed_runs: 1,
        running_runs: 0,
      },
      makeSession("running-1"),
    ] as any);
    vi.spyOn(api, "fetchCommandTowerAlerts").mockResolvedValue({ status: "healthy", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(2, "2026-03-01T00:05:00Z")}
        initialSessions={[]}
      />,
    );

    await ensureDrawerOpen();
    await waitFor(() => {
      expect(overviewSpy.mock.calls.length).toBeGreaterThan(0);
    });

    fireEvent.keyDown(window, { key: "2", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(screen.getByText(/Switched focus view to high[- ]risk/)).toBeInTheDocument();
    });

    const beforeIgnoredKeys = overviewSpy.mock.calls.length;
    fireEvent.keyDown(window, { key: "r", altKey: true });
    fireEvent.keyDown(window, { key: "r", altKey: true, shiftKey: true, repeat: true });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(overviewSpy.mock.calls.length).toBe(beforeIgnoredKeys);
  });

  it("shows copy failure feedback when clipboard write rejects", async () => {
    Object.defineProperty(window.navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error("clipboard denied")) },
    });

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(1, "2026-03-01T00:05:00Z")}
        initialSessions={[makeSession("copy-fail-1")]}
      />,
    );

    await ensureDrawerOpen();
    fireEvent.keyDown(window, { key: "c", altKey: true, shiftKey: true });
    await waitFor(() => {
      expect(screen.getByText("Copy failed. Copy the address bar link manually.")).toBeInTheDocument();
    });
  });

  it("refreshes paused mode and surfaces partial failure feedback", async () => {
    vi.spyOn(api, "fetchCommandTowerOverview").mockResolvedValue(makeOverview(1, "2026-03-01T00:05:00Z"));
    vi.spyOn(api, "fetchPmSessions")
      .mockResolvedValueOnce([makeSession("paused-1")] as any)
      .mockRejectedValueOnce(new Error("sessions down"));
    vi.spyOn(api, "fetchCommandTowerAlerts")
      .mockResolvedValueOnce({ status: "healthy", alerts: [] } as any)
      .mockResolvedValueOnce({ status: "degraded", alerts: [] } as any);

    render(
      <CommandTowerHomeLive
        initialOverview={makeOverview(1, "2026-03-01T00:05:00Z")}
        initialSessions={[makeSession("paused-1")]}
      />,
    );

    await ensureDrawerOpen();
    fireEvent.click(screen.getByRole("button", { name: pauseLiveButtonName }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: resumeLiveButtonName })).toBeInTheDocument();
    });

    const filterRegion = screen.getByRole("region", { name: /Filter console|filters/i });
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. cortexpilot|cortexpilot/i), {
      target: { value: "paused-project" },
    });
    fireEvent.click(within(filterRegion).getByRole("button", { name: /Apply filters|Apply/ }));

    await waitFor(() => {
      expect(screen.getAllByText(/Partial degradation \(([12])\/3\)|部分降级（[12]\/3）/).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/SLO:\s*warning|SLO：\s*warning/)).toBeInTheDocument();
  });
});
