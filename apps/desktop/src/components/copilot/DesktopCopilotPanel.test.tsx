import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DesktopCopilotPanel } from "./DesktopCopilotPanel";

describe("DesktopCopilotPanel", () => {
  it("renders operator-brief truth surfaces and grounded takeaways after generation", async () => {
    const loadBrief = vi.fn().mockResolvedValue({
      report_type: "operator_copilot_brief",
      status: "AVAILABLE",
      scope: "run_detail",
      subject_id: "run-123",
      summary: "The operator should compare the staged diff before accepting the run.",
      likely_cause: "The last proof pack is stale.",
      compare_takeaway: "Compare the staged diff against the last approved run.",
      proof_takeaway: "Refresh the proof pack before asking for review.",
      incident_takeaway: "Treat stale proof as an incident until it is re-generated.",
      queue_takeaway: "Keep the queue paused until proof is current.",
      approval_takeaway: "Approval should wait for a fresh proof receipt.",
      used_truth_surfaces: ["run_detail", "", "proof_pack"],
      limitations: ["review not started", "   "],
      recommended_actions: ["Refresh proof", "Request review", "   "],
      top_risks: ["stale-proof", "", "queue drift"],
    });

    render(
      <DesktopCopilotPanel
        intro="Only grounded control-plane truth belongs here."
        questionSet={["What is blocked?", "What should the operator do next?"]}
        loadBrief={loadBrief}
      />,
    );

    expect(screen.getByText("Only grounded control-plane truth belongs here.")).toBeInTheDocument();
    expect(screen.getByText("What is blocked?")).toBeInTheDocument();
    expect(screen.getByText("What should the operator do next?")).toBeInTheDocument();
    expect(screen.getByText("On demand")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Generate operator brief" }));

    expect(await screen.findByText("Grounded brief")).toBeInTheDocument();
    expect(await screen.findByText("The operator should compare the staged diff before accepting the run.")).toBeInTheDocument();
    expect(screen.getByText("The last proof pack is stale.")).toBeInTheDocument();
    expect(screen.getByText("Scope: run_detail")).toBeInTheDocument();
    expect(screen.getByText("Subject: run-123")).toBeInTheDocument();
    expect(screen.getByText("Truth surfaces: run_detail | proof_pack")).toBeInTheDocument();
    expect(screen.getByText("Limitations: review not started")).toBeInTheDocument();
    expect(screen.getByText("Compare the staged diff against the last approved run.")).toBeInTheDocument();
    expect(screen.getByText("Keep the queue paused until proof is current.")).toBeInTheDocument();
    expect(screen.getByText("Refresh proof")).toBeInTheDocument();
    expect(screen.getByText("queue drift")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate brief" })).toBeInTheDocument();

    expect(loadBrief).toHaveBeenCalledTimes(1);
  });

  it("covers flight-plan fallback labels and empty action/risk lists", async () => {
    const loadBrief = vi.fn().mockResolvedValue({
      report_type: "flight_plan_copilot_brief",
      status: "UNAVAILABLE",
      summary: "The plan is still advisory because execution has not started yet.",
      risk_takeaway: "Approval is still blocked on a missing operator confirmation.",
      capability_takeaway: "Runtime capability is unresolved until the runner binds.",
      approval_takeaway: "An operator must confirm the start gate before execution.",
      used_truth_surfaces: ["execution_plan_preview"],
      recommended_actions: ["", "   "],
      top_risks: [],
      limitations: undefined,
    });

    render(<DesktopCopilotPanel title="Flight plan panel" intro={undefined} questionSet={["Why this plan?"]} loadBrief={loadBrief} />);

    fireEvent.click(screen.getByRole("button", { name: "Generate operator brief" }));

    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Scope: flight_plan")).toBeInTheDocument();
    expect(screen.getByText("Subject: execution_plan_report")).toBeInTheDocument();
    expect(screen.getByText("Truth surfaces: execution_plan_preview")).toBeInTheDocument();
    expect(screen.getByText("Limitations: -")).toBeInTheDocument();
    expect(screen.getAllByText("Approval is still blocked on a missing operator confirmation.").length).toBeGreaterThan(0);
    expect(screen.getByText("This brief stays advisory until a run actually starts.")).toBeInTheDocument();
    expect(screen.getByText("No recommended actions were returned.")).toBeInTheDocument();
    expect(screen.getByText("No explicit risks were returned.")).toBeInTheDocument();
  });

  it("surfaces load failures without leaving the panel in generating state", async () => {
    const loadBrief = vi.fn().mockRejectedValue("brief backend unavailable");

    render(<DesktopCopilotPanel questionSet={["Why did this fail?"]} loadBrief={loadBrief} />);

    fireEvent.click(screen.getByRole("button", { name: "Generate operator brief" }));

    expect(await screen.findByText("brief backend unavailable")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Generate operator brief" })).toBeEnabled();
    });
  });
});
