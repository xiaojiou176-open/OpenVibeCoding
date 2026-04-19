import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentsRoleConfigPanel } from "./AgentsRoleConfigPanel";

vi.mock("../lib/api", () => ({
  applyRoleConfig: vi.fn(),
  fetchRoleConfig: vi.fn(),
  mutationExecutionCapability: vi.fn(() => ({ executable: false, operatorRole: null })),
  previewRoleConfig: vi.fn(),
}));

import { applyRoleConfig, fetchRoleConfig, mutationExecutionCapability, previewRoleConfig } from "../lib/api";

function makeSurface(overrides: Record<string, unknown> = {}) {
  return {
    persisted_source: "policies/role_config_registry.json",
    execution_authority: "task_contract",
    editable_now: {
      system_prompt_ref: "policies/agents/codex/roles/20_planner_core.md",
      skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.planner",
      mcp_bundle_ref: "policies/agent_registry.json#agents(role=PLANNER).capabilities.mcp_tools",
      runtime_binding: {
        runner: "agents",
        provider: "cliproxyapi",
        model: "gpt-5.4",
      },
    },
    ...overrides,
  } as any;
}

describe("AgentsRoleConfigPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: false, operatorRole: null } as any);
  });

  it("shows the empty-state desk when no roles are available", () => {
    render(<AgentsRoleConfigPanel roleCatalog={[]} onApplied={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Role configuration desk" })).toBeInTheDocument();
    expect(screen.getByText("No registered roles are available for configuration yet.")).toBeInTheDocument();
  });

  it("renders zh-CN desk copy when locale is passed", () => {
    render(<AgentsRoleConfigPanel roleCatalog={[]} onApplied={vi.fn()} locale="zh-CN" />);

    expect(screen.getByRole("heading", { name: "角色配置桌" })).toBeInTheDocument();
    expect(screen.getByText("当前还没有可配置的已注册角色。")).toBeInTheDocument();
  });

  it("supports preview mode and reports role-load failures when switching roles", async () => {
    let resolveFirstFetch: (value: any) => void = () => {};
    vi.mocked(fetchRoleConfig)
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirstFetch = resolve;
      }) as any)
      .mockRejectedValueOnce("role config fetch failed");
    vi.mocked(previewRoleConfig).mockResolvedValue({
      changes: [
        { field: "runtime_binding.runner", current: "agents", next: "codex" },
      ],
      preview_surface: {
        runtime_capability: {
          lane: "tool-capable-provider",
          tool_execution: "available",
        },
      },
    } as any);

    render(
      <AgentsRoleConfigPanel
        roleCatalog={[
          { role: "PLANNER", purpose: "Drive wave planning" },
          { role: "REVIEWER" },
        ] as any}
        onApplied={vi.fn()}
      />,
    );

    expect(screen.getByText("Loading role configuration…")).toBeInTheDocument();

    resolveFirstFetch(makeSurface());
    expect(await screen.findByText("Drive wave planning")).toBeInTheDocument();
    expect(screen.getByText("Preview only")).toBeInTheDocument();
    expect(screen.getByText("Preview is available, but saving defaults requires an operator role.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Runtime runner"), { target: { value: "codex" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview defaults" }));

    await waitFor(() => {
      expect(previewRoleConfig).toHaveBeenCalledWith("PLANNER", {
        system_prompt_ref: "policies/agents/codex/roles/20_planner_core.md",
        skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.planner",
        mcp_bundle_ref: "policies/agent_registry.json#agents(role=PLANNER).capabilities.mcp_tools",
        runtime_binding: {
          runner: "codex",
          provider: "cliproxyapi",
          model: "gpt-5.4",
        },
      });
    });
    await waitFor(() => {
      expect(screen.getAllByText("Runtime runner").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("agents → codex")).toBeInTheDocument();
    expect(screen.getByText("tool-capable-provider")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Select role for role configuration"), { target: { value: "REVIEWER" } });

    expect(await screen.findByText("role config fetch failed")).toBeInTheDocument();
    expect(screen.getByText("No role purpose published yet.")).toBeInTheDocument();
  });

  it("applies repo defaults when mutation execution is enabled", async () => {
    const onApplied = vi.fn().mockResolvedValue(undefined);

    vi.mocked(fetchRoleConfig).mockResolvedValue(makeSurface());
    vi.mocked(mutationExecutionCapability).mockReturnValue({ executable: true, operatorRole: "OPS" } as any);
    vi.mocked(previewRoleConfig).mockResolvedValue({
      changes: [],
      preview_surface: {
        runtime_capability: {
          lane: "standard-provider-path",
          tool_execution: "provider-path-required",
        },
      },
    } as any);
    vi.mocked(applyRoleConfig).mockResolvedValue({
      role: "PLANNER",
      surface: makeSurface({
        editable_now: {
          system_prompt_ref: "policies/agents/codex/roles/30_ops.md",
          skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.planner",
          mcp_bundle_ref: "policies/agent_registry.json#agents(role=PLANNER).capabilities.mcp_tools",
          runtime_binding: {
            runner: "codex",
            provider: null,
            model: null,
          },
        },
      }),
    } as any);

    render(
      <AgentsRoleConfigPanel
        roleCatalog={[{ role: "PLANNER", purpose: "Drive wave planning" }] as any}
        onApplied={onApplied}
      />,
    );

    expect(await screen.findByText("Apply enabled for OPS")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("System prompt ref"), {
      target: { value: "  policies/agents/codex/roles/30_ops.md  " },
    });
    fireEvent.change(screen.getByLabelText("Runtime runner"), { target: { value: "codex" } });
    fireEvent.change(screen.getByLabelText("Runtime provider"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Runtime model"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Save repo defaults" }));

    await waitFor(() => {
      expect(applyRoleConfig).toHaveBeenCalledWith("PLANNER", {
        system_prompt_ref: "policies/agents/codex/roles/30_ops.md",
        skills_bundle_ref: "policies/skills_bundle_registry.json#bundles.planner",
        mcp_bundle_ref: "policies/agent_registry.json#agents(role=PLANNER).capabilities.mcp_tools",
        runtime_binding: {
          runner: "codex",
          provider: null,
          model: null,
        },
      });
    });

    expect(await screen.findByText("Saved repo-owned defaults for PLANNER.")).toBeInTheDocument();
    expect(onApplied).toHaveBeenCalledTimes(1);
    expect(screen.getByText("codex / Not set / Not set")).toBeInTheDocument();
  });
});
