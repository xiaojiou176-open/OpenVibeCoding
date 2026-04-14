"use client";

import dynamic from "next/dynamic";
import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import type { StatusVariant } from "@openvibecoding/frontend-shared/statusPresentation";

import { fetchCommandTowerAlerts, fetchCommandTowerOverview, fetchPmSessions } from "../../lib/api";
import type {
  CommandTowerAlert,
  CommandTowerAlertsPayload,
  CommandTowerOverviewPayload,
  PmSessionSummary,
} from "../../lib/types";
import CommandTowerHomeDrawer from "./CommandTowerHomeDrawer";
import CommandTowerHomeLayout from "./CommandTowerHomeLayout";
import SessionBoard from "./SessionBoard";
import { buildHomeViewModel } from "./commandTowerHomeViewModel";
import { useCommandTowerHomeFilters } from "./hooks/useCommandTowerHomeFilters";
import { useDrawerPreferences } from "./hooks/useDrawerPreferences";
import {
  alertsBadgeVariant,
  classifyErrorMessage,
  FOCUS_OPTIONS,
  homeLiveBadgeVariant,
  homeLiveBadgeText,
  sectionStatusBadgeVariant,
  sectionStatusLabel,
  SORT_OPTIONS,
  STATUS_OPTIONS,
} from "./commandTowerHomeHelpers";
import type { FocusMode, LiveMode, QuickActionId, SectionFetchStatus } from "./commandTowerHomeHelpers";

const BASE_INTERVAL_MS = 3000;
const MAX_INTERVAL_MS = 8000;
const REQUEST_TIMEOUT_MS = 12000;
const REQUEST_RETRY_ATTEMPTS = 2;
const HOME_DRAWER_COLLAPSED_KEY = "openvibecoding.commandTower.home.drawerCollapsed";
const HOME_DRAWER_PINNED_KEY = "openvibecoding.commandTower.home.drawerPinned";

type CommandTowerHomeLiveProps = {
  initialOverview: CommandTowerOverviewPayload;
  initialSessions: PmSessionSummary[];
  locale?: UiLocale;
};

type RefreshNowOptions = {
  feedbackMode?: "retry" | "focus_switch";
  skipStartFeedback?: boolean;
  successFeedback?: string;
  partialFeedback?: string;
  failureFeedback?: string;
};

function summarizeSessions(items: PmSessionSummary[]) {
  let failed = 0;
  let blocked = 0;
  let running = 0;
  for (const session of items) {
    if (session.failed_runs > 0) {
      failed += 1;
    }
    if (session.blocked_runs > 0) {
      blocked += 1;
    }
    if (session.running_runs > 0) {
      running += 1;
    }
  }
  return {
    total: items.length,
    failed,
    blocked,
    running,
  };
}

function sessionPriorityScore(session: PmSessionSummary): number {
  if (session.failed_runs > 0) {
    return 0;
  }
  if (session.blocked_runs > 0) {
    return 1;
  }
  if (session.running_runs > 0) {
    return 2;
  }
  return 3;
}

function focusModeActionLabel(
  mode: FocusMode,
  focusModeLabels: ReturnType<typeof getUiCopy>["dashboard"]["commandTowerPage"]["liveHome"]["focusModeLabels"],
): string {
  if (mode === "high_risk") {
    return focusModeLabels.highRisk;
  }
  if (mode === "blocked") {
    return focusModeLabels.blocked;
  }
  if (mode === "running") {
    return focusModeLabels.running;
  }
  return focusModeLabels.all;
}

export { alertsBadgeVariant, classifyErrorMessage, homeLiveBadgeVariant, homeLiveBadgeText };

export default function CommandTowerHomeLive({
  initialOverview,
  initialSessions,
  locale = "en",
}: CommandTowerHomeLiveProps) {
  const uiCopy = getUiCopy(locale);
  const commandTowerCopy = uiCopy.desktop.commandTower;
  const liveHomeCopy = uiCopy.dashboard.commandTowerPage.liveHome;
  const [overview, setOverview] = useState(initialOverview);
  const [sessions, setSessions] = useState(initialSessions);
  const [alerts, setAlerts] = useState<CommandTowerAlert[]>([]);
  const [alertsStatus, setAlertsStatus] = useState<CommandTowerAlertsPayload["status"]>("healthy");
  const [liveMode, setLiveMode] = useState<LiveMode>("running");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState(initialOverview.generated_at || "");
  const [lastSuccessfulUpdated, setLastSuccessfulUpdated] = useState(initialOverview.generated_at || "");
  const [sectionStatus, setSectionStatus] = useState<{
    overview: SectionFetchStatus;
    sessions: SectionFetchStatus;
    alerts: SectionFetchStatus;
  }>({
    overview: "ok",
    sessions: "ok",
    alerts: "ok",
  });
  const [actionFeedback, setActionFeedback] = useState("");

  const intervalRef = useRef(BASE_INTERVAL_MS);
  const projectInputRef = useRef<HTMLInputElement | null>(null);
  const previousRefreshTokenRef = useRef(0);
  const refreshRequestIdRef = useRef(0);
  const SessionBoardComponent = useMemo(
    () =>
      process.env.NODE_ENV === "test"
        ? SessionBoard
        : dynamic(() => import("./SessionBoard"), {
            ssr: false,
            loading: () => (
              <div className="compact-status-card" role="status" aria-live="polite">
                <p className="ct-home-empty-text">{liveHomeCopy.loadingSessionBoard}</p>
              </div>
            ),
          }),
    [liveHomeCopy.loadingSessionBoard],
  );
  const DrawerComponent = useMemo(
    () =>
      process.env.NODE_ENV === "test"
        ? CommandTowerHomeDrawer
        : dynamic(() => import("./CommandTowerHomeDrawer"), {
            ssr: false,
            loading: () => (
              <div
                id="ct-home-drawer-shell"
                className="ct-drawer-panel"
                role="region"
                aria-label={liveHomeCopy.loadingContextPanelAriaLabel}
                aria-busy="true"
              >
                <div className="ct-drawer-header">
                  <h3 className="ct-drawer-title">{liveHomeCopy.loadingContextPanelTitle}</h3>
                </div>
                <div className="ct-drawer-section">
                  <p className="mono" role="status">{liveHomeCopy.loadingContextPanelBody}</p>
                </div>
              </div>
            ),
          }),
    [
      liveHomeCopy.loadingContextPanelAriaLabel,
      liveHomeCopy.loadingContextPanelBody,
      liveHomeCopy.loadingContextPanelTitle,
    ],
  );
  const {
    draftStatuses,
    draftProjectKey,
    setDraftProjectKey,
    draftSort,
    setDraftSort,
    focusMode,
    setFocusMode: setFocusModeState,
    liveEnabled,
    setLiveEnabled,
    appliedStatuses,
    appliedProjectKey,
    appliedSort,
    refreshToken,
    toggleDraftStatus,
    applyFilters,
    resetFilters,
    buildShareUrl,
  } = useCommandTowerHomeFilters();
  const {
    drawerCollapsed,
    setDrawerCollapsed,
    drawerPinned,
    setDrawerPinned,
  } = useDrawerPreferences({
    collapsedStorageKey: HOME_DRAWER_COLLAPSED_KEY,
    pinnedStorageKey: HOME_DRAWER_PINNED_KEY,
  });

  const errorMeta = useMemo(() => classifyErrorMessage(errorMessage), [errorMessage]);

  const toggleDrawerCollapsed = useCallback(() => {
    setDrawerCollapsed((prev) => {
      const next = !prev;
      setActionFeedback(next ? liveHomeCopy.actionFeedback.collapsedDrawer : liveHomeCopy.actionFeedback.expandedDrawer);
      return next;
    });
  }, [liveHomeCopy.actionFeedback.collapsedDrawer, liveHomeCopy.actionFeedback.expandedDrawer]);

  const toggleDrawerPinned = useCallback(() => {
    setDrawerPinned((prev) => {
      const next = !prev;
      setActionFeedback(next ? liveHomeCopy.actionFeedback.pinnedDrawer : liveHomeCopy.actionFeedback.unpinnedDrawer);
      return next;
    });
  }, [liveHomeCopy.actionFeedback.pinnedDrawer, liveHomeCopy.actionFeedback.unpinnedDrawer]);

  const handleFilterKeyDown = (event: ReactKeyboardEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyFilters();
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      resetFilters();
    }
  };

  const refreshAll = useCallback(
    async (signal: AbortSignal, requestId?: number) => {
      const activeRequestId = requestId ?? refreshRequestIdRef.current + 1;
      refreshRequestIdRef.current = activeRequestId;
      const normalizeRetryError = (error: unknown): Error => {
        if (error instanceof Error) {
          return error;
        }
        if (typeof error === "string" && error.trim().length > 0) {
          return new Error(error);
        }
        return new Error("request failed");
      };
      const fetchWithRetry = async <T,>(factory: () => Promise<T>, attempts = REQUEST_RETRY_ATTEMPTS): Promise<T> => {
        let lastError: unknown = null;
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
          try {
            return await factory();
          } catch (error) {
            lastError = normalizeRetryError(error);
            if (attempt < attempts) {
              await new Promise((resolve) => setTimeout(resolve, 300 * attempt));
            }
          }
        }
        throw lastError instanceof Error ? lastError : new Error("request failed");
      };

      const settled = await Promise.allSettled([
        fetchWithRetry(() => fetchCommandTowerOverview({ signal, timeoutMs: REQUEST_TIMEOUT_MS })),
        fetchWithRetry(() =>
          fetchPmSessions(
            {
              status: appliedStatuses.length > 0 ? appliedStatuses : undefined,
              projectKey: appliedProjectKey || undefined,
              sort: appliedSort,
              limit: 40,
              signal,
              timeoutMs: REQUEST_TIMEOUT_MS,
            },
          )
        ),
        fetchWithRetry(() => fetchCommandTowerAlerts({ signal, timeoutMs: REQUEST_TIMEOUT_MS })),
      ]);

      if (refreshRequestIdRef.current !== activeRequestId) {
        return { stale: true as const, partialFailure: false, errorMessage: "" };
      }

      let successCount = 0;
      let firstErrorMessage = "";
      const statusSnapshot: {
        overview: SectionFetchStatus;
        sessions: SectionFetchStatus;
        alerts: SectionFetchStatus;
      } = {
        overview: "error",
        sessions: "error",
        alerts: "error",
      };

      const overviewResult = settled[0];
      if (overviewResult.status === "fulfilled") {
        successCount += 1;
        statusSnapshot.overview = "ok";
        setOverview(overviewResult.value);
        setLastUpdated(overviewResult.value.generated_at || new Date().toISOString());
      } else if (!firstErrorMessage) {
        firstErrorMessage = overviewResult.reason instanceof Error ? overviewResult.reason.message : String(overviewResult.reason);
      }

      const sessionsResult = settled[1];
      if (sessionsResult.status === "fulfilled") {
        successCount += 1;
        statusSnapshot.sessions = "ok";
        setSessions(sessionsResult.value);
      } else if (!firstErrorMessage) {
        firstErrorMessage = sessionsResult.reason instanceof Error ? sessionsResult.reason.message : String(sessionsResult.reason);
      }

      const alertsResult = settled[2];
      if (alertsResult.status === "fulfilled") {
        successCount += 1;
        statusSnapshot.alerts = "ok";
        setAlerts(alertsResult.value.alerts || []);
        setAlertsStatus(alertsResult.value.status || "healthy");
      } else if (!firstErrorMessage) {
        firstErrorMessage = alertsResult.reason instanceof Error ? alertsResult.reason.message : String(alertsResult.reason);
      }

      setSectionStatus(statusSnapshot);
      if (successCount < settled.length) {
        setAlertsStatus(successCount === 0 ? "critical" : "degraded");
      }
      if (successCount === settled.length) {
        setLastSuccessfulUpdated(new Date().toISOString());
      }
      if (successCount === 0) {
        throw new Error(firstErrorMessage || liveHomeCopy.refreshHealth.refreshFailed);
      }

      return {
        stale: false as const,
        partialFailure: successCount < settled.length,
        errorMessage: firstErrorMessage,
      };
    },
    [appliedProjectKey, appliedSort, appliedStatuses],
  );

  const refreshNow = useCallback(async (options?: RefreshNowOptions) => {
    const feedbackMode = options?.feedbackMode || "retry";
    const defaultFeedback =
      feedbackMode === "focus_switch"
        ? {
            start: liveHomeCopy.actionFeedback.focusSwitchStart,
            partial: liveHomeCopy.actionFeedback.focusSwitchPartial,
            success: liveHomeCopy.actionFeedback.focusSwitchSuccess(liveHomeCopy.focusModeLabels.all),
            failure: liveHomeCopy.actionFeedback.focusSwitchFailure,
          }
        : {
            start: liveHomeCopy.actionFeedback.retryRefreshStart,
            partial: liveHomeCopy.actionFeedback.retryRefreshPartial,
            success: liveHomeCopy.actionFeedback.retryRefreshSuccess,
            failure: liveHomeCopy.actionFeedback.retryRefreshFailure,
          };
    const controller = new AbortController();
    setIsRefreshing(true);
    if (!options?.skipStartFeedback) {
      setActionFeedback(defaultFeedback.start);
    }
    try {
      const requestId = refreshRequestIdRef.current + 1;
      const result = await refreshAll(controller.signal, requestId);
      if (result.stale) {
        return;
      }
      if (result.partialFailure) {
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
        if (liveEnabled) {
          setLiveMode("backoff");
        }
        if (result.errorMessage) {
          setErrorMessage(result.errorMessage);
        }
        setActionFeedback(options?.partialFeedback || defaultFeedback.partial);
      } else {
        setErrorMessage("");
        intervalRef.current = BASE_INTERVAL_MS;
        if (liveEnabled) {
          setLiveMode("running");
        }
        setActionFeedback(options?.successFeedback || defaultFeedback.success);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setErrorMessage(message);
      intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
      if (liveEnabled) {
        setLiveMode("backoff");
      }
      setActionFeedback(options?.failureFeedback || defaultFeedback.failure);
    } finally {
      setIsRefreshing(false);
    }
  }, [liveEnabled, refreshAll]);

  const exportFailedSessions = useCallback(() => {
    const failed = sessions.filter((item) => String(item.status || "") === "failed");
    const payload = {
      exported_at: new Date().toISOString(),
      total_failed_sessions: failed.length,
      sessions: failed,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `command-tower-failed-sessions-${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [sessions]);

  const copyCurrentViewLink = useCallback(async () => {
    const shareUrl = buildShareUrl();
    if (!shareUrl) {
      setActionFeedback(liveHomeCopy.actionFeedback.copyUnavailable);
      return;
    }

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = shareUrl;
        textarea.setAttribute("readonly", "");
        textarea.className = "clipboard-copy-buffer";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setActionFeedback(liveHomeCopy.actionFeedback.copiedCurrentView);
    } catch {
      setActionFeedback(liveHomeCopy.actionFeedback.copyFailedManual);
    }
  }, [
    buildShareUrl,
    liveHomeCopy.actionFeedback.copyFailedManual,
    liveHomeCopy.actionFeedback.copyUnavailable,
    liveHomeCopy.actionFeedback.copiedCurrentView,
  ]);

  const handleFocusModeChange = useCallback(
    (nextMode: FocusMode, feedback?: string) => {
      const modeChanged = focusMode !== nextMode;
      setFocusModeState(nextMode);
      if (feedback && !modeChanged) {
        setActionFeedback(feedback);
        return;
      }
      if (!modeChanged) {
        return;
      }
      const focusSwitchFeedback =
        feedback || liveHomeCopy.actionFeedback.focusSwitchSuccess(focusModeActionLabel(nextMode, liveHomeCopy.focusModeLabels));
      setActionFeedback(liveHomeCopy.actionFeedback.focusSwitchStart);
      void refreshNow({
        feedbackMode: "focus_switch",
        skipStartFeedback: true,
        successFeedback: focusSwitchFeedback,
        partialFeedback: liveHomeCopy.actionFeedback.focusSwitchPartial,
      });
    },
    [focusMode, liveHomeCopy.actionFeedback.focusSwitchPartial, liveHomeCopy.actionFeedback.focusSwitchStart, liveHomeCopy.actionFeedback.focusSwitchSuccess, liveHomeCopy.focusModeLabels, refreshNow, setFocusModeState],
  );

  const toggleHighRiskFocus = useCallback(() => {
    const nextMode: FocusMode = focusMode === "high_risk" ? "all" : "high_risk";
    handleFocusModeChange(nextMode);
  }, [focusMode, handleFocusModeChange]);

  useEffect(() => {
    const refreshTokenChanged = previousRefreshTokenRef.current !== refreshToken;
    previousRefreshTokenRef.current = refreshToken;

    if (!liveEnabled) {
      setLiveMode("paused");
      if (!refreshTokenChanged) {
        return;
      }

      let cancelled = false;
      const controller = new AbortController();

      const refreshWhilePaused = async () => {
        try {
          const requestId = refreshRequestIdRef.current + 1;
          const result = await refreshAll(controller.signal, requestId);
          if (cancelled || result.stale) {
            return;
          }
          if (result.partialFailure) {
            if (result.errorMessage) {
              setErrorMessage(result.errorMessage);
            }
          } else {
            setErrorMessage("");
          }
        } catch (error) {
          if (cancelled) {
            return;
          }
          const message = error instanceof Error ? error.message : String(error);
          setErrorMessage(message);
        }
      };

      void refreshWhilePaused();

      return () => {
        cancelled = true;
        controller.abort();
      };
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlightController: AbortController | null = null;

    const tick = async () => {
      if (cancelled) {
        return;
      }
      inFlightController = new AbortController();

      try {
        const requestId = refreshRequestIdRef.current + 1;
        const result = await refreshAll(inFlightController.signal, requestId);
        if (cancelled) {
          return;
        }

        if (result.partialFailure) {
          intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
          setLiveMode(liveEnabled ? "backoff" : "paused");
          if (result.errorMessage) {
            setErrorMessage(result.errorMessage);
          }
        } else {
          setErrorMessage("");
          intervalRef.current = BASE_INTERVAL_MS;
          setLiveMode(liveEnabled ? "running" : "paused");
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        const message = error instanceof Error ? error.message : String(error);
        setErrorMessage(message);
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
        setLiveMode(liveEnabled ? "backoff" : "paused");
      } finally {
        if (!cancelled && liveEnabled) {
          timer = setTimeout(tick, intervalRef.current);
        }
      }
    };

    timer = setTimeout(tick, 0);

    return () => {
      cancelled = true;
      inFlightController?.abort();
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [liveEnabled, refreshAll, refreshToken]);

  useEffect(() => {
    if (!actionFeedback) {
      return;
    }
    const timer = setTimeout(() => {
      setActionFeedback("");
    }, 3500);
    return () => clearTimeout(timer);
  }, [actionFeedback]);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) {
        return false;
      }
      if (target.isContentEditable) {
        return true;
      }
      const tag = target.tagName.toLowerCase();
      return tag === "input" || tag === "textarea" || tag === "select";
    };

    const onGlobalKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || !event.shiftKey || event.repeat) {
        return;
      }
      if (isEditableTarget(event.target)) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "r") {
        event.preventDefault();
        void refreshNow();
        return;
      }
      if (key === "l") {
        event.preventDefault();
        setLiveEnabled((prev) => {
          const next = !prev;
          setActionFeedback(next ? liveHomeCopy.actionFeedback.resumedLiveRefresh : liveHomeCopy.actionFeedback.pausedLiveRefresh);
          return next;
        });
        return;
      }
      if (key === "e") {
        event.preventDefault();
        exportFailedSessions();
        setActionFeedback(liveHomeCopy.actionFeedback.exportedFailedSessions);
        return;
      }
      if (key === "c") {
        event.preventDefault();
        void copyCurrentViewLink();
        return;
      }
      if (key === "f") {
        event.preventDefault();
        projectInputRef.current?.focus();
        setActionFeedback(liveHomeCopy.actionFeedback.focusedProjectKeyInput);
        return;
      }
      if (key === "d") {
        event.preventDefault();
        toggleDrawerCollapsed();
        return;
      }
      if (key === "p") {
        event.preventDefault();
        toggleDrawerPinned();
        return;
      }
      if (key === "1") {
        event.preventDefault();
        handleFocusModeChange("all");
        return;
      }
      if (key === "2") {
        event.preventDefault();
        handleFocusModeChange("high_risk");
        return;
      }
      if (key === "3") {
        event.preventDefault();
        handleFocusModeChange("blocked");
        return;
      }
      if (key === "4") {
        event.preventDefault();
        handleFocusModeChange("running");
      }
    };

    window.addEventListener("keydown", onGlobalKeyDown);
    return () => window.removeEventListener("keydown", onGlobalKeyDown);
  }, [copyCurrentViewLink, exportFailedSessions, handleFocusModeChange, refreshNow, toggleDrawerCollapsed, toggleDrawerPinned]);

  const liveStatusText =
    liveMode === "paused"
      ? liveHomeCopy.liveStatus.paused
      : liveMode === "backoff"
        ? liveHomeCopy.liveStatus.backoff
        : alertsStatus !== "healthy"
          ? liveHomeCopy.liveStatus.degraded
          : liveHomeCopy.liveStatus.running;
  const draftChanged =
    draftSort !== appliedSort ||
    draftProjectKey.trim() !== appliedProjectKey ||
    draftStatuses.length !== appliedStatuses.length ||
    draftStatuses.some((status) => !appliedStatuses.includes(status));
  const draftFilterCount = draftStatuses.length + (draftProjectKey.trim() ? 1 : 0);
  const appliedFilterCount = appliedStatuses.length + (appliedProjectKey ? 1 : 0);
  const alertsSeveritySummary = useMemo(() => {
    const summary = { critical: 0, warning: 0, info: 0, unknown: 0 };
    for (const item of alerts) {
      const severity = String(item?.severity || "").toLowerCase();
      if (severity === "critical") {
        summary.critical += 1;
      } else if (severity === "warning") {
        summary.warning += 1;
      } else if (severity === "info") {
        summary.info += 1;
      } else {
        summary.unknown += 1;
      }
    }
    return summary;
  }, [alerts]);
  const filteredSessionsSummary = useMemo(() => summarizeSessions(sessions), [sessions]);
  const visibleSessions = useMemo(() => {
    if (focusMode === "high_risk") {
      return sessions.filter((session) => session.failed_runs > 0);
    }
    if (focusMode === "blocked") {
      return sessions.filter((session) => session.blocked_runs > 0);
    }
    if (focusMode === "running") {
      return sessions.filter((session) => session.running_runs > 0);
    }
    return sessions;
  }, [focusMode, sessions]);
  const prioritizedVisibleSessions = useMemo(() => {
    return [...visibleSessions].sort((left, right) => {
      const priorityDiff = sessionPriorityScore(left) - sessionPriorityScore(right);
      if (priorityDiff !== 0) {
        return priorityDiff;
      }
      const leftTs = Date.parse(left.updated_at || left.created_at || "");
      const rightTs = Date.parse(right.updated_at || right.created_at || "");
      if (!Number.isNaN(leftTs) || !Number.isNaN(rightTs)) {
        return (Number.isNaN(rightTs) ? 0 : rightTs) - (Number.isNaN(leftTs) ? 0 : leftTs);
      }
      return String(left.pm_session_id).localeCompare(String(right.pm_session_id));
    });
  }, [visibleSessions]);
  const visibleSummary = useMemo(() => summarizeSessions(prioritizedVisibleSessions), [prioritizedVisibleSessions]);
  const visibleSessionCount = prioritizedVisibleSessions.length;
  const focusLabel =
    focusMode === "high_risk"
      ? liveHomeCopy.focusModeLabels.highRisk
      : focusMode === "blocked"
        ? liveHomeCopy.focusModeLabels.blocked
        : focusMode === "running"
          ? liveHomeCopy.focusModeLabels.running
          : liveHomeCopy.focusModeLabels.all;
  const hasAppliedFilters = appliedFilterCount > 0;
  const showFilterEmptyState = sessions.length === 0 && hasAppliedFilters;
  const showFocusEmptyState = visibleSessions.length === 0 && sessions.length > 0 && focusMode !== "all";
  const refreshHealthSummary = useMemo(() => {
    const okCount = Object.values(sectionStatus).filter((status) => status === "ok").length;
    if (okCount === 3 && !errorMessage && alertsStatus === "healthy") {
      return { label: liveHomeCopy.refreshHealth.fullHealthy, badgeVariant: "success" as StatusVariant };
    }
    if (okCount === 0) {
      return { label: liveHomeCopy.refreshHealth.refreshFailed, badgeVariant: "failed" as StatusVariant };
    }
    return { label: liveHomeCopy.refreshHealth.partialDegradation(okCount), badgeVariant: "warning" as StatusVariant };
  }, [alertsStatus, errorMessage, liveHomeCopy.refreshHealth, sectionStatus]);
  const snapshotStatus = useMemo(() => {
    if (refreshHealthSummary.badgeVariant === "failed") {
      return {
        enabled: true,
        label: liveHomeCopy.snapshot.refreshFailed,
      };
    }
    if (refreshHealthSummary.badgeVariant === "warning") {
      return {
        enabled: true,
        label: liveHomeCopy.snapshot.partialDegradation,
      };
    }
    if (liveMode === "paused") {
      return {
        enabled: true,
        label: liveHomeCopy.snapshot.paused,
      };
    }
    return {
      enabled: false,
      label: "",
    };
  }, [liveHomeCopy.snapshot, liveMode, refreshHealthSummary.badgeVariant]);
  const refreshFreshnessSummary = useMemo(() => {
    const source = lastSuccessfulUpdated || lastUpdated;
    if (!source) {
      return liveHomeCopy.freshness.noSuccessfulRefresh;
    }
    const timestamp = Date.parse(source);
    if (Number.isNaN(timestamp)) {
      return liveHomeCopy.freshness.sourceFallback(source);
    }
    const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (diffSeconds < 60) {
      return liveHomeCopy.freshness.lastSuccessfulSeconds(diffSeconds);
    }
    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) {
      return liveHomeCopy.freshness.lastSuccessfulMinutes(diffMinutes);
    }
    const diffHours = Math.floor(diffMinutes / 60);
    return liveHomeCopy.freshness.lastSuccessfulHours(diffHours);
  }, [lastSuccessfulUpdated, lastUpdated, liveHomeCopy.freshness, refreshToken, liveMode]);
  const runQuickAction = useCallback(
    async (actionId: QuickActionId) => {
      if (actionId === "refresh") {
        await refreshNow();
        return;
      }
      if (actionId === "live") {
        setLiveEnabled((prev) => {
          const next = !prev;
          setActionFeedback(next ? liveHomeCopy.actionFeedback.resumedLiveRefresh : liveHomeCopy.actionFeedback.pausedLiveRefresh);
          return next;
        });
        return;
      }
      if (actionId === "export") {
        exportFailedSessions();
        setActionFeedback(liveHomeCopy.actionFeedback.exportedFailedSessions);
        return;
      }
      if (actionId === "copy") {
        await copyCurrentViewLink();
        return;
      }
      if (actionId === "focus-filter") {
        projectInputRef.current?.focus();
        setActionFeedback(liveHomeCopy.actionFeedback.focusedProjectKeyInput);
        return;
      }
      if (actionId === "toggle-drawer") {
        toggleDrawerCollapsed();
        return;
      }
      if (actionId === "toggle-pin") {
        toggleDrawerPinned();
        return;
      }
      if (draftChanged) {
        applyFilters();
        setActionFeedback(liveHomeCopy.actionFeedback.appliedDraftFilters(draftFilterCount));
      } else {
        setActionFeedback(liveHomeCopy.actionFeedback.draftFiltersAlreadyMatch);
      }
    },
    [
      applyFilters,
      copyCurrentViewLink,
      draftChanged,
      draftFilterCount,
      exportFailedSessions,
      liveHomeCopy.actionFeedback,
      refreshNow,
      toggleDrawerCollapsed,
      toggleDrawerPinned,
    ],
  );

  const showGlobalEmptyState = filteredSessionsSummary.total === 0 && !hasAppliedFilters && !errorMessage;
  const {
    quickActionItems,
    drawerLiveBadgeVariant,
    contextHealthItems,
    sectionStatusItems,
    drawerPromptItems,
    priorityLanes,
    focusOptionsForDrawer,
  } = buildHomeViewModel({
    isRefreshing,
    liveEnabled,
    drawerCollapsed,
    drawerPinned,
    alertsStatus,
    liveMode,
    intervalMs: intervalRef.current,
    focusLabel,
    visibleSessionCount,
    hasAppliedFilters,
    appliedFilterCount,
    sectionStatus,
    filteredSessionsSummary,
    alertsSeveritySummary,
    draftChanged,
    draftFilterCount,
    errorMessage,
    errorMetaLabel: errorMeta.label,
    liveStatusText,
    refreshFreshnessSummary,
    showFilterEmptyState,
    showFocusEmptyState,
    showGlobalEmptyState,
    onRunQuickAction: (id) => {
      void runQuickAction(id);
    },
    sectionStatusText: {
      overview: (statusLabel) => `${commandTowerCopy.sectionLabels.overview} ${statusLabel}`,
      sessions: (statusLabel) => `${commandTowerCopy.sectionLabels.sessions} ${statusLabel}`,
      alerts: (statusLabel) => `${commandTowerCopy.sectionLabels.alerts} ${statusLabel}`,
    },
    sectionStatusLabel,
    sectionStatusBadgeVariant,
    homeLiveBadgeText,
    homeLiveBadgeVariant,
    alertsBadgeVariant,
    commandTowerCopy,
    liveHomeCopy,
  });

  const refreshHealthSummaryForLayout = useMemo(
    () => ({
      label: refreshHealthSummary.label,
      badgeVariant: refreshHealthSummary.badgeVariant,
    }),
    [refreshHealthSummary],
  );

  return (
    <CommandTowerHomeLayout
      drawerCollapsed={drawerCollapsed}
      liveMode={liveMode}
      alertsStatus={alertsStatus}
      refreshHealthSummary={refreshHealthSummaryForLayout}
      snapshotStatus={snapshotStatus}
      toggleDrawerCollapsed={toggleDrawerCollapsed}
      liveStatusText={liveStatusText}
      intervalMs={intervalRef.current}
      actionFeedback={actionFeedback}
      priorityLanes={priorityLanes}
      showGlobalEmptyState={showGlobalEmptyState}
      showFilterEmptyState={showFilterEmptyState}
      showFocusEmptyState={showFocusEmptyState}
      resetFilters={resetFilters}
      setFocusMode={handleFocusModeChange}
      toggleHighRiskFocus={toggleHighRiskFocus}
      errorMessage={errorMessage}
      errorMetaLabel={errorMeta.label}
      visibleSessionCount={visibleSessionCount}
      totalSessionCount={filteredSessionsSummary.total}
      visibleSummary={visibleSummary}
      focusLabel={focusLabel}
      visibleSessions={prioritizedVisibleSessions}
      SessionBoardComponent={SessionBoardComponent}
      DrawerComponent={DrawerComponent}
      drawerLiveBadgeVariant={drawerLiveBadgeVariant}
      homeLiveBadgeText={homeLiveBadgeText}
      homeLiveBadgeVariant={homeLiveBadgeVariant}
      alertsBadgeVariant={(status) => alertsBadgeVariant(status as CommandTowerAlertsPayload["status"])}
      quickActionItems={quickActionItems}
      contextHealthItems={contextHealthItems}
      sectionStatusItems={sectionStatusItems}
      drawerPromptItems={drawerPromptItems}
      overview={overview}
      alerts={alerts}
      criticalAlerts={alertsSeveritySummary.critical}
      draftChanged={draftChanged}
      draftStatuses={draftStatuses}
      draftProjectKey={draftProjectKey}
      draftSort={draftSort}
      statusOptions={STATUS_OPTIONS}
      sortOptions={SORT_OPTIONS}
      focusOptionsForDrawer={focusOptionsForDrawer}
      focusMode={focusMode}
      appliedFilterCount={appliedFilterCount}
      projectInputRef={projectInputRef}
      toggleDraftStatus={toggleDraftStatus}
      setDraftProjectKey={setDraftProjectKey}
      setDraftSort={setDraftSort}
      handleFilterKeyDown={handleFilterKeyDown}
      applyFilters={applyFilters}
      onRunQuickAction={(id) => {
        void runQuickAction(id);
      }}
      commandTowerCopy={commandTowerCopy}
      liveHomeCopy={liveHomeCopy}
    />
  );
}
