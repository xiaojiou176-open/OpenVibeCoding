import { cookies } from "next/headers";
import type { Metadata } from "next";
import Link from "next/link";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { fetchArtifact, fetchReports, fetchRun, fetchRuns } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import type { JsonValue, ReportRecord, RunDetailPayload, RunSummary } from "../../lib/types";
import WorkflowQueueMutationControls from "../workflows/WorkflowQueueMutationControls";

const CJK_TEXT_RE = /[\u3400-\u9fff]/;

export function buildPlannerMetadata(locale: "en" | "zh-CN"): Metadata {
  if (locale === "zh-CN") {
    return {
      title: "规划桌 | OpenVibeCoding",
      description:
        "在同一张规划桌里分诊波次计划、worker 提示词合约、解阻塞任务和续跑治理。",
    };
  }

  return {
    title: "Planner desk | OpenVibeCoding",
    description:
      "Triages wave plans, worker prompt contracts, unblock tasks, and continuation governance from one planner-facing control desk.",
  };
}

function hasCjkText(value: string | undefined | null): boolean {
  return Boolean(value && CJK_TEXT_RE.test(value));
}

type PlannerRow = {
  run: RunDetailPayload;
  wavePlan: Record<string, JsonValue> | null;
  workerContracts: Record<string, JsonValue>[];
  unblockTasks: Record<string, JsonValue>[];
  completionGovernance: Record<string, JsonValue> | null;
  plannedWorkerCount: number;
};

type PlannerPriorityState = {
  title: string;
  summary: string;
  tone: "failed" | "warning" | "running";
  primaryHref: string;
  primaryLabel: string;
  secondaryHref: string;
  secondaryLabel: string;
  objective: string;
  runId: string;
};

function asRecord(value: JsonValue | null | undefined): Record<string, JsonValue> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, JsonValue>) : null;
}

function asRecordArray(value: JsonValue | null | undefined): Record<string, JsonValue>[] {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, JsonValue> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function artifactNames(run: RunDetailPayload): string[] {
  const artifacts = Array.isArray(run.manifest?.artifacts) ? run.manifest?.artifacts : [];
  return artifacts
    .map((item) => {
      const record = asRecord(item as JsonValue);
      const name = typeof record?.name === "string" ? record.name : typeof record?.path === "string" ? record.path : "";
      return String(name || "").trim();
    })
    .filter(Boolean);
}

async function resolveDashboardLocale() {
  try {
    const cookieStore = await cookies();
    return normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  } catch {
    return normalizeUiLocale(undefined);
  }
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = await resolveDashboardLocale();
  return buildPlannerMetadata(locale);
}

export function plannerText(locale: "en" | "zh-CN") {
  if (locale === "zh-CN") {
    return {
      title: "规划桌",
      subtitle: "先做规划分诊，再看细节。把波次计划、工作者提示词合约、唤醒策略姿态和完成治理放到同一张控制桌上，直接回答下一步该派谁、该回哪里、该继续还是该解阻塞。",
      actions: {
        pm: "打开 PM 入口",
        tower: "打开指挥塔",
        workflows: "打开工作流案例",
        proof: "打开证明与回放",
      },
      metrics: {
        runs: "带规划产物的运行",
        workers: "可见工作者合约",
        unblock: "可见解阻塞任务",
        wake: "挂了唤醒策略的运行",
      },
      table: {
        run: "运行",
        objective: "波次目标",
        blocker: "当前分诊",
        next: "下一步",
      },
      empty: "当前还没有可见的规划产物。",
      note: "这张桌子保持 `task_contract` 仍是唯一执行权威，但它已经不再只是只读摆件：现在先做规划分诊，再决定回 PM、工作流案例、指挥塔还是证明与回放。",
      openRun: "打开证明室",
      openWorkflow: "打开工作流案例",
      openTower: "打开指挥塔",
      openPm: "打开 PM 入口",
      wakeLabel: "唤醒策略",
      governanceLabel: "治理结论",
      unblockLabel: "解阻塞任务",
      contractsLabel: "工作者合约",
      plannedWorkersLabel: "计划工作者数",
      triageTitle: "规划分诊队列",
      triageSubtitle: "先确认哪条波次缺工作者合约、哪条已经进入续跑、哪条该优先处理解阻塞任务，再去下一张桌子。",
      inspectionTitle: "规划细节档案",
      inspectionSubtitle: "把原始规划产物留在第二层阅读，同时保留规划桌自己的队列与派发控制，不再让它只是一个跳转台。",
    shellLabel: "OpenVibeCoding / 规划桌",
    summaryAriaLabel: "规划桌摘要",
    warningFallback: "当前运行列表暂时不可用，请稍后再试。",
    launchChecklistLabel: "规划桌启动清单",
    launchOpenPmHint: "先把第一条目标、约束和验收口径写清，再回来让规划桌真正开机。",
    launchOpenTowerHint: "如果系统已经在跑，只是规划产物还没挂出来，就先回指挥塔看当前谁在动。",
    launchOpenWorkflowHint: "工作流案例是可持续状态，不是首页解释文；当规划行出现后，回这里继续追。",
    blocker: {
      missingGovernance: "缺完成治理",
        missingContracts: "缺工作者提示词合约",
        hasUnblock: "有待查看的解阻塞任务",
        continuation: "已选续跑",
        reviewProof: "回证明室看真实结果",
      },
    };
  }
  return {
    title: "Planner desk",
    subtitle:
      "Start with planning triage. Bring wave plans, worker prompt contracts, wake-policy posture, and completion governance into one control desk so the operator can decide who moves next, what is blocked, and where truth lives.",
    actions: {
      pm: "Open PM intake",
      tower: "Open Command Tower",
      workflows: "Open Workflow Cases",
      proof: "Open Proof & Replay",
    },
    metrics: {
      runs: "Runs with planning artifacts",
      workers: "Visible worker contracts",
      unblock: "Visible unblock tasks",
      wake: "Runs anchored to wake policy",
    },
    table: {
      run: "Run",
      objective: "Wave objective",
      blocker: "Current triage",
      next: "Next action",
    },
    empty: "No planning artifacts are visible yet.",
    note: "The task contract still owns execution authority, but this desk now acts as the planning control layer: triage first, then decide whether to return to PM intake, Workflow Cases, Command Tower, or Proof & Replay.",
    openRun: "Open run detail",
    openWorkflow: "Open Workflow Cases",
    openTower: "Open Command Tower",
    openPm: "Open PM intake",
    wakeLabel: "Wake policy",
    governanceLabel: "Governance verdict",
    unblockLabel: "Unblock tasks",
    contractsLabel: "Worker contracts",
    plannedWorkersLabel: "Planned workers",
    triageTitle: "Planner triage queue",
    triageSubtitle:
      "Confirm which wave is missing worker contracts, which one already selected a continuation path, and which one should send you to unblock review next.",
    inspectionTitle: "Planning inspection archive",
    inspectionSubtitle:
      "Keep the raw planning artifacts in a second layer while the desk itself keeps minimal queue and dispatch controls close to the triage row.",
    shellLabel: "OpenVibeCoding / planner desk",
    summaryAriaLabel: "Planner desk summary",
    warningFallback: "Run list is temporarily unavailable. Try again later.",
    launchChecklistLabel: "Planner launch checklist",
    launchOpenPmHint: "Start the first wave from PM intake, then return here once the planning surface exists.",
    launchOpenTowerHint: "If work is already running but planning artifacts are missing, scan the tower before you dispatch anything else.",
    launchOpenWorkflowHint: "Workflow Cases keep the durable state once the planner row becomes real.",
    blocker: {
      missingGovernance: "Missing completion governance",
      missingContracts: "Missing worker prompt contract",
      hasUnblock: "Queued unblock tasks need review",
      continuation: "Continuation already selected",
      reviewProof: "Return to proof for live result review",
    },
  };
}

export function plannerTriage(text: ReturnType<typeof plannerText>, row: PlannerRow) {
  const continuationDecision =
    row.completionGovernance?.continuation_decision &&
    typeof row.completionGovernance.continuation_decision === "object" &&
    !Array.isArray(row.completionGovernance.continuation_decision)
      ? (row.completionGovernance.continuation_decision as Record<string, JsonValue>)
      : null;
  const selectedAction = String(continuationDecision?.selected_action || "").trim();

  if (!row.completionGovernance) {
    return {
      label: text.blocker.missingGovernance,
      nextLabel: text.openPm,
      nextHref: "/pm",
      secondaryLabel: text.openTower,
      secondaryHref: "/command-tower",
    };
  }
  if (row.workerContracts.length === 0 || row.plannedWorkerCount > row.workerContracts.length) {
    return {
      label: text.blocker.missingContracts,
      nextLabel: text.openPm,
      nextHref: "/pm",
      secondaryLabel: text.openTower,
      secondaryHref: "/command-tower",
    };
  }
  if (row.unblockTasks.length > 0) {
    return {
      label: text.blocker.hasUnblock,
      nextLabel: text.openWorkflow,
      nextHref: "/workflows",
      secondaryLabel: text.openRun,
      secondaryHref: `/runs/${encodeURIComponent(String(row.run.run_id || ""))}`,
    };
  }
  if (selectedAction && selectedAction !== "-") {
    return {
      label: `${text.blocker.continuation}: ${selectedAction}`,
      nextLabel: text.openRun,
      nextHref: `/runs/${encodeURIComponent(String(row.run.run_id || ""))}`,
      secondaryLabel: text.openTower,
      secondaryHref: "/command-tower",
    };
  }
  return {
    label: text.blocker.reviewProof,
    nextLabel: text.openRun,
    nextHref: `/runs/${encodeURIComponent(String(row.run.run_id || ""))}`,
    secondaryLabel: text.openWorkflow,
    secondaryHref: "/workflows",
  };
}

export function plannerPriorityRank(row: PlannerRow) {
  if (!row.completionGovernance) return 0;
  if (row.workerContracts.length === 0 || row.plannedWorkerCount > row.workerContracts.length) return 1;
  if (row.unblockTasks.length > 0) return 2;
  const continuationDecision =
    row.completionGovernance?.continuation_decision &&
    typeof row.completionGovernance.continuation_decision === "object" &&
    !Array.isArray(row.completionGovernance.continuation_decision)
      ? (row.completionGovernance.continuation_decision as Record<string, JsonValue>)
      : null;
  const selectedAction = String(continuationDecision?.selected_action || "").trim();
  if (selectedAction && selectedAction !== "-") return 3;
  return 4;
}

export function plannerPriorityState(text: ReturnType<typeof plannerText>, rows: PlannerRow[]): PlannerPriorityState {
  if (rows.length === 0) {
    return {
      title:
        text.title === "规划桌"
          ? "先让第一条规划波次进入系统"
          : "Seed the first planning wave",
      summary:
        text.title === "规划桌"
          ? "当前还没有可见的规划产物。先从 PM 入口发起第一条任务，再回来用规划桌做 triage 和 dispatch。"
          : "No planning artifact is visible yet. Start the first task from PM intake, then return here once the wave plan and worker contract exist.",
      tone: "warning",
      primaryHref: "/pm",
      primaryLabel: text.openPm,
      secondaryHref: "/command-tower",
      secondaryLabel: text.openTower,
      objective: "-",
      runId: "-",
    };
  }
  const leadRow = rows[0];
  const triage = plannerTriage(text, leadRow);
  const objective = String(leadRow.wavePlan?.objective || leadRow.run.task_id || "-").trim() || "-";
  const runId = String(leadRow.run.run_id || "-");
  const tone =
    !leadRow.completionGovernance || leadRow.workerContracts.length < leadRow.plannedWorkerCount
      ? "failed"
      : leadRow.unblockTasks.length > 0
        ? "warning"
        : "running";
  return {
    title:
      text.title === "规划桌"
        ? `优先处理：${triage.label}`
        : `Priority queue: ${triage.label}`,
    summary:
      text.title === "规划桌"
        ? `最该先看的波次是「${objective}」。先处理这条分诊，再决定是否继续派发、回到工作流案例，还是直接进证明室。`
        : `The highest-priority wave right now is "${objective}". Resolve this triage first, then decide whether to dispatch more work, return to Workflow Cases, or move into Proof & Replay.`,
    tone,
    primaryHref: triage.nextHref,
    primaryLabel: triage.nextLabel,
    secondaryHref: triage.secondaryHref,
    secondaryLabel: triage.secondaryLabel,
    objective,
    runId,
  };
}

async function loadPlannerRows(runs: RunSummary[]): Promise<PlannerRow[]> {
  const candidateRuns = runs.slice(0, 8);
  const rows = await Promise.all(
    candidateRuns.map(async (run) => {
      const runId = String(run.run_id || "").trim();
      if (!runId) {
        return null;
      }
      const runDetailResult = await safeLoad(
        () => fetchRun(runId),
        { run_id: runId, task_id: run.task_id, status: run.status } as RunDetailPayload,
        `Run detail ${runId}`,
      );
      const detailedRun = runDetailResult.data;
      const names = artifactNames(detailedRun);
      const hasWavePlan =
        names.includes("planning_wave_plan") || names.includes("artifacts/planning_wave_plan.json");
      const hasWorkerContracts =
        names.includes("planning_worker_prompt_contracts") ||
        names.includes("artifacts/planning_worker_prompt_contracts.json");
      const hasUnblockTasks =
        names.includes("planning_unblock_tasks") || names.includes("artifacts/planning_unblock_tasks.json");
      if (!(hasWavePlan || hasWorkerContracts || hasUnblockTasks)) {
        return null;
      }
      const [wavePlanResult, workerContractsResult, unblockTasksResult, reportsResult] = await Promise.all([
        hasWavePlan
          ? safeLoad(() => fetchArtifact(runId, "planning_wave_plan.json"), null, `Wave plan ${runId}`)
          : Promise.resolve({ data: null, warning: null }),
        hasWorkerContracts
          ? safeLoad(
              () => fetchArtifact(runId, "planning_worker_prompt_contracts.json"),
              null,
              `Worker contracts ${runId}`,
            )
          : Promise.resolve({ data: null, warning: null }),
        hasUnblockTasks
          ? safeLoad(() => fetchArtifact(runId, "planning_unblock_tasks.json"), null, `Unblock tasks ${runId}`)
          : Promise.resolve({ data: null, warning: null }),
        safeLoad(() => fetchReports(runId), [] as ReportRecord[], `Reports ${runId}`),
      ]);
      const completionGovernanceRecord = (reportsResult.data as ReportRecord[]).find(
        (report) => report.name === "completion_governance_report.json",
      );
      return {
        run: detailedRun,
        wavePlan: asRecord((wavePlanResult.data as { data?: JsonValue } | null)?.data),
        workerContracts: asRecordArray((workerContractsResult.data as { data?: JsonValue } | null)?.data),
        unblockTasks: asRecordArray((unblockTasksResult.data as { data?: JsonValue } | null)?.data),
        completionGovernance: asRecord(completionGovernanceRecord?.data as JsonValue | undefined),
        plannedWorkerCount: Number(
          asRecord((wavePlanResult.data as { data?: JsonValue } | null)?.data)?.worker_count || 0,
        ),
      } satisfies PlannerRow;
    }),
  );
  return rows.filter((row): row is PlannerRow => row !== null);
}

export default async function PlannerPage() {
  const locale = await resolveDashboardLocale();
  const text = plannerText(locale);
  const { data: runs, warning } = await safeLoad(fetchRuns, [] as RunSummary[], "Run list");
  const rows = await loadPlannerRows(Array.isArray(runs) ? runs : []);
  const sortedRows = [...rows].sort((a, b) => plannerPriorityRank(a) - plannerPriorityRank(b));
  const totalWorkerContracts = rows.reduce((sum, row) => sum + row.workerContracts.length, 0);
  const totalUnblockTasks = rows.reduce((sum, row) => sum + row.unblockTasks.length, 0);
  const wakeAnchoredRuns = rows.filter((row) => Boolean(row.wavePlan?.wake_policy_ref)).length;
  const priority = plannerPriorityState(text, sortedRows);
  const emptyChecklist =
    locale === "zh-CN"
      ? [
          {
            title: "锁定目标和验收口径",
            desc: "先在 PM 入口把目标、约束和完成信号讲清楚，规划桌才能开始工作。",
          },
          {
            title: "把第一条波次送进系统",
            desc: "没有真实波次计划，就不会有分诊队列，也不会有规划桌的优先级排序。",
          },
          {
            title: "回到规划桌继续派发",
            desc: "等规划产物出现后，再回来决定是去指挥塔、工作流案例，还是证明与回放。",
          },
        ]
      : [
          {
            title: "Lock the objective and the done signal",
            desc: "Write the objective, constraints, and acceptance bar in PM intake before you expect the planner to triage anything.",
          },
          {
            title: "Send the first wave into the system",
            desc: "Without a real wave plan there is no triage queue, no worker-contract posture, and no planner priority order.",
          },
          {
            title: "Return here for dispatch",
            desc: "Once the planning artifacts exist, come back here to choose whether the next move belongs in tower, workflow cases, or proof.",
          },
        ];

  return (
    <main className="grid" aria-labelledby="planner-page-title">
      <header className="app-section">
        <div className="planner-hero-shell">
          <div className="planner-hero-copy">
            <div>
              <p className="cell-sub mono muted">{text.shellLabel}</p>
              <h1 id="planner-page-title" className="page-title">{text.title}</h1>
              <p className="page-subtitle">{text.subtitle}</p>
              <p className="desk-question">
                {locale === "zh-CN"
                  ? "这张桌子第一眼只回答一个问题：下一波该派谁、该继续哪条线。"
                  : "This desk should answer one question first: who moves next and which wave continues."}
              </p>
            </div>
            <div className="planner-primary-actions">
              <Button asChild>
                <Link href={priority.primaryHref}>{priority.primaryLabel}</Link>
              </Button>
              <Button asChild variant="secondary">
                <Link href={priority.secondaryHref}>{priority.secondaryLabel}</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/workflows">{text.actions.workflows}</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/runs">{text.actions.proof}</Link>
              </Button>
            </div>
          </div>
          <Card className={`planner-priority-card planner-priority-card--${priority.tone}`}>
            <div className="planner-priority-head">
              <span className="cell-sub mono muted">
                {text.title === "规划桌" ? "当前最该先处理的波次" : "First thing to resolve"}
              </span>
              <Badge variant={priority.tone}>
                {rows.length === 0 ? (locale === "zh-CN" ? "发车模式" : "Launch mode") : `${rows.length} rows`}
              </Badge>
            </div>
            <strong className="planner-priority-title">{priority.title}</strong>
            <p className="planner-priority-summary">{priority.summary}</p>
            <div className="planner-priority-meta">
              <span className="cell-sub mono">{text.table.objective}: {priority.objective}</span>
              <span className="cell-sub mono">{text.table.run}: {priority.runId}</span>
            </div>
          </Card>
        </div>
      </header>

      <section className="stats-grid" aria-label={text.summaryAriaLabel}>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.runs}</p>
          <p className="metric-value">{rows.length}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "有多少条波次已经进入规划读面" : "How many waves already have visible planning surfaces."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.workers}</p>
          <p className="metric-value">{totalWorkerContracts}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "先看合约是否补齐，再决定是否继续派工" : "Check whether worker contracts are complete before dispatching more work."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.unblock}</p>
          <p className="metric-value">{totalUnblockTasks}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "解阻塞任务不该埋进原始报告里" : "Queued unblock tasks should stay visible above the raw artifacts."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.wake}</p>
          <p className="metric-value">{wakeAnchoredRuns}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "唤醒策略是否挂上，决定它是不是可续跑的规划波次" : "Wake-policy posture tells you whether the planning wave is resumable."}</p>
        </article>
      </section>

      {warning ? (
        <Card variant="compact">
          <p className="mono muted">{locale === "zh-CN" && !hasCjkText(warning) ? text.warningFallback : warning}</p>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <Card className="planner-empty-stage">
          <div className="planner-empty-shell">
            <div className="planner-empty-brief">
              <span className="cell-sub mono muted">{text.launchChecklistLabel}</span>
              <strong className="planner-empty-title">
                {locale === "zh-CN" ? "先把第一条规划波次发车，再回来做真正的分诊。" : "Start the first planning wave, then come back for real triage."}
              </strong>
              <p className="planner-empty-summary">{text.note}</p>
              <div className="planner-empty-checklist" aria-label={text.launchChecklistLabel}>
                {emptyChecklist.map((item, index) => (
                  <div key={item.title} className="planner-empty-check">
                    <span className="cell-sub mono muted">{String(index + 1).padStart(2, "0")}</span>
                    <div className="planner-empty-check-body">
                      <strong>{item.title}</strong>
                      <span>{item.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="planner-empty-grid">
              <Link href="/pm" className="planner-empty-card">
                <span className="cell-sub mono muted">DISPATCH · 01</span>
              <strong>{text.openPm}</strong>
              <span>{text.launchOpenPmHint}</span>
              </Link>
              <Link href="/command-tower" className="planner-empty-card">
                <span className="cell-sub mono muted">OBSERVE · 02</span>
              <strong>{text.openTower}</strong>
              <span>{text.launchOpenTowerHint}</span>
              </Link>
              <Link href="/workflows" className="planner-empty-card">
                <span className="cell-sub mono muted">RESUME · 03</span>
              <strong>{text.openWorkflow}</strong>
              <span>{text.launchOpenWorkflowHint}</span>
              </Link>
            </div>
          </div>
        </Card>
      ) : (
        <div className="stack-gap-4">
          <Card variant="table">
            <div className="section-header">
              <div>
                <h2 className="section-title">{text.triageTitle}</h2>
                <p>{text.triageSubtitle}</p>
              </div>
            </div>
            <table className="run-table">
              <thead>
                <tr>
                  <th scope="col">{text.table.run}</th>
                  <th scope="col">{text.table.objective}</th>
                  <th scope="col">{text.table.blocker}</th>
                  <th scope="col">{text.table.next}</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => {
                  const runId = String(row.run.run_id || "-");
                  const objective = String(row.wavePlan?.objective || row.run.task_id || "-").trim() || "-";
                  const triage = plannerTriage(text, row);
                  return (
                    <tr key={runId}>
                      <th scope="row">
                        <div className="stack-gap-2">
                          <Link href={`/runs/${encodeURIComponent(runId)}`}>{runId}</Link>
                          <span className="mono muted">{String(row.run.workflow_status || row.run.status || "-")}</span>
                        </div>
                      </th>
                      <td>
                        <div className="stack-gap-2">
                          <span>{objective}</span>
                          <span className="mono muted">
                            {text.wakeLabel}: {String(row.wavePlan?.wake_policy_ref || "-")}
                          </span>
                          <span className="mono muted">
                            {text.governanceLabel}: {String(row.completionGovernance?.overall_verdict || "-")}
                          </span>
                          <span className="mono muted">
                            {text.plannedWorkersLabel}: {row.plannedWorkerCount || 0} · {text.contractsLabel}: {row.workerContracts.length} · {text.unblockLabel}: {row.unblockTasks.length}
                          </span>
                        </div>
                      </td>
                      <td>
                        <Badge variant={row.unblockTasks.length > 0 ? "warning" : row.completionGovernance ? "running" : "failed"}>
                          {triage.label}
                        </Badge>
                      </td>
                      <td>
                        <div className="planner-row-actions">
                          <Button asChild>
                            <Link href={triage.nextHref}>{triage.nextLabel}</Link>
                          </Button>
                          <Button asChild variant="ghost">
                            <Link href={triage.secondaryHref}>{triage.secondaryLabel}</Link>
                          </Button>
                          <div className="planner-row-queue">
                            <WorkflowQueueMutationControls
                              latestRunId={runId}
                              compact
                              showQueueLatest
                              locale={locale}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mono muted mt-4">{text.note}</p>
          </Card>
          <Card asChild>
            <details className="collapsible">
              <summary>{text.inspectionTitle}</summary>
              <div className="collapsible-body">
                <p className="mono muted mb-4">{text.inspectionSubtitle}</p>
                <div className="grid-2">
                  {sortedRows.map((row) => {
                    const runId = String(row.run.run_id || "-");
                    const objective = String(row.wavePlan?.objective || row.run.task_id || "-").trim() || "-";
                    const continuationSummary = String(
                      row.completionGovernance?.continuation_decision &&
                        typeof row.completionGovernance.continuation_decision === "object" &&
                        !Array.isArray(row.completionGovernance.continuation_decision)
                        ? (row.completionGovernance.continuation_decision as Record<string, JsonValue>).selected_action || "-"
                        : "-",
                    );
                    return (
                      <Card key={`inspection:${runId}`} variant="detail">
                        <div className="stack-gap-2">
                          <span className="card-header-title">{objective}</span>
                          <span className="mono muted">{runId}</span>
                          <div className="planner-archive-list">
                            <span className="mono muted">{text.wakeLabel}: {String(row.wavePlan?.wake_policy_ref || "-")}</span>
                            <span className="mono muted">{text.governanceLabel}: {String(row.completionGovernance?.overall_verdict || "-")}</span>
                            <span className="mono muted">{text.plannedWorkersLabel}: {row.plannedWorkerCount || 0}</span>
                            <span className="mono muted">{text.contractsLabel}: {row.workerContracts.length}</span>
                            <span className="mono muted">{text.unblockLabel}: {row.unblockTasks.length}</span>
                            <span className="mono muted">Continuation: {continuationSummary}</span>
                          </div>
                          <WorkflowQueueMutationControls
                            latestRunId={runId}
                            compact
                            showQueueLatest
                            locale={locale}
                          />
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>
            </details>
          </Card>
        </div>
      )}
    </main>
  );
}
