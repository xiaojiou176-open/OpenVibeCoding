import { useCallback, useEffect, useState } from "react";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { fetchOperatorCopilotBrief, fetchReports, fetchRun } from "../lib/api";
import type { JsonValue, ReportRecord, RunDetailPayload } from "../lib/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import { DesktopCopilotPanel } from "../components/copilot/DesktopCopilotPanel";

type Props = { runId: string; onBack: () => void; locale?: UiLocale };

function asRecord(value: unknown): Record<string, JsonValue> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, JsonValue>) : {};
}

function asNumber(value: JsonValue | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asBoolean(value: JsonValue | undefined): boolean {
  return value === true;
}

function compareCopy(locale: UiLocale) {
  if (locale === "zh-CN") {
    return {
      questions: [
        "和基线相比，发生了什么变化？",
        "现在最值得处理的是哪条差异？",
        "操作员下一步应该做什么？",
        "队列或审批风险现在在哪里？",
      ],
      compareReportMissing: "缺失",
      unavailable: "不可用",
      replayCompare: "重跑 compare",
      awaitingReport: "等待报告",
      title: "运行对比",
      subtitle: "针对当前 run 与所选基线做结构化回放对比。",
      backToRunDetail: "返回证明室",
      currentVerdictLabel: "当前对比结论",
      decisionSummary: "决策摘要",
      keyDeltas: "关键差异",
      recoveryPath: "恢复路径",
      evidenceArchive: "证据归档",
      openRawPayloads: "打开原始对比载荷",
      keepDecisionLayer:
        "先把决策层放在前面。只有当你真的需要往下检查证据栈时，再打开原始 compare 载荷。",
      compareSummaryTitle: "对比摘要",
      runCompareReportTitle: "运行对比报告",
      replayReportTitle: "回放报告",
      runSnapshotTitle: "运行快照",
      operatorCopilotTitle: "AI 对比副驾",
      operatorCopilotIntro: "先围绕当前 compare、proof、incident、queue、approval 态势生成一份解释优先的简报，再决定是否相信这次差异。",
      operatorCopilotButton: "解释这些差异",
      noCompareReport: "暂无 compare 报告",
      observationOnly: "仅观察",
      stableBaseline: "基线稳定",
      decisionNeeded: "需要决策",
      compareObservationSummary: "当前还没有结构化 compare 摘要，因此这个对比面暂时停留在观察模式。",
      compareObservationNext: "先回到证明室触发 replay compare，等 compare 报告生成后再回来刷新。",
      stableSummary: "所选基线与当前 run 在证据哈希、预期报告和 LLM 配置上保持一致。",
      stableNext: "接下来去看 proof 和 outcome，再决定是提升还是关闭这个 run。",
      changedSummary: "对比发现当前 run 与基线之间存在差异，因此在你信任这个结果之前需要先做人审。",
      changedNext: "先看下面的差异，再决定是 replay、调查，还是继续阻塞当前 run。",
      noCompareSurface: "这个 compare 面还没有 `run_compare_report`，因此目前只能看到原始 replay 状态。",
      noCompareSurfaceNext: "先回到证明室运行 replay compare，等 compare 报告出现后再回来刷新。",
      verdictObservation: "当前还没有结构化 compare 报告，因此这个房间只能停留在观察模式。",
      verdictStable: "基线、证据链和 LLM 姿态都对齐了，这个 run 可以继续进入 proof 复核或提升流程。",
      verdictChanged: "已经出现差异。在你信任或提升这个 run 之前，先完成 compare 复核。",
      mismatchedHashes: "不匹配哈希",
      missingArtifacts: "缺失产物",
      failedChecks: "失败检查",
      mismatched: "不匹配",
      missing: "缺失",
      extra: "额外",
      missingReports: "缺少报告",
      evidenceChain: "证据链",
      llmParams: "LLM 参数",
      llmSnapshot: "LLM 快照",
      incidentPrefix: "事故",
      proofPrefix: "证明",
      ok: "正常",
      needsReview: "需要复核",
      changed: "已变化",
    };
  }
  return {
    questions: [
      "What changed compared with the baseline?",
      "Which delta matters most right now?",
      "What should the operator do next?",
      "Where is the queue or approval risk right now?",
    ],
    compareReportMissing: "Missing",
    unavailable: "Unavailable",
    replayCompare: "Replay compare",
    awaitingReport: "Awaiting report",
    title: "Run Compare",
    subtitle: "Structured replay comparison for one run and its selected baseline.",
    backToRunDetail: "Back to run detail",
    currentVerdictLabel: "Current compare verdict",
    decisionSummary: "Decision summary",
    keyDeltas: "Key deltas",
    recoveryPath: "Recovery path",
    evidenceArchive: "Evidence archive",
    openRawPayloads: "Open raw compare payloads",
    keepDecisionLayer: "Keep the decision layer in front. Open the raw compare payloads only when you need to inspect the evidence stack.",
    compareSummaryTitle: "Compare summary",
    runCompareReportTitle: "Run compare report",
    replayReportTitle: "Replay report",
    runSnapshotTitle: "Run snapshot",
    operatorCopilotTitle: "AI compare copilot",
    operatorCopilotIntro: "Generate one explanation-first brief for the current compare, proof, incident, queue, and approval posture before you trust the delta.",
    operatorCopilotButton: "Explain these deltas",
    noCompareReport: "No compare report",
    observationOnly: "Observation only",
    stableBaseline: "Stable baseline",
    decisionNeeded: "Decision needed",
    compareObservationSummary: "Compare is still in observation mode because no structured compare summary is available yet.",
    compareObservationNext: "Go back to Run Detail, trigger replay compare, and refresh this surface once the compare report exists.",
    stableSummary: "The selected baseline matches the current run across evidence hashes, expected reports, and LLM settings.",
    stableNext: "Review proof and outcome details, then decide whether to promote or close the run.",
    changedSummary: "Compare found deltas between the current run and its baseline, so this result needs operator review before you trust it.",
    changedNext: "Review the deltas below, then decide whether to replay, investigate, or keep the current run blocked.",
    noCompareSurface: "This compare surface does not have a `run_compare_report` yet, so only the raw replay state is available.",
    noCompareSurfaceNext: "Go back to Run Detail, run replay compare, and refresh this surface once the compare report exists.",
    verdictObservation: "No structured compare report exists yet, so this room stays in observation mode.",
    verdictStable: "The baseline, evidence chain, and LLM posture all align, so this run can move into proof review or promotion.",
    verdictChanged: "A delta is present. Review the compare before you trust or promote this run.",
    mismatchedHashes: "Mismatched hashes",
    missingArtifacts: "Missing artifacts",
    failedChecks: "Failed report checks",
    mismatched: "Mismatched",
    missing: "Missing",
    extra: "Extra",
    missingReports: "Missing reports",
    evidenceChain: "Evidence chain",
    llmParams: "LLM params",
    llmSnapshot: "LLM snapshot",
    incidentPrefix: "Incident",
    proofPrefix: "Proof",
    ok: "OK",
    needsReview: "Needs review",
    changed: "Changed",
  };
}

function observationSignalCards(locale: UiLocale) {
  const copy = compareCopy(locale);
  return [
    { label: locale === "zh-CN" ? "对比报告" : "Compare report", value: copy.compareReportMissing },
    { label: copy.evidenceChain, value: copy.unavailable },
    { label: locale === "zh-CN" ? "下一步" : "Next move", value: copy.replayCompare },
  ];
}

function observationDeltaRows(locale: UiLocale) {
  const copy = compareCopy(locale);
  return [
    { label: locale === "zh-CN" ? "对比态势" : "Compare posture", value: copy.awaitingReport },
    { label: copy.evidenceChain, value: copy.unavailable },
    { label: copy.llmParams, value: copy.unavailable },
    { label: copy.llmSnapshot, value: copy.unavailable },
  ];
}

export function RunComparePage({ runId, onBack, locale = detectPreferredUiLocale() as UiLocale }: Props) {
  const copy = compareCopy(locale);
  const [run, setRun] = useState<RunDetailPayload | null>(null);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [runPayload, reportPayload] = await Promise.all([fetchRun(runId), fetchReports(runId)]);
      setRun(runPayload);
      setReports(Array.isArray(reportPayload) ? reportPayload : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const replayReport = asRecord(reports.find((item) => item.name === "replay_report.json")?.data);
  const runCompareReport = asRecord(reports.find((item) => item.name === "run_compare_report.json")?.data);
  const compareSummary = asRecord(runCompareReport.compare_summary);
  const proofPack = asRecord(reports.find((item) => item.name === "proof_pack.json")?.data);
  const incidentPack = asRecord(reports.find((item) => item.name === "incident_pack.json")?.data);

  const mismatchedCount = asNumber(compareSummary.mismatched_count);
  const missingCount = asNumber(compareSummary.missing_count);
  const extraCount = asNumber(compareSummary.extra_count);
  const missingReportsCount = asNumber(compareSummary.missing_reports_count);
  const failedChecksCount = asNumber(compareSummary.failed_report_checks_count);
  const evidenceOk = asBoolean(compareSummary.evidence_ok);
  const llmParamsOk = asBoolean(compareSummary.llm_params_ok);
  const llmSnapshotOk = asBoolean(compareSummary.llm_snapshot_ok);
  const totalDelta = mismatchedCount + missingCount + extraCount + missingReportsCount + failedChecksCount;
  const compareDecision =
    Object.keys(compareSummary).length === 0
      ? {
          badge: copy.noCompareReport,
          summary: copy.compareObservationSummary,
          nextAction: copy.compareObservationNext,
        }
      : totalDelta === 0 && evidenceOk && llmParamsOk && llmSnapshotOk
      ? {
          badge: copy.stableBaseline,
          summary: copy.stableSummary,
          nextAction: copy.stableNext,
        }
      : {
          badge: copy.decisionNeeded,
        summary: copy.changedSummary,
        nextAction: copy.changedNext,
      };
  const hasCompareReport = Object.keys(runCompareReport).length > 0;
  const displayBadge = hasCompareReport ? compareDecision.badge : copy.observationOnly;
  const displaySummary = hasCompareReport
    ? compareDecision.summary
    : copy.noCompareSurface;
  const displayNextAction = hasCompareReport
    ? compareDecision.nextAction
    : copy.noCompareSurfaceNext;
  const actionPanelTitle = hasCompareReport ? copy.keyDeltas : copy.recoveryPath;
  const actionPanelIntro = hasCompareReport
    ? ""
    : locale === "zh-CN"
      ? "当前还没有 compare 报告，因此这个面板只保留最短恢复路径。"
      : "No compare report exists yet, so this panel stays focused on the shortest recovery path.";
  const verdictBadge = !hasCompareReport ? copy.observationOnly : compareDecision.badge;
  const verdictSummary = !hasCompareReport
    ? copy.verdictObservation
    : compareDecision.badge === copy.stableBaseline
      ? copy.verdictStable
      : copy.verdictChanged;
  const evidenceStatus = hasCompareReport ? (evidenceOk ? copy.ok : copy.needsReview) : copy.unavailable;
  const llmParamsStatus = hasCompareReport ? (llmParamsOk ? copy.ok : copy.changed) : copy.unavailable;
  const llmSnapshotStatus = hasCompareReport ? (llmSnapshotOk ? copy.ok : copy.changed) : copy.unavailable;
  const signalCards = hasCompareReport
    ? [
        { label: copy.mismatchedHashes, value: String(mismatchedCount) },
        { label: copy.missingArtifacts, value: String(missingCount) },
        { label: copy.failedChecks, value: String(failedChecksCount) },
      ]
    : observationSignalCards(locale);
  const deltaRows = hasCompareReport
    ? [
        { label: copy.mismatched, value: String(mismatchedCount) },
        { label: copy.missing, value: String(missingCount) },
        { label: copy.extra, value: String(extraCount) },
        { label: copy.missingReports, value: String(missingReportsCount) },
        { label: copy.failedChecks, value: String(failedChecksCount) },
        { label: copy.evidenceChain, value: evidenceStatus },
        { label: copy.llmParams, value: llmParamsStatus },
        { label: copy.llmSnapshot, value: llmSnapshotStatus },
      ]
    : observationDeltaRows(locale);

  if (loading) {
    return <div className="content"><div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /></div></div>;
  }
  if (error) {
    return <div className="content"><div className="alert alert-danger">{error}</div><Button onClick={onBack}>{locale === "zh-CN" ? "返回" : "Back"}</Button></div>;
  }

  return (
    <div className="content">
      <div className="compare-stage-shell">
        <div className="compare-stage-copy">
          <span className="cell-sub mono muted">{locale === "zh-CN" ? "OpenVibeCoding / 桌面对比室" : "OpenVibeCoding / desktop compare room"}</span>
          <div className="section-header">
            <div><h1 className="page-title">{copy.title}</h1><p className="page-subtitle">{copy.subtitle}</p></div>
            <Badge>{runId}</Badge>
          </div>
          <div className="toolbar">
            <Button variant="ghost" onClick={onBack}>{copy.backToRunDetail}</Button>
          </div>
        </div>
        <Card className="compare-stage-verdict" aria-label={copy.currentVerdictLabel}>
          <CardHeader><CardTitle>{locale === "zh-CN" ? "当前结论" : "Current verdict"}</CardTitle></CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <Badge variant={!hasCompareReport ? "warning" : compareDecision.badge === copy.stableBaseline ? "success" : compareDecision.badge === copy.noCompareReport ? "warning" : "failed"}>
                {verdictBadge}
              </Badge>
              <p>{verdictSummary}</p>
              <p className="muted">{displayNextAction}</p>
            </div>
          </CardBody>
        </Card>
      </div>
      <div className="mb-4">
        <DesktopCopilotPanel
          locale={locale}
          title={copy.operatorCopilotTitle}
          intro={copy.operatorCopilotIntro}
          buttonLabel={copy.operatorCopilotButton}
          questionSet={copy.questions}
          loadBrief={() => fetchOperatorCopilotBrief(runId)}
        />
      </div>
      <div className="grid-2 compare-stage-grid">
        <Card className="compare-stage-decision">
          <CardHeader><CardTitle>{copy.decisionSummary}</CardTitle></CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <Badge>{displayBadge}</Badge>
              <p>{displaySummary}</p>
              <p className="muted">{displayNextAction}</p>
              <div className="compare-signal-grid">
                {signalCards.map((item) => (
                  <div key={item.label} className="compare-signal-card">
                    <span className="cell-sub mono muted">{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>
        <Card className="compare-stage-next">
          <CardHeader><CardTitle>{actionPanelTitle}</CardTitle></CardHeader>
          <CardBody>
            {actionPanelIntro ? <p className="muted">{actionPanelIntro}</p> : null}
            <div className="data-list">
              {deltaRows.map((item) => (
                <div key={item.label} className="data-list-row">
                  <span className="data-list-label">{item.label}</span>
                  <span className="data-list-value mono">{item.value}</span>
                </div>
              ))}
            </div>
            {incidentPack.summary ? <p className="muted mt-2">{copy.incidentPrefix}: {String(incidentPack.summary)}</p> : null}
            {proofPack.summary ? <p className="muted">{copy.proofPrefix}: {String(proofPack.summary)}</p> : null}
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>{copy.evidenceArchive}</CardTitle></CardHeader>
          <CardBody>
            <details>
              <summary className="mono">{copy.openRawPayloads}</summary>
              <div className="stack-gap-3 mt-3">
                <p className="muted">{copy.keepDecisionLayer}</p>
                <Card>
                  <CardHeader><CardTitle>{copy.compareSummaryTitle}</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(compareSummary, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>{copy.runCompareReportTitle}</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(runCompareReport, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>{copy.replayReportTitle}</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(replayReport, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>{copy.runSnapshotTitle}</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(run, null, 2)}</pre></CardBody>
                </Card>
              </div>
            </details>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
