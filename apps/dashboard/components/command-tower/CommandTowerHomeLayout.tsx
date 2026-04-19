import type { ComponentType, KeyboardEvent as ReactKeyboardEvent, RefObject } from "react";

import type { UiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import type { CommandTowerAlert, CommandTowerOverviewPayload, PmSessionStatus, PmSessionSummary } from "../../lib/types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import Link from "next/link";
import {
  statusLabelFromCanonical,
  toCanonicalStatusFuzzy,
  type StatusVariant,
} from "@openvibecoding/frontend-shared/statusPresentation";

type SortMode = "updated_desc" | "created_desc" | "failed_desc" | "blocked_desc";
type FocusMode = "all" | "high_risk" | "blocked" | "running";

type LayoutProps = {
  locale?: "en" | "zh-CN";
  drawerCollapsed: boolean;
  liveMode: "running" | "backoff" | "paused";
  alertsStatus: string;
  refreshHealthSummary: { label: string; badgeVariant: StatusVariant };
  snapshotStatus: { enabled: boolean; label: string };
  toggleDrawerCollapsed: () => void;
  liveStatusText: string;
  intervalMs: number;
  actionFeedback: string;
  priorityLanes: Array<{ lane: string; title: string; summary: string; badgeVariant: StatusVariant; badgeText: string }>;
  showGlobalEmptyState: boolean;
  showFilterEmptyState: boolean;
  showFocusEmptyState: boolean;
  resetFilters: () => void;
  setFocusMode: (value: FocusMode) => void;
  toggleHighRiskFocus: () => void;
  errorMessage: string;
  errorMetaLabel: string;
  visibleSessionCount: number;
  totalSessionCount: number;
  visibleSummary: { total: number; failed: number; blocked: number; running: number };
  focusLabel: string;
  visibleSessions: PmSessionSummary[];
  SessionBoardComponent: ComponentType<{
    sessions: PmSessionSummary[];
    snapshotStatus?: { enabled: boolean; label: string };
    locale?: "en" | "zh-CN";
  }>;
  DrawerComponent: ComponentType<any>;
  drawerLiveBadgeVariant: StatusVariant;
  homeLiveBadgeText: (mode: "running" | "backoff" | "paused") => string;
  homeLiveBadgeVariant: (mode: "running" | "backoff" | "paused") => StatusVariant;
  alertsBadgeVariant: (status: string) => StatusVariant;
  quickActionItems: Array<{
    id: string;
    shortcut: string;
    description: string;
    actionLabel: string;
    onAction: () => void;
    disabled?: boolean;
  }>;
  contextHealthItems: Array<{ id: string; label: string; value: string; badgeVariant: StatusVariant; badgeLabel: string }>;
  sectionStatusItems: Array<{ id: string; text: string; badgeVariant: StatusVariant }>;
  drawerPromptItems: string[];
  overview: CommandTowerOverviewPayload;
  alerts: CommandTowerAlert[];
  criticalAlerts: number;
  draftChanged: boolean;
  draftStatuses: PmSessionStatus[];
  draftProjectKey: string;
  draftSort: SortMode;
  statusOptions: PmSessionStatus[];
  sortOptions: Array<{ value: SortMode; label: string }>;
  focusOptionsForDrawer: Array<{ value: FocusMode; label: string; count: number }>;
  focusMode: FocusMode;
  appliedFilterCount: number;
  projectInputRef: RefObject<HTMLInputElement | null>;
  toggleDraftStatus: (status: PmSessionStatus) => void;
  setDraftProjectKey: (value: string) => void;
  setDraftSort: (value: SortMode) => void;
  handleFilterKeyDown: (event: ReactKeyboardEvent<HTMLInputElement>) => void;
  applyFilters: () => void;
  onRunQuickAction?: (id: "refresh" | "live" | "export" | "copy" | "focus-filter" | "apply-filter" | "toggle-drawer" | "toggle-pin") => void;
  commandTowerCopy: UiCopy["desktop"]["commandTower"];
  liveHomeCopy: UiCopy["dashboard"]["commandTowerPage"]["liveHome"];
};

function buildHomeLayoutLiveAnnouncement({
  locale,
  hasRefreshIssue,
  refreshHealthLabel,
  liveStatusText,
  intervalMs,
  alertsStatusLabel,
}: {
  locale: "en" | "zh-CN";
  hasRefreshIssue: boolean;
  refreshHealthLabel: string;
  liveStatusText: string;
  intervalMs: number;
  alertsStatusLabel: string;
}): string {
  if (locale === "zh-CN") {
    return `${hasRefreshIssue ? `刷新状态 ${refreshHealthLabel}` : liveStatusText}。刷新间隔 ${intervalMs} 毫秒。当前 SLO 状态 ${alertsStatusLabel}。详细筛选在右侧抽屉中。`;
  }

  return `${hasRefreshIssue ? `Refresh state ${refreshHealthLabel}` : liveStatusText}. Refresh interval ${intervalMs} ms. Current SLO state ${alertsStatusLabel}. Detailed filters are in the right drawer.`;
}

export default function CommandTowerHomeLayout(props: LayoutProps) {
  const locale = props.locale ?? "en";
  const alertsStatusLabel = statusLabelFromCanonical(toCanonicalStatusFuzzy(props.alertsStatus), locale);
  const hasRefreshIssue =
    props.refreshHealthSummary.badgeVariant === "failed" ||
    props.refreshHealthSummary.badgeVariant === "warning";
  const liveSignalVariant = hasRefreshIssue
    ? props.refreshHealthSummary.badgeVariant
    : props.homeLiveBadgeVariant(props.liveMode);
  const liveSignalText = hasRefreshIssue
    ? props.refreshHealthSummary.badgeVariant === "failed"
      ? props.liveHomeCopy.refreshHealth.refreshFailed
      : props.liveHomeCopy.liveStatus.degraded
    : props.homeLiveBadgeText(props.liveMode);
  const sloBadgeVariant = hasRefreshIssue ? props.refreshHealthSummary.badgeVariant : props.alertsBadgeVariant(props.alertsStatus);
  const sloBadgeText = hasRefreshIssue
    ? props.refreshHealthSummary.badgeVariant === "failed"
      ? props.liveHomeCopy.layout.sloDegraded
      : props.liveHomeCopy.layout.sloWarning
    : `${props.commandTowerCopy.badges.sloPrefix}${alertsStatusLabel}`;
  const showFailureEventsAction = props.visibleSummary.failed > 0 || props.visibleSummary.blocked > 0;
  const primarySession = props.visibleSessions[0];
  const primaryActionHref = primarySession
    ? `/command-tower/sessions/${encodeURIComponent(primarySession.pm_session_id)}`
    : "/pm";
  const primaryActionLabel = primarySession ? props.liveHomeCopy.layout.primaryActionOpenRisk : props.liveHomeCopy.layout.primaryActionGoToPm;
  const liveAnnouncement = buildHomeLayoutLiveAnnouncement({
    locale,
    hasRefreshIssue,
    refreshHealthLabel: props.refreshHealthSummary.label,
    liveStatusText: props.liveStatusText,
    intervalMs: props.intervalMs,
    alertsStatusLabel,
  });

  return (
    <div
      className={`ct-home-layout ${
        props.drawerCollapsed ? "ct-home-layout--drawer-collapsed" : "ct-home-layout--drawer-expanded"
      }`}
    >
      <div className="ct-main-workspace">
        <section
          className="app-section"
          aria-label={props.liveHomeCopy.layout.overviewAriaLabel}
          aria-labelledby="ct-home-overview-title"
          aria-describedby="ct-home-overview-desc"
        >
          <div className="section-header">
            <div>
              <h2 id="ct-home-overview-title" className="ct-home-overview-title">{props.liveHomeCopy.layout.overviewTitle}</h2>
              <p id="ct-home-overview-desc">{props.liveHomeCopy.layout.overviewDescription}</p>
            </div>
            <div className="ct-home-header-badges">
              <Badge variant={liveSignalVariant}>
                {liveSignalText}
              </Badge>
              <Badge variant={sloBadgeVariant}>
                {sloBadgeText}
              </Badge>
            </div>
          </div>

          <div className="ct-home-action-bar">
            <Button
              type="button"
              variant={props.focusMode === "high_risk" ? "secondary" : "default"}
              onClick={props.toggleHighRiskFocus}
              aria-controls="command-tower-session-board-region"
              aria-pressed={props.focusMode === "high_risk"}
              aria-label={
                props.focusMode === "high_risk"
                  ? props.liveHomeCopy.layout.focusButtonActiveAriaLabel
                  : props.liveHomeCopy.layout.focusButtonInactiveAriaLabel
              }
              title={
                props.focusMode === "high_risk"
                  ? props.liveHomeCopy.layout.focusButtonActiveTitle
                  : props.liveHomeCopy.layout.focusButtonInactiveTitle
              }
            >
              {props.focusMode === "high_risk" ? props.liveHomeCopy.layout.focusButtonActive : props.liveHomeCopy.layout.focusButtonInactive}
            </Button>
            {props.focusMode === "high_risk" ? (
              <span className="mono muted" role="status" aria-live="polite">
                {props.liveHomeCopy.layout.focusButtonActiveHint}
              </span>
            ) : null}
            {!hasRefreshIssue && !props.snapshotStatus.enabled ? (
              <Button asChild variant="secondary">
                <Link href={primaryActionHref}>{primaryActionLabel}</Link>
              </Button>
            ) : null}
            {!hasRefreshIssue && !props.snapshotStatus.enabled && showFailureEventsAction ? (
              <Button asChild variant="ghost">
                <Link href="/events">{props.liveHomeCopy.layout.failureEvents}</Link>
              </Button>
            ) : null}
            <span className="mono muted" role="note">
              {props.liveHomeCopy.layout.filterDrawerHint}
            </span>
          </div>
          {props.snapshotStatus.enabled || hasRefreshIssue ? (
            <Card variant="compact" className="ct-home-error-alert" role="status" aria-live="polite">
              <p className="ct-home-empty-text">
                {hasRefreshIssue
                  ? props.refreshHealthSummary.badgeVariant === "failed"
                    ? props.liveHomeCopy.layout.degradedRefreshFailed
                    : props.liveHomeCopy.layout.degradedPartial
                  : props.liveHomeCopy.layout.snapshotTimestampOnly(props.snapshotStatus.label)}
              </p>
              <div className="toolbar toolbar--mt" role="group" aria-label={props.liveHomeCopy.layout.degradedActionsAriaLabel}>
                {showFailureEventsAction ? (
                  <Button asChild variant="ghost">
                    <Link href="/events">{props.liveHomeCopy.layout.reviewFailureEvents}</Link>
                  </Button>
                ) : (
                  <Button asChild variant="ghost">
                    <Link href="/runs">{props.liveHomeCopy.layout.reviewRuns}</Link>
                  </Button>
              )}
                <Button asChild variant="secondary">
                  <Link href="/command-tower">{props.liveHomeCopy.layout.reload}</Link>
                </Button>
              </div>
            </Card>
          ) : null}
          {props.totalSessionCount > 0 ? (
            <p className="mono muted" role="status" aria-live="polite">
              {props.liveHomeCopy.layout.riskSampleSummary(
                props.visibleSummary.total,
                props.visibleSummary.failed,
                props.visibleSummary.blocked,
                props.visibleSummary.running,
              )}
            </p>
          ) : null}

          <p className="sr-only" role="status" aria-live="polite">
            {liveAnnouncement}
          </p>
          {props.actionFeedback && (
            <div role="status" aria-live="polite" className="ct-home-action-feedback">
              {props.actionFeedback}
            </div>
          )}

          <section className="ct-priority-lanes" aria-label={props.liveHomeCopy.layout.overviewAriaLabel}>
            {props.priorityLanes.map((lane) => (
              <article
                key={lane.lane}
                className={`ct-priority-lane is-${lane.lane} ${lane.lane === "actions" ? "ct-priority-lane--wide" : ""}`}
              >
                <header>
                  <h3>{lane.title}</h3>
                  <Badge variant={lane.badgeVariant}>
                    {lane.badgeText}
                  </Badge>
                </header>
                <p>{lane.summary}</p>
                <div className="toolbar toolbar--mt" role="group" aria-label={props.liveHomeCopy.layout.laneQuickActionsAriaLabel(lane.title)}>
                  {lane.lane === "live" ? (
                    <Button type="button" variant="ghost" onClick={() => props.onRunQuickAction?.("live")}>
                      {props.liveMode === "paused" ? props.liveHomeCopy.layout.liveLaneSwitchToLive : props.liveHomeCopy.layout.liveLaneSwitchToPaused}
                    </Button>
                  ) : null}
                  {lane.lane === "risk" ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={props.toggleHighRiskFocus}
                      aria-controls="command-tower-session-board-region"
                      aria-pressed={props.focusMode === "high_risk"}
                    >
                      {props.focusMode === "high_risk" ? props.liveHomeCopy.layout.riskLaneRestoreFullView : props.liveHomeCopy.layout.riskLaneSwitchToHighRisk}
                    </Button>
                  ) : null}
                  {lane.lane === "actions" ? (
                    <Button asChild variant="ghost">
                      <Link href={primaryActionHref}>{props.liveHomeCopy.layout.actionsLaneOpenFirstRisk}</Link>
                    </Button>
                  ) : null}
                </div>
              </article>
            ))}
            <p className="mono muted" role="note">
              {props.liveHomeCopy.layout.laneNote}
            </p>
          </section>

          {props.showGlobalEmptyState && (
            <div className="compact-status-card">
              <p className="ct-home-empty-text">{props.liveHomeCopy.layout.noLiveData}</p>
            </div>
          )}
          {props.showFilterEmptyState && (
            <div className="compact-status-card">
              <p className="ct-home-empty-text">{props.commandTowerCopy.noSessionsForFilters}</p>
              <Button type="button" variant="secondary" onClick={props.resetFilters}>{props.commandTowerCopy.reset}</Button>
            </div>
          )}
          {props.showFocusEmptyState && (
            <div className="compact-status-card">
              <p className="ct-home-empty-text">{props.commandTowerCopy.noSessionsForFocus}</p>
              <Button type="button" variant="secondary" onClick={() => props.setFocusMode("all")}>{props.commandTowerCopy.viewAll}</Button>
            </div>
          )}
          {props.errorMessage && props.totalSessionCount === 0 && (
            <Card variant="compact" className="ct-home-error-alert" role="status" aria-live="polite">
              <p className="ct-home-empty-text">{props.liveHomeCopy.layout.dataUnavailable}</p>
              <div className="toolbar toolbar--mt" role="group" aria-label={props.liveHomeCopy.layout.dataUnavailableActionsAriaLabel}>
                <Button asChild variant="secondary">
                  <Link href="/pm">{props.liveHomeCopy.layout.primaryActionGoToPm}</Link>
                </Button>
                <Button asChild variant="ghost">
                  <Link href="/runs">{props.liveHomeCopy.layout.reviewRuns}</Link>
                </Button>
              </div>
            </Card>
          )}
        </section>
        <section className="app-section" aria-label={props.liveHomeCopy.layout.sessionBoardAriaLabel} aria-labelledby="ct-home-session-board-title">
          <div className="section-header">
            <div>
              <h3 id="ct-home-session-board-title" className="ct-home-session-board-title">{props.commandTowerCopy.sessionBoardTitle}</h3>
              <p className="ct-home-session-board-meta">{props.liveHomeCopy.layout.sessionBoardMeta(props.visibleSessionCount, props.totalSessionCount)}</p>
            </div>
            <Badge>{props.focusLabel}</Badge>
            {props.snapshotStatus.enabled ? <Badge variant="warning">{props.liveHomeCopy.layout.cachedSnapshotBadge}</Badge> : null}
          </div>
          <div id="command-tower-session-board-region" role="region" aria-label={props.liveHomeCopy.layout.sessionBoardListAriaLabel}>
            <props.SessionBoardComponent sessions={props.visibleSessions} snapshotStatus={props.snapshotStatus} locale={locale} />
          </div>
        </section>
      </div>

      {!props.drawerCollapsed && (
        <props.DrawerComponent
          liveBadgeVariant={props.drawerLiveBadgeVariant}
          liveBadgeText={props.homeLiveBadgeText(props.liveMode)}
          alertsBadgeVariant={props.alertsBadgeVariant(props.alertsStatus)}
          alertsStatus={props.alertsStatus}
          refreshBadgeVariant={props.refreshHealthSummary.badgeVariant}
          refreshLabel={props.refreshHealthSummary.label}
          quickActionItems={props.quickActionItems}
          contextHealthItems={props.contextHealthItems}
          sectionStatusItems={props.sectionStatusItems}
          drawerPromptItems={props.drawerPromptItems}
          topBlockers={props.overview.top_blockers || []}
          alerts={props.alerts}
          criticalAlerts={props.criticalAlerts}
          draftChanged={props.draftChanged}
          draftStatuses={props.draftStatuses}
          draftProjectKey={props.draftProjectKey}
          draftSort={props.draftSort}
          statusOptions={props.statusOptions}
          sortOptions={props.sortOptions}
          focusOptions={props.focusOptionsForDrawer}
          focusMode={props.focusMode}
          appliedFilterCount={props.appliedFilterCount}
          projectInputRef={props.projectInputRef}
          onToggleDraftStatus={props.toggleDraftStatus}
          onDraftProjectKeyChange={props.setDraftProjectKey}
          onDraftSortChange={(value: string) => props.setDraftSort(value as SortMode)}
          onFilterKeyDown={props.handleFilterKeyDown}
          onApplyFilters={props.applyFilters}
          onResetFilters={props.resetFilters}
          onFocusModeChange={(value: string) => props.setFocusMode(value as FocusMode)}
          onClose={props.toggleDrawerCollapsed}
          commandTowerCopy={props.commandTowerCopy}
          liveHomeCopy={props.liveHomeCopy}
        />
      )}
    </div>
  );
}
