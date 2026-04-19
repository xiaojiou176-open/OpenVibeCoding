import type { CommandTowerPriorityLane } from "../../lib/frontendApiContract";
import type { CommandTowerAlertsPayload } from "../../lib/types";
import type { UiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import type { StatusVariant } from "@openvibecoding/frontend-shared/statusPresentation";

export type SortMode = "updated_desc" | "created_desc" | "failed_desc" | "blocked_desc";
export type FocusMode = "all" | "high_risk" | "blocked" | "running";
export type LiveMode = "running" | "backoff" | "paused";
export type SectionFetchStatus = "ok" | "error";
export type QuickActionId =
  | "refresh"
  | "live"
  | "export"
  | "copy"
  | "focus-filter"
  | "apply-filter"
  | "toggle-drawer"
  | "toggle-pin";

type SessionSummaryStats = {
  total: number;
  failed: number;
  blocked: number;
  running: number;
};

type SeveritySummary = {
  critical: number;
};

type SectionStatus = {
  overview: SectionFetchStatus;
  sessions: SectionFetchStatus;
  alerts: SectionFetchStatus;
};

type BuildArgs = {
  isRefreshing: boolean;
  liveEnabled: boolean;
  drawerCollapsed: boolean;
  drawerPinned: boolean;
  alertsStatus: CommandTowerAlertsPayload["status"];
  liveMode: LiveMode;
  intervalMs: number;
  focusLabel: string;
  visibleSessionCount: number;
  hasAppliedFilters: boolean;
  appliedFilterCount: number;
  sectionStatus: SectionStatus;
  filteredSessionsSummary: SessionSummaryStats;
  alertsSeveritySummary: SeveritySummary;
  draftChanged: boolean;
  draftFilterCount: number;
  errorMessage: string;
  errorMetaLabel: string;
  liveStatusText: string;
  alertsStatusLabel: string;
  refreshFreshnessSummary: string;
  showFilterEmptyState: boolean;
  showFocusEmptyState: boolean;
  showGlobalEmptyState: boolean;
  onRunQuickAction: (id: QuickActionId) => void;
  sectionStatusText: {
    overview: (statusLabel: string) => string;
    sessions: (statusLabel: string) => string;
    alerts: (statusLabel: string) => string;
  };
  sectionStatusLabel: (status: SectionFetchStatus) => string;
  sectionStatusBadgeVariant: (status: SectionFetchStatus) => StatusVariant;
  homeLiveBadgeText: (mode: LiveMode) => string;
  homeLiveBadgeVariant: (mode: LiveMode) => StatusVariant;
  alertsBadgeVariant: (status: CommandTowerAlertsPayload["status"]) => StatusVariant;
  commandTowerCopy: UiCopy["desktop"]["commandTower"];
  liveHomeCopy: UiCopy["dashboard"]["commandTowerPage"]["liveHome"];
};

export function buildHomeViewModel(args: BuildArgs): {
  quickActionItems: Array<{
    id: QuickActionId;
    shortcut: string;
    description: string;
    actionLabel: string;
    onAction: () => void;
    disabled?: boolean;
  }>;
  drawerLiveBadgeVariant: StatusVariant;
  contextHealthItems: Array<{
    id: string;
    label: string;
    value: string;
    badgeVariant: StatusVariant;
    badgeLabel: string;
  }>;
  sectionStatusItems: Array<{ id: string; text: string; badgeVariant: StatusVariant }>;
  drawerPromptItems: string[];
  priorityLanes: Array<{
    lane: CommandTowerPriorityLane;
    title: string;
    summary: string;
    badgeVariant: StatusVariant;
    badgeText: string;
  }>;
  focusOptionsForDrawer: Array<{ value: FocusMode; label: string; count: number }>;
  homeStateSignalLabel: string;
  homeStateSignalDetail: string;
} {
  const quickActionItems: Array<{
    id: QuickActionId;
    shortcut: string;
    description: string;
    actionLabel: string;
    onAction: () => void;
    disabled?: boolean;
  }> = [
    {
      id: "refresh",
      shortcut: "Alt+Shift+R",
      description: args.liveHomeCopy.viewModel.quickActions.refreshDescription,
      actionLabel: args.isRefreshing ? args.commandTowerCopy.actions.refreshing : args.commandTowerCopy.refreshNow,
      onAction: () => args.onRunQuickAction("refresh"),
      disabled: args.isRefreshing,
    },
    {
      id: "live",
      shortcut: "Alt+Shift+L",
      description: args.liveHomeCopy.viewModel.quickActions.liveDescription,
      actionLabel: args.liveEnabled
        ? args.liveHomeCopy.viewModel.quickActions.pauseAction
        : args.liveHomeCopy.viewModel.quickActions.resumeAction,
      onAction: () => args.onRunQuickAction("live"),
    },
    {
      id: "export",
      shortcut: "Alt+Shift+E",
      description: args.liveHomeCopy.viewModel.quickActions.exportDescription,
      actionLabel: args.liveHomeCopy.viewModel.quickActions.exportAction,
      onAction: () => args.onRunQuickAction("export"),
    },
    {
      id: "copy",
      shortcut: "Alt+Shift+C",
      description: args.liveHomeCopy.viewModel.quickActions.copyDescription,
      actionLabel: args.commandTowerCopy.drawer.copy,
      onAction: () => args.onRunQuickAction("copy"),
    },
    {
      id: "focus-filter",
      shortcut: "Alt+Shift+F",
      description: args.liveHomeCopy.viewModel.quickActions.focusDescription,
      actionLabel: args.liveHomeCopy.viewModel.quickActions.focusAction,
      onAction: () => args.onRunQuickAction("focus-filter"),
    },
    {
      id: "toggle-drawer",
      shortcut: "Alt+Shift+D",
      description: args.liveHomeCopy.viewModel.quickActions.toggleDrawerDescription,
      actionLabel: args.drawerCollapsed
        ? args.liveHomeCopy.viewModel.quickActions.expandAction
        : args.liveHomeCopy.viewModel.quickActions.collapseAction,
      onAction: () => args.onRunQuickAction("toggle-drawer"),
    },
    {
      id: "toggle-pin",
      shortcut: "Alt+Shift+P",
      description: args.liveHomeCopy.viewModel.quickActions.togglePinDescription,
      actionLabel: args.drawerPinned
        ? args.liveHomeCopy.viewModel.quickActions.unpinAction
        : args.liveHomeCopy.viewModel.quickActions.pinAction,
      onAction: () => args.onRunQuickAction("toggle-pin"),
    },
    {
      id: "apply-filter",
      shortcut: "Enter (while a filter input is focused)",
      description: args.liveHomeCopy.viewModel.quickActions.applyDescription,
      actionLabel: args.commandTowerCopy.apply,
      onAction: () => args.onRunQuickAction("apply-filter"),
    },
  ];

  const drawerLiveBadgeVariant =
    args.liveMode === "backoff"
      ? "failed"
      : args.liveEnabled
        ? "running"
        : "warning";

  const contextHealthItems: Array<{
    id: string;
    label: string;
    value: string;
    badgeVariant: StatusVariant;
    badgeLabel: string;
  }> = [
    {
      id: "engine",
      label: args.liveHomeCopy.viewModel.contextHealth.liveEngine,
      value: args.liveEnabled
        ? args.liveHomeCopy.viewModel.contextHealth.runningValue(args.intervalMs)
        : args.liveHomeCopy.viewModel.contextHealth.pausedValue,
      badgeVariant: drawerLiveBadgeVariant,
      badgeLabel: args.liveEnabled ? args.commandTowerCopy.drawer.running : args.commandTowerCopy.drawer.paused,
    },
    {
      id: "slo",
      label: args.liveHomeCopy.viewModel.contextHealth.sloHealth,
      value: args.alertsStatusLabel,
      badgeVariant: args.alertsBadgeVariant(args.alertsStatus),
      badgeLabel: args.alertsStatusLabel,
    },
    {
      id: "focus",
      label: args.liveHomeCopy.viewModel.contextHealth.focusHit,
      value: `${args.focusLabel} (${args.visibleSessionCount}/${args.filteredSessionsSummary.total})`,
      badgeVariant: "success",
      badgeLabel: args.commandTowerCopy.drawer.focusHits,
    },
    {
      id: "filter",
      label: args.liveHomeCopy.viewModel.contextHealth.filterState,
      value: args.hasAppliedFilters
        ? args.liveHomeCopy.viewModel.contextHealth.filtersApplied(args.appliedFilterCount)
        : args.liveHomeCopy.viewModel.contextHealth.filtersOff,
      badgeVariant: args.hasAppliedFilters ? "running" : "warning",
      badgeLabel: args.hasAppliedFilters ? args.commandTowerCopy.drawer.filterState : args.commandTowerCopy.drawer.allFilters,
    },
  ];

  const sectionStatusItems: Array<{ id: string; text: string; badgeVariant: StatusVariant }> = [
    {
      id: "overview",
      text: args.sectionStatusText.overview(args.sectionStatusLabel(args.sectionStatus.overview)),
      badgeVariant: args.sectionStatusBadgeVariant(args.sectionStatus.overview),
    },
    {
      id: "sessions",
      text: args.sectionStatusText.sessions(args.sectionStatusLabel(args.sectionStatus.sessions)),
      badgeVariant: args.sectionStatusBadgeVariant(args.sectionStatus.sessions),
    },
    {
      id: "alerts",
      text: args.sectionStatusText.alerts(args.sectionStatusLabel(args.sectionStatus.alerts)),
      badgeVariant: args.sectionStatusBadgeVariant(args.sectionStatus.alerts),
    },
  ];

  const drawerPromptItems: string[] = [];
  if (args.alertsSeveritySummary.critical > 0) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.criticalAlerts(args.alertsSeveritySummary.critical));
  }
  if (args.errorMessage) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.currentIssue(args.errorMetaLabel));
  }
  if (args.draftChanged) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.unappliedDraftFilters(args.draftFilterCount));
  }
  if (args.filteredSessionsSummary.failed > 0 || args.filteredSessionsSummary.blocked > 0) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.riskCounts(args.filteredSessionsSummary.failed, args.filteredSessionsSummary.blocked));
  }
  if (!args.liveEnabled) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.paused);
  }
  if (drawerPromptItems.length === 0) {
    drawerPromptItems.push(args.liveHomeCopy.viewModel.drawerPrompts.stable);
  }

  const priorityLanes: Array<{
    lane: CommandTowerPriorityLane;
    title: string;
    summary: string;
    badgeVariant: StatusVariant;
    badgeText: string;
  }> = [
    {
      lane: "live" as const,
      title: args.liveHomeCopy.viewModel.priorityLanes.liveTitle,
      summary: args.liveHomeCopy.viewModel.priorityLanes.liveSummary(args.homeLiveBadgeText(args.liveMode), args.intervalMs),
      badgeVariant: args.homeLiveBadgeVariant(args.liveMode),
      badgeText: args.liveEnabled
        ? args.liveHomeCopy.viewModel.priorityLanes.liveBadge
        : args.liveHomeCopy.viewModel.priorityLanes.pausedBadge,
    },
    {
      lane: "risk" as const,
      title: args.liveHomeCopy.viewModel.priorityLanes.riskTitle,
      summary: args.liveHomeCopy.viewModel.priorityLanes.riskSummary(
        args.filteredSessionsSummary.failed,
        args.filteredSessionsSummary.blocked,
        args.alertsSeveritySummary.critical,
      ),
      badgeVariant: args.alertsBadgeVariant(args.alertsStatus),
      badgeText: args.alertsStatusLabel,
    },
    {
      lane: "actions" as const,
      title: args.liveHomeCopy.viewModel.priorityLanes.actionsTitle,
      summary: args.draftChanged
        ? args.liveHomeCopy.viewModel.priorityLanes.draftFiltersWaiting(args.draftFilterCount)
        : args.errorMessage || args.alertsStatus !== "healthy"
          ? args.liveHomeCopy.viewModel.priorityLanes.refreshFirst
          : args.liveHomeCopy.viewModel.priorityLanes.primaryActionsReady,
      badgeVariant: args.draftChanged
        ? "warning"
        : args.errorMessage || args.alertsStatus !== "healthy"
          ? "warning"
          : "success",
      badgeText: args.draftChanged
        ? args.liveHomeCopy.viewModel.priorityLanes.pendingBadge
        : args.errorMessage || args.alertsStatus !== "healthy"
          ? args.liveHomeCopy.viewModel.priorityLanes.convergingBadge
          : args.liveHomeCopy.viewModel.priorityLanes.readyBadge,
    },
  ];

  const focusOptionsForDrawer = [
    { value: "all" as const, label: args.commandTowerCopy.focusLabels.all, count: args.filteredSessionsSummary.total },
    { value: "high_risk" as const, label: args.commandTowerCopy.focusLabels.highRisk, count: args.filteredSessionsSummary.failed },
    { value: "blocked" as const, label: args.commandTowerCopy.focusLabels.blocked, count: args.filteredSessionsSummary.blocked },
    { value: "running" as const, label: args.commandTowerCopy.focusLabels.running, count: args.filteredSessionsSummary.running },
  ];

  const homeStateSignalLabel = args.isRefreshing
    ? "Refreshing the live overview..."
    : args.errorMessage
      ? `Refresh failed: ${args.errorMetaLabel}`
      : args.alertsStatus !== "healthy"
        ? "Overview partially degraded. Review the risk lane and session board first."
      : args.showFilterEmptyState
        ? "No sessions match the current filters"
        : args.showFocusEmptyState
          ? `No sessions match the current focus view (${args.focusLabel})`
          : args.showGlobalEmptyState
            ? "No session data yet. Start a request from PM first."
            : args.filteredSessionsSummary.failed > 0
              ? `${args.filteredSessionsSummary.failed} high-risk sessions detected. Quick actions are already staged in the main workspace.`
              : "Live overview ready";

  return {
    quickActionItems,
    drawerLiveBadgeVariant,
    contextHealthItems,
    sectionStatusItems,
    drawerPromptItems: drawerPromptItems.slice(0, 4),
    priorityLanes,
    focusOptionsForDrawer,
    homeStateSignalLabel,
    homeStateSignalDetail: `${args.liveStatusText} · ${args.refreshFreshnessSummary}`,
  };
}
