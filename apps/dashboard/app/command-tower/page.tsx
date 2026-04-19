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

export function buildCommandTowerMetadata(locale: UiLocale): Metadata {
  if (locale === "zh-CN") {
    return {
      title: "指挥塔 | OpenVibeCoding",
      description:
        "从 OpenVibeCoding 指挥塔驾驶舱中监控实时可见性、关联工作流案例、阻塞点和下一步操作。",
    };
  }

  return {
    title: "Command Tower | OpenVibeCoding",
    description:
      "Monitor live operator visibility, linked Workflow Cases, blockers, and next operator actions from the OpenVibeCoding command tower cockpit.",
  };
}

type CommandTowerHomeState = {
  overview: CommandTowerOverviewPayload;
  sessions: PmSessionSummary[];
  warning: string;
  hasLiveData: boolean;
};

function getCommandTowerHomeSectionAriaLabel(locale: UiLocale): string {
  return locale === "zh-CN" ? "指挥塔实时总览" : "Command Tower live overview";
}

function buildCommandTowerWarningSummary({
  locale,
  overviewWarning,
  sessionsWarning,
  hasLiveData,
}: {
  locale: UiLocale;
  overviewWarning: string | null;
  sessionsWarning: string | null;
  hasLiveData: boolean;
}): string {
  if (!overviewWarning && !sessionsWarning) {
    return "";
  }

  if (locale === "zh-CN") {
    if (overviewWarning && sessionsWarning) {
      return "指挥塔总览与 PM 会话列表当前都不可用。请稍后再试。";
    }
    if (overviewWarning) {
      return hasLiveData
        ? "指挥塔总览暂时不可用。当前页面只显示部分快照，继续操作前请直接核对运行记录或工作流案例。"
        : "指挥塔总览暂时不可用。请稍后再试。";
    }
    return hasLiveData
      ? "PM 会话列表暂时不可用。当前页面只显示部分快照，继续操作前请直接核对运行记录或工作流案例。"
      : "PM 会话列表暂时不可用。请稍后再试。";
  }

  if (overviewWarning && sessionsWarning) {
    return "Command Tower overview and PM session list are temporarily unavailable. Try again later.";
  }
  if (overviewWarning) {
    return hasLiveData
      ? "Command Tower overview is temporarily unavailable. The page is showing a partial snapshot, so verify runs or Workflow Cases directly before you act."
      : "Command Tower overview is temporarily unavailable. Try again later.";
  }
  return hasLiveData
    ? "The PM session list is temporarily unavailable. The page is showing a partial snapshot, so verify runs or Workflow Cases directly before you act."
    : "The PM session list is temporarily unavailable. Try again later.";
}

async function loadCommandTowerHomeState(locale: UiLocale): Promise<CommandTowerHomeState> {
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
  const hasLiveData =
    (overview.total_sessions || 0) > 0 ||
    (overview.active_sessions || 0) > 0 ||
    (sessions?.length || 0) > 0;
  const warning = buildCommandTowerWarningSummary({
    locale,
    overviewWarning,
    sessionsWarning,
    hasLiveData,
  });

  return {
    overview,
    sessions,
    warning,
    hasLiveData,
  };
}

export async function CommandTowerHomeSection({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const { overview, sessions, warning, hasLiveData } = await loadCommandTowerHomeState(locale);
  const sectionAriaLabel = getCommandTowerHomeSectionAriaLabel(locale);

  return (
    <>
      {warning && !hasLiveData ? null : (
        <section aria-label={sectionAriaLabel} aria-describedby="command-tower-page-subtitle">
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
    </>
  );
}

export async function generateMetadata(): Promise<Metadata> {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  return buildCommandTowerMetadata(locale);
}

export function CommandTowerHomeSectionFallback({ locale }: { locale: UiLocale }) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const sectionAriaLabel = getCommandTowerHomeSectionAriaLabel(locale);
  return (
    <section aria-label={sectionAriaLabel} aria-describedby="command-tower-page-subtitle" aria-busy="true">
      <p className="mono" role="status">{commandTowerCopy.fallbackLoading}</p>
    </section>
  );
}

export function CommandTowerPageIntro({
  locale,
  mode = "live",
  summary,
}: {
  locale: UiLocale;
  mode?: "live" | "partial" | "recovery";
  summary?: string;
}) {
  const commandTowerCopy = getUiCopy(locale).dashboard.commandTowerPage;
  const recoveryMode = mode === "recovery";
  const partialMode = mode === "partial";
  const towerActions = recoveryMode
    ? locale === "zh-CN"
      ? [
          { href: "/command-tower", label: "重载指挥塔", variant: "default" as const },
          { href: "/pm", label: "回到 PM 入口", variant: "secondary" as const },
        ]
      : [
          { href: "/command-tower", label: "Reload Command Tower", variant: "default" as const },
          { href: "/pm", label: "Start from PM", variant: "secondary" as const },
        ]
    : partialMode
      ? locale === "zh-CN"
        ? [
            { href: "/command-tower", label: "重载指挥塔", variant: "default" as const },
            { href: "/runs", label: commandTowerCopy.actions.viewRuns, variant: "secondary" as const },
          ]
        : [
            { href: "/command-tower", label: "Reload Command Tower", variant: "default" as const },
            { href: "/runs", label: commandTowerCopy.actions.viewRuns, variant: "secondary" as const },
          ]
    : locale === "zh-CN"
      ? [
          { href: "/events", label: "打开风险事件", variant: "warning" as const },
          { href: "/workflows", label: "打开工作流案例", variant: "secondary" as const },
          { href: "/runs", label: "打开证明室", variant: "secondary" as const },
        ]
      : [
          { href: "/events", label: "Open risk events", variant: "warning" as const },
          { href: "/workflows", label: "Open Workflow Cases", variant: "secondary" as const },
          { href: "/runs", label: "Open proof room", variant: "secondary" as const },
        ];
  return (
    <header className="app-section">
      <div className="home-briefing-shell">
        <div className="home-briefing-copy">
          <p className="cell-sub mono muted">
            {recoveryMode
              ? locale === "zh-CN"
                ? "恢复模式 / 当前主面不可用"
                : "Recovery mode / live surface unavailable"
              : partialMode
                ? locale === "zh-CN"
                  ? "部分真相 / 实时主面当前降级"
                  : "Partial truth / live surface degraded"
              : locale === "zh-CN"
                ? "L0 驾驶舱 / 实时控制桌"
                : "L0 cockpit / live control desk"}
          </p>
          <h1 id="command-tower-page-title" className="page-title">
            {commandTowerCopy.srTitle}
          </h1>
          <p id="command-tower-page-subtitle" className="page-subtitle">
            {recoveryMode
              ? locale === "zh-CN"
                ? "指挥塔当前拿不到实时总览。先确认只读真相，再走一条恢复路径。"
                : "Command Tower cannot read the live overview right now. Verify the read-only truth first, then take one recovery path."
              : partialMode
                ? commandTowerCopy.partialNextAction
              : commandTowerCopy.srSubtitle}
          </p>
          <p className="cell-sub mono muted">
            {recoveryMode
              ? summary
              : partialMode
                ? summary
              : locale === "zh-CN"
                ? "这一页应该先告诉你：现在发生什么、哪条线危险、下一步该去哪个真相入口。"
                : "This page should answer three questions first: what is happening now, which lane is risky, and which truth surface to open next."}
          </p>
          <nav className="home-briefing-actions" aria-label={locale === "zh-CN" ? "指挥塔首屏操作" : "Command Tower first-screen actions"}>
            {towerActions.map((action) => (
              <Button asChild key={action.href} variant={action.variant}>
                <Link href={action.href}>{action.label}</Link>
              </Button>
            ))}
          </nav>
        </div>
        <Card className="home-briefing-panel">
          <div className="home-briefing-panel-head">
            <span className="cell-sub mono muted">
              {recoveryMode
                ? locale === "zh-CN"
                  ? "恢复判断"
                  : "Recovery judgment"
                : partialMode
                  ? locale === "zh-CN"
                    ? "部分真相判断"
                    : "Partial-truth judgment"
                : locale === "zh-CN"
                  ? "值班判断"
                  : "Operator judgment"}
            </span>
            <Badge variant={recoveryMode || partialMode ? "warning" : "running"}>
              {recoveryMode
                ? locale === "zh-CN"
                  ? "先恢复主面"
                  : "Restore the surface first"
                : partialMode
                  ? locale === "zh-CN"
                    ? commandTowerCopy.partialBadge
                    : commandTowerCopy.partialBadge
                : locale === "zh-CN"
                  ? "先看实时态"
                  : "Live first"}
            </Badge>
          </div>
          <div className="home-briefing-signal-list">
            {recoveryMode ? (
              <>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "当前状态" : "Current state"}</span>
                  <strong>{locale === "zh-CN" ? "实时总览暂时不可读" : "The live overview is temporarily unavailable"}</strong>
                  <p>{locale === "zh-CN" ? "这不是正常驾驶舱读面。先恢复主面，再继续值班。" : "This is not a normal cockpit read. Restore the surface first, then resume operator work."}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "仍然成立的真相" : "What still holds"}</span>
                  <strong>{locale === "zh-CN" ? "只读入口与证明室仍可用" : "The read-only rooms still work"}</strong>
                  <p>{locale === "zh-CN" ? "你仍然可以回 PM 入口、运行记录和工作流案例，但不要把当前页面当成实时驾驶舱。 " : "You can still use PM, Runs, and Workflow Cases, but do not treat this page as a live cockpit right now."}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "恢复动作" : "Recovery move"}</span>
                  <strong>{locale === "zh-CN" ? "先重载，再决定是否回 PM" : "Reload first, then decide whether to return to PM"}</strong>
                  <p>{locale === "zh-CN" ? "把恢复动作收成一条主路径，而不是继续分散到多个正常驾驶舱动作。 " : "Keep recovery on one main path instead of splitting attention across normal cockpit actions."}</p>
                </div>
              </>
            ) : partialMode ? (
              <>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "当前状态" : "Current state"}</span>
                  <strong>{commandTowerCopy.partialTitle}</strong>
                  <p>{locale === "zh-CN" ? "你现在看到的是部分可读的值班面，不是真正完整的实时驾驶舱。首屏要先承认降级，再继续分诊。" : "You are looking at a partially readable operator surface, not a full live cockpit. The first screen should acknowledge degradation before continuing triage."}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "仍然成立的真相" : "What still holds"}</span>
                  <strong>{locale === "zh-CN" ? "可见面板只算部分快照" : "The visible board only counts as a partial snapshot"}</strong>
                  <p>{commandTowerCopy.partialNextAction}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "下一步" : "What to do next"}</span>
                  <strong>{locale === "zh-CN" ? "先重载，再核对运行记录" : "Reload first, then verify runs"}</strong>
                  <p>{locale === "zh-CN" ? "把动作收成一条恢复路径和一条只读核对路径，不要继续按正常 live cockpit 分散注意力。" : "Keep the first screen to one recovery path and one read-only verification path instead of scattering attention across normal live-cockpit actions."}</p>
                </div>
              </>
            ) : (
              <>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "现在发生什么" : "What is happening now"}</span>
                  <strong>{locale === "zh-CN" ? "先看实时会话面板" : "Scan the live session board first"}</strong>
                  <p>{locale === "zh-CN" ? "不要先钻细节页。先确定 board 上最重要的 run 和 session。" : "Do not drill into detail pages first. Identify the most important session and run on the board."}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "风险在哪" : "Where is the risk"}</span>
                  <strong>{locale === "zh-CN" ? "先看风险通道和降级告警" : "Read the risk lane and degraded alert first"}</strong>
                  <p>{locale === "zh-CN" ? "这页的主任务是分诊，不是浏览所有模块。" : "The main job here is triage, not browsing every module."}</p>
                </div>
                <div className="home-briefing-signal">
                  <span className="cell-sub mono muted">{locale === "zh-CN" ? "下一步" : "What to do next"}</span>
                  <strong>{locale === "zh-CN" ? "先用指挥塔，再跳去工作流或证明面" : "Use the tower before jumping to Workflow or Proof"}</strong>
                  <p>{locale === "zh-CN" ? "让 tower 成为主驾驶舱，而不是另一个数据列表页。" : "Treat the tower as the cockpit, not another reporting page."}</p>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>
    </header>
  );
}

export default async function CommandTowerPage() {
  const cookieStore = await cookies();
  const locale = normalizeUiLocale(cookieStore.get(UI_LOCALE_STORAGE_KEY)?.value);
  const { warning, hasLiveData } = await loadCommandTowerHomeState(locale);
  const introMode = warning ? (hasLiveData ? "partial" : "recovery") : "live";
  const introSummary = warning || undefined;
  return (
    <main className="grid" aria-labelledby="command-tower-page-title" aria-describedby="command-tower-page-subtitle">
      <CommandTowerPageIntro locale={locale} mode={introMode} summary={introSummary} />
      {introMode === "recovery" ? null : (
        <Suspense fallback={<CommandTowerHomeSectionFallback locale={locale} />}>
          <CommandTowerHomeSection locale={locale} />
        </Suspense>
      )}
    </main>
  );
}
