"use client";

import type { EventRecord } from "../lib/types";
import { statusVariant } from "../lib/statusPresentation";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";

type ChainReportStep = {
  index?: number;
  name?: string;
  kind?: string;
  task_id?: string;
  run_id?: string;
  status?: string;
  failure_reason?: string;
};

type ChainReport = {
  chain_id?: string;
  status?: string;
  steps?: ChainReportStep[];
};

type ChainSpecStep = {
  name?: string;
  depends_on?: string[];
  exclusive_paths?: string[];
  context_policy?: Record<string, unknown>;
  parallel_group?: string;
};

type ChainSpec = {
  steps?: ChainSpecStep[];
};

export function pickContextLabel(event: EventRecord, key: string): string {
  const raw = event.context?.[key];
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "-";
}

function StepStatusDot({ status }: { status?: string }) {
  const upper = (status || "").toUpperCase();
  let stateClass = "is-idle";
  if (["SUCCESS", "DONE", "PASSED"].some((s) => upper.includes(s))) stateClass = "is-success";
  else if (["FAIL", "ERROR"].some((s) => upper.includes(s))) stateClass = "is-failed";
  else if (["RUNNING", "IN_PROGRESS"].some((s) => upper.includes(s))) stateClass = "is-running";
  return <span aria-hidden="true" className={`chain-step-dot ${stateClass}`} />;
}

function chainStatusLabel(status?: string): string {
  const upper = (status || "").toUpperCase();
  if (!upper) return "Unknown";
  if (["SUCCESS", "DONE", "PASSED", "COMPLETED"].some((item) => upper.includes(item))) return "Success";
  if (["FAIL", "ERROR"].some((item) => upper.includes(item))) return "Failed";
  if (["RUNNING", "IN_PROGRESS"].some((item) => upper.includes(item))) return "Running";
  if (upper.includes("BLOCK")) return "Blocked";
  if (["PENDING", "WAITING"].some((item) => upper.includes(item))) return "Pending";
  return "Unknown";
}

export default function ChainView({
  chainReport,
  chainSpec,
  events,
}: {
  chainReport: ChainReport | null | undefined;
  chainSpec: ChainSpec | null | undefined;
  events: EventRecord[];
}) {
  if (!chainReport) {
    return (
      <Card>
        <div className="empty-state-stack">
          <span className="chain-muted-text">No chain report yet</span>
          <p className="muted">Reason: the current run has not produced `chain_report.json` yet, or the report is still syncing.</p>
          <p className="muted">Next step: check the Logs tab for event flow, then go back to PM and trigger `/run`.</p>
        </div>
      </Card>
    );
  }

  const steps = Array.isArray(chainReport.steps) ? chainReport.steps : [];
  const specSteps = Array.isArray(chainSpec?.steps) ? chainSpec.steps : [];
  const specMap = new Map<string, ChainSpecStep>();
  specSteps.forEach((step) => {
    if (step?.name) specMap.set(step.name, step);
  });

  const handoffs = (events || []).filter((event) => event.event === "CHAIN_HANDOFF");

  return (
    <div className="chain-view-layout">
      {/* Summary Card */}
      <Card className="chain-summary-card">
        <div className="chain-summary-header">
          <strong className="chain-summary-title">Chain summary</strong>
          <Badge variant={statusVariant(chainReport.status)}>{chainStatusLabel(chainReport.status)}</Badge>
        </div>
        <div className="chain-summary-meta">
          <div className="chain-summary-meta-group">
            <span className="chain-meta-label">Chain ID</span>
            <span className="mono chain-meta-value">{chainReport.chain_id || "-"}</span>
          </div>
          <div className="chain-summary-meta-group">
            <span className="chain-meta-label">Step count</span>
            <span className="chain-step-count">{steps.length}</span>
          </div>
        </div>
      </Card>

      {/* Steps */}
      <div className="chain-section">
        <h4 className="chain-section-title">
          Steps ({steps.length})
        </h4>
        {steps.length === 0 ? (
          <Card>
            <div className="empty-state-stack">
              <span className="mono muted">No step records yet</span>
              <p className="muted">Reason: the chain exists, but concrete steps have not been written yet or are still streaming back.</p>
              <p className="muted">Next step: refresh and retry. If it is still empty, go back to PM and trigger a new execution batch.</p>
            </div>
          </Card>
        ) : (
          steps.map((step) => {
            const stepName = step.name || "unnamed";
            const spec = specMap.get(stepName) || {};
            const depends = spec.depends_on || [];
            const exclusive = spec.exclusive_paths || [];
            const policy = spec.context_policy || {};
            const group = spec.parallel_group || "";
            return (
              <Card key={`${stepName}-${step.index ?? "na"}`} className="chain-step-card">
                <div className="chain-step-card-header">
                  <div className="chain-step-card-title-wrap">
                    <StepStatusDot status={step.status} />
                    <strong className="chain-step-title">
                      #{step.index ?? "-"} {stepName}
                    </strong>
                    {step.kind && (
                      <Badge className="chain-step-kind">{step.kind}</Badge>
                    )}
                  </div>
                  <Badge variant={statusVariant(step.status)} className="chain-step-status">
                    {chainStatusLabel(step.status)}
                  </Badge>
                </div>
                <div className="chain-step-meta">
                  {step.task_id && <span className="mono muted">task: {step.task_id}</span>}
                  {step.run_id && <span className="mono muted">run: {step.run_id}</span>}
                  {group && <span className="mono muted">group: {group}</span>}
                </div>
                {step.failure_reason && (
                  <div className="chain-step-failure">
                    {step.failure_reason}
                  </div>
                )}
                {(depends.length > 0 || exclusive.length > 0 || Object.keys(policy).length > 0) && (
                  <details>
                    <summary className="chain-step-spec-summary">
                      Spec details
                    </summary>
                    <div className="chain-step-spec-body">
                      {depends.length > 0 && (
                        <div>
                          <span className="chain-step-dep-label">Depends on:</span>
                          <div className="chain-step-dep-list">
                            {depends.map((dep) => <Badge key={dep}>{dep}</Badge>)}
                          </div>
                        </div>
                      )}
                      {exclusive.length > 0 && (
                        <pre className="mono">{JSON.stringify(exclusive, null, 2)}</pre>
                      )}
                      {Object.keys(policy).length > 0 && (
                        <pre className="mono">{JSON.stringify(policy, null, 2)}</pre>
                      )}
                    </div>
                  </details>
                )}
              </Card>
            );
          })
        )}
      </div>

      {/* Handoffs */}
      <div className="chain-section">
        <h4 className="chain-section-title">
          Handoffs ({handoffs.length})
        </h4>
        {handoffs.length === 0 ? (
          <Card>
            <span className="mono muted">No handoff events yet</span>
          </Card>
        ) : (
          <Card className="chain-handoff-list">
            {handoffs.map((event, idx) => (
              <div key={`${event.ts || "-"}-${idx}`} className={`chain-handoff-item${idx < handoffs.length - 1 ? " has-divider" : ""}`}>
                <span className="mono chain-handoff-from">{pickContextLabel(event, "from")}</span>
                <span className="chain-handoff-arrow">&rarr;</span>
                <span className="mono chain-handoff-to">{pickContextLabel(event, "to")}</span>
              </div>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}
