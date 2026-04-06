import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { fetchEvents, fetchReports, openEventsStream } from "../../lib/api";
import type { EventRecord, ReportRecord } from "../../lib/types";
import {
  LIVE_BASE_INTERVAL_MS,
  LIVE_EVENT_LIMIT,
  LIVE_MAX_INTERVAL_MS,
  LIVE_REPORT_REFRESH_CYCLE,
  LIVE_SSE_FAILURE_LIMIT,
  deriveTerminalStatus,
  isTerminalStatus,
  latestEventTimestamp,
  mergeEvents,
  type LiveMode,
  type LiveTransport,
} from "./runDetailHelpers";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

type UseRunDetailLiveParams = {
  runId: string | undefined;
  runStatus: unknown;
  liveEnabled: boolean;
  eventsRef: MutableRefObject<EventRecord[]>;
  reportsRef: MutableRefObject<ReportRecord[]>;
  setEventsState: Dispatch<SetStateAction<EventRecord[]>>;
  setReportsState: Dispatch<SetStateAction<ReportRecord[]>>;
  setLiveMode: Dispatch<SetStateAction<LiveMode>>;
  setLiveTransport: Dispatch<SetStateAction<LiveTransport>>;
  setLiveError: Dispatch<SetStateAction<string>>;
  setLiveIntervalMs: Dispatch<SetStateAction<number>>;
  setLiveLagMs: Dispatch<SetStateAction<number>>;
  setLastRefreshAt: Dispatch<SetStateAction<string>>;
};

export function useRunDetailLive({
  runId,
  runStatus,
  liveEnabled,
  eventsRef,
  reportsRef,
  setEventsState,
  setReportsState,
  setLiveMode,
  setLiveTransport,
  setLiveError,
  setLiveIntervalMs,
  setLiveLagMs,
  setLastRefreshAt,
}: UseRunDetailLiveParams) {
  useEffect(() => {
    if (!liveEnabled) {
      setLiveMode("paused");
      return;
    }
    if (!runId) {
      setLiveMode("paused");
      return;
    }
    if (isTerminalStatus(deriveTerminalStatus(runStatus, reportsRef.current))) {
      setLiveMode("stopped");
      return;
    }

    let active = true;
    let timer: number | null = null;
    let retryDelay = LIVE_BASE_INTERVAL_MS;
    let refreshCycle = 0;
    let sseFailures = 0;
    let stream: EventSource | null = null;

    const clearTimer = () => {
      if (timer) {
        window.clearTimeout(timer);
        timer = null;
      }
    };

    const applyLiveSnapshot = (nextEvents: EventRecord[]) => {
      const latestTs = latestEventTimestamp(nextEvents);
      const tsMs = latestTs ? Date.parse(latestTs) : Number.NaN;
      setLiveLagMs(Number.isFinite(tsMs) ? Math.max(0, Date.now() - tsMs) : 0);
      setLastRefreshAt(new Date().toISOString());
    };

    const refreshReports = async () => {
      const nextReports = await fetchReports(runId);
      if (!active) {
        return;
      }
      const reportList = Array.isArray(nextReports) ? nextReports : [];
      reportsRef.current = reportList;
      setReportsState(reportList);
    };

    const schedulePolling = (delayMs: number) => {
      if (!active) {
        return;
      }
      clearTimer();
      setLiveIntervalMs(delayMs);
      timer = window.setTimeout(() => {
        void pollingTick();
      }, delayMs);
    };

    const startPolling = (delayMs = LIVE_BASE_INTERVAL_MS) => {
      setLiveTransport("polling");
      setLiveMode("running");
      schedulePolling(delayMs);
    };

    const pollingTick = async () => {
      if (!active) {
        return;
      }
      if (isTerminalStatus(deriveTerminalStatus(runStatus, reportsRef.current))) {
        setLiveMode("stopped");
        return;
      }
      try {
        const since = latestEventTimestamp(eventsRef.current);
        const incomingEvents = await fetchEvents(runId, {
          since,
          limit: LIVE_EVENT_LIMIT,
          tail: true,
        });
        if (!active) {
          return;
        }

        const mergedEvents = mergeEvents(eventsRef.current, Array.isArray(incomingEvents) ? incomingEvents : []);
        eventsRef.current = mergedEvents;
        setEventsState(mergedEvents);

        refreshCycle += 1;
        if (refreshCycle >= LIVE_REPORT_REFRESH_CYCLE) {
          refreshCycle = 0;
          await refreshReports();
        }

        applyLiveSnapshot(mergedEvents);
        setLiveError("");
        setLiveMode(isTerminalStatus(deriveTerminalStatus(runStatus, reportsRef.current)) ? "stopped" : "running");
        retryDelay = LIVE_BASE_INTERVAL_MS;
        if (!isTerminalStatus(deriveTerminalStatus(runStatus, reportsRef.current))) {
          schedulePolling(retryDelay);
        }
      } catch (err: unknown) {
        if (!active) {
          return;
        }
        console.error(`[run-detail-live] polling refresh failed: ${uiErrorDetail(err)}`);
        const message = sanitizeUiError(err, "Live refresh failed");
        setLiveError(message);
        setLiveMode("backoff");
        retryDelay = Math.min(LIVE_MAX_INTERVAL_MS, retryDelay * 2);
        schedulePolling(retryDelay);
      }
    };

    const startSse = () => {
      if (!active) {
        return;
      }
      if (typeof EventSource === "undefined") {
        startPolling();
        return;
      }
      clearTimer();
      try {
        const since = latestEventTimestamp(eventsRef.current);
        stream = openEventsStream(runId, {
          since,
          limit: LIVE_EVENT_LIMIT,
          tail: true,
        });
      } catch (err: unknown) {
        console.error(`[run-detail-live] sse init failed: ${uiErrorDetail(err)}`);
        const message = sanitizeUiError(err, "Live stream initialization failed");
        setLiveError(message);
        startPolling();
        return;
      }

      setLiveTransport("sse");
      setLiveMode("running");
      setLiveError("");
      setLiveIntervalMs(0);

      stream.onopen = () => {
        if (!active) {
          return;
        }
        sseFailures = 0;
        retryDelay = LIVE_BASE_INTERVAL_MS;
        setLiveMode("running");
        setLiveError("");
      };

      stream.onmessage = (message: MessageEvent<string>) => {
        if (!active) {
          return;
        }
        let item: EventRecord | null = null;
        try {
          item = JSON.parse(message.data) as EventRecord;
        } catch {
          return;
        }

        const mergedEvents = mergeEvents(eventsRef.current, [item]);
        eventsRef.current = mergedEvents;
        setEventsState(mergedEvents);

        refreshCycle += 1;
        if (refreshCycle >= LIVE_REPORT_REFRESH_CYCLE) {
          refreshCycle = 0;
          void refreshReports().catch((err: unknown) => {
            if (!active) {
              return;
            }
            console.error(`[run-detail-live] report refresh failed: ${uiErrorDetail(err)}`);
            const reportErr = sanitizeUiError(err, "Live report refresh failed");
            setLiveError(reportErr);
            setLiveMode("backoff");
          });
        }

        applyLiveSnapshot(mergedEvents);
        const terminal = isTerminalStatus(deriveTerminalStatus(runStatus, reportsRef.current));
        setLiveMode(terminal ? "stopped" : "running");
        if (terminal && stream) {
          stream.close();
          stream = null;
        }
      };

      stream.onerror = () => {
        if (!active) {
          return;
        }
        if (stream) {
          stream.close();
          stream = null;
        }
        sseFailures += 1;
        retryDelay = Math.min(LIVE_MAX_INTERVAL_MS, retryDelay * 2);
        setLiveMode("backoff");
        setLiveError("SSE stream error. Entered retry backoff.");
        setLiveIntervalMs(retryDelay);

        if (sseFailures >= LIVE_SSE_FAILURE_LIMIT) {
          startPolling(retryDelay);
          return;
        }

        timer = window.setTimeout(() => {
          startSse();
        }, retryDelay);
      };
    };

    startSse();

    return () => {
      active = false;
      clearTimer();
      if (stream) {
        stream.close();
        stream = null;
      }
    };
  }, [
    liveEnabled,
    runId,
    runStatus,
    eventsRef,
    reportsRef,
    setEventsState,
    setReportsState,
    setLiveMode,
    setLiveTransport,
    setLiveError,
    setLiveIntervalMs,
    setLiveLagMs,
    setLastRefreshAt,
  ]);
}
