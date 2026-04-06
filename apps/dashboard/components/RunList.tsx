import Link from "next/link";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import {
  type UiLocale,
  formatDashboardDateTime,
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

  return (
    <Card variant="table">
      <table className="run-table">
        <caption className="sr-only">Run list with run identifiers, task context, status flow, role ownership, and failure triage details.</caption>
        <thead>
          <tr>
            <th scope="col">Run ID</th>
            <th scope="col">Status</th>
            <th scope="col">Failure triage</th>
            <th scope="col">Updated at</th>
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
            const failureSummaryText = run.failure_summary_zh || run.failure_reason || "-";
            const actionHintText = run.action_hint_zh || "-";
            const statusView = statusVariant(run?.status);
            const summaryText = failureSummaryText !== "-" ? failureSummaryText : actionHintText;
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
                  <span className="cell-sub mono muted">{`Task: ${taskId}`}</span>
                </th>
                <td>
                  <span className="status-inline">
                    <span className={statusDotClass(run?.status)} aria-hidden="true" />
                    <Badge variant={statusView}>{statusText}</Badge>
                  </span>
                  <span className="cell-sub mono muted">{`Owner: ${ownerText}${assignedText !== "-" ? ` · Assignee: ${assignedText}` : ""}`}</span>
                </td>
                <td>
                  {statusView === "failed" ? (
                    <>
                      <span className={`mono ${summaryText !== "-" ? "cell-danger" : "muted"}`}>
                        {summaryText !== "-" ? summaryText : "No failure summary provided"}
                      </span>
                    </>
                  ) : (
                    <span className="mono muted">-</span>
                  )}
                  {statusView === "failed" && hasRunId ? (
                    <span className="cell-sub mono inline-stack">
                      <Button asChild variant="warning">
                        <Link href={`/events?run_id=${encodeURIComponent(runIdText)}`}>Open triage</Link>
                      </Button>
                    </span>
                  ) : null}
                </td>
                <td>
                  <span className="mono">{formatTime(lastEventText !== "-" ? lastEventText : startTimeText, locale)}</span>
                  <span className="cell-sub mono muted">{workflowText}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
