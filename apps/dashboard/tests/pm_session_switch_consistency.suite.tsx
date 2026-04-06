import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  answerIntake: vi.fn(),
  createIntake: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessions: vi.fn(),
  postPmSessionMessage: vi.fn(),
  runIntake: vi.fn(),
}));

import PMIntakePage from "../app/pm/page";
import { createIntake, fetchPmSession, fetchPmSessionEvents, fetchPmSessions } from "../lib/api";

describe("pm session switch consistency", () => {
  const mockFetchPmSessions = vi.mocked(fetchPmSessions);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockCreateIntake = vi.mocked(createIntake);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPmSessions.mockResolvedValue([
      {
        pm_session_id: "pm-a",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-a",
      },
      {
        pm_session_id: "pm-b",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
        latest_run_id: "run-b",
      },
    ] as never[]);

    mockFetchPmSession.mockImplementation(async (sessionId: string) => ({
      session: {
        pm_session_id: sessionId,
        status: "active",
        latest_run_id: sessionId === "pm-a" ? "run-a" : "run-b",
        run_count: 1,
      },
      runs: [],
      run_ids: [sessionId === "pm-a" ? "run-a" : "run-b"],
    } as any));
    mockFetchPmSessionEvents.mockImplementation(async (sessionId: string) => [
      {
        event: "CHAIN_HANDOFF",
        ts: "2026-02-20T00:00:00Z",
        context: { message: `session=${sessionId}`, role: "PM", from_role: "PM" },
      },
    ] as any);
  });

  it("keeps right context bound to latest selected session", async () => {
    render(<PMIntakePage />);

    const sessionA = await screen.findByTestId("pm-session-item-pm-a");
    const sessionB = await screen.findByTestId("pm-session-item-pm-b");

    await act(async () => {
      fireEvent.click(sessionA);
      fireEvent.click(sessionB);
    });

    await waitFor(() => {
      expect(mockFetchPmSession).toHaveBeenLastCalledWith("pm-b");
      expect(screen.getAllByText(/^run-b$/).length).toBeGreaterThan(0);
    });

    expect(screen.queryByText(/^run-a$/)).toBeNull();
  });

  it("reproduces stale plan/taskChain after switching to another session", async () => {
    mockCreateIntake.mockResolvedValueOnce({
      intake_id: "pm-a",
      questions: [],
      plan: { plan_marker: "plan-a" },
      task_chain: { chain_marker: "chain-a" },
    } as never);

    render(<PMIntakePage />);

    await act(async () => {
      fireEvent.click(screen.getByText("Advanced parameters"));
      fireEvent.click(screen.getByRole("button", { name: "Generate questions" }));
    });

    expect(await screen.findByText(/"plan_marker": "plan-a"/)).toBeInTheDocument();
    expect(screen.getByText(/"chain_marker": "chain-a"/)).toBeInTheDocument();

    const sessionB = await screen.findByTestId("pm-session-item-pm-b");
    await act(async () => {
      fireEvent.click(sessionB);
    });

    await waitFor(() => {
      expect(mockFetchPmSession).toHaveBeenLastCalledWith("pm-b");
    });

    expect(screen.queryByText(/"plan_marker": "plan-a"/)).toBeNull();
    expect(screen.queryByText(/"chain_marker": "chain-a"/)).toBeNull();
  });
});
