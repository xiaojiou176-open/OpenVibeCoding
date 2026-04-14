import { createRef, type ComponentProps } from "react";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";

import CommandTowerHomeLayout from "../components/command-tower/CommandTowerHomeLayout";
import { useDrawerPreferences } from "../components/command-tower/hooks/useDrawerPreferences";
import { useCommandTowerSessionLiveSync } from "../components/command-tower/hooks/useCommandTowerSessionLiveSync";
import * as api from "../lib/api";
import type {
  EventRecord,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
  PmSessionSummary,
} from "../lib/types";

type HookProbeProps = {
  pmSessionId: string;
  initialDetail: PmSessionDetailPayload;
  initialEvents: EventRecord[];
  initialGraph: PmSessionConversationGraphPayload;
  initialMetrics: PmSessionMetricsPayload;
  liveEnabled: boolean;
  onDrawerFeedback?: (message: string) => void;
};

function HookProbe(props: HookProbeProps) {
  const { onDrawerFeedback = () => {}, ...rest } = props;
  const sync = useCommandTowerSessionLiveSync({
    ...rest,
    onDrawerFeedback,
  });
  return (
    <div>
      <p data-testid="session-id">{sync.detail.session.pm_session_id}</p>
      <p data-testid="event-message">{String(sync.events[0]?.context?.message || "none")}</p>
      <p data-testid="transport">{sync.transport}</p>
      <p data-testid="error-message">{sync.errorMessage || "none"}</p>
      <p data-testid="live-mode">{sync.liveMode}</p>
      <p data-testid="last-updated">{sync.lastUpdated || "none"}</p>
      <p data-testid="refreshing">{sync.refreshing ? "true" : "false"}</p>
      <button
        type="button"
        onClick={() => {
          sync.setErrorMessage("stale-error");
          sync.setLiveMode("backoff");
          sync.setTransport("polling");
        }}
      >
        inject-stale
      </button>
      <button
        type="button"
        onClick={() => {
          void sync.refreshAll();
        }}
      >
        manual-refresh
      </button>
    </div>
  );
}

function buildHomeLayoutProps(
  overrides: Partial<ComponentProps<typeof CommandTowerHomeLayout>> = {},
): ComponentProps<typeof CommandTowerHomeLayout> {
  const uiCopy = getUiCopy("en");
  return {
    drawerCollapsed: true,
    liveMode: "running",
    alertsStatus: "ok",
    refreshHealthSummary: { label: "Healthy", badgeVariant: "success" },
    snapshotStatus: { enabled: false, label: "" },
    toggleDrawerCollapsed: vi.fn(),
    liveStatusText: "Running",
    intervalMs: 1500,
    actionFeedback: "",
    priorityLanes: [],
    showGlobalEmptyState: false,
    showFilterEmptyState: false,
    showFocusEmptyState: false,
    resetFilters: vi.fn(),
    setFocusMode: vi.fn(),
    toggleHighRiskFocus: vi.fn(),
    errorMessage: "",
    errorMetaLabel: "Normal",
    visibleSessionCount: 0,
    totalSessionCount: 0,
    visibleSummary: { total: 0, failed: 0, blocked: 0, running: 0 },
    focusLabel: "All",
    visibleSessions: [] as PmSessionSummary[],
    SessionBoardComponent: ({ sessions }: { sessions: PmSessionSummary[] }) => (
      <div data-testid="board-size">{sessions.length}</div>
    ),
    DrawerComponent: () => <aside>drawer</aside>,
    drawerLiveBadgeVariant: "running",
    homeLiveBadgeText: () => "Live",
    homeLiveBadgeVariant: () => "running",
    alertsBadgeVariant: () => "running",
    quickActionItems: [],
    contextHealthItems: [],
    sectionStatusItems: [],
    drawerPromptItems: [],
    overview: { top_blockers: [] } as never,
    alerts: [],
    criticalAlerts: 0,
    draftChanged: false,
    draftStatuses: [],
    draftProjectKey: "",
    draftSort: "updated_desc",
    statusOptions: [],
    sortOptions: [],
    focusOptionsForDrawer: [],
    focusMode: "all",
    appliedFilterCount: 0,
    projectInputRef: createRef<HTMLInputElement>(),
    toggleDraftStatus: vi.fn(),
    setDraftProjectKey: vi.fn(),
    setDraftSort: vi.fn(),
    handleFilterKeyDown: vi.fn(),
    applyFilters: vi.fn(),
    commandTowerCopy: uiCopy.desktop.commandTower,
    liveHomeCopy: uiCopy.dashboard.commandTowerPage.liveHome,
    ...overrides,
  };
}

describe("command tower session live sync + home layout", () => {
  it("resets stale state on session switch and binds new initial payloads", async () => {
    const sessionADetail = {
      session: {
        pm_session_id: "pm-a",
        status: "active",
        latest_run_id: "run-a",
        updated_at: "2026-03-01T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-a"],
    } as unknown as PmSessionDetailPayload;
    const sessionBDetail = {
      session: {
        pm_session_id: "pm-b",
        status: "active",
        latest_run_id: "",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: [],
    } as unknown as PmSessionDetailPayload;
    const sessionAEvents = [{ ts: "2026-03-01T00:00:00Z", context: { message: "session=pm-a" } }] as EventRecord[];
    const sessionBEvents = [{ ts: "2026-03-02T00:00:00Z", context: { message: "session=pm-b" } }] as EventRecord[];

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-a"
        initialDetail={sessionADetail}
        initialEvents={sessionAEvents}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={false}
      />,
    );

    expect(screen.getByTestId("session-id").textContent).toBe("pm-a");
    expect(screen.getByTestId("transport").textContent).toBe("sse");

    fireEvent.click(screen.getByRole("button", { name: "inject-stale" }));
    expect(screen.getByTestId("error-message").textContent).toBe("stale-error");

    rerender(
      <HookProbe
        pmSessionId="pm-b"
        initialDetail={sessionBDetail}
        initialEvents={sessionBEvents}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("session-id").textContent).toBe("pm-b");
    });
    expect(screen.getByTestId("event-message").textContent).toBe("session=pm-b");
    expect(screen.getByTestId("transport").textContent).toBe("polling");
    expect(screen.getByTestId("error-message").textContent).toBe("none");
    expect(screen.getByTestId("live-mode").textContent).toBe("paused");
    expect(screen.getByTestId("last-updated").textContent).toBe("2026-03-02T00:00:00Z");
  });

  it("absorbs updated initial payloads on same session id while live is disabled", async () => {
    const initialDetail = {
      session: {
        pm_session_id: "pm-stable",
        status: "active",
        latest_run_id: "",
        updated_at: "2026-03-01T00:00:00Z",
      },
      runs: [],
      run_ids: [],
    } as unknown as PmSessionDetailPayload;
    const updatedDetail = {
      session: {
        pm_session_id: "pm-stable",
        status: "active",
        latest_run_id: "run-stable",
        updated_at: "2026-03-02T12:34:56Z",
      },
      runs: [],
      run_ids: ["run-stable"],
    } as unknown as PmSessionDetailPayload;
    const initialEvents = [{ ts: "2026-03-01T00:00:00Z", context: { message: "initial-event" } }] as EventRecord[];
    const updatedEvents = [{ ts: "2026-03-02T12:34:56Z", context: { message: "updated-event" } }] as EventRecord[];

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-stable"
        initialDetail={initialDetail}
        initialEvents={initialEvents}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "inject-stale" }));
    expect(screen.getByTestId("error-message").textContent).toBe("stale-error");
    expect(screen.getByTestId("event-message").textContent).toBe("initial-event");
    expect(screen.getByTestId("transport").textContent).toBe("polling");

    rerender(
      <HookProbe
        pmSessionId="pm-stable"
        initialDetail={updatedDetail}
        initialEvents={updatedEvents}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{ refreshed: true } as unknown as PmSessionMetricsPayload}
        liveEnabled={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("event-message").textContent).toBe("updated-event");
    });
    expect(screen.getByTestId("session-id").textContent).toBe("pm-stable");
    expect(screen.getByTestId("error-message").textContent).toBe("none");
    expect(screen.getByTestId("live-mode").textContent).toBe("paused");
    expect(screen.getByTestId("last-updated").textContent).toBe("2026-03-02T12:34:56Z");
    expect(screen.getByTestId("transport").textContent).toBe("sse");
  });

  it("applies drawer state modifier classes on home layout root", () => {
    const { container, rerender } = render(<CommandTowerHomeLayout {...buildHomeLayoutProps({ drawerCollapsed: true })} />);

    const root = container.firstElementChild;
    expect(root).not.toBeNull();
    expect(root).toHaveClass("ct-home-layout");
    expect(root).toHaveClass("ct-home-layout--drawer-collapsed");
    expect(root).not.toHaveClass("ct-home-layout--drawer-expanded");

    rerender(<CommandTowerHomeLayout {...buildHomeLayoutProps({ drawerCollapsed: false })} />);

    const expandedRoot = container.firstElementChild;
    expect(expandedRoot).not.toBeNull();
    expect(expandedRoot).toHaveClass("ct-home-layout");
    expect(expandedRoot).toHaveClass("ct-home-layout--drawer-expanded");
    expect(expandedRoot).not.toHaveClass("ct-home-layout--drawer-collapsed");
  });

  it("resets transport/live mode to running+sse when switched session has latest run and live enabled", async () => {
    const close = vi.fn();
    const stream = {
      close,
      onmessage: null,
      onerror: null,
      onopen: null,
    } as unknown as EventSource;
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockReturnValue(stream);

    const sessionADetail = {
      session: {
        pm_session_id: "pm-a",
        status: "active",
        latest_run_id: "",
        updated_at: "2026-03-01T00:00:00Z",
      },
      runs: [],
      run_ids: [],
    } as unknown as PmSessionDetailPayload;
    const sessionBDetail = {
      session: {
        pm_session_id: "pm-b",
        status: "active",
        latest_run_id: "run-b",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-b"],
    } as unknown as PmSessionDetailPayload;

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-a"
        initialDetail={sessionADetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "inject-stale" }));
    expect(screen.getByTestId("transport").textContent).toBe("polling");
    expect(screen.getByTestId("live-mode").textContent).toBe("backoff");
    expect(screen.getByTestId("error-message").textContent).toBe("stale-error");
    openStreamSpy.mockClear();

    rerender(
      <HookProbe
        pmSessionId="pm-b"
        initialDetail={sessionBDetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("session-id").textContent).toBe("pm-b");
    });
    expect(openStreamSpy).toHaveBeenCalled();
    const lastCall = openStreamSpy.mock.calls.at(-1);
    expect(lastCall?.[0]).toBe("run-b");
    expect(lastCall?.[1]).toEqual(
      expect.objectContaining({
        limit: 100,
        tail: true,
      }),
    );
    expect(screen.getByTestId("transport").textContent).toBe("sse");
    expect(screen.getByTestId("live-mode").textContent).toBe("running");
    expect(screen.getByTestId("error-message").textContent).toBe("none");

    openStreamSpy.mockRestore();
  });

  it("keeps live mode aligned when toggling live while SSE transport is active", async () => {
    const streams: Array<{
      onopen: null | (() => void);
      onmessage: null | (() => void);
      onerror: null | ((event?: Event) => void);
      close: () => void;
    }> = [];
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockImplementation(() => {
      const stream = {
        close: vi.fn(),
        onopen: null,
        onmessage: null,
        onerror: null,
      };
      streams.push(stream);
      return stream as unknown as EventSource;
    });

    const detail = {
      session: {
        pm_session_id: "pm-live",
        status: "active",
        latest_run_id: "run-live",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-live"],
    } as unknown as PmSessionDetailPayload;

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-live"
        initialDetail={detail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("transport").textContent).toBe("sse");
      expect(screen.getByTestId("live-mode").textContent).toBe("running");
    });

    rerender(
      <HookProbe
        pmSessionId="pm-live"
        initialDetail={detail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={false}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("live-mode").textContent).toBe("paused");
    });

    rerender(
      <HookProbe
        pmSessionId="pm-live"
        initialDetail={detail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    await waitFor(() => {
      expect(openStreamSpy).toHaveBeenCalled();
      expect(screen.getByTestId("transport").textContent).toBe("sse");
      expect(screen.getByTestId("live-mode").textContent).toBe("running");
    });

    const latestStream = streams.at(-1);
    latestStream?.onopen?.();
    await waitFor(() => {
      expect(screen.getByTestId("live-mode").textContent).toBe("running");
    });

    openStreamSpy.mockRestore();
  });

  it("treats reconnecting SSE EOF as non-failure but still degrades on real repeated stream errors", async () => {
    const feedback = vi.fn();
    const stream = {
      close: vi.fn(),
      onopen: null as null | (() => void),
      onmessage: null as null | (() => void),
      onerror: null as null | ((event?: Event) => void),
      readyState: 1,
    };
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockReturnValue(stream as unknown as EventSource);

    const detail = {
      session: {
        pm_session_id: "pm-eof",
        status: "active",
        latest_run_id: "run-eof",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-eof"],
    } as unknown as PmSessionDetailPayload;

    render(
      <HookProbe
        pmSessionId="pm-eof"
        initialDetail={detail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
        onDrawerFeedback={feedback}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("transport").textContent).toBe("sse");
      expect(screen.getByTestId("live-mode").textContent).toBe("running");
    });

    await act(async () => {
      stream.onopen?.();
      stream.readyState = 0;
      stream.onerror?.({ currentTarget: stream } as unknown as Event);
    });

    await waitFor(() => {
      expect(screen.getByTestId("transport").textContent).toBe("sse");
      expect(screen.getByTestId("live-mode").textContent).toBe("running");
    });
    expect(feedback).not.toHaveBeenCalledWith(expect.stringContaining("Repeated SSE failures"));

    await act(async () => {
      stream.readyState = -1;
      stream.onerror?.();
      stream.onerror?.();
      stream.onerror?.();
    });

    await waitFor(() => {
      expect(screen.getByTestId("transport").textContent).toBe("polling");
      expect(screen.getByTestId("live-mode").textContent).toBe("backoff");
    });
    expect(feedback).toHaveBeenCalledWith("Repeated SSE failures detected. Switched to polling automatically.");

    openStreamSpy.mockRestore();
  });

  it("aborts in-flight refresh requests when switching session id", async () => {
    const observedSignals: AbortSignal[] = [];
    const pendingBySignal = (_id: string, options?: { signal?: AbortSignal }) =>
      new Promise<unknown>((_resolve, reject) => {
        const signal = options?.signal;
        if (signal) {
          observedSignals.push(signal);
          if (signal.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        }
      });
    const stream = {
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onerror: null,
    } as unknown as EventSource;
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockReturnValue(stream);
    const fetchPmSessionSpy = vi
      .spyOn(api, "fetchPmSession")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionEventsSpy = vi
      .spyOn(api, "fetchPmSessionEvents")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionConversationGraphSpy = vi
      .spyOn(api, "fetchPmSessionConversationGraph")
      .mockImplementation((pmSessionId, _params, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionMetricsSpy = vi
      .spyOn(api, "fetchPmSessionMetrics")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);

    const sessionADetail = {
      session: {
        pm_session_id: "pm-a",
        status: "active",
        latest_run_id: "run-a",
        updated_at: "2026-03-01T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-a"],
    } as unknown as PmSessionDetailPayload;
    const sessionBDetail = {
      session: {
        pm_session_id: "pm-b",
        status: "active",
        latest_run_id: "run-b",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-b"],
    } as unknown as PmSessionDetailPayload;

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-a"
        initialDetail={sessionADetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "manual-refresh" }));
    await waitFor(() => {
      expect(observedSignals.length).toBe(4);
    });

    rerender(
      <HookProbe
        pmSessionId="pm-b"
        initialDetail={sessionBDetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );
    await waitFor(() => {
      expect(observedSignals.every((signal) => signal.aborted)).toBe(true);
    });

    openStreamSpy.mockRestore();
    fetchPmSessionSpy.mockRestore();
    fetchPmSessionEventsSpy.mockRestore();
    fetchPmSessionConversationGraphSpy.mockRestore();
    fetchPmSessionMetricsSpy.mockRestore();
  });

  it("resets refreshing to false after session switch aborts previous refresh", async () => {
    const pendingBySignal = (_id: string, options?: { signal?: AbortSignal }) =>
      new Promise<unknown>((_resolve, reject) => {
        const signal = options?.signal;
        if (!signal) {
          return;
        }
        if (signal.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    const stream = {
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onerror: null,
    } as unknown as EventSource;
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockReturnValue(stream);
    const fetchPmSessionSpy = vi
      .spyOn(api, "fetchPmSession")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionEventsSpy = vi
      .spyOn(api, "fetchPmSessionEvents")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionConversationGraphSpy = vi
      .spyOn(api, "fetchPmSessionConversationGraph")
      .mockImplementation((pmSessionId, _params, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);
    const fetchPmSessionMetricsSpy = vi
      .spyOn(api, "fetchPmSessionMetrics")
      .mockImplementation((pmSessionId, options) => pendingBySignal(pmSessionId, options as { signal?: AbortSignal }) as never);

    const sessionADetail = {
      session: {
        pm_session_id: "pm-a",
        status: "active",
        latest_run_id: "run-a",
        updated_at: "2026-03-01T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-a"],
    } as unknown as PmSessionDetailPayload;
    const sessionBDetail = {
      session: {
        pm_session_id: "pm-b",
        status: "active",
        latest_run_id: "run-b",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-b"],
    } as unknown as PmSessionDetailPayload;

    const { rerender } = render(
      <HookProbe
        pmSessionId="pm-a"
        initialDetail={sessionADetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "manual-refresh" }));
    await waitFor(() => {
      expect(screen.getByTestId("refreshing").textContent).toBe("true");
    });

    rerender(
      <HookProbe
        pmSessionId="pm-b"
        initialDetail={sessionBDetail}
        initialEvents={[]}
        initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
        initialMetrics={{} as PmSessionMetricsPayload}
        liveEnabled={true}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("session-id").textContent).toBe("pm-b");
      expect(screen.getByTestId("refreshing").textContent).toBe("false");
    });

    openStreamSpy.mockRestore();
    fetchPmSessionSpy.mockRestore();
    fetchPmSessionEventsSpy.mockRestore();
    fetchPmSessionConversationGraphSpy.mockRestore();
    fetchPmSessionMetricsSpy.mockRestore();
  });

  it("cleans SSE merge timer on unmount to prevent post-unmount refresh", async () => {
    vi.useFakeTimers();
    const close = vi.fn();
    let streamHandlers: {
      onopen: null | (() => void);
      onmessage: null | (() => void);
      onerror: null | (() => void);
    } = { onopen: null, onmessage: null, onerror: null };
    const openStreamSpy = vi.spyOn(api, "openEventsStream").mockImplementation(() => {
      const stream = {
        close,
        onopen: null as null | (() => void),
        onmessage: null as null | (() => void),
        onerror: null as null | (() => void),
      };
      streamHandlers = stream;
      return stream as unknown as EventSource;
    });
    const fetchPmSessionSpy = vi.spyOn(api, "fetchPmSession");
    const fetchPmSessionEventsSpy = vi.spyOn(api, "fetchPmSessionEvents");
    const fetchPmSessionConversationGraphSpy = vi.spyOn(api, "fetchPmSessionConversationGraph");
    const fetchPmSessionMetricsSpy = vi.spyOn(api, "fetchPmSessionMetrics");

    const detail = {
      session: {
        pm_session_id: "pm-sse",
        status: "active",
        latest_run_id: "run-sse",
        updated_at: "2026-03-02T00:00:00Z",
      },
      runs: [],
      run_ids: ["run-sse"],
    } as unknown as PmSessionDetailPayload;

    try {
      const { unmount } = render(
        <HookProbe
          pmSessionId="pm-sse"
          initialDetail={detail}
          initialEvents={[]}
          initialGraph={{ window: "24h" } as PmSessionConversationGraphPayload}
          initialMetrics={{} as PmSessionMetricsPayload}
          liveEnabled={true}
        />,
      );
      expect(screen.getByTestId("transport").textContent).toBe("sse");

      streamHandlers.onmessage?.();
      unmount();
      vi.advanceTimersByTime(1200);

      expect(close).toHaveBeenCalled();
      expect(fetchPmSessionSpy).not.toHaveBeenCalled();
      expect(fetchPmSessionEventsSpy).not.toHaveBeenCalled();
      expect(fetchPmSessionConversationGraphSpy).not.toHaveBeenCalled();
      expect(fetchPmSessionMetricsSpy).not.toHaveBeenCalled();
    } finally {
      openStreamSpy.mockRestore();
      fetchPmSessionSpy.mockRestore();
      fetchPmSessionEventsSpy.mockRestore();
      fetchPmSessionConversationGraphSpy.mockRestore();
      fetchPmSessionMetricsSpy.mockRestore();
      vi.useRealTimers();
    }
  });

  it("hydrates and persists drawer preferences when testMode is disabled", async () => {
    const collapsedStorageKey = "openvibecoding.test.drawer.collapsed";
    const pinnedStorageKey = "openvibecoding.test.drawer.pinned";
    window.localStorage.setItem(collapsedStorageKey, "1");
    window.localStorage.setItem(pinnedStorageKey, "0");

    const { result } = renderHook(() =>
      useDrawerPreferences({
        collapsedStorageKey,
        pinnedStorageKey,
        testMode: false,
      }),
    );

    await waitFor(() => {
      expect(result.current.drawerCollapsed).toBe(true);
      expect(result.current.drawerPinned).toBe(false);
    });

    act(() => {
      result.current.setDrawerCollapsed(false);
      result.current.setDrawerPinned(true);
    });

    await waitFor(() => {
      expect(window.localStorage.getItem(collapsedStorageKey)).toBe("0");
      expect(window.localStorage.getItem(pinnedStorageKey)).toBe("1");
    });
  });

  it("keeps default drawer preferences when testMode is enabled", async () => {
    const collapsedStorageKey = "openvibecoding.test.drawer.collapsed.default";
    const pinnedStorageKey = "openvibecoding.test.drawer.pinned.default";
    window.localStorage.setItem(collapsedStorageKey, "0");
    window.localStorage.setItem(pinnedStorageKey, "0");

    const { result } = renderHook(() =>
      useDrawerPreferences({
        collapsedStorageKey,
        pinnedStorageKey,
        testMode: true,
      }),
    );

    await waitFor(() => {
      expect(result.current.drawerCollapsed).toBe(true);
      expect(result.current.drawerPinned).toBe(true);
    });
  });
});
