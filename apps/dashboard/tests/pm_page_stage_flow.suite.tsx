import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  answerIntake: vi.fn(),
  createIntake: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchTaskPacks: vi.fn(),
  postPmSessionMessage: vi.fn(),
  previewIntake: vi.fn(),
  runIntake: vi.fn(),
}));

import PMIntakePage from "../app/pm/page";
import PMIntakeCenterPanel from "../app/pm/components/PMIntakeCenterPanel";
import PMIntakeLeftSidebar from "../app/pm/components/PMIntakeLeftSidebar";
import PMIntakeRightSidebar from "../app/pm/components/PMIntakeRightSidebar";
import {
  answerIntake,
  createIntake,
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessions,
  fetchTaskPacks,
  postPmSessionMessage,
  runIntake,
} from "../lib/api";

describe("pm page stage flow", () => {
  const mockCreateIntake = vi.mocked(createIntake);
  const mockAnswerIntake = vi.mocked(answerIntake);
  const mockRunIntake = vi.mocked(runIntake);
  const mockPostPmSessionMessage = vi.mocked(postPmSessionMessage);
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchTaskPacks = vi.mocked(fetchTaskPacks);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-history-1",
        status: "done",
        current_step: "verify",
        run_count: 1,
        running_runs: 0,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        latest_run_id: "run-history-1",
      },
    ]);
    mockFetchPmSession.mockResolvedValue({
      session: {
        pm_session_id: "pm-history-1",
        status: "done",
        run_count: 1,
        running_runs: 0,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
        latest_run_id: "run-history-1",
      },
      run_ids: ["run-history-1"],
      runs: [],
    });
    mockFetchPmSessionEvents.mockResolvedValue([]);
    mockCreateIntake.mockResolvedValue({
      intake_id: "pm-1",
      questions: ["Please add the acceptance criteria"],
    });
    mockAnswerIntake.mockResolvedValue({
      intake_id: "pm-1",
      questions: [],
      plan: { stage: "ready" },
      task_chain: { chain_id: "chain-1" },
    });
    mockRunIntake.mockResolvedValue({ run_id: "run-1" });
    mockPostPmSessionMessage.mockResolvedValue({ ok: true });
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

  it("switches discover -> clarify -> execute in primary stage action", async () => {
    // Keep this flow deterministic: we only validate draft-session stage progression here.
    mockFetchPmSessions.mockResolvedValueOnce([]);
    render(<PMIntakePage />);

    expect(await screen.findByRole("button", { name: /Start first request|Send first request/ }, { timeout: 30000 })).toBeInTheDocument();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/PM composer/i), { target: { value: "Create a session" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });

    await waitFor(() => {
      expect(mockCreateIntake).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole("button", { name: "Answer follow-up questions" })).toBeInTheDocument();

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/PM composer/i), { target: { value: "Acceptance criteria: pass the tests" } });
      fireEvent.click(screen.getByRole("button", { name: "Send" }));
    });

    await waitFor(() => {
      expect(mockAnswerIntake).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByRole("button", { name: /Send \/run to start execution|Monitor execution progress/ })).toBeInTheDocument();
  }, 45_000);

  it("maps historical done session into verify stage", async () => {
    render(<PMIntakePage />);
    const sessionBtn = await screen.findByTestId("pm-session-item-pm-history-1", undefined, {
      timeout: 30000,
    });
    await act(async () => {
      fireEvent.click(sessionBtn.closest("button") as HTMLButtonElement);
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Review results and decide" })).toBeInTheDocument();
    });
  });
});

describe("pm intake component branches", () => {
  function buildLeftSidebarProps(
    overrides: Partial<ComponentProps<typeof PMIntakeLeftSidebar>> = {},
  ): ComponentProps<typeof PMIntakeLeftSidebar> {
    return {
      intakeId: "",
      chatFlowBusy: false,
      newConversationBusy: false,
      onStartNewConversation: vi.fn(),
      workspacePath: "apps/dashboard",
      repoName: "cortexpilot",
      onWorkspacePathChange: vi.fn(),
      onRepoNameChange: vi.fn(),
      stage: "discover",
      sessionHistoryError: "",
      newConversationError: "",
      newConversationNotice: "",
      historyBusy: false,
      sessionHistory: [],
      onSessionSelect: vi.fn(),
      onFocusInput: vi.fn(),
      ...overrides,
    };
  }

  function buildCenterPanelProps(
    overrides: Partial<ComponentProps<typeof PMIntakeCenterPanel>> = {},
  ): ComponentProps<typeof PMIntakeCenterPanel> {
    const scrollNode = document.createElement("div");
    return {
      layoutMode: "dialog",
      onLayoutModeChange: vi.fn(),
      pmStageText: "Discover",
      pmJourneyContext: {
        stage: "discover",
        reason: "No intake has been created yet, so the session is still in discovery.",
        primaryAction: "Send the first request",
        secondaryActions: ["Add acceptance criteria"],
      },
      onPrimaryStageAction: vi.fn(),
      onFillTemplate: vi.fn(),
      chatFlowBusy: false,
      chatError: "",
      chatNotice: "",
      firstRunStage: "Next: enter the first request",
      headerHint: "I will auto-create the session from the first request",
      firstRunNextCta: "Send the first request",
      intakeId: "pm-1",
      chatHistoryBusy: false,
      chatLog: [
        {
          id: "chat-1",
          role: "CortexPilot Command Tower",
          text: "delegation message",
          createdAt: "2026-03-01T10:00:00.000Z",
          kind: "delegation",
          origin: "remote",
        },
      ],
      liveRole: "TECH_LEAD",
      hoveredChainRole: null,
      onHoveredChainRoleChange: vi.fn(),
      chatStickToBottom: true,
      chatUnreadCount: 0,
      onScrollToBottom: vi.fn(),
      workspaceBound: true,
      chatInput: "hello",
      onChatInputChange: vi.fn(),
      onSend: vi.fn(),
      chatBusy: false,
      onStopGeneration: vi.fn(),
      chatPlaceholder: "placeholder",
      chatInputRef: { current: null },
      chatLogRef: { current: scrollNode },
      onChatScroll: vi.fn(),
      chainNodes: [
        { role: "PM", label: "PM", hint: "hint", state: "done" },
        { role: "TECH_LEAD", label: "TL", hint: "hint", state: "active" },
      ],
      ...overrides,
    };
  }

  function buildRightSidebarProps(
    overrides: Partial<ComponentProps<typeof PMIntakeRightSidebar>> = {},
  ): ComponentProps<typeof PMIntakeRightSidebar> {
    return {
      pmJourneyContext: {
        stage: "discover",
        reason: "No intake has been created yet, so the session is still in discovery.",
        primaryAction: "Send the first request",
        secondaryActions: ["Add acceptance criteria"],
      },
      runId: "",
      intakeId: "pm-1",
      liveRole: "TECH_LEAD",
      currentSessionStatus: "failed",
      chainNodes: [
        { role: "PM", label: "PM", hint: "hint", state: "done" },
        { role: "TECH_LEAD", label: "TL", hint: "hint", state: "active" },
      ],
      hoveredChainRole: null,
      onHoveredChainRoleChange: vi.fn(),
      progressFeed: ["line-1"],
      questions: ["question-1"],
      requesterRole: "PM",
      onRequesterRoleChange: vi.fn(),
      browserPreset: "custom",
      onBrowserPresetChange: vi.fn(),
      canUseCustomPreset: true,
      customBrowserPolicy: "{\"stealth_mode\":\"none\"}",
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
      plan: { stage: "ready" },
      taskChain: { chain: "ok" },
      executionPlanPreview: null,
      executionPlanPreviewBusy: false,
      executionPlanPreviewError: "",
      chainPanelRef: { current: null },
      ...overrides,
    };
  }

  it("covers left sidebar inputs, draft focus, and session selection", async () => {
    const onWorkspacePathChange = vi.fn();
    const onRepoNameChange = vi.fn();
    const onStartNewConversation = vi.fn();
    const onFocusInput = vi.fn();
    const onSessionSelect = vi.fn();
    const props = buildLeftSidebarProps({
      onWorkspacePathChange,
      onRepoNameChange,
      onStartNewConversation,
      onFocusInput,
      onSessionSelect,
      sessionHistory: [
        {
          pm_session_id: "pm-history-1",
          status: "active",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 0,
          blocked_runs: 0,
          latest_run_id: "run-1",
          current_role: "PM",
          current_step: "plan",
          updated_at: "2026-03-01T10:00:00.000Z",
        },
      ],
    });

    const { rerender } = render(<PMIntakeLeftSidebar {...props} />);

    expect(screen.getByTestId("pm-sidebar-active-session-indicator")).toHaveTextContent("Current session: Draft (unsent)");
    expect(screen.getByRole("list", { name: "Session picker" })).toBeInTheDocument();
    expect(screen.getByTestId("pm-session-item-draft")).toHaveAttribute("aria-current", "page");

    const workspaceInput = screen.getByLabelText("Workspace path");
    const repoInput = screen.getByLabelText("Repository slug");
    expect(workspaceInput).toHaveClass("input");
    expect(repoInput).toHaveClass("input");

    fireEvent.change(screen.getByLabelText("Workspace path"), { target: { value: "apps/new" } });
    fireEvent.change(screen.getByLabelText("Repository slug"), { target: { value: "cortexpilot-next" } });
    expect(onWorkspacePathChange).toHaveBeenCalledWith("apps/new");
    expect(onRepoNameChange).toHaveBeenCalledWith("cortexpilot-next");

    fireEvent.click(screen.getByRole("button", { name: "+ New chat" }));
    expect(onStartNewConversation).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("pm-session-item-draft"));
    expect(onFocusInput).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("pm-session-item-pm-history-1"));
    expect(onSessionSelect).toHaveBeenCalledWith("pm-history-1");

    rerender(
      <PMIntakeLeftSidebar
        {...buildLeftSidebarProps({
          intakeId: "pm-history-1",
          sessionHistory: props.sessionHistory,
        })}
      />,
    );
    expect(screen.getByTestId("pm-session-item-draft")).not.toHaveAttribute("aria-current");
    expect(screen.getByTestId("pm-sidebar-active-session-indicator")).toHaveTextContent("Current session: pm-history-1");
    expect(screen.getByTestId("pm-session-item-pm-history-1")).toHaveAttribute("aria-current", "page");

    rerender(<PMIntakeLeftSidebar {...buildLeftSidebarProps({ historyBusy: true })} />);
    expect(screen.getByText("Loading session history")).toBeInTheDocument();
  });

  it("covers center panel keyboard link actions and inline chain expand action", () => {
    const onLayoutModeChange = vi.fn();
    const onHoveredChainRoleChange = vi.fn();
    const props = buildCenterPanelProps({ onLayoutModeChange, onHoveredChainRoleChange });

    render(<PMIntakeCenterPanel {...props} />);

    const linkedMessage = screen.getByRole("button", { name: "Highlight messages linked to TECH_LEAD" });
    fireEvent.keyDown(linkedMessage, { key: "Enter" });
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith("TECH_LEAD");

    fireEvent.keyDown(linkedMessage, { key: "Escape" });
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith(null);

    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(onLayoutModeChange).toHaveBeenCalledWith("split");
  });

  it("covers right sidebar chain node keydown branches and custom policy editor", () => {
    const onHoveredChainRoleChange = vi.fn();
    const onCustomBrowserPolicyChange = vi.fn();
    const props = buildRightSidebarProps({ onHoveredChainRoleChange, onCustomBrowserPolicyChange });
    render(<PMIntakeRightSidebar {...props} />);

    const tlNode = screen.getByRole("button", { name: /TL/ });
    fireEvent.keyDown(tlNode, { key: "Enter" });
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith("TECH_LEAD");

    fireEvent.keyDown(tlNode, { key: "Escape" });
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith(null);

    fireEvent.change(screen.getByLabelText("Custom browser policy JSON"), {
      target: { value: "{\"mode\":\"safe\"}" },
    });
    expect(onCustomBrowserPolicyChange).toHaveBeenCalledWith("{\"mode\":\"safe\"}");
    expect(screen.getByText("Runtime")).toBeInTheDocument();
  });
});
