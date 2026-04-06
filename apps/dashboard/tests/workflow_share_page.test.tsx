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

vi.mock("../lib/api", () => ({
  fetchQueue: vi.fn(),
  fetchReports: vi.fn(),
  fetchRun: vi.fn(),
  fetchWorkflow: vi.fn(),
}));

vi.mock("../lib/serverPageData", () => ({
  safeLoad: vi.fn(),
}));

import WorkflowSharePage from "../app/workflows/[id]/share/page";
import { fetchQueue, fetchReports, fetchRun, fetchWorkflow } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";

describe("workflow share page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(safeLoad).mockImplementation(async (loader: () => Promise<unknown>, fallback: unknown) => {
      try {
        return { data: await loader(), warning: "" };
      } catch {
        return { data: fallback, warning: "degraded" };
      }
    });
    vi.mocked(fetchWorkflow).mockResolvedValue({
      workflow: {
        workflow_id: "wf-share",
        status: "running",
        title: "Workflow share title",
        verdict: "active",
        summary: "Close the workflow case loop with proof attached.",
        owner_pm: "pm-owner",
        project_key: "cortex-case",
      },
      runs: [{ run_id: "run-share-1", status: "SUCCESS", created_at: "2026-03-31T12:00:00Z" }],
      events: [],
    } as never);
    vi.mocked(fetchQueue).mockResolvedValue([
      { task_id: "task-1", eligible: true, sla_state: "on_track" },
    ] as never);
    vi.mocked(fetchRun).mockResolvedValue({
      run_id: "run-share-1",
      status: "SUCCESS",
      failure_reason: "",
    } as never);
    vi.mocked(fetchReports).mockResolvedValue([
      { name: "run_compare_report.json", data: { compare_summary: { mismatched_count: 0 } } },
      { name: "proof_pack.json", data: { summary: "Proof is ready.", next_action: "Review the proof bundle.", proof_ready: true } },
      { name: "incident_pack.json", data: { summary: "No incident blocker.", next_action: "Proceed with normal review." } },
    ] as never);
  });

  it("renders a share-ready workflow case asset with export actions", async () => {
    render(await WorkflowSharePage({ params: Promise.resolve({ id: "wf-share" }) }));

    expect(screen.getByRole("heading", { name: "Workflow Case share-ready asset" })).toBeInTheDocument();
    expect(screen.getByText("Title: Workflow share title")).toBeInTheDocument();
    expect(screen.getByText("Close the workflow case loop with proof attached.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy share link" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download case asset JSON" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open latest run" })).toHaveAttribute("href", "/runs/run-share-1");
    expect(screen.getByRole("link", { name: "Open compare surface" })).toHaveAttribute("href", "/runs/run-share-1/compare");
  });

  it("does not claim compare alignment when compare truth is unavailable", async () => {
    vi.mocked(fetchReports).mockRejectedValueOnce(new Error("reports unavailable"));

    render(await WorkflowSharePage({ params: Promise.resolve({ id: "wf-share" }) }));

    expect(screen.getByText("Share-ready asset is in read-only degraded mode")).toBeInTheDocument();
    expect(screen.getByText(/The latest compare summary is unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/currently aligned with its baseline/i)).toBeNull();
  });
});
