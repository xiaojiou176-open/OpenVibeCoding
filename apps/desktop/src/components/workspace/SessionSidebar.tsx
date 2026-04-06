import { Shield } from "lucide-react";
import { Button } from "../ui/Button";
import { sessionStatusToBadge } from "../../lib/status";
import type { DesktopSessionSummary } from "../../lib/api";
import type { Workspace } from "../../lib/desktopUi";

type SessionAgeTone = "fresh" | "active" | "aging";

export function getSessionAgeTone(updatedAtMs: number, nowMs: number): SessionAgeTone {
  const age = nowMs - updatedAtMs;
  if (age <= 5 * 60_000) {
    return "fresh";
  }
  if (age <= 30 * 60_000) {
    return "active";
  }
  return "aging";
}

type SessionSidebarProps = {
  workspace: Workspace | null;
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  setActiveWorkspaceId: (id: string) => void;
  createConversation: () => void;
  sessionItems: DesktopSessionSummary[];
  activeSessionId: string;
  setActiveSessionId: (id: string) => void;
  sessionUpdatedAt: Record<string, number>;
  nowMs: number;
};

export function SessionSidebar({
  workspace,
  workspaces,
  activeWorkspaceId,
  setActiveWorkspaceId,
  createConversation,
  sessionItems,
  activeSessionId,
  setActiveSessionId,
  sessionUpdatedAt,
  nowMs
}: SessionSidebarProps) {
  return (
    <aside className="sidebar session-sidebar" aria-label="Session list">
      <div className="brand-row">
        <span className="brand-icon" aria-hidden="true">
          <Shield size={16} />
        </span>
        <div>
          <strong>Workspaces and Sessions</strong>
          <p>{workspace ? `${workspace.repo} / ${workspace.branch}` : "No workspace selected"}</p>
        </div>
      </div>
      <div className="workspace-actions">
        {workspaces.map((item) => (
          <Button
            key={item.id}
            variant={activeWorkspaceId === item.id ? "primary" : "secondary"}
            onClick={() => setActiveWorkspaceId(item.id)}
          >
            {item.repo} · {item.branch}
          </Button>
        ))}
      </div>
      <Button variant="secondary" onClick={createConversation}>
        + New conversation
      </Button>
      <nav aria-label="Session navigation">
        {sessionItems.map((session) => {
          const badge = sessionStatusToBadge(session.status);
          const active = session.pm_session_id === activeSessionId;
          const ageTone = getSessionAgeTone(
            sessionUpdatedAt[session.pm_session_id] ?? nowMs,
            nowMs
          );
          const ageText = ageTone === "fresh" ? "Fresh" : ageTone === "active" ? "Active" : "Aging";
          return (
            <Button
              key={session.pm_session_id}
              variant={active ? "primary" : "ghost"}
              className={`nav-button ${active ? "is-active" : ""}`.trim()}
              onClick={() => setActiveSessionId(session.pm_session_id)}
              aria-label={`Session ${session.pm_session_id}`}
            >
              <span>{session.pm_session_id}</span>
              <small>{session.current_step || "pm"}</small>
              <span className={`status-badge status-${badge.tone}`}>{badge.label}</span>
              <span className={`status-badge status-${ageTone === "aging" ? "warning" : "running"}`}>{ageText}</span>
              <div className="mini-chain" aria-hidden="true">
                <span className="dot active" />
                <span className="bar" />
                <span className="dot active" />
                <span className="bar" />
                <span className={`dot ${badge.tone === "critical" ? "critical" : "active"}`} />
              </div>
            </Button>
          );
        })}
      </nav>
    </aside>
  );
}
