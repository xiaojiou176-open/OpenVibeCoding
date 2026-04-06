import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockCookies } = vi.hoisted(() => ({
  mockCookies: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  fetchDiff: vi.fn(),
  fetchEvents: vi.fn(),
  fetchOperatorCopilotBrief: vi.fn(),
  fetchReports: vi.fn(),
  fetchRun: vi.fn(),
}));

vi.mock("../components/RunDetail", () => ({
  default: ({ run }: { run: { run_id?: string } }) => <div data-testid="run-detail-stub">{run?.run_id || "-"}</div>,
}));

vi.mock("next/headers", () => ({
  cookies: mockCookies,
}));

import RunDetailPage from "../app/runs/[id]/page";
import { fetchDiff, fetchEvents, fetchReports, fetchRun } from "../lib/api";

describe("run detail page copy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCookies.mockResolvedValue({
      get: () => undefined,
      toString: () => "",
    });
    vi.mocked(fetchRun).mockResolvedValue({ run_id: "run-1", status: "RUNNING" } as never);
    vi.mocked(fetchEvents).mockResolvedValue([] as never[]);
    vi.mocked(fetchDiff).mockResolvedValue({ diff: "" } as never);
    vi.mocked(fetchReports).mockResolvedValue([] as never[]);
  });

  it("renders the English-first page title and summary copy", async () => {
    render(await RunDetailPage({ params: Promise.resolve({ id: "run-1" }) }));

    expect(screen.getByTestId("run-detail-title")).toHaveTextContent("Run detail");
    expect(screen.getByText("Follow one run across status, event evidence, and replay comparison.")).toBeInTheDocument();
    expect(screen.getByText("AI operator copilot")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate operator brief" })).toBeInTheDocument();
    expect(screen.getByTestId("run-detail-stub")).toHaveTextContent("run-1");
  });

  it("switches page-level copy with the zh-CN locale cookie", async () => {
    mockCookies.mockResolvedValueOnce({
      get: () => ({ value: "zh-CN" }),
      toString: () => "cortexpilot.ui.locale=zh-CN",
    });

    render(await RunDetailPage({ params: Promise.resolve({ id: "run-zh" }) }));

    expect(screen.getByTestId("run-detail-title")).toHaveTextContent("运行详情");
    expect(screen.getByText("沿着状态、事件证据和回放对比，完整跟踪这一条 Run。")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开对比视图" })).toHaveAttribute("href", "/runs/run-zh/compare");
  });

  it("shows English safeLoad warning copy when one data source degrades", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.mocked(fetchEvents).mockRejectedValueOnce(new Error("events backend down"));

    render(await RunDetailPage({ params: Promise.resolve({ id: "run-2" }) }));

    expect(screen.getByRole("status")).toHaveTextContent("Run events is temporarily unavailable. Try again later.");
    consoleSpy.mockRestore();
  });

  it("renders decision cards when compare, incident, and proof packs are present", async () => {
    vi.mocked(fetchReports).mockResolvedValueOnce([
      {
        name: "run_compare_report.json",
        data: {
          compare_summary: {
            mismatched_count: 1,
            missing_count: 0,
            extra_count: 0,
            failed_report_checks_count: 0,
          },
        },
      },
      {
        name: "incident_pack.json",
        data: {
          summary: "A blocking gate stopped the run.",
          next_action: "Review the gate before replaying.",
        },
      },
      {
        name: "proof_pack.json",
        data: {
          summary: "Proof artifacts are ready.",
          next_action: "Review the proof bundle before sharing.",
        },
      },
    ] as never[]);

    render(await RunDetailPage({ params: Promise.resolve({ id: "run-3" }) }));

    expect(screen.getByText("Compare decision")).toBeInTheDocument();
    expect(screen.getByText(/Compare found deltas that need operator review/i)).toBeInTheDocument();
    expect(screen.getByText("Incident action")).toBeInTheDocument();
    expect(screen.getByText("Proof action")).toBeInTheDocument();
  });

  it("prompts the operator to generate compare truth when compare summary is missing", async () => {
    vi.mocked(fetchReports).mockResolvedValueOnce([
      {
        name: "incident_pack.json",
        data: {
          summary: "A blocking gate stopped the run.",
          next_action: "Review the gate before replaying.",
        },
      },
    ] as never[]);

    render(await RunDetailPage({ params: Promise.resolve({ id: "run-4" }) }));

    expect(screen.getByText("Compare decision")).toBeInTheDocument();
    expect(screen.getByText("No structured compare report is attached yet.")).toBeInTheDocument();
    expect(screen.getByText("Next step: Generate or refresh a compare report for this run.")).toBeInTheDocument();
    expect(screen.getByText("Incident action")).toBeInTheDocument();
  });
});
