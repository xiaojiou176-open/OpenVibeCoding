"use client";

import { useState } from "react";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import ControlPlaneStatusCallout from "./ControlPlaneStatusCallout";
import { fetchOperatorCopilotBrief, fetchWorkflowCopilotBrief } from "../../lib/api";
import type { OperatorCopilotBrief } from "../../lib/types";

type Props = {
  runId?: string;
  workflowId?: string;
  title?: string;
  intro?: string;
  buttonLabel?: string;
  questionSet?: string[];
  onGenerate?: () => Promise<OperatorCopilotBrief>;
  takeawaysHeading?: string;
  postureHeading?: string;
};

const DEFAULT_QUESTION_SET = [
  "Why did this run fail or get blocked?",
  "What changed compared with the baseline?",
  "What is the next operator action?",
  "Where is the workflow or queue risk right now?",
];

function asList(values: string[] | undefined): string[] {
  return Array.isArray(values) ? values.filter((value) => typeof value === "string" && value.trim()) : [];
}

export default function OperatorCopilotPanel({
  runId,
  workflowId,
  title = "AI operator copilot",
  intro = "Generate one bounded operator brief grounded in current run, compare, proof, incident, workflow, queue, and approval truth.",
  buttonLabel = "Generate operator brief",
  questionSet = DEFAULT_QUESTION_SET,
  onGenerate,
  takeawaysHeading = "Compare, proof, and incident",
  postureHeading = "Queue and approval posture",
}: Props) {
  const [brief, setBrief] = useState<OperatorCopilotBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const workflowIdStr = String(workflowId || "").trim();
      const runIdStr = String(runId || "").trim();
      const payload = await (
        onGenerate
          ? onGenerate()
          : workflowIdStr
          ? fetchWorkflowCopilotBrief(workflowIdStr)
          : fetchOperatorCopilotBrief(runIdStr)
      );
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
            <Badge>
              {brief
                ? brief.status === "UNAVAILABLE"
                  ? "Unavailable"
                  : brief.scope === "flight_plan"
                  ? "Advisory brief"
                  : "Grounded brief"
                : "On demand"}
            </Badge>
            <Button onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? "Generating..." : brief ? "Regenerate brief" : buttonLabel}
            </Button>
          </div>
        </div>
        {!brief && !error ? (
          <div className="stack-gap-2">
            <p className="muted">V1 stays bounded on purpose. It answers a fixed operator question set before it becomes a broader assistant.</p>
            <div className="toolbar" aria-label="Operator copilot question set">
              {questionSet.map((question) => (
                <Badge key={question}>{question}</Badge>
              ))}
            </div>
          </div>
        ) : null}
        {error ? (
          <ControlPlaneStatusCallout
            title="Operator copilot request failed"
            summary={error}
            nextAction="Retry the brief first. If the same failure persists, inspect compare, proof, incident, workflow, and approval surfaces directly."
            tone="warning"
            badgeLabel="Retryable"
          />
        ) : null}
        {brief ? (
          <div className="stack-gap-3">
            {brief.status === "UNAVAILABLE" ? (
              <ControlPlaneStatusCallout
                title="AI operator copilot is unavailable"
                summary={brief.summary}
                nextAction={brief.recommended_actions[0] || "Inspect the existing decision surfaces directly until provider access is restored."}
                tone="warning"
                badgeLabel="Read directly"
              />
            ) : null}
            <div className="grid grid-2">
              <Card>
                <h4>What happened</h4>
                <p className="muted">{brief.summary}</p>
              </Card>
              <Card>
                <h4>Why we think so</h4>
                <p className="muted">{brief.likely_cause}</p>
              </Card>
              <Card>
                <h4>{takeawaysHeading}</h4>
                <ul className="pm-question-list">
                  <li>{brief.compare_takeaway}</li>
                  <li>{brief.proof_takeaway}</li>
                  <li>{brief.incident_takeaway}</li>
                </ul>
              </Card>
              <Card>
                <h4>{postureHeading}</h4>
                <ul className="pm-question-list">
                  <li>{brief.queue_takeaway}</li>
                  <li>{brief.approval_takeaway}</li>
                </ul>
              </Card>
              <Card>
                <h4>Best next action</h4>
                <ul className="pm-question-list">
                  {asList(brief.recommended_actions).length > 0 ? asList(brief.recommended_actions).map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  )) : <li>No recommended actions were returned.</li>}
                </ul>
              </Card>
              <Card>
                <h4>Top risks</h4>
                <ul className="pm-question-list">
                  {asList(brief.top_risks).length > 0 ? asList(brief.top_risks).map((item, index) => (
                    <li key={`${item}-${index}`}>{item}</li>
                  )) : <li>No explicit risks were returned.</li>}
                </ul>
              </Card>
            </div>
            <details>
              <summary className="pm-details-summary">Copilot boundary and truth refs</summary>
              <div className="stack-gap-2">
                <div className="data-list">
                  <div className="data-list-row"><span className="data-list-label">Scope</span><span className="data-list-value mono">{brief.scope || "-"}</span></div>
                  <div className="data-list-row"><span className="data-list-label">Subject</span><span className="data-list-value mono">{brief.subject_id || "-"}</span></div>
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
