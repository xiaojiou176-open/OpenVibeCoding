import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NodeDetailDrawer } from "../components/chain/NodeDetailDrawer";
import { DiffReviewModal } from "../components/review/DiffReviewModal";
import { ChangeGatesPage } from "./ChangeGatesPage";
import { CommandTowerPage } from "./CommandTowerPage";
import { EventsPage } from "./EventsPage";
import { GodModePage } from "./GodModePage";
import { OverviewPage } from "./OverviewPage";
import { RunsPage } from "./RunsPage";
import { SearchPage } from "./SearchPage";
import { WorkflowDetailPage } from "./WorkflowDetailPage";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchRuns: vi.fn(),
  fetchAllEvents: vi.fn(),
  fetchRunSearch: vi.fn(),
  promoteEvidence: vi.fn(),
  fetchQueue: vi.fn(),
  enqueueRunQueue: vi.fn(),
  fetchWorkflow: vi.fn(),
  fetchDiffGate: vi.fn(),
  fetchDiff: vi.fn(),
  rollbackRun: vi.fn(),
  rejectRun: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  approveGodMode: vi.fn(),
  fetchCommandTowerAlerts: vi.fn(),
  fetchPmSessions: vi.fn(),
  runNextQueue: vi.fn(),
}));

import {
  fetchCommandTowerOverview,
  fetchRuns,
  fetchAllEvents,
  fetchRunSearch,
  promoteEvidence,
  fetchQueue,
  enqueueRunQueue,
  fetchWorkflow,
  fetchDiffGate,
  fetchDiff,
  rollbackRun,
  rejectRun,
  fetchPendingApprovals,
  approveGodMode,
  fetchCommandTowerAlerts,
  fetchPmSessions,
  runNextQueue,
} from "../lib/api";

describe("desktop p0 misc controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 2,
      active_sessions: 1,
      failed_ratio: 0.1,
      blocked_sessions: 1,
      generated_at: "2026-02-19T00:00:00Z",
      top_blockers: [],
    } as any);
    vi.mocked(fetchRuns).mockResolvedValue([
      { run_id: "run-001", task_id: "task-001", status: "running", created_at: "2026-02-19T00:00:00Z" },
    ] as any);
    vi.mocked(fetchAllEvents).mockResolvedValue([
      { ts: "2026-02-19T00:00:00Z", event: "CHAIN_STEP", level: "INFO", run_id: "run-001" },
    ] as any);
    vi.mocked(fetchRunSearch).mockResolvedValue({ raw: {}, purified: {}, verification: {}, verification_ai: {} } as any);
    vi.mocked(promoteEvidence).mockResolvedValue({ ok: true, bundle: { run_id: "run-001" } } as any);
    vi.mocked(fetchQueue).mockResolvedValue([] as any);
    vi.mocked(enqueueRunQueue).mockResolvedValue({ ok: true } as any);
    vi.mocked(fetchWorkflow).mockResolvedValue({
      workflow: { workflow_id: "wf-001", status: "running" },
      runs: [{ run_id: "run-001", status: "running" }],
      events: [],
    } as any);
    vi.mocked(fetchDiffGate).mockResolvedValue([
      { run_id: "run-001", status: "failed", failure_reason: "x", allowed_paths: ["apps/desktop"] },
    ] as any);
    vi.mocked(fetchDiff).mockResolvedValue({ diff: "diff --git a/x b/x" } as any);
    vi.mocked(rollbackRun).mockResolvedValue({ ok: true } as any);
    vi.mocked(rejectRun).mockResolvedValue({ ok: true } as any);
    vi.mocked(fetchPendingApprovals).mockResolvedValue([{ run_id: "run-001", task_id: "task-001" }] as any);
    vi.mocked(approveGodMode).mockResolvedValue({ ok: true } as any);
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({ status: "healthy", alerts: [] } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      { pm_session_id: "pm-1", status: "active", run_count: 1, running_runs: 1, failed_runs: 0, success_runs: 0, blocked_runs: 0 },
      { pm_session_id: "pm-2", status: "failed", run_count: 1, running_runs: 0, failed_runs: 1, success_runs: 0, blocked_runs: 1 },
    ] as any);
    vi.mocked(runNextQueue).mockResolvedValue({ ok: false, reason: "queue empty" } as any);
  });

  it("covers NodeDetailDrawer + DiffReviewModal action buttons", async () => {
    const user = userEvent.setup();
    const onOpenDiff = vi.fn();
    const onToggleRaw = vi.fn();
    const onClose = vi.fn();
    const onAccept = vi.fn();
    const onRework = vi.fn();

    render(
      <>
        <NodeDetailDrawer
          open
          selectedNodeId="worker"
          selectedNode={{ id: "worker", data: { label: "Worker", role: "worker", status: "running", subtitle: "s" } } as any}
          reviewDecision="pending"
          showRawNodeOutput={false}
          nodeRawOutput="raw"
          onClose={onClose}
          onToggleRaw={onToggleRaw}
          onOpenDiff={onOpenDiff}
        />
        <DiffReviewModal open reviewDecision="pending" onClose={onClose} onAccept={onAccept} onRework={onRework} />
      </>,
    );

    await user.click(screen.getByRole("button", { name: /打开 Diff 审查|Open diff review/ }));
    await user.click(screen.getByRole("button", { name: /关闭 Diff 审查|Close diff review/ }));
    await user.click(screen.getByRole("button", { name: /接受并合并|Accept and merge/ }));
    await user.click(screen.getByRole("button", { name: /要求修改|Request changes/ }));

    expect(onOpenDiff).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(onAccept).toHaveBeenCalled();
    expect(onRework).toHaveBeenCalled();
  });

  it("covers ChangeGates diff toggle + rollback/reject", async () => {
    const user = userEvent.setup();
    render(<ChangeGatesPage />);

    expect(await screen.findByRole("heading", { name: /变更门禁|Diff gate/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /查看 Diff|View diff/ }));
    await waitFor(() => expect(fetchDiff).toHaveBeenCalledWith("run-001"));
    await user.click(screen.getByRole("button", { name: /隐藏 Diff|Hide diff/ }));
    await user.click(screen.getByRole("button", { name: /回滚|Rollback/ }));
    await waitFor(() => expect(rollbackRun).toHaveBeenCalledWith("run-001"));
    await user.click(screen.getByRole("button", { name: /拒绝变更|Reject change/ }));
    await waitFor(() => expect(rejectRun).toHaveBeenCalledWith("run-001"));
  });

  it("covers GodMode cancel controls in confirm modal", async () => {
    const user = userEvent.setup();
    render(<GodModePage />);
    expect(await screen.findByRole("heading", { name: /快速审批|Quick approval/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /批准执行|Approve execution/ }));

    await user.click(screen.getByRole("button", { name: /取消|Cancel/ }));
    await user.click(screen.getByRole("button", { name: /批准执行|Approve execution/ }));
    await user.click(screen.getByRole("button", { name: /关闭审批确认弹窗|Close approval confirmation dialog/ }));
  });

  it("covers overview, runs, search and workflow run navigation controls", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onNavigateToRun = vi.fn();

    const overview = render(<OverviewPage onNavigate={onNavigate} onNavigateToRun={onNavigateToRun} />);
    expect(await screen.findByRole("heading", { name: /新手起步|Operator overview/ })).toBeInTheDocument();
    expect(screen.getByText(/首次使用建议先走一遍单主流程|follow the primary path/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主步骤 1 · 发需求|Step 1 · Brief PM/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主步骤 2 · 看进度|Step 2 · Watch progress/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主步骤 3 · 看案例|Step 3 · Review Workflow Cases/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /主步骤 4 · 核证据|Step 4 · Verify Proof & Replay/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /审批确认（仅有待确认项时）|Approval checkpoint/ })).toBeInTheDocument();
    expect(screen.getByText(/点进 Run 详情|Open Run detail/)).toBeInTheDocument();
    expect(screen.getByText(/还没有运行记录|No runs yet/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /主步骤 1 · 发需求|Step 1 · Brief PM/ }));
    expect(onNavigate).toHaveBeenCalledWith("pm");
    await user.click(screen.getByRole("button", { name: /主步骤 2 · 看进度|Step 2 · Watch progress/ }));
    expect(onNavigate).toHaveBeenCalledWith("command-tower");
    await user.click(screen.getByRole("button", { name: /主步骤 3 · 看案例|Step 3 · Review Workflow Cases/ }));
    expect(onNavigate).toHaveBeenCalledWith("workflows");
    await user.click(screen.getByRole("button", { name: /主步骤 4 · 核证据|Step 4 · Verify Proof & Replay/ }));
    expect(onNavigate).toHaveBeenCalledWith("runs");
    await user.click(screen.getByRole("button", { name: /审批确认（仅有待确认项时）|Approval checkpoint/ }));
    expect(onNavigate).toHaveBeenCalledWith("god-mode");

    await user.click(screen.getByRole("button", { name: /查看全部运行|View all runs/ }));
    expect(onNavigate).toHaveBeenCalledWith("runs");
    await user.click(screen.getByRole("button", { name: "run-001" }));
    expect(onNavigateToRun).toHaveBeenCalledWith("run-001");
    overview.unmount();

    const runNav = vi.fn();
    const runs = render(<RunsPage onNavigateToRun={runNav} />);
    expect(await screen.findByRole("heading", { name: "Runs" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetchRuns).toHaveBeenCalled());
    runs.unmount();

    const search = render(<SearchPage />);
    await user.type(screen.getByPlaceholderText(/输入 run_id|Enter run_id/), "run-001");
    await user.click(screen.getByRole("button", { name: /提升为证据包|Promote to EvidenceBundle/ }));
    await waitFor(() => expect(promoteEvidence).toHaveBeenCalledWith("run-001"));
    search.unmount();

    const wfNav = vi.fn();
    render(<WorkflowDetailPage workflowId="wf-001" onBack={vi.fn()} onNavigateToRun={wfNav} />);
    expect(await screen.findByText("wf-001")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "run-001" }));
    expect(wfNav).toHaveBeenCalledWith("run-001");
  });

  it("covers desktop command tower p0 header and expansion buttons", async () => {
    const user = userEvent.setup();
    render(<CommandTowerPage />);
    expect(await screen.findByRole("heading", { name: /指挥塔|Command Tower/ })).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: /更新进展|Refresh progress/ }));
    await user.click(screen.getByRole("button", { name: /暂停自动更新|Pause auto-refresh/ }));
    await user.click(screen.getByRole("button", { name: /继续处理|Resume work/ }));

    const toggle = screen.getByRole("button", { name: /展开专家信息|Show advanced detail/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(await screen.findByRole("button", { name: /收起专家信息|Hide advanced detail/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("supports keyboard expand/collapse for events rows", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchAllEvents).mockResolvedValueOnce([
      { ts: "2026-02-19T00:00:00Z", event: "CHAIN_STEP", level: "INFO", context: { phase: "worker" } },
    ] as any);
    render(<EventsPage />);
    const eventRow = await screen.findByRole("button", { name: /查看事件详情 CHAIN_STEP|View event details CHAIN_STEP/ });
    expect(eventRow).toHaveAttribute("aria-expanded", "false");
    eventRow.focus();
    await user.keyboard("{Enter}");
    expect(eventRow).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/\"phase\": \"worker\"/)).toBeInTheDocument();
    await user.keyboard(" ");
    expect(eventRow).toHaveAttribute("aria-expanded", "false");
  });
});
