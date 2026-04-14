import type { KeyboardEvent as ReactKeyboardEvent, RefObject } from "react";
import type { UiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { Badge, type BadgeVariant } from "../ui/badge";
import { Button } from "../ui/button";
import { Input, Select } from "../ui/input";

import BlockerPanel from "./BlockerPanel";
import type { CommandTowerAlert, PmSessionStatus, PmSessionSummary } from "../../lib/types";

type QuickActionItem = {
  id: string;
  shortcut: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  disabled?: boolean;
};

type ContextHealthItem = {
  id: string;
  label: string;
  value: string;
  badgeVariant: BadgeVariant;
  badgeLabel: string;
};

type DrawerSectionStatusItem = {
  id: string;
  text: string;
  badgeVariant: BadgeVariant;
};

type DrawerSortOption = {
  value: string;
  label: string;
};

type DrawerFocusOption = {
  value: string;
  label: string;
  count: number;
};

type CommandTowerHomeDrawerProps = {
  liveBadgeVariant: BadgeVariant;
  liveBadgeText: string;
  alertsBadgeVariant: BadgeVariant;
  alertsStatus: string;
  refreshBadgeVariant: BadgeVariant;
  refreshLabel: string;
  quickActionItems: QuickActionItem[];
  contextHealthItems: ContextHealthItem[];
  sectionStatusItems: DrawerSectionStatusItem[];
  drawerPromptItems: string[];
  topBlockers: PmSessionSummary[];
  alerts: CommandTowerAlert[];
  criticalAlerts: number;
  draftChanged: boolean;
  draftStatuses: PmSessionStatus[];
  draftProjectKey: string;
  draftSort: string;
  statusOptions: PmSessionStatus[];
  sortOptions: DrawerSortOption[];
  focusOptions: DrawerFocusOption[];
  focusMode: string;
  appliedFilterCount: number;
  projectInputRef: RefObject<HTMLInputElement | null>;
  onToggleDraftStatus: (status: PmSessionStatus) => void;
  onDraftProjectKeyChange: (value: string) => void;
  onDraftSortChange: (value: string) => void;
  onFilterKeyDown: (event: ReactKeyboardEvent<HTMLInputElement | HTMLSelectElement>) => void;
  onApplyFilters: () => void;
  onResetFilters: () => void;
  onFocusModeChange: (value: string) => void;
  onClose: () => void;
  commandTowerCopy: UiCopy["desktop"]["commandTower"];
  liveHomeCopy: UiCopy["dashboard"]["commandTowerPage"]["liveHome"];
};

export default function CommandTowerHomeDrawer({
  liveBadgeVariant,
  liveBadgeText,
  alertsBadgeVariant,
  alertsStatus,
  refreshBadgeVariant,
  refreshLabel,
  quickActionItems,
  contextHealthItems,
  sectionStatusItems,
  drawerPromptItems,
  topBlockers,
  alerts,
  criticalAlerts,
  draftChanged,
  draftStatuses,
  draftProjectKey,
  draftSort,
  statusOptions,
  sortOptions,
  focusOptions,
  focusMode,
  appliedFilterCount,
  projectInputRef,
  onToggleDraftStatus,
  onDraftProjectKeyChange,
  onDraftSortChange,
  onFilterKeyDown,
  onApplyFilters,
  onResetFilters,
  onFocusModeChange,
  onClose,
  commandTowerCopy,
  liveHomeCopy,
}: CommandTowerHomeDrawerProps) {
  return (
    <div
      id="ct-home-drawer-shell"
      className="ct-drawer-panel"
      role="region"
      aria-label={liveHomeCopy.loadingContextPanelAriaLabel}
    >
      <div className="ct-drawer-header">
        <h3 className="ct-drawer-title">{commandTowerCopy.drawer.title}</h3>
        <Button
          type="button"
          variant="ghost"
          className="btn-icon"
          onClick={onClose}
          aria-label={commandTowerCopy.drawer.close}
          aria-keyshortcuts="Alt+Shift+D"
        >
          &times;
        </Button>
      </div>

      <div className="ct-drawer-status-row">
        <Badge variant={liveBadgeVariant}>
          {liveBadgeText}
        </Badge>
        <Badge variant={alertsBadgeVariant}>
          {alertsStatus}
        </Badge>
        <Badge variant={refreshBadgeVariant}>
          {refreshLabel}
        </Badge>
      </div>

      <div className="ct-drawer-section">
        <h4 className="ct-drawer-section-title">{commandTowerCopy.drawer.quickActions}</h4>
        <div className="ct-quick-actions-compact">
          {quickActionItems.map((item) => {
            const descriptionId = `ct-home-quick-action-desc-${item.id}`;
            return (
              <div key={item.id}>
                <Button
                  variant="unstyled"
                  className="ct-quick-action-chip"
                  onClick={item.onAction}
                  disabled={item.disabled}
                  title={`${item.description} (${item.shortcut})`}
                  aria-describedby={descriptionId}
                >
                  <span className="ct-chip-label">{item.actionLabel}</span>
                  <kbd className="ct-chip-kbd">
                    {item.shortcut.replace(/^Alt\+Shift\+/, "")}
                  </kbd>
                </Button>
                <span id={descriptionId} className="sr-only">
                  {item.description} ({item.shortcut})
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="ct-drawer-section">
        <div
          className="ct-home-filter-console"
          role="region"
          aria-labelledby="ct-home-filter-title"
          aria-describedby="ct-home-filter-desc"
        >
          <div className="ct-home-filter-header">
            <div>
              <h4 id="ct-home-filter-title" className="ct-home-filter-title">
                {commandTowerCopy.filterTitle}
              </h4>
              <p id="ct-home-filter-desc" className="ct-home-filter-desc">
                {commandTowerCopy.filterHint}
              </p>
            </div>
            {draftChanged ? (
              <Badge variant="warning">{commandTowerCopy.draftNotApplied}</Badge>
            ) : (
              <Badge>
                {appliedFilterCount > 0
                  ? liveHomeCopy.viewModel.contextHealth.filtersApplied(appliedFilterCount)
                  : liveHomeCopy.viewModel.contextHealth.filtersOff}
              </Badge>
            )}
          </div>
          <div className="ct-home-filter-grid">
            <fieldset className="ct-home-status-filter" aria-label={commandTowerCopy.statusLegend}>
              <legend className="ct-home-status-filter-legend">{commandTowerCopy.statusLegend}</legend>
              {statusOptions.map((status) => (
                <label key={status} className="ct-home-status-filter-item">
                  <input
                    type="checkbox"
                    checked={draftStatuses.includes(status)}
                    onChange={() => onToggleDraftStatus(status)}
                  />
                  <span>{status}</span>
                </label>
              ))}
            </fieldset>
            <label className="ct-home-filter-label ct-home-filter-label-project">
              <span className="ct-home-filter-label-text">{commandTowerCopy.projectKey}</span>
              <Input
                ref={projectInputRef}
                className="ct-home-filter-input"
                value={draftProjectKey}
                onChange={(event) => onDraftProjectKeyChange(event.target.value)}
                onKeyDown={onFilterKeyDown}
                placeholder={liveHomeCopy.drawer.projectKeyPlaceholder}
                aria-keyshortcuts="Alt+Shift+F"
              />
            </label>
            <label className="ct-home-filter-label ct-home-filter-label-sort">
              <span className="ct-home-filter-label-text">{commandTowerCopy.sort}</span>
              <Select
                className="ct-home-filter-input"
                value={draftSort}
                onChange={(event) => onDraftSortChange(event.target.value)}
                onKeyDown={onFilterKeyDown}
              >
                {sortOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <div className="ct-home-filter-actions">
              <Button
                type="button"
                variant="default"
                onClick={onApplyFilters}
                disabled={!draftChanged}
                aria-controls="command-tower-session-board-region"
              >
                {commandTowerCopy.apply}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={onResetFilters}
                aria-controls="command-tower-session-board-region"
              >
                {commandTowerCopy.reset}
              </Button>
            </div>
          </div>
          <div role="group" aria-label={liveHomeCopy.drawer.focusViewSwitcherAriaLabel} className="ct-home-focus-switch">
            {focusOptions.map((option) => (
              <Button
                key={option.value}
                type="button"
                variant={focusMode === option.value ? "default" : "ghost"}
                aria-pressed={focusMode === option.value}
                onClick={() => onFocusModeChange(option.value)}
              >
                {option.label}
                <span className="ct-home-focus-count">{option.count}</span>
              </Button>
            ))}
          </div>
        </div>
      </div>

      <div className="ct-drawer-section">
        <h4 className="ct-drawer-section-title">{commandTowerCopy.drawer.health}</h4>
        <div className="ct-health-grid">
          {contextHealthItems.map((item) => (
            <div key={item.id} className="ct-health-row">
              <span className="ct-health-label">{item.label}</span>
              <Badge variant={item.badgeVariant}>
                {item.badgeLabel}
              </Badge>
            </div>
          ))}
        </div>
        <div className="ct-drawer-meta">
          {sectionStatusItems.map((item) => (
            <Badge key={item.id} variant={item.badgeVariant}>
              {item.text}
            </Badge>
          ))}
        </div>
      </div>

      <div className="ct-drawer-section">
        <h4 className="ct-drawer-section-title">{commandTowerCopy.drawer.inspectionPrompts}</h4>
        <ul className="ct-prompt-list">
          {drawerPromptItems.map((item) => (
            <li key={item} className="ct-prompt-item">
              {item}
            </li>
          ))}
        </ul>
      </div>

      <BlockerPanel blockers={topBlockers} />

      <div className="ct-drawer-section">
        <div className="ct-drawer-section-header">
          <h4 className="ct-drawer-section-title">{commandTowerCopy.drawer.alerts}</h4>
          <Badge>
            {criticalAlerts > 0 ? commandTowerCopy.drawer.criticalCount(criticalAlerts) : commandTowerCopy.drawer.records(alerts.length)}
          </Badge>
        </div>
        {alerts.length === 0 ? (
          <p className="ct-empty-hint">{commandTowerCopy.drawer.noAlerts}</p>
        ) : (
          <div className="ct-alert-list" role="list" aria-label={commandTowerCopy.drawer.alerts}>
            {alerts.map((item) => {
              const severity =
                typeof item?.severity === "string" && item.severity.trim()
                  ? item.severity.toUpperCase()
                  : "UNKNOWN";
              const code =
                typeof item?.code === "string" && item.code.trim()
                  ? item.code
                  : "UNKNOWN_CODE";
              const message =
                typeof item?.message === "string" && item.message.trim()
                  ? item.message
                  : "No alert details";
              const severityVariant: BadgeVariant =
                severity === "CRITICAL"
                  ? "failed"
                  : severity === "WARNING"
                    ? "warning"
                    : "default";
              return (
                <div key={`${code}-${message}`} role="listitem" className="ct-alert-item">
                  <div className="ct-alert-head">
                    <Badge variant={severityVariant}>
                      {severity}
                    </Badge>
                    <code className="ct-alert-code">{code}</code>
                  </div>
                  <p className="ct-alert-msg">{message}</p>
                  {item.suggested_action && (
                    <p className="ct-alert-suggestion">{item.suggested_action}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
