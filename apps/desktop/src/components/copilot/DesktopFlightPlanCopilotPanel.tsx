import { useState } from "react";

import type { FlightPlanCopilotBrief } from "../../lib/types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/Card";

type Props = {
  title?: string;
  intro?: string;
  buttonLabel?: string;
  loadBrief: () => Promise<FlightPlanCopilotBrief>;
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

export function DesktopFlightPlanCopilotPanel({
  title = "Flight Plan copilot",
  intro = "Generate one bounded pre-run brief grounded only in the current Flight Plan preview, not in post-run truth.",
  buttonLabel = "Explain this Flight Plan",
  loadBrief,
}: Props) {
  const [brief, setBrief] = useState<FlightPlanCopilotBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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
          <p className="muted">{intro}</p>
          <div className="row-between">
            <Badge>{brief ? (brief.status === "UNAVAILABLE" ? "Unavailable" : "Advisory brief") : "On demand"}</Badge>
            <Button variant="secondary" onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? "Generating..." : brief ? "Regenerate brief" : buttonLabel}
            </Button>
          </div>
          {!brief && !error ? (
            <div className="stack-gap-2">
              <p className="muted">This brief stays advisory. It explains the current plan, but it does not claim any post-run compare, proof, or incident truth.</p>
              <div className="chip-list">
                {QUESTION_SET.map((question) => (
                  <span key={question} className="chip">
                    {question}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          {error ? <div className="alert alert-warning">{error}</div> : null}
          {brief ? (
            <div className="grid-2">
              <Card>
                <CardHeader><CardTitle>What this plan is optimizing for</CardTitle></CardHeader>
                <CardBody><p>{brief.summary}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Main risk gate</CardTitle></CardHeader>
                <CardBody><p>{brief.risk_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Capability triggers</CardTitle></CardHeader>
                <CardBody><p>{brief.capability_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Approval posture</CardTitle></CardHeader>
                <CardBody><p>{brief.approval_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Best next action</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.recommended_actions).length > 0 ? (
                      asList(brief.recommended_actions).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    ) : (
                      <li>No recommended actions were returned.</li>
                    )}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>Top pre-run risks</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.top_risks).length > 0 ? (
                      asList(brief.top_risks).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    ) : (
                      <li>No explicit risks were returned.</li>
                    )}
                  </ul>
                </CardBody>
              </Card>
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}
