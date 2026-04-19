"use client";

import Link from "next/link";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@openvibecoding/frontend-shared/uiCopy";
import { resolveDashboardPublicDocsHref } from "../lib/env";
import { Badge } from "./ui/badge";
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
          eyebrow: "值班入口",
          heroTitle: "AI 工程开放指挥塔",
          heroSubtitle:
            "别再盯着模型跑到哪一步。OpenVibeCoding 把规划、派工、追踪、续跑和验真收进一条真正能值班的操作链。",
          primaryAction: hasRunHistory ? "打开指挥塔" : homePhase2Copy.startFirstTaskLabel,
          secondaryAction: hasRunHistory ? homePhase2Copy.startNewTaskLabel : homePhase2Copy.viewLatestRunsLabel,
          deskTitle: "第一排操作台",
          deskDescription:
            "把最重要的操作面放到第一排，不再让首页像等权链接目录。",
          methodTitle: "方法层，不抢第一屏",
          methodDescription:
            "提示词 / 上下文 / 护栏这三层仍然重要，但它们应该排在指挥塔语义之后出现。",
          templatesTitle: "任务包与起步模版",
          templatesDescription:
            "这些是起步工具，不是首页主角。先看指挥台，再决定拿哪套模版。",
          adoptionTitle: "延伸入口",
          adoptionDescription:
            "公共文档与生态入口保留在后排，避免抢走指挥塔的第一印象。",
          guidesTitle: "第二层导览，不抢首屏",
          guidesDescription:
            "方法层、模板层和生态入口保留，但收进更安静的第二层，避免首页继续像站点目录墙。",
          guidesSummary: "展开第二层导览",
          guidesMeta: ["方法层", "模板", "生态"],
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
          methodTitle: "Method layer, not the hero",
          methodDescription:
            "Prompt / Context / Harness still matters, but it belongs below the control loop instead of competing with it.",
          templatesTitle: "Task packs and launch templates",
          templatesDescription:
            "Templates stay available, but they should not outrank the command tower on the first screen.",
          adoptionTitle: "Extended surfaces",
          adoptionDescription:
            "Public docs and ecosystem entry points stay in the second layer so the command tower remains the first impression.",
          guidesTitle: "Second-layer guides, not the first impression",
          guidesDescription:
            "Keep methods, templates, and ecosystem routes available, but move them into a calmer second layer so the home page stops reading like a route catalog.",
          guidesSummary: "Open second-layer guides",
          guidesMeta: ["Methods", "Templates", "Ecosystem"],
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
      badge: locale === "zh-CN" ? "当前主面" : "Where am I",
      title: locale === "zh-CN" ? "实时指挥塔" : "Live command tower",
      desc: hasRunHistory
        ? locale === "zh-CN"
          ? `当前有 ${runningCount} 条运行正在推进，先从指挥塔看全局，再决定要不要下钻明细。`
          : `${runningCount} live runs are moving right now. Start in the tower before drilling into lists.`
        : locale === "zh-CN"
          ? "第一条运行出现后，指挥塔会变成你的主驾驶舱。"
          : "The tower becomes the main cockpit as soon as the first delegated run exists.",
      meta:
        locale === "zh-CN"
          ? "先看全局，再看细节"
          : "Read the board before drilling down",
      cta: locale === "zh-CN" ? "打开指挥塔" : "Open tower",
      tone: "primary",
    },
    {
      href: failedCount > 0 ? latestFailureGovernanceHref : "/workflows",
      badge: locale === "zh-CN" ? "当前堵点" : "What is blocked",
      title:
        failedCount > 0
          ? locale === "zh-CN"
            ? "风险与堵点"
            : "Risk and blockers"
          : locale === "zh-CN"
            ? "工作流姿态"
            : "Workflow posture",
      desc:
        failedCount > 0
          ? locale === "zh-CN"
            ? `目前有 ${failedCount} 条失败或高风险运行，先处理堵点，再决定是否继续放行。`
            : `${failedCount} failed or high-risk runs need triage before you promote anything else.`
          : locale === "zh-CN"
            ? "当前没有明显失败面，直接从工作流案例看负责人、队列和下一步。"
            : "No obvious failure lane is dominating. Open Workflow Cases to inspect owner, queue, and next action.",
      meta:
        locale === "zh-CN"
          ? failedCount > 0
            ? "失败线优先"
            : "回到工作流案例"
          : failedCount > 0
            ? "Triage blockers first"
            : "Open workflow record",
      cta: locale === "zh-CN" ? "查看风险面" : "Inspect blockers",
      tone: "risk",
    },
    {
      href: "/pm",
      badge: locale === "zh-CN" ? "下一动作" : "What next",
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
          ? "确认指挥塔状态后，回到 PM 入口继续派发新任务。"
          : "After you scan the tower, return to PM intake to dispatch the next piece of work."
        : locale === "zh-CN"
            ? "先把第一条任务送进系统，再回来用指挥塔观察它。"
            : "Start from PM intake, then come back here to watch the first task move through the tower.",
      meta:
        locale === "zh-CN"
          ? "回到 PM 入口"
          : "Return to PM intake",
      cta: locale === "zh-CN" ? "继续派发" : "Dispatch next",
      tone: "action",
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
      : {
          href: resolveHomeHref(homePhase2Copy.proofFirstActionHref),
          label: homePhase2Copy.proofFirstActionLabel,
          variant: "secondary" as ButtonVariant,
        };
  const heroMeters =
    locale === "zh-CN"
      ? [
          {
            kicker: "当前实况",
            value: hasRunHistory ? String(runningCount) : "0",
            detail: hasRunHistory ? "先读指挥塔，再下钻明细" : "先起第一条任务，系统才会亮起来",
          },
          {
            kicker: "当前堵点",
            value: String(failedCount),
            detail: failedCount > 0 ? "先处理风险线，再继续派发" : "当前没有主导性失败线",
          },
          {
            kicker: "真相路径",
            value: hasRunHistory ? "工作流 + 证明" : "先从 PM 开始",
            detail: hasRunHistory ? "首页只负责导向，不负责替代证明室" : "先写请求，再让真相面出现",
          },
        ]
      : [
          {
            kicker: "Live now",
            value: hasRunHistory ? String(runningCount) : "0",
            detail: hasRunHistory ? "Read the tower first, then drill down." : "Start the first task before you trust the shell.",
          },
          {
            kicker: "Blocked now",
            value: String(failedCount),
            detail: failedCount > 0 ? "Handle the risky lane before you dispatch more work." : "No dominant failure lane is blocking the board.",
          },
          {
            kicker: "Truth path",
            value: hasRunHistory ? "Workflow + Proof" : "Start in PM",
            detail: hasRunHistory ? "The homepage routes you; it does not replace proof." : "Write the request first, then let the truth rooms light up.",
          },
        ];
  return (
    <>
      <header className="app-section">
        <div className="home-briefing-shell">
          <div className="home-briefing-copy">
            <p className="cell-sub mono muted">{shellCopy.eyebrow}</p>
              <h1 id="dashboard-home-title" className="page-title">
              {locale === "zh-CN" ? (
                <span className="page-title-stacked">
                  <span>AI 工程开放</span>
                  <span>指挥塔</span>
                </span>
              ) : (
                shellCopy.heroTitle
              )}
            </h1>
            <p className="page-subtitle">{shellCopy.heroSubtitle}</p>
            <p className="cell-sub mono muted home-briefing-guidance">
              {locale === "zh-CN"
                ? "首页第一屏先回答四件事：你现在在哪、系统正在发生什么、哪里堵住了、下一步该进哪条操作路径。"
                : "The first screen should answer four questions immediately: where you are, what is happening now, what is blocked, and which surface to open next."}
            </p>
            <nav aria-label="Home primary actions" className="home-briefing-actions">
              <Button asChild variant="default">
                <Link href={primaryActionHref} prefetch>{shellCopy.primaryAction}</Link>
              </Button>
              {topSecondaryAction ? (
                <Button asChild variant={topSecondaryAction.variant}>
                  <Link href={topSecondaryAction.href}>{topSecondaryAction.label}</Link>
                </Button>
              ) : null}
            </nav>
            <div
              className="home-briefing-meter-row"
              aria-label={locale === "zh-CN" ? "首页首屏仪表带" : "Homepage first-screen meter strip"}
            >
              {heroMeters.map((item) => (
                <div key={item.kicker} className="home-briefing-meter">
                  <span className="home-briefing-meter-kicker">{item.kicker}</span>
                  <strong className="home-briefing-meter-value">{item.value}</strong>
                  <p className="home-briefing-meter-detail">{item.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </header>

      <section className="app-section" aria-labelledby="dashboard-control-desk-title">
        <h2 id="dashboard-control-desk-title" className="sr-only">
          {shellCopy.deskTitle}
        </h2>
        <div className="home-command-grid">
          {controlDeskCards.map((item, index) => (
            <Link
              key={item.title}
              href={item.href}
              className={`home-command-card ${index === 0 ? "home-command-card--primary" : "home-command-card--supporting"} home-command-card--${item.tone}`}
            >
              <div className="home-command-card-head">
                <span className="home-command-kicker">{item.badge}</span>
              </div>
              <div className="home-command-card-body">
                <span className="home-command-title">{item.title}</span>
                <span className="home-command-desc">{item.desc}</span>
              </div>
            </Link>
          ))}
        </div>
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

      <section className="app-section" aria-labelledby="dashboard-second-layer-guides-title">
        <div className="section-header">
          <div>
            <h2 id="dashboard-second-layer-guides-title" className="section-title">
              {shellCopy.guidesTitle}
            </h2>
            <p>{shellCopy.guidesDescription}</p>
          </div>
        </div>
        <Card asChild>
          <details data-testid="home-second-layer-guides" className="home-guides-details">
            <summary className="home-guides-summary">
              <span className="home-guides-summary-title">{shellCopy.guidesSummary}</span>
              <span className="home-guides-summary-meta">
                {shellCopy.guidesMeta.map((label) => (
                  <span key={label} className="home-guides-summary-chip">
                    {label}
                  </span>
                ))}
              </span>
            </summary>
            <div className="home-guides-body mt-3">
              <section className="home-guides-section">
                <div className="home-guides-copy">
                  <h3 className="section-title">{shellCopy.methodTitle}</h3>
                  <p>{shellCopy.methodDescription}</p>
                </div>
                <div className="home-guides-list">
                  {homePhase2Copy.publicAdvantageCards.map((item) => (
                    <Link key={item.title} href={resolveHomeHref(item.href)} className="home-guides-link">
                      <span className="home-guides-link-title">{item.title}</span>
                      <span className="home-guides-link-desc">{item.desc}</span>
                    </Link>
                  ))}
                </div>
              </section>

              <section className="home-guides-section">
                <div className="home-guides-copy">
                  <h3 className="section-title">{shellCopy.templatesTitle}</h3>
                  <p>{shellCopy.templatesDescription}</p>
                  <nav aria-label="Public task template actions">
                    <Button asChild variant="secondary">
                      <Link href={resolveHomeHref(homePhase2Copy.publicTemplatesActionHref)}>
                        {homePhase2Copy.publicTemplatesActionLabel}
                      </Link>
                    </Button>
                  </nav>
                </div>
                <div className="home-guides-list">
                  {homePhase2Copy.publicTemplateCards.map((item) => (
                    <Link key={item.title} href={resolveHomeHref(item.href)} className="home-guides-link">
                      <span className="home-guides-link-kicker">{item.badge}</span>
                      <span className="home-guides-link-title">{item.title}</span>
                      <span className="home-guides-link-desc">{item.desc}</span>
                      <span className="home-guides-link-meta">{item.proof}</span>
                    </Link>
                  ))}
                </div>
              </section>

              <section className="home-guides-section">
                <div className="home-guides-copy">
                  <h3 className="section-title">{shellCopy.adoptionTitle}</h3>
                  <p>{shellCopy.adoptionDescription}</p>
                  <nav aria-label="Adoption and proof-first actions" className="home-guides-actions">
                    <Button asChild variant="secondary">
                      <Link href={resolveHomeHref(homePhase2Copy.proofFirstActionHref)}>{homePhase2Copy.proofFirstActionLabel}</Link>
                    </Button>
                    <Button asChild variant="secondary">
                      <Link href={resolveHomeHref(homePhase2Copy.aiSurfacesActionHref)}>{homePhase2Copy.aiSurfacesActionLabel}</Link>
                    </Button>
                  </nav>
                </div>
                <div className="home-guides-list">
                  {adoptionCards.map((item) => {
                    const href = resolveHomeHref(item.href);
                    return (
                      <Link
                        key={item.title}
                        href={href}
                        className="home-guides-link home-guides-link--secondary"
                        prefetch={item.prefetch ?? href.startsWith("/")}
                      >
                        <span className="home-guides-link-kicker">{item.badge}</span>
                        <span className="home-guides-link-title">{item.title}</span>
                        <span className="home-guides-link-desc">{item.desc}</span>
                      </Link>
                    );
                  })}
                </div>
                <div className="home-guides-footer">
                  <Link href={resolveHomeHref(homePhase2Copy.ecosystemActionHref)} className="home-guides-footer-link">
                    {homePhase2Copy.ecosystemAction}
                  </Link>
                  <Link href={resolveHomeHref(homePhase2Copy.builderQuickstartCtaHref)} className="home-guides-footer-link">
                    {homePhase2Copy.builderQuickstartCtaLabel}
                  </Link>
                </div>
              </section>
            </div>
          </details>
        </Card>
      </section>
    </>
  );
}
