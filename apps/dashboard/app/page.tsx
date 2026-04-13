import Link from "next/link";
import { cookies } from "next/headers";
import { Button } from "../components/ui/button";
import { Badge, type BadgeVariant } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import DashboardHomeStorySections from "../components/DashboardHomeStorySections";
import { fetchRuns, fetchWorkflows } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";
import { getUiCopy } from "@cortexpilot/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";

const CJK_TEXT_RE = /[\u3400-\u9fff]/;

const STATUS_ALIASES_EN: Record<string, string> = {
  active: "running",
  approve: "completed",
  approved: "completed",
  archived: "archived",
  blocked: "blocked",
  canceled: "cancelled",
  cancelled: "cancelled",
  closed: "archived",
  completed: "completed",
  critical: "failed",
  degraded: "blocked",
  denied: "failed",
  done: "completed",
  error: "failed",
  executing: "running",
  fail: "failed",
  failed: "failed",
  failure: "failed",
  healthy: "healthy",
  idle: "idle",
  in_progress: "running",
  info: "info",
  ok: "completed",
  on_hold: "blocked",
  pass: "completed",
  passed: "completed",
  paused: "paused",
  pending: "pending",
  progress: "running",
  reject: "failed",
  rejected: "failed",
  running: "running",
  success: "completed",
  timeout: "failed",
  waiting: "pending",
  warning: "blocked",
  working: "running",
};

const STATUS_LABELS_EN: Record<string, string> = {
  archived: "Archived",
  blocked: "Blocked",
  cancelled: "Cancelled",
  completed: "Completed",
  failed: "Failed",
  healthy: "Healthy",
  idle: "Idle",
  info: "Info",
  paused: "Paused",
  pending: "Pending",
  running: "Running",
};

const OUTCOME_LABELS_EN: Record<string, string> = {
  blocked: "Blocked",
  denied: "Policy denied",
  env: "Environment error",
  environment_error: "Environment error",
  error: "Execution error",
  failure: "Execution failed",
  functional_failure: "Product failure",
  gate: "Policy blocked",
  gate_blocked: "Policy blocked",
  manual: "Manual review required",
  manual_pending: "Manual review required",
  product: "Product failure",
  success: "Completed successfully",
  timeout: "Timed out",
  unknown: "Failure awaiting classification",
};

function hasCjkText(value: string | undefined | null): boolean {
  return Boolean(value && CJK_TEXT_RE.test(value));
}

function firstEnglishText(...values: Array<string | undefined | null>): string | undefined {
  for (const value of values) {
    const trimmed = String(value || "").trim();
    if (trimmed && !hasCjkText(trimmed)) {
      return trimmed;
    }
  }
  return undefined;
}

function statusLabelEn(status: string | undefined | null): string {
  const raw = String(status || "").trim().toLowerCase();
  if (!raw) {
    return "Unknown";
  }
  const canonical = STATUS_ALIASES_EN[raw] || raw;
  return STATUS_LABELS_EN[canonical] || raw.toUpperCase();
}

function outcomeLabelEn(value: string | undefined | null): string {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return "Unclassified";
  }
  return OUTCOME_LABELS_EN[raw] || "Unclassified";
}

function formatLocalTime(value: string | undefined): string {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function runIdentityLabel(runId: string | undefined, taskId: string | undefined): string {
  const runRaw = String(runId || "").trim();
  if (!runRaw) {
    return "-";
  }
  if (runRaw.length <= 20) {
    return runRaw;
  }
  const runHead = runRaw.slice(0, 8);
  const runTail = runRaw.slice(-10);
  const taskRaw = String(taskId || "").trim();
  if (!taskRaw) {
    return `${runHead}…${runTail}`;
  }
  const taskTail = taskRaw.length <= 10 ? taskRaw : taskRaw.slice(-10);
  return `${runTail} · ${taskTail}`;
}

function compactTaskId(value: string | undefined): string {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  return raw.length <= 16 ? raw : `${raw.slice(0, 8)}...${raw.slice(-4)}`;
}

export default async function Home() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const homePhase2Copy = getUiCopy(locale).dashboard.homePhase2;
  const hiddenActionChecklist =
    locale === "zh-CN"
      ? ["开始第一项任务", "查看最新运行", "打开兼容性矩阵"]
      : null;
  const { data: runs, warning } = await safeLoad(fetchRuns, [], "run list");
  const { data: workflows, warning: workflowsWarning } = await safeLoad(fetchWorkflows, [], "workflow list");
  const latestRuns = Array.isArray(runs) ? runs.slice(0, 12) : [];
  const latestWorkflows = Array.isArray(workflows) ? workflows.slice(0, 3) : [];
  const latestRun = latestRuns[0];
  const hasDegradedRunsData = Boolean(warning);
  const hasDegradedWorkflowData = Boolean(workflowsWarning);
  const latestFailure = latestRuns.find((run) =>
    ["FAILED", "FAILURE", "ERROR"].includes(String(run.status || "").toUpperCase())
  );

  const successCount = latestRuns.filter((run) =>
    ["SUCCESS", "DONE", "PASSED"].includes(String(run.status || "").toUpperCase())
  ).length;
  const failedCount = latestRuns.filter((run) =>
    ["FAILED", "FAILURE", "ERROR"].includes(String(run.status || "").toUpperCase())
  ).length;
  const runningCount = Math.max(latestRuns.length - successCount - failedCount, 0);
  const statusSampleCount = latestRuns.length;
  const hasRunHistory = statusSampleCount > 0;
  const failureRate = statusSampleCount > 0 ? failedCount / statusSampleCount : 0;
  const failureRatePercent = Math.round(failureRate * 100);
  const latestRunStatus = String(latestRun?.status || "UNKNOWN").toUpperCase();
  const latestRunIsFailed = ["FAILED", "FAILURE", "ERROR"].includes(latestRunStatus);
  const latestRunIsSuccess = ["SUCCESS", "DONE", "PASSED"].includes(latestRunStatus);
  const latestRunIsRunning = hasRunHistory && !latestRunIsFailed && !latestRunIsSuccess;
  const latestRunStatusClass = latestRunIsFailed
    ? "metric-value--danger"
    : latestRunIsSuccess
      ? "metric-value--success"
      : latestRunIsRunning
        ? "metric-value--warning"
        : "metric-value--primary";
  const distributionValueClass =
    hasDegradedRunsData
      ? "metric-value--warning"
      : failureRate >= 0.5
      ? "metric-value--danger"
      : failureRate >= 0.25
        ? "metric-value--warning"
        : failedCount === 0
          ? "metric-value--success"
          : "metric-value--primary";
  const distributionRiskBadgeVariant: BadgeVariant =
    hasDegradedRunsData
      ? "warning"
      : failureRate >= 0.5
      ? "failed"
      : failureRate >= 0.25
        ? "warning"
        : failedCount === 0
          ? "success"
          : "running";
  const distributionRiskText =
    hasDegradedRunsData
      ? "Data degraded: the run list is temporarily unavailable"
      : failureRate >= 0.5
      ? "High risk: failure rate is elevated, investigate first"
      : failureRate >= 0.25
        ? "Attention: failure rate is rising, monitor abnormal events"
        : failedCount === 0
          ? "Stable: no recent failed runs"
          : "Controlled: a few failures exist, keep monitoring";
  const latestFailureCategory =
    (latestFailure
      ? outcomeLabelEn(latestFailure.failure_class) ||
        outcomeLabelEn(latestFailure.outcome_type)
      : undefined) || "-";
  const latestFailureHint = firstEnglishText(latestFailure?.action_hint_zh) || "inspect failure events";
  const latestFailureGovernanceHref = latestFailure ? "/events" : "/runs";
  const latestFailureGovernanceLabel = latestFailure
    ? `Governance entry: ${latestFailureHint}`
    : "Governance entry: open runs";
  const riskSummaryTitle =
    hasDegradedRunsData
      ? "Data degraded"
      : !hasRunHistory
      ? "Waiting for first run"
      : failureRate >= 0.5 || latestRunIsFailed
      ? "High-risk alert"
      : failureRate >= 0.25 || latestRunIsRunning
        ? "Risk rising"
        : failedCount === 0
          ? "Stable"
          : "Controlled";
  const riskSummaryClass =
    hasDegradedRunsData
      ? "metric-value--warning"
      : !hasRunHistory
      ? "metric-value--primary"
      : failureRate >= 0.5 || latestRunIsFailed
      ? "metric-value--danger"
      : failureRate >= 0.25 || latestRunIsRunning
      ? "metric-value--warning"
      : "metric-value--success";
  const warningText =
    firstEnglishText(warning) || "The run list is temporarily unavailable. Try again soon.";
  const governanceDeckTitle =
    locale === "zh-CN" ? "治理桌与放行控制" : "Governance desks and release controls";
  const governanceDeckDescription =
    locale === "zh-CN"
      ? "这些页面承接审批、contract、role 和治理控制，但它们不再定义首页第一印象。"
      : "These rooms handle approvals, contracts, role posture, and release controls, but they no longer define the homepage first impression.";

  return (
    <main className="grid" aria-labelledby="dashboard-home-title">
      {hiddenActionChecklist ? (
        <section className="sr-only" aria-label="首页起步动作" lang="zh-CN">
          <ul>
            {hiddenActionChecklist.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <DashboardHomeStorySections
        failedCount={failedCount}
        failureRate={failureRate}
        hasRunHistory={hasRunHistory}
        latestFailureGovernanceHref={latestFailureGovernanceHref}
        locale={locale}
        runningCount={runningCount}
        showFirstTaskGuide={!hasRunHistory}
      />

      <section className="app-section" aria-labelledby="dashboard-case-gallery-live-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-case-gallery-live-title" className="section-title">
              {homePhase2Copy.liveCaseGalleryTitle}
            </h2>
            <p>{homePhase2Copy.liveCaseGalleryDescription}</p>
          </div>
          <nav aria-label="Case gallery actions">
            <Button asChild variant="secondary">
              <Link href={homePhase2Copy.liveCaseGalleryActionHref}>
                {homePhase2Copy.liveCaseGalleryActionLabel}
              </Link>
            </Button>
          </nav>
        </div>
        {hasDegradedWorkflowData ? (
          <Card>
            <p className="muted">Workflow gallery data is temporarily degraded. Use the workflow list directly until the gallery snapshot refreshes.</p>
            <p className="mono muted">{String(workflowsWarning || "").trim() || "Workflow list is temporarily unavailable."}</p>
          </Card>
        ) : latestWorkflows.length === 0 ? (
          <Card>
            <p className="muted">No Workflow Case is available for gallery mode yet. Start from PM, then return here to reuse the share-ready case path as a showcase asset.</p>
          </Card>
        ) : (
          <div className="quick-grid">
            {latestWorkflows.map((workflow) => {
              const workflowId = String(workflow.workflow_id || "").trim();
              const workflowSummary = firstEnglishText(workflow.summary, workflow.objective) || "No workflow summary is attached yet.";
              const runCount = Array.isArray(workflow.runs) ? workflow.runs.length : Array.isArray(workflow.run_ids) ? workflow.run_ids.length : 0;
              return (
                <Card key={workflowId || workflowSummary}>
                  <div className="stack-gap-2">
                    <div className="toolbar">
                      <Badge variant="default">Workflow Case</Badge>
                      <Badge>{statusLabelEn(workflow.status)}</Badge>
                    </div>
                    <h3 className="quick-card-title">{workflowId || "Workflow case"}</h3>
                    <p className="quick-card-desc">{workflowSummary}</p>
                    <p className="cell-sub mono">Verdict: {String(workflow.verdict || "-")}</p>
                    <p className="cell-sub mono">Owner: {String(workflow.owner_pm || "-")} · Project: {String(workflow.project_key || "-")}</p>
                    <p className="cell-sub mono">Run mappings: {runCount}</p>
                    <div className="toolbar">
                      {workflowId ? (
                        <Button asChild variant="secondary">
                          <Link href={`/workflows/${encodeURIComponent(workflowId)}`}>Open case</Link>
                        </Button>
                      ) : null}
                      {workflowId ? (
                        <Button asChild variant="ghost">
                          <Link href={`/workflows/${encodeURIComponent(workflowId)}/share`}>Open share-ready asset</Link>
                        </Button>
                      ) : null}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section className="app-section" aria-label="Risk and status summary">
        {warning ? (
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">Some home data is degraded. Core entry actions and the latest snapshot remain available.</p>
            <p className="mono muted">{warningText}</p>
          </Card>
        ) : null}
        <div className="stats-grid">
          <article className="metric-card">
            <p className="metric-label">Risk summary</p>
            <p className={`metric-value ${riskSummaryClass}`}>{riskSummaryTitle}</p>
            <p className={`cell-sub mono ${latestRunStatusClass}`}>
              Latest status: {hasDegradedRunsData ? "Data degraded" : hasRunHistory ? statusLabelEn(latestRun?.status) : "No runs yet"}
            </p>
            <p className={`cell-sub mono ${hasDegradedRunsData ? "cell-warning" : latestFailure ? "cell-danger" : "muted"}`}>
              Failure category: {hasDegradedRunsData ? "unavailable while data is degraded" : String(latestFailureCategory)}
            </p>
            <p className="cell-sub mono muted">{formatLocalTime(latestRun?.last_event_ts || latestRun?.created_at)}</p>
            <Link href={latestFailureGovernanceHref} className="cell-sub mono">
              {hasDegradedRunsData ? "Governance entry: inspect data sources and the run list" : latestFailureGovernanceLabel}
            </Link>
          </article>
          <article className="metric-card">
            <p className="metric-label">Status distribution across the last 12 runs</p>
            <p className={`metric-value ${distributionValueClass}`}>{`Success ${successCount} / Running ${runningCount} / Failed ${failedCount}`}</p>
            <div className="inline-stack" aria-label="Failure-rate risk signal">
              <progress
                className="run-progress"
                max={Math.max(statusSampleCount, 1)}
                value={failedCount}
                aria-label={`Failure share ${failedCount}/${statusSampleCount}`}
              />
              <Badge variant={distributionRiskBadgeVariant} role="status" aria-live="polite">
                {`${distributionRiskText} (${failureRatePercent}%)`}
              </Badge>
            </div>
            <p className="cell-sub mono muted">Total: {hasDegradedRunsData ? "-" : statusSampleCount}</p>
          </article>
        </div>
      </section>

      <section className="app-section" aria-labelledby="dashboard-latest-runs-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-latest-runs-title" className="section-title">
              Latest results and runs
            </h2>
            <p>Start with the latest outcomes. Each entry keeps the task ID, failure clue, and next operator action visible.</p>
            <p>Use run details and deeper evidence surfaces only when you need audit or attribution.</p>
          </div>
          <nav aria-label="Latest runs actions">
            <Button asChild>
              <Link href="/runs">View all runs</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/search">Open results view</Link>
            </Button>
          </nav>
        </div>
        {latestRuns.length === 0 ? (
          <Card><p className="muted">No runs yet.</p></Card>
        ) : (
          <Card>
            <ul className="row-stack" aria-label="Latest run summary">
              {latestRuns.slice(0, 6).map((run) => {
                const runIdRaw = String(run.run_id || "").trim();
                const runHasId = Boolean(runIdRaw);
                const taskIdRaw = String(run.task_id || "").trim();
                const runStatus = String(run.status || "").toUpperCase();
                const runIsFailed = ["FAILED", "FAILURE", "ERROR"].includes(runStatus);
                const runIsSuccess = ["SUCCESS", "DONE", "PASSED"].includes(runStatus);
                const runLabel = runIdentityLabel(runIdRaw, taskIdRaw);
                const failureActionHref = runHasId ? `/events?run_id=${encodeURIComponent(runIdRaw)}` : "/events";
                const runContextText = String(
                  firstEnglishText(run.failure_summary_zh, run.failure_reason, run.outcome_label_zh) ||
                    outcomeLabelEn(run.failure_class) ||
                    outcomeLabelEn(run.outcome_type) ||
                    "Status pending"
                );
                const runActionText =
                  firstEnglishText(run.action_hint_zh) ||
                  (runIsFailed ? "Recommended: inspect failure events" : "Recommended: open run details");

                return (
                  <li key={runIdRaw || String(run.task_id || "")} className="row-stack-item">
                    <span>
                      {runHasId ? (
                        <Link
                          href={`/runs/${encodeURIComponent(runIdRaw)}`}
                          className="run-link"
                          title={runIdRaw}
                          aria-label={`Run ${runIdRaw}`}
                        >
                          {runLabel}
                        </Link>
                      ) : (
                        <span className="mono muted">{runLabel}</span>
                      )}
                      <span className="cell-sub mono muted">{`Task: ${compactTaskId(taskIdRaw)} · ${runContextText}`}</span>
                      {runIsFailed ? (
                        <span className="cell-sub mono cell-danger">
                          {runActionText} · {" "}
                          <Button asChild variant="warning">
                            <Link
                              href={failureActionHref}
                              aria-label={`Handle failure ${runIdRaw || taskIdRaw || "run"}`}
                            >
                              Handle failure
                            </Link>
                          </Button>
                        </span>
                      ) : (
                        <span className="cell-sub mono muted">{runActionText}</span>
                      )}
                    </span>
                    <Badge variant={runIsFailed ? "failed" : runIsSuccess ? "success" : "running"}>
                      {statusLabelEn(run.status)}
                    </Badge>
                    <span className="muted">{formatLocalTime(run.last_event_ts || run.created_at)}</span>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
      </section>

      <section className="app-section" aria-labelledby="dashboard-advanced-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-advanced-title" className="section-title">
              {governanceDeckTitle}
            </h2>
            <p>{governanceDeckDescription}</p>
          </div>
        </div>
        <div className="quick-grid">
          <Link href="/god-mode" className="quick-card">
            <span className="quick-card-desc">Governance</span>
            <span className="quick-card-title">Approvals and release control</span>
            <span className="quick-card-desc">Enter manual approval only when a review item requires it.</span>
          </Link>
          <Link href="/contracts" className="quick-card">
            <span className="quick-card-desc">Authority</span>
            <span className="quick-card-title">Contract desk</span>
            <span className="quick-card-desc">Inspect execution authority, bundle posture, and contract blockers before a run continues.</span>
          </Link>
          <Link href="/agents" className="quick-card">
            <span className="quick-card-desc">Role posture</span>
            <span className="quick-card-title">Role desk</span>
            <span className="quick-card-desc">Check execution seats, runtime bindings, and scheduler posture without turning the homepage into a registry dump.</span>
          </Link>
        </div>
      </section>
    </main>
  );
}
