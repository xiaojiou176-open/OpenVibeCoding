import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsPage } from "./AgentsPage";
import { LocksPage } from "./LocksPage";
import { WorkflowsPage } from "./WorkflowsPage";
import { WorktreesPage } from "./WorktreesPage";

vi.mock("../lib/api", () => ({
  fetchAgents: vi.fn(),
  fetchAgentStatus: vi.fn(),
  fetchRoleConfig: vi.fn(),
  previewRoleConfig: vi.fn(),
  applyRoleConfig: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
  fetchQueue: vi.fn(),
  fetchLocks: vi.fn(),
  fetchWorkflows: vi.fn(),
  fetchWorktrees: vi.fn(),
  runNextQueue: vi.fn(),
}));

import {
  applyRoleConfig,
  fetchAgents,
  fetchAgentStatus,
  fetchRoleConfig,
  fetchQueue,
  fetchLocks,
  mutationExecutionCapability,
  previewRoleConfig,
  fetchWorkflows,
  fetchWorktrees,
  runNextQueue,
} from "../lib/api";

describe("coverage sprint F: low-branch pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    vi.mocked(previewRoleConfig).mockResolvedValue({ changes: [] } as any);
    vi.mocked(applyRoleConfig).mockResolvedValue({ saved: true, surface: {} } as any);
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: false, operatorRole: null } as any);
    vi.mocked(fetchQueue).mockResolvedValue([] as any);
    vi.mocked(runNextQueue).mockResolvedValue({ ok: false, reason: "queue empty" } as any);
  });

  it("covers AgentsPage non-empty, refresh to empty, and error branch", async () => {
    type FirstAgentsPayload = Awaited<ReturnType<typeof fetchAgents>>;
    let resolveFirstAgents: (value: FirstAgentsPayload) => void = () => {};
    vi.mocked(fetchAgents)
      .mockImplementationOnce(
        () => new Promise<FirstAgentsPayload>((resolve) => { resolveFirstAgents = resolve; }) as any,
      )
      .mockResolvedValueOnce({ agents: [] } as any)
      .mockRejectedValueOnce(new Error("agents boom"));
    vi.mocked(fetchAgentStatus)
      .mockResolvedValueOnce({ agents: [{ agent_id: "a-1", role: "TL", stage: "RUNNING", run_id: "run-1234567890abcdef" }] } as any)
      .mockResolvedValueOnce({ agents: [] } as any)
      .mockResolvedValueOnce({ agents: [] } as any);

    render(<AgentsPage />);
    expect(screen.getByRole("button", { name: /刷新中\.\.\.|Refreshing\.\.\./ })).toBeDisabled();
    resolveFirstAgents({
      agents: [{
        agent_id: "a-1",
        role: "TL",
        sandbox: null,
        approval_policy: null,
        network: null,
        mcp_tools: [],
        notes: "worker",
        lock_count: 0,
        locked_paths: [],
      }],
      locks: [],
      role_catalog: [],
    } as FirstAgentsPayload);
    expect(await screen.findByText(/活跃状态机|Active State Machines/)).toBeInTheDocument();
    expect(screen.getByText(/注册代理 \(1\)|Registered Agents \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("run-12345678")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    expect(await screen.findByText(/暂无注册代理|No agents are registered yet/)).toBeInTheDocument();
    expect(screen.queryByText(/活跃状态机|Active state machines/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    const errorBanner = await screen.findByRole("alert");
    expect(errorBanner).toHaveTextContent("agents boom");
  });

  it("covers LocksPage data fallbacks, empty branch, and non-Error rejection", async () => {
    vi.mocked(fetchLocks)
      .mockResolvedValueOnce([
        { path: "/tmp/1", holder: "pm", type: "file", acquired_at: "2026-02-20T00:00:00Z" },
        { resource: "/tmp/2", agent_id: "agent-2", lock_type: "resource" },
      ] as any)
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce("lock-failed");

    render(<LocksPage />);
    expect(await screen.findByText("/tmp/1")).toBeInTheDocument();
    expect(screen.getByText("/tmp/2")).toBeInTheDocument();
    expect(screen.getByText("agent-2")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    expect(await screen.findByText(/暂无锁记录|No lock records yet/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    expect(await screen.findByText("lock-failed")).toBeInTheDocument();
  });

  it("covers WorktreesPage locked/unlocked branches and empty branch", async () => {
    vi.mocked(fetchWorktrees)
      .mockResolvedValueOnce([
        { path: "/repo/wt-1", branch: "main", head: "abcdef1234567890", locked: true },
        { path: "/repo/wt-2", branch: "feat/a", commit: "1234567890abcdef", locked: false },
      ] as any)
      .mockResolvedValueOnce([]);

    render(<WorktreesPage />);
    expect(await screen.findByText("/repo/wt-1")).toBeInTheDocument();
    expect(screen.getByText("abcdef123456")).toBeInTheDocument();
    expect(screen.getAllByText(/已锁定|Locked/).length).toBeGreaterThan(0);
    expect(screen.getByText("1234567890ab")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    expect(await screen.findByText(/暂无工作树|No worktrees yet/)).toBeInTheDocument();
  });

  it("covers WorkflowsPage navigation, namespace/runs fallback, empty and error branches", async () => {
    const onNavigate = vi.fn();
    vi.mocked(fetchWorkflows)
      .mockResolvedValueOnce([{ workflow_id: "wf-1", status: "running", namespace: "", runs: undefined }] as any)
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("workflows down"));

    render(<WorkflowsPage onNavigateToWorkflow={onNavigate} />);
    const workflowLink = await screen.findByRole("button", { name: "wf-1" });
    fireEvent.click(workflowLink);
    expect(onNavigate).toHaveBeenCalledWith("wf-1");
    expect(screen.getAllByText("0").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    expect(await screen.findByText(/暂无工作流|No workflows? cases yet/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /刷新|Refresh/ }));
    await waitFor(() => {
      expect(screen.getByText("workflows down")).toBeInTheDocument();
    });
  });
});
