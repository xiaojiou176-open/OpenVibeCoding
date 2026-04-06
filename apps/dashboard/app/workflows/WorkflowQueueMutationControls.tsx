"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import { useDashboardLocale } from "../../components/DashboardLocaleContext";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { enqueueRunQueue, mutationExecutionCapability, runNextQueue } from "../../lib/api";

type Props = {
  latestRunId?: string;
  queueCount?: number;
  eligibleCount?: number;
  showQueueLatest?: boolean;
  compact?: boolean;
  disableRunNextWhenEmpty?: boolean;
  locale?: UiLocale;
};

function toUtcIsoOrEmpty(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const parsed = new Date(trimmed);
  return Number.isNaN(parsed.getTime()) ? "" : parsed.toISOString();
}

export default function WorkflowQueueMutationControls({
  latestRunId = "",
  queueCount = 0,
  eligibleCount = 0,
  showQueueLatest,
  compact = false,
  disableRunNextWhenEmpty = false,
  locale,
}: Props) {
  const { locale: dashboardLocale } = useDashboardLocale();
  const effectiveLocale = locale ?? dashboardLocale ?? DEFAULT_UI_LOCALE;
  const router = useRouter();
  const workflowDetailCopy = getUiCopy(effectiveLocale).desktop.workflowDetail;
  const [queuePriority, setQueuePriority] = useState("0");
  const [queueScheduledAt, setQueueScheduledAt] = useState("");
  const [queueDeadlineAt, setQueueDeadlineAt] = useState("");
  const [actionNotice, setActionNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyAction, setBusyAction] = useState<"queue" | "run-next" | "">("");
  const [, startRefresh] = useTransition();

  const mutationCapability = useMemo(() => mutationExecutionCapability(), []);
  const hasMutationRole = mutationCapability.executable;
  const operatorRole = mutationCapability.operatorRole || "";
  const roleGateReason = hasMutationRole
    ? ""
    : workflowDetailCopy.roleGateReason;
  const canQueueLatest = typeof showQueueLatest === "boolean" ? showQueueLatest : Boolean(latestRunId);

  async function refreshSurface() {
    startRefresh(() => {
      router.refresh();
    });
  }

  async function handleRunNextQueue() {
    if (!hasMutationRole) {
      setActionError(roleGateReason);
      setActionNotice("");
      return;
    }
    setBusyAction("run-next");
    setActionError("");
    setActionNotice("");
    try {
      const result = await runNextQueue({});
      if (result?.ok) {
        setActionNotice(workflowDetailCopy.startedNotice(String(result.run_id || "-")));
        await refreshSurface();
        return;
      }
      setActionError(String(result?.reason || workflowDetailCopy.queueEmptyReason));
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  }

  async function handleQueueLatestRun() {
    if (!latestRunId) {
      setActionError(workflowDetailCopy.noRunAvailable);
      setActionNotice("");
      return;
    }
    if (!hasMutationRole) {
      setActionError(roleGateReason);
      setActionNotice("");
      return;
    }
    setBusyAction("queue");
    setActionError("");
    setActionNotice("");
    try {
      const priority = Number.parseInt(queuePriority, 10);
      const payload: Record<string, string | number> = {};
      if (Number.isFinite(priority)) {
        payload.priority = priority;
      }
      const scheduledAtIso = toUtcIsoOrEmpty(queueScheduledAt);
      if (queueScheduledAt && !scheduledAtIso) {
        throw new Error(workflowDetailCopy.invalidScheduledAt);
      }
      if (scheduledAtIso) {
        payload.scheduled_at = scheduledAtIso;
      }
      const deadlineAtIso = toUtcIsoOrEmpty(queueDeadlineAt);
      if (queueDeadlineAt && !deadlineAtIso) {
        throw new Error(workflowDetailCopy.invalidDeadlineAt);
      }
      if (deadlineAtIso) {
        payload.deadline_at = deadlineAtIso;
      }
      const result = await enqueueRunQueue(latestRunId, payload);
      setActionNotice(workflowDetailCopy.queuedNotice(String(result.task_id || latestRunId)));
      await refreshSurface();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyAction("");
    }
  }

  return (
    <div className="row-gap-2">
      {operatorRole ? (
        <p className="cell-sub mono muted">{workflowDetailCopy.operatorRoleLabel}: {operatorRole}</p>
      ) : (
        <p className="cell-sub mono muted">{roleGateReason}</p>
      )}
      <p className="cell-sub mono muted">{workflowDetailCopy.queueSummary(queueCount, eligibleCount)}</p>
      {!compact ? (
        <div className="row-gap-2">
          <Input
            type="number"
            aria-label={workflowDetailCopy.queuePriority}
            value={queuePriority}
            onChange={(event) => setQueuePriority(event.target.value)}
            placeholder={workflowDetailCopy.queuePriority}
          />
          <Input
            type="datetime-local"
            aria-label={workflowDetailCopy.queueScheduledAt}
            value={queueScheduledAt}
            onChange={(event) => setQueueScheduledAt(event.target.value)}
            placeholder={workflowDetailCopy.queueScheduledAt}
          />
          <Input
            type="datetime-local"
            aria-label={workflowDetailCopy.queueDeadlineAt}
            value={queueDeadlineAt}
            onChange={(event) => setQueueDeadlineAt(event.target.value)}
            placeholder={workflowDetailCopy.queueDeadlineAt}
          />
        </div>
      ) : null}
      <div className="toolbar">
        {canQueueLatest ? (
          <Button
            variant="secondary"
            onClick={() => void handleQueueLatestRun()}
            disabled={busyAction !== "" && busyAction !== "queue"}
          >
            {busyAction === "queue" ? workflowDetailCopy.queueingTask : workflowDetailCopy.queueLatestRun}
          </Button>
        ) : null}
        <Button
          variant={compact ? "default" : "secondary"}
          onClick={() => void handleRunNextQueue()}
          disabled={(busyAction !== "" && busyAction !== "run-next") || (disableRunNextWhenEmpty && queueCount === 0)}
        >
          {busyAction === "run-next" ? workflowDetailCopy.runningTask : workflowDetailCopy.runNextQueuedTask}
        </Button>
      </div>
      {actionNotice ? <div className="alert alert-warning">{actionNotice}</div> : null}
      {actionError ? <div className="alert alert-danger">{actionError}</div> : null}
    </div>
  );
}
