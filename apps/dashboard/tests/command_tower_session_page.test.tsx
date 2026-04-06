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

vi.mock("../components/command-tower/CommandTowerSessionLive", () => ({
  default: vi.fn(() => <div data-testid="command-tower-session-live" />),
}));

vi.mock("../lib/api", () => ({
  fetchPmSession: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
}));

vi.mock("../lib/serverPageData", () => ({
  safeLoad: vi.fn(),
}));

import CommandTowerSessionLive from "../components/command-tower/CommandTowerSessionLive";
import CommandTowerSessionPage from "../app/command-tower/sessions/[id]/page";
import {
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
} from "../lib/api";
import { safeLoad } from "../lib/serverPageData";

describe("command tower session page state handling", () => {
  const mockSessionLive = vi.mocked(CommandTowerSessionLive);
  const mockFetchPmSession = vi.mocked(fetchPmSession);
  const mockFetchPmSessionEvents = vi.mocked(fetchPmSessionEvents);
  const mockFetchPmSessionConversationGraph = vi.mocked(fetchPmSessionConversationGraph);
  const mockFetchPmSessionMetrics = vi.mocked(fetchPmSessionMetrics);
  const mockSafeLoad = vi.mocked(safeLoad);

  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchPmSession.mockResolvedValue({
      session: {
        pm_session_id: "session-1",
        status: "active",
        run_count: 1,
      },
      run_ids: [],
      runs: [],
      blockers: [],
    } as never);
    mockFetchPmSessionEvents.mockResolvedValue([
      { event: "invalid-ts", ts: "not-a-time" },
      { event: "numeric-ts", ts: 200 },
      { event: "date-ts", ts: "2026-03-01T00:00:00Z" },
    ] as never[]);
    mockFetchPmSessionConversationGraph.mockResolvedValue({
      pm_session_id: "session-1",
      window: "24h",
      nodes: [],
      edges: [],
      stats: { node_count: 0, edge_count: 0 },
    } as never);
    mockFetchPmSessionMetrics.mockResolvedValue({
      pm_session_id: "session-1",
      run_count: 1,
      running_runs: 1,
      failed_runs: 0,
      success_runs: 0,
      blocked_runs: 0,
      failure_rate: 0,
      blocked_ratio: 0,
      avg_duration_seconds: 0,
      avg_recovery_seconds: 0,
      cycle_time_seconds: 0,
      mttr_seconds: 0,
    } as never);
    mockSafeLoad.mockImplementation(async (loader: () => Promise<unknown>) => ({
      data: await loader(),
      warning: null,
    }));
  });

  it("aggregates warnings and sorts initial events by parsed timestamp", async () => {
    mockSafeLoad
      .mockResolvedValueOnce({
        data: {
          session: { pm_session_id: "session-1", status: "active" },
          run_ids: [],
          runs: [],
          blockers: [],
        },
        warning: "详情告警",
      })
      .mockResolvedValueOnce({
        data: [
          { event: "invalid-ts", ts: "not-a-time" },
          { event: "numeric-string-ts", ts: "300" },
          { event: "numeric-ts", ts: 200 },
          { event: "missing-ts", ts: null },
          { event: "date-ts", ts: "2026-03-01T00:00:00Z" },
        ],
        warning: "事件告警",
      })
      .mockResolvedValueOnce({
        data: {
          pm_session_id: "session-1",
          window: "24h",
          nodes: [],
          edges: [],
          stats: { node_count: 0, edge_count: 0 },
        },
        warning: null,
      })
      .mockResolvedValueOnce({
        data: {
          pm_session_id: "session-1",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 0,
          blocked_runs: 0,
          failure_rate: 0,
          blocked_ratio: 0,
          avg_duration_seconds: 0,
          avg_recovery_seconds: 0,
          cycle_time_seconds: 0,
          mttr_seconds: 0,
        },
        warning: null,
      });

    render(
      await CommandTowerSessionPage({
        params: Promise.resolve({ id: "session-1" }),
      }),
    );

    expect(screen.getByRole("status")).toHaveTextContent("详情告警 事件告警");
    const props = mockSessionLive.mock.calls[0]?.[0] as {
      pmSessionId: string;
      initialEvents: Array<{ event: string }>;
    };
    expect(props.pmSessionId).toBe("session-1");
    expect(props.initialEvents.map((event) => event.event)).toEqual([
      "date-ts",
      "numeric-string-ts",
      "numeric-ts",
      "invalid-ts",
      "missing-ts",
    ]);
  });

  it("falls back to built-in warning and empty events when safeLoad call rejects", async () => {
    mockSafeLoad
      .mockResolvedValueOnce({
        data: {
          session: { pm_session_id: "session-1", status: "active" },
          run_ids: [],
          runs: [],
          blockers: [],
        },
        warning: null,
      })
      .mockRejectedValueOnce(new Error("events load crashed"))
      .mockResolvedValueOnce({
        data: {
          pm_session_id: "session-1",
          window: "24h",
          nodes: [],
          edges: [],
          stats: { node_count: 0, edge_count: 0 },
        },
        warning: null,
      })
      .mockResolvedValueOnce({
        data: {
          pm_session_id: "session-1",
          run_count: 1,
          running_runs: 1,
          failed_runs: 0,
          success_runs: 0,
          blocked_runs: 0,
          failure_rate: 0,
          blocked_ratio: 0,
          avg_duration_seconds: 0,
          avg_recovery_seconds: 0,
          cycle_time_seconds: 0,
          mttr_seconds: 0,
        },
        warning: null,
      });

    render(
      await CommandTowerSessionPage({
        params: Promise.resolve({ id: "session-1" }),
      }),
    );

    expect(screen.getByRole("status")).toHaveTextContent("Session event stream is unavailable right now. Please try again later.");
    const props = mockSessionLive.mock.calls[0]?.[0] as { initialEvents: unknown[] };
    expect(props.initialEvents).toEqual([]);
  });
});
