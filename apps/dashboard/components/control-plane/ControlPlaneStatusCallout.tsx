import Link from "next/link";
import { Badge, type BadgeVariant } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";

type Tone = "success" | "warning" | "failed" | "running" | "default";

type ActionLink = {
  href: string;
  label: string;
};

type Props = {
  title: string;
  summary: string;
  nextAction: string;
  nextStepLabel?: string;
  tone?: Tone;
  badgeLabel?: string;
  actions?: ActionLink[];
};

function toneToBadge(tone: Tone): BadgeVariant {
  switch (tone) {
    case "success":
      return "success";
    case "warning":
      return "warning";
    case "failed":
      return "failed";
    case "running":
      return "running";
    default:
      return "default";
  }
}

function toneToAlertClass(tone: Tone): string {
  if (tone === "failed") return "alert alert-danger";
  if (tone === "warning") return "alert alert-warning";
  return "alert";
}

export default function ControlPlaneStatusCallout({
  title,
  summary,
  nextAction,
  nextStepLabel = "Next step",
  tone = "default",
  badgeLabel = "",
  actions = [],
}: Props) {
  return (
    <Card variant="unstyled" className={toneToAlertClass(tone)} role={tone === "failed" ? "alert" : "status"}>
      <div className="stack-gap-2">
        <div className="section-header">
          <div>
            <strong>{title}</strong>
            <p className="muted">{summary}</p>
          </div>
          {badgeLabel ? <Badge variant={toneToBadge(tone)}>{badgeLabel}</Badge> : null}
        </div>
        <p className="mono">{nextStepLabel}: {nextAction}</p>
        {actions.length > 0 ? (
          <div className="toolbar">
            {actions.map((action) => (
              <Button key={`${action.href}-${action.label}`} asChild variant="secondary">
                <Link href={action.href}>{action.label}</Link>
              </Button>
            ))}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
