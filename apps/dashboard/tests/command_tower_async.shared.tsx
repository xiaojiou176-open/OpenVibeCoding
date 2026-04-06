import type { ReactNode } from "react";
import { vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("../lib/api", () => ({
  fetchCommandTowerAlerts: vi.fn(),
  fetchCommandTowerOverview: vi.fn(),
  fetchPmSession: vi.fn(),
  fetchPmSessionConversationGraph: vi.fn(),
  fetchPmSessionEvents: vi.fn(),
  fetchPmSessionMetrics: vi.fn(),
  fetchPmSessions: vi.fn(),
  openEventsStream: vi.fn(),
  postPmSessionMessage: vi.fn(),
}));

import {
  fetchCommandTowerAlerts,
  fetchCommandTowerOverview,
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
  fetchPmSessions,
  openEventsStream,
  postPmSessionMessage,
} from "../lib/api";
import type {
  CommandTowerAlertsPayload,
  CommandTowerOverviewPayload,
  EventRecord,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
  PmSessionSummary,
} from "../lib/types";

export class MockEventSource {
  onopen: (() => void) | null = null;

  onmessage: ((event: MessageEvent) => void) | null = null;

  onerror: (() => void) | null = null;

  close = vi.fn();
}

export function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export function baseOverview(): CommandTowerOverviewPayload {
  return {
    generated_at: "2026-02-09T10:00:00Z",
    total_sessions: 1,
    active_sessions: 1,
    failed_sessions: 0,
    blocked_sessions: 0,
    failed_ratio: 0,
    blocked_ratio: 0,
    failure_trend_30m: 0,
    top_blockers: [],
  };
}

export function baseSessionSummary(status: PmSessionSummary["status"] = "active"): PmSessionSummary {
  return {
    pm_session_id: "pm-1",
    status,
    run_count: 1,
    running_runs: status === "active" ? 1 : 0,
    failed_runs: status === "failed" ? 1 : 0,
    success_runs: status === "done" ? 1 : 0,
    blocked_runs: 0,
    latest_run_id: "run-1",
    current_role: "PM",
    current_step: "plan",
    updated_at: "2026-02-09T10:00:00Z",
  };
}

export function baseAlerts(): CommandTowerAlertsPayload {
  return {
    generated_at: "2026-02-09T10:00:00Z",
    status: "healthy",
    alerts: [],
  };
}

export function baseSessionDetail(
  status: PmSessionSummary["status"] = "active",
  latestRunId = "run-1",
): PmSessionDetailPayload {
  const session = baseSessionSummary(status);
  session.latest_run_id = latestRunId;

  return {
    session,
    run_ids: latestRunId ? [latestRunId] : [],
    runs: latestRunId
      ? [
          {
            run_id: latestRunId,
            status: status === "active" ? "RUNNING" : String(status).toUpperCase(),
            current_role: "PM",
            current_step: "plan",
            blocked: false,
            last_event_ts: "2026-02-09T10:00:00Z",
          },
        ]
      : [],
    blockers: [],
  };
}

export function baseGraph(window: "30m" | "2h" | "24h" = "24h"): PmSessionConversationGraphPayload {
  return {
    pm_session_id: "pm-1",
    window,
    nodes: ["PM", "TL"],
    edges: [
      {
        from_role: "PM",
        to_role: "TL",
        run_id: "run-1",
        ts: "2026-02-09T09:59:59Z",
        event_ref: "evt-1",
      },
    ],
    stats: {
      node_count: 2,
      edge_count: 1,
    },
  };
}

export function baseMetrics(): PmSessionMetricsPayload {
  return {
    pm_session_id: "pm-1",
    run_count: 1,
    running_runs: 1,
    failed_runs: 0,
    success_runs: 0,
    blocked_runs: 0,
    failure_rate: 0,
    blocked_ratio: 0,
    avg_duration_seconds: 2,
    avg_recovery_seconds: 0,
    cycle_time_seconds: 4,
    mttr_seconds: 0,
  };
}

export function baseEvents(): EventRecord[] {
  return [
    {
      ts: "2026-02-09T09:59:55Z",
      event: "CHAIN_STEP_STARTED",
      run_id: "run-1",
      context: { step: "plan" },
    },
  ];
}

export function getCommandTowerAsyncMocks() {
  return {
    mockFetchCommandTowerOverview: vi.mocked(fetchCommandTowerOverview),
    mockFetchPmSessions: vi.mocked(fetchPmSessions),
    mockFetchCommandTowerAlerts: vi.mocked(fetchCommandTowerAlerts),
    mockFetchPmSession: vi.mocked(fetchPmSession),
    mockFetchPmSessionEvents: vi.mocked(fetchPmSessionEvents),
    mockFetchPmSessionConversationGraph: vi.mocked(fetchPmSessionConversationGraph),
    mockFetchPmSessionMetrics: vi.mocked(fetchPmSessionMetrics),
    mockOpenEventsStream: vi.mocked(openEventsStream),
    mockPostPmSessionMessage: vi.mocked(postPmSessionMessage),
  };
}

export function setupCommandTowerAsyncDefaultMocks(mocks: ReturnType<typeof getCommandTowerAsyncMocks>) {
  mocks.mockFetchCommandTowerOverview.mockResolvedValue(baseOverview());
  mocks.mockFetchPmSessions.mockResolvedValue([baseSessionSummary()]);
  mocks.mockFetchCommandTowerAlerts.mockResolvedValue(baseAlerts());

  mocks.mockFetchPmSession.mockResolvedValue(baseSessionDetail());
  mocks.mockFetchPmSessionEvents.mockResolvedValue(baseEvents());
  mocks.mockFetchPmSessionConversationGraph.mockResolvedValue(baseGraph());
  mocks.mockFetchPmSessionMetrics.mockResolvedValue(baseMetrics());

  mocks.mockOpenEventsStream.mockImplementation(() => new MockEventSource() as unknown as EventSource);
  mocks.mockPostPmSessionMessage.mockResolvedValue({ ok: true });
}

export function teardownCommandTowerAsyncMocks() {
  vi.useRealTimers();
  vi.clearAllMocks();
}
