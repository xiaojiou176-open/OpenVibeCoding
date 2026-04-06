"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { fetchLocks, mutationExecutionCapability, releaseLocks } from "../../lib/api";
import { sanitizeUiError, uiErrorDetail } from "../../lib/uiError";

const DEFAULT_ROW_LIMIT = 10;

function formatLocalTime(iso: string | null): string {
  if (!iso) {
    return "--";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString("en-US", { hour12: false });
}

export default function LocksPage() {
  const [locks, setLocks] = useState<Array<Record<string, unknown>>>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [refreshFeedback, setRefreshFeedback] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(DEFAULT_ROW_LIMIT);
  const [releaseLoadingLockId, setReleaseLoadingLockId] = useState<string | null>(null);
  const [optimisticReleasedLockIds, setOptimisticReleasedLockIds] = useState<Set<string>>(() => new Set());
  const [releaseFeedback, setReleaseFeedback] = useState<string | null>(null);
  const [releaseFeedbackIsError, setReleaseFeedbackIsError] = useState(false);

  const mutationCapability = mutationExecutionCapability();
  const normalizedRole = mutationCapability.operatorRole || "";
  const hasMutationRole = mutationCapability.executable;
  const roleGateReason = hasMutationRole ? "" : "NEXT_PUBLIC_CORTEXPILOT_OPERATOR_ROLE is not configured in this environment, so release actions are disabled.";

  async function loadLocks(options: { soft?: boolean; preserveWarning?: boolean } = {}) {
    const soft = options.soft ?? false;
    if (soft) {
      setRefreshing(true);
      setRefreshFeedback("Refreshing lock list...");
    } else {
      setInitialLoading(true);
      setRefreshFeedback(null);
    }
    if (!options.preserveWarning) {
      setWarning(null);
    }
    try {
      const payload = await fetchLocks();
      const nextLocks = Array.isArray(payload) ? payload : [];
      setLocks(nextLocks);
      setLastUpdatedAt(new Date().toISOString());
      if (soft) {
        setRefreshFeedback(`Lock list refreshed (${formatLocalTime(new Date().toISOString())})`);
      }
      setOptimisticReleasedLockIds((previous) => {
        if (previous.size === 0) {
          return previous;
        }
        const idsInPayload = new Set(nextLocks.map((lock) => String(lock.lock_id || "").trim()).filter(Boolean));
        const next = new Set(previous);
        for (const lockId of Array.from(next)) {
          if (!idsInPayload.has(lockId)) {
            next.delete(lockId);
          }
        }
        return next;
      });
    } catch (err: unknown) {
      console.error(`[locks] load failed: ${uiErrorDetail(err)}`);
      setWarning(sanitizeUiError(err, "Lock records are unavailable right now. Please try again later."));
      if (!soft) {
        setLocks([]);
      }
      if (soft) {
        setRefreshFeedback("Refresh failed. Keeping the current list.");
      }
    } finally {
      if (soft) {
        setRefreshing(false);
      } else {
        setInitialLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadLocks();
  }, []);

  async function handleRelease(lock: Record<string, unknown>) {
    const lockId = String(lock.lock_id || "").trim();
    const targetPath = String(lock.path || "").trim();
    if (!hasMutationRole) {
      setReleaseFeedbackIsError(true);
      setReleaseFeedback(roleGateReason);
      return;
    }
    if (!targetPath) {
      setReleaseFeedbackIsError(true);
      setReleaseFeedback("This lock record is missing `path`, so it cannot be released.");
      return;
    }
    setReleaseLoadingLockId(lockId);
    setReleaseFeedbackIsError(false);
    setReleaseFeedback(`Releasing lock (${targetPath})...`);
    try {
      const result = await releaseLocks([targetPath]);
      const ok = result?.ok ? "succeeded" : "failed";
      setReleaseFeedbackIsError(!result?.ok);
      setReleaseFeedback(`Lock release ${ok} (${targetPath})`);
      if (result?.ok && lockId) {
        setOptimisticReleasedLockIds((previous) => {
          const next = new Set(previous);
          next.add(lockId);
          return next;
        });
      }
      await loadLocks({ soft: true, preserveWarning: true });
    } catch (err: unknown) {
      console.error(`[locks] release failed: ${uiErrorDetail(err)}`);
      setReleaseFeedbackIsError(true);
      setReleaseFeedback(`Lock release failed: ${sanitizeUiError(err, "Please try again later")}`);
    } finally {
      setReleaseLoadingLockId(null);
    }
  }

  const visibleLocksSource = locks.filter((lock) => {
    const lockId = String(lock.lock_id || "").trim();
    return !lockId || !optimisticReleasedLockIds.has(lockId);
  });
  const filteredLocks = visibleLocksSource.filter((lock) => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return [lock.lock_id, lock.run_id, lock.agent_id, lock.role, lock.path]
      .map((value) => String(value || "").toLowerCase())
      .some((value) => value.includes(query));
  });
  const visibleLocks = filteredLocks.slice(0, visibleCount);
  const hasMoreLocks = filteredLocks.length > visibleCount;

  useEffect(() => {
    setVisibleCount(DEFAULT_ROW_LIMIT);
  }, [searchQuery]);

  return (
    <main className="grid" aria-labelledby="locks-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="locks-page-title" className="page-title">Lock Management</h1>
            <p className="page-subtitle">Review lock records, linked runs, and resource paths in one place.</p>
          </div>
          <Badge data-testid="locks-count-badge">{visibleLocksSource.length} locks</Badge>
        </div>
      </header>
      <section className="app-section" aria-label="Lock record list">
        <Card data-testid="locks-actions-card">
          <div className="mono muted">Total lock records: {visibleLocksSource.length}. The first view shows up to {DEFAULT_ROW_LIMIT} rows.</div>
          <div className="mono muted" data-testid="locks-last-updated">Last refreshed: {formatLocalTime(lastUpdatedAt)}</div>
          <div className="toolbar mt-2">
            <label className="diff-gate-filter-field">
              <span className="muted">Search</span>
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Filter by lock ID, run_id, or path"
                aria-label="Search lock records"
                data-testid="locks-search-input"
              />
            </label>
            <div className="diff-gate-filter-field">
              <span className="muted">Operator role</span>
              <span className="mono" data-testid="locks-role-select">
                {normalizedRole || "Not configured"}
              </span>
            </div>
          </div>
          {!hasMutationRole ? (
            <p className="mono muted diff-gate-role-tip" data-testid="locks-role-tip">{roleGateReason}</p>
          ) : null}
          <div className="toolbar mt-2">
            <Button
              variant="default"
              type="button"
              onClick={() => void loadLocks({ soft: true })}
              data-testid="locks-refresh-action"
              disabled={initialLoading || refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh lock list"}
            </Button>
            <Button
              variant="secondary"
              type="button"
              onClick={() => void loadLocks({ soft: true })}
              data-testid="locks-refresh-inline-action"
              disabled={initialLoading || refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh now"}
            </Button>
            <Button asChild variant="ghost">
              <Link href="/runs" data-testid="locks-go-runs-action">Go to runs</Link>
            </Button>
          </div>
          {refreshFeedback ? (
            <div className="diff-gate-feedback" role="status" aria-live="polite" data-testid="locks-refresh-feedback">
              {refreshFeedback}
            </div>
          ) : null}
          {releaseFeedback ? (
            <div
              className={`diff-gate-feedback ${releaseFeedbackIsError ? "is-error" : ""}`}
              role="status"
              aria-live="polite"
              data-testid="locks-release-feedback"
            >
              {releaseFeedback}
            </div>
          ) : null}
        </Card>
        {warning ? (
          <div className="alert alert-warning" role="status" data-testid="locks-warning-state">
            <strong>Lock records failed to load:</strong>
            <span>{warning}</span>
          </div>
        ) : null}
        {initialLoading ? (
          <Card data-testid="locks-loading-state">
            <div className="mono muted" role="status" aria-live="polite">Loading lock records...</div>
            <div className="skeleton skeleton-card skeleton-card-tall" />
          </Card>
        ) : visibleLocksSource.length === 0 ? (
          <Card data-testid="locks-empty-state">
            <div className="empty-state-stack">
              <strong>No lock records yet</strong>
              <span className="muted">There are no active or recorded resource locks right now.</span>
              <span className="mono muted">Next: run a lock-using task, then return here and refresh.</span>
            </div>
          </Card>
        ) : (
          <Card variant="table" data-testid="locks-table-card">
            <table className="run-table">
              <caption className="mono">Lock records (showing {visibleLocks.length} / {filteredLocks.length})</caption>
              <thead>
                <tr>
                  <th scope="col">Lock ID</th>
                  <th scope="col">Run ID</th>
                  <th scope="col">Agent ID</th>
                  <th scope="col">Role</th>
                  <th scope="col">Path</th>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleLocks.map((lock: Record<string, unknown>) => (
                  <tr key={`${lock.lock_id}-${lock.path}`}>
                    <th scope="row"><span className="mono">{String(lock.lock_id)}</span></th>
                    <td><span className="mono">{String(lock.run_id || "-")}</span></td>
                    <td><span className="mono">{String(lock.agent_id || "-")}</span></td>
                    <td><Badge>{String(lock.role || "-")}</Badge></td>
                    <td><span className="chip">{String(lock.path)}</span></td>
                    <td><span className="mono muted">{String(lock.ts || "-")}</span></td>
                    <td>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => handleRelease(lock)}
                        disabled={
                          releaseLoadingLockId === String(lock.lock_id || "") ||
                          !hasMutationRole ||
                          !String(lock.path || "").trim()
                        }
                        data-testid={`locks-release-action-${String(lock.lock_id || "unknown")}`}
                        title={
                          !String(lock.path || "").trim()
                            ? "Missing `path`, cannot release"
                            : !hasMutationRole
                              ? roleGateReason
                              : "Release lock"
                        }
                      >
                        {releaseLoadingLockId === String(lock.lock_id || "") ? "Releasing..." : "Release lock"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
        {hasMoreLocks ? (
          <Card>
            <div className="mono muted">{filteredLocks.length - visibleCount} more lock records are hidden.</div>
            <div className="toolbar mt-2">
              <Button type="button" variant="secondary" onClick={() => setVisibleCount(filteredLocks.length)} data-testid="locks-show-all">
                Show all
              </Button>
            </div>
          </Card>
        ) : null}
      </section>
    </main>
  );
}
