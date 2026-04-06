"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import {
  fetchPmSession,
  postPmSessionMessage,
} from "../../lib/api";
import type {
  EventRecord,
  PmSessionConversationGraphPayload,
  PmSessionDetailPayload,
  PmSessionMetricsPayload,
} from "../../lib/types";
import CommandTowerSessionDrawer from "./CommandTowerSessionDrawer";
import CommandTowerSessionPanels from "./CommandTowerSessionPanels";
import { useCommandTowerSessionLiveSync } from "./hooks/useCommandTowerSessionLiveSync";
import { useDrawerPreferences } from "./hooks/useDrawerPreferences";
import {
  REQUEST_TIMEOUT_MS,
  classifyError,
  errorKindLabel,
  extractErrorMessage,
  sessionLiveBadgeText,
} from "./sessionLiveHelpers";
import { Button } from "../ui/button";
import { Card } from "../ui/card";

const SESSION_MAIN_TAB_ORDER: SessionMainTab[] = ["runs", "graph", "timeline"];
const SESSION_DRAWER_COLLAPSED_KEY = "cortexpilot.commandTower.session.drawerCollapsed";
const SESSION_DRAWER_PINNED_KEY = "cortexpilot.commandTower.session.drawerPinned";
type CommandTowerSessionLiveProps = { pmSessionId: string; initialDetail: PmSessionDetailPayload; initialEvents: EventRecord[]; initialGraph: PmSessionConversationGraphPayload; initialMetrics: PmSessionMetricsPayload };
type SessionMainTab = "runs" | "graph" | "timeline";
type RunDetailViewState = "idle" | "loading" | "ready" | "empty" | "error";
export { classifyError, errorKindLabel, eventFingerprint, eventName, eventTsValue, extractErrorMessage, isTerminalStatus, lastEventTs, mergeEventWindow, sessionLiveBadgeText, sessionLiveBadgeVariant } from "./sessionLiveHelpers";
function resolveCandidateRunId(detailPayload: PmSessionDetailPayload): string {
  const sessionLatestRunId = String(detailPayload.session.latest_run_id || "").trim();
  if (sessionLatestRunId) {
    return sessionLatestRunId;
  }
  return String(detailPayload.runs[0]?.run_id || "").trim();
}
export default function CommandTowerSessionLive({
  pmSessionId,
  initialDetail,
  initialEvents,
  initialGraph,
  initialMetrics,
}: CommandTowerSessionLiveProps) {
  const [drawerActionFeedback, setDrawerActionFeedback] = useState(
    "Shortcuts: Alt+L toggles live mode, Alt+R refreshes, Alt+M focuses the message input, Alt+D toggles the drawer, Alt+P pins the drawer.",
  );
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [messageDraft, setMessageDraft] = useState("");
  const [messageSending, setMessageSending] = useState(false);
  const [messageError, setMessageError] = useState("");
  const [messageOk, setMessageOk] = useState("");
  const [activeMainTab, setActiveMainTab] = useState<SessionMainTab>("runs");
  const [sessionTabFeedback, setSessionTabFeedback] = useState("");
  const [runDetailViewState, setRunDetailViewState] = useState<RunDetailViewState>("idle");
  const [runDetailTargetRunId, setRunDetailTargetRunId] = useState("");
  const [runDetailStateMessage, setRunDetailStateMessage] = useState("");
  const messageInputRef = useRef<HTMLTextAreaElement | null>(null);
  const sessionMainTabRefs = useRef<Record<SessionMainTab, HTMLButtonElement | null>>({
    runs: null,
    graph: null,
    timeline: null,
  });
  const {
    drawerCollapsed,
    setDrawerCollapsed,
    drawerPinned,
    setDrawerPinned,
  } = useDrawerPreferences({
    collapsedStorageKey: SESSION_DRAWER_COLLAPSED_KEY,
    pinnedStorageKey: SESSION_DRAWER_PINNED_KEY,
  });
  const {
    detail: syncedDetail,
    setDetail: setSyncedDetail,
    events,
    graph,
    metrics,
    liveMode,
    transport,
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
  } = useCommandTowerSessionLiveSync({
    pmSessionId,
    initialDetail,
    initialEvents,
    initialGraph,
    initialMetrics,
    liveEnabled,
    onDrawerFeedback: setDrawerActionFeedback,
  });
  const detail = syncedDetail;
  const latestRunId = String(detail.session.latest_run_id || "").trim();
  const sessionStatus = String(detail.session.status || "-");
  const contextRunCount = detail.runs.length;
  const contextBlockedRuns = detail.runs.filter((run) => Boolean(run.blocked)).length;
  const contextLastEventTs = eventCursorRef.current || "-";
  const contextLatestRun = latestRunId || detail.runs[0]?.run_id || "";
  const domIdSeed = useMemo(() => String(pmSessionId || "session").replace(/[^a-zA-Z0-9_-]/g, "-"), [pmSessionId]);
  const sessionMainRegionId = `session-main-region-${domIdSeed}`;
  const sessionMainTablistId = `session-main-tablist-${domIdSeed}`;
  const sessionMetricsRegionId = `session-metrics-region-${domIdSeed}`;
  const sessionRunsRegionId = `session-runs-region-${domIdSeed}`;
  const sessionRunsTabId = `session-runs-tab-${domIdSeed}`;
  const sessionGraphRegionId = `session-graph-region-${domIdSeed}`;
  const sessionGraphTabId = `session-graph-tab-${domIdSeed}`;
  const sessionTimelineRegionId = `session-timeline-region-${domIdSeed}`;
  const sessionTimelineTabId = `session-timeline-tab-${domIdSeed}`;
  const sessionMainTabStateId = `session-main-tab-state-${domIdSeed}`;
  const sessionDrawerStatusId = `session-live-status-${domIdSeed}`;
  const sessionDrawerFeedbackId = `session-drawer-feedback-${domIdSeed}`;
  const sessionMessageInputId = `pm-session-message-input-${domIdSeed}`;
  const sessionMessageHintId = `pm-session-message-hint-${domIdSeed}`;
  const sessionRunDetailStateId = `session-run-detail-state-${domIdSeed}`;
  const activeMainTabLabel =
    activeMainTab === "runs" ? "Runs" : activeMainTab === "graph" ? "Role flow" : "Timeline";
  const liveModeLabel = sessionLiveBadgeText(liveMode);
  const transportLabel = transport === "sse" ? "SSE live stream" : "Polling fallback";
  const transportDescription = transport === "sse" ? "Low-latency streaming path" : "Automatic degraded fallback path";
  const chatStreamRuntime = "openEventsStream";
  const liveAnnouncement = `Live state ${liveModeLabel}, current transport ${transportLabel}, refresh interval ${intervalRef.current} ms.`;
  const focusSessionMainTab = (tab: SessionMainTab) => {
    sessionMainTabRefs.current[tab]?.focus();
  };
  const labelForMainTab = (tab: SessionMainTab): string => {
    if (tab === "runs") return "Runs";
    if (tab === "graph") return "Role flow";
    return "Timeline";
  };
  const moveSessionMainTab = (target: SessionMainTab) => {
    setActiveMainTab(target);
    setSessionTabFeedback(`Switched to ${labelForMainTab(target)}.`);
    focusSessionMainTab(target);
  };
  const handleSessionMainTabClick = (target: SessionMainTab) => {
    if (activeMainTab === target) {
      setSessionTabFeedback(`Already showing ${labelForMainTab(target)}. Keep reviewing the latest content.`);
      return;
    }
    setActiveMainTab(target);
    setSessionTabFeedback(`Switched to ${labelForMainTab(target)}.`);
  };
  const handleSessionMainTabKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, currentTab: SessionMainTab) => {
    const key = event.key;
    if (key !== "ArrowLeft" && key !== "ArrowRight" && key !== "Home" && key !== "End") {
      return;
    }
    event.preventDefault();
    if (key === "Home") {
      moveSessionMainTab(SESSION_MAIN_TAB_ORDER[0]);
      return;
    }
    if (key === "End") {
      moveSessionMainTab(SESSION_MAIN_TAB_ORDER[SESSION_MAIN_TAB_ORDER.length - 1]);
      return;
    }
    const currentIndex = SESSION_MAIN_TAB_ORDER.indexOf(currentTab);
    if (currentIndex < 0) {
      return;
    }
    const delta = key === "ArrowRight" ? 1 : -1;
    const nextIndex = (currentIndex + delta + SESSION_MAIN_TAB_ORDER.length) % SESSION_MAIN_TAB_ORDER.length;
    moveSessionMainTab(SESSION_MAIN_TAB_ORDER[nextIndex]);
  };
  const handleToggleLive = () => {
    const nextLiveEnabled = !liveEnabled;
    setLiveEnabled(nextLiveEnabled);
    setDrawerActionFeedback(nextLiveEnabled ? "Live refresh resumed." : "Live refresh paused.");
  };
  const focusMessageComposer = () => {
    messageInputRef.current?.focus();
    setDrawerActionFeedback("Focused the PM message input. Type now and press Enter to send.");
  };
  const handleManualRefresh = async () => {
    setDrawerActionFeedback("Refreshing session context manually...");
    try {
      await refreshActionRef.current();
      setDrawerActionFeedback("Manual refresh finished.");
    } catch (error) {
      const message = extractErrorMessage(error);
      setErrorMessage(message);
      setErrorKind(classifyError(message));
      setDrawerActionFeedback(`Manual refresh failed: ${message}`);
    }
  };
  const handleOpenRunDetail = async () => {
    setRunDetailViewState("loading");
    setRunDetailStateMessage("");
    setRunDetailTargetRunId("");
    try {
      const latestDetail = await fetchPmSession(pmSessionId, { timeoutMs: REQUEST_TIMEOUT_MS });
      setSyncedDetail(latestDetail);
      setLastUpdated(latestDetail.session.updated_at || new Date().toISOString());
      const nextRunId = resolveCandidateRunId(latestDetail);
      if (!nextRunId) {
        setRunDetailViewState("empty");
        setRunDetailStateMessage("There is no run detail available for this session yet.");
        return;
      }
      setRunDetailTargetRunId(nextRunId);
      setRunDetailViewState("ready");
      setRunDetailStateMessage(`Located run ${nextRunId}.`);
    } catch (error) {
      const fallbackRunId = resolveCandidateRunId(detail);
      if (fallbackRunId) {
        setRunDetailTargetRunId(fallbackRunId);
        setRunDetailViewState("ready");
        setRunDetailStateMessage(`Session refresh failed. Fell back to the latest run ${fallbackRunId}.`);
        return;
      }
      setRunDetailViewState("error");
      setRunDetailStateMessage(`Failed to load run detail: ${extractErrorMessage(error)}`);
    }
  };
  const handleSendMessage = async () => {
    const normalized = messageDraft.trim();
    if (!normalized) {
      setMessageError("Message cannot be empty");
      setMessageOk("");
      return;
    }
    setMessageSending(true);
    setMessageError("");
    setMessageOk("");
    try {
      await postPmSessionMessage(pmSessionId, {
        message: normalized,
        from_role: "PM",
        to_role: "TECH_LEAD",
        kind: "chat",
      });
      setMessageDraft("");
      setMessageOk("Message sent");
      await refreshAll();
    } catch (error) {
      setMessageError(extractErrorMessage(error));
    } finally {
      setMessageSending(false);
    }
  };
  useEffect(() => {
    setRunDetailViewState("idle");
    setRunDetailTargetRunId("");
    setRunDetailStateMessage("");
    setSessionTabFeedback("");
  }, [pmSessionId]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }
      const key = event.key.toLowerCase();
      const target = event.target as HTMLElement | null;
      const tagName = target?.tagName;
      const inEditable =
        Boolean(target?.isContentEditable) ||
        tagName === "INPUT" ||
        tagName === "TEXTAREA" ||
        tagName === "SELECT";
      if (key === "m") {
        event.preventDefault();
        messageInputRef.current?.focus();
        setDrawerActionFeedback("Focused the PM message input. Type now and press Enter to send.");
        return;
      }
      if (inEditable) {
        return;
      }
      if (key === "l") {
        event.preventDefault();
        setLiveEnabled((previous) => {
          const nextLiveEnabled = !previous;
          setDrawerActionFeedback(nextLiveEnabled ? "Live refresh resumed." : "Live refresh paused.");
          return nextLiveEnabled;
        });
        return;
      }
      if (key === "r") {
        event.preventDefault();
        setDrawerActionFeedback("Refreshing session context manually...");
        void refreshActionRef.current().then(
          () => {
            setDrawerActionFeedback("Manual refresh finished.");
          },
          (error) => {
            const message = extractErrorMessage(error);
            setErrorMessage(message);
            setErrorKind(classifyError(message));
            setDrawerActionFeedback(`Manual refresh failed: ${message}`);
          },
        );
        return;
      }
      if (key === "d") {
        event.preventDefault();
        setDrawerCollapsed((previous) => {
          const next = !previous;
          setDrawerActionFeedback(next ? "Collapsed the right context drawer." : "Expanded the right context drawer.");
          return next;
        });
        return;
      }
      if (key === "p") {
        event.preventDefault();
        setDrawerPinned((previous) => {
          const next = !previous;
          setDrawerActionFeedback(next ? "Pinned the right drawer." : "Unpinned the right drawer.");
          return next;
        });
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, []);
  return (
    <div
      className={`command-tower-layout${drawerCollapsed ? " command-tower-layout--drawer-collapsed" : " command-tower-layout--drawer-expanded"}${drawerPinned ? " command-tower-layout--drawer-pinned" : " command-tower-layout--drawer-unpinned"}`}
      data-drawer-collapsed={drawerCollapsed ? "true" : "false"}
      data-drawer-pinned={drawerPinned ? "true" : "false"}
    >
      <main
        id={sessionMainRegionId}
        className="app-section command-tower-main"
        aria-label="Session main workspace"
        data-testid="ct-session-main-region"
      >
          <section className="app-section" id={sessionMetricsRegionId} aria-label="Session metrics overview">
            <div className="section-header">
              <div>
                <h2>Session {pmSessionId}</h2>
                <p>Review the key progress first and close one operator loop before switching across runs, role flow, and timeline views.</p>
              </div>
            </div>
            <div className="stats-grid">
              <article className="metric-card">
                <p className="metric-label">Runs</p>
                <p className="metric-value">{metrics.run_count}</p>
              </article>
              <article className="metric-card">
                <p className="metric-label">Running</p>
                <p className="metric-value">{metrics.running_runs}</p>
              </article>
              <article className="metric-card">
                <p className="metric-label">Failed</p>
                <p className="metric-value">{metrics.failed_runs}</p>
              </article>
              <article className="metric-card">
                <p className="metric-label">Blocked</p>
                <p className="metric-value">{metrics.blocked_runs}</p>
              </article>
            </div>
            <div className="toolbar toolbar--mt" role="group" aria-label="Session primary actions">
              <Button
                variant="default"
                onClick={() => void handleManualRefresh()}
                aria-label="Refresh latest progress"
                aria-controls={`${sessionMainRegionId} ${sessionDrawerStatusId}`}
                aria-describedby={sessionDrawerFeedbackId}
                aria-keyshortcuts="Alt+R"
                disabled={refreshing}
              >
                {refreshing ? "Refreshing..." : "Refresh progress"}
              </Button>
              <Button
                variant="secondary"
                onClick={handleToggleLive}
                aria-label={liveEnabled ? "Pause auto refresh" : "Resume auto refresh"}
                aria-pressed={liveEnabled}
                aria-controls={`${sessionMainRegionId} ${sessionDrawerStatusId}`}
                aria-describedby={sessionDrawerFeedbackId}
                aria-keyshortcuts="Alt+L"
              >
                {liveEnabled ? "Pause auto refresh" : "Resume auto refresh"}
              </Button>
              <Button
                variant="secondary"
                aria-label="Open run detail"
                onClick={() => void handleOpenRunDetail()}
                disabled={runDetailViewState === "loading"}
                aria-controls={sessionRunDetailStateId}
                data-testid="ct-session-open-run-detail-trigger"
              >
                {runDetailViewState === "loading" ? "Loading..." : "Open run detail"}
              </Button>
            </div>
            <Card
              id={sessionRunDetailStateId}
              className="toolbar toolbar--mt"
              role={runDetailViewState === "error" ? "alert" : "status"}
              aria-live={runDetailViewState === "error" ? "assertive" : "polite"}
              aria-atomic="true"
              aria-busy={runDetailViewState === "loading"}
              data-testid="ct-session-run-detail-state"
              data-state={runDetailViewState}
            >
              <span className="mono" data-testid="ct-session-run-detail-state-label">
                State: {runDetailViewState}
              </span>
              <span className="mono muted" data-testid="ct-session-run-detail-state-message">
                {runDetailStateMessage ||
                  (runDetailViewState === "idle"
                    ? "Click \"Open run detail\" to load the latest run."
                    : runDetailViewState === "loading"
                      ? "Loading the latest run detail..."
                      : "Continue with the next operator action.")}
              </span>
              {runDetailViewState === "ready" && runDetailTargetRunId ? (
                <Button asChild variant="secondary">
                  <Link
                    href={`/runs/${encodeURIComponent(runDetailTargetRunId)}`}
                    data-testid="ct-session-open-run-detail-ready-link"
                    title={runDetailTargetRunId}
                    data-run-id={runDetailTargetRunId}
                  >
                    Open run detail
                  </Link>
                </Button>
              ) : null}
              {runDetailViewState === "empty" ? (
                <Button asChild variant="ghost">
                  <Link href="/pm" data-testid="ct-session-open-run-detail-next-action">
                    Go to the PM session and trigger /run
                  </Link>
                </Button>
              ) : null}
              {runDetailViewState === "error" ? (
                <Button
                  variant="ghost"
                  onClick={() => void handleOpenRunDetail()}
                  data-testid="ct-session-open-run-detail-retry"
                >
                  Retry
                </Button>
              ) : null}
            </Card>
            <div className="toolbar toolbar--mt" role="group" aria-label="Session view switcher">
              <div
                className="run-detail-tablist"
                role="tablist"
                aria-label="Session main view switcher"
                id={sessionMainTablistId}
                aria-describedby={sessionMainTabStateId}
                data-testid="ct-session-tablist"
              >
                <Button
                  variant="ghost"
                  role="tab"
                  id={sessionRunsTabId}
                  className={activeMainTab === "runs" ? "ct-session-main-tab is-active" : "ct-session-main-tab"}
                  aria-selected={activeMainTab === "runs"}
                  aria-controls={sessionRunsRegionId}
                  tabIndex={activeMainTab === "runs" ? 0 : -1}
                  data-testid="ct-session-tab-runs"
                  ref={(node) => {
                    sessionMainTabRefs.current.runs = node;
                  }}
                  onKeyDown={(event) => handleSessionMainTabKeyDown(event, "runs")}
                  onClick={() => handleSessionMainTabClick("runs")}
                >
                  Runs
                </Button>
                <Button
                  variant="ghost"
                  role="tab"
                  id={sessionGraphTabId}
                  className={activeMainTab === "graph" ? "ct-session-main-tab is-active" : "ct-session-main-tab"}
                  aria-selected={activeMainTab === "graph"}
                  aria-controls={sessionGraphRegionId}
                  tabIndex={activeMainTab === "graph" ? 0 : -1}
                  data-testid="ct-session-tab-graph"
                  ref={(node) => {
                    sessionMainTabRefs.current.graph = node;
                  }}
                  onKeyDown={(event) => handleSessionMainTabKeyDown(event, "graph")}
                  onClick={() => handleSessionMainTabClick("graph")}
                >
                  Role flow
                </Button>
                <Button
                  variant="ghost"
                  role="tab"
                  id={sessionTimelineTabId}
                  className={activeMainTab === "timeline" ? "ct-session-main-tab is-active" : "ct-session-main-tab"}
                  aria-selected={activeMainTab === "timeline"}
                  aria-controls={sessionTimelineRegionId}
                  tabIndex={activeMainTab === "timeline" ? 0 : -1}
                  data-testid="ct-session-tab-timeline"
                  ref={(node) => {
                    sessionMainTabRefs.current.timeline = node;
                  }}
                  onKeyDown={(event) => handleSessionMainTabKeyDown(event, "timeline")}
                  onClick={() => handleSessionMainTabClick("timeline")}
                >
                  Timeline
                </Button>
              </div>
              <p id={sessionMainTabStateId} className="mono muted" role="status" aria-live="polite" data-testid="ct-session-tab-active-state">
                Current main view: {activeMainTabLabel}
                {sessionTabFeedback ? ` - ${sessionTabFeedback}` : ""}
              </p>
            </div>
            {refreshing ? (
              <p className="mono muted" role="status" aria-live="polite">
                Refreshing session context...
              </p>
            ) : null}
            {drawerCollapsed && errorMessage ? (
              <p className="run-detail-live-error mono" role="alert" aria-live="assertive">
                Session live state degraded: {errorMessage}
              </p>
            ) : null}
            {events.length === 0 ? (
              <p className="mono muted" role="status" aria-live="polite">
                No event timeline yet. Trigger a run and the key nodes and role flow will appear automatically.
              </p>
            ) : null}
            <p className="mono muted" role="status" aria-live="polite">
              The chat input supports Shift+Enter for newlines and Enter for direct send.
            </p>
            <p className="sr-only" data-chat-stream-runtime={chatStreamRuntime}>
              chat-stream-runtime: {chatStreamRuntime}
            </p>
            {drawerCollapsed && messageError ? (
              <p className="run-detail-live-error mono" role="alert" aria-live="assertive">
                Message send failed: {messageError}
              </p>
            ) : null}
          </section>
          <CommandTowerSessionPanels
            detail={detail}
            events={events}
            graph={graph}
            activeMainTab={activeMainTab}
            sessionRunsRegionId={sessionRunsRegionId}
            sessionRunsTabId={sessionRunsTabId}
            sessionGraphRegionId={sessionGraphRegionId}
            sessionGraphTabId={sessionGraphTabId}
            sessionTimelineRegionId={sessionTimelineRegionId}
            sessionTimelineTabId={sessionTimelineTabId}
          />
        </main>
      <CommandTowerSessionDrawer
        drawerCollapsed={drawerCollapsed}
        drawerPinned={drawerPinned}
        sessionDrawerFeedbackId={sessionDrawerFeedbackId}
        sessionDrawerStatusId={sessionDrawerStatusId}
        sessionMetricsRegionId={sessionMetricsRegionId}
        sessionRunsRegionId={sessionRunsRegionId}
        sessionTimelineRegionId={sessionTimelineRegionId}
        sessionMainRegionId={sessionMainRegionId}
        sessionMessageInputId={sessionMessageInputId}
        sessionMessageHintId={sessionMessageHintId}
        liveMode={liveMode}
        liveEnabled={liveEnabled}
        handleToggleLive={handleToggleLive}
        handleManualRefresh={handleManualRefresh}
        refreshing={refreshing}
        focusMessageComposer={focusMessageComposer}
        setDrawerCollapsed={setDrawerCollapsed}
        setDrawerPinned={setDrawerPinned}
        drawerActionFeedback={drawerActionFeedback}
        transportLabel={transportLabel}
        transportDescription={transportDescription}
        refreshIntervalMs={intervalRef.current}
        sseFailures={sseFailuresRef.current}
        lastUpdated={lastUpdated}
        liveModeLabel={liveModeLabel}
        liveAnnouncement={liveAnnouncement}
        errorMessage={errorMessage}
        errorKind={errorKind}
        sessionStatus={sessionStatus}
        contextRunCount={contextRunCount}
        contextBlockedRuns={contextBlockedRuns}
        contextLastEventTs={contextLastEventTs}
        contextLatestRun={contextLatestRun}
        messageInputRef={messageInputRef}
        messageDraft={messageDraft}
        setMessageDraft={setMessageDraft}
        handleSendMessage={handleSendMessage}
        messageSending={messageSending}
        messageOk={messageOk}
        messageError={messageError}
        detail={detail}
      />
    </div>
  );
}
