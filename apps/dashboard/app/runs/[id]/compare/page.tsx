import Link from "next/link";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card } from "../../../../components/ui/card";
import OperatorCopilotPanel from "../../../../components/control-plane/OperatorCopilotPanel";
import { fetchReports, fetchRun } from "../../../../lib/api";
import { safeLoad } from "../../../../lib/serverPageData";

type RunComparePageParams = {
  id: string;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asBoolean(value: unknown): boolean {
  return value === true;
}

function compareDecision(copy: Record<string, unknown>): {
  badge: string;
  tone: "success" | "warning" | "failed";
  summary: string;
  nextAction: string;
  keyDeltas: Array<{ label: string; value: number | string }>;
} {
  const mismatchedCount = asNumber(copy.mismatched_count);
  const missingCount = asNumber(copy.missing_count);
  const extraCount = asNumber(copy.extra_count);
  const missingReportsCount = asNumber(copy.missing_reports_count);
  const failedChecksCount = asNumber(copy.failed_report_checks_count);
  const evidenceOk = asBoolean(copy.evidence_ok);
  const llmParamsOk = asBoolean(copy.llm_params_ok);
  const llmSnapshotOk = asBoolean(copy.llm_snapshot_ok);
  const totalDelta =
    mismatchedCount + missingCount + extraCount + missingReportsCount + failedChecksCount;

  if (totalDelta === 0 && evidenceOk && llmParamsOk && llmSnapshotOk) {
    return {
      badge: "Stable baseline",
      tone: "success",
      summary: "The current run matches the selected baseline on evidence hashes, expected reports, and LLM configuration snapshots.",
      nextAction: "Review proof and outcome details, then decide whether to promote, approve, or share the current result.",
      keyDeltas: [
        { label: "Mismatched hashes", value: mismatchedCount },
        { label: "Missing artifacts", value: missingCount },
        { label: "Extra artifacts", value: extraCount },
        { label: "Report failures", value: failedChecksCount },
      ],
    };
  }

  const tone = totalDelta >= 3 || !evidenceOk ? "failed" : "warning";
  return {
    badge: tone === "failed" ? "Decision needed" : "Needs review",
    tone,
    summary: "The comparison found at least one delta between the current run and its baseline, so the operator should review the result before trusting it.",
    nextAction:
      tone === "failed"
        ? "Open Run Detail and inspect proof, incident, and replay context before retrying or approving."
        : "Review the key deltas below, then decide whether to keep the current run, replay it, or investigate further.",
    keyDeltas: [
      { label: "Mismatched hashes", value: mismatchedCount },
      { label: "Missing artifacts", value: missingCount },
      { label: "Extra artifacts", value: extraCount },
      { label: "Missing reports", value: missingReportsCount },
      { label: "Failed report checks", value: failedChecksCount },
      { label: "Evidence chain", value: evidenceOk ? "OK" : "Needs review" },
      { label: "LLM params", value: llmParamsOk ? "OK" : "Changed" },
      { label: "LLM snapshot", value: llmSnapshotOk ? "OK" : "Changed" },
    ],
  };
}

export default async function RunComparePage({
  params,
}: {
  params: Promise<RunComparePageParams>;
}) {
  const { id } = await params;
  const { data: run } = await safeLoad(() => fetchRun(id), { run_id: id, status: "UNKNOWN" } as any, "Run detail");
  const { data: reports } = await safeLoad(() => fetchReports(id), [] as any[], "Run reports");
  const reportList = Array.isArray(reports) ? reports : [];
  const replayReport = asRecord(reportList.find((item) => item?.name === "replay_report.json")?.data);
  const runCompareReport = asRecord(reportList.find((item) => item?.name === "run_compare_report.json")?.data);
  const proofPack = asRecord(reportList.find((item) => item?.name === "proof_pack.json")?.data);
  const incidentPack = asRecord(reportList.find((item) => item?.name === "incident_pack.json")?.data);
  const compareSummary = asRecord(runCompareReport.compare_summary);
  const decision = compareDecision(compareSummary);
  const hasCompareReport = Object.keys(runCompareReport).length > 0;
  const evidenceStatus = hasCompareReport ? (asBoolean(compareSummary.evidence_ok) ? "OK" : "Needs review") : "Unavailable";
  const llmParamsStatus = hasCompareReport ? (asBoolean(compareSummary.llm_params_ok) ? "OK" : "Changed") : "Unavailable";
  const llmSnapshotStatus = hasCompareReport ? (asBoolean(compareSummary.llm_snapshot_ok) ? "OK" : "Changed") : "Unavailable";
  const displayBadge = hasCompareReport ? decision.badge : "Observation only";
  const displaySummary = hasCompareReport
    ? decision.summary
    : "This compare surface does not have a `run_compare_report` yet, so only the raw replay state is available.";
  const displayNextAction = hasCompareReport
    ? decision.nextAction
    : "Go back to Run Detail, run replay compare, and refresh this page once the report exists.";
  const verdictTitle = !hasCompareReport
    ? "Observation mode only."
    : decision.tone === "success"
      ? "Baseline is stable."
      : "A comparison decision is required.";
  const verdictSummary = !hasCompareReport
    ? "No structured compare report exists yet, so this room stays in observation mode."
    : decision.tone === "success"
      ? "The baseline, evidence chain, and LLM posture all align, so this run can move forward into proof review or promotion."
      : "A delta is present. Review the compare before you trust or promote this run.";
  const compareTone = !hasCompareReport ? "warning" : decision.tone === "success" ? "success" : decision.tone === "failed" ? "failed" : "warning";

  return (
    <main className="grid" aria-labelledby="run-compare-page-title">
      <section className="app-section">
        <div className="compare-room-shell">
          <div className="compare-room-copy">
            <p className="cell-sub mono muted">OpenVibeCoding / compare truth room</p>
            <h1 id="run-compare-page-title">Run compare</h1>
            <p>Review the structured replay comparison without digging through the full Run Detail report stack.</p>
            <p className="cell-sub mono muted">
              Keep this room verdict-first: what changed, how serious it is, and what the operator should do next.
            </p>
          </div>
          <Card className={`compare-verdict-card compare-verdict-card--${compareTone}`}>
            <div className="compare-verdict-head">
              <span className="cell-sub mono muted">Current verdict</span>
              <Badge variant={compareTone}>{displayBadge}</Badge>
            </div>
            <strong className="compare-verdict-title">{verdictTitle}</strong>
            <p className="compare-verdict-summary">{verdictSummary}</p>
            <p className="cell-sub mono">{displayNextAction}</p>
          </Card>
        </div>
        <div className="toolbar compare-toolbar-row">
          <Badge className="mono">{id}</Badge>
          <Link href={`/runs/${encodeURIComponent(id)}`}>Back to run detail</Link>
        </div>
        <div className="compare-primary-grid">
          <Card className={`compare-decision-card compare-decision-card--${compareTone}`}>
            <h2 className="section-title">Decision summary</h2>
            <p>{displaySummary}</p>
            <div className="compare-signal-grid" aria-label="Compare signal highlights">
              {[
                { label: "Hash deltas", value: compareSummary.mismatched_count },
                { label: "Artifact gaps", value: compareSummary.missing_count },
                { label: "Unexpected extras", value: compareSummary.extra_count },
                { label: "Report gaps", value: compareSummary.missing_reports_count },
                { label: "Check failures", value: compareSummary.failed_report_checks_count },
              ].map((item) => (
                <div key={item.label} className="compare-signal-card">
                  <span className="cell-sub mono muted">{item.label}</span>
                  <strong>{String(item.value ?? 0)}</strong>
                </div>
              ))}
            </div>
            <div className="toolbar">
              <Button asChild variant="ghost">
                <Link href={`/runs/${encodeURIComponent(id)}`}>Open run detail</Link>
              </Button>
            </div>
          </Card>
          <Card className="compare-next-card">
            <h2 className="section-title">Next operator step</h2>
            <p className="muted">Use compare as a decision surface first, raw JSON second.</p>
            <p className="mono">{displayNextAction}</p>
            {incidentPack.summary ? <p className="mono">Incident: {String(incidentPack.summary)}</p> : null}
            {proofPack.summary ? <p className="mono">Proof: {String(proofPack.summary)}</p> : null}
          </Card>
        </div>
        <Card className="compare-copilot-card">
          <OperatorCopilotPanel
            runId={id}
            title="AI compare copilot"
            intro="Generate one explanation-first brief for the current compare, proof, incident, queue, and approval posture before you trust the delta."
            buttonLabel="Explain these deltas"
          />
        </Card>
        <div className="grid grid-2">
          <Card className="compare-delta-card">
            <h3>Key deltas</h3>
            <div className="data-list">
              {decision.keyDeltas.map((item) => (
                <div key={item.label} className="data-list-row">
                  <span className="data-list-label">{item.label}</span>
                  <span className="data-list-value mono">{String(item.value)}</span>
                </div>
              ))}
            </div>
          </Card>
          <Card className="compare-archive-card">
            <h3>Operator choreography</h3>
            <div className="stack-gap-2">
              <p className="muted">Keep the second card decision-oriented too. Treat this as operator choreography, not a duplicate summary.</p>
              <p className="mono">{hasCompareReport ? "Compare first → proof second → replay only after the verdict is clear." : "No compare report yet → return to Run Detail, generate compare, then re-open this room."}</p>
              <p className="mono">Evidence chain: {evidenceStatus}</p>
              <p className="mono">LLM params: {llmParamsStatus} · Snapshot: {llmSnapshotStatus}</p>
            </div>
          </Card>
          <Card asChild>
            <details className="collapsible">
              <summary>Evidence archive</summary>
              <div className="collapsible-body stack-gap-4">
                <p className="muted">
                  Keep the first screen decision-first. Open the raw compare payload only when you need to inspect the underlying proof.
                </p>
                <div className="grid grid-2">
                  <Card>
                    <h3>Run compare report</h3>
                    <pre className="mono">{JSON.stringify(runCompareReport, null, 2)}</pre>
                  </Card>
                  <Card>
                    <h3>Compare summary</h3>
                    <pre className="mono">{JSON.stringify(compareSummary, null, 2)}</pre>
                  </Card>
                  <Card>
                    <h3>Replay report</h3>
                    <pre className="mono">{JSON.stringify(replayReport, null, 2)}</pre>
                  </Card>
                  <Card>
                    <h3>Run snapshot</h3>
                    <pre className="mono">{JSON.stringify(run, null, 2)}</pre>
                  </Card>
                </div>
              </div>
            </details>
          </Card>
        </div>
      </section>
    </main>
  );
}
