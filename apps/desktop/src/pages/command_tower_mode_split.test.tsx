import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "../components/layout/AppSidebar";
import { CommandTowerPage } from "./CommandTowerPage";
import { CTSessionDetailPage } from "./CTSessionDetailPage";

vi.mock("../lib/api", () => ({
  fetchCommandTowerOverview: vi.fn(),
  fetchCommandTowerAlerts: vi.fn(),
  fetchPmSessions: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
  postPmSessionMessage: vi.fn(),
  openEventsStream: vi.fn(() => ({ close: vi.fn() })),
}));

import {
  fetchCommandTowerAlerts,
  fetchCommandTowerOverview,
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
  fetchPmSessions,
} from "../lib/api";

describe("desktop command tower mode split", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCommandTowerOverview).mockResolvedValue({
      total_sessions: 2,
      active_sessions: 1,
      failed_sessions: 1,
      blocked_sessions: 1,
      failed_ratio: 0.5,
      generated_at: "2026-02-20T00:00:00Z",
    } as any);
    vi.mocked(fetchCommandTowerAlerts).mockResolvedValue({
      status: "degraded",
      alerts: [{ code: "A1", severity: "warning", message: "degraded" }],
    } as any);
    vi.mocked(fetchPmSessions).mockResolvedValue([
      {
        pm_session_id: "pm-1",
        status: "active",
        objective: "obj",
        run_count: 2,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 1,
        blocked_runs: 0,
      },
    ] as any);
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "run-1" },
      runs: [],
    } as any);
    vi.mocked(fetchPmSessionEvents).mockResolvedValue([] as any);
    vi.mocked(fetchPmSessionConversationGraph).mockResolvedValue({ nodes: [], edges: [] } as any);
    vi.mocked(fetchPmSessionMetrics).mockResolvedValue({
      run_count: 1,
      running_runs: 0,
      failed_runs: 0,
      blocked_runs: 0,
      failure_rate: 0,
      mttr_seconds: 0,
    } as any);
    vi.spyOn(window, "open").mockImplementation(() => null);
  });

  it("shows execution-first and web-first governance navigation grouping", () => {
    render(<AppSidebar activePage="pm" onNavigate={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Governance" })).toBeInTheDocument();
  });

  it("keeps desktop command tower execution-first and provides web deep-analysis handoff", async () => {
    const onNavigateToSession = vi.fn();
    render(<CommandTowerPage onNavigateToSession={onNavigateToSession} />);
    expect(await screen.findByRole("heading", { name: "Command Tower" })).toBeInTheDocument();
    const handoff = await screen.findByRole("button", { name: "Open web deep analysis" });
    fireEvent.click(handoff);
    expect(window.open).toHaveBeenCalledTimes(1);
    fireEvent.click(await screen.findByRole("button", { name: "Show advanced detail" }));
    const sessionRow = await screen.findByRole("button", { name: /Open session pm-1/ });
    fireEvent.keyDown(sessionRow, { key: "Enter" });
    expect(onNavigateToSession).toHaveBeenCalledWith("pm-1");
  });

  it("supports keyboard activation for session rows with Space key", async () => {
    const onNavigateToSession = vi.fn();
    render(<CommandTowerPage onNavigateToSession={onNavigateToSession} />);
    fireEvent.click(await screen.findByRole("button", { name: "Show advanced detail" }));
    const sessionRow = await screen.findByRole("button", { name: /Open session pm-1/ });
    fireEvent.keyDown(sessionRow, { key: " " });
    expect(onNavigateToSession).toHaveBeenCalledWith("pm-1");
  });

  it("supports web deep-analysis handoff from session detail page", async () => {
    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Session detail" })).toBeInTheDocument();
    });
    fireEvent.click(await screen.findByRole("button", { name: "Open web session analysis" }));
    expect(window.open).toHaveBeenCalledTimes(1);
  });

  it("keeps backoff mode when session refresh is partially failed", async () => {
    vi.mocked(fetchPmSession).mockResolvedValue({
      session: { pm_session_id: "pm-1", status: "active", latest_run_id: "" },
      runs: [],
    } as any);
    vi.mocked(fetchPmSessionEvents).mockRejectedValue(new Error("events fetch failed"));
    vi.mocked(fetchPmSessionConversationGraph).mockResolvedValue({ nodes: [], edges: [] } as any);
    vi.mocked(fetchPmSessionMetrics).mockResolvedValue({
      run_count: 1,
      running_runs: 0,
      failed_runs: 0,
      blocked_runs: 0,
      failure_rate: 0,
      mttr_seconds: 0,
    } as any);

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText("Partial refresh degraded (1/4 failed)")).toBeInTheDocument();
    });
  });

  it("sorts timeline events by latest timestamp and keeps event rows keyboard-accessible", async () => {
    vi.mocked(fetchPmSessionEvents).mockResolvedValue([
      { event: "OLDER_EVENT", ts: "2026-02-20T00:00:00Z" },
      { event: "LATEST_EVENT", ts: "2026-02-20T01:00:00Z" },
    ] as any);

    render(<CTSessionDetailPage sessionId="pm-1" onBack={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Session detail" })).toBeInTheDocument();
    });

    const eventButtons = await screen.findAllByTestId("ct-session-event-button");
    expect(eventButtons[0]).toHaveTextContent("LATEST_EVENT");
    expect(eventButtons[0]).toHaveAttribute("aria-label", "View event details LATEST_EVENT");

    fireEvent.click(eventButtons[0]);
    expect(eventButtons[0]).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/"event": "LATEST_EVENT"/)).toBeInTheDocument();
  });
});
