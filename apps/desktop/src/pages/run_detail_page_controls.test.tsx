import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { toast } from "sonner";

import { RunDetailPage } from "./RunDetailPage";

const streamState = vi.hoisted(() => ({
  stream: null as null | {
    close: ReturnType<typeof vi.fn>;
    onmessage: ((event: MessageEvent) => void) | null;
    onerror: ((event: Event) => void) | null;
  },
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../lib/api", () => ({
  fetchRun: vi.fn(),
  fetchEvents: vi.fn(),
  fetchDiff: vi.fn(),
  fetchReports: vi.fn(),
  fetchArtifact: vi.fn(),
  fetchOperatorCopilotBrief: vi.fn(),
  fetchToolCalls: vi.fn(),
  fetchChainSpec: vi.fn(),
  fetchAgentStatus: vi.fn(),
  fetchRuns: vi.fn(),
  rollbackRun: vi.fn(),
  rejectRun: vi.fn(),
  replayRun: vi.fn(),
  promoteEvidence: vi.fn(),
  openEventsStream: vi.fn(() => {
    const stream = {
      close: vi.fn(),
      onmessage: null,
      onerror: null,
    };
    streamState.stream = stream;
    return stream;
  }),
}));

import {
  fetchRun,
  fetchEvents,
  fetchDiff,
  fetchReports,
  fetchArtifact,
  fetchOperatorCopilotBrief,
  fetchToolCalls,
  fetchChainSpec,
  fetchAgentStatus,
  fetchRuns,
  rollbackRun,
  rejectRun,
  replayRun,
  promoteEvidence,
  openEventsStream,
} from "../lib/api";

const consoleWarnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

function makeRun(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-001",
    task_id: "task-001",
    status: "running",
    created_at: "2026-02-19T00:00:00Z",
    owner_agent_id: "pm-1",
    owner_role: "PM",
    assigned_agent_id: "tl-1",
    assigned_role: "TL",
    manifest: {},
    contract: null,
    allowed_paths: ["apps/desktop"],
    ...overrides,
  } as any;
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("RunDetailPage p0 controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRun).mockReset();
    vi.mocked(fetchEvents).mockReset();
    vi.mocked(fetchDiff).mockReset();
    vi.mocked(fetchReports).mockReset();
    vi.mocked(fetchArtifact).mockReset();
    vi.mocked(fetchToolCalls).mockReset();
    vi.mocked(fetchChainSpec).mockReset();
    vi.mocked(fetchAgentStatus).mockReset();
    vi.mocked(fetchRuns).mockReset();
    vi.mocked(rollbackRun).mockReset();
    vi.mocked(rejectRun).mockReset();
    vi.mocked(promoteEvidence).mockReset();
    vi.mocked(replayRun).mockReset();
    vi.mocked(openEventsStream).mockReset();
    vi.mocked(openEventsStream).mockImplementation(() => {
      const stream = {
        close: vi.fn(),
        onmessage: null,
        onerror: null,
      };
      streamState.stream = stream;
      return stream as any;
    });
    streamState.stream = null;
    consoleWarnSpy.mockClear();
    vi.mocked(fetchRun).mockResolvedValue(makeRun());
    vi.mocked(fetchEvents).mockResolvedValue([
      { ts: "2026-02-19T00:00:01Z", event: "CHAIN_STEP", level: "INFO", context: { phase: "worker" } },
    ] as any);
    vi.mocked(fetchDiff).mockResolvedValue({ diff: "" } as any);
    vi.mocked(fetchReports).mockResolvedValue([] as any);
    vi.mocked(fetchArtifact).mockResolvedValue({ data: [] } as any);
    vi.mocked(fetchOperatorCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "run",
      subject_id: "run-001",
      run_id: "run-001",
      workflow_id: "wf-1",
      status: "OK",
      summary: "The run is blocked by a review gate.",
      likely_cause: "A gate still needs operator review.",
      compare_takeaway: "Compare still shows one delta.",
      proof_takeaway: "Proof exists but should not be promoted yet.",
      incident_takeaway: "Incident context points to a governance block.",
      queue_takeaway: "Queue posture is stable.",
      approval_takeaway: "No extra approval is attached right now.",
      recommended_actions: ["Review the gate first."],
      top_risks: ["Gate still open"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as any);
    vi.mocked(fetchToolCalls).mockResolvedValue({ data: [] } as any);
    vi.mocked(fetchChainSpec).mockResolvedValue({ data: null } as any);
    vi.mocked(fetchAgentStatus).mockResolvedValue({ agents: [] } as any);
    vi.mocked(fetchRuns).mockResolvedValue([{ run_id: "run-002", task_id: "task-002", status: "done" }] as any);
    vi.mocked(rollbackRun).mockResolvedValue({ ok: true } as any);
    vi.mocked(rejectRun).mockResolvedValue({ ok: true } as any);
    vi.mocked(promoteEvidence).mockResolvedValue({ ok: true } as any);
    vi.mocked(replayRun).mockResolvedValue({ ok: true, diff_summary: "none" } as any);
  });

  it("covers action bar, live toggle, tabs, replay, event row expand and refresh affordances", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    vi.mocked(fetchReports).mockResolvedValue([
      {
        name: "run_compare_report.json",
        data: {
          compare_summary: {
            mismatched_count: 0,
            missing_count: 0,
            extra_count: 0,
          },
        },
      },
      {
        name: "proof_pack.json",
        data: {
          summary: "Proof artifacts are ready.",
        },
      },
    ] as any);
    render(<RunDetailPage runId="run-001" onBack={onBack} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByText("AI operator copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate operator brief" })).toBeInTheDocument();
    await waitFor(() => {
      expect(openEventsStream).toHaveBeenCalledWith("run-001", { tail: true });
    });
    expect(fetchEvents).toHaveBeenCalledTimes(1);
    const stream = streamState.stream;
    expect(stream?.close).toBeTypeOf("function");
    act(() => {
      stream?.onerror?.(new Event("error"));
    });
    await waitFor(() => {
      expect(fetchEvents).toHaveBeenCalledTimes(2);
    });

    const liveToggle = screen.getByRole("button", { name: "LIVE" });
    expect(liveToggle).toHaveAttribute("title", "Pause live updates");
    await user.click(liveToggle);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "PAUSED" })).toHaveAttribute("title", "Resume live updates");
    });

    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => expect(rollbackRun).toHaveBeenCalledWith("run-001"));
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(rejectRun).toHaveBeenCalledWith("run-001"));

    const eventRow = screen.getByRole("button", { name: "View event details CHAIN_STEP" });
    expect(eventRow).toHaveAttribute("aria-expanded", "false");
    await user.click(eventRow);
    expect(eventRow).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/"phase": "worker"/)).toBeInTheDocument();
    eventRow.focus();
    await user.keyboard("{Enter}");
    expect(eventRow).toHaveAttribute("aria-expanded", "false");
    await user.keyboard("{Enter}");
    expect(eventRow).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: /Change diff/ }));
    await user.click(screen.getByRole("button", { name: /Reports/ }));
    await user.click(screen.getByRole("button", { name: /Tool calls/ }));
    await user.click(screen.getByRole("button", { name: /Chain flow/ }));
    await user.click(screen.getByRole("button", { name: /Contract policy/ }));
    await user.click(screen.getByRole("button", { name: /Replay compare/ }));
    expect(await screen.findByText("Compare decision")).toBeInTheDocument();
    expect(screen.getByText("Action context")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Promote evidence" }));
    await waitFor(() => expect(promoteEvidence).toHaveBeenCalledWith("run-001"));
    await user.click(screen.getByRole("button", { name: "Run replay" }));
    await waitFor(() => expect(replayRun).toHaveBeenCalledWith("run-001", undefined));
  }, 10000);

  it("interprets compare summary via numeric counts instead of string matching", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchReports).mockResolvedValueOnce([
      {
        name: "run_compare_report.json",
        data: {
          compare_summary: {
            extra_count: 0,
            missing_count: 0,
            mismatched_count: 0,
            note: "all clear",
          },
        },
      },
    ] as any);

    render(<RunDetailPage runId="run-compare-clean" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Replay compare/ }));
    expect(await screen.findByText("The current run looks aligned with the selected baseline.")).toBeInTheDocument();
  });

  it("renders locale-aware operator labels on run detail when zh-CN is requested", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        manifest: {
          artifacts: [
            { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
            { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
          ],
        },
      }),
    );
    vi.mocked(fetchArtifact)
      .mockResolvedValueOnce({
        data: [
          {
            prompt_contract_id: "worker-zh",
            continuation_policy: {
              on_incomplete: "reply_auditor_reprompt_and_continue_same_session",
              on_blocked: "spawn_independent_temporary_unblock_task",
            },
            done_definition: { acceptance_checks: ["repo_hygiene", "test_report"] },
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          {
            unblock_task_id: "unblock-zh",
            owner: "L0",
            mode: "independent_temporary_task",
            trigger: "spawn_independent_temporary_unblock_task",
          },
        ],
      } as any);

    render(<RunDetailPage runId="run-zh" onBack={vi.fn()} locale="zh-CN" />);

    expect(await screen.findByText("AI 操作员副驾驶")).toBeInTheDocument();
    expect(screen.getByText("Run 总览")).toBeInTheDocument();
    expect(screen.getByText("执行角色")).toBeInTheDocument();
    expect(screen.getByText("证据与可追溯性")).toBeInTheDocument();
    expect(screen.getByText("完成治理摘要")).toBeInTheDocument();
    expect(screen.queryByText("Worker prompt contracts")).toBeNull();
    expect(screen.getByText("工作者提示合约")).toBeInTheDocument();
    expect(screen.getByText("未完成时")).toBeInTheDocument();
    expect(screen.getByText("阻塞时")).toBeInTheDocument();
    expect(screen.getByText("解阻塞任务")).toBeInTheDocument();
    expect(
      screen.getByText(
        "这些摘要来自持久化的工作者提示合约和解阻塞任务；它们只提供参考，`task_contract` 仍然掌握执行权威。",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行中" })).toHaveAttribute("title", "暂停实时更新");
    expect(screen.getByRole("button", { name: /事件时间线（1）/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "回放对比" })).toBeInTheDocument();
  });

  it("covers error state retry/back controls", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    vi.mocked(fetchRun).mockRejectedValueOnce(new Error("boom"));
    render(<RunDetailPage runId="run-err" onBack={onBack} />);

    expect(await screen.findByText(/Run detail failed to load/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to list" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("renders the role binding read model inside the run overview card", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        role_binding_read_model: {
          authority: "contract-derived-read-model",
          source: "persisted from contract",
          execution_authority: "task_contract",
          skills_bundle_ref: {
            status: "registry-backed",
            ref: "registry://skills/worker",
            bundle_id: "worker_delivery_core_v1",
            resolved_skill_set: ["contract_alignment"],
            validation: "fail-closed",
          },
          mcp_bundle_ref: {
            status: "registry-backed",
            ref: "registry://mcp/worker-readonly",
            resolved_mcp_tool_set: ["codex"],
            validation: "fail-closed",
          },
          runtime_binding: {
            status: "contract-derived",
            authority_scope: "contract-derived-read-model",
            source: {
              runner: "runtime_options.runner",
              provider: "runtime_options.provider",
              model: "role_contract.runtime_binding.model",
            },
            summary: { runner: "agents", provider: "cliproxyapi", model: "gpt-5.4" },
            capability: {
              status: "previewable",
              lane: "standard-provider-path",
              compat_api_mode: "responses",
              provider_status: "allowlisted",
              provider_inventory_id: "cliproxyapi",
              tool_execution: "provider-path-required",
              notes: [
                "Chat-style compatibility may differ from tool-execution capability.",
                "Execution authority remains task_contract even when role defaults change.",
              ],
            },
          },
        },
        manifest: {
          artifacts: [
            { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
            { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
          ],
        },
      }),
    );
    vi.mocked(fetchArtifact)
      .mockResolvedValueOnce({
        data: [
          {
            prompt_contract_id: "worker-1",
            continuation_policy: {
              on_incomplete: "reply_auditor_reprompt_and_continue_same_session",
              on_blocked: "spawn_independent_temporary_unblock_task",
            },
            done_definition: { acceptance_checks: ["repo_hygiene", "test_report"] },
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          {
            unblock_task_id: "unblock-worker-1",
            owner: "L0",
            mode: "independent_temporary_task",
            trigger: "spawn_independent_temporary_unblock_task",
          },
        ],
      } as any);

    render(<RunDetailPage runId="run-binding" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByText("Role binding read model")).toBeInTheDocument();
    expect(screen.getByText("Execution authority")).toBeInTheDocument();
    expect(screen.getByText("task_contract")).toBeInTheDocument();
    expect(screen.getByText("worker_delivery_core_v1 (registry-backed)")).toBeInTheDocument();
    expect(screen.getByText("agents / cliproxyapi / gpt-5.4")).toBeInTheDocument();
    expect(screen.getByText("standard-provider-path")).toBeInTheDocument();
    expect(screen.getByText("standard-provider-path / provider-path-required")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Read-only note: this mirrors the persisted binding summary. task_contract still owns execution authority.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Completion governance")).toBeInTheDocument();
    expect(screen.getByText("Worker prompt contracts")).toBeInTheDocument();
    expect(screen.getByText("On incomplete")).toBeInTheDocument();
    expect(screen.getByText("On blocked")).toBeInTheDocument();
    expect(screen.getByText("Unblock tasks")).toBeInTheDocument();
    expect(screen.getByText("Unblock owner")).toBeInTheDocument();
    expect(screen.getByText("L0")).toBeInTheDocument();
  });

  it("prefers runtime completion governance read-back when a runtime report exists", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        manifest: {
          artifacts: [
            { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
            { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
          ],
        },
      }),
    );
    vi.mocked(fetchReports).mockResolvedValueOnce([
      {
        name: "completion_governance_report.json",
        data: {
          authority: "runtime-evaluated-read-back",
          source: "reports/completion_governance_report.json",
          execution_authority: "task_contract",
          overall_verdict: "continue_required",
          dod_checker: {
            status: "failed",
            summary: "Missing test_report before completion.",
            required_checks: ["repo_hygiene", "test_report"],
            unmet_checks: ["test_report"],
          },
          reply_auditor: {
            status: "needs_followup",
            summary: "Reply stopped before verification evidence landed.",
          },
          continuation_decision: {
            selected_action: "reply_auditor_reprompt_and_continue_same_session",
            summary: "Continue in the same session after the auditor reprompt.",
            action_source: "reply_auditor",
            unblock_task_id: "unblock-runtime-1",
          },
          context_pack: {
            status: "not_requested",
            summary: "Fallback context pack stayed idle.",
          },
          harness_request: {
            status: "not_requested",
            summary: "Harness escalation was not required.",
          },
        },
      },
    ] as any);
    vi.mocked(fetchArtifact)
      .mockResolvedValueOnce({
        data: [
          {
            prompt_contract_id: "worker-1",
            continuation_policy: {
              on_incomplete: "reply_auditor_reprompt_and_continue_same_session",
              on_blocked: "spawn_independent_temporary_unblock_task",
            },
            done_definition: { acceptance_checks: ["repo_hygiene", "test_report"] },
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          {
            unblock_task_id: "unblock-runtime-1",
            owner: "L0",
            mode: "independent_temporary_task",
            trigger: "spawn_independent_temporary_unblock_task",
          },
        ],
      } as any);

    render(<RunDetailPage runId="run-runtime-report" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByText("Runtime evaluator verdict")).toBeInTheDocument();
    expect(screen.getByText("Overall verdict")).toBeInTheDocument();
    expect(screen.getByText("continue_required")).toBeInTheDocument();
    expect(screen.getByText("DoD checker")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
    expect(screen.getByText("Reply auditor")).toBeInTheDocument();
    expect(screen.getByText("needs_followup")).toBeInTheDocument();
    expect(screen.getByText("Continuation decision")).toBeInTheDocument();
    expect(screen.getByText("Context Pack")).toBeInTheDocument();
    expect(screen.getByText("Harness Request")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Runtime-evaluated read-back: this report reflects the live completion evaluator. task_contract still owns execution authority; this report does not replace the contract.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Planning advisory fallback")).toBeInTheDocument();
    expect(screen.getByText("Worker prompt contracts")).toBeInTheDocument();
  });

  it("reads context pack and harness request artifacts when runtime governance produced them", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        manifest: {
          artifacts: [
            { name: "context_pack", path: "artifacts/context_pack.json" },
            { name: "harness_request", path: "artifacts/harness_request.json" },
          ],
        },
      }),
    );
    vi.mocked(fetchReports).mockResolvedValueOnce([
      {
        name: "completion_governance_report.json",
        data: {
          authority: "runtime-evaluated-read-back",
          source: "reports/completion_governance_report.json",
          execution_authority: "task_contract",
          overall_verdict: "continue_same_session",
          dod_checker: {
            status: "failed",
            summary: "Need follow-up.",
            required_checks: ["repo_hygiene"],
            unmet_checks: ["run_status"],
          },
          reply_auditor: {
            status: "needs_follow_up",
            summary: "Reply was incomplete.",
          },
          continuation_decision: {
            selected_action: "reply_auditor_reprompt_and_continue_same_session",
            summary: "Queued follow-up contract for the same session.",
            action_source: "continuation_policy.on_incomplete",
          },
          context_pack: {
            status: "generated",
            summary: "Generated ctx-pack-run-001 for fallback handoff.",
          },
          harness_request: {
            status: "approval_required",
            summary: "Generated harness-run-001 with approval_required policy verdict.",
          },
        },
      },
    ] as any);
    vi.mocked(fetchArtifact)
      .mockResolvedValueOnce({
        data: {
          pack_id: "ctx-pack-run-001",
          trigger_reason: "contamination",
        },
      } as any)
      .mockResolvedValueOnce({
        data: {
          request_id: "harness-run-001",
          scope: "project-local",
          approval_required: true,
        },
      } as any);

    render(<RunDetailPage runId="run-governance-artifacts" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByText("Context Pack ID")).toBeInTheDocument();
    expect(screen.getByText("ctx-pack-run-001")).toBeInTheDocument();
    expect(screen.getByText("Context Pack trigger")).toBeInTheDocument();
    expect(screen.getByText("contamination")).toBeInTheDocument();
    expect(screen.getByText("Harness Request ID")).toBeInTheDocument();
    expect(screen.getByText("harness-run-001")).toBeInTheDocument();
    expect(screen.getByText("Harness Request scope")).toBeInTheDocument();
    expect(screen.getByText("project-local")).toBeInTheDocument();
    expect(screen.getByText("Harness approval required")).toBeInTheDocument();
  });

  it("recovers from error state after retry load", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchRun).mockRejectedValueOnce(new Error("first fail"));
    render(<RunDetailPage runId="run-error-retry" onBack={vi.fn()} />);

    expect(await screen.findByText(/Run detail failed to load/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry load" }));
    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchRun).toHaveBeenCalledTimes(2);
    });
  });

  it("keeps detail page available when events fetch fails during initial load", async () => {
    vi.mocked(fetchEvents).mockRejectedValueOnce(new Error("events unavailable"));
    render(<RunDetailPage runId="run-events-fail" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh events" })).toBeInTheDocument();
    expect(screen.queryByText(/Run detail failed to load/)).not.toBeInTheDocument();
  });

  it("covers no-run state retry/back and diff empty actions", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    vi.mocked(fetchRun).mockResolvedValueOnce(null as any);
    render(<RunDetailPage runId="run-none" onBack={onBack} />);

    expect(await screen.findByText("No detail payload is available for this run yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to list" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("covers empty events tab refresh + return to events", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchEvents).mockResolvedValueOnce([] as any);
    render(<RunDetailPage runId="run-empty-events" onBack={vi.fn()} />);

    expect(await screen.findByRole("button", { name: "Refresh events" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Change diff/ }));
    expect(await screen.findByRole("button", { name: "Retry load" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to Event timeline" }));
    expect(screen.getByRole("button", { name: "Refresh events" })).toBeInTheDocument();
  });

  it("covers empty tab panels refresh actions and replay baseline selection", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchEvents).mockResolvedValueOnce([
      { ts: "2026-02-19T00:00:01Z", event: "NO_CONTEXT", level: "INFO" },
    ] as any);
    vi.mocked(fetchDiff).mockResolvedValueOnce({ diff: "" } as any);
    vi.mocked(fetchReports).mockResolvedValueOnce([] as any);
    vi.mocked(fetchToolCalls).mockResolvedValueOnce({ data: [] } as any);
    vi.mocked(fetchChainSpec).mockResolvedValueOnce({ data: null } as any);
    vi.mocked(fetchRun).mockResolvedValueOnce(makeRun({ contract: null, manifest: {} }));
    render(<RunDetailPage runId="run-empty-tabs" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View event details/ })).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /Change diff/ }));
    await user.click(await screen.findByRole("button", { name: "Retry load" }));
    await user.click(await screen.findByRole("button", { name: "Back to Event timeline" }));
    expect(await screen.findByRole("button", { name: "Refresh" })).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: /Reports/ }));
    await user.click(await screen.findByRole("button", { name: "Refresh reports" }));
    await user.click(await screen.findByRole("button", { name: /Tool calls/ }));
    await user.click(await screen.findByRole("button", { name: "Refresh tool calls" }));
    await user.click(await screen.findByRole("button", { name: /Chain flow/ }));
    await user.click(await screen.findByRole("button", { name: "Refresh chain flow" }));
    await user.click(await screen.findByRole("button", { name: /Contract policy/ }));
    await user.click(await screen.findByRole("button", { name: "Refresh contract" }));
    await user.click(await screen.findByRole("button", { name: /Replay compare/ }));
    await user.selectOptions(await screen.findByRole("combobox"), "run-002");
    await user.click(await screen.findByRole("button", { name: "Run replay" }));
    await waitFor(() => {
      expect(replayRun).toHaveBeenCalledWith("run-empty-tabs", "run-002");
    });
  }, 10000);

  it("uses unified manual-pending wording", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        status: "blocked",
        failure_class: "manual",
      }),
    );
    vi.mocked(fetchEvents).mockResolvedValueOnce([] as any);

    render(<RunDetailPage runId="run-manual" onBack={vi.fn()} />);

    expect(
      await screen.findByText("This run is marked as awaiting human approval. Next step: complete the approval before continuing."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/人工待处理/)).not.toBeInTheDocument();
  });

  it("renders shared zh-CN operator copy for high-value run detail surfaces", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(
      makeRun({
        role_binding_read_model: {
          authority: "contract-derived-read-model",
          source: "persisted from contract",
          execution_authority: "task_contract",
          skills_bundle_ref: {
            status: "registry-backed",
            ref: "registry://skills/worker",
            bundle_id: "worker_delivery_core_v1",
            resolved_skill_set: ["contract_alignment"],
            validation: "fail-closed",
          },
          mcp_bundle_ref: {
            status: "registry-backed",
            ref: "registry://mcp/worker-readonly",
            resolved_mcp_tool_set: ["codex"],
            validation: "fail-closed",
          },
          runtime_binding: {
            status: "contract-derived",
            authority_scope: "contract-derived-read-model",
            source: {
              runner: "runtime_options.runner",
              provider: "runtime_options.provider",
              model: "role_contract.runtime_binding.model",
            },
            summary: { runner: "agents", provider: "cliproxyapi", model: "gpt-5.4" },
          },
        },
      }),
    );
    render(<RunDetailPage runId="run-zh" onBack={vi.fn()} locale="zh-CN" />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    expect(screen.getByText("任务 task-001")).toBeInTheDocument();
    expect(screen.getByText("AI 操作员副驾驶")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "生成操作摘要" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行中" })).toHaveAttribute("title", "暂停实时更新");
    expect(screen.getByRole("button", { name: /事件时间线（1）/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "回放对比" })).toBeInTheDocument();
    expect(screen.getByText("Run 总览")).toBeInTheDocument();
    expect(screen.getByText("角色绑定只读模型")).toBeInTheDocument();
    expect(screen.getByText("执行角色")).toBeInTheDocument();
    expect(screen.getByText("证据与可追溯性")).toBeInTheDocument();
    expect(
      screen.getByText("只读说明：这里展示的是持久化的角色绑定摘要镜像；`task_contract` 仍然掌握执行权威。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提升为证据" })).toBeInTheDocument();
  });

  it("keeps live updates paused for terminal runs", async () => {
    vi.mocked(fetchRun).mockResolvedValueOnce(makeRun({ status: "archived" }));
    render(<RunDetailPage runId="run-archived" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "PAUSED" })).toHaveAttribute("title", "Resume live updates");
    });
    expect(openEventsStream).not.toHaveBeenCalled();
  });

  it("shows pending approvals alert and handles action failure error path", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchEvents).mockResolvedValueOnce([
      { ts: "2026-02-19T00:00:01Z", event: "HUMAN_APPROVAL_REQUIRED", level: "WARN" },
    ] as any);
    vi.mocked(rollbackRun).mockRejectedValueOnce(new Error("rollback failed"));
    render(<RunDetailPage runId="run-pending-approval" onBack={vi.fn()} />);

    expect(await screen.findByText(/This run is waiting for human approval/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rollback" }));
    await waitFor(() => {
      expect(rollbackRun).toHaveBeenCalledWith("run-pending-approval");
      expect(toast.error).toHaveBeenCalled();
    });
    expect(screen.getByRole("button", { name: "Rollback" })).toBeEnabled();
  });

  it("stops live updates when SSE receives terminal event", async () => {
    render(<RunDetailPage runId="run-sse-terminal" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();

    await waitFor(() => {
      expect(openEventsStream).toHaveBeenCalledWith("run-sse-terminal", { tail: true });
      expect(streamState.stream).not.toBeNull();
    });
    const stream = streamState.stream;
    expect(stream?.close).toEqual(expect.any(Function));
    act(() => {
      stream?.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            ts: "2026-02-19T00:00:03Z",
            event: "RUN_COMPLETED",
            level: "INFO",
            context: { done: true },
          }),
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "PAUSED" })).toHaveAttribute("title", "Resume live updates");
    });
  });

  it("falls back to polling when SSE stream cannot be opened", async () => {
    vi.mocked(openEventsStream).mockImplementationOnce(() => {
      throw new Error("sse unavailable");
    });
    render(<RunDetailPage runId="run-sse-throw" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    await waitFor(() => {
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        "[RunDetailPage] SSE unavailable, switching to polling fallback.",
        expect.any(Error),
      );
      expect(vi.mocked(fetchRun).mock.calls.length).toBeGreaterThanOrEqual(2);
      expect(vi.mocked(fetchEvents).mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it("logs polling fallback warnings when run/events refresh both fail", async () => {
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(makeRun())
      .mockRejectedValueOnce(new Error("poll run failed"))
      .mockResolvedValue(makeRun());
    vi.mocked(fetchEvents)
      .mockResolvedValueOnce([
        { ts: "2026-02-19T00:00:01Z", event: "CHAIN_STEP", level: "INFO", context: { phase: "worker" } },
      ] as any)
      .mockRejectedValueOnce(new Error("poll events failed"))
      .mockResolvedValue([] as any);
    render(<RunDetailPage runId="run-poll-warn" onBack={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "run-001" })).toBeInTheDocument();
    act(() => {
      streamState.stream?.onerror?.(new Event("error"));
    });
    await waitFor(() => {
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        "[RunDetailPage] SSE disconnected, switching to polling fallback.",
      );
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining("[RunDetailPage] polling run refresh failed:"),
      );
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining("[RunDetailPage] polling events refresh failed:"),
      );
    });
  });

  it("renders rich detail branches for reports/tooling/contract/chain and resets LIVE after runId switch", async () => {
    const user = userEvent.setup();
    const richRun = makeRun({
      run_id: "run-rich",
      status: "running",
      failure_code: "E_TEST",
      failure_summary_zh: "Failure summary payload",
      failure_reason: "Failure reason payload",
      contract: { mode: "strict" },
      manifest: {
        trace_id: "trace-001",
        workflow: { workflow_id: "wf-001" },
        evidence_hashes: { a: "1234567890abcdef", b: "abcdef1234567890" },
      },
    });
    vi.mocked(fetchRun)
      .mockResolvedValueOnce(richRun)
      .mockResolvedValue(makeRun({ run_id: "run-rich-2", task_id: "task-002" }));
    vi.mocked(fetchEvents).mockResolvedValueOnce([
      { ts: "", event_type: "FALLBACK_EVENT", level: "", task_id: "" },
    ] as any);
    vi.mocked(fetchDiff).mockResolvedValueOnce({ diff: "diff --git a b" } as any);
    vi.mocked(fetchReports).mockResolvedValueOnce([
      { name: "test_report.json", data: { pass: 1 } },
      { name: "review_report.json", data: { score: "A" } },
      { name: "evidence_report.json", data: "evidence body" },
      { name: "work_report.json", data: { work: true } },
      { name: "task_result.json", data: { ok: true } },
    ] as any);
    vi.mocked(fetchToolCalls).mockResolvedValueOnce({
      data: [
        { tool: "shell", status: "error", task_id: "task-err", duration_ms: 10, error: "tool failed" },
      ],
    } as any);
    vi.mocked(fetchChainSpec).mockResolvedValueOnce({ data: { stage: "chain-spec" } } as any);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({
      agents: [{ role: "WORKER", status: "running", agent_id: "worker-1" }],
    } as any);
    vi.mocked(fetchRuns).mockResolvedValueOnce([{ run_id: "run-base", task_id: "task-base", status: "done" }] as any);

    const { rerender } = render(<RunDetailPage runId="run-rich" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "run-rich" })).toBeInTheDocument();
    expect(screen.getByText("E_TEST")).toBeInTheDocument();
    expect(screen.getAllByText("Failure summary payload").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Failure reason payload").length).toBeGreaterThan(0);
    expect(screen.getByText("trace-001")).toBeInTheDocument();
    expect(screen.getByText("wf-001")).toBeInTheDocument();
    expect(screen.getByText("worker-1")).toBeInTheDocument();
    expect(screen.getByText("1234567890abcdef...")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View event details/ })).not.toBeInTheDocument();
    expect(screen.getByText("FALLBACK_EVENT")).toBeInTheDocument();
    const fallbackRow = screen.getByText("FALLBACK_EVENT").closest("tr");
    expect(fallbackRow).not.toBeNull();
    if (!fallbackRow) {
      throw new Error("fallback event row not found");
    }
    expect(within(fallbackRow).getAllByText("-").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Change diff/ }));
    expect(screen.getByText("diff --git a b")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Reports/ }));
    expect(screen.getByText("test_report.json")).toBeInTheDocument();
    expect(screen.getByText("review_report.json")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Tool calls/ }));
    expect(screen.getByText("shell")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Chain flow/ }));
    expect(screen.getByText("Chain Spec (chain.json)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Contract policy/ }));
    expect(screen.getByText(/"mode": "strict"/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Replay compare/ }));
    expect(screen.getByText("test_report.json")).toBeInTheDocument();
    expect(screen.getByText("review_report.json")).toBeInTheDocument();
    expect(screen.getByText("evidence_report.json")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "LIVE" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "PAUSED" })).toBeInTheDocument();
    });
    rerender(<RunDetailPage runId="run-rich-2" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "run-rich-2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "LIVE" })).toHaveAttribute("title", "Pause live updates");
  }, 10000);

  it("ignores stale secondary payloads when runId switches during parallel detail loads", async () => {
    const user = userEvent.setup();
    const oldDiff = createDeferred<{ diff: string }>();

    vi.mocked(fetchRun)
      .mockResolvedValueOnce(makeRun({ run_id: "run-old", task_id: "task-old" }))
      .mockResolvedValueOnce(makeRun({ run_id: "run-new", task_id: "task-new" }));
    vi.mocked(fetchEvents)
      .mockResolvedValueOnce([{ ts: "2026-02-19T00:00:01Z", event: "OLD_EVENT", level: "INFO" }] as any)
      .mockResolvedValueOnce([{ ts: "2026-02-19T00:00:02Z", event: "NEW_EVENT", level: "INFO" }] as any);
    vi.mocked(fetchDiff)
      .mockImplementationOnce(() => oldDiff.promise as Promise<any>)
      .mockResolvedValueOnce({ diff: "new diff payload" } as any);

    const { rerender } = render(<RunDetailPage runId="run-old" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(fetchDiff).toHaveBeenCalledTimes(1);
    });

    rerender(<RunDetailPage runId="run-new" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "run-new" })).toBeInTheDocument();

    await act(async () => {
      oldDiff.resolve({ diff: "old diff payload" });
      await Promise.resolve();
    });

    await user.click(screen.getByRole("button", { name: /Change diff/ }));
    expect(screen.getByText("new diff payload")).toBeInTheDocument();
    expect(screen.queryByText("old diff payload")).toBeNull();
  });

  it("ignores stale artifact summaries when runId switches during artifact loads", async () => {
    const oldPlanning = createDeferred<{ data: Array<Record<string, unknown>> }>();

    vi.mocked(fetchRun)
      .mockResolvedValueOnce(
        makeRun({
          run_id: "run-old",
          task_id: "task-old",
          manifest: {
            artifacts: [
              { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
              { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
            ],
          },
        }),
      )
      .mockResolvedValueOnce(
        makeRun({
          run_id: "run-new",
          task_id: "task-new",
          manifest: {
            artifacts: [
              { name: "planning_worker_prompt_contracts", path: "artifacts/planning_worker_prompt_contracts.json" },
              { name: "planning_unblock_tasks", path: "artifacts/planning_unblock_tasks.json" },
            ],
          },
        }),
      );
    vi.mocked(fetchEvents)
      .mockResolvedValueOnce([{ ts: "2026-02-19T00:00:01Z", event: "OLD_EVENT", level: "INFO" }] as any)
      .mockResolvedValueOnce([{ ts: "2026-02-19T00:00:02Z", event: "NEW_EVENT", level: "INFO" }] as any);
    vi.mocked(fetchArtifact).mockImplementation((requestedRunId, artifactName) => {
      if (requestedRunId === "run-old" && artifactName === "planning_worker_prompt_contracts.json") {
        return oldPlanning.promise as Promise<any>;
      }
      if (requestedRunId === "run-old" && artifactName === "planning_unblock_tasks.json") {
        return Promise.resolve({
          data: [
            {
              unblock_task_id: "unblock-old",
              owner: "old-owner",
              mode: "old-mode",
              trigger: "old-trigger",
            },
          ],
        } as any);
      }
      if (requestedRunId === "run-new" && artifactName === "planning_worker_prompt_contracts.json") {
        return Promise.resolve({
          data: [
            {
              prompt_contract_id: "worker-new",
              continuation_policy: {
                on_incomplete: "new-incomplete",
                on_blocked: "new-blocked",
              },
              done_definition: { acceptance_checks: ["new-check"] },
            },
          ],
        } as any);
      }
      if (requestedRunId === "run-new" && artifactName === "planning_unblock_tasks.json") {
        return Promise.resolve({
          data: [
            {
              unblock_task_id: "unblock-new",
              owner: "new-owner",
              mode: "new-mode",
              trigger: "new-trigger",
            },
          ],
        } as any);
      }
      return Promise.resolve({ data: [] } as any);
    });

    const { rerender } = render(<RunDetailPage runId="run-old" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(fetchArtifact).toHaveBeenCalledWith("run-old", "planning_worker_prompt_contracts.json");
    });

    rerender(<RunDetailPage runId="run-new" onBack={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "run-new" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("new-owner")).toBeInTheDocument();
      expect(screen.getByText("new-incomplete")).toBeInTheDocument();
    });

    await act(async () => {
      oldPlanning.resolve({
        data: [
          {
            prompt_contract_id: "worker-old",
            continuation_policy: {
              on_incomplete: "old-incomplete",
              on_blocked: "old-blocked",
            },
            done_definition: { acceptance_checks: ["old-check"] },
          },
        ],
      });
      await Promise.resolve();
    });

    expect(screen.getByText("new-owner")).toBeInTheDocument();
    expect(screen.getByText("new-incomplete")).toBeInTheDocument();
    expect(screen.queryByText("old-incomplete")).toBeNull();
    expect(screen.queryByText("old-owner")).toBeNull();
  });
});
