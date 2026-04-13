import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsPage } from "./AgentsPage";

vi.mock("../lib/api", () => ({
  fetchAgents: vi.fn(),
  fetchAgentStatus: vi.fn(),
  fetchRoleConfig: vi.fn(),
  previewRoleConfig: vi.fn(),
  applyRoleConfig: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
}));

import { fetchAgents, fetchAgentStatus, fetchRoleConfig } from "../lib/api";

describe("AgentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("uses the shared role-desk story on the first screen", async () => {
    vi.mocked(fetchAgents).mockResolvedValue({
      agents: [
        { agent_id: "agent-1", role: "PLANNER", notes: "primary planner", lock_count: 1 },
      ],
      locks: [],
      role_catalog: [
        {
          role: "PLANNER",
          purpose: "Drive wave planning",
          role_binding_read_model: {
            execution_authority: "registry-published",
            skills_bundle_ref: {
              status: "resolved",
              ref: "policies/skills_bundle_registry.json#bundles.planner",
              bundle_id: "planner",
              resolved_skill_set: [],
              validation: "fail-closed",
            },
            mcp_bundle_ref: {
              status: "resolved",
              ref: "policies/agent_registry.json#agents(role=PLANNER).capabilities.mcp_tools",
              resolved_mcp_tool_set: [],
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
        },
      ],
    } as any);
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      agents: [{ agent_id: "agent-1", role: "PLANNER", stage: "RUNNING", run_id: "run-123456789abc" }],
    } as any);
    vi.mocked(fetchRoleConfig).mockResolvedValue({
      role: "PLANNER",
      editable_now: {
        system_prompt_ref: "",
        skills_bundle_ref: "",
        mcp_bundle_ref: "",
        runtime_binding: {
          runner: "",
          provider: "",
          model: "",
        },
      },
      current_read_model: null,
      pending_preview: null,
      policy_notes: [],
    } as any);

    render(<AgentsPage />);

    expect(await screen.findByRole("heading", { level: 1, name: /Role desk|角色桌|Agents|代理/ })).toBeInTheDocument();
    expect(
      screen.getAllByText(/role desk|control-plane desk|role \/ control-plane desk/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { level: 2, name: /Role desk \(read-only mirror\)|角色 desk|Role desk/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Execution lane triage|执行 lane 分诊/ })).toBeInTheDocument();
    expect(screen.getByText(/Registered execution seats|已注册执行 seats/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("PLANNER").length).toBeGreaterThan(0);
      expect(screen.getAllByText("agent-1").length).toBeGreaterThan(0);
    });
  });
});
