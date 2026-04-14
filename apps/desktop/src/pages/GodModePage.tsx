import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import type { JsonValue } from "../lib/types";
import { approveGodMode, fetchPendingApprovals } from "../lib/api";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";

type GodModePageProps = {
  locale?: UiLocale;
};

export function GodModePage({ locale = DEFAULT_UI_LOCALE }: GodModePageProps) {
  const approvalCopy = getUiCopy(locale).desktop.approval;
  const [pending, setPending] = useState<Array<Record<string, JsonValue>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [manualRunId, setManualRunId] = useState("");
  const [manualStatus, setManualStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [confirmRunId, setConfirmRunId] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const manualRunIdInputId = "god-mode-manual-run-id";
  const confirmDialogRef = useRef<HTMLDivElement | null>(null);
  const confirmCancelButtonRef = useRef<HTMLButtonElement | null>(null);
  const confirmTriggerRef = useRef<HTMLElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchPendingApprovals();
      setPending(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleApprove(runId: string) {
    setActionBusy(true);
    setConfirmRunId(null);
    try {
      await approveGodMode(runId);
      toast.success(approvalCopy.approvedToast(runId));
      void load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    } finally {
      setActionBusy(false);
    }
  }

  async function handleManualApprove() {
    if (!manualRunId.trim()) return;
    setActionBusy(true);
    setManualStatus(null);
    try {
      const trimmedRunId = manualRunId.trim();
      await approveGodMode(trimmedRunId);
      setManualStatus({ ok: true, msg: approvalCopy.approvedToast(trimmedRunId) });
      setManualRunId("");
      void load();
    } catch (err) {
      setManualStatus({ ok: false, msg: err instanceof Error ? err.message : String(err) });
    } finally {
      setActionBusy(false);
    }
  }

  function openConfirmDialog(runId: string) {
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement) {
      confirmTriggerRef.current = activeElement;
    }
    setConfirmRunId(runId);
  }

  function closeConfirmDialog() {
    setConfirmRunId(null);
  }

  useEffect(() => {
    if (!confirmRunId) {
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
        setConfirmRunId(null);
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
  }, [confirmRunId]);

  return (
    <div className="content">
      <div className="section-header">
        <div>
          <h2 className="page-title">{approvalCopy.pageTitle}</h2>
          <p className="page-subtitle">{approvalCopy.pageSubtitle}</p>
        </div>
        <Button onClick={load}>{approvalCopy.refresh}</Button>
      </div>
      <div className="alert alert-warning">
        {approvalCopy.warningBanner}
      </div>
      {error && <div className="alert alert-danger">Pending approvals queue is temporarily unavailable: {error}</div>}

      <div className="god-mode-panel">
        <div className="god-mode-header">
          <h2>{approvalCopy.queueTitle}</h2>
          <Badge variant="warning">{approvalCopy.pendingBadge(pending.length)}</Badge>
        </div>
        {loading ? (
          <div className="skeleton-stack">
            <div className="skeleton skeleton-card-tall" />
          </div>
        ) : pending.length === 0 ? (
          <div className="empty-state-stack">
            <p className="muted">{approvalCopy.noPendingText}</p>
          </div>
        ) : (
          <div className="god-mode-queue">
            {pending.map((item, i) => {
              const runId = String(item.run_id || "");
              const approvalPack = item.approval_pack && typeof item.approval_pack === "object"
                ? (item.approval_pack as Record<string, unknown>)
                : null;
              const approvalSummary = approvalPack ? String(approvalPack.summary || "").trim() : "";
              return (
                <div key={i} className="god-mode-item">
                  <div className="god-mode-item-header">
                    <code>{runId || `Task ${i + 1}`}</code>
                    <Badge variant="failed">{approvalCopy.criticalBadge}</Badge>
                  </div>
                  {approvalSummary ? (
                    <div className="god-mode-detail">
                      <span className="god-mode-detail-label">{approvalCopy.summaryLabel}</span>
                      <span>{approvalSummary}</span>
                    </div>
                  ) : null}
                  {item.task_id && (
                    <div className="god-mode-detail">
                      <span className="god-mode-detail-label">{approvalCopy.taskIdLabel}</span>
                      <span className="mono">{String(item.task_id)}</span>
                    </div>
                  )}
                  {item.failure_reason && (
                    <div className="god-mode-detail">
                      <span className="god-mode-detail-label">{approvalCopy.failureReasonLabel}</span>
                      <span className="cell-danger">{String(item.failure_reason)}</span>
                    </div>
                  )}
                  <Button
                    variant="primary"
                    className="god-mode-approve-btn"
                    disabled={actionBusy}
                    onClick={() => openConfirmDialog(runId)}
                  >
                    {approvalCopy.approveExecution}
                  </Button>
                </div>
              );
            })}
          </div>
        )}

        <div className="god-mode-manual">
          <h3 className="god-mode-manual-title">{approvalCopy.manualInputTitle}</h3>
          <p className="god-mode-hint">{approvalCopy.manualInputHint}</p>
          <div className="god-mode-input-row">
            <label htmlFor={manualRunIdInputId} className="sr-only">{approvalCopy.runIdLabel}</label>
            <Input
              id={manualRunIdInputId}
              name="run_id"
              placeholder={approvalCopy.runIdPlaceholder}
              value={manualRunId}
              onChange={(e) => setManualRunId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleManualApprove();
              }}
            />
            <Button variant="primary" disabled={actionBusy || !manualRunId.trim()} onClick={handleManualApprove}>
              {approvalCopy.approve}
            </Button>
          </div>
          {manualStatus && <div className={`god-mode-status ${manualStatus.ok ? "" : "is-error"}`}>{manualStatus.msg}</div>}
        </div>
      </div>

      {confirmRunId && (
        <div className="god-mode-confirm-overlay">
          <Button
            variant="unstyled"
            className="god-mode-confirm-backdrop"
            aria-label={approvalCopy.closeConfirmDialogAriaLabel}
            onClick={closeConfirmDialog}
          />
          <div
            className="god-mode-confirm-card"
            role="dialog"
            aria-modal="true"
            aria-label={approvalCopy.confirmDialogAriaLabel}
            ref={confirmDialogRef}
            tabIndex={-1}
          >
            <h3>{approvalCopy.confirmTitle}</h3>
            <p>{approvalCopy.confirmDescription(confirmRunId)}</p>
            <div className="god-mode-confirm-actions">
              <Button ref={confirmCancelButtonRef} onClick={closeConfirmDialog}>{approvalCopy.cancel}</Button>
              <Button variant="primary" disabled={actionBusy} onClick={() => handleApprove(confirmRunId)}>
                {approvalCopy.confirmApproval}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
