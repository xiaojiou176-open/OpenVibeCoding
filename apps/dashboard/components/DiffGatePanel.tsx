"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDiffGate, fetchDiff, mutationExecutionCapability, rejectRun, rollbackRun } from "../lib/api";
import DiffViewer from "./DiffViewer";
import Link from "next/link";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";
import { formatDashboardDateTime, statusLabel } from "../lib/statusPresentation";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input, Select } from "./ui/input";

const DEFAULT_ROW_LIMIT = 10;
const TERMINAL_STATUSES = new Set([
  "SUCCESS",
  "SUCCEEDED",
  "COMPLETED",
  "DONE",
  "FAILED",
  "FAILURE",
  "ERROR",
  "CANCELLED",
  "REJECTED",
  "ROLLED_BACK",
  "ABORTED",
  "TIMEOUT",
]);

type GateAction = "rollback" | "reject";

type ExpandedDiffState = {
  diffText: string;
  isEmpty: boolean;
  loadedAt: string;
};

function formatLocalTime(iso: string): string {
  return formatDashboardDateTime(iso, "en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function toTestIdSegment(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "_") || "unknown";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readBooleanHint(item: Record<string, unknown>, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = item[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return null;
}

function readBlockedActions(item: Record<string, unknown>): Set<string> {
  const direct: unknown[] = Array.isArray(item.blocked_actions) ? item.blocked_actions : [];
  const nestedValue = asRecord(item.diff_gate).blocked_actions;
  const nested: unknown[] = Array.isArray(nestedValue) ? nestedValue : [];
  const merged = [...direct, ...nested].map((value) => String(value || "").trim().toLowerCase()).filter(Boolean);
  return new Set(merged);
}

function resolveActionGate(item: Record<string, unknown>, action: GateAction): { allowed: boolean; reason: string } {
  const runId = String(item.run_id || "").trim();
  if (!runId) {
    return { allowed: false, reason: "Missing run_id, so this action is unavailable." };
  }

  const blockedActions = readBlockedActions(item);
  if (blockedActions.has(action)) {
    return { allowed: false, reason: "This record policy blocks the action." };
  }

  const keyAlias = action === "rollback"
    ? ["can_rollback", "rollback_allowed", "rollback_executable"]
    : ["can_reject", "reject_allowed", "reject_executable"];
  const directHint = readBooleanHint(item, keyAlias);
  if (directHint === false) {
    return { allowed: false, reason: "This record is marked non-executable." };
  }

  const gateMeta = asRecord(item.diff_gate);
  const nestedHint = readBooleanHint(gateMeta, keyAlias);
  if (nestedHint === false) {
    return { allowed: false, reason: "The Diff Gate result marks this action non-executable." };
  }

  const hasExplicitAllow = directHint === true || nestedHint === true;
  const status = String(item.status || "").trim().toUpperCase();
  const failureReason = String(item.failure_reason || "").trim().toLowerCase();
  if (!hasExplicitAllow && status && TERMINAL_STATUSES.has(status)) {
    return { allowed: false, reason: "This record is already in a terminal state, so the action is disabled." };
  }
  if (!hasExplicitAllow && action === "reject" && failureReason.includes("diff gate rejected")) {
    return { allowed: false, reason: "This record was already rejected by Diff Gate, so there is nothing to reject again." };
  }

  return { allowed: true, reason: "" };
}

function buildActionErrorMessage(actionLabel: "Rollback" | "Reject", err: unknown): string {
  const detail = uiErrorDetail(err);
  const normalized = detail.toLowerCase();
  if (/\b422\b/.test(normalized)) {
    return `${actionLabel} failed: the current record state does not satisfy the action precondition. Refresh and verify the Diff state first.`;
  }
  if (/\b409\b/.test(normalized)) {
    return `${actionLabel} failed: the record state changed. Refresh the list and try again.`;
  }
  if (normalized.includes("401") || normalized.includes("403") || normalized.includes("auth") || normalized.includes("token")) {
    return `${actionLabel} failed: permission or authentication error. Confirm the login state and role configuration.`;
  }
  if (normalized.includes("network") || normalized.includes("fetch") || normalized.includes("timeout")) {
    return `${actionLabel} failed: network error. Please try again later.`;
  }
  return `${actionLabel} failed: ${sanitizeUiError(err, "check the event log and try again")}`;
}

export default function DiffGatePanel() {
  const [items, setItems] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState("Loading pending changes for review...");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, ExpandedDiffState>>({});
  const [diffLoading, setDiffLoading] = useState<Record<string, boolean>>({});
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<Record<string, string>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [visibleCount, setVisibleCount] = useState(DEFAULT_ROW_LIMIT);
  const [listStatus, setListStatus] = useState("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const loadRequestRef = useRef(0);

  async function load(options: { soft?: boolean; forceNetwork?: boolean } = {}) {
    const soft = options.soft ?? false;
    const forceNetwork = options.forceNetwork ?? false;
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    if (soft) {
      setRefreshing(true);
    } else {
      setLoadingMessage(forceNetwork ? "Retrying pending changes for review..." : "Loading pending changes for review...");
      setLoading(true);
    }
    setLoadError(null);
    try {
      let data: Array<Record<string, unknown>> = [];
      if (forceNetwork && typeof window !== "undefined") {
        try {
          const refreshed = await fetch(`/api/diff-gate?refresh_ts=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
              accept: "application/json",
            },
          });
          if (!refreshed.ok) {
            throw new Error(`API /api/diff-gate failed: ${refreshed.status}`);
          }
          const payload = await refreshed.json();
          if (Array.isArray(payload)) {
            data = payload as Array<Record<string, unknown>>;
          } else {
            const maybeItems = asRecord(payload).items;
            data = Array.isArray(maybeItems) ? (maybeItems as Array<Record<string, unknown>>) : [];
          }
        } catch (networkErr: unknown) {
          console.error(`[diff-gate] force-network refresh fallback: ${uiErrorDetail(networkErr)}`);
          const fallback = await fetchDiffGate();
          data = Array.isArray(fallback) ? (fallback as Array<Record<string, unknown>>) : [];
        }
      } else {
        const fallback = await fetchDiffGate();
        data = Array.isArray(fallback) ? (fallback as Array<Record<string, unknown>>) : [];
      }
      if (loadRequestRef.current !== requestId) {
        return;
      }
      setItems(data);
      const nextCount = data.length;
      const refreshedAt = new Date().toISOString();
      setLastRefreshedAt(refreshedAt);
      setListStatus(soft ? `Pending review list refreshed. ${nextCount} record(s) currently available.` : `Loaded ${nextCount} pending review record(s).`);
    } catch (err: unknown) {
      if (loadRequestRef.current !== requestId) {
        return;
      }
      console.error(`[diff-gate] load failed: ${uiErrorDetail(err)}`);
      setLoadError(sanitizeUiError(err, "please try again later"));
      if (!soft) {
        setItems([]);
      }
      setListStatus(soft ? "Refresh failed. The current list and filter context were preserved." : "Load failed. Try again.");
    } finally {
      if (loadRequestRef.current === requestId) {
        setLoading(false);
        setRefreshing(false);
        setLoadedOnce(true);
      }
    }
  }

  useEffect(() => {
    void load();
  }, []);
  const mutationCapability = mutationExecutionCapability();
  const normalizedRole = mutationCapability.operatorRole || "";
  const hasMutationRole = mutationCapability.executable;
  const roleGateReason = hasMutationRole ? "" : "NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE is not configured. High-risk actions are disabled.";

  const statusOptions = useMemo(() => {
    const options = new Set<string>(["ALL"]);
    for (const item of items) {
      const raw = String(item.status || "").trim().toUpperCase();
      if (raw) {
        options.add(raw);
      }
    }
    return Array.from(options);
  }, [items]);

  const filteredItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return items
      .filter((item) => {
        const statusText = String(item.status || "").trim().toUpperCase();
        if (statusFilter !== "ALL" && statusText !== statusFilter) {
          return false;
        }
        if (!query) {
          return true;
        }
        const runId = String(item.run_id || "").toLowerCase();
        const failureReason = String(item.failure_reason || "").toLowerCase();
        return runId.includes(query) || failureReason.includes(query) || statusText.toLowerCase().includes(query);
      })
      .sort((left, right) => String(right.run_id || "").localeCompare(String(left.run_id || "")));
  }, [items, searchQuery, statusFilter]);

  const visibleItems = useMemo(() => filteredItems.slice(0, visibleCount), [filteredItems, visibleCount]);
  const hasMoreRows = filteredItems.length > visibleCount;

  useEffect(() => {
    setVisibleCount(DEFAULT_ROW_LIMIT);
  }, [searchQuery, statusFilter]);

  async function toggleDiff(runId: string) {
    if (expanded[runId]) {
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });
      return;
    }
    setDiffLoading((prev) => ({ ...prev, [runId]: true }));
    try {
      const resp = await fetchDiff(runId);
      const diffText = typeof resp?.diff === "string" ? resp.diff : "";
      setExpanded((prev) => ({ ...prev, [runId]: { diffText, isEmpty: !diffText.trim(), loadedAt: new Date().toISOString() } }));
      if (!diffText) {
        setStatus((prev) => ({ ...prev, [runId]: "No visible diff was produced for this run. The panel is now in read-only empty state." }));
      } else {
        setStatus((prev) => ({ ...prev, [runId]: `Diff ready: ${diffText.length} characters loaded for review.` }));
      }
    } catch (err: unknown) {
      console.error(`[diff-gate] fetch diff failed (${runId}): ${uiErrorDetail(err)}`);
      setStatus((prev) => ({ ...prev, [runId]: `Failed to load Diff: ${sanitizeUiError(err, "refresh and try again, or inspect the run detail page")}` }));
      setExpanded((prev) => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });
    } finally {
      setDiffLoading((prev) => ({ ...prev, [runId]: false }));
    }
  }

  async function handleRollback(runId: string) {
    if (!hasMutationRole) {
      setStatus((prev) => ({ ...prev, [runId]: roleGateReason }));
      return;
    }
    setActionLoading((prev) => ({ ...prev, [runId]: true }));
    setStatus((prev) => ({ ...prev, [runId]: "Running rollback..." }));
    try {
      const resp = await rollbackRun(runId);
      setStatus((prev) => ({
        ...prev,
        [runId]: resp?.ok
          ? "Rollback succeeded: the audit event was recorded and the pending review list is refreshing."
          : "Rollback failed: the service did not confirm execution. Check the event log.",
      }));
      await load({ soft: true });
    } catch (err: unknown) {
      console.error(`[diff-gate] rollback failed (${runId}): ${uiErrorDetail(err)}`);
      setStatus((prev) => ({ ...prev, [runId]: buildActionErrorMessage("Rollback", err) }));
    } finally {
      setActionLoading((prev) => ({ ...prev, [runId]: false }));
    }
  }

  async function handleReject(runId: string) {
    if (!hasMutationRole) {
      setStatus((prev) => ({ ...prev, [runId]: roleGateReason }));
      return;
    }
    setActionLoading((prev) => ({ ...prev, [runId]: true }));
    setStatus((prev) => ({ ...prev, [runId]: "Rejecting change..." }));
    try {
      const resp = await rejectRun(runId);
      setStatus((prev) => ({
        ...prev,
        [runId]: resp?.ok
          ? "Reject succeeded: the audit event was recorded and the pending review list is refreshing."
          : "Reject failed: the service did not confirm execution. Check the event log.",
      }));
      await load({ soft: true });
    } catch (err: unknown) {
      console.error(`[diff-gate] reject failed (${runId}): ${uiErrorDetail(err)}`);
      setStatus((prev) => ({ ...prev, [runId]: buildActionErrorMessage("Reject", err) }));
    } finally {
      setActionLoading((prev) => ({ ...prev, [runId]: false }));
    }
  }

  if (loading) {
    return (
      <Card role="status" aria-live="polite" aria-busy="true" data-testid="diff-gate-loading-state">
        <div className="mono muted">{loadingMessage}</div>
        <div className="toolbar mt-2" role="group" aria-label="Pending governance actions" data-testid="diff-gate-loading-actions">
          <Button type="button" variant="default" disabled data-testid="diff-gate-loading-approve">
            Approve
          </Button>
          <Button type="button" variant="secondary" disabled data-testid="diff-gate-loading-reject">
            Reject change
          </Button>
          <Button type="button" variant="ghost" disabled data-testid="diff-gate-loading-rollback">
            Rollback run
          </Button>
        </div>
        <div className="toolbar mt-2" data-testid="diff-gate-loading-audit-context">
          <Badge variant="default">Loading audit context</Badge>
          <div className="mono muted">Run IDs, status snapshots, and recent audit timestamps will appear after the data returns.</div>
        </div>
        <div className="skeleton-stack-md mt-2" aria-hidden="true">
          <div className="skeleton skeleton-row" data-testid="diff-gate-loading-audit-row-primary" />
          <div className="skeleton skeleton-row skeleton-w-50" data-testid="diff-gate-loading-audit-row-secondary" />
        </div>
        <div className="skeleton skeleton-card skeleton-card-tall" />
      </Card>
    );
  }

  if (loadError && items.length === 0) {
    return (
      <Card data-testid="diff-gate-error-state">
        <div className="alert alert-danger" role="alert">
          <strong>Diff Gate truth is currently unavailable:</strong>
          <span>{loadError}</span>
        </div>
        <p className="mono muted">
          This is a data-availability problem, not evidence that all changes already passed review.
        </p>
        <div className="toolbar">
          <Button
            variant="default"
            type="button"
            onClick={() => void load({ forceNetwork: true })}
            data-testid="diff-gate-retry-load"
          >
            Retry load
          </Button>
          <Button asChild variant="ghost">
            <Link href="/runs" data-testid="diff-gate-go-runs-after-error">Open runs list for investigation</Link>
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="grid" data-testid="diff-gate-panel">
      <Card>
        <p className="mono muted">
          Diff Gate separates read-only review, gate-blocked changes, and missing truth. Do not treat an empty or degraded view as approval.
        </p>
        <p className="mono muted" role="status" aria-live="polite" data-testid="diff-gate-list-status">
          {listStatus || `Pending review records: ${items.length}; showing ${visibleItems.length}.`}
        </p>
        <p className="mono muted" data-testid="diff-gate-last-refreshed-at">
          Last refreshed: {lastRefreshedAt ? formatLocalTime(lastRefreshedAt) : "--"}
        </p>
        {loadError && loadedOnce && items.length > 0 ? (
          <div className="alert alert-danger" role="alert" data-testid="diff-gate-soft-error">
            <strong>Refresh failed:</strong>
            <span>{loadError}</span>
          </div>
        ) : null}
        <div className="toolbar mt-2 diff-gate-toolbar-filters">
          <label className="diff-gate-filter-field">
            <span className="muted">Search</span>
            <Input
              data-testid="diff-gate-search-input"
              type="search"
              value={searchQuery}
              placeholder="Filter by run_id / status / failure reason"
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
          <label className="diff-gate-filter-field">
            <span className="muted">Status filter</span>
            <Select
              data-testid="diff-gate-status-filter"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              {statusOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "ALL" ? "All statuses" : option}
                </option>
              ))}
            </Select>
          </label>
          <div className="diff-gate-filter-field">
            <span className="muted">Operator role</span>
            <span className="mono" data-testid="diff-gate-operator-role">
              {normalizedRole || "Not configured"}
            </span>
          </div>
        </div>
        {!hasMutationRole ? (
          <div className="alert alert-warning diff-gate-role-tip" role="status" data-testid="diff-gate-role-tip">
            <strong>Diff Gate is in read-only mode.</strong>
            <span>{roleGateReason}</span>
          </div>
        ) : null}
        <div className="toolbar mt-2">
          <Button
            variant="default"
            type="button"
            onClick={() => void load({ soft: true, forceNetwork: true })}
            disabled={refreshing}
            data-testid="diff-gate-refresh-list"
          >
            {refreshing ? "Refreshing..." : "Refresh pending review list"}
          </Button>
          {hasMoreRows ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setVisibleCount(filteredItems.length);
                setListStatus(`Expanded all ${filteredItems.length} pending review record(s).`);
              }}
              data-testid="diff-gate-expand-list"
            >
              Expand all ({filteredItems.length})
            </Button>
          ) : filteredItems.length > DEFAULT_ROW_LIMIT ? (
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setVisibleCount(DEFAULT_ROW_LIMIT);
                setListStatus(`Collapsed back to the first ${DEFAULT_ROW_LIMIT} record(s).`);
              }}
              data-testid="diff-gate-collapse-list"
            >
              Collapse to first 10
            </Button>
          ) : null}
          <Button asChild variant="ghost">
            <Link href="/runs" data-testid="diff-gate-go-runs-list">Open runs list</Link>
          </Button>
        </div>
      </Card>
      <div className="diff-gate-list" role="list" aria-label="Diff Gate review list" data-testid="diff-gate-list">
        {items.length === 0 ? (
          <Card data-testid="diff-gate-no-items">
            <div className="empty-state-stack">
              <strong>No pending Diff Gate records right now</strong>
              <span className="muted">All changes are approved, or nothing is waiting for review.</span>
              <span className="mono muted">Refresh the list or inspect recent execution from the runs list.</span>
            </div>
          </Card>
        ) : visibleItems.length === 0 ? (
          <Card data-testid="diff-gate-filter-empty">
            <div className="empty-state-stack">
              <strong>No pending review records match the current filters</strong>
              <span className="muted">Adjust the search text or status filter.</span>
            </div>
          </Card>
        ) : null}
        {visibleItems.map((item, index) => {
          const runId = String(item.run_id || "");
          const rowKey = runId ? `${runId}-${index}` : `unknown-${index}`;
          const statusText = statusLabel(String(item.status || ""), "en");
          const expandedDiff = expanded[runId];
          const hasDiff = Boolean(expandedDiff);
          const rowBusy = Boolean(actionLoading[runId] || diffLoading[runId]);
          const runTestId = toTestIdSegment(runId);
          const failureReason = typeof item.failure_reason === "string" ? item.failure_reason : "";
          const allowedPaths = Array.isArray(item.allowed_paths)
            ? item.allowed_paths.map((path) => String(path))
            : [];
          const rollbackGate = resolveActionGate(item, "rollback");
          const rejectGate = resolveActionGate(item, "reject");
          const rollbackDisabled = rowBusy || !hasMutationRole || !rollbackGate.allowed;
          const rejectDisabled = rowBusy || !hasMutationRole || !rejectGate.allowed;
          const rollbackReason = !hasMutationRole ? roleGateReason : rollbackGate.reason;
          const rejectReason = !hasMutationRole ? roleGateReason : rejectGate.reason;
          return (
            <article key={rowKey} className="diff-gate-item" role="listitem" data-testid={`diff-gate-item-${runTestId}`}>
              <header className="diff-gate-item-header">
                <Link href={`/runs/${encodeURIComponent(runId)}`} className="diff-gate-run-link">
                  {runId}
                </Link>
                <Badge>{statusText}</Badge>
              </header>

              {failureReason && (
                <p className="diff-gate-failure">{failureReason}</p>
              )}

              <details className="diff-gate-details">
                <summary>Allowed paths</summary>
                <pre className="mono pm-code-block">{JSON.stringify(allowedPaths, null, 2)}</pre>
              </details>

              <div className="diff-gate-actions">
                <Button
                  variant="secondary"
                  type="button"
                  onClick={() => void toggleDiff(runId)}
                  disabled={rowBusy}
                  aria-label={diffLoading[runId] ? `Load Diff ${runId}` : hasDiff ? `Hide Diff ${runId}` : `View Diff ${runId}`}
                  data-testid={`diff-gate-toggle-diff-${runTestId}`}
                >
                  {diffLoading[runId] ? "Loading Diff..." : hasDiff ? "Hide Diff" : "View Diff"}
                </Button>
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => void handleRollback(runId)}
                  disabled={rollbackDisabled}
                  aria-label={`Rollback ${runId}`}
                  title={rollbackReason || `Run rollback ${runId}`}
                  data-testid={`diff-gate-rollback-${runTestId}`}
                >
                  Rollback
                </Button>
                <Button
                  variant="destructive"
                  type="button"
                  onClick={() => void handleReject(runId)}
                  disabled={rejectDisabled}
                  aria-label={`Reject change ${runId}`}
                  title={rejectReason || `Reject change ${runId}`}
                  data-testid={`diff-gate-reject-${runTestId}`}
                >
                  Reject change
                </Button>
              </div>
              {rollbackReason || rejectReason ? (
                <p className="mono muted diff-gate-action-hint" data-testid={`diff-gate-action-hint-${runTestId}`}>
                  {rollbackReason || rejectReason}
                </p>
              ) : null}

              {status[runId] && (
                <div
                  className={`diff-gate-feedback ${/\b(failed|error)\b/i.test(status[runId]) ? "is-error" : ""}`}
                  role="status"
                  aria-live="polite"
                  data-testid={`diff-gate-feedback-${runTestId}`}
                >
                  {status[runId]}
                </div>
              )}

              {hasDiff && (
                <div className="diff-gate-diff-region" data-testid={`diff-gate-diff-region-${runTestId}`}>
                  <p className="mono muted" data-testid={`diff-gate-diff-meta-${runTestId}`}>
                    {expandedDiff?.isEmpty
                      ? "Diff loaded: read-only empty state (no visible changes)"
                      : `Diff loaded and ready for review (loaded at ${expandedDiff?.loadedAt ?? "-"})`}
                  </p>
                  {expandedDiff?.isEmpty ? (
                    <div className="diff-gate-readonly-empty" data-testid={`diff-gate-readonly-empty-${runTestId}`}>
                      No diff content was produced. This region is read-only.
                    </div>
                  ) : (
                    <DiffViewer diff={expandedDiff?.diffText || ""} allowedPaths={allowedPaths} />
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
      {filteredItems.length > DEFAULT_ROW_LIMIT && visibleCount >= filteredItems.length ? (
        <Card>
          <div className="mono muted">Expanded all {filteredItems.length} record(s).</div>
          <div className="toolbar mt-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setVisibleCount(DEFAULT_ROW_LIMIT)}
              data-testid="diff-gate-collapse-footer"
            >
              Collapse to first 10
            </Button>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
