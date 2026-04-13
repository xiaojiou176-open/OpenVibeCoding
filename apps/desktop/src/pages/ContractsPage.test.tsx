import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContractsPage } from "./ContractsPage";

vi.mock("../lib/api", () => ({
  fetchContracts: vi.fn(),
}));

import { fetchContracts } from "../lib/api";

describe("ContractsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchContracts).mockResolvedValue([] as any);
  });

  afterEach(() => {
    cleanup();
  });

  it("renders empty state and then contract details after refresh", async () => {
    vi.mocked(fetchContracts)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          task_id: "task-1",
          run_id: "run-1",
          allowed_paths: ["apps/desktop/src"],
          acceptance_tests: ["pnpm test"],
          tool_permissions: { shell: "allow" },
          role_binding_read_model: {
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
                notes: [],
              },
            },
          },
        },
      ] as any);
    const user = userEvent.setup();
    render(<ContractsPage />);
    expect(await screen.findByRole("heading", { name: /Contract desk|合约桌|Contracts|合约/ })).toBeInTheDocument();
    expect(screen.getByText(/contract desk|command tower 的 contract desk/i, { selector: "p.page-subtitle" })).toBeInTheDocument();
    expect(await screen.findByText(/No contracts yet|暂无合约/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Refresh|刷新/ }));
    expect(await screen.findByRole("heading", { level: 2, name: /Contract triage queue|先处理哪份 contract/ })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("task-1").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("apps/desktop/src")).toBeInTheDocument();
    expect(screen.getByText("pnpm test")).toBeInTheDocument();
    expect(screen.getByText(/"shell": "allow"/)).toBeInTheDocument();
    expect(screen.getByText("standard-provider-path")).toBeInTheDocument();
    expect(screen.getByText("standard-provider-path / provider-path-required")).toBeInTheDocument();
  });

  it("surfaces load error", async () => {
    vi.mocked(fetchContracts).mockRejectedValue(new Error("contracts down"));
    render(<ContractsPage />);
    await waitFor(() => {
      expect(screen.getByText("contracts down")).toBeInTheDocument();
    });
  });
});
