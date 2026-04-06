import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    refresh: vi.fn(),
  }),
}));

vi.mock("../lib/api", () => ({
  fetchAgents: vi.fn(),
  fetchAgentStatus: vi.fn(),
  fetchRoleConfig: vi.fn(),
  previewRoleConfig: vi.fn(),
  applyRoleConfig: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
}));

import AgentsPage from "../app/agents/page";
import {
  applyRoleConfig,
  fetchAgents,
  fetchAgentStatus,
  fetchRoleConfig,
  mutationExecutionCapability,
  previewRoleConfig,
} from "../lib/api";

describe("agents page presentation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses operations-oriented subtitle instead of developer wording", async () => {
    vi.mocked(fetchAgents).mockResolvedValueOnce({ agents: [], locks: [] } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("Triage blocked risk first, confirm available execution seats next, then drill into individual task records.")).toBeInTheDocument();
    expect(screen.getByText("Use role and keyword filters to separate bound agent records from pending scheduling backlog. Without filters, the page shows a full inspection view.")).toBeInTheDocument();
    expect(screen.getByText("Pending tasks stay out of this card to avoid backlog confusion.")).toBeInTheDocument();
  });

  it("shows explicit downgrade warning guidance when data source fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(fetchAgents).mockRejectedValueOnce(new Error("agents api unavailable"));
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("The agent overview is currently in degraded snapshot mode. Re-check run detail before governance actions.")).toBeInTheDocument();
    expect(screen.getByText("Agent registry is temporarily unavailable. Try again later.")).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("falls back to prefix-only agent labels when ids normalize to empty", async () => {
    vi.mocked(fetchAgents).mockResolvedValueOnce({
      agents: [{ agent_id: "!!!", role: "OPS", lock_count: 0, locked_paths: [] }],
      locks: [],
    } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getAllByText("AGENT").length).toBeGreaterThan(0);
  });

  it("sorts grouped agent rows by normalized agent id", async () => {
    vi.mocked(fetchAgents).mockResolvedValueOnce({
      agents: [
        { agent_id: "agent-000010", role: "OPS", lock_count: 0, locked_paths: [] },
        { agent_id: "agent-000002", role: "OPS", lock_count: 0, locked_paths: [] },
        { agent_id: "agent-000111", role: "OPS", lock_count: 0, locked_paths: [] },
      ],
      locks: [],
    } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));

    const text = document.body.textContent || "";
    expect(text.indexOf("AGENT-000002")).toBeGreaterThan(-1);
    expect(text.indexOf("AGENT-000010")).toBeGreaterThan(-1);
    expect(text.indexOf("AGENT-000111")).toBeGreaterThan(-1);
    expect(text.indexOf("AGENT-000002")).toBeLessThan(text.indexOf("AGENT-000010"));
    expect(text.indexOf("AGENT-000010")).toBeLessThan(text.indexOf("AGENT-000111"));
  });

  it("shows the read-only role catalog before the full agent inventory", async () => {
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
            skills_bundle_ref: {
              status: "resolved",
              ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
              bundle_id: "worker_delivery_core_v1",
              resolved_skill_set: ["l1-backend-verify"],
              validation: "fail-closed",
            },
            mcp_bundle_ref: {
              status: "resolved",
              ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
              resolved_mcp_tool_set: ["codex"],
              validation: "fail-closed",
            },
            runtime_binding: {
              status: "partially-resolved",
              authority_scope: "contract-derived-read-model",
              source: {
                runner: "unresolved",
                provider: "unresolved",
                model: "unresolved",
              },
              summary: {
                runner: null,
                provider: null,
                model: null,
              },
            },
          },
          registered_agent_count: 1,
          locked_agent_count: 0,
        },
      ],
    } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);
    vi.mocked(fetchRoleConfig).mockResolvedValueOnce({
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
    } as never);
    vi.mocked(previewRoleConfig).mockResolvedValue({} as never);
    vi.mocked(applyRoleConfig).mockResolvedValue({} as never);
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: false, operatorRole: null } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));

    expect(await screen.findByText("Role configuration desk")).toBeInTheDocument();
    expect(screen.getByText("Preview is available, but saving defaults requires an operator role.")).toBeInTheDocument();
    expect(screen.getByText("Role catalog (read-only first screen)")).toBeInTheDocument();
    expect(screen.getAllByText("task_contract").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/worker_delivery_core_v1/).length).toBeGreaterThan(0);
    expect(screen.getByText("Registered agent inventory (expandable, 1 items)")).toBeInTheDocument();
  });

  it("wires the role configuration desk preview flow", async () => {
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
            skills_bundle_ref: {
              status: "resolved",
              ref: "policies/skills_bundle_registry.json#bundles.worker_delivery_core_v1",
              bundle_id: "worker_delivery_core_v1",
              resolved_skill_set: [],
              validation: "fail-closed",
            },
            mcp_bundle_ref: {
              status: "resolved",
              ref: "policies/agent_registry.json#agents(role=WORKER).capabilities.mcp_tools",
              resolved_mcp_tool_set: [],
              validation: "fail-closed",
            },
            runtime_binding: {
              status: "unresolved",
              authority_scope: "contract-derived-read-model",
              source: {
                runner: "unresolved",
                provider: "unresolved",
                model: "unresolved",
              },
              summary: {
                runner: null,
                provider: null,
                model: null,
              },
            },
          },
          registered_agent_count: 1,
          locked_agent_count: 0,
        },
      ],
    } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValueOnce({ agents: [] } as never);
    vi.mocked(fetchRoleConfig).mockResolvedValueOnce({
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
        notes: [],
      },
    } as never);
    vi.mocked(previewRoleConfig).mockResolvedValueOnce({
      role: "WORKER",
      authority: "repo-owned-role-config",
      validation: "fail-closed",
      can_apply: true,
      current_surface: {} as never,
      preview_surface: {
        runtime_capability: {
          lane: "standard-provider-path",
          tool_execution: "provider-path-required",
        },
      } as never,
      changes: [],
    } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({}) }));
    fireEvent.click(await screen.findByRole("button", { name: "Preview defaults" }));
    await waitFor(() => expect(previewRoleConfig).toHaveBeenCalledTimes(1));
  });
});
