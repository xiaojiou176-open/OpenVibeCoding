"use client";

import { useEffect, useRef, useState } from "react";
import { approveGodMode, fetchPendingApprovals, mutationExecutionCapability } from "../lib/api";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";
import { useDashboardLocale } from "./DashboardLocaleContext";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import Link from "next/link";
import { formatDashboardDateTime } from "../lib/statusPresentation";

type QueueUiState = "loading" | "error" | "pending" | "idle";

function inferQueueUiState(pendingLoading: boolean, pendingError: string | null, pendingCount: number): QueueUiState {
  if (pendingLoading) return "loading";
  if (pendingError) return "error";
  if (pendingCount > 0) return "pending";
  return "idle";
}

function queueBadgeMeta(
  state: QueueUiState,
  pendingCount: number,
  text: {
    loading: string;
    error: string;
    idle: string;
    pending: (count: number) => string;
  },
): { variant: "running" | "failed" | "warning" | "success"; text: string } {
  switch (state) {
    case "loading":
      return { variant: "running", text: text.loading };
    case "error":
      return { variant: "failed", text: text.error };
    case "pending":
      return { variant: "warning", text: text.pending(pendingCount) };
    default:
      return { variant: "success", text: text.idle };
  }
}

function isAuthRelatedError(errorText: string): boolean {
  const normalized = errorText.toLowerCase();
  return normalized.includes("401") || normalized.includes("403") || normalized.includes("auth") || normalized.includes("token");
}

export default function GodModePanel() {
  const { locale, uiCopy } = useDashboardLocale();
  const approvalCopy = uiCopy.dashboard.approval;
  const [runId, setRunId] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<"success" | "error" | "info">("info");
  const [pending, setPending] = useState<Array<Record<string, unknown>>>([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [pendingError, setPendingError] = useState<string | null>(null);
  const [pendingLastAttemptAt, setPendingLastAttemptAt] = useState<string | null>(null);
  const [pendingLastSuccessAt, setPendingLastSuccessAt] = useState<string | null>(null);
  const [approvingRunId, setApprovingRunId] = useState<string | null>(null);
  const [manualApproving, setManualApproving] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<string | null>(null);
  const confirmDialogRef = useRef<HTMLDivElement | null>(null);
  const confirmCancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmTriggerRef = useRef<HTMLElement | null>(null);

  const mutationCapability = mutationExecutionCapability();
  const normalizedRole = mutationCapability.operatorRole || "";
  const hasMutationRole = mutationCapability.executable;
  const roleGateReason = hasMutationRole ? "" : "NEXT_PUBLIC_OPENVIBECODING_OPERATOR_ROLE is not configured. Approval actions are disabled.";
  const queueState = inferQueueUiState(pendingLoading, pendingError, pending.length);
  const queueBadge = queueBadgeMeta(queueState, pending.length, {
    loading: approvalCopy.queueLoadingBadge,
    error: approvalCopy.queueLoadFailedBadge,
    idle: approvalCopy.queueIdleBadge,
    pending: approvalCopy.queuePendingBadge,
  });
  const hasPendingLoadError = Boolean(pendingError);
  const pendingErrorIsAuth = pendingError ? isAuthRelatedError(pendingError) : false;

  async function loadPending(options?: { preserveStatus?: boolean; trigger?: "initial" | "refresh" | "retry" }) {
    const preserveStatus = options?.preserveStatus ?? false;
    const trigger = options?.trigger ?? "refresh";
    const attemptAt = new Date().toISOString();
    setPendingLoading(true);
    setPendingLastAttemptAt(attemptAt);
    if (!preserveStatus) {
      setStatusTone("info");
      setStatus(trigger === "retry" ? approvalCopy.statusRetryingQueue : approvalCopy.statusRefreshingQueue);
    }
    try {
      const items = await fetchPendingApprovals();
      setPending(Array.isArray(items) ? items : []);
      setPendingError(null);
      setPendingLastSuccessAt(new Date().toISOString());
      if (!preserveStatus) {
        setStatusTone("success");
        setStatus(approvalCopy.statusQueueRefreshed(Array.isArray(items) ? items.length : 0));
      }
    } catch (err: unknown) {
      console.error(`[god-mode] load-pending failed: ${uiErrorDetail(err)}`);
      const normalizedError = sanitizeUiError(err, "Pending approvals queue fetch failed");
      const isAuthError = isAuthRelatedError(normalizedError);
      setPendingError(normalizedError);
      setPending([]);
      if (!preserveStatus) {
        setStatusTone("error");
        setStatus(
          trigger === "retry"
            ? approvalCopy.statusRetryFailed(normalizedError, isAuthError)
            : approvalCopy.statusRefreshFailed(normalizedError, isAuthError),
        );
      }
    } finally {
      setPendingLoading(false);
    }
  }

  useEffect(() => {
    void loadPending({ trigger: "initial" });
  }, []);

  async function handleApprove() {
    if (!hasMutationRole) {
      setStatusTone("error");
      setStatus(roleGateReason);
      return;
    }
    const targetRunId = runId.trim();
    if (!targetRunId) {
      setStatusTone("error");
      setStatus(approvalCopy.statusEnterRunId);
      return;
    }
    setManualApproving(true);
    setStatusTone("info");
    setStatus(approvalCopy.statusSubmittingApproval);
    try {
      await approveGodMode(targetRunId);
      setStatusTone("success");
      setStatus(approvalCopy.statusApproved);
      await loadPending({ preserveStatus: true });
    } catch (err: unknown) {
      console.error(`[god-mode] approve failed: ${uiErrorDetail(err)}`);
      setStatusTone("error");
      setStatus(approvalCopy.statusFailed(sanitizeUiError(err, "Approval failed")));
    } finally {
      setManualApproving(false);
    }
  }

  function requestApproveItem(id: string, triggerElement?: HTMLElement | null) {
    if (!hasMutationRole) {
      setStatusTone("error");
      setStatus(roleGateReason);
      return;
    }
    if (triggerElement) {
      confirmTriggerRef.current = triggerElement;
    } else {
      const activeElement = document.activeElement;
      if (activeElement instanceof HTMLElement) {
        confirmTriggerRef.current = activeElement;
      }
    }
    setConfirmTarget(id);
  }

  function cancelConfirm() {
    setConfirmTarget(null);
  }

  useEffect(() => {
    if (!confirmTarget) {
      const trigger = confirmTriggerRef.current;
      if (trigger && trigger.isConnected) {
        trigger.focus();
      }
      confirmTriggerRef.current = null;
      return;
    }

    const dialog = confirmDialogRef.current;
    if (!dialog) return;

    const focusableSelector = [
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[href]",
      "[tabindex]:not([tabindex='-1'])",
    ].join(", ");

    const getFocusableElements = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector)).filter(
        (element) => !element.hasAttribute("disabled") && element.getAttribute("aria-hidden") !== "true",
      );

    const initialFocusTarget = confirmCancelButtonRef.current ?? getFocusableElements()[0] ?? dialog;
    initialFocusTarget.focus();
    const focusSyncFrame = window.requestAnimationFrame(() => {
      const first = confirmCancelButtonRef.current ?? getFocusableElements()[0] ?? dialog;
      if (!dialog.contains(document.activeElement)) {
        first.focus();
      }
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setConfirmTarget(null);
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = getFocusableElements();
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey) {
        if (active === first || !dialog.contains(active)) {
          event.preventDefault();
          last.focus();
        }
        return;
      }

      if (active === last || !dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      }
    };

    const onFocusIn = (event: FocusEvent) => {
      const target = event.target as Node | null;
      if (!target || !dialog.contains(target)) {
        const first = confirmCancelButtonRef.current ?? getFocusableElements()[0] ?? dialog;
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      window.cancelAnimationFrame(focusSyncFrame);
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
    };
  }, [confirmTarget]);

  async function confirmApproveItem() {
    if (!confirmTarget) return;
    if (!hasMutationRole) {
      setStatusTone("error");
      setStatus(roleGateReason);
      setConfirmTarget(null);
      return;
    }
    const targetRunId = confirmTarget;
    setConfirmTarget(null);
    setRunId(targetRunId);
    setApprovingRunId(targetRunId);
    setStatusTone("info");
    setStatus(approvalCopy.statusSubmittingApproval);
    try {
      await approveGodMode(targetRunId);
      setStatusTone("success");
      setStatus(approvalCopy.statusApproved);
      await loadPending({ preserveStatus: true });
    } catch (err: unknown) {
      console.error(`[god-mode] approve-item failed: ${uiErrorDetail(err)}`);
      setStatusTone("error");
      setStatus(approvalCopy.statusFailed(sanitizeUiError(err, "Approval failed")));
    } finally {
      setApprovingRunId(null);
    }
  }

  return (
    <section className="god-mode-panel" aria-labelledby="god-mode-title">
      <header className="god-mode-header">
        <h2 id="god-mode-title">{approvalCopy.panelTitle}</h2>
        <Badge variant={queueBadge.variant} data-testid="god-mode-queue-badge">
          {queueBadge.text}
        </Badge>
      </header>
      <p className="mono muted">
        {approvalCopy.panelIntro}
      </p>
      <div className="god-mode-detail" role="group" aria-label={approvalCopy.roleConfigurationAriaLabel}>
        <span className="god-mode-detail-label">{approvalCopy.operatorRoleLabel}</span>
        <div className="god-mode-input-row">
          <Input
            value={normalizedRole || approvalCopy.operatorRoleUnconfigured}
            aria-label={approvalCopy.operatorRoleLabel}
            data-testid="god-mode-role-select"
            readOnly
          />
          <Button
            variant="ghost"
            onClick={() => void loadPending({ trigger: "refresh" })}
            disabled={pendingLoading}
            data-testid="god-mode-refresh-pending"
          >
            {pendingLoading ? approvalCopy.refreshingPending : approvalCopy.refreshPending}
          </Button>
        </div>
        <span className="mono muted" data-testid="god-mode-last-success-at">
          {approvalCopy.lastSuccessfulRefreshPrefix} {formatDashboardDateTime(pendingLastSuccessAt, locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
        </span>
        {!hasMutationRole ? (
          <div className="alert alert-warning" data-testid="god-mode-role-tip">
            <strong>{approvalCopy.actionsDisabledTitle}</strong>
            <span>{roleGateReason}</span>
          </div>
        ) : null}
      </div>

      {hasPendingLoadError && (
        <div className="god-mode-detail" role="alert" aria-live="assertive">
          <div className="grid">
            <span className="god-mode-detail-label">{approvalCopy.pendingTruthUnavailable(String(pendingError || ""))}</span>
            <span className="mono muted">
              {approvalCopy.recoveryTip}
            </span>
            <span className="mono muted" data-testid="god-mode-last-attempt-at">
              {approvalCopy.lastAttemptPrefix} {formatDashboardDateTime(pendingLastAttemptAt, locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
            </span>
          </div>
          <div className="toolbar mt-2">
            <Button
              variant="ghost"
              onClick={() => void loadPending({ trigger: "retry" })}
              disabled={pendingLoading}
              data-testid="god-mode-retry-pending"
            >
              {pendingLoading ? approvalCopy.retryingFetch : approvalCopy.retryFetch}
            </Button>
            <Button asChild variant="secondary">
              <Link href="/pm">{approvalCopy.inspectConnection}</Link>
            </Button>
            {pendingErrorIsAuth ? (
              <Button asChild variant="ghost">
                <Link href="/command-tower">{approvalCopy.verifyAuthState}</Link>
              </Button>
            ) : null}
          </div>
        </div>
      )}

      {pendingLoading ? (
        <div className="mono muted" role="status" aria-live="polite" data-testid="god-mode-loading-state">
          {approvalCopy.loadingPending}
        </div>
      ) : null}

      {pending.length > 0 && (
        <div className="god-mode-queue" role="list" aria-label={approvalCopy.pendingQueueAriaLabel}>
          {pending.map((item) => (
            <article key={String(item.run_id || "")} className="god-mode-item" role="listitem">
              <div className="god-mode-item-header">
                <code className="mono">{String(item.run_id || "-")}</code>
                <Badge variant="warning">{String(item.status || "-")}</Badge>
              </div>
              {item.approval_pack && typeof item.approval_pack === "object" ? (
                <p className="mono muted">{String((item.approval_pack as Record<string, unknown>).summary || "")}</p>
              ) : null}
              {Array.isArray(item.reason) && item.reason.length > 0 && (
                <div className="god-mode-detail">
                  <span className="god-mode-detail-label">{approvalCopy.reasonLabel}</span>
                  <ul className="god-mode-detail-list">
                    {item.reason.map((r, i) => <li key={i}>{String(r)}</li>)}
                  </ul>
                </div>
              )}
              {Array.isArray(item.actions) && item.actions.length > 0 && (
                <div className="god-mode-detail">
                  <span className="god-mode-detail-label">{approvalCopy.requiredActionLabel}</span>
                  <ul className="god-mode-detail-list">
                    {item.actions.map((a, i) => <li key={i}>{String(a)}</li>)}
                  </ul>
                </div>
              )}
              {item.resume_step && (
                <p className="god-mode-resume">
                  {approvalCopy.resumeAtLabel}: <code>{String(item.resume_step)}</code>
                </p>
              )}
              <Button
                variant="default"
                className="god-mode-approve-btn"
                onClick={(event) => requestApproveItem(String(item.run_id), event.currentTarget)}
                disabled={!hasMutationRole || pendingLoading || approvingRunId === String(item.run_id)}
              >
                {approvingRunId === String(item.run_id) ? approvalCopy.continuingButton : approvalCopy.continueButton}
              </Button>
            </article>
          ))}
        </div>
      )}

      <div className="god-mode-manual">
        <p className="god-mode-hint">
          {approvalCopy.manualHint}
        </p>
        <label className="sr-only" htmlFor="god-mode-run-id">
          {approvalCopy.runIdLabel}
        </label>
        <div className="god-mode-input-row">
          <Input
            id="god-mode-run-id"
            name="run_id"
            placeholder={approvalCopy.runIdPlaceholder}
            value={runId}
            onChange={(e) => setRunId(e.target.value)}
            aria-label={approvalCopy.runIdLabel}
          />
          <Button variant="default" onClick={handleApprove} disabled={!runId.trim() || !hasMutationRole || manualApproving}>
            {manualApproving ? approvalCopy.approvingButton : approvalCopy.approveButton}
          </Button>
        </div>
      </div>
      {status && (
        <div
          className={`god-mode-status ${statusTone === "error" ? "is-error" : statusTone === "info" ? "is-info" : ""}`}
          role="status"
          aria-live="polite"
          data-testid="god-mode-status"
        >
          {status}
        </div>
      )}

      {confirmTarget && (
        <div className="god-mode-confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="god-mode-confirm-title">
          <div className="god-mode-confirm-card" ref={confirmDialogRef} tabIndex={-1}>
            <h3 id="god-mode-confirm-title">{approvalCopy.confirmTitle}</h3>
            <p>
              {approvalCopy.confirmDescription(confirmTarget)}
            </p>
            <div className="god-mode-confirm-actions">
              <Button variant="ghost" ref={confirmCancelButtonRef} onClick={cancelConfirm}>{approvalCopy.cancel}</Button>
              <Button variant="default" onClick={confirmApproveItem}>{approvalCopy.confirmApproval}</Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
