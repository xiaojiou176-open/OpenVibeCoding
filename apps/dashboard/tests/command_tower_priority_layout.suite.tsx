import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchCommandTowerAlerts: vi.fn(),
}));

import CommandTowerHomeLive from "../components/command-tower/CommandTowerHomeLive";
import {
  fetchCommandTowerAlerts,
  fetchCommandTowerOverview,
  fetchPmSessions,
} from "../lib/api";
import type { PmSessionSummary } from "../lib/types";

describe("command tower priority layout", () => {
  const mockOverview = vi.mocked(fetchCommandTowerOverview);
  const mockSessions = vi.mocked(fetchPmSessions);
  const mockAlerts = vi.mocked(fetchCommandTowerAlerts);
  const seededSessions: PmSessionSummary[] = [
    {
      pm_session_id: "pm-1",
      status: "active",
      run_count: 2,
      running_runs: 1,
      failed_runs: 0,
      success_runs: 1,
      blocked_runs: 0,
      objective: "session one",
    },
    {
      pm_session_id: "pm-2",
      status: "failed",
      run_count: 1,
      running_runs: 0,
      failed_runs: 1,
      success_runs: 0,
      blocked_runs: 1,
      objective: "session two",
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    mockOverview.mockResolvedValue({
      generated_at: "2026-02-20T00:00:00Z",
      total_sessions: 2,
      active_sessions: 1,
      failed_sessions: 1,
      blocked_sessions: 1,
      failed_ratio: 0.5,
      blocked_ratio: 0.5,
      failure_trend_30m: 1,
      top_blockers: [],
    });
    mockSessions.mockResolvedValue(seededSessions);
    mockAlerts.mockResolvedValue({
      generated_at: "2026-02-20T00:00:00Z",
      status: "degraded",
      alerts: [{ code: "A1", severity: "warning", message: "degraded" }],
    });
  });

  it("renders live/risk/action lanes and details zone label", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={{
          generated_at: "2026-02-20T00:00:00Z",
          total_sessions: 1,
          active_sessions: 1,
          failed_sessions: 0,
          blocked_sessions: 0,
          failed_ratio: 0,
          blocked_ratio: 0,
          failure_trend_30m: 0,
          top_blockers: [],
        }}
        initialSessions={[]}
      />,
    );

    expect(await screen.findByRole("heading", { name: "Live Lane" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Risk Lane" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Action Lane" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Focus high-risk sessions" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Each lane card exposes quick actions so you can jump straight into live control, risk focus, or the next operator step.",
      ),
    ).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Reload" })).toHaveAttribute("href", "/command-tower");
    expect(screen.getAllByText(/cached snapshot/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Expand|Collapse/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch to paused analysis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Switch to high-risk view" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open first risk session" })).toHaveAttribute("href", "/command-tower/sessions/pm-2");
    expect(screen.queryByRole("button", { name: /Retry|Retrying/i })).not.toBeInTheDocument();
  });

  it("keeps session details collapsed until expanded", async () => {
    render(
      <CommandTowerHomeLive
        initialOverview={{
          generated_at: "2026-02-20T00:00:00Z",
          total_sessions: 2,
          active_sessions: 1,
          failed_sessions: 1,
          blocked_sessions: 1,
          failed_ratio: 0.5,
          blocked_ratio: 0.5,
          failure_trend_30m: 1,
          top_blockers: [],
        }}
        initialSessions={seededSessions}
      />,
    );

    const failedRow = screen.getByRole("row", { name: /session two/i });
    expect(await screen.findByText(/Risk sample:\s*2 sessions/i)).toBeInTheDocument();
    expect(within(failedRow).getAllByText("Failure path 1").length).toBeGreaterThan(0);
    expect(within(failedRow).getAllByText("Blocked 1").length).toBeGreaterThan(0);
  });
});
