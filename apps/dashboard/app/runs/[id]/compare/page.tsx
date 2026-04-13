import Link from "next/link";
import { Badge } from "../../../../components/ui/badge";
import { Card } from "../../../../components/ui/card";
import ControlPlaneStatusCallout from "../../../../components/control-plane/ControlPlaneStatusCallout";
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

  return (
    <main className="grid" aria-labelledby="run-compare-page-title">
      <section className="app-section">
        <div className="section-header">
          <div>
            <h1 id="run-compare-page-title">Run compare</h1>
            <p>Review the structured replay comparison without digging through the full Run Detail report stack.</p>
          </div>
          <div className="toolbar">
            <Badge className="mono">{id}</Badge>
            <Link href={`/runs/${encodeURIComponent(id)}`}>Back to run detail</Link>
          </div>
        </div>
        {!hasCompareReport ? (
          <ControlPlaneStatusCallout
            title="Compare report unavailable"
            summary="This compare surface does not have a `run_compare_report` yet, so only the raw replay state is available."
            nextAction="Go back to Run Detail, run replay compare, and refresh this page once the report exists."
            tone="warning"
            badgeLabel="Observation only"
            actions={[
              { href: `/runs/${encodeURIComponent(id)}`, label: "Back to run detail" },
            ]}
          />
        ) : (
          <ControlPlaneStatusCallout
            title="Decision summary"
            summary={decision.summary}
            nextAction={decision.nextAction}
            tone={decision.tone}
            badgeLabel={decision.badge}
            actions={[
              { href: `/runs/${encodeURIComponent(id)}`, label: "Open run detail" },
            ]}
          />
        )}
        <OperatorCopilotPanel
          runId={id}
          title="AI compare copilot"
          intro="Generate one explanation-first brief for the current compare, proof, incident, queue, and approval posture before you trust the delta."
          buttonLabel="Explain these deltas"
        />
        <div className="grid grid-2">
          <Card>
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
          <Card>
            <h3>Next operator step</h3>
            <div className="stack-gap-2">
              <p className="muted">Use compare as a decision surface first, raw JSON second.</p>
              <p className="mono">{decision.nextAction}</p>
              {incidentPack.summary ? <p className="mono">Incident: {String(incidentPack.summary)}</p> : null}
              {proofPack.summary ? <p className="mono">Proof: {String(proofPack.summary)}</p> : null}
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
