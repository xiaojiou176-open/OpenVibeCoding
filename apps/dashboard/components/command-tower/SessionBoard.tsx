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
    return objective.length > 28 ? `${objective.slice(0, 28)}...` : objective;
  }
  return "Untitled session";
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

export default function SessionBoard({ sessions, snapshotStatus }: SessionBoardProps) {
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
          {snapshotStatus?.label || "Snapshot"}: timestamps reflect snapshot time and do not represent the current live state.
        </p>
      ) : null}
      {groupedSessions.length > visibleGroupedSessions.length ? (
        <p className="mono muted" role="status">Showing {visibleGroupedSessions.length} representative groups on the first view; repeated failure paths are folded together.</p>
      ) : null}
      <table className="run-table">
        <caption className="sr-only">Command Tower session table with status, role step, run stats, and updated time.</caption>
        <thead>
          <tr>
            <th scope="col">Session</th>
            <th scope="col">Status</th>
            <th scope="col">Risk sample</th>
            <th scope="col">Updated</th>
          </tr>
        </thead>
        <tbody>
          {sessions.length === 0 ? (
            <tr>
                  <td colSpan={4} className="muted">
                <div className="empty-state-stack">
                  <span>No PM sessions yet</span>
                  <Link className="run-link" href="/pm">
                    Create a session from PM
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
                        {sessionPrimaryLabel(session)}
                      </Link>
                      {grouped.count > 1 ? (
                        <Badge
                          title={`Grouped sample (${grouped.count})`}
                          aria-label={`Grouped sample (${grouped.count})`}
                        >
                          x{grouped.count}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mono muted">{sessionExecutionLabel(session)}</div>
                    <div className="toolbar toolbar--mt" role="group" aria-label="Session actions">
                      <Link className="run-link" href={`/command-tower/sessions/${encodeURIComponent(session.pm_session_id)}`}>
                        Session details
                      </Link>
                      {session.latest_run_id ? (
                        <Link className="run-link" href={`/runs/${encodeURIComponent(session.latest_run_id)}`}>
                          Latest run
                        </Link>
                      ) : null}
                      {(session.failed_runs > 0 || session.blocked_runs > 0) ? (
                        <Link className="run-link" href="/events">
                          Failure details
                        </Link>
                      ) : null}
                    </div>
                  </th>
                  <td>
                    <div className="run-detail-chip-row run-detail-inline-gap">
                      <Badge variant={sessionBadgeVariant(displayStatus)}>{displayStatus}</Badge>
                      {sessionHealthLabel(session) === "Not started" ? (
                        <span className="mono muted">Not started</span>
                      ) : (
                        <Badge variant={sessionHealthVariant(session)}>{sessionHealthLabel(session)}</Badge>
                      )}
                      {stale ? <Badge variant="warning">Stale</Badge> : null}
                    </div>
                    <span className="sr-only">
                      Session status: {displayStatus}, health: {sessionHealthLabel(session)}
                      {snapshotMode ? ", showing snapshot data" : ""}
                      {stale ? ", update is stale" : ""}
                    </span>
                  </td>
                  <td>
                    <div className="run-detail-chip-row run-detail-inline-gap">
                      {grouped.failedRuns > 0 ? (
                        <Badge variant="failed">Failure path {grouped.failedRuns}</Badge>
                      ) : grouped.blockedRuns > 0 ? (
                        <Badge variant="warning">Blocked path {grouped.blockedRuns}</Badge>
                      ) : grouped.runningRuns > 0 ? (
                        <Badge variant="running">Running {grouped.runningRuns}</Badge>
                      ) : (
                        <Badge variant="success">Stable sample</Badge>
                      )}
                      {grouped.failedRuns > 0 && grouped.blockedRuns > 0 ? (
                        <Badge variant="warning">Blocked {grouped.blockedRuns}</Badge>
                      ) : null}
                    </div>
                    <div className="mono muted">Runs {session.run_count} · Success {grouped.successRuns}</div>
                    {!compactFailureView ? (
                      <div className="run-detail-chip-row run-detail-inline-gap">
                        <Badge variant="running">Success rate {progress}%</Badge>
                        <progress
                          aria-label={`Session ${session.pm_session_id} success rate`}
                          aria-valuetext={`Success rate ${progress}%`}
                          max={100}
                          value={progress}
                          className="run-progress"
                        />
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div className="mono" title={updatedAt}>{toRelativeTs(session.updated_at || session.created_at)}</div>
                    {snapshotMode ? (
                      <div className="mono muted">
                        Snapshot time{updatedAt !== "-" ? " · hover to see the full timestamp" : ""}
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
