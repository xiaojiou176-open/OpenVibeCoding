"use client";

import Link from "next/link";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import { resolveDashboardPublicDocsHref } from "../lib/env";
import { Button, type ButtonVariant } from "./ui/button";
import { Card } from "./ui/card";
import { useDashboardLocale } from "./DashboardLocaleContext";

type DashboardHomeStorySectionsProps = {
  failedCount: number;
  failureRate: number;
  hasRunHistory: boolean;
  latestFailureGovernanceHref: string;
  locale: UiLocale;
  runningCount: number;
  showFirstTaskGuide: boolean;
};

export default function DashboardHomeStorySections({
  failedCount,
  failureRate,
  hasRunHistory,
  latestFailureGovernanceHref,
  locale,
  runningCount,
  showFirstTaskGuide,
}: DashboardHomeStorySectionsProps) {
  const { locale: dashboardLocale, uiCopy } = useDashboardLocale();
  const resolvedUiCopy =
    dashboardLocale === DEFAULT_UI_LOCALE && locale !== DEFAULT_UI_LOCALE ? getUiCopy(locale) : uiCopy;
  const homePhase2Copy = resolvedUiCopy.dashboard.homePhase2;
  const resolveHomeHref = (href: string) => resolveDashboardPublicDocsHref(href);
  const shellCopy =
    locale === "zh-CN"
      ? {
          eyebrow: "OpenVibeCoding / 指挥塔入口",
          heroTitle: homePhase2Copy.heroTitle,
          heroSubtitle: homePhase2Copy.heroSubtitle,
          primaryAction: hasRunHistory ? "打开 Command Tower" : homePhase2Copy.startFirstTaskLabel,
          secondaryAction: hasRunHistory ? homePhase2Copy.startNewTaskLabel : homePhase2Copy.viewLatestRunsLabel,
          deskTitle: "第一屏控制台",
          deskDescription:
            "把最重要的操作面放到第一排，不再让首页像等权链接目录。",
          loopTitle: "Operator loop",
          loopDescription:
            "先 plan，再 delegate，然后 track、resume、prove。首页应该像飞行前简报，不是站内导航页。",
          methodTitle: "方法层，不抢第一屏",
          methodDescription:
            "Prompt / Context / Harness 仍然重要，但它们应该在 command tower 语义之后出现。",
          templatesTitle: "任务包与起步模版",
          templatesDescription:
            "这些是起步工具，不是首页主角。先看 cockpit，再决定拿哪套模版。",
          adoptionTitle: "延伸入口",
          adoptionDescription:
            "公共文档与生态入口保留在后排，避免抢走 command tower 的第一印象。",
        }
      : {
          eyebrow: "OpenVibeCoding / command tower entry",
          heroTitle: homePhase2Copy.heroTitle,
          heroSubtitle: homePhase2Copy.heroSubtitle,
          primaryAction: hasRunHistory ? "Open command tower" : homePhase2Copy.startFirstTaskLabel,
          secondaryAction: hasRunHistory ? homePhase2Copy.startNewTaskLabel : homePhase2Copy.viewLatestRunsLabel,
          deskTitle: "First-screen control desk",
          deskDescription:
            "Put the highest-leverage surfaces in the front row so the page reads like a cockpit, not a catalog of equal-weight links.",
          loopTitle: "Operator loop",
          loopDescription:
            "Plan, delegate, track, resume, and prove. The home page should behave like a pre-flight briefing, not a router-heavy portal.",
          methodTitle: "Method layer, not the hero",
          methodDescription:
            "Prompt / Context / Harness still matters, but it belongs below the control loop instead of competing with it.",
          templatesTitle: "Task packs and launch templates",
          templatesDescription:
            "Templates stay available, but they should not outrank the command tower on the first screen.",
          adoptionTitle: "Extended surfaces",
          adoptionDescription:
            "Public docs and ecosystem entry points stay in the second layer so the command tower remains the first impression.",
        };
  const adoptionCards = [
    homePhase2Copy.integrationCards[0],
    homePhase2Copy.builderCards[0],
    homePhase2Copy.integrationCards[1],
    homePhase2Copy.integrationCards[2],
    homePhase2Copy.builderCards[1],
  ];
  const controlDeskCards = [
    {
      href: "/command-tower",
      badge: locale === "zh-CN" ? "Where am I" : "Where am I",
      title: locale === "zh-CN" ? "实时 Command Tower" : "Live command tower",
      desc: hasRunHistory
        ? locale === "zh-CN"
          ? `当前有 ${runningCount} 条 live run 正在推进，先从 tower 看全局。`
          : `${runningCount} live runs are moving right now. Start in the tower before drilling into lists.`
        : locale === "zh-CN"
          ? "第一条 run 出现后，tower 会成为你的主驾驶舱。"
          : "The tower becomes the main cockpit as soon as the first delegated run exists.",
    },
    {
      href: failedCount > 0 ? latestFailureGovernanceHref : "/workflows",
      badge: locale === "zh-CN" ? "What is blocked" : "What is blocked",
      title:
        failedCount > 0
          ? locale === "zh-CN"
            ? "风险与堵点"
            : "Risk and blockers"
          : locale === "zh-CN"
            ? "Workflow posture"
            : "Workflow posture",
      desc:
        failedCount > 0
          ? locale === "zh-CN"
            ? `目前有 ${failedCount} 条失败或高风险 run，先处理堵点，再决定是否继续放行。`
            : `${failedCount} failed or high-risk runs need triage before you promote anything else.`
          : locale === "zh-CN"
            ? "当前没有明显失败面，直接从 Workflow Cases 看 owner、queue 和 next step。"
            : "No obvious failure lane is dominating. Open Workflow Cases to inspect owner, queue, and next action.",
    },
    {
      href: "/pm",
      badge: locale === "zh-CN" ? "What next" : "What next",
      title:
        hasRunHistory
          ? locale === "zh-CN"
            ? "继续派发下一项任务"
            : "Queue the next task"
          : locale === "zh-CN"
            ? "开始第一项任务"
            : "Start the first task",
      desc:
        hasRunHistory
          ? locale === "zh-CN"
            ? "确认 tower 状态后，回到 PM 入口继续派发新任务。"
            : "After you scan the tower, return to PM intake to dispatch the next piece of work."
          : locale === "zh-CN"
            ? "先把第一条任务送进系统，再回来用 tower 观察它。"
            : "Start from PM intake, then come back here to watch the first task move through the tower.",
    },
  ];
  const operatorLoopCards = [
    {
      href: "/pm",
      badge: "1",
      title: "Plan",
      desc:
        locale === "zh-CN"
          ? "从 PM 入口写清目标、约束和验收口径。"
          : "Define the objective, constraints, and acceptance bar from PM intake.",
    },
    {
      href: "/pm",
      badge: "2",
      title: "Delegate",
      desc:
        locale === "zh-CN"
          ? "把计划变成真实队列任务，不要停在说明文档里。"
          : "Turn the plan into queued work instead of leaving it as a note.",
    },
    {
      href: "/command-tower",
      badge: "3",
      title: "Track",
      desc:
        locale === "zh-CN"
          ? "用 live tower 先看现在到底在发生什么。"
          : "Use the live tower to see what is happening right now.",
    },
    {
      href: "/workflows",
      badge: "4",
      title: "Resume",
      desc:
        locale === "zh-CN"
          ? "回到 Workflow Case，沿 durable state 继续推进。"
          : "Use Workflow Cases as the durable operating record.",
    },
    {
      href: "/runs",
      badge: "5",
      title: "Prove",
      desc:
        locale === "zh-CN"
          ? "用 run 结果、失败线索和 replay 证据收口。"
          : "Use run results, failure clues, and replayable evidence to close the loop.",
    },
  ];

  const primaryActionHref = hasRunHistory ? "/command-tower" : "/pm";
  const topSecondaryAction = failedCount > 0
    ? {
        href: failureRate >= 0.5 ? "/events" : latestFailureGovernanceHref,
        label:
          failureRate >= 0.5
            ? homePhase2Copy.investigateHighRiskFailuresLabel
            : homePhase2Copy.handleLatestFailureLabel,
        variant: (failureRate >= 0.5 ? "warning" : "secondary") as ButtonVariant,
      }
    : hasRunHistory
      ? {
          href: "/pm",
          label: shellCopy.secondaryAction,
          variant: "secondary" as ButtonVariant,
        }
      : null;

  return (
    <>
      <header className="app-section">
        <div className="section-header">
          <div>
            <p className="cell-sub mono muted">{shellCopy.eyebrow}</p>
            <h1 id="dashboard-home-title" className="page-title">
              {shellCopy.heroTitle}
            </h1>
            <p className="page-subtitle">{shellCopy.heroSubtitle}</p>
            <p className="cell-sub mono muted">
              {locale === "zh-CN"
                ? "首页第一屏先回答四件事：你现在在哪、系统正在发生什么、哪里堵住了、下一步该进哪条操作路径。"
                : "The first screen should answer four questions immediately: where you are, what is happening now, what is blocked, and which surface to open next."}
            </p>
          </div>
          <nav aria-label="Home primary actions">
            <Button asChild variant="default">
              <Link href={primaryActionHref} prefetch>{shellCopy.primaryAction}</Link>
            </Button>
            {topSecondaryAction ? (
              <Button asChild variant={topSecondaryAction.variant}>
                <Link href={topSecondaryAction.href}>{topSecondaryAction.label}</Link>
              </Button>
            ) : null}
          </nav>
        </div>
      </header>

      <section className="app-section" aria-labelledby="dashboard-control-desk-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-control-desk-title" className="section-title">
              {shellCopy.deskTitle}
            </h2>
            <p>{shellCopy.deskDescription}</p>
          </div>
        </div>
        <div className="quick-grid">
          {controlDeskCards.map((item) => (
            <Link key={item.title} href={item.href} className="quick-card">
              <span className="quick-card-desc">{item.badge}</span>
              <span className="quick-card-title">{item.title}</span>
              <span className="quick-card-desc">{item.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-section" aria-labelledby="dashboard-operator-loop-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-operator-loop-title" className="section-title">
              {shellCopy.loopTitle}
            </h2>
            <p>{shellCopy.loopDescription}</p>
          </div>
        </div>
        <div className="quick-grid">
          {operatorLoopCards.map((item) => (
            <Link key={item.title} href={item.href} className="quick-card">
              <span className="quick-card-desc">{item.badge}</span>
              <span className="quick-card-title">{item.title}</span>
              <span className="quick-card-desc">{item.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-section" aria-labelledby="dashboard-public-advantages-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-public-advantages-title" className="section-title">
              {shellCopy.methodTitle}
            </h2>
            <p>{shellCopy.methodDescription}</p>
          </div>
        </div>
        <div className="quick-grid">
          {homePhase2Copy.publicAdvantageCards.map((item) => (
            <Link key={item.title} href={resolveHomeHref(item.href)} className="quick-card">
              <span className="quick-card-title">{item.title}</span>
              <span className="quick-card-desc">{item.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-section" aria-labelledby="dashboard-public-templates-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-public-templates-title" className="section-title">
              {shellCopy.templatesTitle}
            </h2>
            <p>{shellCopy.templatesDescription}</p>
          </div>
          <nav aria-label="Public task template actions">
            <Button asChild variant="secondary">
              <Link href={resolveHomeHref(homePhase2Copy.publicTemplatesActionHref)}>
                {homePhase2Copy.publicTemplatesActionLabel}
              </Link>
            </Button>
          </nav>
        </div>
        <div className="quick-grid">
          {homePhase2Copy.publicTemplateCards.map((item) => (
            <Link key={item.title} href={resolveHomeHref(item.href)} className="quick-card">
              <span className="quick-card-desc">{item.badge}</span>
              <span className="quick-card-title">{item.title}</span>
              <span className="quick-card-desc">{item.desc}</span>
              <span className="cell-sub mono">Best for: {item.bestFor}</span>
              <span className="cell-sub mono">Try with: {item.example}</span>
              <span className="cell-sub mono">{item.proof}</span>
              <span className="cell-sub mono">{item.fields.join(" · ")}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-section" aria-labelledby="dashboard-integration-adoption-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-integration-adoption-title" className="section-title">
              {shellCopy.adoptionTitle}
            </h2>
            <p>{shellCopy.adoptionDescription}</p>
          </div>
          <nav aria-label="Adoption and proof-first actions">
            <Button asChild variant="secondary">
              <Link href={resolveHomeHref(homePhase2Copy.proofFirstActionHref)}>{homePhase2Copy.proofFirstActionLabel}</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href={resolveHomeHref(homePhase2Copy.aiSurfacesActionHref)}>{homePhase2Copy.aiSurfacesActionLabel}</Link>
            </Button>
          </nav>
        </div>
        <div className="quick-grid">
          {adoptionCards.map((item) => {
            const href = resolveHomeHref(item.href);
            return (
              <Link key={item.title} href={href} className="quick-card" prefetch={item.prefetch ?? href.startsWith("/")}>
                <span className="quick-card-desc">{item.badge}</span>
                <span className="quick-card-title">{item.title}</span>
                <span className="quick-card-desc">{item.desc}</span>
              </Link>
            );
          })}
        </div>
        <p>
          Need the broader ecosystem framing? <Link href={resolveHomeHref(homePhase2Copy.ecosystemActionHref)}>{homePhase2Copy.ecosystemAction}</Link>.
          Need the full package ladder in one place?{" "}
          <Link href={resolveHomeHref(homePhase2Copy.builderQuickstartCtaHref)}>
            {homePhase2Copy.builderQuickstartCtaLabel}
          </Link>.
        </p>
      </section>

      {showFirstTaskGuide ? (
        <section className="app-section" aria-label="Start your first task in four steps">
          <div className="section-header">
            <div>
              <h2 className="section-title">{homePhase2Copy.firstTaskGuideTitle}</h2>
              <p>{homePhase2Copy.firstTaskGuideDescription}</p>
            </div>
          </div>
          <Card asChild>
            <details data-testid="home-onboarding-details">
              <summary className="quick-card-title">{homePhase2Copy.firstTaskGuideSummary}</summary>
              <div className="quick-grid mt-2">
                {homePhase2Copy.firstTaskGuideSteps.map((step) => (
                  <Link key={step.href} href={resolveHomeHref(step.href)} prefetch={step.prefetch} className="quick-card">
                    <span className="quick-card-desc">{step.step}</span>
                    <span className="quick-card-title">{step.title}</span>
                    <span className="quick-card-desc">{step.desc}</span>
                  </Link>
                ))}
              </div>
              <div className="quick-grid mt-2" aria-label="Optional approval step">
                <Link
                  href={resolveHomeHref(homePhase2Copy.optionalApprovalStep.href)}
                  prefetch={homePhase2Copy.optionalApprovalStep.prefetch}
                  className="quick-card"
                >
                  <span className="quick-card-desc">{homePhase2Copy.optionalApprovalStep.step}</span>
                  <span className="quick-card-title">{homePhase2Copy.optionalApprovalStep.title}</span>
                  <span className="quick-card-desc">{homePhase2Copy.optionalApprovalStep.desc}</span>
                </Link>
              </div>
            </details>
          </Card>
        </section>
      ) : null}
    </>
  );
}
