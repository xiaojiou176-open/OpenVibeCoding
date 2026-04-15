import Link from "next/link";
import { cookies } from "next/headers";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import DashboardHomeStorySections from "../components/DashboardHomeStorySections";
import { fetchRuns, fetchWorkflows } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

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
  const latestFailureGovernanceHref = latestFailure ? "/events" : "/runs";
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

      {hasRunHistory && warning ? (
        <section className="app-section" aria-label="Home data degradation">
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">
              {locale === "zh-CN"
                ? "首页数据当前是降级快照，但主入口与最新读面仍可继续使用。"
                : "Home data is currently degraded, but the main entry actions and latest read surfaces remain available."}
            </p>
            <p className="mono muted">{warningText}</p>
          </Card>
        </section>
      ) : null}

      {hasRunHistory ? (
        <>
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
              <Card variant="compact">
                <p className="ct-home-empty-text">No Workflow Case is available for gallery mode yet. Start from PM, then return here to reuse the share-ready case path as a showcase asset.</p>
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

          <section className="app-section" aria-labelledby="dashboard-latest-runs-title">
            <div className="section-header">
              <div>
                <h2 id="dashboard-latest-runs-title" className="section-title">
                  {locale === "zh-CN" ? "最新结果与运行" : "Latest results and runs"}
                </h2>
                <p>
                  {locale === "zh-CN"
                    ? "先从最新结果开始看。每一条都把任务 ID、失败线索和下一步操作保留在首屏。"
                    : "Start with the latest outcomes. Each entry keeps the task ID, failure clue, and next operator action visible."}
                </p>
                <p>
                  {locale === "zh-CN"
                    ? "只有在你需要审计归因时，再下钻到 Run Detail 或更深的证据面。"
                    : "Use run details and deeper evidence surfaces only when you need audit or attribution."}
                </p>
              </div>
              <nav aria-label="Latest runs actions">
                <Button asChild>
                  <Link href="/runs">{locale === "zh-CN" ? "查看全部运行" : "View all runs"}</Link>
                </Button>
                <Button asChild variant="secondary">
                  <Link href="/search">{locale === "zh-CN" ? "打开结果视图" : "Open results view"}</Link>
                </Button>
              </nav>
            </div>
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
                            {runActionText} ·{" "}
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
          </section>
        </>
      ) : (
        <section className="app-section" aria-labelledby="dashboard-first-unlock-title">
          <div className="section-header">
            <div>
                <h2 id="dashboard-first-unlock-title" className="section-title">
                  {locale === "zh-CN" ? "首个任务落地后会解锁什么" : "What unlocks after the first task lands"}
                </h2>
                <p>
                  {locale === "zh-CN"
                    ? "空首页不该假装自己已经有实时数据。先把最重要的三间房间亮出来：工作流、证明室，以及治理桌。"
                    : "The empty home state should not pretend it already has live data. Surface the three most valuable rooms first: Workflow, Proof, and the governance desks."}
                </p>
              </div>
          </div>
          <div className="home-command-grid">
            <Link href="/workflows" className="home-command-card home-command-card--supporting">
              <span className="home-command-kicker">Workflow Cases</span>
              <span className="home-command-title">{homePhase2Copy.liveCaseGalleryTitle}</span>
              <span className="home-command-desc">The first durable case record appears here once PM intake launches the first task.</span>
            </Link>
            <Link href="/runs" className="home-command-card home-command-card--supporting">
              <span className="home-command-kicker">Proof &amp; Replay</span>
              <span className="home-command-title">{locale === "zh-CN" ? "最新结果与运行" : "Latest results and runs"}</span>
              <span className="home-command-desc">
                {locale === "zh-CN"
                  ? "当第一条运行真正留下证据后，这里才会成为可以核对真相的房间。"
                  : "This room becomes the truth surface once the first run finishes and leaves evidence behind."}
              </span>
            </Link>
            <Link href="/contracts" className="home-command-card home-command-card--supporting">
              <span className="home-command-kicker">{locale === "zh-CN" ? "治理" : "Governance"}</span>
              <span className="home-command-title">{locale === "zh-CN" ? "治理桌集合" : "Governance rooms"}</span>
              <span className="home-command-desc">{governanceDeckDescription}</span>
            </Link>
          </div>
        </section>
      )}

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
            <span className="quick-card-desc">{locale === "zh-CN" ? "治理" : "Governance"}</span>
            <span className="quick-card-title">{locale === "zh-CN" ? "审批与放行控制" : "Approvals and release control"}</span>
            <span className="quick-card-desc">
              {locale === "zh-CN"
                ? "只有当评审项真的需要人工放行时，才进入手动审批。"
                : "Enter manual approval only when a review item requires it."}
            </span>
          </Link>
          <Link href="/contracts" className="quick-card">
            <span className="quick-card-desc">{locale === "zh-CN" ? "执行权" : "Authority"}</span>
            <span className="quick-card-title">{locale === "zh-CN" ? "合约桌" : "Contract desk"}</span>
            <span className="quick-card-desc">
              {locale === "zh-CN"
                ? "继续放行之前，先检查执行权、技能包姿态和当前合约阻碍。"
                : "Inspect execution authority, bundle posture, and contract blockers before a run continues."}
            </span>
          </Link>
          <Link href="/agents" className="quick-card">
            <span className="quick-card-desc">{locale === "zh-CN" ? "角色姿态" : "Role posture"}</span>
            <span className="quick-card-title">{locale === "zh-CN" ? "角色桌" : "Role desk"}</span>
            <span className="quick-card-desc">
              {locale === "zh-CN"
                ? "检查执行席位、运行时绑定和调度姿态，但不要把首页变回注册表 dump。"
                : "Check execution seats, runtime bindings, and scheduler posture without turning the homepage into a registry dump."}
            </span>
          </Link>
        </div>
      </section>
    </main>
  );
}
