"use client";

import { useEffect, useRef, useState } from "react";
import { approveGodMode, fetchPendingApprovals, mutationExecutionCapability } from "../lib/api";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";
import { useDashboardLocale } from "./DashboardLocaleContext";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
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

function approvalStatusLabel(rawStatus: string, locale: "en" | "zh-CN"): string {
  const normalized = rawStatus.trim().toUpperCase();
  if (!normalized) {
    return locale === "zh-CN" ? "等待人工拍板" : "Waiting for a human decision";
  }
  if (normalized.includes("WAIT") || normalized.includes("PENDING") || normalized.includes("APPROVAL")) {
    return locale === "zh-CN" ? "等待人工拍板" : "Waiting for a human decision";
  }
  if (normalized.includes("FAIL") || normalized.includes("ERROR")) {
    return locale === "zh-CN" ? "需要人工接管" : "Needs human intervention";
  }
  return locale === "zh-CN" ? "需要人工确认" : "Needs human confirmation";
}

function approvalHeadline(item: Record<string, unknown>, locale: "en" | "zh-CN"): string {
  const approvalPack =
    item.approval_pack && typeof item.approval_pack === "object" ? (item.approval_pack as Record<string, unknown>) : null;
  const summary = String(approvalPack?.summary || "").trim();
  if (summary) {
    return summary;
  }
  const actions = Array.isArray(item.actions) ? item.actions : [];
  const reasons = Array.isArray(item.reason) ? item.reason : [];
  const firstAction = String(actions[0] || "").trim();
  if (firstAction) {
    return firstAction;
  }
  const firstReason = String(reasons[0] || "").trim();
  if (firstReason) {
    return firstReason;
  }
  return locale === "zh-CN" ? "这条运行需要你先拍板后再继续。" : "This run needs a human decision before it can continue.";
}

function humanizeOperationalIssue(errorText: string, locale: "en" | "zh-CN"): string {
  if (isAuthRelatedError(errorText)) {
    return locale === "zh-CN"
      ? "认证或权限状态异常，请先确认当前登录态。"
      : "Authentication or permission issue. Confirm the current sign-in state.";
  }
  return errorText;
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
  const queueFetchFallback = locale === "zh-CN" ? "待审批队列读取失败" : "Pending approvals queue fetch failed";
  const approvalFailedFallback = locale === "zh-CN" ? "审批失败" : "Approval failed";
  const roleGateReason = hasMutationRole
    ? ""
    : locale === "zh-CN"
      ? "当前环境没有启用可执行的审批权限，所以这张桌面暂时只能只读查看。"
      : "This environment does not have an executable approval role yet, so this desk is currently read-only.";
  const queueState = inferQueueUiState(pendingLoading, pendingError, pending.length);
  const queueBadge = queueBadgeMeta(queueState, pending.length, {
    loading: approvalCopy.queueLoadingBadge,
    error: approvalCopy.queueLoadFailedBadge,
    idle: approvalCopy.queueIdleBadge,
    pending: approvalCopy.queuePendingBadge,
  });
  const hasPendingLoadError = Boolean(pendingError);
  const pendingErrorIsAuth = pendingError ? isAuthRelatedError(pendingError) : false;
  const showRecoveryChamber = hasPendingLoadError && pending.length === 0;

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
      const normalizedError = sanitizeUiError(err, queueFetchFallback);
      const isAuthError = isAuthRelatedError(normalizedError);
      const displayError = humanizeOperationalIssue(normalizedError, locale);
      setPendingError(displayError);
      setPending([]);
      if (!preserveStatus) {
        setStatusTone("error");
        setStatus(
          trigger === "retry"
            ? approvalCopy.statusRetryFailed(displayError, isAuthError)
            : approvalCopy.statusRefreshFailed(displayError, isAuthError),
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
      setStatus(approvalCopy.statusFailed(humanizeOperationalIssue(sanitizeUiError(err, approvalFailedFallback), locale)));
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

  const localeRef = useRef(locale);
  useEffect(() => {
    if (localeRef.current === locale) {
      return;
    }
    localeRef.current = locale;
    void loadPending({ preserveStatus: false, trigger: "refresh" });
  }, [locale]);

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
      setStatus(approvalCopy.statusFailed(humanizeOperationalIssue(sanitizeUiError(err, approvalFailedFallback), locale)));
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
      <div className="compare-signal-grid">
        <div className="compare-signal-card">
          <span className="cell-sub mono muted">{locale === "zh-CN" ? "待审批数量" : "Pending approvals"}</span>
          <strong>{pending.length}</strong>
          <span className="muted">
            {locale === "zh-CN"
              ? "先处理这里，再决定是否继续派更多任务。"
              : "Decide here before you allow more work to continue."}
          </span>
        </div>
        <div className="compare-signal-card">
          <span className="cell-sub mono muted">{locale === "zh-CN" ? "审批权限" : "Approval authority"}</span>
          <strong>{normalizedRole || approvalCopy.operatorRoleUnconfigured}</strong>
          <span className="muted">
            {hasMutationRole
              ? locale === "zh-CN"
                ? "当前环境允许你做真实审批动作。"
                : "This environment allows real approval actions."
              : locale === "zh-CN"
                ? "当前只允许只读查看，不能直接放行。"
                : "This environment is read-only right now."}
          </span>
        </div>
        <div className="compare-signal-card">
          <span className="cell-sub mono muted">{locale === "zh-CN" ? "读回状态" : "Read-back state"}</span>
          <strong>{queueBadge.text}</strong>
          <span className="muted">
            {hasPendingLoadError
              ? locale === "zh-CN"
                ? "先恢复连接或权限，再继续做审批。"
                : "Restore connectivity or permissions before continuing."
              : locale === "zh-CN"
                ? "队列安静不代表以后都不需要人工拍板。"
                : "A quiet queue does not mean approvals are globally done."}
          </span>
        </div>
      </div>
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

      {hasPendingLoadError ? (
        showRecoveryChamber ? (
          <div className="god-mode-recovery-grid">
            <Card variant="detail" className="god-mode-recovery-card" role="alert" aria-live="assertive">
              <div className="stack-gap-2">
                <span className="cell-sub mono muted">
                  {locale === "zh-CN" ? "待审批真相" : "Approval truth"}
                </span>
                <strong className="god-mode-recovery-title">
                  {locale === "zh-CN" ? "当前还不能直接做审批" : "Approval cannot continue yet"}
                </strong>
                <p className="god-mode-recovery-desc">
                  {approvalCopy.pendingTruthUnavailable(String(pendingError || ""))}
                </p>
                <p className="mono muted">
                  {approvalCopy.recoveryTip}
                </p>
              </div>
            </Card>
            <Card variant="detail" className="god-mode-recovery-card">
              <div className="stack-gap-3">
                <div className="stack-gap-1">
                  <span className="cell-sub mono muted">
                    {locale === "zh-CN" ? "恢复动作" : "Recovery actions"}
                  </span>
                  <strong className="god-mode-recovery-title">
                    {locale === "zh-CN" ? "先把连接和权限恢复" : "Restore connectivity and permissions first"}
                  </strong>
                </div>
                <span className="mono muted" data-testid="god-mode-last-attempt-at">
                  {approvalCopy.lastAttemptPrefix} {formatDashboardDateTime(pendingLastAttemptAt, locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}
                </span>
                <div className="toolbar">
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
            </Card>
          </div>
        ) : (
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
        )
      ) : null}

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
                <div className="god-mode-item-heading">
                  <strong className="god-mode-item-title">{approvalHeadline(item, locale)}</strong>
                  <span className="mono muted">
                    {locale === "zh-CN" ? "运行 ID" : "Run ID"} {String(item.run_id || "-")}
                  </span>
                </div>
                <Badge variant="warning">{approvalStatusLabel(String(item.status || ""), locale)}</Badge>
              </div>
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

      <details className="god-mode-manual-shell" open={Boolean(runId)}>
        <summary className="god-mode-manual-summary">
          {locale === "zh-CN" ? "手动处理特定运行" : "Handle a specific run manually"}
        </summary>
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
      </details>
      {status && !hasPendingLoadError && (
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
