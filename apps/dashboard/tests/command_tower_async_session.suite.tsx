import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MockEventSource,
  baseEvents,
  baseGraph,
  baseMetrics,
  baseSessionDetail,
  getCommandTowerAsyncMocks,
  setupCommandTowerAsyncDefaultMocks,
  teardownCommandTowerAsyncMocks,
} from "./command_tower_async.shared";
import CommandTowerSessionLive from "../components/command-tower/CommandTowerSessionLive";
import type { PmSessionDetailPayload, PmSessionSummary } from "../lib/types";

describe("command tower async hardening (session)", () => {
  const mocks = getCommandTowerAsyncMocks();
  const {
    mockFetchPmSession,
    mockFetchPmSessionConversationGraph,
    mockFetchPmSessionEvents,
    mockFetchPmSessionMetrics,
    mockOpenEventsStream,
    mockPostPmSessionMessage,
  } = mocks;
  const pauseLiveButtonName = /Pause Live|Pause live refresh|Pause auto refresh/;
  const resumeLiveButtonName = /Resume Live|Resume live refresh|Resume auto refresh/;
  const statusContains = (pattern: RegExp): boolean =>
    screen.queryAllByRole("status").some((node) => pattern.test(node.textContent || ""));
  const hasBackoffSignal = (): boolean =>
    statusContains(/backoff/i) || screen.queryAllByText(/backoff/i).length > 0;
  async function ensureDrawerExpanded() {
    const drawerLayoutGroup = screen.getByRole("group", { name: "Drawer layout controls" });
    const toggleButton = within(drawerLayoutGroup).getByRole("button", { name: /Collapse drawer|Expand drawer/ });
    if (toggleButton.getAttribute("aria-pressed") !== "true") {
      return;
    }
    await act(async () => {
      fireEvent.click(toggleButton);
      await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: "Collapse drawer" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Live status/i)).toBeInTheDocument();
  }
  async function enableAdvancedMode() {
    const toggle = screen.queryByRole("button", { name: /Expand expert info|Expand advanced drawer/ });
    if (toggle) {
      fireEvent.click(toggle);
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByRole("button", { name: /Collapse expert info|Collapse advanced drawer/ })).toBeInTheDocument();
    }
  }

  beforeEach(() => {
    setupCommandTowerAsyncDefaultMocks(mocks);
  });

  afterEach(() => {
    teardownCommandTowerAsyncMocks();
  });

  it("stops session live refresh when session is archived", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-archived"
        initialDetail={baseSessionDetail("archived", "run-archived")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    const liveControlGroup = screen.getByRole("group", { name: "Live controls" });
    expect(within(liveControlGroup).getByRole("button", { name: pauseLiveButtonName })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(mockFetchPmSession).not.toHaveBeenCalled();
    expect(mockFetchPmSessionEvents).not.toHaveBeenCalled();
    expect(mockFetchPmSessionConversationGraph).not.toHaveBeenCalled();
    expect(mockFetchPmSessionMetrics).not.toHaveBeenCalled();
    expect(mockOpenEventsStream).not.toHaveBeenCalled();
  });

  it("keeps run/graph/timeline panels visible by tab and toggles advanced drawer on demand", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-mode"
        initialDetail={baseSessionDetail("active", "run-mode")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    const drawerLayoutGroup = screen.getByRole("group", { name: "Drawer layout controls" });
    const modeButton = within(drawerLayoutGroup).getByRole("button", { name: /Collapse drawer|Expand drawer/ });
    expect(modeButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("ct-session-panel-runs")).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-timeline")).toBeNull();
    expect(screen.getByLabelText("Context operations drawer")).toBeInTheDocument();
    expect(screen.queryByText(/Live status/i)).toBeNull();

    fireEvent.click(screen.getByTestId("ct-session-tab-timeline"));
    expect(screen.getByTestId("ct-session-panel-timeline")).toBeVisible();
    expect(screen.queryByTestId("ct-session-panel-runs")).toBeNull();

    fireEvent.click(modeButton);
    expect(await screen.findByRole("button", { name: "Collapse drawer" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Live status/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Collapse drawer" }));
    expect(await screen.findByRole("button", { name: "Expand drawer" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText(/Live status/i)).toBeNull();
  });

  it("exposes drawer controls with explicit aria contracts", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-a11y"
        initialDetail={baseSessionDetail("active", "run-a11y")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();
    await ensureDrawerExpanded();

    const liveControlGroup = screen.getByRole("group", { name: "Live controls" });
    const pauseButton = within(liveControlGroup).getByRole("button", { name: pauseLiveButtonName });
    const refreshButton = within(liveControlGroup).getByRole("button", { name: /Manual refresh/i });
    const focusButton = within(liveControlGroup).getByRole("button", { name: /Focus PM message input/i });

    expect(pauseButton.getAttribute("aria-controls") || "").toContain("session-main-region-pm-a11y");
    expect(pauseButton.getAttribute("aria-controls") || "").toContain("session-live-status-pm-a11y");
    expect(refreshButton.getAttribute("aria-controls") || "").toContain("session-main-region-pm-a11y");
    expect(refreshButton.getAttribute("aria-controls") || "").toContain("session-live-status-pm-a11y");
    expect(focusButton).toHaveAttribute("aria-controls", "pm-session-message-input-pm-a11y");

    const liveStatus = document.getElementById("session-live-status-pm-a11y");
    expect(liveStatus).not.toBeNull();
    expect(liveStatus).toHaveAttribute("role", "status");
    expect(liveStatus).toHaveAttribute("aria-live", "polite");
    expect(liveStatus?.textContent || "").toMatch(/Transport:/);
    expect(liveStatus?.textContent || "").toMatch(/SSE live stream|Polling fallback/);
  });

  it("coalesces burst SSE messages into throttled refresh calls", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-02-09T10:00:00Z"));

    const stream = new MockEventSource();
    mockOpenEventsStream.mockImplementation(() => stream as unknown as EventSource);

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-sse"
        initialDetail={baseSessionDetail("active", "run-sse")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    expect(mockOpenEventsStream).toHaveBeenCalledTimes(1);

    await act(async () => {
      stream.onmessage?.({} as MessageEvent);
      stream.onmessage?.({} as MessageEvent);
      stream.onmessage?.({} as MessageEvent);
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(mockFetchPmSession).toHaveBeenCalledTimes(1);

    await act(async () => {
      stream.onmessage?.({} as MessageEvent);
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(mockFetchPmSession).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(mockFetchPmSession).toHaveBeenCalledTimes(2);
  });

  it("does not run polling loop while SSE transport stays healthy", async () => {
    vi.useFakeTimers();

    const stream = new MockEventSource();
    mockOpenEventsStream.mockImplementation(() => stream as unknown as EventSource);

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-sse-only"
        initialDetail={baseSessionDetail("active", "run-sse-only")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    mockFetchPmSession.mockClear();
    mockFetchPmSessionEvents.mockClear();
    mockFetchPmSessionConversationGraph.mockClear();
    mockFetchPmSessionMetrics.mockClear();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(mockFetchPmSession).not.toHaveBeenCalled();
    expect(mockFetchPmSessionEvents).not.toHaveBeenCalled();
    expect(mockFetchPmSessionConversationGraph).not.toHaveBeenCalled();
    expect(mockFetchPmSessionMetrics).not.toHaveBeenCalled();
  });

  it("keeps session live alive on partial allSettled failure and classifies auth error", async () => {
    vi.useFakeTimers();

    mockFetchPmSession.mockResolvedValue(baseSessionDetail("active", ""));
    mockFetchPmSessionEvents.mockRejectedValue(new Error("401 unauthorized"));
    mockFetchPmSessionConversationGraph.mockResolvedValue(baseGraph("24h"));
    mockFetchPmSessionMetrics.mockResolvedValue(baseMetrics());

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-partial"
        initialDetail={baseSessionDetail("active", "")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph("24h")}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    await enableAdvancedMode();

    expect(mockFetchPmSession).toHaveBeenCalled();
    const alertRegion = screen.getByRole("alert");
    expect(alertRegion).toHaveTextContent(/401 unauthorized/i);
    expect(alertRegion).toHaveTextContent(/auth/i);
    expect(statusContains(/polling/i)).toBe(true);
  });

  it("covers session polling fallback when stream open fails and toggles live button", async () => {
    mockOpenEventsStream.mockImplementation(() => {
      throw new Error("stream init failed");
    });

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-stream-fail"
        initialDetail={baseSessionDetail("active", "run-stream-fail")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();

    await waitFor(() => {
      expect(statusContains(/polling/i)).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByText(/Failed to open the SSE channel|Polling is active right now/)).toBeInTheDocument();
    });

    const liveControlGroup = screen.getByRole("group", { name: "Live controls" });
    fireEvent.click(within(liveControlGroup).getByRole("button", { name: pauseLiveButtonName }));
    expect(within(liveControlGroup).getByRole("button", { name: resumeLiveButtonName })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("covers main action click handlers and Alt+R failure feedback branch", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-main-actions"
        initialDetail={baseSessionDetail("active", "run-main-actions")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });

    const mainActionGroup = screen.getByRole("group", { name: "Session primary actions" });
    const mainLiveToggle = within(mainActionGroup).getByRole("button", { name: /Pause auto refresh|Resume auto refresh/ });
    fireEvent.click(mainLiveToggle);
    expect(within(mainActionGroup).getByRole("button", { name: /Resume auto refresh|Pause auto refresh/ })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    mockFetchPmSession.mockClear();
    fireEvent.click(within(mainActionGroup).getByRole("button", { name: /Refresh progress|Refresh latest progress/ }));
    await waitFor(() => {
      expect(mockFetchPmSession).toHaveBeenCalled();
    });

    mockFetchPmSession.mockRejectedValueOnce(new Error("shortcut-detail-fail"));
    mockFetchPmSessionEvents.mockRejectedValueOnce(new Error("shortcut-events-fail"));
    mockFetchPmSessionConversationGraph.mockRejectedValueOnce(new Error("shortcut-graph-fail"));
    mockFetchPmSessionMetrics.mockRejectedValueOnce(new Error("shortcut-metrics-fail"));

    fireEvent.keyDown(window, { key: "r", altKey: true });
    await waitFor(() => {
      expect(screen.getAllByText(/Manual refresh failed:/).length).toBeGreaterThan(0);
    });
  });

  it("supports keyboard shortcuts for toggle, refresh, drawer, and composer focus", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-shortcuts"
        initialDetail={baseSessionDetail("active", "run-shortcuts")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();
    await ensureDrawerExpanded();

    const input = screen.getByRole("textbox", { name: /PM session message input/i });
    expect(input).not.toHaveFocus();

    fireEvent.keyDown(window, { key: "m", altKey: true });
    expect(input).toHaveFocus();

    fireEvent.keyDown(window, { key: "l", altKey: true });
    const resumeButtons = screen.getAllByRole("button", { name: resumeLiveButtonName });
    expect(resumeButtons.every((button) => button.getAttribute("aria-pressed") === "false")).toBe(true);

    fireEvent.keyDown(window, { key: "d", altKey: true });
    expect(screen.queryByText(/Live status/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Expand drawer" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.keyDown(window, { key: "p", altKey: true });
    expect(screen.getByRole("button", { name: "Pin drawer" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.keyDown(window, { key: "d", altKey: true });
    expect(screen.getByText(/Live status/i)).toBeInTheDocument();

    mockFetchPmSession.mockClear();
    fireEvent.keyDown(window, { key: "r", altKey: true });
    await waitFor(() => {
      expect(mockFetchPmSession).toHaveBeenCalled();
    });
  });

  it("does not send PM message when Enter is pressed during IME composing", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-ime"
        initialDetail={baseSessionDetail("active", "run-ime")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();
    await ensureDrawerExpanded();

    const input = screen.getByRole("textbox", { name: /PM session message input/i });
    fireEvent.change(input, { target: { value: "ime-composing-message" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false, isComposing: true });

    expect(mockPostPmSessionMessage).not.toHaveBeenCalled();
  });

  it("covers session message send empty/success/failure branches and editable shortcut guard", async () => {
    render(
      <CommandTowerSessionLive
        pmSessionId="pm-message-branches"
        initialDetail={baseSessionDetail("active", "run-message-branches")}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();
    await ensureDrawerExpanded();

    const input = screen.getByRole("textbox", { name: /PM session message input/i });
    const sendButton = screen.getByRole("button", { name: "Send to session" });

    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.click(sendButton);
    expect(mockPostPmSessionMessage).not.toHaveBeenCalled();
    expect(screen.getByText("Message cannot be empty")).toBeInTheDocument();

    mockPostPmSessionMessage.mockResolvedValueOnce({ ok: true } as never);
    fireEvent.change(input, { target: { value: "Please sync the latest progress" } });
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(mockPostPmSessionMessage).toHaveBeenCalledWith(
        "pm-message-branches",
        expect.objectContaining({
          message: "Please sync the latest progress",
          from_role: "PM",
          to_role: "TECH_LEAD",
          kind: "chat",
        }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText("Message sent")).toBeInTheDocument();
    });

    mockPostPmSessionMessage.mockRejectedValueOnce(new Error("message failed"));
    fireEvent.change(input, { target: { value: "Try one more time" } });
    fireEvent.click(sendButton);
    await waitFor(() => {
      expect(screen.getByText("message failed")).toBeInTheDocument();
    });

    const pauseButton = within(screen.getByRole("group", { name: /Session primary actions/i })).getByRole("button", {
      name: pauseLiveButtonName,
    });
    expect(pauseButton).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(input, { key: "l", altKey: true });
    expect(pauseButton).toHaveAttribute("aria-pressed", "true");
  });

  it("covers session fallback fields and blocked yes branch", async () => {
    const detail = baseSessionDetail("active", "run-fallback-fields");
    detail.runs = [
      {
        run_id: "run-fallback-fields",
        status: "RUNNING",
        blocked: true,
        current_role: "",
        current_step: "",
        last_event_ts: "",
        finished_at: "2026-02-09T10:01:00Z",
        created_at: "2026-02-09T10:00:00Z",
      },
    ] as unknown as PmSessionDetailPayload["runs"];

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-fallback-fields"
        initialDetail={detail}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();

    const fallbackRunLink = screen.getByRole("link", { name: "run-fallback-fields" });
    const fallbackRowText = fallbackRunLink.closest("tr")?.textContent || "";
    expect(fallbackRowText).toMatch(/2026-02-09T10:01:00Z/);
    expect(fallbackRowText).toMatch(/yes|true/i);
  });

  it("covers session run-table final fallback dashes", async () => {
    const detail = baseSessionDetail("active", "run-fallback-dash");
    detail.runs = [
      {
        run_id: "run-fallback-dash",
        status: "",
        blocked: false,
        current_role: "",
        current_step: "",
        last_event_ts: "",
        finished_at: "",
        created_at: "",
      },
    ] as unknown as PmSessionDetailPayload["runs"];

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-fallback-dash"
        initialDetail={detail}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();

    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });

  it("covers session all-refresh failure path and backoff mode", async () => {
    vi.useFakeTimers();

    mockFetchPmSession.mockRejectedValue("detail down");
    mockFetchPmSessionEvents.mockRejectedValue(new Error("events down"));
    mockFetchPmSessionConversationGraph.mockRejectedValue(new Error("graph down"));
    mockFetchPmSessionMetrics.mockRejectedValue(new Error("metrics down"));

    const initial = baseSessionDetail("active", "");
    initial.session.updated_at = "";
    initial.session.status = "" as unknown as PmSessionSummary["status"];

    render(
      <CommandTowerSessionLive
        pmSessionId="pm-all-fail"
        initialDetail={initial}
        initialEvents={baseEvents()}
        initialGraph={baseGraph()}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    await enableAdvancedMode();

    expect(hasBackoffSignal()).toBe(true);
    expect(screen.getByRole("alert").textContent || "").toMatch(/detail|events|graph|metrics/);
  });

  it("covers session polling options fallback and stream error branches", async () => {
    vi.useFakeTimers();

    const stream = new MockEventSource();
    mockOpenEventsStream.mockImplementation(() => stream as unknown as EventSource);

    const detail = baseSessionDetail("active", "run-stream-branch");
    detail.session.updated_at = "";
    mockFetchPmSession.mockResolvedValue(baseSessionDetail("active", "run-stream-branch"));

    const graph = baseGraph("24h");
    graph.window = "" as unknown as "24h";

    const { unmount } = render(
      <CommandTowerSessionLive
        pmSessionId="pm-stream-branch"
        initialDetail={detail}
        initialEvents={[]}
        initialGraph={graph}
        initialMetrics={baseMetrics()}
      />,
    );

    await act(async () => {
      await Promise.resolve();
    });
    await enableAdvancedMode();
    await ensureDrawerExpanded();

    await act(async () => {
      stream.onmessage?.({} as MessageEvent);
      await vi.advanceTimersByTimeAsync(400);
    });

    const eventCall = mockFetchPmSessionEvents.mock.calls.at(-1)?.[1] as
      | {
          since?: string;
          limit?: number;
        }
      | undefined;
    expect(eventCall).not.toBeUndefined();
    expect(eventCall?.since).toBeUndefined();
    expect(eventCall?.limit).toBe(800);

    const graphCall = mockFetchPmSessionConversationGraph.mock.calls.at(-1)?.[1] as
      | {
          window?: string;
        }
      | undefined;
    expect(graphCall?.window).toBe("24h");

    await act(async () => {
      stream.onmessage?.({} as MessageEvent);
      await vi.advanceTimersByTimeAsync(1);
      stream.onerror?.();
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(stream.close).not.toHaveBeenCalled();

    await act(async () => {
      stream.onerror?.();
      stream.onerror?.();
      await vi.advanceTimersByTimeAsync(1);
    });

    expect(stream.close).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Transport: Polling fallback/)).toBeInTheDocument();
    expect(screen.getAllByText(/Polling is active right now|Repeated SSE failures detected/).length).toBeGreaterThan(0);

    unmount();
    expect(stream.close).toHaveBeenCalled();
  });
});
