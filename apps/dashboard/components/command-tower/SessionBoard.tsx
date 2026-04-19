import Link from "next/link";
import { Badge, type BadgeVariant } from "../ui/badge";
import { Card } from "../ui/card";

import type { PmSessionSummary } from "../../lib/types";

const SESSION_STALE_MS = 24 * 60 * 60 * 1000;

function sessionBadgeVariant(status: string): BadgeVariant {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "done") {
    return "success";
  }
  if (normalized === "failed") {
    return "failed";
  }
  if (normalized === "paused" || normalized === "archived") {
    return "warning";
  }
  return "running";
}

function safeSessionStatus(status: string | undefined): string {
  const normalized = String(status || "").trim();
  return normalized || "unknown";
}

function sessionHealthVariant(session: PmSessionSummary): BadgeVariant {
  if (session.failed_runs > 0) {
    return "failed";
  }
  if (session.blocked_runs > 0) {
    return "warning";
  }
  if (session.running_runs > 0) {
    return "running";
  }
  if (session.success_runs > 0) {
    return "success";
  }
  return "default";
}

function sessionHealthLabel(session: PmSessionSummary): string {
  if (session.failed_runs > 0) {
    return "High risk";
  }
  if (session.blocked_runs > 0) {
    return "Blocked";
  }
  if (session.running_runs > 0) {
    return "Running";
  }
  if (session.success_runs > 0) {
    return "Stable";
  }
  return "Not started";
}

function completionPercent(session: PmSessionSummary): number {
  if (session.run_count <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((session.success_runs / session.run_count) * 100)));
}

function toRelativeTs(rawTs: string | undefined): string {
  if (!rawTs) {
    return "-";
  }
  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return rawTs;
  }

  const diffSec = Math.round((Date.now() - parsed) / 1000);
  if (diffSec < 5) {
    return "just now";
  }
  if (diffSec < 60) {
    return `${diffSec}s ago`;
  }
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) {
    return `${diffMin}m ago`;
  }
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) {
    return `${diffHour}h ago`;
  }
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay}d ago`;
}

function isSessionStale(rawTs: string | undefined): boolean {
  if (!rawTs) {
    return false;
  }
  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return false;
  }
  return Date.now() - parsed > SESSION_STALE_MS;
}

function sessionExecutionLabel(session: PmSessionSummary): string {
  const role = String(session.current_role || "").trim();
  const step = String(session.current_step || "").trim();
  if (!role && !step) {
    return "No active step";
  }
  if (role && step) {
    return `Current: ${role} / ${step}`;
  }
  return `Current: ${role || step}`;
}

function sessionPrimaryLabel(session: PmSessionSummary): string {
  const project = String(session.project_key || "").trim();
  if (project) {
    return `Project ${project}`;
  }
  const objective = String(session.objective || "").trim();
  if (objective) {
    const looksLikePromptDump =
      objective.length > 42
      || /^[A-Z0-9 _./:-]{24,}$/.test(objective)
      || /\b(please|create|review|public|prompt|spec|task)\b/i.test(objective);
    if (looksLikePromptDump) {
      return `Session ${session.pm_session_id.slice(-6)}`;
    }
    return objective.length > 28 ? `${objective.slice(0, 28)}...` : objective;
  }
  return "Untitled session";
}

function sessionObjectivePreview(session: PmSessionSummary): string | undefined {
  const objective = String(session.objective || "").trim();
  if (!objective) {
    return undefined;
  }
  const looksLikePromptDump =
    objective.length > 42
    || /^[A-Z0-9 _./:-]{24,}$/.test(objective)
    || /\b(please|create|review|public|prompt|spec|task)\b/i.test(objective);
  if (looksLikePromptDump) {
    return "Original request available in session details.";
  }
  return objective.length > 72 ? `${objective.slice(0, 72)}...` : objective;
}

function shouldShowSuccessRate(session: PmSessionSummary, grouped: GroupedSession): boolean {
  if (grouped.failedRuns > 0) {
    return false;
  }
  return session.run_count >= 2 || grouped.successRuns > 0;
}

function sessionRowClass(session: PmSessionSummary): string {
  if (session.failed_runs > 0) {
    return "session-row session-row--failed";
  }
  if (session.blocked_runs > 0) {
    return "session-row session-row--blocked";
  }
  if (session.running_runs > 0) {
    return "session-row session-row--running";
  }
  return "session-row";
}

type SessionBoardProps = {
  sessions: PmSessionSummary[];
  snapshotStatus?: { enabled: boolean; label: string };
  locale?: "en" | "zh-CN";
};

type GroupedSession = {
  key: string;
  representative: PmSessionSummary;
  count: number;
  failedRuns: number;
  blockedRuns: number;
  runningRuns: number;
  successRuns: number;
};

function localizedSessionStatus(status: string | undefined, locale: "en" | "zh-CN"): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (!normalized) {
    return locale === "zh-CN" ? "未知" : "unknown";
  }
  if (locale !== "zh-CN") {
    return normalized;
  }
  if (normalized === "done") return "已完成";
  if (normalized === "failed") return "失败";
  if (normalized === "paused") return "已暂停";
  if (normalized === "archived") return "已归档";
  if (normalized === "blocked") return "已阻塞";
  if (normalized === "active" || normalized === "running") return "运行中";
  return normalized;
}

function localizedSessionHealth(session: PmSessionSummary, locale: "en" | "zh-CN"): string {
  if (locale !== "zh-CN") {
    return sessionHealthLabel(session);
  }
  if (session.failed_runs > 0) return "高风险";
  if (session.blocked_runs > 0) return "已阻塞";
  if (session.running_runs > 0) return "运行中";
  if (session.success_runs > 0) return "稳定";
  return "未开始";
}

function localizedRelativeTime(rawTs: string | undefined, locale: "en" | "zh-CN"): string {
  if (locale !== "zh-CN") {
    return toRelativeTs(rawTs);
  }
  if (!rawTs) {
    return "-";
  }
  const parsed = Date.parse(rawTs);
  if (Number.isNaN(parsed)) {
    return rawTs;
  }
  const diffSec = Math.round((Date.now() - parsed) / 1000);
  if (diffSec < 5) return "刚刚";
  if (diffSec < 60) return `${diffSec} 秒前`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  const diffDay = Math.round(diffHour / 24);
  return `${diffDay} 天前`;
}

export default function SessionBoard({ sessions, snapshotStatus, locale = "en" }: SessionBoardProps) {
  const snapshotMode = Boolean(snapshotStatus?.enabled);
  const groupedSessions = Array.from(
    sessions.reduce((acc, session) => {
      const key = [
        sessionPrimaryLabel(session),
        safeSessionStatus(session.status),
        sessionHealthLabel(session),
        session.current_role || "-",
        session.current_step || "-",
      ].join("|");
      const grouped = acc.get(key) ?? {
        key,
        representative: session,
        count: 0,
        failedRuns: 0,
        blockedRuns: 0,
        runningRuns: 0,
        successRuns: 0,
      };
      grouped.count += 1;
      grouped.failedRuns += session.failed_runs;
      grouped.blockedRuns += session.blocked_runs;
      grouped.runningRuns += session.running_runs;
      grouped.successRuns += session.success_runs;
      acc.set(key, grouped);
      return acc;
    }, new Map<string, GroupedSession>())
  ).map(([, grouped]) => grouped);
  const visibleGroupedSessions = groupedSessions.slice(0, 12);

  return (
    <Card variant="table">
      {snapshotMode ? (
        <p className="mono muted" role="status" aria-live="polite">
          {snapshotStatus?.label || (locale === "zh-CN" ? "快照" : "Snapshot")}:{" "}
          {locale === "zh-CN"
            ? "时间戳只代表快照生成时间，不代表当前实时状态。"
            : "timestamps reflect snapshot time and do not represent the current live state."}
        </p>
      ) : null}
      {groupedSessions.length > visibleGroupedSessions.length ? (
        <p className="mono muted" role="status">
          {locale === "zh-CN"
            ? `首屏先显示 ${visibleGroupedSessions.length} 个代表性分组；重复失败路径已折叠。`
            : `Showing ${visibleGroupedSessions.length} representative groups on the first view; repeated failure paths are folded together.`}
        </p>
      ) : null}
      <table className="run-table">
        <caption className="sr-only">
          {locale === "zh-CN"
            ? "指挥塔会话表，包含状态、角色步骤、运行统计和更新时间。"
            : "Command Tower session table with status, role step, run stats, and updated time."}
        </caption>
        <thead>
          <tr>
            <th scope="col">{locale === "zh-CN" ? "会话" : "Session"}</th>
            <th scope="col">{locale === "zh-CN" ? "状态" : "Status"}</th>
            <th scope="col">{locale === "zh-CN" ? "风险样本" : "Risk sample"}</th>
            <th scope="col">{locale === "zh-CN" ? "更新时间" : "Updated"}</th>
          </tr>
        </thead>
        <tbody>
          {sessions.length === 0 ? (
            <tr>
                  <td colSpan={4} className="muted">
                <div className="empty-state-stack">
                  <span>{locale === "zh-CN" ? "当前还没有 PM 会话" : "No PM sessions yet"}</span>
                  <Link className="run-link" href="/pm">
                    {locale === "zh-CN" ? "从 PM 创建会话" : "Create a session from PM"}
                  </Link>
                </div>
              </td>
            </tr>
          ) : (
            visibleGroupedSessions.map((grouped) => {
              const session = grouped.representative;
              const updatedAt = session.updated_at || session.created_at || "-";
              const progress = completionPercent(session);
              const displayStatus = safeSessionStatus(session.status);
              const stale = !snapshotMode && isSessionStale(session.updated_at || session.created_at);
              const compactFailureView = grouped.failedRuns > 0;
              return (
                <tr key={grouped.key} className={sessionRowClass(session)}>
                  <th scope="row">
                    <div className="run-detail-chip-row">
                      <Link
                        className="run-link"
                        href={`/command-tower/sessions/${encodeURIComponent(session.pm_session_id)}`}
                        title={session.pm_session_id}
                      >
                        {locale === "zh-CN" && String(session.project_key || "").trim()
                          ? `项目 ${String(session.project_key || "").trim()}`
                          : sessionPrimaryLabel(session)}
                      </Link>
                      {grouped.count > 1 ? (
                        <Badge
                          title={locale === "zh-CN" ? `分组样本（${grouped.count}）` : `Grouped sample (${grouped.count})`}
                          aria-label={locale === "zh-CN" ? `分组样本（${grouped.count}）` : `Grouped sample (${grouped.count})`}
                        >
                          x{grouped.count}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mono muted">
                      {locale === "zh-CN"
                        ? (() => {
                            const role = String(session.current_role || "").trim();
                            const step = String(session.current_step || "").trim();
                            if (!role && !step) return "当前没有执行步骤";
                            if (role && step) return `当前：${role} / ${step}`;
                            return `当前：${role || step}`;
                          })()
                        : sessionExecutionLabel(session)}
                    </div>
                    {sessionObjectivePreview(session) ? (
                      <div className="cell-sub mono muted">
                        {locale === "zh-CN" && sessionObjectivePreview(session) === "Original request available in session details."
                          ? "原始请求可在会话详情中查看。"
                          : sessionObjectivePreview(session)}
                      </div>
                    ) : null}
                    <div className="toolbar toolbar--mt" role="group" aria-label={locale === "zh-CN" ? "会话动作" : "Session actions"}>
                      <Link className="run-link" href={`/command-tower/sessions/${encodeURIComponent(session.pm_session_id)}`}>
                        {locale === "zh-CN" ? "会话详情" : "Session details"}
                      </Link>
                      {session.latest_run_id ? (
                        <Link className="run-link" href={`/runs/${encodeURIComponent(session.latest_run_id)}`}>
                          {locale === "zh-CN" ? "最新运行" : "Latest run"}
                        </Link>
                      ) : null}
                      {(session.failed_runs > 0 || session.blocked_runs > 0) ? (
                        <Link className="run-link" href="/events">
                          {locale === "zh-CN" ? "失败详情" : "Failure details"}
                        </Link>
                      ) : null}
                    </div>
                  </th>
                  <td>
                    <div className="run-detail-chip-row run-detail-inline-gap">
                      <Badge variant={sessionBadgeVariant(displayStatus)}>{localizedSessionStatus(session.status, locale)}</Badge>
                      {localizedSessionHealth(session, locale) === (locale === "zh-CN" ? "未开始" : "Not started") ? (
                        <span className="mono muted">{locale === "zh-CN" ? "未开始" : "Not started"}</span>
                      ) : (
                        <Badge variant={sessionHealthVariant(session)}>{localizedSessionHealth(session, locale)}</Badge>
                      )}
                      {stale ? <Badge variant="warning">{locale === "zh-CN" ? "已过期" : "Stale"}</Badge> : null}
                    </div>
                    <span className="sr-only">
                      {locale === "zh-CN"
                        ? `会话状态：${localizedSessionStatus(session.status, locale)}，健康度：${localizedSessionHealth(session, locale)}`
                        : `Session status: ${displayStatus}, health: ${localizedSessionHealth(session, locale)}`}
                      {snapshotMode ? (locale === "zh-CN" ? "，当前显示快照数据" : ", showing snapshot data") : ""}
                      {stale ? (locale === "zh-CN" ? "，更新已过期" : ", update is stale") : ""}
                    </span>
                  </td>
                  <td>
                    <div className="run-detail-chip-row run-detail-inline-gap">
                      {grouped.failedRuns > 0 ? (
                        <Badge variant="failed">{locale === "zh-CN" ? `失败路径 ${grouped.failedRuns}` : `Failure path ${grouped.failedRuns}`}</Badge>
                      ) : grouped.blockedRuns > 0 ? (
                        <Badge variant="warning">{locale === "zh-CN" ? `阻塞路径 ${grouped.blockedRuns}` : `Blocked path ${grouped.blockedRuns}`}</Badge>
                      ) : grouped.runningRuns > 0 ? (
                        <Badge variant="running">{locale === "zh-CN" ? `运行中 ${grouped.runningRuns}` : `Running ${grouped.runningRuns}`}</Badge>
                      ) : (
                        <Badge variant="success">{locale === "zh-CN" ? "稳定样本" : "Stable sample"}</Badge>
                      )}
                      {grouped.failedRuns > 0 && grouped.blockedRuns > 0 ? (
                        <Badge variant="warning">{locale === "zh-CN" ? `阻塞 ${grouped.blockedRuns}` : `Blocked ${grouped.blockedRuns}`}</Badge>
                      ) : null}
                    </div>
                    <div className="mono muted">
                      {locale === "zh-CN"
                        ? `运行 ${session.run_count} · 成功 ${grouped.successRuns}`
                        : `Runs ${session.run_count} · Success ${grouped.successRuns}`}
                    </div>
                    {!compactFailureView && shouldShowSuccessRate(session, grouped) ? (
                      <div className="run-detail-chip-row run-detail-inline-gap">
                        <Badge variant="running">{locale === "zh-CN" ? `成功率 ${progress}%` : `Success rate ${progress}%`}</Badge>
                        <progress
                          aria-label={locale === "zh-CN" ? `会话 ${session.pm_session_id} 成功率` : `Session ${session.pm_session_id} success rate`}
                          aria-valuetext={locale === "zh-CN" ? `成功率 ${progress}%` : `Success rate ${progress}%`}
                          max={100}
                          value={progress}
                          className="run-progress"
                        />
                      </div>
                    ) : !compactFailureView ? (
                      <div className="run-detail-chip-row run-detail-inline-gap">
                        <Badge variant="default">{locale === "zh-CN" ? "早期样本" : "Early sample"}</Badge>
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div className="mono" title={updatedAt}>{localizedRelativeTime(session.updated_at || session.created_at, locale)}</div>
                    {snapshotMode ? (
                      <div className="mono muted">
                        {locale === "zh-CN"
                          ? `快照时间${updatedAt !== "-" ? " · 悬停可看完整时间戳" : ""}`
                          : `Snapshot time${updatedAt !== "-" ? " · hover to see the full timestamp" : ""}`}
                      </div>
                    ) : null}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </Card>
  );
}
