import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "../components/conversation/ChatPanel";
import { NodeDetailDrawer } from "../components/chain/NodeDetailDrawer";
import { AgentsPage } from "./AgentsPage";
import { CTSessionDetailPage } from "./CTSessionDetailPage";
import { ChangeGatesPage } from "./ChangeGatesPage";
import { CommandTowerPage } from "./CommandTowerPage";
import { ContractsPage } from "./ContractsPage";
import { EventsPage } from "./EventsPage";
import { GodModePage } from "./GodModePage";
import { LocksPage } from "./LocksPage";
import { OverviewPage } from "./OverviewPage";
import { PoliciesPage } from "./PoliciesPage";
import { ReviewsPage } from "./ReviewsPage";
import { TestsPage } from "./TestsPage";
import { WorkflowDetailPage } from "./WorkflowDetailPage";
import { WorkflowsPage } from "./WorkflowsPage";
import { WorktreesPage } from "./WorktreesPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../lib/api", () => ({
  fetchAgents: vi.fn(),
  fetchAgentStatus: vi.fn(),
  fetchRoleConfig: vi.fn(),
  previewRoleConfig: vi.fn(),
  applyRoleConfig: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
  fetchCommandTowerOverview: vi.fn(),
  fetchCommandTowerAlerts: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
  postPmSessionMessage: vi.fn(),
  previewFlightPlanCopilotBrief: vi.fn(),
  openEventsStream: vi.fn(() => ({ close: vi.fn() })),
  fetchDiffGate: vi.fn(),
  fetchContracts: vi.fn(),
  fetchAllEvents: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  fetchQueue: vi.fn(),
  fetchLocks: vi.fn(),
  fetchPolicies: vi.fn(),
  fetchReviews: vi.fn(),
  fetchTests: vi.fn(),
  enqueueRunQueue: vi.fn(),
  fetchWorkflow: vi.fn(),
  fetchWorkflows: vi.fn(),
  fetchWorktrees: vi.fn(),
  fetchRuns: vi.fn(),
  runNextQueue: vi.fn(),
}));

import {
  fetchAgents,
  fetchAgentStatus,
  fetchRoleConfig,
  previewRoleConfig,
  applyRoleConfig,
  mutationExecutionCapability,
  fetchCommandTowerOverview,
  fetchCommandTowerAlerts,
  fetchPmSessions,
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessionConversationGraph,
  fetchPmSessionMetrics,
  previewFlightPlanCopilotBrief,
  fetchDiffGate,
  fetchContracts,
  fetchAllEvents,
  fetchPendingApprovals,
  fetchQueue,
  fetchLocks,
  fetchPolicies,
  fetchReviews,
  fetchTests,
  enqueueRunQueue,
  fetchWorkflow,
  fetchWorkflows,
  fetchWorktrees,
  fetchRuns,
  runNextQueue,
} from "../lib/api";

function readCssBundle(entryPath: string, visited: Set<string> = new Set()): string {
  if (!existsSync(entryPath) || visited.has(entryPath)) {
    return "";
  }
  visited.add(entryPath);
  const css = readFileSync(entryPath, "utf8");
  const imports = [...css.matchAll(/@import\s+["'](.+?)["'];/g)];
  let bundledCss = css;
  for (const match of imports) {
    const importTarget = match[1];
    if (!importTarget.endsWith(".css")) {
      continue;
    }
    bundledCss += `\n${readCssBundle(resolve(dirname(entryPath), importTarget), visited)}`;
  }
  return bundledCss;
}

describe("desktop p1 controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchQueue).mockResolvedValue([] as any);
    vi.mocked(enqueueRunQueue).mockResolvedValue({ ok: true } as any);
    vi.mocked(runNextQueue).mockResolvedValue({ ok: false, reason: "queue empty" } as any);

    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    Object.defineProperty(URL, "createObjectURL", {
      value: vi.fn(() => "blob:mock"),
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: vi.fn(),
      configurable: true,
    });

    vi.mocked(fetchAgents).mockResolvedValue({ agents: [] } as any);
    vi.mocked(fetchAgentStatus).mockResolvedValue({ agents: [] } as any);
    vi.mocked(fetchRoleConfig).mockResolvedValue({
      authority: "repo-owned-role-config",
      persisted_source: "policies/role_config_registry.json",
      overlay_state: "repo-owned-defaults",
      field_modes: {
        purpose: "reserved-for-later",
        system_prompt_ref: "editable-now",
        skills_bundle_ref: "editable-now",
        mcp_bundle_ref: "editable-now",
        runtime_binding: "editable-now",
        role_binding_summary: "derived-read-only",
        role_binding_read_model: "derived-read-only",
        workflow_case_read_model: "derived-read-only",
        execution_authority: "authority-source",
      },
      editable_now: {
        system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md",
        skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
        mcp_bundle_ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
        runtime_binding: { runner: null, provider: null, model: null },
      },
      registry_defaults: {
        system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md",
        skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
        mcp_bundle_ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
        runtime_binding: { runner: null, provider: null, model: null },
      },
      persisted_values: {
        system_prompt_ref: "policies/agents/codex/roles/50_worker_core.md",
        skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
        mcp_bundle_ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
        runtime_binding: { runner: null, provider: null, model: null },
      },
      validation: "fail-closed",
      preview_supported: true,
      apply_supported: true,
      execution_authority: "task_contract",
      runtime_capability: {
        status: "previewable",
        lane: "standard-provider-path",
        compat_api_mode: "responses",
        provider_status: "unresolved",
        provider_inventory_id: null,
        tool_execution: "provider-path-required",
        notes: [
          "Chat-style compatibility may differ from tool-execution capability.",
          "Execution authority remains task_contract even when role defaults change.",
        ],
      },
    } as any);
    vi.mocked(previewRoleConfig).mockResolvedValue({
      role: "WORKER",
      authority: "repo-owned-role-config",
      validation: "fail-closed",
      can_apply: true,
      current_surface: {} as any,
      preview_surface: {
        runtime_capability: {
          lane: "standard-provider-path",
          tool_execution: "provider-path-required",
        },
      } as any,
      changes: [],
    } as any);
    vi.mocked(applyRoleConfig).mockResolvedValue({ role: "WORKER", saved: true, surface: {} } as any);
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: false, operatorRole: null } as any);
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 2,
      active_sessions: 1,
      failed_sessions: 1,
      blocked_sessions: 0,
      failed_ratio: 0.2,
      generated_at: "2026-02-19T00:00:00Z",
    } as any);
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({ status: "healthy", alerts: [] } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-1",
        objective: "obj",
        status: "active",
        run_count: 1,
        success_runs: 0,
        failed_runs: 0,
        blocked_runs: 0,
        running_runs: 1,
        updated_at: "2026-02-19T00:00:00Z",
      },
    ] as any);
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "" },
      runs: [],
    } as any);
    vi.mocked(fetchPmSessionEvents).mockResolvedValue([] as any);
    vi.mocked(fetchPmSessionConversationGraph).mockResolvedValue({ nodes: [], edges: [] } as any);
    vi.mocked(fetchPmSessionMetrics).mockResolvedValue({
      run_count: 0,
      running_runs: 0,
      failed_runs: 0,
      blocked_runs: 0,
      failure_rate: 0,
      mttr_seconds: 0,
    } as any);

    vi.mocked(fetchDiffGate).mockResolvedValue([] as any);
    vi.mocked(fetchContracts).mockResolvedValue([] as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([] as any);
    vi.mocked(fetchPendingApprovals).mockResolvedValue([] as any);
    vi.mocked(fetchLocks).mockResolvedValue([] as any);
    vi.mocked(fetchPolicies).mockResolvedValue({} as any);
    vi.mocked(fetchReviews).mockResolvedValue([] as any);
    vi.mocked(fetchTests).mockResolvedValue([] as any);
    vi.mocked(fetchWorkflow).mockResolvedValue({
      workflow: { workflow_id: "wf-001", status: "running" },
      runs: [],
      events: [],
    } as any);
    vi.mocked(fetchWorkflows).mockResolvedValue([] as any);
    vi.mocked(fetchWorktrees).mockResolvedValue([] as any);
    vi.mocked(fetchRuns).mockResolvedValue([] as any);
    vi.mocked(previewFlightPlanCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "flight_plan",
      subject_id: "pm-1",
      intake_id: "pm-1",
      status: "OK",
      summary: "The plan is bounded but still needs one final human review on scope and approval risk.",
      likely_cause: "Manual approval posture and scope boundary are the main pre-run gates.",
      compare_takeaway: "Capability triggers show why this plan needs search and approval review before the first run.",
      proof_takeaway: "Expected reports and artifacts are defined before execution starts.",
      incident_takeaway: "Warnings mark the first places where execution could fail.",
      queue_takeaway: "Scope and assigned role are aligned with the previewed plan.",
      approval_takeaway: "Manual approval is likely before execution finishes.",
      recommended_actions: ["Confirm the highest-risk gate before starting execution."],
      top_risks: ["Manual approval likely"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as any);
  });

  it("covers ChatPanel refresh and NodeDetailDrawer raw toggle controls", async () => {
    const refreshNow = vi.fn();
    const onToggleRaw = vi.fn();

    render(
      <>
        <ChatPanel
          onboardingVisible={false}
          dismissOnboarding={vi.fn()}
          isOffline={false}
          liveError=""
          workspace={{ id: "w1", repo: "openvibecoding-core", branch: "main", path: ".", activeAgents: 1 }}
          activeSessionId="pm-1"
          activeSessionGenerating={false}
          phaseText="phase"
          refreshNow={refreshNow}
          drawerVisible={true}
          drawerPinned={true}
          setDrawerVisible={vi.fn()}
          setDrawerPinned={vi.fn()}
          activeTimeline={[]}
          chatThreadRef={{ current: null }}
          streamingText=""
          reportActions={{}}
          creatingFirstSession={false}
          firstSessionBootstrapError=""
          firstSessionAllowedPath="."
          onCreateFirstSession={vi.fn()}
          onOpenSessionFallback={vi.fn()}
          chooseDecision={vi.fn()}
          recoverableDraft={null}
          restoreDraft={vi.fn()}
          discardDraft={vi.fn()}
          composerRef={{ current: null }}
          composerInput=""
          setComposerInput={vi.fn()}
          onComposerEnterSend={vi.fn()}
          composerPlaceholder="placeholder"
          composerLength={0}
          composerMaxChars={4000}
          composerOverLimit={false}
          canSend={false}
          sendDisabledReason="请输入消息后发送"
          starterPrompts={[]}
          onApplyStarterPrompt={vi.fn()}
          hasActiveGeneration={false}
          stopGeneration={vi.fn()}
          isUserNearBottom={true}
          unreadCount={0}
          onBackToBottom={vi.fn()}
        />
        <NodeDetailDrawer
          open
          selectedNodeId="n1"
          selectedNode={{ id: "n1", data: { label: "N1", role: "Worker", status: "running", subtitle: "s" } } as any}
          reviewDecision="pending"
          showRawNodeOutput={false}
          nodeRawOutput="raw"
          onClose={vi.fn()}
          onToggleRaw={onToggleRaw}
          onOpenDiff={vi.fn()}
        />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /立即刷新|Refresh now/ }));
    expect(refreshNow).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /查看原始输出|Show raw output/ }));
    expect(onToggleRaw).toHaveBeenCalled();
  });

  it("renders Flight Plan copilot in desktop preview mode", async () => {
    const onPreviewFirstSession = vi.fn();

    render(
      <ChatPanel
        onboardingVisible={false}
        dismissOnboarding={vi.fn()}
        isOffline={false}
        liveError=""
        workspace={{ id: "w1", repo: "openvibecoding-core", branch: "main", path: ".", activeAgents: 1 }}
        activeSessionId=""
        activeSessionGenerating={false}
        phaseText="phase"
        refreshNow={vi.fn()}
        drawerVisible={false}
        drawerPinned={false}
        setDrawerVisible={vi.fn()}
        setDrawerPinned={vi.fn()}
        activeTimeline={[]}
        chatThreadRef={{ current: null }}
        streamingText=""
        reportActions={{}}
        creatingFirstSession={false}
        firstSessionBootstrapError=""
        firstSessionAllowedPath="."
        executionPlanPreview={{
          report_type: "execution_plan_report",
          generated_at: "2026-03-31T12:00:00Z",
          objective: "Queue the next workflow case run safely.",
          summary: "Preview the next governed run before execution starts.",
          questions: [],
          warnings: ["Manual approval may be required"],
          notes: ["Preview only; run truth starts after execution."],
          assigned_role: "TECH_LEAD",
          allowed_paths: ["apps/dashboard", "apps/orchestrator/src"],
          acceptance_tests: [{ cmd: "pnpm --dir apps/dashboard test:target tests/workflow_detail_page.test.tsx" }],
          search_queries: ["workflow queue posture"],
          predicted_reports: ["task_result.json"],
          predicted_artifacts: ["patch.diff"],
          requires_human_approval: true,
          contract_preview: {},
        }}
        executionPlanPreviewLoading={false}
        executionPlanPreviewError=""
        onCreateFirstSession={vi.fn()}
        onOpenSessionFallback={vi.fn()}
        onPreviewFirstSession={onPreviewFirstSession}
        chooseDecision={vi.fn()}
        recoverableDraft={null}
        restoreDraft={vi.fn()}
        discardDraft={vi.fn()}
        composerRef={{ current: null }}
        composerInput=""
        setComposerInput={vi.fn()}
        onComposerEnterSend={vi.fn()}
        composerPlaceholder="placeholder"
        composerLength={0}
        composerMaxChars={4000}
        composerOverLimit={false}
        canSend={false}
        sendDisabledReason="请输入消息后发送"
        starterPrompts={[]}
        onApplyStarterPrompt={vi.fn()}
        hasActiveGeneration={false}
        stopGeneration={vi.fn()}
        isUserNearBottom={true}
        unreadCount={0}
        onBackToBottom={vi.fn()}
      />,
    );

    expect(screen.getByText("Flight Plan copilot")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Explain this Flight Plan" }));
    await waitFor(() => {
      expect(previewFlightPlanCopilotBrief).toHaveBeenCalledTimes(1);
    });
  });

  it("covers command tower and ct-session p1 controls", async () => {
    const onBack = vi.fn();
    const onNavigateToSession = vi.fn();

    const commandTower = render(<CommandTowerPage onNavigateToSession={onNavigateToSession} />);
    expect(await screen.findByRole("heading", { name: /指挥塔|Command Tower/ })).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /更新进展|Refresh progress/ }));
    fireEvent.click(screen.getByRole("button", { name: /暂停自动更新|Pause auto-refresh/ }));
    fireEvent.click(screen.getByRole("button", { name: /展开专家信息|Show advanced detail/ }));
    fireEvent.click(screen.getByRole("button", { name: /应用|Apply/ }));
    fireEvent.click(screen.getByRole("button", { name: /重置|Reset/ }));
    const focusToggleGroup = screen.getByRole("group", { name: /聚焦视图切换|Focus view switcher/ });
    fireEvent.click(within(focusToggleGroup).getByRole("button", { name: /^(全部|All)/ }));
    commandTower.unmount();

    render(<CTSessionDetailPage sessionId="pm-1" onBack={onBack} />);
    expect(await screen.findByRole("heading", { name: /会话透视|Session detail/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /< 返回会话总览|< Back to session overview/ }));
    expect(onBack).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /暂停实时|Pause live/ }));
    expect(screen.getByRole("button", { name: /恢复实时|Resume live/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /手动刷新|Refresh now/ }));
    await waitFor(() => expect(fetchPmSession).toHaveBeenCalled());
  });

  it("covers refresh/back controls across desktop pages", async () => {
    const onNavigate = vi.fn();

    const agents = render(<AgentsPage />);
    expect(await screen.findByRole("heading", { name: /角色桌|Role desk|代理|Agents/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchAgents).toHaveBeenCalledTimes(2));
    agents.unmount();

    const changeGates = render(<ChangeGatesPage />);
    expect(await screen.findByRole("heading", { name: /变更门禁|Diff gate/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchDiffGate).toHaveBeenCalledTimes(2));
    changeGates.unmount();

    const contracts = render(<ContractsPage />);
    expect(await screen.findByRole("heading", { name: /合约桌|Contract desk|合约|Contracts/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchContracts).toHaveBeenCalledTimes(2));
    contracts.unmount();

    const events = render(<EventsPage />);
    expect(await screen.findByRole("heading", { name: /事件流|Events/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchAllEvents).toHaveBeenCalledTimes(2));
    events.unmount();

    const godMode = render(<GodModePage />);
    expect(await screen.findByRole("heading", { name: /快速审批|Quick approval/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchPendingApprovals).toHaveBeenCalledTimes(2));
    godMode.unmount();

    const locks = render(<LocksPage />);
    expect(await screen.findByRole("heading", { name: /锁管理|Locks/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchLocks).toHaveBeenCalledTimes(2));
    locks.unmount();

    const overview = render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: /指挥面总览|Command deck overview|新手起步|Operator overview/ })).toBeInTheDocument();
    const recentExceptionsSection = screen.getByRole("region", { name: /最近异常|Recent exceptions/ });
    fireEvent.click(within(recentExceptionsSection).getByRole("button", { name: /查看全部异常|View all exceptions/ }));
    expect(onNavigate).toHaveBeenCalledWith("events");
    fireEvent.click(screen.getByRole("button", { name: /刷新数据|Refresh data/ }));
    await waitFor(() => expect(fetchCommandTowerOverview).toHaveBeenCalledTimes(2));
    overview.unmount();

    const policies = render(<PoliciesPage />);
    expect(await screen.findByRole("heading", { name: /策略|Policies/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchPolicies).toHaveBeenCalledTimes(2));
    policies.unmount();

    const reviews = render(<ReviewsPage />);
    expect(await screen.findByRole("heading", { name: /评审|Reviews/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchReviews).toHaveBeenCalledTimes(2));
    reviews.unmount();

    const tests = render(<TestsPage />);
    expect(await screen.findByRole("heading", { name: /测试|Tests/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchTests).toHaveBeenCalledTimes(2));
    tests.unmount();

    const wfDetailOnBack = vi.fn();
    const workflowDetail = render(<WorkflowDetailPage workflowId="wf-001" onBack={wfDetailOnBack} onNavigateToRun={vi.fn()} />);
    expect(await screen.findByText("wf-001")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /返回工作流列表|Back to workflow list/ }));
    expect(wfDetailOnBack).toHaveBeenCalled();
    workflowDetail.unmount();

    const workflows = render(<WorkflowsPage onNavigateToWorkflow={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: /工作流|Workflow Cases/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchWorkflows).toHaveBeenCalledTimes(2));
    workflows.unmount();

    const worktrees = render(<WorktreesPage />);
    expect(await screen.findByRole("heading", { name: /工作树|Worktrees/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => expect(fetchWorktrees).toHaveBeenCalledTimes(2));
    worktrees.unmount();
  });

  it("renders role configuration desk in preview-only mode and calls preview", async () => {
    vi.mocked(fetchAgents).mockResolvedValueOnce({
      agents: [{ agent_id: "agent-1", role: "WORKER", lock_count: 0, locked_paths: [] }],
      locks: [],
      role_catalog: [
        {
          role: "WORKER",
          purpose: "Execute the contracted change inside allowed_paths and produce structured evidence.",
          role_binding_read_model: {
            authority: "contract-derived-read-model",
            source: "derived from compiled role_contract and runtime inputs; not an execution authority surface",
            execution_authority: "task_contract",
            skills_bundle_ref: { status: "resolved", ref: "a", bundle_id: "b", resolved_skill_set: [], validation: "fail-closed" },
            mcp_bundle_ref: { status: "resolved", ref: "c", resolved_mcp_tool_set: [], validation: "fail-closed" },
            runtime_binding: {
              status: "unresolved",
              authority_scope: "contract-derived-read-model",
              source: { runner: "unresolved", provider: "unresolved", model: "unresolved" },
              summary: { runner: null, provider: null, model: null },
            },
          },
          registered_agent_count: 1,
          locked_agent_count: 0,
        },
      ],
    } as any);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as any);

    render(<AgentsPage />);
    expect(await screen.findByText("Role configuration desk")).toBeInTheDocument();
    expect(screen.getByText("Preview is available, but saving defaults requires an operator role.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview defaults" }));
    await waitFor(() => expect(previewRoleConfig).toHaveBeenCalledTimes(1));
  });

  it("keeps contrast-safe muted and badge text tokens in desktop styles", () => {
    const cssPathCandidates = [
      (() => {
        try {
          return fileURLToPath(new URL("../styles.css", import.meta.url));
        } catch {
          return "";
        }
      })(),
      resolve(process.cwd(), "src/styles.css"),
      resolve(process.cwd(), "apps/desktop/src/styles.css"),
    ].filter(Boolean);
    const cssPath = cssPathCandidates.find((candidate) => existsSync(candidate));
    expect(cssPath).not.toBeUndefined();
    const css = readCssBundle(cssPath as string);

    expect(css).toContain("--color-text-muted: #6b7280;");
    expect(css).toContain("--color-success-ink: #065f46;");
    expect(css).toContain("--color-warning-ink: #92400e;");
    expect(css).toContain("--color-danger-ink: #b91c1c;");
    expect(css).toContain(".quick-card-desc");
    expect(css).toContain(".badge--muted");
    expect(css).toContain(".sidebar-link");
  });
});
