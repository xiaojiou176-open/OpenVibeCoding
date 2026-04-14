import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchFlightPlanCopilotBrief: vi.fn(),
  previewFlightPlanCopilotBrief: vi.fn(),
}));

import PMIntakeCenterPanel from "../app/pm/components/PMIntakeCenterPanel";
import PMIntakeRightSidebar from "../app/pm/components/PMIntakeRightSidebar";
import type { ChainNode, ChatItem } from "../app/pm/components/PMIntakeFeature.shared";
import { previewFlightPlanCopilotBrief } from "../lib/api";

function createJourneyContext(stage: "discover" | "clarify" | "execute" | "verify" = "discover") {
  return {
    stage,
    reason: "stage reason",
    primaryAction: "Continue to the next step",
    secondaryActions: [] as string[],
  };
}

function createChainNodes(): ChainNode[] {
  return [
    { role: "PM", label: "PM", hint: "Entry", state: "done" },
    { role: "TECH_LEAD", label: "TL", hint: "Break down", state: "active" },
    { role: "WORKER", label: "Worker pool", hint: "Execute", state: "idle" },
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
    firstRunNextCta: "Send first request",
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
    progressFeed: ["line-1"],
    questions: ["question-1"],
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
    plan: { stage: "ready" },
    taskChain: { chain: "ok" },
    executionPlanPreview: null,
    executionPlanPreviewBusy: false,
    executionPlanPreviewError: "",
    chainPanelRef: createRef<HTMLElement>(),
  };
  return { ...base, ...overrides };
}

describe("pm intake center panel component branches", () => {
  it("uses discover-stage wording that matches focus-first behavior", () => {
    render(<PMIntakeCenterPanel {...createCenterProps({ intakeId: "", chatInput: "" })} />);
    expect(screen.getByTestId("pm-stage-primary-action")).toHaveTextContent("Start first request");
    expect(screen.getByTestId("pm-context-primary-action")).toHaveTextContent("Next: enter the first request");
  });

  it("uses the first-send shortcut when discover stage input is already ready", () => {
    const onSend = vi.fn();
    const onFillTemplate = vi.fn();
    render(
      <PMIntakeCenterPanel
        {...createCenterProps({
          intakeId: "",
          chatInput: "ready to send",
          onSend,
          onFillTemplate,
        })}
      />,
    );

    fireEvent.click(screen.getByTestId("pm-context-send-first"));
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onFillTemplate).not.toHaveBeenCalled();
  });

  it("renders loading and empty states for chat-first flow", () => {
    const { rerender, container } = render(
      <PMIntakeCenterPanel {...createCenterProps()} />
    );
    rerender(<PMIntakeCenterPanel {...createCenterProps({ chatHistoryBusy: true })} />);
    expect(container.querySelector(".skeleton-chat-loading-primary")).not.toBeNull();

    rerender(<PMIntakeCenterPanel {...createCenterProps({ chatHistoryBusy: false, intakeId: "" })} />);
    expect(screen.getByText("No session yet. Send the first request")).toBeInTheDocument();

    rerender(<PMIntakeCenterPanel {...createCenterProps({ intakeId: "pm-1" })} />);
    expect(screen.getByText("No messages in this session yet")).toBeInTheDocument();
  });

  it("handles message hover/keyboard linking, composer controls, and dialog expand", () => {
    const onHoveredChainRoleChange = vi.fn();
    const onSend = vi.fn();
    const onScrollToBottom = vi.fn();
    const onLayoutModeChange = vi.fn();
    const onStopGeneration = vi.fn();
    const chatLog: ChatItem[] = [
      {
        id: "m1",
        role: "PM",
        text: "first",
        createdAt: "2026-03-01T10:00:00.000Z",
        kind: "message",
        origin: "local",
      },
      {
        id: "m2",
        role: "OpenVibeCoding Command Tower",
        text: "second",
        createdAt: "2026-03-01T10:10:00.000Z",
        kind: "progress",
        origin: "remote",
      },
    ];

    const { rerender } = render(
      <PMIntakeCenterPanel
        {...createCenterProps({
          chatLog,
          onHoveredChainRoleChange,
          onSend,
          onScrollToBottom,
          onLayoutModeChange,
          chatStickToBottom: false,
          chatUnreadCount: 3,
          chatInput: "hello",
          onStopGeneration,
        })}
      />,
    );

    const linkedMessage = screen.getByRole("button", { name: "Highlight messages linked to WORKER" });
    fireEvent.mouseEnter(linkedMessage);
    fireEvent.focus(linkedMessage);
    fireEvent.keyDown(linkedMessage, { key: "Enter" });
    fireEvent.keyDown(linkedMessage, { key: " " });
    fireEvent.keyDown(linkedMessage, { key: "Escape" });
    fireEvent.blur(linkedMessage);
    fireEvent.mouseLeave(linkedMessage);
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith("WORKER");
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith(null);
    expect(screen.getByRole("note")).toHaveTextContent("10 min");

    fireEvent.click(screen.getByRole("button", { name: "Back to bottom, 3 new messages" }));
    expect(onScrollToBottom).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(onLayoutModeChange).toHaveBeenCalledWith("split");

    fireEvent.keyDown(screen.getByLabelText("PM composer"), {
      key: "Enter",
      shiftKey: false,
      nativeEvent: { isComposing: false },
    });
    expect(onSend).toHaveBeenCalledTimes(1);

    rerender(
      <PMIntakeCenterPanel
        {...createCenterProps({
          workspaceBound: false,
          chatBusy: true,
          chatInput: "no-send",
          onSend,
          onStopGeneration,
        })}
      />,
    );
    expect(screen.getByText("Select a workspace to start")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop generation" }));
    expect(onStopGeneration).toHaveBeenCalledTimes(1);
  });

  it("hides verbose layout feedback chip outside dialog mode", () => {
    render(<PMIntakeCenterPanel {...createCenterProps({ layoutMode: "chain" })} />);
    expect(screen.queryByTestId("pm-center-layout-feedback")).toBeNull();
  });
});

describe("pm intake right sidebar component branches", () => {
  it("covers chain node keyboard/mouse transitions and custom policy editor", () => {
    const onHoveredChainRoleChange = vi.fn();
    const onCustomBrowserPolicyChange = vi.fn();
    const onRequesterRoleChange = vi.fn();
    const onBrowserPresetChange = vi.fn();
    const onCreate = vi.fn();
    const onAnswer = vi.fn();
    const onRun = vi.fn();

    render(
      <PMIntakeRightSidebar
        {...createSidebarProps({
          currentSessionStatus: "failed",
          hoveredChainRole: "PM",
          onHoveredChainRoleChange,
          browserPreset: "custom",
          canUseCustomPreset: true,
          customBrowserPolicy: "{\"mode\":\"none\"}",
          onCustomBrowserPolicyChange,
          onRequesterRoleChange,
          onBrowserPresetChange,
          onCreate,
          onAnswer,
          onRun,
          error: "boom",
        })}
      />,
    );

    const tlNode = screen.getByRole("button", { name: /TL/i });
    fireEvent.mouseEnter(tlNode);
    fireEvent.focus(tlNode);
    fireEvent.keyDown(tlNode, { key: "Enter" });
    fireEvent.keyDown(tlNode, { key: " " });
    fireEvent.keyDown(tlNode, { key: "Escape" });
    fireEvent.blur(tlNode);
    fireEvent.mouseLeave(tlNode);
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith("TECH_LEAD");
    expect(onHoveredChainRoleChange).toHaveBeenCalledWith(null);

    fireEvent.change(screen.getByLabelText("Requester role"), { target: { value: "OPS" } });
    fireEvent.change(screen.getByLabelText("Browser preset"), { target: { value: "aggressive" } });
    fireEvent.change(screen.getByLabelText("Custom browser policy JSON"), { target: { value: "{\"mode\":\"plugin\"}" } });
    expect(onRequesterRoleChange).toHaveBeenCalledWith("OPS");
    expect(onBrowserPresetChange).toHaveBeenCalledWith("aggressive");
    expect(onCustomBrowserPolicyChange).toHaveBeenCalledWith("{\"mode\":\"plugin\"}");

    expect(screen.getAllByText("failed").length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: "Generate questions" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate plan" }));
    fireEvent.click(screen.getByRole("button", { name: "Start execution" }));
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it("renders Flight Plan as a sign-off checklist instead of raw JSON only", () => {
    vi.mocked(previewFlightPlanCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "flight_plan",
      subject_id: "pm-1",
      intake_id: "pm-1",
      status: "OK",
      summary: "The current Flight Plan is safe to review but still has one approval gate to confirm.",
      likely_cause: "Manual approval is the dominant pre-run risk gate.",
      compare_takeaway: "Search and approval triggers exist because this plan needs external evidence and a protected execution path.",
      proof_takeaway: "The plan already predicts reports and artifacts that should be reviewed before execution.",
      incident_takeaway: "The first likely failure point is a policy mismatch before execution starts.",
      queue_takeaway: "The scope boundary is narrow and stays inside apps/dashboard.",
      approval_takeaway: "Manual approval is likely before completion.",
      recommended_actions: ["Confirm the approval expectation before starting execution."],
      top_risks: ["Manual approval likely"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as never);
    render(
      <PMIntakeRightSidebar
        {...createSidebarProps({
          executionPlanPreview: {
            report_type: "execution_plan_report",
            generated_at: "2026-03-31T12:00:00Z",
            objective: "Queue the latest workflow case run",
            summary: "The next run will operate inside apps/dashboard and publish queue-side evidence.",
            questions: [],
            warnings: ["Manual approval may be required"],
            notes: ["This preview is advisory and not run truth."],
            assigned_role: "TECH_LEAD",
            allowed_paths: ["apps/dashboard", "apps/orchestrator/src"],
            acceptance_tests: [{ cmd: "pnpm --dir apps/dashboard test:target tests/workflows_queue_page.test.tsx" }],
            search_queries: ["workflow queue mutation"],
            predicted_reports: ["task_result.json", "review_report.json"],
            predicted_artifacts: ["queue.jsonl", "patch.diff"],
            requires_human_approval: true,
            wave_plan: {
              wave_id: "bundle-preview-1",
              execution_mode: "long_running",
              worker_count: 1,
              wake_policy_ref: "policies/control_plane_runtime_policy.json#/wake_policy",
              completion_policy_ref: "policies/control_plane_runtime_policy.json#/wave_completion_policy",
            },
            worker_prompt_contracts: [
              {
                prompt_contract_id: "worker-prompt-1",
                assigned_agent: { role: "WORKER", agent_id: "agent-1" },
                scope: "Queue the latest workflow case run",
                verification_requirements: ["repo_hygiene"],
              },
            ],
            unblock_tasks: [
              {
                unblock_task_id: "unblock-worker-prompt-1",
                owner: "L0",
                mode: "independent_temporary_task",
                trigger: "spawn_independent_temporary_unblock_task",
              },
            ],
            contract_preview: {
              assigned_agent: { role: "WORKER", agent_id: "agent-1" },
              owner_agent: { role: "TECH_LEAD", agent_id: "agent-2" },
            },
          },
        })}
      />,
    );

    expect(screen.getByText(/Advisory only: use this checklist to understand the planned contract and gates before starting execution/i)).toBeInTheDocument();
    expect(screen.getByText("Flight Plan copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain this Flight Plan" })).toBeInTheDocument();
    expect(screen.getByText("Sign-off checklist")).toBeInTheDocument();
    expect(screen.getByText(/Contract summary: Queue the latest workflow case run/)).toBeInTheDocument();
    expect(screen.getByText(/Acceptance checks:/)).toBeInTheDocument();
    expect(screen.getByText(/Capability triggers: Search \(1 query\), Manual approval/)).toBeInTheDocument();
    expect(screen.getByText("Operator notes")).toBeInTheDocument();
    expect(screen.getByText("Risk gates")).toBeInTheDocument();
    expect(screen.getByText("Wave plan snapshot")).toBeInTheDocument();
    expect(screen.getByText(/Wave ID: bundle-preview-1/)).toBeInTheDocument();
    expect(screen.getByText("Worker prompt contracts")).toBeInTheDocument();
    expect(screen.getByText(/^worker-prompt-1$/)).toBeInTheDocument();
    expect(screen.getByText("Unblock task candidates")).toBeInTheDocument();
    expect(screen.getByText(/unblock-worker-prompt-1/)).toBeInTheDocument();
    expect(screen.getByText("Contract preview excerpts")).toBeInTheDocument();
    expect(screen.getByText("Advanced planning payloads")).toBeInTheDocument();
  });
});
