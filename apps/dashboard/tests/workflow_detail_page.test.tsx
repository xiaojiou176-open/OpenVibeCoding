import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockCookies } = vi.hoisted(() => ({
  mockCookies: vi.fn(),
}));

const mockRefresh = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: mockRefresh }),
}));

vi.mock("../lib/api", () => ({
  enqueueRunQueue: vi.fn(),
  fetchQueue: vi.fn(),
  fetchWorkflowCopilotBrief: vi.fn(),
  fetchWorkflow: vi.fn(),
  mutationExecutionCapability: vi.fn(),
  runNextQueue: vi.fn(),
}));

vi.mock("../lib/serverPageData", () => ({
  safeLoad: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: mockCookies,
}));

import WorkflowDetailPage, { generateMetadata } from "../app/workflows/[id]/page";
import { enqueueRunQueue, fetchQueue, fetchWorkflow, fetchWorkflowCopilotBrief, mutationExecutionCapability, runNextQueue } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";

describe("workflow detail page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRefresh.mockReset();
    mockCookies.mockResolvedValue({
      get: () => undefined,
      toString: () => "",
    });
    vi.mocked(safeLoad).mockImplementation(
      async (loader: () => Promise<unknown>, fallback: unknown, label: string) => {
        try {
          return { data: await loader(), warning: "" };
        } catch (error) {
          const message =
            error instanceof Error ? error.message : typeof error === "string" ? error : "unknown";
          console.error(`[safeLoad] ${label} load failed: ${message}`);
          return { data: fallback, warning: `${label} is temporarily unavailable. Try again later.` };
        }
      },
    );
    vi.mocked(fetchWorkflow).mockResolvedValue({
      workflow: {
        workflow_id: "wf-1",
        status: "running",
        namespace: "ns",
        task_queue: "q1",
        objective: "Close the workflow case loop",
        owner_pm: "pm-owner",
        project_key: "cortex-case",
        verdict: "active",
        workflow_case_read_model: {
          authority: "workflow-case-read-model",
          source: "latest linked run manifest.role_binding_summary",
          execution_authority: "task_contract",
          workflow_id: "wf-1",
          source_run_id: "run/1",
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
      runs: [{ run_id: "run/1", status: "running", created_at: "2026-02-25T00:00:00Z" }],
      events: [],
    } as never);
    vi.mocked(fetchQueue).mockResolvedValue([] as never);
    vi.mocked(fetchWorkflowCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "workflow",
      subject_id: "wf-1",
      workflow_id: "wf-1",
      run_id: "run/1",
      status: "OK",
      summary: "The workflow case is blocked by its latest linked run.",
      likely_cause: "The latest run is still blocked by a gate.",
      compare_takeaway: "The latest run still differs from its baseline.",
      proof_takeaway: "Proof is present but not final yet.",
      incident_takeaway: "One truth surface still needs review.",
      queue_takeaway: "Queue posture is stable.",
      approval_takeaway: "No approval blocker is attached.",
      recommended_actions: ["Review the latest linked run."],
      top_risks: ["Latest run gap"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as never);
    vi.mocked(runNextQueue).mockResolvedValue({ ok: true, run_id: "run-queued-1" } as never);
    vi.mocked(enqueueRunQueue).mockResolvedValue({ ok: true, task_id: "task-queue" } as never);
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: true, operatorRole: "TECH_LEAD" } as never);
  });

  it("exports workflow detail metadata with the workflow id", async () => {
    await expect(
      generateMetadata({ params: Promise.resolve({ id: "wf-1" }) }),
    ).resolves.toMatchObject({
      title: "Workflow Case detail · wf-1 | CortexPilot",
    });
  });

  it("falls back to raw id when route id is malformed percent-encoding", async () => {
    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "%E0%A4%A" }),
    });
    render(view);
    expect(fetchWorkflow).toHaveBeenCalledWith("%E0%A4%A");
    expect(screen.getByText("workflow_id: wf-1")).toBeInTheDocument();
    expect(screen.getByText("Owner: pm-owner")).toBeInTheDocument();
  });

  it("renders zh-CN page-level copy when the locale cookie is set", async () => {
    mockCookies.mockResolvedValueOnce({
      get: () => ({ value: "zh-CN" }),
      toString: () => "cortexpilot.ui.locale=zh-CN",
    });

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-zh" }),
    });
    render(view);

    expect(screen.getByRole("heading", { name: "工作流案例详情" })).toBeInTheDocument();
    expect(screen.getByText("先判断风险，再确认案例摘要、Run 映射、队列姿态和事件时间线，然后再做治理动作。")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "打开可分享案例资产" })[0]).toHaveAttribute("href", "/workflows/wf-zh/share");
    expect(screen.getByText("操作角色: TECH_LEAD")).toBeInTheDocument();
    expect(screen.getByText("当前可见队列项：0。现在可执行：0。")).toBeInTheDocument();
    expect(screen.getByLabelText("队列优先级")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "排入最新 Run 合约" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行下一条排队任务" })).toBeInTheDocument();
  });

  it("encodes run link when run id contains reserved chars", async () => {
    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-1" }),
    });
    render(view);
    expect(screen.getByRole("link", { name: "run/1" })).toHaveAttribute("href", "/runs/run%2F1");
    expect(screen.getAllByText("Normal state").length).toBeGreaterThan(0);
    expect(screen.getByText("Next Operator Action")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open share-ready case asset" })[0]).toHaveAttribute("href", "/workflows/wf-1/share");
    expect(screen.getByRole("button", { name: "Queue latest run contract" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run next queued task" })).toBeInTheDocument();
    expect(screen.getByText("Workflow Case copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain this workflow case" })).toBeInTheDocument();
    expect(screen.getByText("Workflow read model")).toBeInTheDocument();
  });

  it("decodes valid encoded route id before fetching workflow", async () => {
    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf%2Fencoded" }),
    });
    render(view);

    expect(fetchWorkflow).toHaveBeenCalledWith("wf/encoded");
  });

  it("shows warning and empty run state when fetch fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(fetchWorkflow).mockRejectedValueOnce(new Error("service unavailable"));

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-fallback" }),
    });
    render(view);

    expect(screen.getByRole("status")).toHaveTextContent("Workflow detail is temporarily unavailable. Try again later.");
    expect(screen.getByText("Workflow Case is in read-only degraded mode")).toBeInTheDocument();
    expect(screen.getByText("Identity snapshot (degraded)")).toBeInTheDocument();
    expect(screen.getByText("Run mapping samples (degraded)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Governance entry (disabled in degraded mode)" })).toBeDisabled();
    expect(screen.getByText("workflow_id: wf-fallback")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Retry load" })[0]).toHaveAttribute("href", "/workflows/wf-fallback");
    expect(screen.getAllByRole("link", { name: "Back to workflow list" })[0]).toHaveAttribute("href", "/workflows");

    consoleSpy.mockRestore();
  });

  it("falls back to empty lists when runs or events are not arrays", async () => {
    vi.mocked(fetchWorkflow).mockResolvedValueOnce({
      workflow: { workflow_id: "wf-2", status: "failed" },
      runs: { run_id: "bad-shape" },
      events: null,
    } as never);

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-2" }),
    });
    render(view);

    expect(screen.getByText("Runs: 0")).toBeInTheDocument();
    expect(screen.getAllByText("High-risk state").length).toBeGreaterThan(0);
    expect(screen.getByText("No related runs")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "bad-shape" })).not.toBeInTheDocument();
  });

  it("renders degraded run sample rows when fallback payload still contains runs", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(fetchWorkflow).mockRejectedValueOnce(new Error("degraded"));

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-sample" }),
    });
    render(view);

    expect(screen.getByText("No verifiable run mapping is available in degraded mode.")).toBeInTheDocument();
    expect(screen.getByText("Read-only note: use the run chain for assessment only, not for direct governance actions.")).toBeInTheDocument();
    consoleSpy.mockRestore();
  });

  it("maps unknown and success workflow states into risk badges and metadata", async () => {
    vi.mocked(fetchWorkflow).mockResolvedValueOnce({
      workflow: { workflow_id: "wf-3", status: "", title: "Workflow Title", created_at: "2026-03-09T09:00:00Z" },
      runs: [],
      events: [{ event: "READY", ts: "2026-03-09T09:01:00Z" }],
    } as never);

    const unknownView = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-3" }),
    });
    render(unknownView);

    expect(screen.getAllByText("Normal state").length).toBeGreaterThan(0);
    expect(screen.getByText("Name: Workflow Title")).toBeInTheDocument();
    expect(screen.getByText("Updated at: 2026-03-09T09:00:00Z")).toBeInTheDocument();
    expect(screen.getByText("Events")).toBeInTheDocument();
  });

  it("covers success badge and workflow id fallback when payload id is missing", async () => {
    vi.mocked(fetchWorkflow).mockResolvedValueOnce({
      workflow: { status: "DONE", title: "No Id Workflow", created_at: "2026-03-09T10:00:00Z" },
      runs: [],
      events: [],
    } as never);

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-fallback-id" }),
    });
    render(view);

    expect(screen.getAllByText("Normal state").length).toBeGreaterThan(0);
    expect(screen.getByText("workflow_id: wf-fallback-id")).toBeInTheDocument();
    expect(screen.getByText("Name: No Id Workflow")).toBeInTheDocument();
  });

  it("covers degraded warning branch with sampled runs payload", async () => {
    vi.mocked(safeLoad).mockResolvedValueOnce({
      data: {
        workflow: { workflow_id: "wf-warning", status: "RUNNING" },
        runs: [{ run_id: "run-warning-1", status: "RUNNING", created_at: "2026-03-09T10:01:00Z" }],
        events: [],
      },
      warning: "Workflow detail is temporarily unavailable. Try again later.",
    } as never);

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-warning" }),
    });
    render(view);

    expect(screen.getByRole("status")).toHaveTextContent("Workflow detail is temporarily unavailable. Try again later.");
    expect(screen.getByText("run-warning-1 / Running / 2026-03-09T10:01:00Z")).toBeInTheDocument();
  });

  it("covers run link fallback and created-at fallback in normal branch", async () => {
    vi.mocked(fetchWorkflow).mockResolvedValueOnce({
      workflow: { workflow_id: "wf-run-fallback", status: "READY", created_at: "2026-03-09T10:05:00Z" },
      runs: [{ status: "READY", created_at: "" }],
      events: [],
    } as never);

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-run-fallback" }),
    });
    render(view);

    const emptyRunLink = document.querySelector('a[href="/runs/"]');
    expect(emptyRunLink).not.toBeNull();
    expect(emptyRunLink?.parentElement).toHaveTextContent(/Ready|Unknown/);
    expect(emptyRunLink?.parentElement).toHaveTextContent(" -");
  });

  it("falls back to route id and preserves run created_at when workflow payload is missing", async () => {
    vi.mocked(fetchWorkflow).mockResolvedValueOnce({
      runs: [{ run_id: "run-created-at", status: "RUNNING", created_at: "2026-03-09T10:06:00Z" }],
      events: [],
    } as never);

    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-missing-payload" }),
    });
    render(view);

    expect(screen.getByText("workflow_id: wf-missing-payload")).toBeInTheDocument();
    expect(screen.getByText("Name: wf-missing-payload")).toBeInTheDocument();
    const runLink = screen.getByRole("link", { name: "run-created-at" });
    expect(runLink.parentElement).toHaveTextContent("Running");
    expect(runLink.parentElement).toHaveTextContent("2026-03-09T10:06:00Z");
  });

  it("executes queue mutations from the web workflow case detail", async () => {
    const view = await WorkflowDetailPage({
      params: Promise.resolve({ id: "wf-1" }),
    });
    render(view);

    expect(screen.getByText(/No queued work exists yet\. Queue the latest run contract to move this Workflow Case into SLA tracking\./)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Queue priority"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Queue scheduled at"), { target: { value: "2026-03-30T12:00" } });
    fireEvent.change(screen.getByLabelText("Queue deadline at"), { target: { value: "2026-03-30T13:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue latest run contract" }));

    await waitFor(() => {
      expect(enqueueRunQueue).toHaveBeenCalledWith(
        "run/1",
        expect.objectContaining({
          priority: 3,
          scheduled_at: expect.stringMatching(/Z$/),
          deadline_at: expect.stringMatching(/Z$/),
        }),
      );
    });
    expect(await screen.findByText("Queued task-queue. Refreshing the workflow view...")).toBeInTheDocument();
  });
});
