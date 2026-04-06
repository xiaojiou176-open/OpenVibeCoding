import { cookies } from "next/headers";
import type { Metadata } from "next";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import Link from "next/link";
import type { BadgeVariant } from "../../components/ui/badge";
import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { fetchQueue, fetchWorkflows } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import { statusLabel } from "../../lib/statusPresentation";
import WorkflowQueueMutationControls from "./WorkflowQueueMutationControls";

export const metadata: Metadata = {
  title: "Workflow Cases | CortexPilot",
  description:
    "Review Workflow Cases, queue posture, linked runs, and next operator actions inside the CortexPilot Command Tower.",
};

function statusBadgeVariant(status: string | undefined): BadgeVariant {
  const s = String(status || "").toLowerCase();
  if (["success", "done", "passed", "completed"].includes(s)) return "success";
  if (["failed", "failure", "error"].includes(s)) return "failed";
  if (["running", "active", "in_progress"].includes(s)) return "running";
  if (["blocked", "warning", "paused"].includes(s)) return "warning";
  return "default";
}

export default async function WorkflowsPage() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const workflowListPageCopy = getUiCopy(locale).dashboard.workflowListPage;
  const { data: workflows, warning } = await safeLoad(fetchWorkflows, [] as Record<string, unknown>[], "Workflow list");
  const { data: queueItems } = await safeLoad(fetchQueue, [] as Record<string, unknown>[], "Queue list");

  const queueByWorkflow = new Map<string, Array<Record<string, unknown>>>();
  for (const item of queueItems) {
    const workflowId = String(item.workflow_id || "").trim();
    if (!workflowId) {
      continue;
    }
    queueByWorkflow.set(workflowId, [...(queueByWorkflow.get(workflowId) || []), item]);
  }
  const eligibleQueueCount = queueItems.filter((item) => {
    if (Boolean(item.eligible) || String(item.queue_state || "") === "eligible") {
      return true;
    }
    const status = String(item.status || "").toUpperCase();
    return status === "PENDING";
  }).length;
  const atRiskQueueCount = queueItems.filter((item) => {
    const state = String(item.sla_state || "").toLowerCase();
    return state === "at_risk" || state === "breached";
  }).length;
  const queuedWorkflowCount = new Set(
    queueItems.map((item) => String(item.workflow_id || "").trim()).filter(Boolean),
  ).size;
  const recommendedActionText =
    eligibleQueueCount > 0
      ? workflowListPageCopy.recommendedActions.runNext
      : queueItems.length > 0
      ? workflowListPageCopy.recommendedActions.reviewTiming
      : workflows.length > 0
      ? workflowListPageCopy.recommendedActions.openWorkflow
      : workflowListPageCopy.recommendedActions.createFirstWorkflow;

  return (
    <main className="grid" aria-labelledby="workflows-page-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="workflows-page-title" className="page-title">{workflowListPageCopy.title}</h1>
            <p className="page-subtitle">{workflowListPageCopy.subtitle}</p>
          </div>
          <Badge>{workflowListPageCopy.countsBadge(workflows.length, queueItems.length)}</Badge>
        </div>
        <WorkflowQueueMutationControls queueCount={queueItems.length} eligibleCount={eligibleQueueCount} compact />
      </header>
      <section className="stats-grid" aria-label={workflowListPageCopy.summaryAriaLabel}>
        <article className="metric-card">
          <p className="metric-label">{workflowListPageCopy.metricLabels.workflowCases}</p>
          <p className="metric-value">{workflows.length}</p>
          <p className="cell-sub mono muted">{workflowListPageCopy.casesWithQueuedWork(queuedWorkflowCount)}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{workflowListPageCopy.metricLabels.queueSla}</p>
          <p className="metric-value">{queueItems.length}</p>
          <p className="cell-sub mono muted">{workflowListPageCopy.eligibleNow(eligibleQueueCount, atRiskQueueCount)}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{workflowListPageCopy.metricLabels.nextRecommendedAction}</p>
          <p className="cell-sub mono muted">{recommendedActionText}</p>
        </article>
      </section>
      <section className="app-section" aria-label="Workflow list">
        {warning ? <p className="alert alert-warning" role="status">{warning}</p> : null}
        {workflows.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">{workflowListPageCopy.emptyTitle}</span>
              <span className="mono muted">{workflowListPageCopy.emptyHint}</span>
            </div>
          </Card>
        ) : (
          <Card variant="table">
            <table className="run-table">
              <caption className="sr-only">{workflowListPageCopy.tableCaption}</caption>
              <thead>
                <tr>
                  <th scope="col">{workflowListPageCopy.tableHeaders.workflowId}</th>
                  <th scope="col">{workflowListPageCopy.tableHeaders.status}</th>
                  <th scope="col">{workflowListPageCopy.tableHeaders.namespace}</th>
                  <th scope="col">{workflowListPageCopy.tableHeaders.taskQueue}</th>
                  <th scope="col">{workflowListPageCopy.tableHeaders.runs}</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((workflow: Record<string, unknown>) => {
                  const wfId = String(workflow.workflow_id || "-");
                  const runs = Array.isArray(workflow.runs) ? workflow.runs : [];
                  const queueItemsForWorkflow = queueByWorkflow.get(wfId) || [];
                  const objective = String(workflow.objective || "").trim();
                  const verdict = String(workflow.verdict || "").trim();
                  return (
                    <tr key={wfId}>
                      <th scope="row">
                        <Link href={`/workflows/${encodeURIComponent(wfId)}`} className="run-link">
                          {wfId.length > 20 ? `${wfId.slice(0, 20)}...` : wfId}
                        </Link>
                        {objective ? (
                          <span className="cell-sub mono muted">{objective}</span>
                        ) : null}
                      </th>
                      <td>
                        <Badge variant={statusBadgeVariant(workflow.status as string)}>
                          {statusLabel(workflow.status as string, locale)}
                        </Badge>
                        {verdict ? <span className="cell-sub mono muted">{workflowListPageCopy.verdictPrefix}: {verdict}</span> : null}
                      </td>
                      <td><span className="mono">{String(workflow.namespace || "-")}</span></td>
                      <td><span className="mono">{String(workflow.task_queue || "-")}</span></td>
                      <td>
                        <span className="cell-primary">{runs.length}</span>
                        {runs.slice(0, 2).map((run: Record<string, unknown>) => (
                          <span key={String(run.run_id)} className="cell-sub mono muted">
                            <Link href={`/runs/${encodeURIComponent(String(run.run_id || ""))}`} className="run-link">{String(run.run_id).slice(0, 10)}</Link>
                          </span>
                        ))}
                        {queueItemsForWorkflow.length > 0 ? (
                          <span className="cell-sub mono muted">
                            {workflowListPageCopy.queueSummary(
                              queueItemsForWorkflow.length,
                              String(queueItemsForWorkflow[0]?.sla_state || "-"),
                            )}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </main>
  );
}
