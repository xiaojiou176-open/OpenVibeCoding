import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CTSessionDetailPage } from "./CTSessionDetailPage";

vi.mock("../lib/api", () => ({
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
  postPmSessionMessage: vi.fn(),
  openEventsStream: vi.fn(),
}));

import {
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
  openEventsStream,
  postPmSessionMessage,
} from "../lib/api";

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function mockHealthyState() {
  vi.mocked(fetchPmSession).mockResolvedValue({
    session: { pm_session_id: "pm-1", status: "active", latest_run_id: "run-1" },
    runs: [
      {
        run_id: "run-1",
        status: "running",
        failure_reason: "",
        current_role: "TECH_LEAD",
        blocked: false,
      },
    ],
  } as any);
  vi.mocked(fetchPmSessionEvents).mockResolvedValue([
    { event: "CHAIN_DONE", ts: "2026-02-20T01:00:00Z", detail: "ok" },
    { event: "CHAIN_FAIL", ts: "2026-02-20T00:00:00Z", detail: "bad" },
  ] as any);
  vi.mocked(fetchPmSessionConversationGraph).mockResolvedValue({
    nodes: [{ role: "PM", message_count: 3 }],
    edges: [{ from: "PM", to: "TECH_LEAD" }],
  } as any);
  vi.mocked(fetchPmSessionMetrics).mockResolvedValue({
    run_count: 3,
    running_runs: 1,
    failed_runs: 1,
    blocked_runs: 0,
    failure_rate: 0.33,
    mttr_seconds: 42.2,
  } as any);
  vi.mocked(openEventsStream).mockReturnValue({ close: vi.fn() } as any);
  vi.mocked(postPmSessionMessage).mockResolvedValue({ ok: true } as any);
}

describe("CTSessionDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHealthyState();
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  it("renders metrics, graph, run table and timeline details", async () => {
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Session detail" })).toBeInTheDocument();
    expect(screen.getByText("Run count")).toBeInTheDocument();
    expect(screen.getByText("Conversation flow")).toBeInTheDocument();
    expect(screen.getByText("Event timeline")).toBeInTheDocument();
    expect(screen.getByText("Run status list for the current session")).toBeInTheDocument();
    expect(screen.getByText("CHAIN_DONE")).toBeInTheDocument();

    const buttons = screen.getAllByTestId("ct-session-event-button");
    fireEvent.click(buttons[0]);
    expect(buttons[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/"event": "CHAIN_DONE"/)).toBeInTheDocument();
    expect(within(buttons[0]).queryByText(/"event": "CHAIN_DONE"/)).toBeNull();
  });

  it("renders zh-CN shell copy when locale is passed", async () => {
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} locale="zh-CN" />);

    expect(await screen.findByRole("heading", { name: "会话详情" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "< 返回会话总览" })).toBeInTheDocument();
    expect(screen.getByText("本会话运行")).toBeInTheDocument();
    expect(screen.getByText("事件时间线")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂停实时" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "发送给 PM 的消息" })).toBeInTheDocument();
  });

  it("supports PM message send success path by button and enter key", async () => {
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });

    await user.type(textarea, "first message");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(postPmSessionMessage).toHaveBeenCalledWith(
        "pm-1",
        expect.objectContaining({ message: "first message", from_role: "PM" }),
      );
    });
    expect(screen.getByText("Message sent.")).toBeInTheDocument();

    await user.type(textarea, "second message{enter}");
    await waitFor(() => {
      expect(postPmSessionMessage).toHaveBeenCalledTimes(2);
    });
  });

  it("blocks duplicate send triggers while message is in-flight", async () => {
    const pending = createDeferred<{ ok: true }>();
    vi.mocked(postPmSessionMessage).mockImplementation(() => pending.promise as any);
    const user = userEvent.setup();

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });
    await user.type(textarea, "dedupe send");

    await user.type(textarea, "{enter}");
    await waitFor(() => {
      expect(postPmSessionMessage).toHaveBeenCalledTimes(1);
    });

    await user.type(textarea, "{enter}");
    const sendingButton = screen.getByRole("button", { name: "Sending..." });
    expect(sendingButton).toBeDisabled();
    await user.click(sendingButton);
    expect(postPmSessionMessage).toHaveBeenCalledTimes(1);

    pending.resolve({ ok: true });
    expect(await screen.findByText("Message sent.")).toBeInTheDocument();
  });

  it("shows send failure message and keeps draft when posting fails", async () => {
    vi.mocked(postPmSessionMessage).mockRejectedValue(new Error("发送失败: 网络错误"));
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });
    await user.type(textarea, "need retry");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("发送失败: 网络错误")).toBeInTheDocument();
    expect((textarea as HTMLTextAreaElement).value).toBe("need retry");
  });

  it("falls back to degraded mode when all refresh endpoints fail", async () => {
    vi.mocked(fetchPmSession).mockRejectedValue(new Error("d"));
    vi.mocked(fetchPmSessionEvents).mockRejectedValue(new Error("e"));
    vi.mocked(fetchPmSessionConversationGraph).mockRejectedValue(new Error("g"));
    vi.mocked(fetchPmSessionMetrics).mockRejectedValue(new Error("m"));
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    expect(await screen.findByText("All requests failed")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("switches to polling after repeated SSE errors", async () => {
    let streamHandlers: { onerror?: (() => void) | null; onopen?: (() => void) | null } = {};
    vi.mocked(openEventsStream).mockImplementation(() => {
      const stream = {
        onopen: null as null | (() => void),
        onmessage: null as null | (() => void),
        onerror: null as null | (() => void),
        close: vi.fn(),
      };
      streamHandlers = stream;
      return stream as any;
    });
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });
    streamHandlers.onopen?.();
    if (streamHandlers.onerror) {
      streamHandlers.onerror();
      streamHandlers.onerror();
      streamHandlers.onerror();
    }
    await waitFor(() => {
      expect(screen.getByText("POLLING")).toBeInTheDocument();
    });
  });

  it("supports hotkeys and utility actions", async () => {
    const onBack = vi.fn();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={onBack} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });
    fireEvent.keyDown(window, { altKey: true, key: "m" });
    expect(textarea).toHaveFocus();

    fireEvent.keyDown(window, { altKey: true, key: "l" });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Resume live" })).toBeInTheDocument();
    });
    const countBefore = vi.mocked(fetchPmSession).mock.calls.length;
    fireEvent.keyDown(window, { altKey: true, key: "r" });
    await waitFor(() => {
      expect(vi.mocked(fetchPmSession).mock.calls.length).toBeGreaterThan(countBefore);
    });
    fireEvent.click(screen.getByRole("button", { name: /Back to session overview/ }));
    expect(onBack).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Open web session analysis" }));
    expect(window.open).toHaveBeenCalledTimes(1);
  });

  it("shows partial degraded refresh and stopped state for terminal session", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "archived", latest_run_id: "run-1" },
      runs: [],
    } as any);
    vi.mocked(fetchPmSessionEvents).mockRejectedValue(new Error("events down"));
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    expect(await screen.findByText("Partial refresh degraded (1/4 failed)")).toBeInTheDocument();
    expect(screen.getByText("Stopped")).toBeInTheDocument();
    expect(screen.getByText("No runs recorded yet.")).toBeInTheDocument();
  });

  it("supports event filter empty-state and event detail toggle collapse", async () => {
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });

    const buttons = screen.getAllByTestId("ct-session-event-button");
    fireEvent.click(buttons[0]);
    expect(buttons[0]).toHaveAttribute("aria-expanded", "true");
    const detailsId = buttons[0].getAttribute("aria-controls");
    expect(detailsId).not.toBeNull();
    expect(document.getElementById(detailsId as string)).not.toBeNull();
    fireEvent.click(buttons[0]);
    expect(buttons[0]).toHaveAttribute("aria-expanded", "false");

    await user.type(screen.getByRole("textbox", { name: "Filter events" }), "not-exists");
    expect(screen.getByText("No events yet.")).toBeInTheDocument();
  });

  it("uses slug-safe id for event filter input", async () => {
    render(<CTSessionDetailPage sessionId="pm/1 demo" onBack={vi.fn()} />);
    const filterInput = await screen.findByRole("textbox", { name: "Filter events" });
    expect(filterInput).toHaveAttribute("id", "ct-session-event-filter-pm-1-demo");
  });

  it("ignores Alt+L and Alt+R while editing, and keeps draft on Shift+Enter/IME Enter", async () => {
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });
    await user.type(textarea, "draft");

    fireEvent.keyDown(textarea, { altKey: true, key: "l" });
    expect(screen.getByRole("button", { name: "Pause live" })).toBeInTheDocument();

    const countBefore = vi.mocked(fetchPmSession).mock.calls.length;
    fireEvent.keyDown(textarea, { altKey: true, key: "r" });
    await waitFor(() => {
      expect(vi.mocked(fetchPmSession).mock.calls.length).toBe(countBefore);
    });

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(vi.mocked(postPmSessionMessage)).not.toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toBe("draft");

    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false, isComposing: true });
    expect(vi.mocked(postPmSessionMessage)).not.toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toBe("draft");
  });

  it("toggles live state by toolbar and supports manual refresh button", async () => {
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });

    const pauseBtn = screen.getByRole("button", { name: "Pause live" });
    await user.click(pauseBtn);
    expect(await screen.findByRole("button", { name: "Resume live" })).toBeInTheDocument();

    const countBefore = vi.mocked(fetchPmSession).mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Refresh now" }));
    await waitFor(() => {
      expect(vi.mocked(fetchPmSession).mock.calls.length).toBeGreaterThan(countBefore);
    });
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });

  it("keeps polling when latest run id is empty", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "   " },
      runs: [],
    } as any);
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });
    await waitFor(() => {
      expect(screen.getByText("POLLING")).toBeInTheDocument();
    });
    expect(openEventsStream).not.toHaveBeenCalled();
  });

  it("falls back to polling when opening SSE throws", async () => {
    vi.clearAllMocks();
    mockHealthyState();
    vi.mocked(openEventsStream).mockImplementation(() => {
      throw new Error("sse unavailable");
    });
    render(<CTSessionDetailPage sessionId="pm-2" onBack={vi.fn()} />);
    await screen.findAllByRole("heading", { name: "Session detail" });
    await waitFor(() => {
      expect(screen.getByText("POLLING")).toBeInTheDocument();
    });
  });

  it("does not send empty message and keeps send button disabled for whitespace", async () => {
    const user = userEvent.setup();
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });
    const sendBtn = screen.getByRole("button", { name: "Send" });
    expect(sendBtn).toBeDisabled();

    await user.type(textarea, "   ");
    expect(sendBtn).toBeDisabled();
    await user.click(sendBtn);
    await user.type(textarea, "{enter}");
    expect(sendBtn).toBeDisabled();
    expect(postPmSessionMessage).not.toHaveBeenCalled();
  });

  it("ignores shortcut when modifier keys include ctrl/meta/shift", async () => {
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    const textarea = await screen.findByRole("textbox", { name: "Message for PM" });

    fireEvent.keyDown(window, { altKey: true, shiftKey: true, key: "m" });
    expect(textarea).not.toHaveFocus();

    fireEvent.keyDown(window, { altKey: true, ctrlKey: true, key: "r" });
    expect(textarea).not.toHaveFocus();
  });

  it("opens web session analysis with mapped web port and renders blocked/role fallback run row", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "run-1" },
      runs: [
        {
          run_id: "run-2",
          status: "blocked",
          failure_reason: "",
          role_step: "REVIEWER",
          blocked: true,
        },
      ],
    } as any);

    const originalLocation = window.location;
    try {
      Object.defineProperty(window, "location", {
        value: { ...originalLocation, protocol: "http:", hostname: "localhost", port: "1420" },
        configurable: true,
      });

      const user = userEvent.setup();
      render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
      await screen.findByText("Blocked");
      expect(screen.getByText("REVIEWER")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Open web session analysis" }));
      expect(window.open).toHaveBeenCalledWith(
        "http://localhost:3100/command-tower/sessions/pm-1",
        "_blank",
        "noopener,noreferrer",
      );
    } finally {
      Object.defineProperty(window, "location", {
        value: originalLocation,
        configurable: true,
      });
    }
  });

  it("does not treat string 'false' blocked flag as blocked state", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "run-1" },
      runs: [
        {
          run_id: "run-3",
          status: "running",
          failure_reason: "",
          current_role: "WORKER",
          blocked: "false",
        },
      ],
    } as any);

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });
    const runRow = screen.getByText("run-3").closest("tr");
    expect(runRow).not.toBeNull();
    const runCells = within(runRow as HTMLTableRowElement).getAllByRole("cell");
    expect(runCells[4]).toHaveTextContent(/^\s*-\s*$/);
    expect(runCells[4]).not.toHaveTextContent("Blocked");
  });

  it("covers polling tick and mixed timestamp branches in event sorting", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "   " },
      runs: [],
    } as any);
    vi.mocked(fetchPmSessionEvents).mockResolvedValue([
      { event: "NUMERIC_TS", ts: 1700000001000, detail: "n" },
      { event: "STRING_TS", ts: "1700000000000", detail: "s" },
      { event: "BAD_TS", ts: "bad-time", detail: "b" },
      { event: "MISSING_TS", detail: "m" } as any,
    ] as any);

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });
    expect(await screen.findByText("NUMERIC_TS")).toBeInTheDocument();
    expect(await screen.findByText("MISSING_TS")).toBeInTheDocument();

    const before = vi.mocked(fetchPmSession).mock.calls.length;
    await waitFor(() => {
      expect(vi.mocked(fetchPmSession).mock.calls.length).toBeGreaterThan(before);
    }, { timeout: 2600 });
  });

  it("passes abort signal and timeout controls to refresh endpoints", async () => {
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });

    const sessionArgs = vi.mocked(fetchPmSession).mock.calls[0];
    const eventsArgs = vi.mocked(fetchPmSessionEvents).mock.calls[0];
    const graphArgs = vi.mocked(fetchPmSessionConversationGraph).mock.calls[0];
    const metricsArgs = vi.mocked(fetchPmSessionMetrics).mock.calls[0];

    expect(sessionArgs[0]).toBe("pm-1");
    expect(sessionArgs[1]).toMatchObject({ timeoutMs: 6000 });
    expect(sessionArgs[1]?.signal).toBeInstanceOf(AbortSignal);

    expect(eventsArgs[0]).toBe("pm-1");
    expect(eventsArgs[1]).toMatchObject({ limit: 500, tail: true, timeoutMs: 6000 });
    expect(eventsArgs[1]?.signal).toBeInstanceOf(AbortSignal);

    expect(graphArgs[0]).toBe("pm-1");
    expect(graphArgs[1]).toBe("24h");
    expect(graphArgs[2]).toMatchObject({ timeoutMs: 6000 });
    expect(graphArgs[2]?.signal).toBeInstanceOf(AbortSignal);

    expect(metricsArgs[0]).toBe("pm-1");
    expect(metricsArgs[1]).toMatchObject({ timeoutMs: 6000 });
    expect(metricsArgs[1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("keeps SSE before fail limit and schedules merged refresh on message", async () => {
    const close = vi.fn();
    let handlers: {
      onopen: null | (() => void);
      onmessage: null | (() => void);
      onerror: null | (() => void);
    } = { onopen: null, onmessage: null, onerror: null };
    vi.mocked(openEventsStream).mockImplementation(() => {
      const stream = {
        onopen: null as null | (() => void),
        onmessage: null as null | (() => void),
        onerror: null as null | (() => void),
        close,
      };
      handlers = stream;
      return stream as any;
    });

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await screen.findByRole("heading", { name: "Session detail" });
    await act(async () => {
      handlers.onopen?.();
    });
    await waitFor(() => {
      expect(screen.getByText("SSE")).toBeInTheDocument();
    });

    const before = vi.mocked(fetchPmSession).mock.calls.length;
    await act(async () => {
      handlers.onmessage?.();
    });
    await waitFor(() => {
      expect(vi.mocked(fetchPmSession).mock.calls.length).toBeGreaterThan(before);
    }, { timeout: 1800 });

    await act(async () => {
      handlers.onerror?.();
    });
    await waitFor(() => {
      expect(screen.getByText("SSE")).toBeInTheDocument();
    });
    expect(close).not.toHaveBeenCalled();
  });
});
