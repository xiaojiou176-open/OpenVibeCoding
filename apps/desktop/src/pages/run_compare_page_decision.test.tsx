import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RunComparePage } from "./RunComparePage";

vi.mock("../lib/api", () => ({
  fetchOperatorCopilotBrief: vi.fn(),
  fetchReports: vi.fn(),
  fetchRun: vi.fn(),
}));

import { fetchOperatorCopilotBrief, fetchReports, fetchRun } from "../lib/api";

describe("RunComparePage decision surface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchOperatorCopilotBrief).mockResolvedValue({
      report_type: "operator_copilot_brief",
      generated_at: "2026-03-31T12:00:00Z",
      scope: "run",
      subject_id: "run-compare-1",
      run_id: "run-compare-1",
      workflow_id: "wf-1",
      status: "OK",
      summary: "The current compare still needs operator review.",
      likely_cause: "One material delta still separates this run from its baseline.",
      compare_takeaway: "The compare surface still shows a material mismatch.",
      proof_takeaway: "Proof exists but is not ready for promotion yet.",
      incident_takeaway: "A blocking gate still needs review.",
      queue_takeaway: "Queue posture is stable.",
      approval_takeaway: "No current approval blocker is attached.",
      recommended_actions: ["Review the compare delta before deciding to replay."],
      top_risks: ["Compare delta"],
      questions_answered: [],
      used_truth_surfaces: [],
      limitations: [],
      provider: "gemini",
      model: "gemini-2.5-flash",
    } as never);
    vi.mocked(fetchRun).mockResolvedValue({ run_id: "run-compare-1", status: "SUCCESS" } as never);
    vi.mocked(fetchReports).mockResolvedValue([
      {
        name: "run_compare_report.json",
        data: {
          compare_summary: {
            mismatched_count: 2,
            missing_count: 1,
            extra_count: 0,
            failed_report_checks_count: 1,
            evidence_ok: false,
            llm_params_ok: true,
            llm_snapshot_ok: true,
          },
        },
      },
      {
        name: "incident_pack.json",
        data: { summary: "A gate blocked the run." },
      },
      {
        name: "proof_pack.json",
        data: { summary: "Proof artifacts are ready." },
      },
    ] as never);
  });

  it("renders decision-first compare cards", async () => {
    render(<RunComparePage runId="run-compare-1" onBack={vi.fn()} />);

    expect(await screen.findByText("Decision summary")).toBeInTheDocument();
    expect(screen.getByText("Decision needed")).toBeInTheDocument();
    expect(screen.getByText("Key deltas")).toBeInTheDocument();
    expect(screen.getByText(/Incident: A gate blocked the run\./)).toBeInTheDocument();
    expect(screen.getByText(/Proof: Proof artifacts are ready\./)).toBeInTheDocument();
    expect(screen.getByText("AI compare copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain these deltas" })).toBeInTheDocument();
    expect(screen.getByText("Evidence archive")).toBeInTheDocument();
  });
});
