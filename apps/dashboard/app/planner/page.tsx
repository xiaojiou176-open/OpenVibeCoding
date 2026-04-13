import { cookies } from "next/headers";
import type { Metadata } from "next";
import Link from "next/link";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@cortexpilot/frontend-shared/uiLocale";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { fetchArtifact, fetchReports, fetchRun, fetchRuns } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import type { JsonValue, ReportRecord, RunDetailPayload, RunSummary } from "../../lib/types";
import WorkflowQueueMutationControls from "../workflows/WorkflowQueueMutationControls";

export const metadata: Metadata = {
  title: "Planner desk | OpenVibeCoding",
  description:
    "Triages wave plans, worker prompt contracts, unblock tasks, and continuation governance from one planner-facing control desk.",
};

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

function plannerText(locale: "en" | "zh-CN") {
  if (locale === "zh-CN") {
    return {
      title: "规划桌",
      subtitle: "先做分诊，再看细节。把 wave plan、worker prompt contracts、wake policy 和 completion governance 放到同一张控制桌上，直接回答下一步该派谁、该回哪里、该继续还是该解阻塞。",
      actions: {
        pm: "打开 PM 入口",
        tower: "打开 Command Tower",
        workflows: "打开工作流案例",
        proof: "打开 Proof & Replay",
      },
      metrics: {
        runs: "带规划产物的 runs",
        workers: "可见 worker contracts",
        unblock: "可见 unblock tasks",
        wake: "挂了 wake policy 的 runs",
      },
      table: {
        run: "Run",
        objective: "Wave objective",
        blocker: "当前分诊",
        next: "下一步",
      },
      empty: "当前还没有可见的规划产物。",
      note: "这张桌子保持 `task_contract` 仍是唯一执行权威，但它已经不再只是 read-only 摆件：现在先做规划分诊，再决定回 PM、Workflow Cases、Command Tower 还是 Proof & Replay。",
      openRun: "打开证明室",
      openWorkflow: "打开工作流案例",
      openTower: "打开 Command Tower",
      openPm: "打开 PM 入口",
      wakeLabel: "Wake policy",
      governanceLabel: "Governance verdict",
      unblockLabel: "Unblock tasks",
      contractsLabel: "Worker contracts",
      plannedWorkersLabel: "Planned workers",
      triageTitle: "规划分诊队列",
      triageSubtitle: "先确认哪条 wave 缺 worker contract、哪条已经进入 continuation、哪条该优先处理 unblock，再去下一张桌子。",
      inspectionTitle: "规划细节档案",
      inspectionSubtitle: "把原始 planning artifact 留在第二层阅读，同时保留 planner desk 自己的 queue / dispatch 控制，不再让它只是一个跳转台。",
      blocker: {
        missingGovernance: "缺 completion governance",
        missingContracts: "缺 worker prompt contract",
        hasUnblock: "有 unblock 任务待看",
        continuation: "已选 continuation",
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
    blocker: {
      missingGovernance: "Missing completion governance",
      missingContracts: "Missing worker prompt contract",
      hasUnblock: "Queued unblock tasks need review",
      continuation: "Continuation already selected",
      reviewProof: "Return to proof for live result review",
    },
  };
}

function plannerTriage(text: ReturnType<typeof plannerText>, row: PlannerRow) {
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

function plannerPriorityRank(row: PlannerRow) {
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

function plannerPriorityState(text: ReturnType<typeof plannerText>, rows: PlannerRow[]): PlannerPriorityState {
  if (rows.length === 0) {
    return {
      title:
        text.title === "规划桌"
          ? "先让第一条规划 wave 进入系统"
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
        ? `最该先看的 wave 是「${objective}」。先处理这条 triage，再决定是否继续派发、回到 workflow case，还是直接进证明室。`
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

  return (
    <main className="grid" aria-labelledby="planner-page-title">
      <header className="app-section">
        <div className="planner-hero-shell">
          <div className="planner-hero-copy">
            <div>
              <p className="cell-sub mono muted">OpenVibeCoding / planner desk</p>
              <h1 id="planner-page-title" className="page-title">{text.title}</h1>
              <p className="page-subtitle">{text.subtitle}</p>
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
              <Badge variant={priority.tone}>{rows.length} rows</Badge>
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

      <section className="stats-grid" aria-label="Planner desk summary">
        <article className="metric-card">
          <p className="metric-label">{text.metrics.runs}</p>
          <p className="metric-value">{rows.length}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "有多少条 wave 已经进入规划读面" : "How many waves already have visible planning surfaces."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.workers}</p>
          <p className="metric-value">{totalWorkerContracts}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "先看 contract 是否补齐，再决定是否继续派工" : "Check whether worker contracts are complete before dispatching more work."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.unblock}</p>
          <p className="metric-value">{totalUnblockTasks}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "unblock task 不该埋进原始报告里" : "Queued unblock tasks should stay visible above the raw artifacts."}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">{text.metrics.wake}</p>
          <p className="metric-value">{wakeAnchoredRuns}</p>
          <p className="cell-sub mono muted">{text.title === "规划桌" ? "wake policy 是否挂上，决定它是不是可续跑的 planning wave" : "Wake-policy posture tells you whether the planning wave is resumable."}</p>
        </article>
      </section>

      {warning ? (
        <Card variant="compact">
          <p className="mono muted">{warning}</p>
        </Card>
      ) : null}

      {rows.length === 0 ? (
        <Card className="planner-empty-stage">
          <div className="empty-state-stack">
            <span className="muted">{text.empty}</span>
            <span className="mono muted">{text.note}</span>
          </div>
          <div className="planner-empty-grid">
            <Link href="/pm" className="planner-empty-card">
              <span className="cell-sub mono muted">01</span>
              <strong>{text.openPm}</strong>
              <span>{text.title === "规划桌" ? "先把第一条目标、约束和验收口径写清，再回来让 planner desk 真正开机。" : "Start the first wave from PM intake, then return here once the planning surface exists."}</span>
            </Link>
            <Link href="/command-tower" className="planner-empty-card">
              <span className="cell-sub mono muted">02</span>
              <strong>{text.openTower}</strong>
              <span>{text.title === "规划桌" ? "如果系统已经在跑，只是规划产物还没挂出来，就先回 tower 看当前谁在动。" : "If work is already running but planning artifacts are missing, scan the tower before you dispatch anything else."}</span>
            </Link>
            <Link href="/workflows" className="planner-empty-card">
              <span className="cell-sub mono muted">03</span>
              <strong>{text.openWorkflow}</strong>
              <span>{text.title === "规划桌" ? "Workflow Case 是 durable state，不是首页解释文；当 planning row 出现后，回这里继续追。" : "Workflow Cases keep the durable state once the planner row becomes real."}</span>
            </Link>
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
