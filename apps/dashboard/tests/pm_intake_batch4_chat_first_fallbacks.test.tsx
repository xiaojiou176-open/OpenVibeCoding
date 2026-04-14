import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PMIntakeCenterPanel from "../app/pm/components/PMIntakeCenterPanel";
import PMIntakeRightSidebar from "../app/pm/components/PMIntakeRightSidebar";
import type { ChainNode, ChatItem } from "../app/pm/components/PMIntakeFeature.shared";
import { usePMIntakeActions } from "../app/pm/hooks/usePMIntakeActions";
import { usePMIntakeData } from "../app/pm/hooks/usePMIntakeData";
import { usePMIntakeView } from "../app/pm/hooks/usePMIntakeView";
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

function createAbortError(message = "aborted") {
  const error = new Error(message) as Error & { name: string };
  error.name = "AbortError";
  return error;
}

function createJourneyContext(stage: "discover" | "clarify" | "execute" | "verify") {
  return {
    stage,
    reason: `${stage}-reason`,
    primaryAction: `${stage}-primary`,
    secondaryActions: ["Support action A"],
  };
}

function createChainNodes(): ChainNode[] {
  return [
    { role: "PM", label: "PM", hint: "Entry", state: "done" },
    { role: "TECH_LEAD", label: "TL", hint: "Breakdown", state: "active" },
    { role: "WORKER", label: "Worker", hint: "Execution", state: "idle" },
  ];
}

function createCenterProps(overrides: Partial<Parameters<typeof PMIntakeCenterPanel>[0]> = {}) {
  const base: Parameters<typeof PMIntakeCenterPanel>[0] = {
    layoutMode: "dialog",
    onLayoutModeChange: vi.fn(),
    pmStageText: "Discover",
    pmJourneyContext: createJourneyContext("discover"),
    onPrimaryStageAction: vi.fn(),
    onFillTemplate: vi.fn(),
    chatFlowBusy: false,
    chatError: "",
    chatNotice: "",
    firstRunStage: "Discover",
    headerHint: "hint",
    firstRunNextCta: "Next",
    intakeId: "",
    chatHistoryBusy: false,
    chatLog: [],
    liveRole: "TECH_LEAD",
    hoveredChainRole: null,
    onHoveredChainRoleChange: vi.fn(),
    chatStickToBottom: true,
    chatUnreadCount: 0,
    onScrollToBottom: vi.fn(),
    workspaceBound: true,
    chatInput: "",
    onChatInputChange: vi.fn(),
    onSend: vi.fn(),
    chatBusy: false,
    onStopGeneration: vi.fn(),
    chatPlaceholder: "placeholder",
    chatInputRef: createRef<HTMLTextAreaElement>(),
    chatLogRef: createRef<HTMLDivElement>(),
    onChatScroll: vi.fn(),
    chainNodes: createChainNodes(),
  };
  return { ...base, ...overrides };
}

function createSidebarProps(overrides: Partial<Parameters<typeof PMIntakeRightSidebar>[0]> = {}) {
  const base: Parameters<typeof PMIntakeRightSidebar>[0] = {
    pmJourneyContext: createJourneyContext("discover"),
    runId: "",
    intakeId: "pm-1",
    liveRole: "TECH_LEAD",
    currentSessionStatus: "active",
    chainNodes: createChainNodes(),
    hoveredChainRole: null,
    onHoveredChainRoleChange: vi.fn(),
    progressFeed: [],
    questions: [],
    requesterRole: "PM",
    onRequesterRoleChange: vi.fn(),
    browserPreset: "safe",
    onBrowserPresetChange: vi.fn(),
    canUseCustomPreset: false,
    customBrowserPolicy: "",
    onCustomBrowserPolicyChange: vi.fn(),
    error: "",
    objective: "objective",
    onObjectiveChange: vi.fn(),
    allowedPaths: "apps/dashboard",
    onAllowedPathsChange: vi.fn(),
    constraints: "safe",
    onConstraintsChange: vi.fn(),
    searchQueries: "query",
    onSearchQueriesChange: vi.fn(),
    chatFlowBusy: false,
    onCreate: vi.fn(),
    onAnswer: vi.fn(),
    onPreview: vi.fn(),
    onRun: vi.fn(),
    hasIntakeId: true,
    plan: null,
    taskChain: null,
    executionPlanPreview: null,
    executionPlanPreviewBusy: false,
    executionPlanPreviewError: "",
    chainPanelRef: createRef<HTMLElement>(),
  };
  return { ...base, ...overrides };
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

describe("batch4 pm intake components chat-first fallbacks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTaskPacks).mockResolvedValue([
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

  it("covers center stage transitions, stage-action callbacks, and empty state variants", () => {
    const onPrimaryStageAction = vi.fn();
    const onFillTemplate = vi.fn();
    const { rerender } = render(
      <PMIntakeCenterPanel
        {...createCenterProps({
          onPrimaryStageAction,
          onFillTemplate,
          chatError: "chat error",
          chatNotice: "chat notice",
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("pm-stage-primary-action"));
    fireEvent.click(screen.getByTestId("pm-stage-fill-template"));
    fireEvent.click(screen.getByTestId("pm-context-primary-action"));
    fireEvent.click(screen.getByTestId("pm-context-fill-template"));

    expect(onPrimaryStageAction).toHaveBeenCalledTimes(2);
    expect(onFillTemplate).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert")).toHaveTextContent("chat error");
    expect(screen.getByText("chat notice")).toBeInTheDocument();

    rerender(
      <PMIntakeCenterPanel
        {...createCenterProps({
          pmJourneyContext: createJourneyContext("clarify"),
          intakeId: "pm-1",
          chatLog: [],
        })}
      />,
    );
    expect(screen.getByLabelText("Clarify stage guide")).toBeInTheDocument();
    expect(screen.getByText("No messages in this session yet")).toBeInTheDocument();

    rerender(
      <PMIntakeCenterPanel
        {...createCenterProps({
          pmJourneyContext: createJourneyContext("execute"),
          intakeId: "pm-1",
          chatLog: [],
        })}
      />,
    );
    expect(screen.getByLabelText("Execute stage guide")).toBeInTheDocument();

    rerender(
      <PMIntakeCenterPanel
        {...createCenterProps({
          pmJourneyContext: createJourneyContext("verify"),
          intakeId: "",
          chatLog: [],
        })}
      />,
    );
    expect(screen.getByLabelText("Verify stage guide")).toBeInTheDocument();
    expect(screen.getByText("No session yet. Send the first request")).toBeInTheDocument();
  });

  it("covers right-sidebar runtime status badge branches for done and default states", () => {
    const { rerender } = render(
      <PMIntakeRightSidebar
        {...createSidebarProps({
          currentSessionStatus: "done",
          progressFeed: ["progress-1"],
          questions: ["question-1"],
        })}
      />,
    );

    const doneBadge = document.querySelector(".pm-runtime-row .badge") as HTMLElement | null;
    expect(doneBadge).not.toBeNull();
    expect(doneBadge?.textContent).toBe("done");
    expect(doneBadge?.className).toContain("badge--success");
    expect(screen.getByText("progress-1")).toBeInTheDocument();
    expect(screen.getByText("question-1")).toBeInTheDocument();

    rerender(
      <PMIntakeRightSidebar
        {...createSidebarProps({
          currentSessionStatus: "active",
          progressFeed: [],
          questions: [],
        })}
      />,
    );

    const activeBadge = document.querySelector(".pm-runtime-row .badge") as HTMLElement | null;
    expect(activeBadge).not.toBeNull();
    expect(activeBadge?.textContent).toBe("active");
    expect(activeBadge?.className).not.toContain("badge--success");
    expect(activeBadge?.className).not.toContain("badge--failed");
  });
});

describe("batch4 pm intake view hook chat-first transitions", () => {
  it("covers run-stage scroll fallback when chat log ref is missing", () => {
    const state = createViewState({
      runId: "run-1",
      chatLogRef: { current: null },
    });
    const actions = createViewActions();

    const { result } = renderHook(() => usePMIntakeView(state as never, actions as never));

    act(() => {
      result.current.handlePrimaryStageAction();
    });

    expect(state.setChatError).not.toHaveBeenCalled();
  });
});

describe("batch4 pm intake actions hook chat-first fallbacks", () => {
  const mockAnswerIntake = vi.mocked(answerIntake);
  const mockCreateIntake = vi.mocked(createIntake);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockRunIntake = vi.mocked(runIntake);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPmSession.mockResolvedValue({ session: {}, run_ids: [], runs: [] } as never);
    mockFetchPmSessionEvents.mockResolvedValue([] as never);
    mockFetchPmSessions.mockResolvedValue([] as never);
    mockCreateIntake.mockResolvedValue({ intake_id: "pm-1", questions: [] } as never);
    mockAnswerIntake.mockResolvedValue({ intake_id: "pm-1", questions: [] } as never);
    mockRunIntake.mockResolvedValue({ run_id: "run-1" } as never);
  });

  it("retries refreshSessionHistory and clears previous load error after retry success", async () => {
    mockFetchPmSessions
      .mockRejectedValueOnce(new Error("temporary network"))
      .mockResolvedValueOnce([] as never);

    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalledTimes(2);
    });

    await act(async () => {
      await result.current.actions.refreshSessionHistory();
    });

    expect(result.current.state.sessionHistoryError).toBe("");
    expect(result.current.state.historyBusy).toBe(false);
  });

  it("covers buildIntakePayload fallback defaults and custom-json failure", async () => {
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });

    await act(async () => {
      result.current.state.setWorkspacePath("");
      result.current.state.setRepoName("");
    });
    expect(() => result.current.actions.buildIntakePayload("objective")).toThrow("Workspace path and repository name must be bound first");

    await act(async () => {
      result.current.state.setWorkspacePath("apps/dashboard");
      result.current.state.setRepoName("openvibecoding");
      result.current.state.setAllowedPaths("\n");
      result.current.state.setConstraints("constraint-a");
      result.current.state.setSearchQueries("search-a");
    });
    const payload = result.current.actions.buildIntakePayload("objective");
    expect(payload.allowed_paths).toEqual(["apps/dashboard", "apps/orchestrator/src"]);

    await act(async () => {
      result.current.state.setRequesterRole("OWNER");
      result.current.state.setTaskTemplate("general");
      result.current.state.setBrowserPreset("custom");
      result.current.state.setCustomBrowserPolicy("{");
    });
    expect(() => result.current.actions.buildIntakePayload("objective")).toThrow("Custom browser policy JSON is invalid");
  });

  it("covers browser preset fallback, handleRun guard rails, and aborted run fallback", async () => {
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });

    await act(async () => {
      result.current.state.setRequesterRole("PM");
      result.current.state.setBrowserPreset("custom");
    });

    await waitFor(() => {
      expect(result.current.state.browserPreset).toBe("safe");
    });

    await act(async () => {
      await result.current.actions.handleRun();
    });
    expect(result.current.state.error).toBe("Create a PM session first.");

    await act(async () => {
      result.current.state.setIntakeId("pm-run");
      result.current.state.setChatBusy(true);
    });
    await act(async () => {
      await result.current.actions.handleRun();
    });
    expect(mockRunIntake).not.toHaveBeenCalled();

    await act(async () => {
      result.current.state.setChatBusy(false);
    });
    mockRunIntake.mockRejectedValueOnce(createAbortError());

    await act(async () => {
      await result.current.actions.handleRun();
    });

    expect(result.current.state.chatNotice).toBe("Request cancelled.");
    const latestSessionId = result.current.state.intakeId || "";
    const latestLog = result.current.state.chatLogBySession[latestSessionId] || [];
    expect(latestLog.some((item: ChatItem) => item.text.includes("Cancelled the active request"))).toBe(true);
  });

  it("covers handleCreate and handleAnswer error/empty-state transitions", async () => {
    const { result } = renderHook(() => {
      const state = usePMIntakeData();
      const actions = usePMIntakeActions(state);
      return { state, actions };
    });

    await waitFor(() => {
      expect(mockFetchPmSessions).toHaveBeenCalled();
    });

    await act(async () => {
      result.current.state.setWorkspacePath("apps/dashboard");
      result.current.state.setRepoName("openvibecoding");
      result.current.state.setObjective("create-flow");
    });

    mockCreateIntake.mockRejectedValueOnce(new Error("create failed"));
    await act(async () => {
      await result.current.actions.handleCreate();
    });
    expect(result.current.state.error).toBe("Create failed");

    await act(async () => {
      result.current.state.setBusy(true);
    });
    await act(async () => {
      await result.current.actions.handleCreate();
    });
    expect(mockCreateIntake).toHaveBeenCalledTimes(1);

    await act(async () => {
      result.current.state.setBusy(false);
      result.current.state.setIntakeId("");
    });
    await act(async () => {
      await result.current.actions.handleAnswer();
    });
    expect(result.current.state.error).toBe("Create a PM session first.");

    await act(async () => {
      result.current.state.setIntakeId("pm-answer");
      result.current.state.setAnswers("answer-1");
    });
    mockAnswerIntake.mockRejectedValueOnce(new Error("answer failed"));
    await act(async () => {
      await result.current.actions.handleAnswer();
    });
    expect(result.current.state.error).toBe("Generate plan failed");

    mockAnswerIntake.mockResolvedValueOnce({ intake_id: "pm-answer", questions: ["q-next"] } as never);
    await act(async () => {
      await result.current.actions.handleAnswer();
    });
    expect(result.current.state.chatNotice).toBe("Answer saved. 1 clarifiers remaining.");
    expect(result.current.state.questions).toEqual(["q-next"]);
  });

  it("covers start-new-conversation busy fallback notice", async () => {
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
    });

    await act(async () => {
      await result.current.actions.handleStartNewConversation();
    });

    expect(result.current.state.newConversationNotice).toBe("New chat creation is already in progress. Please wait.");
  });
});
