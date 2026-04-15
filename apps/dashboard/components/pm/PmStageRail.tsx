import type { PmJourneyStage } from "../../lib/frontendApiContract";
import { useDashboardLocale } from "../DashboardLocaleContext";

function stageOrder(locale: "en" | "zh-CN"): Array<{ key: PmJourneyStage; title: string; hint: string }> {
  if (locale === "zh-CN") {
    return [
      { key: "discover", title: "发现", hint: "定义目标" },
      { key: "clarify", title: "澄清", hint: "澄清约束" },
      { key: "execute", title: "执行", hint: "推进执行" },
      { key: "verify", title: "验真", hint: "复核结果" },
    ];
  }
  return [
    { key: "discover", title: "Discover", hint: "Define the goal" },
    { key: "clarify", title: "Clarify", hint: "Clarify constraints" },
    { key: "execute", title: "Execute", hint: "Drive execution" },
    { key: "verify", title: "Verify", hint: "Review results" },
  ];
}

export default function PmStageRail({ stage }: { stage: PmJourneyStage }) {
  const { locale } = useDashboardLocale();
  const stages = stageOrder(locale);
  const activeIndex = stages.findIndex((item) => item.key === stage);

  return (
    <section className="pm-stage-rail" aria-label={locale === "zh-CN" ? "PM 旅程导航" : "PM journey navigation"}>
      {stages.map((item, index) => {
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
