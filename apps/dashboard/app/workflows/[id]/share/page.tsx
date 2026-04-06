import Link from "next/link";

import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Card } from "../../../../components/ui/card";
import ControlPlaneStatusCallout from "../../../../components/control-plane/ControlPlaneStatusCallout";
import WorkflowCaseShareActions from "../../../../components/workflows/WorkflowCaseShareActions";
import { fetchQueue, fetchReports, fetchRun, fetchWorkflow } from "../../../../lib/api";
import { safeLoad } from "../../../../lib/serverPageData";

type WorkflowSharePageParams = {
  id: string;
};

function safeDecodeParam(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function asText(value: unknown, fallback = "-"): string {
  const text = String(value || "").trim();
  return text || fallback;
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function statusLabelEn(status: string | undefined): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) {
    return "Unknown";
  }
  if (["done", "success", "completed", "approved"].includes(normalized)) return "Completed";
  if (["fail", "failed", "failure", "error", "rollback", "rejected", "reject", "abort", "timeout", "blocked", "deny"].includes(normalized)) return "Failed";
  if (["running", "active", "pending", "queued", "ready"].includes(normalized)) return normalized === "ready" ? "Ready" : "Running";
  return normalized.replace(/_/g, " ");
}

function resolveLatestRunId(runs: Array<Record<string, unknown>>): string {
  const sortedRuns = [...runs];
  sortedRuns.sort((left, right) => {
    const leftTs = Date.parse(String(left.created_at || ""));
    const rightTs = Date.parse(String(right.created_at || ""));
    return (Number.isFinite(rightTs) ? rightTs : 0) - (Number.isFinite(leftTs) ? leftTs : 0);
  });
  return String(sortedRuns[0]?.run_id || "").trim();
}

export default async function WorkflowSharePage({
  params,
}: {
  params: Promise<WorkflowSharePageParams>;
}) {
  const { id } = await params;
  const workflowId = safeDecodeParam(id);
  const { data: workflowPayload, warning: workflowWarning } = await safeLoad(
    () => fetchWorkflow(workflowId),
    { workflow: { workflow_id: workflowId }, runs: [], events: [] },
    "Workflow detail",
  );
  const { data: queueItems, warning: queueWarning } = await safeLoad(
    () => fetchQueue(workflowId),
    [] as Record<string, unknown>[],
    "Queue detail",
  );

  const workflow = asRecord(workflowPayload.workflow);
  const runs = asArray<Record<string, unknown>>(workflowPayload.runs);
  const latestRunId = resolveLatestRunId(runs);
  const { data: latestRun, warning: latestRunWarning } = await safeLoad(
    () => (latestRunId ? fetchRun(latestRunId) : Promise.resolve({ run_id: "", status: "UNKNOWN" })),
    { run_id: latestRunId, status: "UNKNOWN" } as Record<string, unknown>,
    "Latest run detail",
  );
  const { data: latestRunReports, warning: latestRunReportsWarning } = await safeLoad(
    () => (latestRunId ? fetchReports(latestRunId) : Promise.resolve([])),
    [] as Record<string, unknown>[],
    "Latest run reports",
  );

  const reportList = asArray<Record<string, unknown>>(latestRunReports);
  const runCompareReport = asRecord(reportList.find((item) => item?.name === "run_compare_report.json")?.data);
  const compareSummary = asRecord(runCompareReport.compare_summary);
  const proofPack = asRecord(reportList.find((item) => item?.name === "proof_pack.json")?.data);
  const incidentPack = asRecord(reportList.find((item) => item?.name === "incident_pack.json")?.data);
  const eligibleQueueCount = asArray<Record<string, unknown>>(queueItems).filter((item) => item.eligible === true).length;
  const warnings = [workflowWarning, queueWarning, latestRunWarning, latestRunReportsWarning].filter(Boolean);
  const compareAvailable = Object.keys(runCompareReport).length > 0 && Object.keys(compareSummary).length > 0;

  const shareAsset = {
    asset_type: "workflow_case_share_v1",
    generated_at: new Date().toISOString(),
    workflow_id: asText(workflow.workflow_id, workflowId),
    title: asText(workflow.name || workflow.title || workflow.workflow_id, workflowId),
    status: asText(workflow.status, "UNKNOWN"),
    verdict: asText(workflow.verdict, "-"),
    summary: asText(workflow.summary || workflow.objective, "No summary is attached yet."),
    owner_pm: asText(workflow.owner_pm, "-"),
    project_key: asText(workflow.project_key, "-"),
    latest_run: {
      run_id: asText(latestRunId, "-"),
      status: asText((latestRun as Record<string, unknown>).status, "UNKNOWN"),
      failure_reason: asText((latestRun as Record<string, unknown>).failure_reason, ""),
    },
    queue: {
      total_items: asArray<Record<string, unknown>>(queueItems).length,
      eligible_items: eligibleQueueCount,
      sla_states: asArray<Record<string, unknown>>(queueItems).map((item) => asText(item.sla_state, "")).filter(Boolean),
    },
    warnings,
    truth_status: warnings.length > 0 ? "partial" : "ok",
    compare_status: compareAvailable ? "available" : "unavailable",
    compare_summary: compareSummary,
    proof_pack: {
      summary: asText(proofPack.summary, "No proof pack attached."),
      next_action: asText(proofPack.next_action, "-"),
      proof_ready: proofPack.proof_ready === true,
    },
    incident_pack: {
      summary: asText(incidentPack.summary, "No incident pack attached."),
      next_action: asText(incidentPack.next_action, "-"),
    },
  };

  const compareDeltaCount =
    asNumber(compareSummary.mismatched_count) +
    asNumber(compareSummary.missing_count) +
    asNumber(compareSummary.extra_count) +
    asNumber(compareSummary.failed_report_checks_count);
  const sharePath = `/workflows/${encodeURIComponent(workflowId)}/share`;
  const truthCoverageLabel = warnings.length > 0 ? "Partial truth coverage" : "Full repo-visible truth coverage";
  const galleryPunchline = !compareAvailable
    ? "This case is still gallery-ineligible until compare truth is attached."
    : compareDeltaCount === 0
    ? "This case is ready for a calm, proof-first recap because the latest compare view is aligned."
    : "This case is ready for a review-first recap because the latest compare view still shows operator-relevant deltas.";

  return (
    <main className="grid" aria-labelledby="workflow-share-title">
      <header className="app-section">
        <div className="section-header">
          <div>
            <h1 id="workflow-share-title">Workflow Case share-ready asset</h1>
            <p>
              Export a read-only case summary that combines workflow identity, queue posture, and the latest proof and replay highlights.
            </p>
          </div>
          <div className="toolbar">
            <Badge>{statusLabelEn(String(workflow.status || ""))}</Badge>
            <Button asChild variant="secondary">
              <Link href={`/workflows/${encodeURIComponent(workflowId)}`}>Back to Workflow Case</Link>
            </Button>
          </div>
        </div>
      </header>

      {warnings.length > 0 ? (
        <section className="app-section">
          <ControlPlaneStatusCallout
            title="Share-ready asset is in read-only degraded mode"
            summary={warnings.join(" ")}
            nextAction="Use the visible asset as a partial recap only. Refresh the workflow case before sharing it as a final summary."
            tone="warning"
            badgeLabel="Partial context"
          />
        </section>
      ) : null}

      <section className="app-section" aria-label="Workflow case asset summary">
        <div className="grid grid-3">
          <Card>
            <h3>Case identity</h3>
            <div className="mono">workflow_id: {shareAsset.workflow_id}</div>
            <div className="mono">Title: {shareAsset.title}</div>
            <div className="mono">Status: {statusLabelEn(shareAsset.status)}</div>
            <div className="mono">Verdict: {shareAsset.verdict}</div>
            <div className="mono">Owner: {shareAsset.owner_pm}</div>
            <div className="mono">Project: {shareAsset.project_key}</div>
          </Card>
          <Card>
            <h3>Why this case matters</h3>
            <p className="muted">{shareAsset.summary}</p>
            <p className="mono">
              Latest run: {shareAsset.latest_run.run_id} / {statusLabelEn(shareAsset.latest_run.status)}
            </p>
          </Card>
          <Card>
            <h3>Queue posture</h3>
            <div className="mono">Queue items: {shareAsset.queue.total_items}</div>
            <div className="mono">Eligible now: {shareAsset.queue.eligible_items}</div>
            <div className="mono">
              SLA states: {shareAsset.queue.sla_states.length > 0 ? shareAsset.queue.sla_states.join(" | ") : "-"}
            </div>
          </Card>
          <Card>
            <h3>Truth coverage</h3>
            <p className="muted">{truthCoverageLabel}</p>
            <div className="mono">truth_status: {shareAsset.truth_status}</div>
            <div className="mono">compare_status: {shareAsset.compare_status}</div>
            <div className="mono">proof_ready: {shareAsset.proof_pack.proof_ready ? "true" : "false"}</div>
            <div className="mono">warning_count: {warnings.length}</div>
          </Card>
          <Card>
            <h3>Proof &amp; Replay highlight</h3>
            <p className="muted">
              {!compareAvailable
                ? "The latest compare summary is unavailable, so this share-ready asset stays partial until compare truth is attached."
                : compareDeltaCount === 0
                ? "The latest compare summary is currently aligned with its baseline."
                : "The latest compare summary still shows operator-relevant deltas."}
            </p>
            <p className="mono">Proof: {shareAsset.proof_pack.summary}</p>
            <p className="mono">Incident: {shareAsset.incident_pack.summary}</p>
          </Card>
          <Card>
            <h3>Gallery-ready capsule</h3>
            <p className="muted">{galleryPunchline}</p>
            <p className="mono">Share headline: {shareAsset.title}</p>
            <p className="mono">Operator posture: {shareAsset.latest_run.status === "UNKNOWN" ? "Review workflow first" : "Review latest run first"}</p>
            <p className="mono">Public-safe mode: read-only recap only</p>
          </Card>
          <Card>
            <h3>Best next share context</h3>
            <p className="muted">
              Use this page when you need a read-only recap for review, handoff, or proof sharing without sending people back through the full operator UI.
            </p>
            <div className="toolbar">
              {latestRunId ? (
                <Button asChild variant="secondary">
                  <Link href={`/runs/${encodeURIComponent(latestRunId)}`}>Open latest run</Link>
                </Button>
              ) : null}
              {latestRunId ? (
                <Button asChild variant="secondary">
                  <Link href={`/runs/${encodeURIComponent(latestRunId)}/compare`}>Open compare surface</Link>
                </Button>
              ) : null}
            </div>
          </Card>
          <Card>
            <h3>Export and share</h3>
            <WorkflowCaseShareActions
              sharePath={sharePath}
              fileName={`workflow-case-${workflowId}-share-v1.json`}
              payload={shareAsset}
            />
          </Card>
        </div>
      </section>
    </main>
  );
}
