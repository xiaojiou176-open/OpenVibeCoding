import type { Metadata } from "next";
import { cookies } from "next/headers";
import { getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import { normalizeUiLocale, UI_LOCALE_STORAGE_KEY } from "@openvibecoding/frontend-shared/uiLocale";
import Link from "next/link";
import { Suspense } from "react";
import { Badge } from "../../components/ui/badge";
import { Card } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import CommandTowerHomeLiveClient from "./CommandTowerHomeLiveClient";
import ControlPlaneStatusCallout from "../../components/control-plane/ControlPlaneStatusCallout";
import { fetchCommandTowerOverview, fetchPmSessions } from "../../lib/api";
import { safeLoad } from "../../lib/serverPageData";
import type { CommandTowerOverviewPayload, PmSessionSummary } from "../../lib/types";
import type { UiLocale } from "@openvibecoding/frontend-shared/uiCopy";

export const metadata: Metadata = {
  title: "Command Tower | OpenVibeCoding",
  description:
    "Monitor live operator visibility, linked Workflow Cases, blockers, and next operator actions from the OpenVibeCoding command tower cockpit.",
};

export async function CommandTowerHomeSection({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const fallbackOverview: CommandTowerOverviewPayload = {
    generated_at: new Date().toISOString(),
    total_sessions: 0,
    active_sessions: 0,
    failed_sessions: 0,
    blocked_sessions: 0,
    failed_ratio: 0,
    blocked_ratio: 0,
    failure_trend_30m: 0,
    top_blockers: [],
  };
  const fallbackSessions: PmSessionSummary[] = [];

  const settled = await Promise.allSettled([
    safeLoad(fetchCommandTowerOverview, fallbackOverview, "Command Tower overview"),
    safeLoad(() => fetchPmSessions({ limit: 40 }), fallbackSessions, "PM session list"),
  ]);

  const overviewResult =
    settled[0].status === "fulfilled"
      ? settled[0].value
      : {
          data: fallbackOverview,
          warning:
            locale === "zh-CN"
              ? "指挥塔总览暂时不可用，请稍后再试。"
              : "Command Tower overview is unavailable right now. Please try again later.",
        };
  const sessionsResult =
    settled[1].status === "fulfilled"
      ? settled[1].value
      : {
          data: fallbackSessions,
          warning:
            locale === "zh-CN"
              ? "PM 会话列表暂时不可用，请稍后再试。"
              : "The PM session list is unavailable right now. Please try again later.",
        };

  const overview = overviewResult.data;
  const sessions = sessionsResult.data;
  const overviewWarning = overviewResult.warning;
  const sessionsWarning = sessionsResult.warning;
  const warning = [overviewWarning, sessionsWarning].filter(Boolean).join(" ");
  const hasLiveData =
    (overview.total_sessions || 0) > 0 ||
    (overview.active_sessions || 0) > 0 ||
    (sessions?.length || 0) > 0;

  return (
    <>
      {warning && !hasLiveData ? null : (
        <section aria-label="Command Tower live overview" aria-describedby="command-tower-page-subtitle">
          <CommandTowerHomeLiveClient initialOverview={overview} initialSessions={sessions} locale={locale} />
        </section>
      )}
      {warning && !hasLiveData ? (
        <ControlPlaneStatusCallout
          title={commandTowerCopy.unavailableTitle}
          summary={warning}
          nextAction={commandTowerCopy.unavailableNextAction}
          tone="warning"
          badgeLabel={commandTowerCopy.unavailableBadge}
          actions={[
            { href: "/command-tower", label: commandTowerCopy.actions.reload },
            { href: "/runs", label: commandTowerCopy.actions.viewRuns },
            { href: "/pm", label: commandTowerCopy.actions.startFromPm },
          ]}
        />
      ) : null}
      {warning && hasLiveData ? (
        <ControlPlaneStatusCallout
          title={commandTowerCopy.partialTitle}
          summary={warning}
          nextAction={commandTowerCopy.partialNextAction}
          tone="warning"
          badgeLabel={commandTowerCopy.partialBadge}
          actions={[
            { href: "/runs", label: commandTowerCopy.actions.openRuns },
            { href: "/workflows", label: commandTowerCopy.actions.openWorkflowCases },
          ]}
        />
      ) : null}
    </>
  );
}

export function CommandTowerHomeSectionFallback({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  return (
    <section aria-label="Command Tower live overview" aria-describedby="command-tower-page-subtitle" aria-busy="true">
      <p className="mono" role="status">{commandTowerCopy.fallbackLoading}</p>
    </section>
  );
}

export function CommandTowerPageIntro({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const towerActions =
    locale === "zh-CN"
      ? [
          { href: "/events", label: "打开风险事件" },
          { href: "/workflows", label: "打开工作流案例" },
          { href: "/runs", label: "打开证明室" },
        ]
      : [
          { href: "/events", label: "Open risk events" },
          { href: "/workflows", label: "Open Workflow Cases" },
          { href: "/runs", label: "Open proof room" },
        ];
  return (
    <header className="app-section">
      <div className="home-briefing-shell">
        <div className="home-briefing-copy">
          <p className="cell-sub mono muted">
            {locale === "zh-CN" ? "L0 驾驶舱 / 实时控制桌" : "L0 cockpit / live control desk"}
          </p>
          <h1 id="command-tower-page-title" className="page-title">
            {commandTowerCopy.srTitle}
          </h1>
          <p id="command-tower-page-subtitle" className="page-subtitle">
            {commandTowerCopy.srSubtitle}
          </p>
          <p className="cell-sub mono muted">
            {locale === "zh-CN"
              ? "这一页应该先告诉你：现在发生什么、哪条线危险、下一步该去哪个真相入口。"
              : "This page should answer three questions first: what is happening now, which lane is risky, and which truth surface to open next."}
          </p>
          <nav className="home-briefing-actions" aria-label={locale === "zh-CN" ? "指挥塔首屏操作" : "Command Tower first-screen actions"}>
            {towerActions.map((action, index) => (
              <Button asChild key={action.href} variant={index === 0 ? "warning" : "secondary"}>
                <Link href={action.href}>{action.label}</Link>
              </Button>
            ))}
          </nav>
        </div>
        <Card className="home-briefing-panel">
          <div className="home-briefing-panel-head">
            <span className="cell-sub mono muted">
              {locale === "zh-CN" ? "值班判断" : "Operator judgment"}
            </span>
            <Badge variant="running">
              {locale === "zh-CN" ? "先看 live" : "Live first"}
            </Badge>
          </div>
          <div className="home-briefing-signal-list">
            <div className="home-briefing-signal">
              <span className="cell-sub mono muted">{locale === "zh-CN" ? "现在发生什么" : "What is happening now"}</span>
              <strong>{locale === "zh-CN" ? "先看 live session board" : "Scan the live session board first"}</strong>
              <p>{locale === "zh-CN" ? "不要先钻细节页。先确定 board 上最重要的 run 和 session。" : "Do not drill into detail pages first. Identify the most important session and run on the board."}</p>
            </div>
            <div className="home-briefing-signal">
              <span className="cell-sub mono muted">{locale === "zh-CN" ? "风险在哪" : "Where is the risk"}</span>
              <strong>{locale === "zh-CN" ? "先读 risk lane 和 degraded alert" : "Read the risk lane and degraded alert first"}</strong>
              <p>{locale === "zh-CN" ? "这页的主任务是分诊，不是浏览所有模块。" : "The main job here is triage, not browsing every module."}</p>
            </div>
            <div className="home-briefing-signal">
              <span className="cell-sub mono muted">{locale === "zh-CN" ? "下一步" : "What to do next"}</span>
              <strong>{locale === "zh-CN" ? "先用 tower 再跳去 Workflow 或 Proof" : "Use the tower before jumping to Workflow or Proof"}</strong>
              <p>{locale === "zh-CN" ? "让 tower 成为主驾驶舱，而不是另一个数据列表页。" : "Treat the tower as the cockpit, not another reporting page."}</p>
            </div>
          </div>
        </Card>
      </div>
    </header>
  );
}

export default async function CommandTowerPage() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  return (
    <main className="grid" aria-labelledby="command-tower-page-title" aria-describedby="command-tower-page-subtitle">
      <CommandTowerPageIntro locale={locale} />
      <Suspense fallback={<CommandTowerHomeSectionFallback locale={locale} />}>
        <CommandTowerHomeSection locale={locale} />
      </Suspense>
    </main>
  );
}
