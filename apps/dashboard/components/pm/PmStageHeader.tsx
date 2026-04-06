import type { PmJourneyContext } from "../../lib/frontendApiContract";
import { stageLabel } from "../../lib/pmStageResolver";

export default function PmStageHeader({ context }: { context: PmJourneyContext }) {
  return (
    <section className={`pm-stage-header is-${context.stage}`} aria-label="Current stage summary">
      <div className="pm-stage-header-main">
        <span className="pm-stage-header-kicker">Journey Stage</span>
        <h2>{stageLabel(context.stage)}</h2>
        <p>{context.reason}</p>
      </div>
      <div className="pm-stage-header-cta" role="status" aria-live="polite">
        <strong>Next</strong>
        <span>{context.primaryAction}</span>
      </div>
    </section>
  );
}
