import type { MouseEvent } from "react";
import PmStageRail from "../../../components/pm/PmStageRail";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import type { PmSessionSummary } from "../../../lib/types";
import { buildSessionMiniChain, summarizeSession } from "./PMIntakeFeature.shared";

type Props = {
  intakeId: string;
  chatFlowBusy: boolean;
  newConversationBusy: boolean;
  onStartNewConversation: () => void;
  workspacePath: string;
  repoName: string;
  onWorkspacePathChange: (value: string) => void;
  onRepoNameChange: (value: string) => void;
  stage: "discover" | "clarify" | "execute" | "verify";
  sessionHistoryError: string;
  newConversationError: string;
  newConversationNotice: string;
  historyBusy: boolean;
  sessionHistory: PmSessionSummary[];
  onSessionSelect: (sessionId: string) => void;
  onFocusInput: () => void;
};

export default function PMIntakeLeftSidebar(props: Props) {
  const {
    intakeId,
    chatFlowBusy,
    newConversationBusy,
    onStartNewConversation,
    workspacePath,
    repoName,
    onWorkspacePathChange,
    onRepoNameChange,
    stage,
    sessionHistoryError,
    newConversationError,
    newConversationNotice,
    historyBusy,
    sessionHistory,
    onSessionSelect,
    onFocusInput,
  } = props;
  const shortenSessionId = (sessionId: string) =>
    sessionId.length <= 16 ? sessionId : `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`;
  const activeSessionLabel = intakeId
    ? `Current session: ${shortenSessionId(intakeId)}`
    : "Current session: Draft (unsent)";

  const handleDraftSessionClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    onFocusInput();
  };

  const handleSessionItemClick =
    (sessionId: string) =>
    (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      onSessionSelect(sessionId);
    };

  return (
    <aside className="pm-claude-left" aria-label="Session history sidebar">
      <header className="pm-sidebar-header">
        <h2 className="pm-sidebar-title">PM</h2>
        <Button
          variant="default"
          className="pm-new-chat-btn"
          disabled={chatFlowBusy || newConversationBusy}
          onClick={() => onStartNewConversation()}
          data-testid="pm-new-conversation"
        >
          {newConversationBusy ? "Creating..." : "+ New chat"}
        </Button>
      </header>

      <div className="pm-workspace-bind">
        <div className="pm-workspace-row">
          <label className="sr-only" htmlFor="pm-workspace-path-input">
            Workspace path
          </label>
          <Input
            id="pm-workspace-path-input"
            name="workspace_path"
            className="pm-input pm-input-compact"
            value={workspacePath}
            onChange={(event) => onWorkspacePathChange(event.target.value)}
            placeholder="Workspace path"
            aria-label="Workspace path"
          />
          <label className="sr-only" htmlFor="pm-repo-input">
            Repo
          </label>
          <Input
            id="pm-repo-input"
            name="repo_name"
            className="pm-input pm-input-compact pm-repo-input"
            value={repoName}
            onChange={(event) => onRepoNameChange(event.target.value)}
            placeholder="Repo"
            aria-label="Repository slug"
          />
        </div>
      </div>

      <PmStageRail stage={stage} />
      <p className="mono muted" role="status" aria-live="polite" data-testid="pm-sidebar-active-session-indicator">
        {activeSessionLabel}
      </p>

      {sessionHistoryError && <p className="alert alert-danger" role="alert">{sessionHistoryError}</p>}
      {newConversationError && (
        <p className="alert alert-danger" role="alert" data-testid="pm-new-conversation-error">
          {newConversationError}
        </p>
      )}
      {newConversationNotice && !newConversationError && (
        <p className="alert alert-success" role="status" aria-live="polite" data-testid="pm-new-conversation-notice">
          {newConversationNotice}
        </p>
      )}

      <nav aria-label="Session history list">
        <ul className="pm-session-list" aria-label="Session picker">
          <li>
            <Button
              variant="unstyled"
              className={`pm-session-item${!intakeId ? " is-active" : ""}`}
              data-testid="pm-session-item-draft"
              disabled={chatFlowBusy}
              onClick={handleDraftSessionClick}
              aria-current={!intakeId ? "page" : undefined}
              data-draft-focus-only="true"
              aria-label="Draft session, focus the composer"
            >
              <div className="pm-session-item-row">
                <strong className="pm-session-id">Draft session (start typing)</strong>
              </div>
              <span className="pm-session-meta">Focuses the composer only. Sending the first request creates the formal session.</span>
            </Button>
          </li>
          {historyBusy && sessionHistory.length === 0 ? (
            <li className="pm-session-loading">
              <div role="status" aria-live="polite">
                <p>Loading session history</p>
                <div className="skeleton skeleton-row" />
                <div className="skeleton skeleton-row" />
              </div>
            </li>
          ) : sessionHistory.length === 0 ? (
            <li className="pm-session-empty">No previous sessions yet. Send the first request to start.</li>
          ) : (
            sessionHistory.map((session) => {
              const isActive = session.pm_session_id === intakeId;
              const miniChain = buildSessionMiniChain(session);
              const sessionDisplayId = shortenSessionId(session.pm_session_id);
              return (
                <li key={session.pm_session_id}>
                  <Button
                    variant="unstyled"
                    className={`pm-session-item${isActive ? " is-active" : ""}`}
                    data-testid={`pm-session-item-${session.pm_session_id}`}
                    disabled={chatFlowBusy}
                    onClick={handleSessionItemClick(session.pm_session_id)}
                    aria-current={isActive ? "page" : undefined}
                    data-state={isActive ? "active" : "inactive"}
                    data-pm-session-id={session.pm_session_id}
                    aria-label={`Historical session ${session.pm_session_id}`}
                  >
                    <div className="pm-session-item-row">
                      <strong className="pm-session-id" title={session.pm_session_id}>
                        {sessionDisplayId}
                      </strong>
                      <span className="pm-mini-chain" aria-hidden="true">
                        {miniChain.map((state, index) => (
                          <span key={index} className={`pm-mini-node is-${state}`} />
                        ))}
                      </span>
                    </div>
                    <span className="pm-session-meta">{summarizeSession(session)}</span>
                  </Button>
                </li>
              );
            })
          )}
        </ul>
      </nav>
    </aside>
  );
}
