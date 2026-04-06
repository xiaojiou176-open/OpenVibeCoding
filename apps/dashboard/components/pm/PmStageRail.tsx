import type { PmJourneyStage } from "../../lib/frontendApiContract";

const STAGE_ORDER: Array<{ key: PmJourneyStage; title: string; hint: string }> = [
  { key: "discover", title: "Discover", hint: "Define the goal" },
  { key: "clarify", title: "Clarify", hint: "Clarify constraints" },
  { key: "execute", title: "Execute", hint: "Drive execution" },
  { key: "verify", title: "Verify", hint: "Review results" },
];

export default function PmStageRail({ stage }: { stage: PmJourneyStage }) {
  const activeIndex = STAGE_ORDER.findIndex((item) => item.key === stage);

  return (
    <section className="pm-stage-rail" aria-label="PM journey navigation">
      {STAGE_ORDER.map((item, index) => {
        const active = item.key === stage;
        const reached = activeIndex >= index;
        return (
          <div
            key={item.key}
            className={`pm-stage-rail-item${active ? " is-active" : ""}${reached ? " is-reached" : ""}`}
            aria-current={active ? "step" : undefined}
          >
            <span className="pm-stage-rail-dot" aria-hidden="true" />
            <div>
              <strong>{item.title}</strong>
              <p>{item.hint}</p>
            </div>
          </div>
        );
      })}
    </section>
  );
}
