import { useState } from "react";

import type { FlightPlanCopilotBrief, OperatorCopilotBrief } from "../../lib/types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/Card";

type BriefPayload = OperatorCopilotBrief | FlightPlanCopilotBrief;

type Props = {
  title?: string;
  intro?: string;
  buttonLabel?: string;
  questionSet: string[];
  loadBrief: () => Promise<BriefPayload>;
  takeawaysHeading?: string;
  postureHeading?: string;
  summaryHeading?: string;
  causeHeading?: string;
};

function asList(values: string[] | undefined): string[] {
  return Array.isArray(values) ? values.filter((value) => typeof value === "string" && value.trim()) : [];
}

export function DesktopCopilotPanel({
  title = "AI operator copilot",
  intro,
  buttonLabel = "Generate operator brief",
  questionSet,
  loadBrief,
  takeawaysHeading = "Compare, proof, and incident",
  postureHeading = "Queue and approval posture",
  summaryHeading = "What happened",
  causeHeading = "Why we think so",
}: Props) {
  const [brief, setBrief] = useState<BriefPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isFlightPlanBrief = brief?.report_type === "flight_plan_copilot_brief";
  const scopeLabel =
    brief && "scope" in brief
      ? brief.scope || "-"
      : brief?.report_type === "flight_plan_copilot_brief"
      ? "flight_plan"
      : "-";
  const subjectLabel =
    brief && "subject_id" in brief
      ? brief.subject_id || "-"
      : brief?.report_type === "flight_plan_copilot_brief"
      ? "execution_plan_report"
      : "-";
  const takeaways = brief
    ? isFlightPlanBrief
      ? [brief.risk_takeaway, brief.capability_takeaway]
      : [brief.compare_takeaway, brief.proof_takeaway, brief.incident_takeaway]
    : [];
  const postureItems = brief
    ? isFlightPlanBrief
      ? [brief.approval_takeaway, "This brief stays advisory until a run actually starts."]
      : [brief.queue_takeaway, brief.approval_takeaway]
    : [];
  const causeText =
    brief && isFlightPlanBrief
      ? brief.risk_takeaway
      : brief && "likely_cause" in brief
      ? brief.likely_cause
      : "";

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const payload = await loadBrief();
      setBrief(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        <div className="stack-gap-2">
          {intro ? <p className="muted">{intro}</p> : null}
          <div className="row-between">
              <Badge>
              {brief
                ? brief.status === "UNAVAILABLE"
                  ? "Unavailable"
                  : isFlightPlanBrief || ("scope" in brief && brief.scope === "flight_plan")
                  ? "Advisory brief"
                  : "Grounded brief"
                : "On demand"}
            </Badge>
            <Button variant="secondary" onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? "Generating..." : brief ? "Regenerate brief" : buttonLabel}
            </Button>
          </div>
          {!brief && !error ? (
            <div className="stack-gap-2">
              <p className="muted">This panel stays bounded on purpose. It explains current truth without becoming a freeform chat surface.</p>
              <div className="chip-list">
                {questionSet.map((question) => (
                  <span key={question} className="chip">
                    {question}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {error ? <div className="alert alert-warning">{error}</div> : null}
          {brief ? (
            <div className="stack-gap-3">
              <details className="collapsible">
                <summary>Copilot boundary and truth refs</summary>
                <div className="collapsible-body stack-gap-2">
                  <div className="mono">Scope: {scopeLabel}</div>
                  <div className="mono">Subject: {subjectLabel}</div>
                  <div className="mono">Truth surfaces: {asList(brief.used_truth_surfaces).join(" | ") || "-"}</div>
                  <div className="mono">Limitations: {asList(brief.limitations).join(" | ") || "-"}</div>
                </div>
              </details>
              <div className="grid-2">
              <Card>
                <CardHeader><CardTitle>{summaryHeading}</CardTitle></CardHeader>
                <CardBody><p>{brief.summary}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{causeHeading}</CardTitle></CardHeader>
                <CardBody><p>{causeText}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{takeawaysHeading}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {takeaways.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{postureHeading}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {postureItems.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Best next action</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.recommended_actions).length > 0 ? asList(brief.recommended_actions).map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    )) : <li>No recommended actions were returned.</li>}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Top risks</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.top_risks).length > 0 ? asList(brief.top_risks).map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    )) : <li>No explicit risks were returned.</li>}
                  </ul>
                </CardBody>
              </Card>
              </div>
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}
