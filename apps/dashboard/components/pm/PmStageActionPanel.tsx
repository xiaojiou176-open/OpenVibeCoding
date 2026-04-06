import type { PmJourneyContext } from "../../lib/frontendApiContract";
import { Button } from "../ui/button";

type PmStageActionPanelProps = {
  context: PmJourneyContext;
  disabled?: boolean;
  onPrimaryAction: () => void;
  onFillTemplate?: () => void;
};

export default function PmStageActionPanel({
  context,
  disabled,
  onPrimaryAction,
  onFillTemplate,
}: PmStageActionPanelProps) {
  return (
    <section className="pm-stage-action-panel" aria-label="Stage action panel">
      <Button
        variant="default"
        onClick={onPrimaryAction}
        disabled={disabled}
        data-testid="pm-stage-primary-action"
      >
        {context.primaryAction}
      </Button>
      {context.stage === "discover" && onFillTemplate ? (
        <Button
          variant="ghost"
          onClick={onFillTemplate}
          disabled={disabled}
          data-testid="pm-stage-fill-template"
        >
          Fill example
        </Button>
      ) : null}
      {context.secondaryActions.length > 0 ? (
        <div className="pm-stage-action-secondary" role="list" aria-label="Stage secondary actions">
          {context.secondaryActions.map((item) => (
            <span key={item} className="pm-stage-action-chip" role="listitem">
              {item}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
