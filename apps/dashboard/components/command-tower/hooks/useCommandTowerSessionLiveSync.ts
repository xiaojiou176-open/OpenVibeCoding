import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";

import {
  fetchPmSession,
  fetchPmSessionConversationGraph,
  fetchPmSessionEvents,
  fetchPmSessionMetrics,
  openEventsStream,
} from "../../../lib/api";
import type {
  EventRecord,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
} from "../../../lib/types";
import {
  BASE_INTERVAL_MS,
  DELTA_EVENT_LIMIT,
  FULL_EVENT_LIMIT,
  MAX_INTERVAL_MS,
  REQUEST_TIMEOUT_MS,
  SSE_FAILURE_LIMIT,
  SSE_MERGE_WINDOW_MS,
  classifyError,
  extractErrorMessage,
  isTerminalStatus,
  lastEventTs,
  mergeEventWindow,
  type LiveErrorKind,
  type LiveMode,
  type LiveTransport,
} from "../sessionLiveHelpers";

type UseCommandTowerSessionLiveSyncArgs = {
  pmSessionId: string;
  initialDetail: PmSessionDetailPayload;
  initialEvents: EventRecord[];
  initialGraph: PmSessionConversationGraphPayload;
  initialMetrics: PmSessionMetricsPayload;
  liveEnabled: boolean;
  onDrawerFeedback: (message: string) => void;
};

type UseCommandTowerSessionLiveSyncResult = {
  detail: PmSessionDetailPayload;
  setDetail: Dispatch<SetStateAction<PmSessionDetailPayload>>;
  events: EventRecord[];
  graph: PmSessionConversationGraphPayload;
  metrics: PmSessionMetricsPayload;
  liveMode: LiveMode;
  setLiveMode: Dispatch<SetStateAction<LiveMode>>;
  transport: LiveTransport;
  setTransport: Dispatch<SetStateAction<LiveTransport>>;
  errorMessage: string;
  setErrorMessage: Dispatch<SetStateAction<string>>;
  errorKind: LiveErrorKind;
  setErrorKind: Dispatch<SetStateAction<LiveErrorKind>>;
  lastUpdated: string;
  setLastUpdated: Dispatch<SetStateAction<string>>;
  refreshing: boolean;
  intervalRef: MutableRefObject<number>;
  sseFailuresRef: MutableRefObject<number>;
  eventCursorRef: MutableRefObject<string>;
  refreshActionRef: MutableRefObject<() => Promise<void>>;
  refreshAll: () => Promise<void>;
};

export function useCommandTowerSessionLiveSync({
  pmSessionId,
  initialDetail,
  initialEvents,
  initialGraph,
  initialMetrics,
  liveEnabled,
  onDrawerFeedback,
}: UseCommandTowerSessionLiveSyncArgs): UseCommandTowerSessionLiveSyncResult {
  const [detail, setDetail] = useState(initialDetail);
  const [events, setEvents] = useState(initialEvents);
  const [graph, setGraph] = useState(initialGraph);
  const [metrics, setMetrics] = useState(initialMetrics);
  const [liveMode, setLiveMode] = useState<LiveMode>("running");
  const [transport, setTransport] = useState<LiveTransport>(
    String(initialDetail.session.latest_run_id || "").trim() ? "sse" : "polling",
  );
  const [errorMessage, setErrorMessage] = useState("");
  const [errorKind, setErrorKind] = useState<LiveErrorKind>("unknown");
  const [lastUpdated, setLastUpdated] = useState(initialDetail.session.updated_at || "");
  const [refreshing, setRefreshing] = useState(false);
  const isTerminal = isTerminalStatus(detail.session.status || "");

  const intervalRef = useRef(BASE_INTERVAL_MS);
  const sseFailuresRef = useRef(0);
  const eventCursorRef = useRef(lastEventTs(initialEvents));
  const activeRequestRef = useRef<AbortController | null>(null);
  const refreshInFlightRef = useRef(false);
  const refreshQueuedRef = useRef(false);
  const sseMergeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSseRefreshTsRef = useRef(0);
  const refreshActionRef = useRef<() => Promise<void>>(async () => {});
  const mountedRef = useRef(true);
  const lifecycleTokenRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      lifecycleTokenRef.current += 1;
      if (sseMergeTimerRef.current) {
        clearTimeout(sseMergeTimerRef.current);
        sseMergeTimerRef.current = null;
      }
      activeRequestRef.current?.abort();
      activeRequestRef.current = null;
      refreshInFlightRef.current = false;
      refreshQueuedRef.current = false;
    };
  }, []);

  useEffect(() => {
    lifecycleTokenRef.current += 1;
    if (sseMergeTimerRef.current) {
      clearTimeout(sseMergeTimerRef.current);
      sseMergeTimerRef.current = null;
    }
    lastSseRefreshTsRef.current = 0;
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    refreshInFlightRef.current = false;
    refreshQueuedRef.current = false;
    setDetail(initialDetail);
    setEvents(initialEvents);
    setGraph(initialGraph);
    setMetrics(initialMetrics);
    eventCursorRef.current = lastEventTs(initialEvents);
    intervalRef.current = BASE_INTERVAL_MS;
    sseFailuresRef.current = 0;
    setErrorMessage("");
    setErrorKind("unknown");
    setLastUpdated(initialDetail.session.updated_at || "");
    setRefreshing(false);
    if (!liveEnabled) {
      setLiveMode("paused");
      setTransport(String(initialDetail.session.latest_run_id || "").trim() ? "sse" : "polling");
      return;
    }
    if (isTerminalStatus(initialDetail.session.status || "")) {
      setLiveMode("stopped");
      setTransport("polling");
      return;
    }
    setLiveMode("running");
    setTransport(String(initialDetail.session.latest_run_id || "").trim() ? "sse" : "polling");
  }, [pmSessionId]);

  useEffect(() => {
    if (liveEnabled) {
      return;
    }
    lifecycleTokenRef.current += 1;
    if (sseMergeTimerRef.current) {
      clearTimeout(sseMergeTimerRef.current);
      sseMergeTimerRef.current = null;
    }
    lastSseRefreshTsRef.current = 0;
    activeRequestRef.current?.abort();
    activeRequestRef.current = null;
    refreshInFlightRef.current = false;
    refreshQueuedRef.current = false;
    setDetail(initialDetail);
    setEvents(initialEvents);
    setGraph(initialGraph);
    setMetrics(initialMetrics);
    eventCursorRef.current = lastEventTs(initialEvents);
    intervalRef.current = BASE_INTERVAL_MS;
    sseFailuresRef.current = 0;
    setErrorMessage("");
    setErrorKind("unknown");
    setLastUpdated(initialDetail.session.updated_at || "");
    setRefreshing(false);
    setLiveMode("paused");
    setTransport(String(initialDetail.session.latest_run_id || "").trim() ? "sse" : "polling");
  }, [initialDetail, initialEvents, initialGraph, initialMetrics, liveEnabled]);

  const refreshAll = useCallback(async () => {
    if (!mountedRef.current) {
      return;
    }
    const lifecycleToken = lifecycleTokenRef.current;
    if (refreshInFlightRef.current) {
      refreshQueuedRef.current = true;
      return;
    }
    refreshInFlightRef.current = true;
    setRefreshing(true);
    const controller = new AbortController();
    activeRequestRef.current?.abort();
    activeRequestRef.current = controller;
    const requestOptions = { signal: controller.signal, timeoutMs: REQUEST_TIMEOUT_MS };
    try {
      const eventSince = eventCursorRef.current || undefined;
      const eventLimit = eventSince ? DELTA_EVENT_LIMIT : FULL_EVENT_LIMIT;
      const graphWindow = (graph.window as "30m" | "2h" | "24h") || "24h";
      const [detailResult, eventsResult, graphResult, metricsResult] = await Promise.allSettled([
        fetchPmSession(pmSessionId, requestOptions),
        fetchPmSessionEvents(pmSessionId, {
          since: eventSince,
          limit: eventLimit,
          tail: true,
          signal: controller.signal,
          timeoutMs: REQUEST_TIMEOUT_MS,
        }),
        fetchPmSessionConversationGraph(
          pmSessionId,
          {
            window: graphWindow,
            groupByRole: true,
          },
          requestOptions,
        ),
        fetchPmSessionMetrics(pmSessionId, requestOptions),
      ]);
      if (
        !mountedRef.current ||
        lifecycleTokenRef.current !== lifecycleToken ||
        controller.signal.aborted
      ) {
        return;
      }
      let successCount = 0;
      const failures: string[] = [];
      if (detailResult.status === "fulfilled") {
        setDetail(detailResult.value);
        setLastUpdated(detailResult.value.session.updated_at || new Date().toISOString());
        successCount += 1;
      } else {
        failures.push(`detail: ${extractErrorMessage(detailResult.reason)}`);
      }
      if (eventsResult.status === "fulfilled") {
        setEvents((previous) => {
          const merged = mergeEventWindow(previous, eventsResult.value);
          eventCursorRef.current = lastEventTs(merged);
          return merged;
        });
        successCount += 1;
      } else {
        failures.push(`events: ${extractErrorMessage(eventsResult.reason)}`);
      }
      if (graphResult.status === "fulfilled") {
        setGraph(graphResult.value);
        successCount += 1;
      } else {
        failures.push(`graph: ${extractErrorMessage(graphResult.reason)}`);
      }
      if (metricsResult.status === "fulfilled") {
        setMetrics(metricsResult.value);
        successCount += 1;
      } else {
        failures.push(`metrics: ${extractErrorMessage(metricsResult.reason)}`);
      }
      if (successCount === 0) {
        setLiveMode("backoff");
        throw new Error(failures[0] || "all refresh requests failed");
      }
      if (failures.length > 0) {
        const partialMessage = `partial refresh degraded: ${failures.join(" | ")}`;
        setErrorMessage(partialMessage);
        setErrorKind(classifyError(partialMessage));
      } else {
        setErrorMessage("");
        setErrorKind("unknown");
      }
    } finally {
      refreshInFlightRef.current = false;
      if (mountedRef.current && lifecycleTokenRef.current === lifecycleToken) {
        setRefreshing(false);
      }
      if (activeRequestRef.current === controller) {
        activeRequestRef.current = null;
      }
      if (
        refreshQueuedRef.current &&
        mountedRef.current &&
        lifecycleTokenRef.current === lifecycleToken
      ) {
        refreshQueuedRef.current = false;
        void refreshAll();
      } else if (refreshQueuedRef.current) {
        refreshQueuedRef.current = false;
      }
    }
  }, [graph.window, pmSessionId]);

  refreshActionRef.current = refreshAll;

  useEffect(() => {
    if (transport !== "polling") {
      return;
    }
    if (!liveEnabled) {
      setLiveMode("paused");
      return;
    }
    if (isTerminal) {
      setLiveMode("stopped");
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (cancelled || isTerminal) {
        return;
      }
      try {
        await refreshActionRef.current();
        if (cancelled) {
          return;
        }
        intervalRef.current = BASE_INTERVAL_MS;
        setLiveMode("running");
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = extractErrorMessage(error);
        setErrorMessage(message);
        setErrorKind(classifyError(message));
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
        setLiveMode("backoff");
      } finally {
        if (!cancelled && liveEnabled && !isTerminal) {
          timer = setTimeout(tick, intervalRef.current);
        }
      }
    };
    timer = setTimeout(tick, intervalRef.current);
    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
      if (sseMergeTimerRef.current) {
        clearTimeout(sseMergeTimerRef.current);
        sseMergeTimerRef.current = null;
      }
      activeRequestRef.current?.abort();
      activeRequestRef.current = null;
      refreshInFlightRef.current = false;
      refreshQueuedRef.current = false;
    };
  }, [isTerminal, liveEnabled, pmSessionId, transport]);

  useEffect(() => {
    if (!liveEnabled) {
      setLiveMode("paused");
      return;
    }
    if (isTerminal) {
      setLiveMode("stopped");
      return;
    }
    if (transport === "sse") {
      setLiveMode("running");
    }
  }, [isTerminal, liveEnabled, transport]);

  useEffect(() => {
    if (!liveEnabled || isTerminal) {
      return;
    }
    const latestRunId = String(detail.session.latest_run_id || "").trim();
    if (!latestRunId) {
      setTransport("polling");
      return;
    }
    let stream: EventSource | null = null;
    let cancelled = false;
    let seenSseOpen = false;
    let reconnectNoiseBudget = 0;
    const eventSourceConnecting = typeof EventSource !== "undefined" ? EventSource.CONNECTING : 0;
    const resolveReadyState = (event?: Event): number | null => {
      const target =
        (event?.currentTarget as { readyState?: unknown } | null) ||
        (event?.target as { readyState?: unknown } | null);
      const state = target?.readyState ?? stream?.readyState;
      return typeof state === "number" ? state : null;
    };
    const scheduleSseRefresh = () => {
      if (sseMergeTimerRef.current) {
        return;
      }
      const elapsed = Date.now() - lastSseRefreshTsRef.current;
      const delay = elapsed >= SSE_MERGE_WINDOW_MS ? 0 : SSE_MERGE_WINDOW_MS - elapsed;
      sseMergeTimerRef.current = setTimeout(() => {
        sseMergeTimerRef.current = null;
        lastSseRefreshTsRef.current = Date.now();
        if (!cancelled) {
          void refreshActionRef.current().catch(() => {
            // polling loop handles retry/backoff
          });
        }
      }, delay);
    };
    try {
      stream = openEventsStream(latestRunId, {
        since: eventCursorRef.current || undefined,
        limit: 100,
        tail: true,
      });
      setTransport("sse");
    } catch {
      setTransport("polling");
      onDrawerFeedback("Failed to open the SSE channel. Fell back to polling.");
      return;
    }
    stream.onopen = () => {
      seenSseOpen = true;
      reconnectNoiseBudget = 1;
      sseFailuresRef.current = 0;
      setTransport("sse");
      setLiveMode("running");
      setErrorMessage("");
      setErrorKind("unknown");
    };
    stream.onmessage = () => {
      if (cancelled) {
        return;
      }
      setLiveMode("running");
      scheduleSseRefresh();
    };
    stream.onerror = (event) => {
      if (cancelled) {
        return;
      }
      const readyState = resolveReadyState(event);
      if (
        readyState === eventSourceConnecting &&
        seenSseOpen &&
        reconnectNoiseBudget > 0
      ) {
        reconnectNoiseBudget -= 1;
        return;
      }
      sseFailuresRef.current += 1;
      if (sseFailuresRef.current >= SSE_FAILURE_LIMIT) {
        setTransport("polling");
        setLiveMode("backoff");
        onDrawerFeedback("Repeated SSE failures detected. Switched to polling automatically.");
        stream?.close();
      }
    };
    return () => {
      cancelled = true;
      if (sseMergeTimerRef.current) {
        clearTimeout(sseMergeTimerRef.current);
        sseMergeTimerRef.current = null;
      }
      activeRequestRef.current?.abort();
      activeRequestRef.current = null;
      refreshInFlightRef.current = false;
      refreshQueuedRef.current = false;
      stream?.close();
    };
  }, [detail.session.latest_run_id, isTerminal, liveEnabled, onDrawerFeedback]);

  useEffect(() => {
    if (transport === "sse") {
      return;
    }
    if (!liveEnabled) {
      return;
    }
    if (isTerminal) {
      return;
    }
    onDrawerFeedback("Polling is active right now. You can keep monitoring the live state.");
  }, [isTerminal, liveEnabled, onDrawerFeedback, transport]);

  return {
    detail,
    setDetail,
    events,
    graph,
    metrics,
    liveMode,
    setLiveMode,
    transport,
    setTransport,
    errorMessage,
    setErrorMessage,
    errorKind,
    setErrorKind,
    lastUpdated,
    setLastUpdated,
    refreshing,
    intervalRef,
    sseFailuresRef,
    eventCursorRef,
    refreshActionRef,
    refreshAll,
  };
}
