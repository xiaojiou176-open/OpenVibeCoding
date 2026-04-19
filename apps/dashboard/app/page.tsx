import Link from "next/link";
import { cookies } from "next/headers";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import DashboardHomeStorySections from "../components/DashboardHomeStorySections";
import { fetchRuns, fetchWorkflows } from "../lib/api";
import { safeLoad } from "../lib/serverPageData";
import { formatDashboardDateTime, statusLabel } from "../lib/statusPresentation";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";

const CJK_TEXT_RE = /[\u3400-\u9fff]/;

const OUTCOME_LABELS_BY_LOCALE = {
  en: {
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
  },
  "zh-CN": {
    blocked: "已阻塞",
    denied: "策略拒绝",
    env: "环境异常",
    environment_error: "环境异常",
    error: "执行异常",
    failure: "执行失败",
    functional_failure: "产品失败",
    gate: "策略阻塞",
    gate_blocked: "策略阻塞",
    manual: "需要人工确认",
    manual_pending: "需要人工确认",
    product: "产品失败",
    success: "已成功完成",
    timeout: "执行超时",
    unknown: "未分类",
  },
};

function hasCjkText(value: string | undefined | null): boolean {
  return Boolean(value && CJK_TEXT_RE.test(value));
}

function firstLocalizedText(locale: "en" | "zh-CN", ...values: Array<string | undefined | null>): string | undefined {
  for (const value of values) {
    const trimmed = String(value || "").trim();
    if (!trimmed) {
      continue;
    }
    const isCjkText = hasCjkText(trimmed);
    if ((locale === "zh-CN" && isCjkText) || (locale === "en" && !isCjkText)) {
      return trimmed;
    }
  }
  return undefined;
}

function outcomeLabel(locale: "en" | "zh-CN", value: string | undefined | null): string {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) {
    return locale === "zh-CN" ? "未分类" : "Unclassified";
  }
  return (
    OUTCOME_LABELS_BY_LOCALE[locale][raw as keyof (typeof OUTCOME_LABELS_BY_LOCALE)["en"]]
    || OUTCOME_LABELS_BY_LOCALE[locale].unknown
  );
}

function verdictLabel(status: string | undefined | null, locale: "en" | "zh-CN"): string {
  const raw = String(status || "").trim().toLowerCase();
  if (!raw) {
    return locale === "zh-CN" ? "-" : "-";
  }
  if (hasCjkText(raw)) {
    return raw;
  }
  const localizedStatus = statusLabel(raw, locale);
  if (
    (locale === "zh-CN" && localizedStatus !== "未知")
    || (locale === "en" && localizedStatus !== "Unknown")
  ) {
    return localizedStatus;
  }
  return raw;
}

function formatLocalTime(value: string | undefined, locale: "en" | "zh-CN"): string {
  return formatDashboardDateTime(value, locale, {
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
  const isZh = locale === "zh-CN";
  const homePhase2Copy = getUiCopy(locale).dashboard.homePhase2;
  const hiddenActionChecklist =
    isZh
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
  const governanceDeckTitle =
    isZh ? "治理桌与放行控制" : "Governance desks and release controls";
  const governanceDeckDescription =
    isZh
      ? "这些页面承接审批、合约、角色姿态和治理控制，但它们不再定义首页第一印象。"
      : "These rooms handle approvals, contracts, role posture, and release controls, but they no longer define the homepage first impression.";
  const homeText = isZh
    ? {
        dataDegradationAria: "首页数据降级",
        warningTextFallback: "运行列表暂时不可用，请稍后再试。",
        workflowGalleryActionsAria: "工作流案例操作",
        workflowGalleryDegraded: "工作流案例画廊数据当前处于降级快照。请先直接查看工作流列表，等画廊快照刷新后再回来。",
        workflowGalleryWarningFallback: "工作流列表当前暂时不可用。",
        workflowGalleryEmpty: "当前还没有可用于画廊模式的工作流案例。先从 PM 发起第一项任务，等第一个可分享案例出现后再回来。",
        workflowBadge: "工作流案例",
        workflowTitleFallback: "工作流案例",
        workflowSummaryFallback: "当前还没有工作流摘要。",
        verdictPrefix: "判定",
        ownerPrefix: "负责人",
        projectPrefix: "项目",
        runMappingsPrefix: "运行映射",
        openCase: "打开案例",
        openShareAsset: "打开可分享资产",
        latestRunsTitle: "最新结果与运行",
        latestRunsDescriptionPrimary: "先从最新结果开始看。每一条都把任务 ID、失败线索和下一步操作保留在首屏。",
        latestRunsDescriptionSecondary: "只有在你需要审计归因时，再下钻到 Run Detail 或更深的证据面。",
        latestRunsActionsAria: "最新运行操作",
        viewAllRuns: "查看全部运行",
        openResultsView: "打开结果视图",
        latestRunSummaryAria: "最新运行摘要",
        taskPrefix: "任务",
        defaultFailureAction: "建议：检查失败事件",
        defaultRunAction: "建议：打开运行详情",
        handleFailure: "处理失败",
        handleFailureAria: (id: string) => `处理失败 ${id || "运行"}`,
        runAria: (id: string) => `运行 ${id}`,
        emptyWorkflowKicker: "工作流案例",
        emptyWorkflowDesc: "首个可追踪的案例记录会在 PM 发起第一项任务后出现在这里。",
        emptyReplayKicker: "证明与回放",
        emptyReplayDesc: "第一条运行真正留下证据后，这里才会成为可以核对真相的房间。",
        emptyGovernanceKicker: "治理",
        emptyGovernanceTitle: "治理桌集合",
      }
    : {
        dataDegradationAria: "Home data degradation",
        warningTextFallback: "The run list is temporarily unavailable. Try again soon.",
        workflowGalleryActionsAria: "Case gallery actions",
        workflowGalleryDegraded: "Workflow gallery data is temporarily degraded. Use the workflow list directly until the gallery snapshot refreshes.",
        workflowGalleryWarningFallback: "Workflow list is temporarily unavailable.",
        workflowGalleryEmpty: "No Workflow Case is available for gallery mode yet. Start from PM, then return here to reuse the first share-ready case as a proof-ready reference.",
        workflowBadge: "Workflow Case",
        workflowTitleFallback: "Workflow case",
        workflowSummaryFallback: "No workflow summary is attached yet.",
        verdictPrefix: "Verdict",
        ownerPrefix: "Owner",
        projectPrefix: "Project",
        runMappingsPrefix: "Run mappings",
        openCase: "Open case",
        openShareAsset: "Open share-ready asset",
        latestRunsTitle: "Latest results and runs",
        latestRunsDescriptionPrimary: "Start with the latest outcomes. Each entry keeps the task ID, failure clue, and next operator action visible.",
        latestRunsDescriptionSecondary: "Use run details and deeper evidence surfaces only when you need audit or attribution.",
        latestRunsActionsAria: "Latest runs actions",
        viewAllRuns: "View all runs",
        openResultsView: "Open results view",
        latestRunSummaryAria: "Latest run summary",
        taskPrefix: "Task",
        defaultFailureAction: "Recommended: inspect failure events",
        defaultRunAction: "Recommended: open run details",
        handleFailure: "Handle failure",
        handleFailureAria: (id: string) => `Handle failure ${id || "run"}`,
        runAria: (id: string) => `Run ${id}`,
        emptyWorkflowKicker: "Workflow Cases",
        emptyWorkflowDesc: "The first durable case record appears here once PM intake launches the first task.",
        emptyReplayKicker: "Proof & Replay",
        emptyReplayDesc: "This room becomes the truth surface once the first run finishes and leaves evidence behind.",
        emptyGovernanceKicker: "Governance",
        emptyGovernanceTitle: "Governance rooms",
      };
  const warningText = firstLocalizedText(locale, warning) || homeText.warningTextFallback;
  const workflowsWarningText = firstLocalizedText(locale, workflowsWarning) || homeText.workflowGalleryWarningFallback;

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
        <section className="app-section" aria-label={homeText.dataDegradationAria}>
          <Card variant="compact" role="status" aria-live="polite">
            <p className="ct-home-empty-text">
              {isZh
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
              <nav aria-label={homeText.workflowGalleryActionsAria}>
                <Button asChild variant="secondary">
                  <Link href={homePhase2Copy.liveCaseGalleryActionHref}>
                    {homePhase2Copy.liveCaseGalleryActionLabel}
                  </Link>
                </Button>
              </nav>
            </div>
            {hasDegradedWorkflowData ? (
              <Card>
                <p className="muted">{homeText.workflowGalleryDegraded}</p>
                <p className="mono muted">{workflowsWarningText}</p>
              </Card>
            ) : latestWorkflows.length === 0 ? (
              <Card variant="compact">
                <p className="ct-home-empty-text">{homeText.workflowGalleryEmpty}</p>
              </Card>
            ) : (
              <div className="quick-grid">
                {latestWorkflows.map((workflow) => {
                  const workflowId = String(workflow.workflow_id || "").trim();
                  const workflowSummary =
                    firstLocalizedText(locale, workflow.summary, workflow.objective) || homeText.workflowSummaryFallback;
                  const runCount = Array.isArray(workflow.runs) ? workflow.runs.length : Array.isArray(workflow.run_ids) ? workflow.run_ids.length : 0;
                  return (
                    <Card key={workflowId || workflowSummary}>
                      <div className="stack-gap-2">
                        <div className="toolbar">
                          <Badge variant="default">{homeText.workflowBadge}</Badge>
                          <Badge>{statusLabel(workflow.status, locale)}</Badge>
                        </div>
                        <h3 className="quick-card-title">{workflowId || homeText.workflowTitleFallback}</h3>
                        <p className="quick-card-desc">{workflowSummary}</p>
                        <p className="cell-sub mono">{`${homeText.verdictPrefix}: ${verdictLabel(workflow.verdict, locale)}`}</p>
                        <p className="cell-sub mono">{`${homeText.ownerPrefix}: ${String(workflow.owner_pm || "-")} · ${homeText.projectPrefix}: ${String(workflow.project_key || "-")}`}</p>
                        <p className="cell-sub mono">{`${homeText.runMappingsPrefix}: ${runCount}`}</p>
                        <div className="toolbar">
                          {workflowId ? (
                            <Button asChild variant="secondary">
                              <Link href={`/workflows/${encodeURIComponent(workflowId)}`}>{homeText.openCase}</Link>
                            </Button>
                          ) : null}
                          {workflowId ? (
                            <Button asChild variant="ghost">
                              <Link href={`/workflows/${encodeURIComponent(workflowId)}/share`}>{homeText.openShareAsset}</Link>
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
                  {homeText.latestRunsTitle}
                </h2>
                <p>{homeText.latestRunsDescriptionPrimary}</p>
                <p>{homeText.latestRunsDescriptionSecondary}</p>
              </div>
              <nav aria-label={homeText.latestRunsActionsAria}>
                <Button asChild>
                  <Link href="/runs">{homeText.viewAllRuns}</Link>
                </Button>
                <Button asChild variant="secondary">
                  <Link href="/search">{homeText.openResultsView}</Link>
                </Button>
              </nav>
            </div>
            <Card>
              <ul className="row-stack" aria-label={homeText.latestRunSummaryAria}>
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
                    firstLocalizedText(locale, run.failure_summary_zh, run.failure_reason, run.outcome_label_zh)
                    || (String(run.failure_class || "").trim() ? outcomeLabel(locale, run.failure_class) : undefined)
                    || (String(run.outcome_type || "").trim() ? outcomeLabel(locale, run.outcome_type) : undefined)
                    || outcomeLabel(locale, undefined)
                  );
                  const runActionText =
                    firstLocalizedText(locale, run.action_hint_zh)
                    || (runIsFailed ? homeText.defaultFailureAction : homeText.defaultRunAction);

                  return (
                    <li key={runIdRaw || String(run.task_id || "")} className="row-stack-item">
                      <span>
                        {runHasId ? (
                          <Link
                            href={`/runs/${encodeURIComponent(runIdRaw)}`}
                            className="run-link"
                            title={runIdRaw}
                            aria-label={homeText.runAria(runIdRaw)}
                          >
                            {runLabel}
                          </Link>
                        ) : (
                          <span className="mono muted">{runLabel}</span>
                        )}
                        <span className="cell-sub mono muted">{`${homeText.taskPrefix}: ${compactTaskId(taskIdRaw)} · ${runContextText}`}</span>
                        {runIsFailed ? (
                          <span className="cell-sub mono cell-danger">
                            {runActionText} ·{" "}
                            <Button asChild variant="warning">
                              <Link
                                href={failureActionHref}
                                aria-label={homeText.handleFailureAria(runIdRaw || taskIdRaw || "")}
                              >
                                {homeText.handleFailure}
                              </Link>
                            </Button>
                          </span>
                        ) : (
                          <span className="cell-sub mono muted">{runActionText}</span>
                        )}
                      </span>
                      <Badge variant={runIsFailed ? "failed" : runIsSuccess ? "success" : "running"}>
                        {statusLabel(run.status, locale)}
                      </Badge>
                      <span className="muted">{formatLocalTime(run.last_event_ts || run.created_at, locale)}</span>
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
              <span className="home-command-kicker">{homeText.emptyWorkflowKicker}</span>
              <span className="home-command-title">{homePhase2Copy.liveCaseGalleryTitle}</span>
              <span className="home-command-desc">{homeText.emptyWorkflowDesc}</span>
            </Link>
            <Link href="/runs" className="home-command-card home-command-card--supporting">
              <span className="home-command-kicker">{homeText.emptyReplayKicker}</span>
              <span className="home-command-title">{homeText.latestRunsTitle}</span>
              <span className="home-command-desc">{homeText.emptyReplayDesc}</span>
            </Link>
            <Link href="/contracts" className="home-command-card home-command-card--supporting">
              <span className="home-command-kicker">{homeText.emptyGovernanceKicker}</span>
              <span className="home-command-title">{homeText.emptyGovernanceTitle}</span>
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
                ? "检查执行席位、运行时绑定和调度姿态，但不要把首页变回注册表清单。"
                : "Check execution seats, runtime bindings, and scheduler posture without turning the homepage into a registry dump."}
            </span>
          </Link>
        </div>
      </section>
    </main>
  );
}
