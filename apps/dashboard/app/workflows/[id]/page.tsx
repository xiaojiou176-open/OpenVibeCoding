import { cookies } from "next/headers";
import type { Metadata } from "next";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import Link from "next/link";
import EventTimeline from "../../../components/EventTimeline";
import type { BadgeVariant } from "../../../components/ui/badge";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card } from "../../../components/ui/card";
import ControlPlaneStatusCallout from "../../../components/control-plane/ControlPlaneStatusCallout";
import WorkflowOperatorCopilotPanel from "../../../components/control-plane/WorkflowOperatorCopilotPanel";
import { fetchQueue, fetchWorkflow } from "../../../lib/api";
import { safeLoad } from "../../../lib/serverPageData";
import { statusLabel } from "../../../lib/statusPresentation";
import type { QueueItemRecord, WorkflowDetailPayload } from "../../../lib/types";
import { formatBindingReadModelLabel, formatRoleBindingRuntimeSummary } from "../../../lib/types";
import WorkflowQueueMutationControls from "../WorkflowQueueMutationControls";

type WorkflowDetailPageParams = {
  id: string;
};

function safeDecodeParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function isWorkflowAtRisk(status: unknown): boolean {
  const normalized = String(status || "").trim().toUpperCase();
  if (!normalized) {
    return false;
  }
  return ["FAIL", "ERROR", "REJECT", "DENY", "TIMEOUT", "ROLLBACK", "ABORT", "BLOCK"].some((token) =>
    normalized.includes(token)
  );
}

function workflowRiskBadgeVariant(status: unknown): BadgeVariant {
  if (isWorkflowAtRisk(status)) {
    return "failed";
  }
  const normalized = String(status || "").trim().toUpperCase();
  if (!normalized) {
    return "warning";
  }
  if (["RUNNING", "ACTIVE", "PENDING", "QUEUED"].some((token) => normalized.includes(token))) {
    return "running";
  }
  if (["DONE", "SUCCESS", "COMPLETED", "APPROVED"].some((token) => normalized.includes(token))) {
    return "success";
  }
  return "default";
}

function workflowRunRowKey(run: Record<string, unknown>, index: number): string {
  return [
    String(run.run_id || "no-run-id"),
    String(run.created_at || "no-created-at"),
    String(run.status || "no-status"),
    String(index),
  ].join(":");
}

function resolveLatestRunId(runs: Array<Record<string, unknown>>): string {
  const sortedRuns = [...runs];
  sortedRuns.sort((left, right) => {
    const leftTs = Date.parse(String(left.created_at || ""));
    const rightTs = Date.parse(String(right.created_at || ""));
    return (Number.isFinite(rightTs) ? rightTs : 0) - (Number.isFinite(leftTs) ? leftTs : 0);
  });
  return String(sortedRuns[0]?.run_id || "").trim();
}

export async function generateMetadata({
  params,
}: {
  params: Promise<WorkflowDetailPageParams>;
}): Promise<Metadata> {
  const { id } = await params;
  const workflowId = safeDecodeParam(id);
  const titleSuffix = workflowId ? ` · ${workflowId}` : "";
  return {
    title: `Workflow Case detail${titleSuffix} | OpenVibeCoding`,
    description:
      "Inspect one Workflow Case across risk, queue posture, linked runs, event timeline, and the next operator action inside the OpenVibeCoding command tower.",
  };
}

export default async function WorkflowDetailPage({
  params,
}: {
  params: Promise<WorkflowDetailPageParams>;
}) {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const uiCopy = getUiCopy(locale);
  const workflowDetailPageCopy = uiCopy.dashboard.workflowDetailPage;
  const workflowDetailCopy = uiCopy.desktop.workflowDetail;
  const { id } = await params;
  const workflowId = safeDecodeParam(id);
  const { data: payload, warning } = await safeLoad<WorkflowDetailPayload>(
    () => fetchWorkflow(workflowId),
    { workflow: { workflow_id: workflowId }, runs: [], events: [] },
    "Workflow detail",
  );
  const { data: queueItems } = await safeLoad<QueueItemRecord[]>(
    () => fetchQueue(workflowId),
    [],
    "Queue detail",
  );
  const workflow = payload.workflow ?? { workflow_id: workflowId };
  const runs = Array.isArray(payload.runs) ? payload.runs : [];
  const events = Array.isArray(payload.events) ? payload.events : [];
  const workflowName = String(
    workflow.name || workflow.title || workflow.workflow_id || workflowId || "-",
  );
  const workflowStatus = statusLabel(String(workflow.status || ""), locale);
  const workflowUpdatedAt = String(workflow.updated_at || workflow.created_at || "-");
  const workflowRisk = isWorkflowAtRisk(workflow.status);
  const riskLabel = workflowRisk ? workflowDetailPageCopy.highRiskLabel : workflowDetailPageCopy.normalRiskLabel;
  const latestRunId = resolveLatestRunId(runs);
  const workflowCaseReadModel = workflow.workflow_case_read_model;
  const roleBindingSummary = workflowCaseReadModel?.role_binding_summary;
  const skillsBundle = roleBindingSummary?.skills_bundle_ref;
  const mcpBundle = roleBindingSummary?.mcp_bundle_ref;
  const sourceRunId = String(workflowCaseReadModel?.source_run_id || "").trim();
  const eligibleQueueCount = queueItems.filter((item) => {
    if (item.eligible === true || String(item.eligible || "").toLowerCase() === "true") {
      return true;
    }
    const status = String(item.status || "").toUpperCase();
    const queueState = String(item.queue_state || "").toLowerCase();
    return status === "PENDING" && (queueState === "" || queueState === "eligible");
  }).length;

  if (warning) {
    return (
      <main className="grid" aria-labelledby="workflow-detail-title">
        <header className="app-section">
          <div className="section-header">
            <div>
              <p className="cell-sub mono muted">OpenVibeCoding / workflow case detail</p>
              <h1 id="workflow-detail-title">{workflowDetailPageCopy.title}</h1>
              <p>{workflowDetailPageCopy.subtitle}</p>
            </div>
            <Badge className="mono">{workflowId}</Badge>
          </div>
        </header>
        <section className="app-section" aria-label="Workflow degraded state">
          <ControlPlaneStatusCallout
            title={workflowDetailPageCopy.degradedTitle}
            summary={warning}
            nextAction={workflowDetailPageCopy.degradedNextAction}
            tone="warning"
            badgeLabel={workflowDetailPageCopy.degradedBadge}
            actions={[
              { href: `/workflows/${encodeURIComponent(workflowId)}`, label: workflowDetailPageCopy.retryLoadAction },
              { href: "/workflows", label: workflowDetailPageCopy.backToWorkflowListAction },
            ]}
          />
          <div className="grid grid-3">
            <Card>
              <h3>{workflowDetailPageCopy.degradedIdentityTitle}</h3>
              <div className="mono">{workflowDetailPageCopy.caseFieldLabels.workflowId}: {workflowId}</div>
              <div className="mono">{workflowDetailPageCopy.caseFieldLabels.name}: {workflowName}</div>
              <div className="mono">{workflowDetailPageCopy.summaryStatus}: {workflowStatus}</div>
              <div className="mono">{workflowDetailPageCopy.caseFieldLabels.updatedAt}: {workflowUpdatedAt}</div>
              <Badge variant="warning">{workflowDetailPageCopy.degradedBadge}</Badge>
            </Card>
            <Card>
              <h3>{workflowDetailPageCopy.degradedRunMappingTitle}</h3>
              {runs.length === 0 ? (
                <div className="mono">{workflowDetailPageCopy.degradedRunMappingEmpty}</div>
              ) : (
                runs.map((run, index) => (
                  <div key={workflowRunRowKey(run, index)} className="mono">
                    {run.run_id} / {statusLabel(String(run.status || ""), locale)} / {run.created_at || "-"}
                  </div>
                ))
              )}
              <span className="mono muted">{workflowDetailPageCopy.degradedRunMappingReadonlyNote}</span>
            </Card>
            <Card>
              <h3>{workflowDetailPageCopy.degradedEventTimelineTitle}</h3>
              <EventTimeline events={events} />
              <span className="mono muted">{workflowDetailPageCopy.degradedEventTimelineReadonlyNote}</span>
            </Card>
          </div>
          <Card>
            <div className="toolbar mt-2">
              <Button asChild variant="secondary">
                <Link href={`/workflows/${encodeURIComponent(workflowId)}`}>{workflowDetailPageCopy.retryLoadAction}</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/workflows">{workflowDetailPageCopy.backToWorkflowListAction}</Link>
              </Button>
              <Button variant="ghost" disabled aria-disabled="true">
                {workflowDetailPageCopy.governanceEntryDisabled}
              </Button>
            </div>
          </Card>
        </section>
      </main>
    );
  }

  return (
    <main className="grid" aria-labelledby="workflow-detail-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <p className="cell-sub mono muted">OpenVibeCoding / workflow case detail</p>
            <h1 id="workflow-detail-title">{workflowDetailPageCopy.title}</h1>
            <p>{workflowDetailPageCopy.subtitle}</p>
          </div>
          <div className="toolbar" role="group" aria-label={workflowDetailPageCopy.riskSummaryAriaLabel}>
            <Badge className="mono">{workflow.workflow_id || workflowId}</Badge>
            <Badge variant={workflowRiskBadgeVariant(workflow.status)}>{riskLabel}</Badge>
            <Button asChild variant="secondary">
              <Link href={`/workflows/${encodeURIComponent(workflowId)}/share`}>{workflowDetailPageCopy.shareAssetCta}</Link>
            </Button>
          </div>
        </div>
      </header>
      <section className="stats-grid" aria-label="Workflow summary">
        <article className="metric-card">
          <p className="metric-label">{workflowDetailPageCopy.summaryStatus}</p>
          <p className={`metric-value ${workflowRisk ? "metric-value--danger" : "metric-value--primary"}`}>{workflowStatus}</p>
          <Badge variant={workflowRiskBadgeVariant(workflow.status)}>{riskLabel}</Badge>
        </article>
        <article className="metric-card">
          <p className="metric-label">{workflowDetailPageCopy.summaryRunMappings}</p>
          <p className="metric-value">{runs.length}</p>
          <p className="cell-sub mono muted">{workflowDetailPageCopy.summaryRunMappingsHint}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{workflowDetailPageCopy.summaryEvents}</p>
          <p className="metric-value">{events.length}</p>
          <p className="cell-sub mono muted">{workflowDetailPageCopy.summaryEventsHint}</p>
        </article>
      </section>
      <section className="app-section" aria-label="Workflow copilot">
        <WorkflowOperatorCopilotPanel workflowId={workflowId} />
      </section>
      <section className="app-section" aria-label="Workflow detail panels">
        <div className="grid grid-3">
          <Card>
            <h3>{workflowDetailCopy.nextOperatorActionTitle}</h3>
            <div className="mono">
              {queueItems.length > 0
                ? workflowDetailCopy.recommendedActionQueued
                : latestRunId
                ? workflowDetailCopy.recommendedActionNoQueue
                : workflowDetailCopy.recommendedActionNoRun}
            </div>
            <WorkflowQueueMutationControls
              latestRunId={latestRunId}
              queueCount={queueItems.length}
              eligibleCount={eligibleQueueCount}
              showQueueLatest
              disableRunNextWhenEmpty
              locale={locale}
            />
          </Card>
          <Card>
            <h3>{workflowDetailCopy.summaryTitle}</h3>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.workflowId}: {workflow.workflow_id || workflowId}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.name}: {workflowName}</div>
            <div className="mono">{workflowDetailPageCopy.summaryStatus}: {workflowStatus}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.updatedAt}: {workflowUpdatedAt}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.namespace}: {workflow.namespace || "-"}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.taskQueue}: {workflow.task_queue || "-"}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.owner}: {String(workflow.owner_pm || "-")}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.project}: {String(workflow.project_key || "-")}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.verdict}: {String(workflow.verdict || "-")}</div>
            <div className="mono">{workflowDetailPageCopy.caseFieldLabels.runs}: {runs.length}</div>
            <div className="toolbar mt-2">
              <Button asChild variant="secondary">
                <Link href={`/workflows/${encodeURIComponent(workflowId)}/share`}>{workflowDetailPageCopy.shareAssetCta}</Link>
              </Button>
            </div>
          </Card>
          <Card>
            <h3>{workflowDetailCopy.readModelTitle}</h3>
            {!workflowCaseReadModel ? (
              <div className="mono">{workflowDetailCopy.noReadModel}</div>
            ) : (
              <>
                <div className="mono">{workflowDetailCopy.readModelLabels.authority}: {String(workflowCaseReadModel.authority || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.executionAuthority}: {String(workflowCaseReadModel.execution_authority || "-")}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.source}: {String(workflowCaseReadModel.source || "-")}</div>
                <div className="mono">
                  {workflowDetailCopy.readModelLabels.sourceRunId}:{" "}
                  {sourceRunId ? (
                    <Link href={`/runs/${encodeURIComponent(sourceRunId)}`} aria-label={`Source run ${sourceRunId}`}>
                      {sourceRunId}
                    </Link>
                  ) : "-"}
                </div>
                <div className="mono">{workflowDetailCopy.readModelLabels.skillsBundle}: {formatBindingReadModelLabel(skillsBundle)}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.mcpBundle}: {formatBindingReadModelLabel(mcpBundle)}</div>
                <div className="mono">{workflowDetailCopy.readModelLabels.runtimeBinding}: {formatRoleBindingRuntimeSummary(roleBindingSummary)}</div>
                <span className="mono muted">
                  {workflowDetailCopy.readModelLabels.readOnlyNote}
                </span>
              </>
            )}
          </Card>
          <Card>
            <h3>{workflowDetailCopy.relatedRunsTitle(runs.length)}</h3>
            {runs.length === 0 ? (
              <div className="mono">{workflowDetailCopy.noRelatedRuns}</div>
            ) : (
              runs.map((run, index) => (
                <div key={workflowRunRowKey(run, index)} className="mono">
                  <Link href={`/runs/${encodeURIComponent(String(run.run_id || ""))}`}>{run.run_id}</Link> / {statusLabel(String(run.status || ""), locale)} / {run.created_at || "-"}
                </div>
              ))
            )}
          </Card>
          <Card>
            <h3>{workflowDetailCopy.eventsTitle(events.length)}</h3>
            <EventTimeline events={events} />
          </Card>
          <Card>
            <h3>{workflowDetailCopy.queueSlaTitle(queueItems.length)}</h3>
            {queueItems.length === 0 ? (
              <div className="mono">{workflowDetailCopy.noQueuedWork}</div>
            ) : (
              queueItems.map((item, index) => (
                <div key={`${String(item.queue_id || "queue")}-${index}`} className="mono">
                  {String(item.task_id || "-")} / {String(item.status || "-")} / {workflowDetailCopy.queueMeta(String(item.priority ?? "-"), String(item.sla_state || "-"))}
                </div>
              ))
            )}
            <span className="mono muted">{workflowDetailPageCopy.queuePostureNote}</span>
          </Card>
        </div>
      </section>
    </main>
  );
}
