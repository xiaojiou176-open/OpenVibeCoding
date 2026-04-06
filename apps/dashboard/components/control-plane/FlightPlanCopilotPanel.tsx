"use client";

import { useState } from "react";
import { fetchFlightPlanCopilotBrief } from "../../lib/api";
import type { ExecutionPlanReport, OperatorCopilotBrief } from "../../lib/types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import ControlPlaneStatusCallout from "./ControlPlaneStatusCallout";

type Props = {
  preview: ExecutionPlanReport;
  title?: string;
  intro?: string;
  buttonLabel?: string;
};

const QUESTION_SET = [
  "What is the most important risk gate before execution starts?",
  "Why are these capabilities triggered?",
  "What should the operator confirm before starting?",
  "Where is this plan most likely to fail?",
];

function asList(values: string[] | undefined): string[] {
  return Array.isArray(values) ? values.filter((value) => typeof value === "string" && value.trim()) : [];
}

export default function FlightPlanCopilotPanel({
  preview,
  title = "Flight Plan copilot",
  intro = "Generate one bounded pre-run brief grounded only in the current Flight Plan preview, not in post-run truth.",
  buttonLabel = "Explain this Flight Plan",
}: Props) {
  const [brief, setBrief] = useState<OperatorCopilotBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchFlightPlanCopilotBrief(preview);
      setBrief(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <div className="stack-gap-3">
        <div className="section-header">
          <div>
            <h3>{title}</h3>
            <p className="muted">{intro}</p>
          </div>
          <div className="toolbar">
            <Badge>{brief ? (brief.status === "UNAVAILABLE" ? "Unavailable" : "Advisory brief") : "On demand"}</Badge>
            <Button onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? "Generating..." : brief ? "Regenerate brief" : buttonLabel}
            </Button>
          </div>
        </div>
        {!brief && !error ? (
          <div className="stack-gap-2">
            <p className="muted">This brief stays advisory. It explains the current plan, but it does not claim any post-run compare, proof, or incident truth.</p>
            <div className="toolbar" aria-label="Flight Plan copilot question set">
              {QUESTION_SET.map((question) => (
                <Badge key={question}>{question}</Badge>
              ))}
            </div>
          </div>
        ) : null}
        {error ? (
          <ControlPlaneStatusCallout
            title="Flight Plan copilot request failed"
            summary={error}
            nextAction="Retry the brief first. If the same failure persists, keep using the sign-off checklist and contract preview directly."
            tone="warning"
            badgeLabel="Retryable"
          />
        ) : null}
        {brief ? (
          <div className="stack-gap-3">
            {brief.status === "UNAVAILABLE" ? (
              <ControlPlaneStatusCallout
                title="Flight Plan copilot is unavailable"
                summary={brief.summary}
                nextAction={brief.recommended_actions[0] || "Review the sign-off checklist directly until provider access is restored."}
                tone="warning"
                badgeLabel="Advisory only"
              />
            ) : null}
            <div className="grid grid-2">
              <Card>
                <h4>What this plan is optimizing for</h4>
                <p className="muted">{brief.summary}</p>
              </Card>
              <Card>
                <h4>Main risk gate</h4>
                <p className="muted">{brief.likely_cause}</p>
              </Card>
              <Card>
                <h4>Capability triggers</h4>
                <p className="muted">{brief.compare_takeaway}</p>
              </Card>
              <Card>
                <h4>Approval posture</h4>
                <p className="muted">{brief.approval_takeaway}</p>
              </Card>
              <Card>
                <h4>Best next action</h4>
                <ul className="pm-question-list">
                  {asList(brief.recommended_actions).length > 0 ? (
                    asList(brief.recommended_actions).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                  ) : (
                    <li>No recommended actions were returned.</li>
                  )}
                </ul>
              </Card>
              <Card>
                <h4>Top pre-run risks</h4>
                <ul className="pm-question-list">
                  {asList(brief.top_risks).length > 0 ? (
                    asList(brief.top_risks).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                  ) : (
                    <li>No explicit risks were returned.</li>
                  )}
                </ul>
              </Card>
            </div>
            <details>
              <summary className="pm-details-summary">Flight Plan copilot boundary and truth refs</summary>
              <div className="stack-gap-2">
                <div className="data-list">
                  <div className="data-list-row"><span className="data-list-label">Status</span><span className="data-list-value mono">{brief.status}</span></div>
                  <div className="data-list-row"><span className="data-list-label">Provider</span><span className="data-list-value mono">{brief.provider}</span></div>
                  <div className="data-list-row"><span className="data-list-label">Model</span><span className="data-list-value mono">{brief.model}</span></div>
                </div>
                <div className="mono">Questions answered: {asList(brief.questions_answered).join(" | ") || "-"}</div>
                <div className="mono">Truth surfaces: {asList(brief.used_truth_surfaces).join(" | ") || "-"}</div>
                <div className="mono">Limitations: {asList(brief.limitations).join(" | ") || "-"}</div>
              </div>
            </details>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
