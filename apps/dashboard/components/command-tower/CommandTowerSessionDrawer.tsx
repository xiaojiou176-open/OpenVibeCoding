import Link from "next/link";
import type { RefObject } from "react";
import { Badge, type BadgeVariant } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Textarea } from "../ui/input";

import type { PmSessionDetailPayload } from "../../lib/types";
import { SSE_FAILURE_LIMIT, errorKindLabel, sessionLiveBadgeText, type LiveErrorKind, type LiveMode } from "./sessionLiveHelpers";

type Props = {
  drawerCollapsed: boolean;
  drawerPinned: boolean;
  sessionDrawerFeedbackId: string;
  sessionDrawerStatusId: string;
  sessionMetricsRegionId: string;
  sessionRunsRegionId: string;
  sessionTimelineRegionId: string;
  sessionMainRegionId: string;
  sessionMessageInputId: string;
  sessionMessageHintId: string;
  liveMode: LiveMode;
  liveEnabled: boolean;
  handleToggleLive: () => void;
  handleManualRefresh: () => Promise<void>;
  refreshing: boolean;
  focusMessageComposer: () => void;
  setDrawerCollapsed: (value: boolean | ((previous: boolean) => boolean)) => void;
  setDrawerPinned: (value: boolean | ((previous: boolean) => boolean)) => void;
  drawerActionFeedback: string;
  transportLabel: string;
  transportDescription: string;
  refreshIntervalMs: number;
  sseFailures: number;
  lastUpdated: string;
  liveModeLabel: string;
  liveAnnouncement: string;
  errorMessage: string;
  errorKind: LiveErrorKind;
  sessionStatus: string;
  contextRunCount: number;
  contextBlockedRuns: number;
  contextLastEventTs: string;
  contextLatestRun: string;
  messageInputRef: RefObject<HTMLTextAreaElement | null>;
  messageDraft: string;
  setMessageDraft: (value: string) => void;
  handleSendMessage: () => Promise<void>;
  messageSending: boolean;
  messageOk: string;
  messageError: string;
  detail: PmSessionDetailPayload;
};

function sessionLiveBadgeVariant(mode: LiveMode): BadgeVariant {
  if (mode === "backoff") {
    return "failed";
  }
  return "running";
}

export default function CommandTowerSessionDrawer(props: Props) {
  const collapseLabel = props.drawerCollapsed ? "Expand drawer" : "Collapse drawer";
  const pinLabel = props.drawerPinned ? "Unpin drawer" : "Pin drawer";
  const drawerLayoutState = `Drawer layout: ${props.drawerCollapsed ? "collapsed" : "expanded"} - ${props.drawerPinned ? "pinned" : "floating"}`;
  return (
    <aside
      className={`app-section command-tower-drawer${props.drawerCollapsed ? " command-tower-drawer--collapsed" : ""}${props.drawerPinned ? "" : " command-tower-drawer--unpinned"}`}
      aria-label="Context operations drawer"
      aria-labelledby="session-context-drawer-title"
      aria-describedby={`session-context-drawer-desc ${props.sessionDrawerFeedbackId}`}
      data-testid="ct-session-context-drawer"
      data-drawer-collapsed={props.drawerCollapsed ? "true" : "false"}
      data-drawer-pinned={props.drawerPinned ? "true" : "false"}
    >
      <Card className="ct-drawer-persistent">
        <h3 id="session-context-drawer-title">Context operations drawer</h3>
        <p id="session-context-drawer-desc" className="muted">
          A persistent right-side drawer that gathers live controls, context summaries, and quick jumps.
        </p>
        <nav aria-label="Session quick anchors" className="session-drawer-anchor-nav">
          <a href={`#${props.sessionMetricsRegionId}`} className="run-link">Jump to metrics</a>
          <a href={`#${props.sessionRunsRegionId}`} className="run-link">Jump to runs</a>
          <a href={`#${props.sessionTimelineRegionId}`} className="run-link">Jump to timeline</a>
        </nav>
        <div className="toolbar toolbar--mt" role="group" aria-label="Live controls">
          <Badge variant={sessionLiveBadgeVariant(props.liveMode)}>{sessionLiveBadgeText(props.liveMode)}</Badge>
          <Button
            variant="secondary"
            onClick={props.handleToggleLive}
            aria-label={props.liveEnabled ? "Pause live refresh" : "Resume live refresh"}
            aria-pressed={props.liveEnabled}
            aria-controls={`${props.sessionMainRegionId} ${props.sessionDrawerStatusId}`}
            aria-describedby={props.sessionDrawerFeedbackId}
            aria-keyshortcuts="Alt+L"
          >
            {props.liveEnabled ? "Pause live refresh" : "Resume live refresh"}
          </Button>
          <Button
            variant="secondary"
            onClick={() => void props.handleManualRefresh()}
            aria-label="Manual refresh"
            aria-controls={`${props.sessionMainRegionId} ${props.sessionDrawerStatusId}`}
            aria-describedby={props.sessionDrawerFeedbackId}
            aria-keyshortcuts="Alt+R"
            disabled={props.refreshing}
          >
            {props.refreshing ? "Refreshing..." : "Refresh now"}
          </Button>
          <Button
            variant="secondary"
            onClick={props.focusMessageComposer}
            aria-label="Focus PM message input"
            aria-controls={props.sessionMessageInputId}
            aria-describedby={props.sessionMessageHintId}
            aria-keyshortcuts="Alt+M"
          >
            Focus message input
          </Button>
        </div>
        <div className="toolbar toolbar--mt" role="group" aria-label="Drawer layout controls">
          <Button
            variant="secondary"
            onClick={() => props.setDrawerCollapsed((previous) => !previous)}
            aria-pressed={props.drawerCollapsed}
            aria-describedby={props.sessionDrawerFeedbackId}
            aria-keyshortcuts="Alt+D"
            aria-label={collapseLabel}
          >
            {collapseLabel}
          </Button>
          <Button
            variant="secondary"
            onClick={() => props.setDrawerPinned((previous) => !previous)}
            aria-pressed={props.drawerPinned}
            aria-describedby={props.sessionDrawerFeedbackId}
            aria-keyshortcuts="Alt+P"
            aria-label={pinLabel}
          >
            {pinLabel}
          </Button>
        </div>
        <p className="mono muted" role="status" aria-live="polite" data-testid="ct-session-drawer-layout-state">
          {drawerLayoutState}
        </p>
        <p id={props.sessionDrawerFeedbackId} className="mono muted drawer-feedback" role="status" aria-live="polite" aria-atomic="true">
          {props.drawerActionFeedback}
        </p>
      </Card>

        {props.drawerCollapsed ? null : (
        <>
          <Card id={props.sessionDrawerStatusId} className="run-detail-live-panel" role="status" aria-live="polite" aria-atomic="true">
            <h3>Live status</h3>
            <div className="run-detail-live-head">
              <span className="mono">Transport: {props.transportLabel}</span>
              <span className="mono">Strategy: {props.transportDescription}</span>
              <span className="mono">Refresh interval (ms): {props.refreshIntervalMs}</span>
              <span className="mono">SSE failure count: {props.sseFailures}</span>
              <span className="mono">Last updated: {props.lastUpdated || "-"}</span>
            </div>
            <p className="mono muted drawer-status-note">
              Current state: {props.liveModeLabel}. After {SSE_FAILURE_LIMIT} consecutive SSE failures, the drawer falls back to polling automatically.
            </p>
            <p className="sr-only">{props.liveAnnouncement}</p>
            {props.errorMessage ? (
              <p className="run-detail-live-error mono" role="alert" aria-live="assertive">
                Error type: {errorKindLabel(props.errorKind)} | Details: {props.errorMessage}
              </p>
            ) : null}
          </Card>

          <Card>
            <h3>Key context</h3>
            <dl className="grid session-context-grid">
              <div className="session-context-row"><dt className="mono muted">Session status</dt><dd className="mono">{props.sessionStatus}</dd></div>
              <div className="session-context-row"><dt className="mono muted">Linked runs</dt><dd className="mono">{props.contextRunCount}</dd></div>
              <div className="session-context-row"><dt className="mono muted">Blocked runs</dt><dd className="mono">{props.contextBlockedRuns}</dd></div>
              <div className="session-context-row"><dt className="mono muted">Latest event</dt><dd className="mono">{props.contextLastEventTs}</dd></div>
            </dl>
            {props.contextLatestRun ? (
              <div className="toolbar toolbar--mt">
                <Button asChild>
                  <Link
                    href={`/runs/${encodeURIComponent(props.contextLatestRun)}`}
                    aria-label="Jump to latest run"
                  >
                    Jump to latest run
                  </Link>
                </Button>
              </div>
            ) : null}
          </Card>

          <Card>
            <h3>PM session chat</h3>
            <p className="muted">Append a PM message to the current session and drive the TL/Worker collaboration chain forward.</p>
            <Textarea
              variant="unstyled"
              ref={props.messageInputRef}
              id={props.sessionMessageInputId}
              value={props.messageDraft}
              onChange={(event) => props.setMessageDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  void props.handleSendMessage();
                }
              }}
              rows={3}
              className="session-message-input"
              placeholder="Type a message and press Enter to send (Shift+Enter inserts a newline)"
              disabled={props.messageSending}
              aria-label="PM session message input"
              aria-describedby={`${props.sessionMessageHintId} ${props.sessionDrawerFeedbackId}`}
            />
            <p id={props.sessionMessageHintId} className="mono muted session-message-hint">
              Press Enter to send, Shift+Enter for a newline, and Alt+M to focus the input quickly.
            </p>
            <div className="toolbar toolbar--mt">
              <Button
                variant="secondary"
                onClick={() => void props.handleSendMessage()}
                disabled={props.messageSending}
                title={props.messageSending ? "Sending message. Please wait." : "Send the PM message to the current session"}
              >
                {props.messageSending ? "Sending..." : "Send to session"}
              </Button>
              {props.messageOk ? <span className="mono" role="status" aria-live="polite">{props.messageOk}</span> : null}
              {props.messageError ? <span className="mono run-detail-live-error" role="alert" aria-live="assertive">{props.messageError}</span> : null}
            </div>
          </Card>

          <Card>
            <h3>Session runs</h3>
            <p className="muted">Jump into run detail pages quickly and locate the current execution context.</p>
            {props.detail.runs.length ? (
              <nav aria-label="Session run quick links">
                <ul className="session-run-list">
                  {props.detail.runs.slice(0, 5).map((run) => (
                    <li key={`drawer-${run.run_id}`}>
                      <Link href={`/runs/${encodeURIComponent(run.run_id)}`} className="run-link" aria-label={`Jump to run ${run.run_id}`}>
                        {run.run_id}
                      </Link>
                    </li>
                  ))}
                </ul>
              </nav>
            ) : (
              <p className="mono muted">No runs available to jump to</p>
            )}
          </Card>
        </>
      )}
    </aside>
  );
}
