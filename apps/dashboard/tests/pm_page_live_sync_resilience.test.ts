import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../lib/api", () => ({
  answerIntake: vi.fn(),
  createIntake: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessions: vi.fn(),
  runIntake: vi.fn(),
}));

import { usePMIntakeActions } from "../app/pm/hooks/usePMIntakeActions";
import { usePMIntakeData } from "../app/pm/hooks/usePMIntakeData";
import { usePMIntakeView } from "../app/pm/hooks/usePMIntakeView";
import { fetchPmSession, fetchPmSessionEvents, fetchPmSessions } from "../lib/api";

describe("pm page live sync resilience", () => {
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPmSessions.mockResolvedValue([]);
  });

  it("keeps live-sync state updates resilient under mixed success/failure responses", async () => {
    mockFetchPmSession.mockImplementation((pmSessionId) => {
      if (pmSessionId === "pm-1") {
        return Promise.reject(new Error("detail failed"));
      }
      if (pmSessionId === "pm-2") {
        return Promise.resolve({
          session: {
            pm_session_id: "pm-2",
            latest_run_id: "run-2",
            current_role: "reviewer",
          },
          runs: [],
          run_ids: ["run-2"],
        } as never);
      }
      return Promise.resolve({ session: {}, runs: [], run_ids: [] } as never);
    });

    mockFetchPmSessionEvents.mockImplementation((_pmSessionId, options) => {
      if ((options as { limit?: number } | undefined)?.limit === 200) {
        return Promise.resolve([] as never);
      }
      if (_pmSessionId === "pm-1") {
        return Promise.resolve([
          {
            ts: "2026-03-02T10:00:00.000Z",
            context: {
              message: "worker accepted",
              current_role: "WORKER",
            },
          },
        ] as never);
      }
      if (_pmSessionId === "pm-2") {
        return Promise.reject(new Error("events failed"));
      }
      return Promise.resolve([] as never);
    });

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      usePMIntakeActions(state);
      return state;
    });

    await act(async () => {
      result.current.setIntakeId("pm-1");
    });

    await waitFor(() => {
      expect(result.current.progressFeed).toHaveLength(1);
    });
    expect(result.current.runId).toBe("");
    expect(result.current.liveRole).toBe("WORKER");

    await act(async () => {
      result.current.setIntakeId("pm-2");
    });

    await waitFor(() => {
      expect(result.current.runId).toBe("run-2");
    });
    expect(result.current.progressFeed).toHaveLength(0);
    expect(result.current.liveRole).toBe("REVIEWER");

    expect(mockFetchPmSession).toHaveBeenCalledWith("pm-1");
    expect(mockFetchPmSession).toHaveBeenCalledWith("pm-2");
    expect(mockFetchPmSessionEvents).toHaveBeenCalledWith(
      "pm-1",
      expect.objectContaining({ limit: 120, tail: true }),
    );
    expect(mockFetchPmSessionEvents).toHaveBeenCalledWith(
      "pm-2",
      expect.objectContaining({ limit: 120, tail: true }),
    );
  });

  it("prevents overlapping live-sync requests and queues a single follow-up tick", async () => {
    vi.useFakeTimers();
    try {
      let resolveDetail: ((value: unknown) => void) | null = null;
      let resolveEvents: ((value: unknown) => void) | null = null;
      const detailPromise = new Promise((resolve) => {
        resolveDetail = resolve;
      });
      const eventsPromise = new Promise((resolve) => {
        resolveEvents = resolve;
      });

      mockFetchPmSession.mockImplementation((_pmSessionId) => detailPromise as never);
      mockFetchPmSessionEvents.mockImplementation((_pmSessionId, options) => {
        if ((options as { limit?: number } | undefined)?.limit === 200) {
          return Promise.resolve([] as never);
        }
        return eventsPromise as never;
      });

      const { result } = renderHook(() => {
        const state = usePMIntakeData();
        usePMIntakeActions(state);
        return state;
      });

      await act(async () => {
        result.current.setIntakeId("pm-guard");
        await Promise.resolve();
      });

      expect(mockFetchPmSession).toHaveBeenCalledTimes(1);
      expect(mockFetchPmSessionEvents).toHaveBeenCalledWith(
        "pm-guard",
        expect.objectContaining({ limit: 120, tail: true }),
      );

      act(() => {
        vi.advanceTimersByTime(10000);
      });
      expect(mockFetchPmSession).toHaveBeenCalledTimes(1);

      await act(async () => {
        resolveDetail?.({
          session: {
            pm_session_id: "pm-guard",
            latest_run_id: "run-guard",
            current_role: "TECH_LEAD",
          },
          runs: [],
          run_ids: ["run-guard"],
        } as never);
        resolveEvents?.([] as never);
        await Promise.resolve();
        await Promise.resolve();
      });

      expect(mockFetchPmSession).toHaveBeenCalledTimes(2);
      const liveSyncEventCalls = mockFetchPmSessionEvents.mock.calls.filter(
        (_args) => (_args[1] as { limit?: number } | undefined)?.limit === 120,
      );
      expect(liveSyncEventCalls).toHaveLength(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("pm intake view branch coverage", () => {
  function buildViewState(overrides: Record<string, unknown> = {}) {
    const chatNode = document.createElement("div");
    Object.defineProperty(chatNode, "scrollHeight", { value: 400, configurable: true, writable: true });
    Object.defineProperty(chatNode, "scrollTop", { value: 0, configurable: true, writable: true });
    Object.defineProperty(chatNode, "clientHeight", { value: 200, configurable: true, writable: true });

    return {
      workspaceBound: true,
      intakeId: "",
      questions: [] as string[],
      runId: "",
      copyVariant: "a",
      chatFlowBusy: false,
      chatBusy: false,
      busy: false,
      chatHistoryBusy: false,
      liveRole: "PM",
      chatLog: [] as Array<{ role: string }>,
      progressFeed: [] as string[],
      plan: null,
      taskChain: null,
      sessionHistory: [],
      setHoveredChainRole: vi.fn(),
      activeChatSessionId: "",
      lastChatLengthRef: { current: 0 },
      chatStickToBottom: true,
      setChatStickToBottom: vi.fn(),
      setChatUnreadCount: vi.fn(),
      chatLogRef: { current: chatNode as HTMLDivElement | null },
      chatAbortRef: { current: null as AbortController | null },
      chatInputRef: { current: null as HTMLTextAreaElement | null },
      chainPanelRef: { current: null as HTMLElement | null },
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

  function buildViewActions(overrides: Record<string, unknown> = {}) {
    return {
      handleChatSend: vi.fn(),
      handleRun: vi.fn(),
      handleStartNewConversation: vi.fn(),
      ...overrides,
    };
  }

  it("covers primary stage action branches across workspace/intake/question/run states", () => {
    const noWorkspaceState = buildViewState({ workspaceBound: false, chatInput: "need workspace" });
    const noWorkspaceActions = buildViewActions();
    const noWorkspace = renderHook(() => usePMIntakeView(noWorkspaceState as never, noWorkspaceActions as never));
    act(() => {
      noWorkspace.result.current.handlePrimaryStageAction();
    });
    expect(noWorkspaceState.setChatError).toHaveBeenCalledWith("Bind Workspace and Repo first.");
    noWorkspace.unmount();

    const draftEmptyState = buildViewState({ workspaceBound: true, intakeId: "", chatInput: "   " });
    const draftEmptyActions = buildViewActions();
    const draftEmpty = renderHook(() => usePMIntakeView(draftEmptyState as never, draftEmptyActions as never));
    act(() => {
      draftEmpty.result.current.handlePrimaryStageAction();
    });
    expect(draftEmptyState.setChatError).toHaveBeenCalledWith("Enter a request first, or click \"Fill example\".");
    draftEmpty.unmount();

    const draftInputState = buildViewState({ intakeId: "", chatInput: "create intake" });
    const draftInputActions = buildViewActions();
    const draftInput = renderHook(() => usePMIntakeView(draftInputState as never, draftInputActions as never));
    act(() => {
      draftInput.result.current.handlePrimaryStageAction();
    });
    expect(draftInputActions.handleChatSend).toHaveBeenCalledTimes(1);
    draftInput.unmount();

    const clarifyEmptyState = buildViewState({ intakeId: "pm-1", questions: ["q1"], chatInput: " " });
    const clarifyEmptyActions = buildViewActions();
    const clarifyEmpty = renderHook(() => usePMIntakeView(clarifyEmptyState as never, clarifyEmptyActions as never));
    act(() => {
      clarifyEmpty.result.current.handlePrimaryStageAction();
    });
    expect(clarifyEmptyState.setChatError).toHaveBeenCalledWith("Answer the clarifying question in the composer before sending.");
    clarifyEmpty.unmount();

    const clarifyInputState = buildViewState({ intakeId: "pm-1", questions: ["q1"], chatInput: "answer q1" });
    const clarifyInputActions = buildViewActions();
    const clarifyInput = renderHook(() => usePMIntakeView(clarifyInputState as never, clarifyInputActions as never));
    act(() => {
      clarifyInput.result.current.handlePrimaryStageAction();
    });
    expect(clarifyInputActions.handleChatSend).toHaveBeenCalledTimes(1);
    clarifyInput.unmount();

    const executeState = buildViewState({ intakeId: "pm-1", questions: [], runId: "" });
    const executeActions = buildViewActions();
    const executeView = renderHook(() => usePMIntakeView(executeState as never, executeActions as never));
    act(() => {
      executeView.result.current.handlePrimaryStageAction();
    });
    expect(executeActions.handleRun).toHaveBeenCalledTimes(1);
    executeView.unmount();
  });

  it("covers stop-generation and scroll-to-bottom helper branches", () => {
    const noControllerState = buildViewState({ chatAbortRef: { current: null } });
    const noControllerActions = buildViewActions();
    const noController = renderHook(() => usePMIntakeView(noControllerState as never, noControllerActions as never));
    act(() => {
      noController.result.current.requestStopGeneration();
    });
    expect(noControllerState.setChatNotice).toHaveBeenCalledWith("There is no active request to cancel.");
    noController.unmount();

    const controller = new AbortController();
    const withControllerState = buildViewState({ chatAbortRef: { current: controller } });
    const withControllerActions = buildViewActions();
    const withController = renderHook(() => usePMIntakeView(withControllerState as never, withControllerActions as never));
    act(() => {
      withController.result.current.requestStopGeneration();
    });
    expect(controller.signal.aborted).toBe(true);
    expect(withControllerState.setChatNotice).toHaveBeenCalledWith("Cancelling the active request...");

    const scrollToMock = vi.fn();
    const scrollNode = withControllerState.chatLogRef.current as HTMLDivElement;
    Object.defineProperty(scrollNode, "scrollTo", { value: scrollToMock, configurable: true });
    const runReadyState = buildViewState({
      intakeId: "pm-1",
      runId: "run-1",
      chatInput: "ignored",
      chatLogRef: { current: scrollNode },
    });
    const runReadyActions = buildViewActions();
    const runReady = renderHook(() => usePMIntakeView(runReadyState as never, runReadyActions as never));
    act(() => {
      runReady.result.current.handlePrimaryStageAction();
    });
    expect(scrollToMock).toHaveBeenCalled();
    expect(runReadyState.setChatUnreadCount).toHaveBeenCalledWith(0);
    runReady.unmount();
    withController.unmount();
  });
});
