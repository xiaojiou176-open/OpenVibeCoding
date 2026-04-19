import { useState } from "react";

import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { FlightPlanCopilotBrief, OperatorCopilotBrief } from "../../lib/types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/Card";

type BriefPayload = OperatorCopilotBrief | FlightPlanCopilotBrief;

type Props = {
  locale?: UiLocale;
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

function panelCopy(locale: UiLocale) {
  if (locale === "zh-CN") {
    return {
      defaultTitle: "AI 操作员副驾",
      defaultButtonLabel: "生成操作员简报",
      defaultTakeawaysHeading: "对比、证明与事故",
      defaultPostureHeading: "队列与审批态势",
      defaultSummaryHeading: "发生了什么",
      defaultCauseHeading: "为什么这样判断",
      unavailable: "不可用",
      advisoryBrief: "建议型简报",
      groundedBrief: "有依据的简报",
      onDemand: "按需生成",
      generating: "生成中...",
      regenerate: "重新生成简报",
      boundedHint: "这个面板故意保持边界清晰，只解释当前真相，不会变成自由聊天窗口。",
      flightPlanAdvisory: "这份简报在 run 真正开始之前都只是建议层。",
      boundarySummary: "副驾边界与真相引用",
      scope: "范围",
      subject: "对象",
      truthSurfaces: "真相面",
      limitations: "限制",
      bestNextAction: "最佳下一步",
      noRecommendedActions: "当前没有返回推荐动作。",
      topRisks: "顶部风险",
      noTopRisks: "当前没有返回显式风险。",
    };
  }
  return {
    defaultTitle: "AI operator copilot",
    defaultButtonLabel: "Generate operator brief",
    defaultTakeawaysHeading: "Compare, proof, and incident",
    defaultPostureHeading: "Queue and approval posture",
    defaultSummaryHeading: "What happened",
    defaultCauseHeading: "Why we think so",
    unavailable: "Unavailable",
    advisoryBrief: "Advisory brief",
    groundedBrief: "Grounded brief",
    onDemand: "On demand",
    generating: "Generating...",
    regenerate: "Regenerate brief",
    boundedHint: "This panel stays bounded on purpose. It explains current truth without becoming a freeform chat surface.",
    flightPlanAdvisory: "This brief stays advisory until a run actually starts.",
    boundarySummary: "Copilot boundary and truth refs",
    scope: "Scope",
    subject: "Subject",
    truthSurfaces: "Truth surfaces",
    limitations: "Limitations",
    bestNextAction: "Best next action",
    noRecommendedActions: "No recommended actions were returned.",
    topRisks: "Top risks",
    noTopRisks: "No explicit risks were returned.",
  };
}

export function DesktopCopilotPanel(props: Props) {
  const {
    locale = detectPreferredUiLocale() as UiLocale,
    title,
    intro,
    buttonLabel,
    questionSet,
    loadBrief,
    takeawaysHeading,
    postureHeading,
    summaryHeading,
    causeHeading,
  } = props;
  const [brief, setBrief] = useState<BriefPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const copy = panelCopy(locale);
  const resolvedTitle = title ?? copy.defaultTitle;
  const resolvedButtonLabel = buttonLabel ?? copy.defaultButtonLabel;
  const resolvedTakeawaysHeading = takeawaysHeading ?? copy.defaultTakeawaysHeading;
  const resolvedPostureHeading = postureHeading ?? copy.defaultPostureHeading;
  const resolvedSummaryHeading = summaryHeading ?? copy.defaultSummaryHeading;
  const resolvedCauseHeading = causeHeading ?? copy.defaultCauseHeading;

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
      ? [brief.approval_takeaway, copy.flightPlanAdvisory]
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
        <CardTitle>{resolvedTitle}</CardTitle>
      </CardHeader>
      <CardBody>
        <div className="stack-gap-2">
          {intro ? <p className="muted">{intro}</p> : null}
          <div className="row-between">
              <Badge>
              {brief
                ? brief.status === "UNAVAILABLE"
                  ? copy.unavailable
                  : isFlightPlanBrief || ("scope" in brief && brief.scope === "flight_plan")
                  ? copy.advisoryBrief
                  : copy.groundedBrief
                : copy.onDemand}
            </Badge>
            <Button variant="secondary" onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? copy.generating : brief ? copy.regenerate : resolvedButtonLabel}
            </Button>
          </div>
          {!brief && !error ? (
            <div className="stack-gap-2">
              <p className="muted">{copy.boundedHint}</p>
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
                <summary>{copy.boundarySummary}</summary>
                <div className="collapsible-body stack-gap-2">
                  <div className="mono">{copy.scope}: {scopeLabel}</div>
                  <div className="mono">{copy.subject}: {subjectLabel}</div>
                  <div className="mono">{copy.truthSurfaces}: {asList(brief.used_truth_surfaces).join(" | ") || "-"}</div>
                  <div className="mono">{copy.limitations}: {asList(brief.limitations).join(" | ") || "-"}</div>
                </div>
              </details>
              <div className="grid-2">
              <Card>
                <CardHeader><CardTitle>{resolvedSummaryHeading}</CardTitle></CardHeader>
                <CardBody><p>{brief.summary}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{resolvedCauseHeading}</CardTitle></CardHeader>
                <CardBody><p>{causeText}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{resolvedTakeawaysHeading}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {takeaways.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{resolvedPostureHeading}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {postureItems.map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.bestNextAction}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.recommended_actions).length > 0 ? asList(brief.recommended_actions).map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    )) : <li>{copy.noRecommendedActions}</li>}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.topRisks}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.top_risks).length > 0 ? asList(brief.top_risks).map((item, index) => (
                      <li key={`${item}-${index}`}>{item}</li>
                    )) : <li>{copy.noTopRisks}</li>}
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
