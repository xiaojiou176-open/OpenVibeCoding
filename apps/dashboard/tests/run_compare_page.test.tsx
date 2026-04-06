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
  fetchOperatorCopilotBrief: vi.fn(),
  fetchReports: vi.fn(),
  fetchRun: vi.fn(),
}));

vi.mock("../lib/serverPageData", () => ({
  safeLoad: vi.fn(),
}));

import RunComparePage from "../app/runs/[id]/compare/page";
import { fetchReports, fetchRun } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";

describe("run compare decision surface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(safeLoad).mockImplementation(async (loader: () => Promise<unknown>, fallback: unknown) => {
      try {
        return { data: await loader(), warning: "" };
      } catch {
        return { data: fallback, warning: "degraded" };
      }
    });
    vi.mocked(fetchRun).mockResolvedValue({ run_id: "run-compare-1", status: "SUCCESS" } as never);
    vi.mocked(fetchReports).mockResolvedValue([
      {
        name: "run_compare_report.json",
        data: {
          report_type: "run_compare_report",
          run_id: "run-compare-1",
          baseline_run_id: "run-baseline-1",
          status: "fail",
          compare_summary: {
            mismatched_count: 2,
            missing_count: 1,
            extra_count: 0,
            missing_reports_count: 0,
            failed_report_checks_count: 1,
            evidence_ok: false,
            llm_params_ok: true,
            llm_snapshot_ok: true,
          },
        },
      },
      {
        name: "incident_pack.json",
        data: {
          report_type: "incident_pack",
          summary: "A blocking gate stopped the run.",
          next_action: "Review the blocking gate before replay.",
        },
      },
      {
        name: "proof_pack.json",
        data: {
          report_type: "proof_pack",
          summary: "Proof artifacts exist for the successful slice.",
          next_action: "Review the proof bundle before sharing.",
        },
      },
    ] as never);
  });

  it("renders decision-first compare cards before raw JSON", async () => {
    render(await RunComparePage({ params: Promise.resolve({ id: "run-compare-1" }) }));

    expect(screen.getByText("Decision summary")).toBeInTheDocument();
    expect(screen.getByText("Decision needed")).toBeInTheDocument();
    expect(screen.getByText(/comparison found at least one delta/i)).toBeInTheDocument();
    expect(screen.getByText("Key deltas")).toBeInTheDocument();
    expect(screen.getByText("Mismatched hashes")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/Incident: A blocking gate stopped the run\./)).toBeInTheDocument();
    expect(screen.getByText("AI compare copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain these deltas" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open run detail" })).toHaveAttribute("href", "/runs/run-compare-1");
  });
});
