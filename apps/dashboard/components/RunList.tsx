import Link from "next/link";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import {
  formatDashboardDateTime,
  type UiLocale,
  statusDotClass,
  statusLabel,
  statusVariant,
} from "../lib/statusPresentation";
import type { RunSummary } from "../lib/types";

function formatRole(role: unknown, agentId: unknown): string {
  const roleText = typeof role === "string" && role.trim() ? role.trim() : "-";
  const agentText = typeof agentId === "string" && agentId.trim() ? agentId.trim() : "";
  return agentText ? `${roleText} (${agentText})` : roleText;
}

type RunListLocale = UiLocale;

function formatTime(value: string, locale: RunListLocale): string {
  return formatDashboardDateTime(value, locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function humanizeToken(value: string | undefined): string {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "";
  }
  return normalized
    .toLowerCase()
    .split(/[_-]+/)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function runListText(locale: RunListLocale) {
  if (locale === "zh-CN") {
    return {
      caption: "Run 列表，突出操作者席位、Proof 姿态与下一步动作。",
      headers: {
        run: "Run",
        operator: "操作者姿态",
        proof: "Proof 姿态",
        next: "下一步",
        updated: "最近更新",
      },
      runTaskPrefix: "Task",
      workflowPrefix: "Workflow",
      ownerPrefix: "Owner",
      assigneePrefix: "Assignee",
      noOutcome: "当前还没有 outcome posture。",
      runningOutcome: "证据仍在形成中。",
      failedOutcome: "当前 Run 仍有 proof gap。",
      completedOutcome: "结果已进入可复核 proof 姿态。",
      neutralOutcome: "当前 Run 还没有明确 proof posture。",
      noAdditionalProof: "当前没有额外的 failure 或 root-event 摘要。",
      nextOpenRun: "打开 Run Detail",
      nextOpenProof: "打开 Proof & Replay",
      nextMonitorRun: "监看活跃 Run",
      nextReviewProof: "复核 proof 与 outcome",
      nextFallback: "检查 Run 详情",
      nextOpenEvents: "打开事件时间线",
      noHint: "当前没有显式 action hint。",
      noRunAction: "Run 还没有稳定 ID，先回到上游任务确认。",
    };
  }
  return {
    caption: "Run list with operator ownership, proof posture, and the next command-tower action.",
    headers: {
      run: "Run",
      operator: "Operator posture",
      proof: "Proof posture",
      next: "Next operator action",
      updated: "Updated",
    },
    runTaskPrefix: "Task",
    workflowPrefix: "Workflow",
    ownerPrefix: "Owner",
    assigneePrefix: "Assignee",
    noOutcome: "No explicit outcome posture is attached yet.",
    runningOutcome: "Evidence is still forming on this run.",
    failedOutcome: "This run still has an open proof gap.",
    completedOutcome: "The outcome is ready for proof review.",
    neutralOutcome: "This run has not reported a clear proof posture yet.",
    noAdditionalProof: "No extra failure or root-event summary is attached.",
    nextOpenRun: "Open run detail",
    nextOpenProof: "Open Proof & Replay",
    nextMonitorRun: "Monitor live run",
    nextReviewProof: "Review proof and outcome",
    nextFallback: "Inspect run detail",
    nextOpenEvents: "Open event timeline",
    noHint: "No explicit operator hint is attached yet.",
    noRunAction: "This row does not have a stable run id yet. Confirm the upstream task first.",
  };
}

function deriveProofPrimary(run: RunSummary, locale: RunListLocale, text: ReturnType<typeof runListText>): string {
  const outcomeLabel = String(run.outcome_label_zh || "").trim();
  if (outcomeLabel) {
    return outcomeLabel;
  }
  const outcomeTypeLabel = humanizeToken(run.outcome_type);
  if (outcomeTypeLabel) {
    return outcomeTypeLabel;
  }
  const statusView = statusVariant(run?.status);
  if (statusView === "failed") return text.failedOutcome;
  if (statusView === "running") return text.runningOutcome;
  if (statusView === "success") return text.completedOutcome;
  return text.neutralOutcome;
}

function deriveProofSecondary(run: RunSummary, proofPrimary: string, text: ReturnType<typeof runListText>): string {
  const candidates = [
    String(run.failure_summary_zh || "").trim(),
    String(run.failure_reason || "").trim(),
    String(run.root_event || "").trim(),
    String(run.failure_stage || "").trim(),
  ].filter(Boolean);
  const distinct = candidates.find((value) => value !== proofPrimary);
  return distinct || text.noAdditionalProof;
}

function deriveNextAction(run: RunSummary, locale: RunListLocale, text: ReturnType<typeof runListText>): string {
  const explicitHint = String(run.action_hint_zh || "").trim();
  if (explicitHint) {
    return explicitHint;
  }
  const statusView = statusVariant(run?.status);
  if (statusView === "failed") return text.nextOpenProof;
  if (statusView === "running") return text.nextMonitorRun;
  if (statusView === "success") return text.nextReviewProof;
  return text.nextFallback;
}

export default function RunList({ runs, locale = "en" }: { runs: RunSummary[]; locale?: RunListLocale }) {
  if (!runs || runs.length === 0) {
    return (
      <Card>
        <div className="empty-state-stack">
          <span className="muted">No runs yet.</span>
          <span className="mono muted">Next: create a task from the PM page. It will appear here automatically.</span>
          <Button asChild variant="default">
            <Link href="/pm">Create your first task in PM</Link>
          </Button>
        </div>
      </Card>
    );
  }

  const text = runListText(locale);

  return (
    <Card variant="table">
      <table className="run-table">
        <caption className="sr-only">{text.caption}</caption>
        <thead>
          <tr>
            <th scope="col">{text.headers.run}</th>
            <th scope="col">{text.headers.operator}</th>
            <th scope="col">{text.headers.proof}</th>
            <th scope="col">{text.headers.next}</th>
            <th scope="col">{text.headers.updated}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run, index) => {
            const runId = typeof run?.run_id === "string" ? run.run_id.trim() : "";
            const hasRunId = Boolean(runId);
            const runIdText = hasRunId ? runId : "unknown-run";
            const runIdDisplay = runIdText.length > 12 ? `${runIdText.slice(0, 12)}...` : runIdText;
            const taskId = typeof run?.task_id === "string" && run.task_id.trim() ? run.task_id : "-";
            const statusText = statusLabel(run?.status, locale);
            const workflowText = run.workflow_status || "-";
            const startTimeText = run.created_at || run.start_ts || "-";
            const ownerText = formatRole(run.owner_role, run.owner_agent_id);
            const assignedText = formatRole(run.assigned_role, run.assigned_agent_id);
            const lastEventText = run.last_event_ts || "-";
            const statusView = statusVariant(run?.status);
            const proofPrimary = deriveProofPrimary(run, locale, text);
            const proofSecondary = deriveProofSecondary(run, proofPrimary, text);
            const nextActionText = deriveNextAction(run, locale, text);
            const rowClass = statusView === "failed"
              ? "session-row--failed"
              : statusView === "warning"
                ? "session-row--blocked"
                : statusView === "running"
                  ? "session-row--running"
                  : "";

            return (
              <tr key={`${runIdText || "unknown-run"}-${index}`} className={rowClass}>
                <th scope="row">
                  {hasRunId ? (
                    <Link href={`/runs/${encodeURIComponent(runIdText)}`} className="run-link">
                      {runIdDisplay}
                    </Link>
                  ) : (
                    <span className="run-link muted" aria-disabled="true">{runIdDisplay}</span>
                  )}
                  <span className="cell-sub mono muted">{`${text.runTaskPrefix}: ${taskId}`}</span>
                  <span className="cell-sub mono muted">{`${text.workflowPrefix}: ${workflowText}`}</span>
                </th>
                <td>
                  <span className="status-inline">
                    <span className={statusDotClass(run?.status)} aria-hidden="true" />
                    <Badge variant={statusView}>{statusText}</Badge>
                  </span>
                  <span className="cell-sub mono muted">
                    {`${text.ownerPrefix}: ${ownerText}${assignedText !== "-" ? ` · ${text.assigneePrefix}: ${assignedText}` : ""}`}
                  </span>
                </td>
                <td>
                  <span className={`mono ${statusView === "failed" ? "cell-danger" : "cell-primary"}`}>{proofPrimary}</span>
                  <span className="cell-sub mono muted">{proofSecondary}</span>
                </td>
                <td>
                  <span className="mono">{hasRunId ? nextActionText : text.noRunAction}</span>
                  <span className="cell-sub mono inline-stack">
                    {hasRunId ? (
                      <>
                        <Button asChild variant={statusView === "failed" ? "warning" : "secondary"}>
                          <Link href={`/runs/${encodeURIComponent(runIdText)}`}>
                            {statusView === "failed" ? text.nextOpenProof : text.nextOpenRun}
                          </Link>
                        </Button>
                        {statusView === "failed" ? (
                          <Button asChild variant="ghost">
                            <Link href={`/events?run_id=${encodeURIComponent(runIdText)}`}>{text.nextOpenEvents}</Link>
                          </Button>
                        ) : null}
                      </>
                    ) : (
                      <span className="muted">{text.noHint}</span>
                    )}
                  </span>
                </td>
                <td>
                  <span className="mono">{formatTime(lastEventText !== "-" ? lastEventText : startTimeText, locale)}</span>
                  <span className="cell-sub mono muted">{statusView === "failed" ? nextActionText : proofPrimary}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
