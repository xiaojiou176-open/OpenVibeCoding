import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { usePMIntakeView } from "../app/pm/hooks/usePMIntakeView";
import { usePMIntakeActions } from "../app/pm/hooks/usePMIntakeActions";
import { usePMIntakeData } from "../app/pm/hooks/usePMIntakeData";
import { buildTaskPackFieldStateForPack } from "../lib/types";
import type { TaskPackManifest } from "../lib/types";
import {
  answerIntake,
  createIntake,
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessions,
  fetchTaskPacks,
  runIntake,
} from "../lib/api";

vi.mock("../lib/api", () => ({
  answerIntake: vi.fn(),
  createIntake: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchTaskPacks: vi.fn(),
  runIntake: vi.fn(),
}));

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function createViewState(overrides: Record<string, unknown> = {}) {
  return {
    workspaceBound: true,
    intakeId: "",
    questions: [],
    runId: "",
    copyVariant: "a",
    chatFlowBusy: false,
    chatBusy: false,
    busy: false,
    chatHistoryBusy: false,
    liveRole: "TECH_LEAD",
    chatLog: [],
    progressFeed: [],
    plan: null,
    taskChain: null,
    sessionHistory: [],
    setHoveredChainRole: vi.fn(),
    activeChatSessionId: "",
    lastChatLengthRef: { current: 0 },
    chatStickToBottom: true,
    setChatStickToBottom: vi.fn(),
    setChatUnreadCount: vi.fn(),
    chatLogRef: { current: null },
    chatAbortRef: { current: null },
    chatInputRef: { current: { focus: vi.fn() } },
    chainPanelRef: { current: null },
    setChatError: vi.fn(),
    chatInput: "",
    setChatInput: vi.fn(),
    setChatNotice: vi.fn(),
    layoutMode: "dialog",
    setLayoutMode: vi.fn(),
    setTaskTemplate: vi.fn(),
    setNewsDigestTopic: vi.fn(),
    setNewsDigestSources: vi.fn(),
    setNewsDigestTimeRange: vi.fn(),
    setNewsDigestMaxResults: vi.fn(),
    ...overrides,
  };
}

function createViewActions(overrides: Record<string, unknown> = {}) {
  return {
    handleChatSend: vi.fn(),
    handleRun: vi.fn(),
    handleStartNewConversation: vi.fn(),
    ...overrides,
  };
}

describe("pm intake view hook branches", () => {
  it("covers primary stage transitions and stop-generation branches", () => {
    const setChatError = vi.fn();
    const setChatNotice = vi.fn();
    const setChatStickToBottom = vi.fn();
    const setChatUnreadCount = vi.fn();
    const scrollTo = vi.fn();
    const handleChatSend = vi.fn();
    const handleRun = vi.fn();

    const scenarios = [
      createViewState({ workspaceBound: false, setChatError }),
      createViewState({ workspaceBound: true, chatInput: "", setChatError }),
      createViewState({ chatInput: "create", setChatError }),
      createViewState({ intakeId: "pm-1", questions: ["q1"], chatInput: "", setChatError }),
      createViewState({ intakeId: "pm-1", questions: ["q1"], chatInput: "answer", setChatError }),
      createViewState({ intakeId: "pm-1", questions: [], runId: "", chatInput: "run", setChatError }),
      createViewState({
        intakeId: "pm-1",
        runId: "run-1",
        chatLogRef: { current: { scrollHeight: 500, scrollTop: 0, clientHeight: 200, scrollTo } },
        setChatStickToBottom,
        setChatUnreadCount,
        setChatError,
      }),
    ];

    const actions = createViewActions({ handleChatSend, handleRun });

    scenarios.forEach((state) => {
      const { result, unmount } = renderHook(() => usePMIntakeView(state as never, actions as never));
      act(() => {
        result.current.handlePrimaryStageAction();
      });
      unmount();
    });

    expect(setChatError).toHaveBeenCalledWith("Bind Workspace and Repo first.");
    expect(setChatError).toHaveBeenCalledWith("Enter a request first, or click \"Fill example\".");
    expect(setChatError).toHaveBeenCalledWith("Answer the clarifying question in the composer before sending.");
    expect(handleChatSend).toHaveBeenCalledTimes(2);
    expect(handleRun).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalled();
    expect(setChatStickToBottom).toHaveBeenCalledWith(true);
    expect(setChatUnreadCount).toHaveBeenCalledWith(0);

    const noAbortState = createViewState({ setChatNotice });
    const { result: noAbortResult, unmount: unmountNoAbort } = renderHook(() =>
      usePMIntakeView(noAbortState as never, actions as never),
    );
    act(() => {
      noAbortResult.current.requestStopGeneration();
    });
    expect(setChatNotice).toHaveBeenCalledWith("There is no active request to cancel.");
    unmountNoAbort();

    const abort = vi.fn();
    const abortState = createViewState({
      chatAbortRef: { current: { abort, signal: { aborted: false } } },
      setChatNotice,
    });
    const { result: abortResult } = renderHook(() => usePMIntakeView(abortState as never, actions as never));
    act(() => {
      abortResult.current.requestStopGeneration();
    });
    expect(abort).toHaveBeenCalledTimes(1);
    expect(setChatNotice).toHaveBeenCalledWith("Cancelling the active request...");
  });

  it("applies example template and chat scroll unread fallback", () => {
    const setChatInput = vi.fn();
    const setChatError = vi.fn();
    const setChatNotice = vi.fn();
    const setChatStickToBottom = vi.fn();
    const setChatUnreadCount = vi.fn();
    const state = createViewState({
      setChatInput,
      setChatError,
      setChatNotice,
      setChatStickToBottom,
      setChatUnreadCount,
      chatStickToBottom: false,
      chatLog: [{ id: "m1", role: "PM", text: "msg", createdAt: "2026-03-01T10:00:00.000Z", kind: "message", origin: "local" }],
      lastChatLengthRef: { current: 0 },
    });
    const actions = createViewActions();
    const { result } = renderHook(() => usePMIntakeView(state as never, actions as never));

    act(() => {
      result.current.applyExampleTemplate();
    });
    const updater = setChatInput.mock.calls[0][0] as (value: string) => string;
    expect(updater("")).toContain("Please create a public-read-only Seattle tech and AI news digest");
    expect(setChatError).toHaveBeenCalledWith("");
    expect(setChatNotice).toHaveBeenCalledWith("Filled the news_digest example. Send it as-is or keep editing.");

    act(() => {
      result.current.handleChatScroll({ scrollHeight: 500, scrollTop: 0, clientHeight: 100 } as HTMLDivElement);
      result.current.handleChatScroll({ scrollHeight: 500, scrollTop: 450, clientHeight: 100 } as HTMLDivElement);
    });
    expect(setChatStickToBottom).toHaveBeenCalledWith(false);
    expect(setChatStickToBottom).toHaveBeenCalledWith(true);
  });

  it("preselects the public task template from the URL query string", async () => {
    window.history.replaceState({}, "", "/pm?template=page_brief");
    const setTaskTemplate = vi.fn();
    const setTaskPackFieldValuesByTemplate = vi.fn();
    const setChatNotice = vi.fn();
    const pageBriefPack: TaskPackManifest = {
      pack_id: "page_brief",
      version: "v1",
      title: "Public Page Brief",
      description: "Public, read-only page brief for a single URL.",
      visibility: "public",
      entry_mode: "pm_intake",
      task_template: "page_brief",
      input_fields: [
        { field_id: "url", label: "Page URL", control: "url", required: true, placeholder: "https://example.com" },
      ],
      ui_hint: { surface_group: "public_task_templates", default_label: "Public page brief" },
    };

    const state = createViewState({
      taskPacks: [pageBriefPack],
      setTaskTemplate,
      setTaskPackFieldValuesByTemplate,
      setChatNotice,
    });
    const actions = createViewActions();

    renderHook(() => usePMIntakeView(state as never, actions as never));

    await waitFor(() => {
      expect(setTaskTemplate).toHaveBeenCalledWith("page_brief");
      expect(setTaskPackFieldValuesByTemplate).toHaveBeenCalled();
    });

    const updater = setTaskPackFieldValuesByTemplate.mock.calls[0][0] as (previous: Record<string, Record<string, string>>) => Record<string, Record<string, string>>;
    expect(updater({})).toEqual({
      page_brief: buildTaskPackFieldStateForPack(pageBriefPack, {}),
    });
    expect(setChatNotice).toHaveBeenCalledWith("Loaded the page_brief public example. Preview the Flight Plan or send it as-is.");
  });
});

describe("pm intake actions hook branches", () => {
  const mockAnswerIntake = vi.mocked(answerIntake);
  const mockCreateIntake = vi.mocked(createIntake);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockFetchTaskPacks = vi.mocked(fetchTaskPacks);
  const mockRunIntake = vi.mocked(runIntake);

  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, "", "/pm");
    mockFetchPmSession.mockResolvedValue({ session: {}, runs: [], run_ids: [] } as never);
    mockFetchPmSessionEvents.mockResolvedValue([] as never);
    mockCreateIntake.mockResolvedValue({ intake_id: "pm-1", questions: [] } as never);
    mockAnswerIntake.mockResolvedValue({ intake_id: "pm-1", questions: [] } as never);
    mockRunIntake.mockResolvedValue({ run_id: "run-1" } as never);
    mockFetchTaskPacks.mockResolvedValue([
      {
        pack_id: "news_digest",
        version: "v1",
        title: "Public News Digest",
        description: "Public, read-only digest over recent sources for one topic.",
        visibility: "public",
        entry_mode: "pm_intake",
        task_template: "news_digest",
        input_fields: [
          { field_id: "topic", label: "Topic", control: "text", required: true, default_value: "Seattle tech and AI" },
        ],
        ui_hint: { surface_group: "public_task_templates", default_label: "Public news digest" },
      },
    ] as never);
  });

  it("handles new-conversation refresh failure branch", async () => {
    window.history.replaceState({}, "", "/pm?pm_session_id=pm-old");
    mockFetchPmSessions.mockRejectedValue(new Error("network down"));
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    await act(async () => {
      await result.current.actions.handleStartNewConversation();
    });

    expect(result.current.state.newConversationError).toBe("Session list refresh timed out or failed, but you can still send the first request.");
    expect(result.current.state.newConversationNotice).toBe("");
    expect(window.location.search).toBe("");
  });

  it("handles new-conversation focus throw catch branch", async () => {
    mockFetchPmSessions.mockResolvedValue([]);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    act(() => {
      result.current.state.chatInputRef.current = {
        focus: () => {
          throw new Error("focus failed");
        },
      } as never;
    });

    await act(async () => {
      await result.current.actions.handleStartNewConversation();
    });

    expect(result.current.state.newConversationError).toBe("Failed to create a new chat");
    expect(result.current.state.newConversationNotice).toBe("");
  });

  it("short-circuits session select when selecting current session id", async () => {
    mockFetchPmSessions.mockResolvedValue([]);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    await act(async () => {
      result.current.state.setIntakeId("pm-same");
      result.current.state.setQuestions(["q-keep"]);
      result.current.state.setPlan({ keep: true });
      result.current.state.setTaskChain({ keep: "chain" });
      await Promise.resolve();
    });

    act(() => {
      result.current.actions.handleSessionSelect("pm-same");
    });
    expect(result.current.state.intakeId).toBe("pm-same");
    expect(result.current.state.questions).toEqual(["q-keep"]);
    expect(result.current.state.plan).toEqual({ keep: true });
    expect(result.current.state.taskChain).toEqual({ keep: "chain" });
  });

  it("updates URL and hydrates session context when selecting a different session", async () => {
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-a",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-a",
      },
      {
        pm_session_id: "pm-b",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-b",
      },
    ] as never);
    mockFetchPmSession.mockImplementation(async (sessionId: string) => {
      return {
        session: {
          pm_session_id: sessionId,
          latest_run_id: sessionId === "pm-b" ? "run-b" : "run-a",
          current_role: "TECH_LEAD",
        },
        runs: [],
        run_ids: [sessionId === "pm-b" ? "run-b" : "run-a"],
      } as never;
    });
    mockFetchPmSessionEvents.mockResolvedValue([] as never);

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(result.current.state.sessionHistory.length).toBeGreaterThanOrEqual(2);
    });

    act(() => {
      result.current.actions.handleSessionSelect("pm-b");
    });

    await waitFor(() => {
      expect(result.current.state.intakeId).toBe("pm-b");
      expect(result.current.state.runId).toBe("run-b");
      expect(window.location.search).toContain("pm_session_id=pm-b");
    });
  });

  it("restores intake from URL when session exists in refreshed history", async () => {
    window.history.replaceState({}, "", "/pm?pm_session_id=pm-url");
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-url",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-url",
      },
    ] as never);
    mockFetchPmSession.mockResolvedValue({
      session: {
        pm_session_id: "pm-url",
        latest_run_id: "run-url",
        current_role: "WORKER",
      },
      runs: [],
      run_ids: ["run-url"],
    } as never);
    mockFetchPmSessionEvents.mockResolvedValue([] as never);

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      usePMIntakeActions(state);
      return state;
    });

    await waitFor(() => {
      expect(result.current.intakeId).toBe("pm-url");
      expect(result.current.runId).toBe("run-url");
    });
  });

  it("covers run success path, busy guards, and custom preset fallback", async () => {
    mockFetchPmSessions.mockResolvedValue([] as never);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });

    await act(async () => {
      result.current.state.setIntakeId("pm-run");
      result.current.state.setBrowserPreset("custom");
      result.current.state.setRequesterRole("pm");
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.state.browserPreset).toBe("safe");
    });

    await act(async () => {
      await result.current.actions.handleRun();
    });
    expect(result.current.state.runId).toBe("run-1");
    expect(result.current.state.chatNotice).toContain("Execution started");

    await act(async () => {
      result.current.state.setChatBusy(true);
      await Promise.resolve();
    });
    await act(async () => {
      await result.current.actions.handleCreate();
      await result.current.actions.handleAnswer();
    });
    expect(mockCreateIntake).not.toHaveBeenCalled();
    expect(mockAnswerIntake).not.toHaveBeenCalled();
  });

  it("covers session-select guards for blank, duplicate in-flight and stale session", async () => {
    const detailDeferred = createDeferred<any>();
    const eventsDeferred = createDeferred<any[]>();
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-a",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-a",
      },
      {
        pm_session_id: "pm-b",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-b",
      },
    ] as never);
    mockFetchPmSession.mockImplementation((sessionId: string) => {
      if (sessionId === "pm-b") {
        return detailDeferred.promise as never;
      }
      return Promise.resolve({
        session: {
          pm_session_id: sessionId,
          latest_run_id: "run-a",
          current_role: "PM",
        },
        runs: [],
        run_ids: ["run-a"],
      } as never);
    });
    mockFetchPmSessionEvents.mockImplementation((sessionId: string) => {
      if (sessionId === "pm-b") {
        return eventsDeferred.promise as never;
      }
      return Promise.resolve([] as never);
    });

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(result.current.state.sessionHistory.length).toBeGreaterThanOrEqual(2);
    });

    act(() => {
      result.current.actions.handleSessionSelect("   ");
    });
    expect(result.current.state.intakeId).toBe("");

    act(() => {
      result.current.actions.handleSessionSelect("pm-b");
    });
    const detailCallsAfterFirstSelect = mockFetchPmSession.mock.calls.length;
    act(() => {
      result.current.actions.handleSessionSelect("pm-b");
    });
    expect(mockFetchPmSession.mock.calls.length).toBe(detailCallsAfterFirstSelect);

    await act(async () => {
      detailDeferred.resolve({
        session: {
          pm_session_id: "pm-b",
          latest_run_id: "run-b",
          current_role: "TECH_LEAD",
        },
        runs: [],
        run_ids: ["run-b"],
      });
      eventsDeferred.resolve([]);
      await Promise.resolve();
    });
    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      result.current.actions.handleSessionSelect("pm-missing");
    });
    await waitFor(() => {
      expect(result.current.state.chatError).toContain("Session is stale");
      expect(result.current.state.chatNotice).toContain("Session list updated");
    });
  });

  it("shows in-flight notice when starting new conversation repeatedly", async () => {
    mockFetchPmSessions.mockResolvedValue([] as never);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });

    await act(async () => {
      result.current.state.setNewConversationBusy(true);
      await Promise.resolve();
    });
    await act(async () => {
      await result.current.actions.handleStartNewConversation();
    });

    expect(result.current.state.newConversationNotice).toContain("New chat creation is already in progress");
  });

  it("updates run id and notice on successful handleRun", async () => {
    mockFetchPmSessions.mockResolvedValue([] as never);
    mockRunIntake.mockResolvedValue({ run_id: "run-success" } as never);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    await act(async () => {
      result.current.state.setIntakeId("pm-run");
      await Promise.resolve();
    });

    await act(async () => {
      await result.current.actions.handleRun();
    });

    expect(mockRunIntake).toHaveBeenCalledWith(
      "pm-run",
      {},
      expect.objectContaining({ timeoutMs: expect.any(Number) }),
    );
    expect(result.current.state.runId).toBe("run-success");
    expect(result.current.state.chatNotice).toContain("run-success");
  });

  it("returns early in handleAnswer when busy", async () => {
    mockFetchPmSessions.mockResolvedValue([] as never);
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });
    await act(async () => {
      result.current.state.setIntakeId("pm-answer");
      result.current.state.setBusy(true);
      await Promise.resolve();
    });

    await act(async () => {
      await result.current.actions.handleAnswer();
    });

    expect(mockAnswerIntake).not.toHaveBeenCalled();
  });

  it("surfaces hydrate failure when session detail/events loading fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-fail",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        latest_run_id: "run-fail",
      },
    ] as never);
    mockFetchPmSession.mockRejectedValue(new Error("detail broke"));
    mockFetchPmSessionEvents.mockRejectedValue(new Error("events broke"));

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    try {
      await waitFor(() => {
        expect(result.current.state.sessionHistory.length).toBe(1);
      });

      act(() => {
        result.current.actions.handleSessionSelect("pm-fail");
      });

      await waitFor(() => {
        expect(result.current.state.chatError).toBe("Failed to load session details. Please retry.");
        expect(result.current.state.chatNotice).toBe("Failed to switch to session pm-fail. Please retry.");
      });
      expect(consoleSpy).toHaveBeenCalled();
    } finally {
      consoleSpy.mockRestore();
    }
  });

  it("handles start-new-conversation timeout branch via promise race timer", async () => {
    mockFetchPmSessions
      .mockResolvedValueOnce([] as never)
      .mockImplementationOnce(
        () =>
          new Promise(() => {
            // keep pending to force timeout branch
          }) as never,
      );
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    try {
      await waitFor(() => {
        expect(mockFetchPmSessions).toHaveBeenCalledTimes(1);
      });

      vi.useFakeTimers();
      await act(async () => {
        const promise = result.current.actions.handleStartNewConversation();
        await vi.advanceTimersByTimeAsync(10_001);
        await promise;
      });

      expect(result.current.state.newConversationError).toBe(
        "Session list refresh timed out or failed, but you can still send the first request.",
      );
      expect(result.current.state.newConversationNotice).toBe("");
    } finally {
      vi.useRealTimers();
    }
  });
});
