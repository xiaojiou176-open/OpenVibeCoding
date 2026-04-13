import { render, screen } from "@testing-library/react";
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
import { fetchAgents, fetchAgentStatus, fetchRoleConfig } from "../lib/api";

function buildStatuses(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    run_id: `run-${index}`,
    task_id: `task-${index}`,
    role: "WORKER",
    stage: "RUNNING",
    agent_id: `agent-${index}`,
  }));
}

describe("agents page pagination semantics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAgents).mockResolvedValue({ agents: [], locks: [] } as never);
    vi.mocked(fetchAgentStatus).mockResolvedValue({ agents: [] } as never);
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
    } as never);
  });

  it("renders disabled pagination as non-link semantics on boundary pages", async () => {
    render(await AgentsPage({ searchParams: Promise.resolve({ page: "1" }) }));

    expect(screen.getByRole("heading", { name: "Scheduling and task triage detail" })).toBeInTheDocument();
    expect(screen.getByText("Failure-led queue")).toBeInTheDocument();
    expect(screen.getByText("Registered capacity")).toBeInTheDocument();
    expect(screen.getByText("Pending scheduling backlog")).toBeInTheDocument();
    expect(screen.getByText("Role desk (read-only mirror)")).toBeInTheDocument();

    expect(screen.queryByRole("link", { name: "Previous" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Next" })).toBeNull();
    expect(screen.getByRole("navigation", { name: "Agent pagination navigation (footer)" })).toBeInTheDocument();

    const prevDisabled = screen.getAllByText("Previous");
    const nextDisabled = screen.getAllByText("Next");
    expect(prevDisabled).toHaveLength(1);
    expect(nextDisabled).toHaveLength(1);
    for (const element of [...prevDisabled, ...nextDisabled]) {
      expect(element).toHaveAttribute("aria-disabled", "true");
    }
    expect(screen.getAllByText("Page 1 / 1 (15 rows per page)")).toHaveLength(1);
    for (const indicator of screen.getAllByText("Page 1 / 1 (15 rows per page)")) {
      expect(indicator).toHaveAttribute("role", "status");
      expect(indicator).toHaveAttribute("aria-live", "polite");
    }
  });

  it("renders active pagination controls as real links with deterministic href", async () => {
    vi.mocked(fetchAgentStatus).mockResolvedValue({ agents: buildStatuses(31) } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({ page: "2" }) }));

    const prevLinks = screen.getAllByRole("link", { name: "Previous" });
    const nextLinks = screen.getAllByRole("link", { name: "Next" });
    expect(prevLinks).toHaveLength(1);
    expect(nextLinks).toHaveLength(1);
    for (const element of prevLinks) {
      expect(element).toHaveAttribute("href", "/agents?page=1");
    }
    for (const element of nextLinks) {
      expect(element).toHaveAttribute("href", "/agents?page=3");
    }
  });

  it("renders fallback row semantics for missing run/agent context and failed stage", async () => {
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      agents: [
        {
          run_id: "",
          task_id: "",
          role: "",
          stage: "timeout",
          agent_id: "",
          worktree: "",
          path: "",
        },
      ],
    } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({ page: "1" }) }));

    expect(screen.getByText("Scheduling failed")).toBeInTheDocument();
    expect(screen.getByText("System task")).toBeInTheDocument();
    expect(screen.getAllByText("Pending scheduling").length).toBeGreaterThan(0);
    expect(screen.getByText("Run ID missing")).toBeInTheDocument();
    expect(screen.getByText("Unbound")).toBeInTheDocument();
  });

  it("renders safe-load warning and clamps invalid page to first page", async () => {
    vi.mocked(fetchAgentStatus).mockRejectedValue(new Error("boom"));

    render(
      await AgentsPage({
        searchParams: Promise.resolve({ page: "-2", q: [" RUN-1 ", "ignored"], role: "worker" }),
      })
    );

    const warningStatus = screen.getAllByRole("status").find((node) => node.textContent?.includes("Agent state machine"));
    expect(warningStatus).not.toBeUndefined();
    expect(warningStatus?.textContent ?? "").toContain("Agent state machine");
    expect(screen.getAllByText("Page 1 / 1 (15 rows per page)")).toHaveLength(1);
  });

  it("renders deterministic governance links for run detail, failed runs and failed events", async () => {
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      agents: [
        {
          run_id: "run alpha/1",
          task_id: "task-alpha",
          role: "WORKER",
          stage: "FAILED",
          agent_id: "agent-alpha",
        },
      ],
    } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({ page: "1" }) }));

    const runDetailLink = screen.getByRole("link", { name: "Detail" });
    expect(runDetailLink).toHaveAttribute("href", "/runs/run%20alpha%2F1");
    expect(runDetailLink).toHaveAttribute("title", expect.stringContaining("run detail"));

    const failedRunLinks = screen.getAllByRole("link", { name: "View failed runs in bulk" });
    expect(failedRunLinks.length).toBeGreaterThan(0);
    for (const link of failedRunLinks) {
      expect(link).toHaveAttribute("href", "/runs?status=FAILED");
    }

    const registeredAgentsLink = screen.getByRole("link", { name: "Go to the registered agent list" });
    expect(registeredAgentsLink).toHaveAttribute("href", "#agents-role-catalog-title");
    expect(registeredAgentsLink).toHaveTextContent("View role catalog");

    expect(screen.getByRole("link", { name: "Failed events" })).toHaveAttribute("href", "/events");
  });

  it("avoids duplicate React key warnings for repeated agent/lock rows", async () => {
    vi.mocked(fetchAgents).mockResolvedValue({
      agents: [
        { agent_id: "dup-agent", role: "WORKER", lock_count: 1, locked_paths: ["/tmp/a"] },
        { agent_id: "dup-agent", role: "WORKER", lock_count: 1, locked_paths: ["/tmp/a"] },
      ],
      locks: [
        {
          lock_id: "dup-lock",
          run_id: "run-x",
          agent_id: "dup-agent",
          role: "WORKER",
          path: "/tmp/path",
          ts: "2026-03-02T00:00:00Z",
        },
        {
          lock_id: "dup-lock",
          run_id: "run-x",
          agent_id: "dup-agent",
          role: "WORKER",
          path: "/tmp/path",
          ts: "2026-03-02T00:00:00Z",
        },
      ],
    } as never);

    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let hasDuplicateKeyWarning = false;
    try {
      render(await AgentsPage({ searchParams: Promise.resolve({ page: "1" }) }));
      hasDuplicateKeyWarning = consoleErrorSpy.mock.calls.some((args) =>
        args.some((value) => String(value).includes("Encountered two children with the same key"))
      );
    } finally {
      consoleErrorSpy.mockRestore();
    }
    expect(hasDuplicateKeyWarning).toBe(false);
  });

  it("maps mixed stage states to actionable labels and context rendering", async () => {
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      agents: [
        {
          run_id: "run-verify",
          task_id: "task-verify",
          role: "REVIEWER",
          stage: "VERIFY_PENDING",
          agent_id: "agent-verify",
          worktree: "/tmp/worktrees/run-verify/task-verify",
        },
        {
          run_id: "run-done",
          task_id: "task-done",
          role: "WORKER",
          stage: "DONE",
          agent_id: "agent-done",
        },
        {
          run_id: "run-init",
          task_id: "task-init",
          role: "",
          stage: "INIT_BOOT",
          agent_id: "",
          worktree: "",
          path: "",
        },
      ],
    } as never);

    render(await AgentsPage({ searchParams: Promise.resolve({ page: "1" }) }));

    expect(screen.getByText("In review")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Bootstrapping")).toBeInTheDocument();
    expect(screen.getByText(/Node/)).toBeInTheDocument();
  });

  it("shows active filter CTA and keeps query params in pagination links", async () => {
    vi.mocked(fetchAgentStatus).mockResolvedValue({
      agents: buildStatuses(31).map((item) => ({ ...item, role: "WORKER" })),
    } as never);

    render(
      await AgentsPage({
        searchParams: Promise.resolve({ page: "2", q: ["run-"], role: ["worker"] }),
      }),
    );

    expect(screen.getByRole("button", { name: "Apply filter" })).toBeInTheDocument();
    expect(screen.queryByText("Leave the fields empty to show everything, then apply the filter once criteria are ready.")).toBeNull();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/agents?q=run-&role=WORKER&page=1",
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/agents?q=run-&role=WORKER&page=3",
    );
  });
});
