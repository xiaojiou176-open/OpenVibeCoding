import { useEffect, useMemo, useState } from "react";
import {
  fetchDesktopAlerts,
  fetchDesktopOverview,
  fetchDesktopSessions,
  type DesktopAlert,
  type DesktopSessionSummary
} from "../lib/api";
import { sanitizeUiError } from "../lib/uiError";

const BASE_INTERVAL_MS = 1500;
const MAX_INTERVAL_MS = 8000;
const IS_TEST_MODE = import.meta.env.MODE === "test";
const SHOULD_LOG_ERROR = import.meta.env.DEV || import.meta.env.MODE === "test";
const RETRY_DELAY_MS = 250;

export function nextBackoffInterval(currentMs: number): number {
  return Math.min(currentMs * 2, MAX_INTERVAL_MS);
}

function isNetworkUnreachable(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const normalized = error.message.toLowerCase();
  return (
    normalized.includes("failed to fetch") ||
    normalized.includes("networkerror") ||
    normalized.includes("load failed") ||
    normalized.includes("connection refused")
  );
}

function toReachabilityCopy(error: unknown, fallback: string): string {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    return "The network is offline. Live polling is paused and will retry automatically when connectivity returns.";
  }
  if (isNetworkUnreachable(error)) {
    return "The backend is currently unreachable. Backoff retry is active and local actions can continue.";
  }
  return sanitizeUiError(error, fallback);
}

async function fetchWithRetry<T>(task: (signal: AbortSignal) => Promise<T>, attempts = 2): Promise<T> {
  let lastError: unknown;
  for (let index = 0; index < attempts; index += 1) {
    const controller = new AbortController();
    try {
      return await task(controller.signal);
    } catch (error) {
      controller.abort();
      lastError = error;
      if (index + 1 >= attempts) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    }
  }
  throw lastError;
}

export type OverviewMetric = {
  label: string;
  value: string;
  detail: string;
};

type LiveDataResult = {
  overviewMetrics: OverviewMetric[];
  sessions: DesktopSessionSummary[];
  alerts: DesktopAlert[];
  liveError: string;
  refreshNow: () => void;
};

const fallbackMetrics: OverviewMetric[] = [
  { label: "Active sessions", value: "--", detail: "Waiting for backend connectivity" },
  { label: "Failure rate", value: "--", detail: "Waiting for backend connectivity" },
  { label: "Blocked sessions", value: "--", detail: "Waiting for backend connectivity" }
];

export function useDesktopData(activePage: string): LiveDataResult {
  const [overviewMetrics, setOverviewMetrics] = useState<OverviewMetric[]>(fallbackMetrics);
  const [sessions, setSessions] = useState<DesktopSessionSummary[]>([]);
  const [alerts, setAlerts] = useState<DesktopAlert[]>([]);
  const [liveError, setLiveError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let intervalMs = BASE_INTERVAL_MS;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const loop = async () => {
      try {
        const payload = await fetchWithRetry((signal) => fetchDesktopOverview(signal));
        if (!cancelled) {
          setOverviewMetrics([
            {
              label: "Active sessions",
              value: String(payload.active_sessions ?? "0"),
              detail: `${payload.total_sessions ?? 0} sessions in total`
            },
            {
              label: "Failure rate",
              value: `${Math.round((payload.failed_ratio ?? 0) * 100)}%`,
              detail: "Tracks failure trend over time"
            },
            {
              label: "Blocked sessions",
              value: String(payload.blocked_sessions ?? 0),
              detail: "Needs manual triage"
            }
          ]);
          intervalMs = BASE_INTERVAL_MS;
          if (activePage === "overview") {
            setLiveError("");
          }
        }
      } catch (error) {
        if (!cancelled) {
          intervalMs = nextBackoffInterval(intervalMs);
          if (activePage === "overview") {
            setLiveError(toReachabilityCopy(error, "Failed to refresh overview data"));
          }
          if (SHOULD_LOG_ERROR) {
            console.error("[desktop-overview] fetch failed:", error instanceof Error ? error.message : String(error));
          }
        }
      }

      if (!cancelled && !IS_TEST_MODE) {
        timer = setTimeout(loop, intervalMs);
      }
    };

    void loop();

    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [refreshKey, activePage]);

  useEffect(() => {
    let cancelled = false;
    void fetchWithRetry((signal) => fetchDesktopSessions(signal))
      .then((rows) => {
        if (cancelled) {
          return;
        }
        setSessions(rows);
        if (activePage === "sessions") {
          setLiveError("");
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        if (activePage === "sessions") {
          setLiveError(toReachabilityCopy(error, "Failed to refresh the session list"));
        }
        if (SHOULD_LOG_ERROR) {
          console.error("[desktop-sessions] fetch failed:", error instanceof Error ? error.message : String(error));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activePage, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    void fetchWithRetry((signal) => fetchDesktopAlerts(signal))
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setAlerts(Array.isArray(payload.alerts) ? payload.alerts : []);
        if (activePage === "gates") {
          setLiveError("");
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        if (activePage === "gates") {
          setLiveError(toReachabilityCopy(error, "Failed to refresh policy alerts"));
        }
        if (SHOULD_LOG_ERROR) {
          console.error("[desktop-alerts] fetch failed:", error instanceof Error ? error.message : String(error));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [activePage, refreshKey]);

  return useMemo(
    () => ({
      overviewMetrics,
      sessions,
      alerts,
      liveError,
      refreshNow: () => setRefreshKey((value) => value + 1)
    }),
    [overviewMetrics, sessions, alerts, liveError]
  );
}
