import { useCallback, useEffect, useState } from "react";
import { fetchOperatorCopilotBrief, fetchReports, fetchRun } from "../lib/api";
import type { JsonValue, ReportRecord, RunDetailPayload } from "../lib/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import { DesktopCopilotPanel } from "../components/copilot/DesktopCopilotPanel";

const COMPARE_COPILOT_QUESTIONS = [
  "What changed compared with the baseline?",
  "Which delta matters most right now?",
  "What should the operator do next?",
  "Where is the queue or approval risk right now?",
];

type Props = { runId: string; onBack: () => void };

function asRecord(value: unknown): Record<string, JsonValue> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, JsonValue>) : {};
}

function asNumber(value: JsonValue | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asBoolean(value: JsonValue | undefined): boolean {
  return value === true;
}

export function RunComparePage({ runId, onBack }: Props) {
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
          badge: "No compare report",
          summary: "Compare is still in observation mode because no structured compare summary is available yet.",
          nextAction: "Go back to Run Detail, trigger replay compare, and refresh this surface once the compare report exists.",
        }
      : totalDelta === 0 && evidenceOk && llmParamsOk && llmSnapshotOk
      ? {
          badge: "Stable baseline",
          summary: "The selected baseline matches the current run across evidence hashes, expected reports, and LLM settings.",
          nextAction: "Review proof and outcome details, then decide whether to promote or close the run.",
        }
      : {
          badge: "Decision needed",
        summary: "Compare found deltas between the current run and its baseline, so this result needs operator review before you trust it.",
        nextAction: "Review the deltas below, then decide whether to replay, investigate, or keep the current run blocked.",
      };
  const hasCompareReport = Object.keys(runCompareReport).length > 0;
  const displayBadge = hasCompareReport ? compareDecision.badge : "Observation only";
  const displaySummary = hasCompareReport
    ? compareDecision.summary
    : "This compare surface does not have a `run_compare_report` yet, so only the raw replay state is available.";
  const displayNextAction = hasCompareReport
    ? compareDecision.nextAction
    : "Go back to Run Detail, run replay compare, and refresh this surface once the compare report exists.";
  const verdictBadge = !hasCompareReport ? "Observation only" : compareDecision.badge;
  const verdictSummary = !hasCompareReport
    ? "No structured compare report exists yet, so this room stays in observation mode."
    : compareDecision.badge === "Stable baseline"
      ? "The baseline, evidence chain, and LLM posture all align, so this run can move into proof review or promotion."
      : "A delta is present. Review the compare before you trust or promote this run.";

  if (loading) {
    return <div className="content"><div className="skeleton-stack-lg"><div className="skeleton skeleton-row" /></div></div>;
  }
  if (error) {
    return <div className="content"><div className="alert alert-danger">{error}</div><Button onClick={onBack}>Back</Button></div>;
  }

  return (
    <div className="content">
      <div className="compare-stage-shell">
        <div className="compare-stage-copy">
          <span className="cell-sub mono muted">OpenVibeCoding / desktop compare room</span>
          <div className="section-header">
            <div><h1 className="page-title">Run Compare</h1><p className="page-subtitle">Structured replay comparison for one run and its selected baseline.</p></div>
            <Badge>{runId}</Badge>
          </div>
          <div className="toolbar">
            <Button variant="ghost" onClick={onBack}>Back to run detail</Button>
          </div>
        </div>
        <Card className="compare-stage-verdict">
          <CardHeader><CardTitle>Current verdict</CardTitle></CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <Badge variant={!hasCompareReport ? "warning" : compareDecision.badge === "Stable baseline" ? "success" : compareDecision.badge === "No compare report" ? "warning" : "failed"}>
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
          title="AI compare copilot"
          intro="Generate one explanation-first brief for the current compare, proof, incident, queue, and approval posture before you trust the delta."
          buttonLabel="Explain these deltas"
          questionSet={COMPARE_COPILOT_QUESTIONS}
          loadBrief={() => fetchOperatorCopilotBrief(runId)}
        />
      </div>
      <div className="grid-2 compare-stage-grid">
        <Card className="compare-stage-decision">
          <CardHeader><CardTitle>Decision summary</CardTitle></CardHeader>
          <CardBody>
            <div className="stack-gap-2">
              <Badge>{displayBadge}</Badge>
              <p>{displaySummary}</p>
              <p className="muted">{displayNextAction}</p>
              <div className="compare-signal-grid">
                <div className="compare-signal-card">
                  <span className="cell-sub mono muted">Mismatched hashes</span>
                  <strong>{mismatchedCount}</strong>
                </div>
                <div className="compare-signal-card">
                  <span className="cell-sub mono muted">Missing artifacts</span>
                  <strong>{missingCount}</strong>
                </div>
                <div className="compare-signal-card">
                  <span className="cell-sub mono muted">Failed report checks</span>
                  <strong>{failedChecksCount}</strong>
                </div>
              </div>
            </div>
          </CardBody>
        </Card>
        <Card className="compare-stage-next">
          <CardHeader><CardTitle>Key deltas</CardTitle></CardHeader>
          <CardBody>
            <div className="data-list">
              <div className="data-list-row"><span className="data-list-label">Mismatched</span><span className="data-list-value mono">{mismatchedCount}</span></div>
              <div className="data-list-row"><span className="data-list-label">Missing</span><span className="data-list-value mono">{missingCount}</span></div>
              <div className="data-list-row"><span className="data-list-label">Extra</span><span className="data-list-value mono">{extraCount}</span></div>
              <div className="data-list-row"><span className="data-list-label">Missing reports</span><span className="data-list-value mono">{missingReportsCount}</span></div>
              <div className="data-list-row"><span className="data-list-label">Failed checks</span><span className="data-list-value mono">{failedChecksCount}</span></div>
              <div className="data-list-row"><span className="data-list-label">Evidence chain</span><span className="data-list-value mono">{evidenceOk ? "OK" : "Needs review"}</span></div>
              <div className="data-list-row"><span className="data-list-label">LLM params</span><span className="data-list-value mono">{llmParamsOk ? "OK" : "Changed"}</span></div>
              <div className="data-list-row"><span className="data-list-label">LLM snapshot</span><span className="data-list-value mono">{llmSnapshotOk ? "OK" : "Changed"}</span></div>
            </div>
            {incidentPack.summary ? <p className="muted mt-2">Incident: {String(incidentPack.summary)}</p> : null}
            {proofPack.summary ? <p className="muted">Proof: {String(proofPack.summary)}</p> : null}
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>Evidence archive</CardTitle></CardHeader>
          <CardBody>
            <details>
              <summary className="mono">Open raw compare payloads</summary>
              <div className="stack-gap-3 mt-3">
                <p className="muted">Keep the decision layer in front. Open the raw compare payloads only when you need to inspect the evidence stack.</p>
                <Card>
                  <CardHeader><CardTitle>Compare summary</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(compareSummary, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Run compare report</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(runCompareReport, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Replay report</CardTitle></CardHeader>
                  <CardBody><pre>{JSON.stringify(replayReport, null, 2)}</pre></CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>Run snapshot</CardTitle></CardHeader>
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
