import { cookies } from "next/headers";
import type { Metadata } from "next";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import { statusCtaFromCanonical, toCanonicalStatusFuzzy } from "@openvibecoding/frontend-shared/statusPresentation";
import Link from "next/link";
import type { BadgeVariant } from "../../components/ui/badge";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { fetchQueue, fetchWorkflows } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import { formatDashboardDateTime, statusLabel } from "../../lib/statusPresentation";
import {
  formatRoleBindingRuntimeSummary,
  type WorkflowRecord,
  type WorkflowRun,
} from "../../lib/types";
import WorkflowQueueMutationControls from "./WorkflowQueueMutationControls";

const CJK_TEXT_RE = /[\u3400-\u9fff]/;

export function buildWorkflowsMetadata(locale: "en" | "zh-CN"): Metadata {
  if (locale === "zh-CN") {
    return {
      title: "工作流案例 | OpenVibeCoding",
      description:
        "在 OpenVibeCoding 指挥塔里查看工作流案例、队列姿态、关联运行和下一步操作。",
    };
  }

  return {
    title: "Workflow Cases | OpenVibeCoding",
    description:
      "Review Workflow Cases, queue posture, linked runs, and next operator actions inside the OpenVibeCoding command tower.",
  };
}

function hasCjkText(value: string | undefined | null): boolean {
  return Boolean(value && CJK_TEXT_RE.test(value));
}

function statusBadgeVariant(status: string | undefined): BadgeVariant {
  const s = String(status || "").toLowerCase();
  if (["success", "done", "passed", "completed"].includes(s)) return "success";
  if (["failed", "failure", "error"].includes(s)) return "failed";
  if (["running", "active", "in_progress"].includes(s)) return "running";
  if (["blocked", "warning", "paused"].includes(s)) return "warning";
  return "default";
}

function workflowListText(locale: "en" | "zh-CN") {
  if (locale === "zh-CN") {
    return {
      headers: {
        workflow: "Workflow Case",
        posture: "案例姿态",
        authority: "权威 / Runtime",
        latestRun: "最新 linked run",
        nextAction: "下一步",
      },
      ownerPrefix: "Owner",
      namespacePrefix: "Namespace",
      queuePrefix: "Queue",
      authorityMissing: "当前还没有 workflow read model。",
      runtimeMissing: "当前还没有 runtime binding 摘要。",
      latestRunMissing: "当前还没有 linked run。",
      proofQueued: "队列里还有待派发工作，先确认案例再决定是否放行。",
      proofFailed: "最新 linked run 仍然有 proof gap。",
      proofRunning: "最新 linked run 仍在形成证据。",
      proofCompleted: "最新 linked run 已进入可复核姿态。",
      proofFallback: "当前案例还没有稳定的 proof posture。",
      openCase: "打开 Workflow Case",
      dispatchQueued: "打开案例并处理队列",
      inspectLatestRun: "检查最新 Run",
      confirmCase: "确认案例 posture",
      latestRunLabel: "Run",
      latestRunUpdated: "最近事件",
      latestRunStatus: "状态",
      readModelSource: "来源",
      readModelAuthority: "Authority",
      readModelExecution: "Execution",
      runtimeLabel: "Runtime",
      proofLabel: "Proof",
      verdictLabel: "Verdict",
      sourceRunLabel: "Source run",
    operatorDeskNote: "这张列表会把负责人、关联运行、执行权、运行时和下一步动作压到同一行，方便操作者先看指挥语义，再决定是否下钻。",
    };
  }
  return {
    headers: {
      workflow: "Workflow Case",
      posture: "Case posture",
      authority: "Authority / runtime",
      latestRun: "Latest linked run",
      nextAction: "Next operator action",
    },
    ownerPrefix: "Owner",
    namespacePrefix: "Namespace",
    queuePrefix: "Queue",
    authorityMissing: "No workflow read model is attached yet.",
    runtimeMissing: "No runtime binding summary is attached yet.",
    latestRunMissing: "No linked run is attached yet.",
    proofQueued: "Queued work is still waiting. Confirm the case before you promote or approve anything.",
    proofFailed: "The latest linked run still has a proof gap.",
    proofRunning: "The latest linked run is still building evidence.",
    proofCompleted: "The latest linked run is ready for proof review.",
    proofFallback: "This case has not reported a stable proof posture yet.",
    openCase: "Open Workflow Case",
    dispatchQueued: "Open case and handle queue",
    inspectLatestRun: "Inspect latest run",
    confirmCase: "Confirm case posture",
    latestRunLabel: "Run",
    latestRunUpdated: "Latest event",
    latestRunStatus: "Status",
    readModelSource: "Source",
    readModelAuthority: "Authority",
    readModelExecution: "Execution",
    runtimeLabel: "Runtime",
    proofLabel: "Proof",
    verdictLabel: "Verdict",
    sourceRunLabel: "Source run",
    operatorDeskNote: "This list compresses owner, linked run, authority, runtime, and the next action into one operator row so the command tower reads like an operating desk instead of a field dump.",
  };
}

function pickLatestRun(workflow: WorkflowRecord): WorkflowRun | undefined {
  const runs = Array.isArray(workflow.runs) ? workflow.runs : [];
  if (runs.length === 0) {
    return undefined;
  }
  const sourceRunId = String(workflow.workflow_case_read_model?.source_run_id || "").trim();
  if (sourceRunId) {
    const sourceRun = runs.find((run) => String(run.run_id || "").trim() === sourceRunId);
    if (sourceRun) {
      return sourceRun;
    }
  }
  return [...runs].sort((left, right) => {
    const leftTs = Date.parse(String(left.created_at || ""));
    const rightTs = Date.parse(String(right.created_at || ""));
    if (Number.isNaN(leftTs) && Number.isNaN(rightTs)) return 0;
    if (Number.isNaN(leftTs)) return 1;
    if (Number.isNaN(rightTs)) return -1;
    return rightTs - leftTs;
  })[0];
}

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  return buildWorkflowsMetadata(locale);
}

export default async function WorkflowsPage() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const listText = workflowListText(locale);
  const workflowListPageCopy = getUiCopy(locale).dashboard.workflowListPage;
  const { data: workflows, warning } = await safeLoad(fetchWorkflows, [] as WorkflowRecord[], "Workflow list");
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
            <p className="cell-sub mono muted">{locale === "zh-CN" ? "OpenVibeCoding / 工作流桌" : "OpenVibeCoding / workflow desk"}</p>
            <h1 id="workflows-page-title" className="page-title">{workflowListPageCopy.title}</h1>
            <p className="page-subtitle">{workflowListPageCopy.subtitle}</p>
          </div>
          <Badge>{workflowListPageCopy.countsBadge(workflows.length, queueItems.length)}</Badge>
        </div>
        {workflows.length > 0 || queueItems.length > 0 ? (
          <WorkflowQueueMutationControls queueCount={queueItems.length} eligibleCount={eligibleQueueCount} compact disableRunNextWhenEmpty />
        ) : null}
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
      <section className="app-section" aria-label={locale === "zh-CN" ? "工作流列表" : "Workflow list"}>
        {warning ? (
          <p className="alert alert-warning" role="status">
            {locale === "zh-CN" && !hasCjkText(warning)
              ? "当前工作流列表暂时不可用，请稍后再试。"
              : warning}
          </p>
        ) : null}
        <Card variant="compact">
          <p className="mono muted">{listText.operatorDeskNote}</p>
        </Card>
        {workflows.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="muted">{workflowListPageCopy.emptyTitle}</span>
              <span className="mono muted">{workflowListPageCopy.emptyHint}</span>
              <Button asChild variant="default">
                <Link href="/pm">打开 PM 入口</Link>
              </Button>
            </div>
          </Card>
        ) : (
          <Card variant="table">
            <table className="run-table">
              <caption className="sr-only">{workflowListPageCopy.tableCaption}</caption>
              <thead>
                <tr>
                  <th scope="col">{listText.headers.workflow}</th>
                  <th scope="col">{listText.headers.posture}</th>
                  <th scope="col">{listText.headers.authority}</th>
                  <th scope="col">{listText.headers.latestRun}</th>
                  <th scope="col">{listText.headers.nextAction}</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((workflow: WorkflowRecord) => {
                  const wfId = String(workflow.workflow_id || "-");
                  const runs = Array.isArray(workflow.runs) ? workflow.runs : [];
                  const queueItemsForWorkflow = queueByWorkflow.get(wfId) || [];
                  const objective = String(workflow.objective || "").trim();
                  const verdict = String(workflow.verdict || "").trim();
                  const latestRun = pickLatestRun(workflow);
                  const latestRunId = String(latestRun?.run_id || "").trim();
                  const roleBindingSummary = workflow.workflow_case_read_model?.role_binding_summary;
                  const authorityText = workflow.workflow_case_read_model
                    ? `${String(workflow.workflow_case_read_model.authority || "-")} / ${String(workflow.workflow_case_read_model.execution_authority || "-")}`
                    : listText.authorityMissing;
                  const runtimeSummary = roleBindingSummary
                    ? formatRoleBindingRuntimeSummary(roleBindingSummary)
                    : listText.runtimeMissing;
                  const latestRunStatus = latestRun ? statusLabel(latestRun.status, locale) : listText.latestRunMissing;
                  const latestRunTime = latestRun?.created_at
                    ? formatDashboardDateTime(latestRun.created_at, locale, {
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "-";
                  const eligibleQueued = queueItemsForWorkflow.some((item) => {
                    if (Boolean(item.eligible) || String(item.queue_state || "") === "eligible") {
                      return true;
                    }
                    return String(item.status || "").toUpperCase() === "PENDING";
                  });
                  const latestCanonical = toCanonicalStatusFuzzy(latestRun?.status || workflow.status);
                  const proofPosture = eligibleQueued
                    ? listText.proofQueued
                    : latestCanonical === "failed"
                    ? listText.proofFailed
                    : latestCanonical === "running"
                    ? listText.proofRunning
                    : latestCanonical === "completed" || latestCanonical === "healthy"
                    ? listText.proofCompleted
                    : listText.proofFallback;
                  const nextActionHref = eligibleQueued || !latestRunId
                    ? `/workflows/${encodeURIComponent(wfId)}`
                    : `/runs/${encodeURIComponent(latestRunId)}`;
                  const nextActionLabel = eligibleQueued
                    ? listText.dispatchQueued
                    : latestRunId
                    ? latestCanonical === "completed" || latestCanonical === "healthy"
                      ? listText.confirmCase
                      : statusCtaFromCanonical(latestCanonical, locale) || listText.inspectLatestRun
                    : listText.openCase;
                  return (
                    <tr key={wfId}>
                      <th scope="row">
                        <Link href={`/workflows/${encodeURIComponent(wfId)}`} className="run-link">
                          {wfId.length > 20 ? `${wfId.slice(0, 20)}...` : wfId}
                        </Link>
                        {objective ? (
                          <span className="cell-sub mono muted">{objective}</span>
                        ) : null}
                        {workflow.summary ? (
                          <span className="cell-sub mono muted">{String(workflow.summary)}</span>
                        ) : null}
                      </th>
                      <td>
                        <Badge variant={statusBadgeVariant(workflow.status as string)}>
                          {statusLabel(workflow.status as string, locale)}
                        </Badge>
                        <span className="cell-sub mono muted">
                          {`${listText.ownerPrefix}: ${String(workflow.owner_pm || "-")}`}
                        </span>
                        <span className="cell-sub mono muted">
                          {`${listText.namespacePrefix}: ${String(workflow.namespace || "-")} · ${listText.queuePrefix}: ${String(workflow.task_queue || "-")}`}
                        </span>
                      </td>
                      <td>
                        <span className="cell-primary">{authorityText}</span>
                        <span className="cell-sub mono muted">{`${listText.runtimeLabel}: ${runtimeSummary}`}</span>
                        {workflow.workflow_case_read_model?.source ? (
                          <span className="cell-sub mono muted">
                            {`${listText.readModelSource}: ${String(workflow.workflow_case_read_model.source || "-")}`}
                          </span>
                        ) : null}
                      </td>
                      <td>
                        {latestRunId ? (
                          <Link href={`/runs/${encodeURIComponent(latestRunId)}`} className="run-link">
                            {latestRunId.length > 16 ? `${latestRunId.slice(0, 16)}...` : latestRunId}
                          </Link>
                        ) : (
                          <span className="mono muted">{listText.latestRunMissing}</span>
                        )}
                        <span className="cell-sub mono muted">
                          {`${listText.latestRunStatus}: ${latestRunStatus}`}
                        </span>
                        <span className="cell-sub mono muted">
                          {`${listText.latestRunUpdated}: ${latestRunTime}`}
                        </span>
                      </td>
                      <td>
                        <span className="cell-primary">{proofPosture}</span>
                        {verdict ? (
                          <span className="cell-sub mono muted">{`${listText.verdictLabel}: ${verdict}`}</span>
                        ) : null}
                        {workflow.workflow_case_read_model?.source_run_id ? (
                          <span className="cell-sub mono muted">
                            {`${listText.sourceRunLabel}: ${String(workflow.workflow_case_read_model.source_run_id)}`}
                          </span>
                        ) : null}
                        <span className="cell-sub mono inline-stack">
                          <Link href={nextActionHref} className="run-link">
                            {nextActionLabel}
                          </Link>
                          {queueItemsForWorkflow.length > 0 ? (
                            <span className="muted">
                              {workflowListPageCopy.queueSummary(
                                queueItemsForWorkflow.length,
                                String(queueItemsForWorkflow[0]?.sla_state || "-"),
                              )}
                            </span>
                          ) : null}
                        </span>
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
