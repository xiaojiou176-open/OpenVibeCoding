import type { PmJourneyContext } from "../../lib/frontendApiContract";

type PmStageContextPanelProps = {
  context: PmJourneyContext;
  runId: string;
  intakeId: string;
  liveRole: string;
  sessionStatus: string;
};

export default function PmStageContextPanel({
  context,
  runId,
  intakeId,
  liveRole,
  sessionStatus,
}: PmStageContextPanelProps) {
  return (
    <section className="pm-stage-context-panel" aria-label="Stage context">
      <h3>Context and strategy</h3>
      <ul className="pm-stage-context-list">
        <li>
          <span>stage</span>
          <code>{context.stage}</code>
        </li>
        <li>
          <span>session</span>
          <code>{intakeId || "-"}</code>
        </li>
        <li>
          <span>run</span>
          <code>{runId || "-"}</code>
        </li>
        <li>
          <span>active role</span>
          <code>{liveRole || "-"}</code>
        </li>
        <li>
          <span>status</span>
          <code>{sessionStatus || "-"}</code>
        </li>
      </ul>
    </section>
  );
}
