import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import type { RunSummary, EventRecord } from "../lib/types";
import type { CommandTowerOverviewPayload } from "../lib/types";
import { fetchRuns, fetchAllEvents, fetchCommandTowerOverview } from "../lib/api";
import { badgeClass, formatDesktopDateTime, statusDotClass, statusLabelDesktop } from "../lib/statusPresentation";
import type { DesktopPageKey } from "../App";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";

/* ── SVG Icons (matching Dashboard) ── */
const IconChat = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 3h10a1 1 0 011 1v6a1 1 0 01-1 1H6l-3 3V4a1 1 0 011-1z" />
  </svg>
);
const IconTower = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M8 2v12M4 6h8M5 2h6M3 14h10" />
  </svg>
);
const IconRuns = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="4" cy="4" r="2" /><circle cx="12" cy="8" r="2" /><circle cx="4" cy="12" r="2" />
    <path d="M6 4h4l2 4M6 12h4l2-4" />
  </svg>
);
const IconBolt = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 1L3 9h5l-1 6 6-8H8l1-6z" />
  </svg>
);

function formatDateTime(value: string | undefined, locale: UiLocale): string {
  return formatDesktopDateTime(value, locale);
}

type OverviewPageProps = {
  onNavigate: (page: DesktopPageKey) => void;
  onNavigateToRun: (runId: string) => void;
  locale?: UiLocale;
};

export function OverviewPage({ onNavigate, onNavigateToRun, locale = "en" }: OverviewPageProps) {
  const [overview, setOverview] = useState<CommandTowerOverviewPayload | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const overviewCopy = getUiCopy(locale).desktop.overview;
  const shellCopy =
    locale === "zh-CN"
      ? {
          eyebrow: "OpenVibeCoding / 指挥总览",
          commandDeckTitle: "先看这四件事",
          commandDeckSubtitle: "第一屏先回答现在在发生什么、哪里堵住了、风险是否在上升、下一步该进哪条操作面。",
          nextActionTitle: "下一步",
          nextActionQueued: "回到 Command Tower 继续盯 live 队列",
          nextActionRunning: "打开 Workflow Cases 继续沿 durable state 推进",
          nextActionClear: "从 PM 入口继续派发新任务",
        }
      : {
          eyebrow: "OpenVibeCoding / command overview",
          commandDeckTitle: "Start with these four checks",
          commandDeckSubtitle:
            "The first screen should tell you what is moving, what is blocked, whether risk is rising, and which surface to open next.",
          nextActionTitle: "Next operator action",
          nextActionQueued: "Return to the command tower and keep the live queue in view",
          nextActionRunning: "Open Workflow Cases and continue from the durable state",
          nextActionClear: "Return to PM intake and queue the next task",
        };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [o, r, e] = await Promise.all([
        fetchCommandTowerOverview().catch(() => null),
        fetchRuns().catch(() => []),
        fetchAllEvents().catch(() => []),
      ]);
      setOverview(o);
      setRuns(Array.isArray(r) ? r.slice(0, 10) : []);
      setEvents(Array.isArray(e) ? e.slice(0, 15) : []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const metrics = [
    { label: overviewCopy.metricLabels.totalSessions, value: overview?.total_sessions ?? "-", variant: "" },
    { label: overviewCopy.metricLabels.activeNow, value: overview?.active_sessions ?? "-", variant: "metric-value--primary" },
    { label: overviewCopy.metricLabels.failureRatio, value: overview?.failed_ratio != null ? `${(overview.failed_ratio * 100).toFixed(1)}%` : "-", variant: overview && overview.failed_ratio > 0.1 ? "metric-value--danger" : "metric-value--success" },
    { label: overviewCopy.metricLabels.blockedQueue, value: overview?.blocked_sessions ?? "-", variant: overview && (overview.blocked_sessions ?? 0) > 0 ? "metric-value--danger" : "" },
  ];

  const quickActions: { label: string; desc: string; page: DesktopPageKey; icon: ReactNode }[] = [
    { label: overviewCopy.quickActions.step1Label, desc: overviewCopy.quickActions.step1Desc, page: "pm", icon: <IconChat /> },
    { label: overviewCopy.quickActions.step2Label, desc: overviewCopy.quickActions.step2Desc, page: "command-tower", icon: <IconTower /> },
    { label: overviewCopy.quickActions.step3Label, desc: overviewCopy.quickActions.step3Desc, page: "workflows", icon: <IconRuns /> },
    { label: overviewCopy.quickActions.step4Label, desc: overviewCopy.quickActions.step4Desc, page: "runs", icon: <IconBolt /> },
  ];

  const runningRuns = runs.filter((run) => (run.status || "").toLowerCase() === "running");
  const failedRuns = runs.filter((run) => {
    const s = (run.status || "").toLowerCase();
    return s === "failed" || s === "error" || s === "rejected";
  });
  const blockedEvents = events.filter((evt) => {
    const eventToken = (evt.event || evt.event_type || "").toUpperCase();
    const levelToken = (evt.level || "").toUpperCase();
    return (
      levelToken === "ERROR" ||
      levelToken === "WARN" ||
      eventToken.includes("FAIL") ||
      eventToken.includes("ERROR") ||
      eventToken.includes("BLOCK") ||
      eventToken.includes("DENY")
    );
  });

  const progressCards = [
    {
      title: overviewCopy.runningNowTitle,
      value: runningRuns.length,
      hint: runningRuns.length > 0 ? overviewCopy.progressCards.runningNowHint : overviewCopy.progressCards.runningNowEmpty,
      variant: "metric-value--primary",
    },
    {
      title: overviewCopy.progressCards.needsAttention,
      value: failedRuns.length,
      hint: failedRuns.length > 0 ? overviewCopy.progressCards.needsAttentionHint : overviewCopy.progressCards.needsAttentionEmpty,
      variant: failedRuns.length > 0 ? "metric-value--danger" : "metric-value--success",
    },
    {
      title: overviewCopy.progressCards.riskEvents,
      value: blockedEvents.length,
      hint: blockedEvents.length > 0 ? overviewCopy.progressCards.riskEventsHint : overviewCopy.progressCards.riskEventsEmpty,
      variant: blockedEvents.length > 0 ? "metric-value--danger" : "metric-value--success",
    },
    {
      title: shellCopy.nextActionTitle,
      value: failedRuns.length > 0 ? overviewCopy.viewAllExceptions : runningRuns.length > 0 ? overviewCopy.viewAllRuns : overviewCopy.quickActions.step1Label,
      hint:
        failedRuns.length > 0
          ? shellCopy.nextActionQueued
          : runningRuns.length > 0
            ? shellCopy.nextActionRunning
            : shellCopy.nextActionClear,
      variant: failedRuns.length > 0 ? "metric-value--warning" : "metric-value--primary",
    },
  ];

  const recentExceptions = [
    ...failedRuns.map((run) => ({
      key: `run-${run.run_id}`,
      time: formatDateTime(run.created_at, locale),
      title: overviewCopy.recentExceptionTaskRequiresAttention(run.task_id),
      detail: `${overviewCopy.recentExceptionRunPrefix} ${run.run_id.slice(0, 12)} · ${statusLabelDesktop(run.status, locale)}`,
      runId: run.run_id,
    })),
    ...blockedEvents.slice(0, 6).map((evt, index) => ({
      key: `evt-${evt.ts || index}`,
      time: formatDateTime(evt.ts, locale),
      title: `${evt.event || evt.event_type || overviewCopy.recentExceptionOperatorEventFallback}`,
      detail: `${overviewCopy.recentExceptionLevelPrefix} ${evt.level || "-"} · ${overviewCopy.recentExceptionRunPrefix} ${(evt.run_id || evt._run_id || "-").toString().slice(0, 12)}`,
      runId: (evt.run_id || evt._run_id || "").toString(),
    })),
  ].slice(0, 8);

  return (
    <section className="content" aria-labelledby="overview-title">
      <div className="sr-only" aria-label="总览起步动作" lang="zh-CN">
        <ul>
          <li>开始第一项任务</li>
          <li>查看运行状态</li>
          <li>打开事件列表</li>
        </ul>
      </div>
      {/* Header */}
      <header className="section-header">
        <div>
          <p className="cell-sub mono muted">{shellCopy.eyebrow}</p>
          <h1 id="overview-title" className="page-title">{overviewCopy.title}</h1>
          <p className="page-subtitle">{overviewCopy.subtitle}</p>
        </div>
        <Button onClick={load} aria-label={overviewCopy.refreshData}>{overviewCopy.refreshData}</Button>
      </header>

      <section className="app-section" aria-labelledby="progress-title">
        <div className="section-header">
          <div>
            <h2 id="progress-title" className="section-title">{shellCopy.commandDeckTitle}</h2>
            <p>{shellCopy.commandDeckSubtitle}</p>
          </div>
        </div>
        <div className="stats-grid">
          {progressCards.map((card) => (
            <article key={card.title} className="metric-card">
              <p className="metric-label">{card.title}</p>
              <p className={`metric-value ${card.variant}`}>{card.value}</p>
              <p className="muted text-xs">{card.hint}</p>
            </article>
          ))}
        </div>
      </section>

      {/* Metrics */}
      <section className="app-section" aria-label={overviewCopy.metricsAriaLabel}>
        {loading ? (
          <div className="stats-grid">
            <div className="skeleton skeleton-card" />
            <div className="skeleton skeleton-card" />
            <div className="skeleton skeleton-card" />
            <div className="skeleton skeleton-card" />
          </div>
        ) : (
          <div className="stats-grid">
            {metrics.map((m) => (
              <article key={m.label} className="metric-card">
                <p className="metric-label">{m.label}</p>
                <p className={`metric-value ${m.variant}`}>{m.value}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      {/* Main actions */}
      <section className="app-section" aria-label={overviewCopy.primaryActionsTitle}>
        <h2 className="section-title">{overviewCopy.primaryActionsTitle}</h2>
        <div className="quick-grid">
          {quickActions.map((a) => (
            <Button
              key={a.page}
              unstyled
              className="quick-card"
              onClick={() => onNavigate(a.page)}
            >
              <div className="quick-card-icon">{a.icon}</div>
              <span className="quick-card-title">{a.label}</span>
              <span className="quick-card-desc">{a.desc}</span>
            </Button>
          ))}
        </div>
        <div className="quick-grid" aria-label={overviewCopy.optionalStepLabel}>
          <Button
            unstyled
            className="quick-card"
            onClick={() => onNavigate("god-mode")}
          >
            <div className="quick-card-icon"><IconBolt /></div>
            <span className="quick-card-desc">{overviewCopy.optionalStepLabel}</span>
            <span className="quick-card-title">{overviewCopy.approvalCheckpoint}</span>
            <span className="quick-card-desc">{overviewCopy.approvalCheckpointDesc}</span>
          </Button>
        </div>
      </section>

      {/* Recent Runs */}
      <section className="app-section" aria-labelledby="recent-runs-title">
        <div className="section-header">
          <div>
            <h2 id="recent-runs-title" className="section-title">{overviewCopy.recentRunsTitle}</h2>
            <p className="overview-runs-hint">
              {overviewCopy.recentRunsHint}
            </p>
            <p className="muted text-xs">{overviewCopy.noRunsYet}</p>
          </div>
          <Button onClick={() => onNavigate("runs")}>{overviewCopy.viewAllRuns}</Button>
        </div>
        {runs.length === 0 ? (
          <div className="empty-state-stack"><p className="muted">{overviewCopy.noRunsYet}</p></div>
        ) : (
          <Card className="table-card">
            <table className="run-table">
              <thead>
                <tr><th>{overviewCopy.tableHeaders.runId}</th><th>{overviewCopy.tableHeaders.taskId}</th><th>{overviewCopy.tableHeaders.status}</th><th>{overviewCopy.tableHeaders.createdAt}</th></tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id} className={run.status === "failed" ? "session-row--failed" : run.status === "running" ? "session-row--running" : ""}>
                    <td>
                      <Button
                        type="button"
                        unstyled
                        className="run-link run-link-reset"
                        onClick={() => onNavigateToRun(run.run_id)}
                      >
                        {run.run_id.slice(0, 12)}
                      </Button>
                    </td>
                    <td className="cell-primary">{run.task_id}</td>
                    <td>
                      <span className="status-inline">
                        <span className={statusDotClass(run.status)} />
                        <Badge className={badgeClass(run.status)}>{statusLabelDesktop(run.status, locale)}</Badge>
                      </span>
                    </td>
                    <td className="muted">{formatDateTime(run.created_at, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      {/* Recent Events */}
      <section className="app-section" aria-labelledby="recent-events-title">
        <div className="section-header">
          <h2 id="recent-events-title" className="section-title">{overviewCopy.recentEventsTitle}</h2>
          <Button variant="ghost" onClick={() => onNavigate("events")}>{overviewCopy.viewAllExceptions}</Button>
        </div>
        {recentExceptions.length === 0 ? (
          <div className="empty-state-stack"><p className="muted">{overviewCopy.noExceptionsYet}</p></div>
        ) : (
          <Card className="table-card">
            <table className="run-table">
              <thead>
                <tr><th>{overviewCopy.tableHeaders.time}</th><th>{overviewCopy.tableHeaders.exception}</th><th>{overviewCopy.tableHeaders.details}</th><th>{overviewCopy.tableHeaders.action}</th></tr>
              </thead>
              <tbody>
                {recentExceptions.map((entry) => (
                  <tr key={entry.key}>
                    <td className="muted">{entry.time}</td>
                    <td className="cell-primary">{entry.title}</td>
                    <td className="muted">{entry.detail}</td>
                    <td>
                      {entry.runId ? (
                        <Button variant="ghost" onClick={() => onNavigateToRun(entry.runId)}>
                          {overviewCopy.viewRun}
                        </Button>
                      ) : (
                        <span className="muted">{overviewCopy.openEventStream}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </section>
  );
}
