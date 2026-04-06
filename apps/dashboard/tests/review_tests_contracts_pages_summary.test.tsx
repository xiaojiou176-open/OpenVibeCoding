import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchReviews: vi.fn(),
  fetchTests: vi.fn(),
  fetchContracts: vi.fn(),
}));

import ReviewsPage from "../app/reviews/page";
import TestsPage from "../app/tests/page";
import ContractsPage from "../app/contracts/page";
import { fetchContracts, fetchReviews, fetchTests } from "../lib/api";

describe("summary-first rendering for reviews/tests/contracts pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reviews page keeps JSON in collapsible detail only", async () => {
    vi.mocked(fetchReviews).mockResolvedValueOnce([
      {
        run_id: "run-review-1",
        report: {
          verdict: "PASS",
          reviewed_at: "2026-03-08T08:00:00Z",
          summary: { summary_en: "Code review passed" },
          scope_check: { ok: false, violations: ["path outside allowed"] },
          evidence: ["reports/review.json"],
        },
      },
    ] as never[]);

    render(await ReviewsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("Triage failed verdicts and scope violations before drilling into evidence and the raw report.")).toBeInTheDocument();
    expect(screen.getByText("Code review passed")).toBeInTheDocument();
    expect(screen.getByText("Failed (1 issue)")).toBeInTheDocument();
    expect(screen.getByText("Needs triage")).toBeInTheDocument();

    const preBlocks = document.querySelectorAll("pre");
    expect(preBlocks.length).toBe(1);
    expect(screen.getByText("Full report JSON")).toBeInTheDocument();
  });

  it("tests page keeps JSON in collapsible detail only", async () => {
    vi.mocked(fetchTests).mockResolvedValueOnce([
      {
        run_id: "run-test-1",
        report: {
          status: "FAILED",
          started_at: "2026-03-08T08:00:00Z",
          finished_at: "2026-03-08T08:03:00Z",
          summary: { passed: 8, failed: 2, skipped: 1 },
          failure: { code: "E2E_FAIL", reason: "playwright timeout" },
          commands: ["npm run test"],
        },
      },
    ] as never[]);

    render(await TestsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("Triage failed and running test reports first, then inspect commands, summaries, and the full report.")).toBeInTheDocument();
    expect(screen.getByText("Passed 8 / Failed 2 / Skipped 1")).toBeInTheDocument();
    expect(screen.getByText("E2E_FAIL / playwright timeout")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();

    const preBlocks = document.querySelectorAll("pre");
    expect(preBlocks.length).toBe(1);
    expect(screen.getByText("Full report JSON")).toBeInTheDocument();
  });

  it("contracts page keeps JSON in collapsible detail only", async () => {
    vi.mocked(fetchContracts).mockResolvedValueOnce([
      {
        path: "runs/run-contract-1/contract.json",
        source: "runs_root",
        task_id: "task-1",
        allowed_paths: ["apps/dashboard"],
        acceptance_tests: ["npm run test"],
        tool_permissions: { shell: "allow", network: "deny" },
        assigned_role: "TECH_LEAD",
        execution_authority: "task_contract",
        role_binding_read_model: {
          authority: "contract-derived-read-model",
          source: "derived from compiled role_contract and runtime inputs; not an execution authority surface",
          execution_authority: "task_contract",
          skills_bundle_ref: {
            status: "resolved",
            ref: "policies/skills_bundle_registry.json#bundles.tech_lead_contract_bridge_v1",
            bundle_id: "tech_lead_contract_bridge_v1",
            resolved_skill_set: ["l1-product-plan-and-delegate"],
            validation: "fail-closed",
          },
          mcp_bundle_ref: {
            status: "unresolved",
            ref: null,
            resolved_mcp_tool_set: [],
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
            capability: {
              status: "previewable",
              lane: "switchyard-chat-compatible",
              compat_api_mode: "chat_completions",
              provider_status: "unresolved",
              provider_inventory_id: null,
              tool_execution: "fail-closed",
              notes: [
                "Chat-style compatibility may differ from tool-execution capability.",
                "Execution authority remains task_contract even when role defaults change.",
              ],
            },
          },
        },
        payload: {
          task_id: "task-1",
          allowed_paths: ["apps/dashboard"],
          acceptance_tests: ["npm run test"],
          tool_permissions: { shell: "allow", network: "deny" },
        },
      },
    ] as never[]);

    render(await ContractsPage({ searchParams: Promise.resolve({}) }));

    const permissionRow = screen.getByText("Tool permissions").closest(".data-list-row");
    expect(permissionRow).not.toBeNull();
    expect(within(permissionRow as HTMLElement).getByText("shell: allow")).toBeInTheDocument();
    expect(within(permissionRow as HTMLElement).getByText("network: deny")).toBeInTheDocument();
    expect(screen.getByText("task_contract")).toBeInTheDocument();
    expect(screen.getByText(/tech_lead_contract_bridge_v1/)).toBeInTheDocument();
    expect(screen.getByText("switchyard-chat-compatible")).toBeInTheDocument();
    expect(screen.getByText("switchyard-chat-compatible / fail-closed")).toBeInTheDocument();

    const preBlocks = document.querySelectorAll("pre");
    expect(preBlocks.length).toBe(1);
    expect(screen.getByText("Full contract JSON")).toBeInTheDocument();
  });

  it("contracts page exposes expand-all link when more than the default rows exist", async () => {
    vi.mocked(fetchContracts).mockResolvedValueOnce(
      Array.from({ length: 11 }).map((_, index) => ({
        path: `runs/run-contract-${index + 1}/contract.json`,
        source: "runs_root",
        task_id: `task-${index + 1}`,
        allowed_paths: ["apps/dashboard"],
        acceptance_tests: ["npm run test"],
        tool_permissions: { shell: "allow" },
        payload: {
          task_id: `task-${index + 1}`,
          allowed_paths: ["apps/dashboard"],
          acceptance_tests: ["npm run test"],
          tool_permissions: { shell: "allow" },
        },
      })) as never[],
    );

    render(await ContractsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("link", { name: "Show all" })).toHaveAttribute("href", "/contracts?q=&limit=11");
  });

  it("tests page exposes expand-all link when more than the default rows exist", async () => {
    vi.mocked(fetchTests).mockResolvedValueOnce(
      Array.from({ length: 11 }).map((_, index) => ({
        run_id: `run-test-${index + 1}`,
        report: {
          status: "PASSED",
          started_at: "2026-03-08T08:00:00Z",
          finished_at: "2026-03-08T08:03:00Z",
          summary: { passed: 1, failed: 0, skipped: 0 },
        },
      })) as never[],
    );

    render(await TestsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("link", { name: "Show all" })).toHaveAttribute("href", "/tests?q=&status=ALL&limit=11");
  });

  it("reviews page exposes expand-all link and summary fallback copy", async () => {
    vi.mocked(fetchReviews).mockResolvedValueOnce(
      Array.from({ length: 11 }).map((_, index) => ({
        run_id: `run-review-${index + 1}`,
        report: {
          verdict: index === 0 ? "UNKNOWN" : "PASS",
          reviewed_at: index === 0 ? "" : "2026-03-08T08:00:00Z",
          summary: index === 0 ? { foo: "bar" } : { summary_en: "Code review passed" },
        },
      })) as never[],
    );

    render(await ReviewsPage({ searchParams: Promise.resolve({ q: "run-review", limit: "10" }) }));

    expect(screen.getByText("A structured summary is available. Expand the full report for details.")).toBeInTheDocument();
    expect(screen.getByText("-")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show all" })).toHaveAttribute("href", "/reviews?q=run-review&limit=11");
  });

  it("reviews page covers scope-check pass, count, and no-count variants", async () => {
    vi.mocked(fetchReviews).mockResolvedValueOnce([
      {
        run_id: "run-review-reject",
        report: {
          verdict: "REJECT",
          reviewed_at: "2026-03-08T08:00:00Z",
          summary: "Needs manual follow-up",
          scope_check: { passed: true },
        },
      },
      {
        run_id: "run-review-approved",
        report: {
          verdict: "APPROVED",
          reviewed_at: "2026-03-08T08:05:00Z",
          summary: { summary_en: "Code review passed" },
          scope_check: { issues: ["scope-a", "scope-b"] },
        },
      },
      {
        run_id: "run-review-pending",
        report: {
          verdict: "PENDING",
          reviewed_at: "2026-03-08T08:10:00Z",
          summary: "",
          scope_check: { issues: [] },
        },
      },
    ] as never[]);

    render(await ReviewsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("Needs manual follow-up")).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getByText("Failed (2 issues)")).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByText("Needs triage")).toBeInTheDocument();
  });

  it("reviews page query matches verdict text and hides non-matching rows", async () => {
    vi.mocked(fetchReviews).mockResolvedValueOnce([
      {
        run_id: "run-review-pass",
        report: {
          verdict: "APPROVED",
          reviewed_at: "2026-03-08T08:00:00Z",
          summary: { summary_en: "Code review passed" },
        },
      },
      {
        run_id: "run-review-fail",
        report: {
          verdict: "REJECT",
          reviewed_at: "2026-03-08T08:05:00Z",
          summary: { summary_en: "Rework required" },
        },
      },
    ] as never[]);

    render(await ReviewsPage({ searchParams: Promise.resolve({ q: "approved" }) }));

    expect(screen.getByRole("link", { name: "run-review-pass" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "run-review-fail" })).not.toBeInTheDocument();
  });

  it("tests page renders summary and failure fallbacks for mixed record shapes", async () => {
    vi.mocked(fetchTests).mockResolvedValueOnce([
      {
        run_id: "run-test-fallback-1",
        report: {
          status: "queued",
          started_at: "",
          finished_at: "",
          summary: { foo: "bar" },
          failure: "raw failure text",
        },
      },
    ] as never[]);

    render(await TestsPage({ searchParams: Promise.resolve({ q: "run-test-fallback-1", status: "QUEUED" }) }));

    expect(screen.getByText("Passed 0 / Failed 0 / Skipped 0")).toBeInTheDocument();
    expect(screen.getByText("raw failure text")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Running 0 / Total 1")).toBeInTheDocument();
  });

  it("reviews page covers failed-metric and scope fallback branches", async () => {
    vi.mocked(fetchReviews).mockResolvedValueOnce([
      {
        run_id: "run-review-failed-1",
        report: {
          verdict: "FAILED",
          reviewed_at: "2026-03-08T08:00:00Z",
          summary: "Manual review failed",
          scope_check: true,
        },
      },
      {
        run_id: "run-review-scope-pass",
        report: {
          verdict: "PASS",
          reviewed_at: "2026-03-08T08:01:00Z",
          summary: { summary_en: "Code review passed" },
          scope_check: { ok: true },
        },
      },
      {
        run_id: "run-review-scope-violations",
        report: {
          verdict: "PASS",
          reviewed_at: "2026-03-08T08:02:00Z",
          summary: { summary_en: "Evidence needs completion" },
          scope_check: { violations: ["missing report"] },
        },
      },
      {
        run_id: "run-review-scope-fallback",
        report: {
          verdict: "PASS",
          reviewed_at: "2026-03-08T08:03:00Z",
          summary: { summary_en: "Waiting for recheck" },
          scope_check: { foo: "bar" },
        },
      },
    ] as never[]);

    render(await ReviewsPage({}));

    expect(screen.getByText("Manual review failed")).toBeInTheDocument();
    expect(screen.getByText("Scope check data unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
    expect(screen.getByText("Failed (1 issue)")).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
    expect(screen.getByText("Needs triage")).toBeInTheDocument();
  });

  it("contracts page resolves raw contract payload fallback and expand-all link", async () => {
    vi.mocked(fetchContracts).mockResolvedValueOnce(
      Array.from({ length: 11 }).map((_, index) => ({
        path: `runs/run-contract-${index + 1}/contract.json`,
        source: index === 0 ? "" : "runs_root",
        task_id: index === 0 ? "" : `task-${index + 1}`,
        run_id: index === 0 ? "run-fallback" : "",
        allowed_paths: index === 0 ? [] : ["apps/dashboard"],
        acceptance_tests: index === 0 ? [] : ["npm run test"],
        tool_permissions: index === 0 ? {} : { shell: "allow" },
      })) as never[],
    );

    render(await ContractsPage({ searchParams: Promise.resolve({ q: "run-contract", limit: "10" }) }));

    expect(screen.getByText("Unrestricted")).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show all" })).toHaveAttribute("href", "/contracts?q=run-contract&limit=11");
  });

  it("contracts page falls back to default permissions text when tool permissions are non-object", async () => {
    vi.mocked(fetchContracts).mockResolvedValueOnce([
      {
        path: "runs/run-contract-invalid/contract.json",
        source: "runs_root",
        task_id: "task-invalid",
        allowed_paths: ["apps/dashboard"],
        acceptance_tests: ["npm run test"],
        tool_permissions: "inherit",
        payload: {
          task_id: "task-invalid",
          allowed_paths: ["apps/dashboard"],
          acceptance_tests: ["npm run test"],
          tool_permissions: "inherit",
        },
      },
    ] as never[]);

    render(await ContractsPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("reviews page renders warning snapshot and filtered empty state", async () => {
    vi.mocked(fetchReviews).mockRejectedValueOnce(new Error("review backend down"));

    render(await ReviewsPage({ searchParams: Promise.resolve({ q: "missing-review" }) }));

    expect(screen.getByText("Review data is currently served from a degraded snapshot. Open run detail before taking governance action.")).toBeInTheDocument();
    expect(screen.getByText("No reviews yet")).toBeInTheDocument();
    expect(screen.getByText("No reviews matched this filter. Adjust the keyword and try again.")).toBeInTheDocument();
  });

  it("tests page renders warning snapshot and filtered empty state", async () => {
    vi.mocked(fetchTests).mockRejectedValueOnce(new Error("test backend down"));

    render(await TestsPage({ searchParams: Promise.resolve({ q: "missing-test", status: "FAILED" }) }));

    expect(screen.getByText("Test data is currently in degraded snapshot mode. Re-check run detail before approving any release action.")).toBeInTheDocument();
    expect(screen.getByText("No test reports yet")).toBeInTheDocument();
    expect(screen.getByText("No reports match the current filter. Adjust it and try again.")).toBeInTheDocument();
  });

  it("contracts page renders warning snapshot and empty state", async () => {
    vi.mocked(fetchContracts).mockRejectedValueOnce(new Error("contract backend down"));

    render(await ContractsPage({ searchParams: Promise.resolve({ q: "missing-contract" }) }));

    expect(screen.getByRole("status")).toHaveTextContent("Contract list");
    expect(screen.getByText("No contracts yet")).toBeInTheDocument();
    expect(screen.getByText("Contracts are generated automatically when work is assigned.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply filter" })).not.toBeDisabled();
  });
});
