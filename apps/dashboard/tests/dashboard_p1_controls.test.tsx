import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...props }: { href: string; children: React.ReactNode; prefetch?: boolean }) => (
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
import DashboardError from "../app/error";
import CommandTowerError from "../app/command-tower/error";
import PmPageError from "../app/pm/error";
import { fetchPmSession, fetchPmSessionEvents, fetchPmSessions } from "../lib/api";
import type { EventRecord, PmSessionDetailPayload, PmSessionSummary } from "../lib/types";

describe("dashboard p1 controls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const pmSessions: PmSessionSummary[] = [
      {
        pm_session_id: "pm-history-1",
        status: "active",
        current_step: "pm",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
      {
        pm_session_id: "pm-history-2",
        status: "failed",
        current_step: "reviewer",
        run_count: 1,
        running_runs: 0,
        failed_runs: 1,
        success_runs: 0,
        blocked_runs: 1,
      },
    ];
    const pmSessionDetail: PmSessionDetailPayload = {
      session: {
        pm_session_id: "pm-history-1",
        status: "active",
        run_count: 1,
        running_runs: 1,
        failed_runs: 0,
        success_runs: 0,
        blocked_runs: 0,
      },
      run_ids: [],
      runs: [],
    };
    const pmSessionEvents: EventRecord[] = [
      { ts: "2026-02-19T00:00:00Z", context: { from_role: "PM", message: "会话一消息" } },
    ];
    vi.mocked(fetchPmSessions).mockResolvedValue(pmSessions);
    vi.mocked(fetchPmSession).mockResolvedValue(pmSessionDetail);
    vi.mocked(fetchPmSessionEvents).mockResolvedValue(pmSessionEvents);
  });

  it("covers PM page new conversation, session switch and split expand", async () => {
    render(<PMIntakePage />);
    expect(await screen.findByText(/ID pm-history-1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /\+ New chat/ }));
    const chatLog = screen.getByRole("log");
    const emptyState = chatLog.querySelector(".pm-empty-state");
    expect(chatLog).toHaveAttribute("aria-busy", "false");
    expect(emptyState).not.toBeNull();
    expect(emptyState).toHaveTextContent(/No session yet\. Send the first request/);
    expect(emptyState).toHaveTextContent(/Send the first request and I will create the session automatically\./);
    expect(screen.getByText(/Send the first real task into the system/)).toBeInTheDocument();

    const sessionEntry = screen.getByText(/ID pm-history-1/).closest("button");
    expect(sessionEntry).not.toBeNull();
    fireEvent.click(sessionEntry as HTMLButtonElement);
    await waitFor(() => expect(fetchPmSession).toHaveBeenCalled());

    const layoutModeGroup = screen.getByRole("tablist", { name: "Layout mode" });
    const splitButton = within(layoutModeGroup).getByRole("tab", { name: "Split" });
    fireEvent.click(splitButton);
    expect(splitButton).toHaveAttribute("aria-selected", "true");
    const page = document.querySelector("main.pm-claude-page");
    expect(page).toHaveClass("pm-layout-split");
  }, 45_000);

  it("covers error boundary retry buttons", async () => {
    const resetRoot = vi.fn();
    const resetCt = vi.fn();
    const resetPm = vi.fn();

    const rootView = render(<DashboardError error={new Error("root")} reset={resetRoot} />);
    fireEvent.click(rootView.getByRole("button"));
    expect(resetRoot).toHaveBeenCalled();
    rootView.unmount();

    const ctView = render(<CommandTowerError error={new Error("ct")} reset={resetCt} />);
    fireEvent.click(ctView.getByRole("button"));
    expect(resetCt).toHaveBeenCalled();
    ctView.unmount();

    const pmView = render(<PmPageError error={new Error("pm")} reset={resetPm} />);
    fireEvent.click(pmView.getByRole("button"));
    expect(resetPm).toHaveBeenCalled();
  });
});
