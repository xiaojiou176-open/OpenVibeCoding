import { useEffect, useRef, useState } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  LIVE_SSE_FAILURE_LIMIT,
  LIVE_REPORT_REFRESH_CYCLE,
  type LiveMode,
  type LiveTransport,
  badgeVariantForStage,
  deriveTerminalStatus,
  eventIdentity,
  eventTimestamp,
  isTerminalStatus,
  latestEventTimestamp,
  lifecycleBadges,
  liveBadgeVariant,
  liveLabel,
  mergeEvents,
  normalizedStatus,
  sortEvents,
  toArray,
  toDisplayText,
  toObject,
  toStringOr,
} from "../components/run-detail/runDetailHelpers";
import { useRunDetailLive } from "../components/run-detail/useRunDetailLive";
import type { EventRecord, ReportRecord } from "../lib/types";
import * as api from "../lib/api";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

type LiveHookHarnessArgs = {
  runId?: string;
  runStatus?: unknown;
  liveEnabled?: boolean;
  initialReports?: ReportRecord[];
};

function useRunDetailLiveHarness(args: LiveHookHarnessArgs = {}) {
  const {
    runId = "run-live",
    runStatus = "RUNNING",
    liveEnabled = true,
    initialReports = [],
  } = args;
  const eventsRef = useRef<EventRecord[]>([]);
  const reportsRef = useRef<ReportRecord[]>(initialReports);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [reports, setReports] = useState<ReportRecord[]>(initialReports);
  const [liveMode, setLiveMode] = useState<LiveMode>("paused");
  const [liveTransport, setLiveTransport] = useState<LiveTransport>("polling");
  const [liveError, setLiveError] = useState("");
  const [liveIntervalMs, setLiveIntervalMs] = useState(0);
  const [liveLagMs, setLiveLagMs] = useState(0);
  const [lastRefreshAt, setLastRefreshAt] = useState("");

  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  useEffect(() => {
    reportsRef.current = reports;
  }, [reports]);

  useRunDetailLive({
    runId,
    runStatus,
    liveEnabled,
    eventsRef,
    reportsRef,
    setEventsState: setEvents,
    setReportsState: setReports,
    setLiveMode,
    setLiveTransport,
    setLiveError,
    setLiveIntervalMs,
    setLiveLagMs,
    setLastRefreshAt,
  });

  return {
    eventsRef,
    reportsRef,
    events,
    reports,
    liveMode,
    liveTransport,
    liveError,
    liveIntervalMs,
    liveLagMs,
    lastRefreshAt,
  };
}

class HookEventSource {
  onopen: ((event: Event) => void) | null = null;

  onmessage: ((event: MessageEvent<string>) => void) | null = null;

  onerror: ((event: Event) => void) | null = null;

  close = vi.fn();
}

describe("RunDetail helper functions", () => {
  it("covers lifecycle badge decision matrix", () => {
    expect(lifecycleBadges(null)).toEqual([]);
    const minimal = lifecycleBadges({
      observed_path: undefined,
      workers: {},
      reviewers: {},
      tests: {},
      return_to_pm: {},
    });
    expect(minimal.find((item) => item.key === "pm-start")?.status).toBe("running");

    const running = lifecycleBadges({
      observed_path: ["PM", "TECH_LEAD", "WORKER"],
      workers: { ok: false, observed: 1, required: 2 },
      reviewers: { ok: false, pass: 0, quorum: 2 },
      tests: { ok: false, pass: 0 },
      return_to_pm: { ok: false },
    });

    expect(running.find((item) => item.key === "pm-start")?.status).toBe("ok");
    expect(running.find((item) => item.key === "tl-plan")?.status).toBe("ok");
    expect(running.find((item) => item.key === "workers")?.status).toBe("running");
    expect(running.find((item) => item.key === "reviewers")?.status).toBe("failed");
    expect(running.find((item) => item.key === "testing")?.status).toBe("failed");
    expect(running.find((item) => item.key === "tl-signoff")?.status).toBe("running");
    expect(running.find((item) => item.key === "pm-final")?.status).toBe("failed");

    const ok = lifecycleBadges({
      observed_path: ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "TECH_LEAD", "PM"],
      workers: { ok: true, observed: 2, required: 2 },
      reviewers: { ok: true, pass: 2, quorum: 2 },
      tests: { ok: true, pass: 1 },
      return_to_pm: { ok: true },
    });

    expect(ok.every((item) => item.status === "ok")).toBe(true);
  });

  it("covers badge/status helpers", () => {
    expect(badgeVariantForStage("ok")).toBe("success");
    expect(badgeVariantForStage("failed")).toBe("failed");
    expect(badgeVariantForStage("running")).toBe("running");

    expect(normalizedStatus(" success ")).toBe("SUCCESS");
    expect(normalizedStatus(42)).toBe("");

    expect(isTerminalStatus("SUCCESS")).toBe(true);
    expect(isTerminalStatus("running")).toBe(false);

    expect(liveBadgeVariant("stopped")).toBe("success");
    expect(liveBadgeVariant("backoff")).toBe("failed");
    expect(liveBadgeVariant("running")).toBe("running");

    expect(liveLabel("paused")).toBe("Paused");
    expect(liveLabel("backoff")).toBe("Retry backoff");
    expect(liveLabel("stopped")).toBe("Terminal snapshot");
    expect(liveLabel("running")).toBe("Live refresh active");

    expect(toStringOr("x", "fallback")).toBe("x");
    expect(toStringOr(undefined, "fallback")).toBe("fallback");
    expect(toStringOr(10, "fallback")).toBe("10");

    expect(toDisplayText("abc")).toBe("abc");
    expect(toDisplayText(0)).toBe("0");
    expect(toDisplayText("")).toBe("-");
    expect(toDisplayText(undefined)).toBe("-");

    expect(toArray([1, 2])).toEqual([1, 2]);
    expect(toArray(undefined)).toEqual([]);

    expect(toObject({ a: 1 })).toEqual({ a: 1 });
    expect(toObject(undefined)).toEqual({});
    expect(toObject([1, 2])).toEqual({});
  });

  it("covers event timestamp/sort/merge helpers", () => {
    const e1: EventRecord = { ts: "2026-01-01T00:00:00Z", event: "A", context: { x: 1 } };
    const e2: EventRecord = { _ts: "2026-01-01T00:00:01Z", event: "B", context: { y: 2 } };
    const e3: EventRecord = { event: "C", context: { z: 3 } };

    expect(eventTimestamp(e1)).toBe("2026-01-01T00:00:00Z");
    expect(eventTimestamp(e2)).toBe("2026-01-01T00:00:01Z");
    expect(eventTimestamp(e3)).toBe("");

    expect(eventIdentity(e1)).toContain("A");

    const sameTsA: EventRecord = { ts: "2026-01-01T00:00:02Z", event: "Z" };
    const sameTsB: EventRecord = { ts: "2026-01-01T00:00:02Z", event: "Y" };
    const sorted = sortEvents([sameTsA, e1, sameTsB]);
    expect(sorted[0]?.event).toBe("A");
    expect(["Y", "Z"]).toContain(String(sorted[1]?.event));
    expect(["Y", "Z"]).toContain(String(sorted[2]?.event));

    const deduped = mergeEvents([e1], [e1, e2]);
    expect(deduped.length).toBe(2);

    const bigList: EventRecord[] = Array.from({ length: 810 }, (_, index) => ({
      ts: `2026-01-01T00:00:${String(index).padStart(2, "0")}Z`,
      event: `E${index}`,
    }));
    const trimmed = mergeEvents([], bigList);
    expect(trimmed.length).toBe(800);

    expect(latestEventTimestamp([])).toBe("");
    expect(latestEventTimestamp([e1, e2])).toBe("2026-01-01T00:00:01Z");
  });

  it("covers terminal status derivation precedence", () => {
    const reports1: ReportRecord[] = [
      { name: "chain_report.json", data: { status: "failed" } },
      { name: "task_result.json", data: { status: "success" } },
    ];
    expect(deriveTerminalStatus("running", reports1)).toBe("FAILED");

    const reports2: ReportRecord[] = [{ name: "task_result.json", data: { status: "success" } }];
    expect(deriveTerminalStatus("running", reports2)).toBe("SUCCESS");

    const reports3: ReportRecord[] = [];
    expect(deriveTerminalStatus(" done ", reports3)).toBe("DONE");
  });

  it("falls back to polling transport when EventSource is unavailable", async () => {
    const originalEventSource = globalThis.EventSource;
    globalThis.EventSource = undefined;

    const fetchEventsSpy = vi.spyOn(api, "fetchEvents").mockResolvedValue([]);
    vi.spyOn(api, "fetchReports").mockResolvedValue([]);
    vi.spyOn(api, "openEventsStream");

    try {
      const { result, unmount } = renderHook(() => useRunDetailLiveHarness());
      await waitFor(() => {
        expect(result.current.liveTransport).toBe("polling");
        expect(result.current.liveMode).toBe("running");
      });
      unmount();
      expect(fetchEventsSpy).not.toHaveBeenCalled();
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });

  it("pauses live updates when run id is missing", async () => {
    const openEventsStreamSpy = vi.spyOn(api, "openEventsStream");
    const fetchEventsSpy = vi.spyOn(api, "fetchEvents");

    const { result, unmount } = renderHook(() => useRunDetailLiveHarness({ runId: "" }));
    await waitFor(() => {
      expect(result.current.liveMode).toBe("paused");
    });
    expect(openEventsStreamSpy).not.toHaveBeenCalled();
    expect(fetchEventsSpy).not.toHaveBeenCalled();
    unmount();
  });

  it("enters backoff when live report refresh fails on SSE message bursts", async () => {
    const originalEventSource = globalThis.EventSource;
    // @ts-expect-error test-only override
    globalThis.EventSource = class {};

    const stream = new HookEventSource();
    vi.spyOn(api, "openEventsStream").mockReturnValue(stream as unknown as EventSource);
    vi.spyOn(api, "fetchReports").mockRejectedValue(new Error("report refresh failed"));
    vi.spyOn(api, "fetchEvents").mockResolvedValue([]);

    try {
      const { result, unmount } = renderHook(() => useRunDetailLiveHarness());
      await waitFor(() => {
        expect(result.current.liveTransport).toBe("sse");
      });

      act(() => {
        stream.onopen?.(new Event("open"));
      });

      for (let index = 0; index < LIVE_REPORT_REFRESH_CYCLE; index += 1) {
        act(() => {
          stream.onmessage?.({
            data: JSON.stringify({
              ts: `2026-03-08T14:00:0${index}.000Z`,
              event: "CHAIN_STEP_STARTED",
            }),
          } as MessageEvent<string>);
        });
      }

      await waitFor(() => {
        expect(result.current.liveMode).toBe("backoff");
        expect(result.current.liveError).toBe("Live report refresh failed");
      });
      unmount();
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });

  it("closes SSE stream and stops live mode when reports become terminal", async () => {
    const originalEventSource = globalThis.EventSource;
    // @ts-expect-error test-only override
    globalThis.EventSource = class {};

    const stream = new HookEventSource();
    vi.spyOn(api, "openEventsStream").mockReturnValue(stream as unknown as EventSource);
    vi.spyOn(api, "fetchReports").mockResolvedValue([]);
    vi.spyOn(api, "fetchEvents").mockResolvedValue([]);

    try {
      const { result, unmount } = renderHook(() => useRunDetailLiveHarness());
      await waitFor(() => {
        expect(result.current.liveTransport).toBe("sse");
      });

      act(() => {
        result.current.reportsRef.current = [
          {
            name: "task_result.json",
            data: { status: "success" },
          },
        ] as ReportRecord[];
      });

      act(() => {
        stream.onmessage?.({
          data: JSON.stringify({
            ts: "2026-03-08T14:05:00.000Z",
            event: "CHAIN_STEP_RESULT",
          }),
        } as MessageEvent<string>);
      });

      await waitFor(() => {
        expect(stream.close).toHaveBeenCalled();
        expect(result.current.liveMode).toBe("stopped");
      });

      unmount();
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });

  it("keeps previous events when SSE payload is malformed JSON", async () => {
    const originalEventSource = globalThis.EventSource;
    // @ts-expect-error test-only override
    globalThis.EventSource = class {};

    const stream = new HookEventSource();
    vi.spyOn(api, "openEventsStream").mockReturnValue(stream as unknown as EventSource);
    vi.spyOn(api, "fetchReports").mockResolvedValue([]);
    vi.spyOn(api, "fetchEvents").mockResolvedValue([]);

    try {
      const { result, unmount } = renderHook(() => useRunDetailLiveHarness());
      await waitFor(() => {
        expect(result.current.liveTransport).toBe("sse");
      });

      act(() => {
        stream.onmessage?.({
          data: "{malformed-json",
        } as MessageEvent<string>);
      });

      expect(result.current.events).toEqual([]);
      expect(result.current.liveError).toBe("");
      unmount();
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });

  it("falls back to polling after repeated SSE errors", async () => {
    const originalEventSource = globalThis.EventSource;
    // @ts-expect-error test-only override
    globalThis.EventSource = class {};

    const stream = new HookEventSource();
    const openEventsStreamSpy = vi.spyOn(api, "openEventsStream").mockReturnValue(stream as unknown as EventSource);
    vi.spyOn(api, "fetchEvents").mockResolvedValue([]);
    vi.spyOn(api, "fetchReports").mockResolvedValue([]);

    try {
      const { result, unmount } = renderHook(() => useRunDetailLiveHarness());
      await waitFor(() => {
        expect(result.current.liveTransport).toBe("sse");
      });

      act(() => {
        stream.onerror?.(new Event("error"));
        for (let index = 0; index < LIVE_SSE_FAILURE_LIMIT; index += 1) {
          stream.onerror?.(new Event("error"));
        }
      });

      await waitFor(() => {
        expect(result.current.liveTransport).toBe("polling");
      });
      expect(result.current.liveMode).toBe("running");
      expect(result.current.liveError).toBe("SSE stream error. Entered retry backoff.");
      expect(openEventsStreamSpy).toHaveBeenCalledTimes(1);

      unmount();
    } finally {
      globalThis.EventSource = originalEventSource;
    }
  });
});
