import { useState } from "react";

import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import type { FlightPlanCopilotBrief } from "../../lib/types";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "../ui/Card";

type Props = {
  locale?: UiLocale;
  title?: string;
  intro?: string;
  buttonLabel?: string;
  loadBrief: () => Promise<FlightPlanCopilotBrief>;
};

function panelCopy(locale: UiLocale) {
  if (locale === "zh-CN") {
    return {
      defaultTitle: "Flight Plan 副驾",
      defaultIntro: "生成一份只基于当前 Flight Plan 预览的边界化预跑前简报，而不是冒充 post-run 真相。",
      defaultButtonLabel: "解释这份 Flight Plan",
      questionSet: [
        "执行开始前最重要的风险门是什么？",
        "为什么会触发这些能力？",
        "操作员在开始前应该先确认什么？",
        "这份计划最可能在哪里失败？",
      ],
      unavailable: "不可用",
      advisoryBrief: "建议型简报",
      onDemand: "按需生成",
      generating: "生成中...",
      regenerate: "重新生成简报",
      advisoryHint: "这份简报始终停留在建议层。它解释当前计划，但不会假装拥有 compare、proof 或 incident 的 post-run 真相。",
      optimizingFor: "这份计划在优化什么",
      mainRiskGate: "主风险门",
      capabilityTriggers: "能力触发原因",
      approvalPosture: "审批态势",
      bestNextAction: "最佳下一步",
      noRecommendedActions: "当前没有返回推荐动作。",
      topPreRunRisks: "顶部预跑前风险",
      noTopRisks: "当前没有返回显式风险。",
    };
  }
  return {
    defaultTitle: "Flight Plan copilot",
    defaultIntro: "Generate one bounded pre-run brief grounded only in the current Flight Plan preview, not in post-run truth.",
    defaultButtonLabel: "Explain this Flight Plan",
    questionSet: [
      "What is the most important risk gate before execution starts?",
      "Why are these capabilities triggered?",
      "What should the operator confirm before starting?",
      "Where is this plan most likely to fail?",
    ],
    unavailable: "Unavailable",
    advisoryBrief: "Advisory brief",
    onDemand: "On demand",
    generating: "Generating...",
    regenerate: "Regenerate brief",
    advisoryHint: "This brief stays advisory. It explains the current plan, but it does not claim any post-run compare, proof, or incident truth.",
    optimizingFor: "What this plan is optimizing for",
    mainRiskGate: "Main risk gate",
    capabilityTriggers: "Capability triggers",
    approvalPosture: "Approval posture",
    bestNextAction: "Best next action",
    noRecommendedActions: "No recommended actions were returned.",
    topPreRunRisks: "Top pre-run risks",
    noTopRisks: "No explicit risks were returned.",
  };
}

function asList(values: string[] | undefined): string[] {
  return Array.isArray(values) ? values.filter((value) => typeof value === "string" && value.trim()) : [];
}

export function DesktopFlightPlanCopilotPanel({
  locale = detectPreferredUiLocale() as UiLocale,
  title,
  intro,
  buttonLabel,
  loadBrief,
}: Props) {
  const [brief, setBrief] = useState<FlightPlanCopilotBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const copy = panelCopy(locale);
  const resolvedTitle = title ?? copy.defaultTitle;
  const resolvedIntro = intro ?? copy.defaultIntro;
  const resolvedButtonLabel = buttonLabel ?? copy.defaultButtonLabel;

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
          <p className="muted">{resolvedIntro}</p>
          <div className="row-between">
            <Badge>{brief ? (brief.status === "UNAVAILABLE" ? copy.unavailable : copy.advisoryBrief) : copy.onDemand}</Badge>
            <Button variant="secondary" onClick={() => void handleGenerate()} disabled={loading}>
              {loading ? copy.generating : brief ? copy.regenerate : resolvedButtonLabel}
            </Button>
          </div>
          {!brief && !error ? (
            <div className="stack-gap-2">
              <p className="muted">{copy.advisoryHint}</p>
              <div className="chip-list">
                {copy.questionSet.map((question) => (
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
                <CardHeader><CardTitle>{copy.optimizingFor}</CardTitle></CardHeader>
                <CardBody><p>{brief.summary}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.mainRiskGate}</CardTitle></CardHeader>
                <CardBody><p>{brief.risk_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.capabilityTriggers}</CardTitle></CardHeader>
                <CardBody><p>{brief.capability_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.approvalPosture}</CardTitle></CardHeader>
                <CardBody><p>{brief.approval_takeaway}</p></CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.bestNextAction}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.recommended_actions).length > 0 ? (
                      asList(brief.recommended_actions).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    ) : (
                      <li>{copy.noRecommendedActions}</li>
                    )}
                  </ul>
                </CardBody>
              </Card>
              <Card>
                <CardHeader><CardTitle>{copy.topPreRunRisks}</CardTitle></CardHeader>
                <CardBody>
                  <ul className="stack-gap-2">
                    {asList(brief.top_risks).length > 0 ? (
                      asList(brief.top_risks).map((item, index) => <li key={`${item}-${index}`}>{item}</li>)
                    ) : (
                      <li>{copy.noTopRisks}</li>
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
