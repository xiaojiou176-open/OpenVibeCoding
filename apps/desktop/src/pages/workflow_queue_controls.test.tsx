import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowDetailPage } from "./WorkflowDetailPage";
import { WorkflowsPage } from "./WorkflowsPage";

vi.mock("../lib/api", () => ({
  enqueueRunQueue: vi.fn(),
  fetchQueue: vi.fn(),
  fetchWorkflowCopilotBrief: vi.fn(),
  fetchWorkflow: vi.fn(),
  fetchWorkflows: vi.fn(),
  runNextQueue: vi.fn(),
}));

import { enqueueRunQueue, fetchQueue, fetchWorkflow, fetchWorkflowCopilotBrief, fetchWorkflows, runNextQueue } from "../lib/api";

describe("workflow queue controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWorkflows).mockResolvedValue([
      {
        workflow_id: "wf-queue",
        status: "running",
        namespace: "default",
        runs: [{ run_id: "run-001" }],
      },
    ] as never);
    vi.mocked(fetchWorkflow).mockResolvedValue({
      workflow: {
        workflow_id: "wf-queue",
        status: "running",
        objective: "Queue the latest run",
        workflow_case_read_model: {
          authority: "workflow-case-read-model",
          source: "latest linked run manifest.role_binding_summary",
          execution_authority: "task_contract",
          workflow_id: "wf-queue",
          source_run_id: "run-001",
          role_binding_summary: {
            authority: "contract-derived-read-model",
            source: "persisted from contract",
            execution_authority: "task_contract",
            skills_bundle_ref: {
              status: "registry-backed",
              ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
              bundle_id: "worker_delivery_core_v1",
              resolved_skill_set: ["contract_alignment"],
              validation: "fail-closed",
            },
            mcp_bundle_ref: {
              status: "registry-backed",
              ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
              resolved_mcp_tool_set: ["codex"],
              validation: "fail-closed",
            },
            runtime_binding: {
              status: "contract-derived",
              authority_scope: "contract-derived-read-model",
              summary: { runner: "agents", provider: "cliproxyapi", model: "gpt-5.4" },
            },
          },
        },
      },
      runs: [{ run_id: "run-001", status: "running" }],
      events: [],
    } as never);
    vi.mocked(fetchQueue).mockResolvedValue([
      {
        queue_id: "queue-1",
        task_id: "task-queue",
        workflow_id: "wf-queue",
        status: "PENDING",
        priority: 5,
        sla_state: "at_risk",
      },
    ] as never);
    vi.mocked(fetchWorkflowCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "workflow",
      subject_id: "wf-queue",
      workflow_id: "wf-queue",
      run_id: "run-001",
      status: "OK",
      summary: "The workflow case is ready for queue review.",
      likely_cause: "Queue posture is the main operator focus.",
      compare_takeaway: "The latest run still needs operator review.",
      proof_takeaway: "Proof exists but should be reviewed before sharing.",
      incident_takeaway: "One workflow truth surface still needs review.",
      queue_takeaway: "One eligible queue item is ready.",
      approval_takeaway: "No approval blocker is attached.",
      recommended_actions: ["Run the next queued task."],
      top_risks: ["Queue backlog"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as never);
    vi.mocked(enqueueRunQueue).mockResolvedValue({ ok: true, task_id: "task-queue" } as never);
    vi.mocked(runNextQueue).mockResolvedValue({ ok: true, run_id: "run-queued-1" } as never);
  });

  it("renders queue summary on workflows list and runs next queued task", async () => {
    render(<WorkflowsPage onNavigateToWorkflow={vi.fn()} />);

    expect(await screen.findByText("sla: at_risk")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run next queued task" }));

    await waitFor(() => {
      expect(runNextQueue).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("Started queued work as run run-queued-1.")).toBeInTheDocument();
  });

  it("queues latest run contract from workflow detail and shows queue rows", async () => {
    render(<WorkflowDetailPage workflowId="wf-queue" onBack={vi.fn()} onNavigateToRun={vi.fn()} />);

    expect(await screen.findByText("Next Operator Action")).toBeInTheDocument();
    expect(screen.getByText("Workflow Case copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain this workflow case" })).toBeInTheDocument();
    expect(screen.getByText(/Queued work already exists\. The next high-value action is to run the next queued task and watch the case move\./)).toBeInTheDocument();
    expect(await screen.findByText("Queue / SLA (1)")).toBeInTheDocument();
    expect(screen.getByText("priority 5 / sla at_risk")).toBeInTheDocument();
    expect(screen.getByText("Workflow read model")).toBeInTheDocument();
    expect(screen.getByText("execution_authority: task_contract")).toBeInTheDocument();
    expect(screen.getByText("skills_bundle: worker_delivery_core_v1 (registry-backed)")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Queue priority"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Queue scheduled at"), { target: { value: "2026-03-30T12:00" } });
    fireEvent.change(screen.getByLabelText("Queue deadline at"), { target: { value: "2026-03-30T13:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue latest run contract" }));
    await waitFor(() => {
      expect(enqueueRunQueue).toHaveBeenCalledWith(
        "run-001",
        expect.objectContaining({
          priority: 3,
          scheduled_at: expect.stringMatching(/Z$/),
          deadline_at: expect.stringMatching(/Z$/),
        }),
      );
    });
    expect(await screen.findByText("Queued task-queue. Refreshing the workflow view...")).toBeInTheDocument();
  });

  it("renders locale-aware workflow detail labels when zh-CN is requested", async () => {
    render(<WorkflowDetailPage workflowId="wf-queue" onBack={vi.fn()} onNavigateToRun={vi.fn()} locale="zh-CN" />);

    expect(await screen.findByRole("button", { name: "返回工作流列表" })).toBeInTheDocument();
    expect(screen.getByText("AI 工作流副驾驶")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "解释这个工作流案例" })).toBeInTheDocument();
    expect(screen.getByText("下一步操作")).toBeInTheDocument();
    expect(screen.getByText("工作流案例摘要")).toBeInTheDocument();
    expect(screen.getByText("工作流只读模型")).toBeInTheDocument();
    expect(screen.getByText("相关 Run（1）")).toBeInTheDocument();
    expect(screen.getByText("事件（0）")).toBeInTheDocument();
    expect(screen.getByText("队列 / SLA（1）")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "排入最新 Run 合约" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行下一条排队任务" })).toBeInTheDocument();
    expect(screen.getByText("优先级 5 / SLA at_risk")).toBeInTheDocument();
    expect(screen.getAllByText("运行中").length).toBeGreaterThan(0);
  });
});
