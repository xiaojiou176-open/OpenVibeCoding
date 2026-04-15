import type { MouseEvent } from "react";
import PmStageRail from "../../../components/pm/PmStageRail";
import { useDashboardLocale } from "../../../components/DashboardLocaleContext";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import type { PmSessionSummary } from "../../../lib/types";
import { buildSessionDisplayLabel, buildSessionMiniChain, compactSessionId, summarizeSession } from "./PMIntakeFeature.shared";

type Props = {
  intakeId: string;
  chatFlowBusy: boolean;
  newConversationBusy: boolean;
  onStartNewConversation: () => void;
  objective: string;
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
  const { locale } = useDashboardLocale();
  const {
    intakeId,
    chatFlowBusy,
    newConversationBusy,
    onStartNewConversation,
    objective,
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
  const activeSession = sessionHistory.find((session) => session.pm_session_id === intakeId);
  const activeSessionLabel = intakeId
    ? `${locale === "zh-CN" ? "当前会话" : "Current session"}: ${
        activeSession
          ? buildSessionDisplayLabel(activeSession)
          : buildSessionDisplayLabel({ objective, project_key: repoName, pm_session_id: intakeId })
      }`
    : locale === "zh-CN" ? "当前会话：草稿（未发送）" : "Current session: Draft (unsent)";

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
          {newConversationBusy ? (locale === "zh-CN" ? "正在创建..." : "Creating...") : locale === "zh-CN" ? "+ 新会话" : "+ New chat"}
        </Button>
      </header>

      <div className="pm-workspace-bind">
        <div className="pm-workspace-row">
          <label className="sr-only" htmlFor="pm-workspace-path-input">
            {locale === "zh-CN" ? "仓库路径" : "Workspace path"}
          </label>
          <Input
            id="pm-workspace-path-input"
            name="workspace_path"
            className="pm-input pm-input-compact"
            value={workspacePath}
            onChange={(event) => onWorkspacePathChange(event.target.value)}
            placeholder={locale === "zh-CN" ? "仓库路径" : "Workspace path"}
            aria-label={locale === "zh-CN" ? "仓库路径" : "Workspace path"}
          />
          <label className="sr-only" htmlFor="pm-repo-input">
            {locale === "zh-CN" ? "仓库标识" : "Repo"}
          </label>
          <Input
            id="pm-repo-input"
            name="repo_name"
            className="pm-input pm-input-compact pm-repo-input"
            value={repoName}
            onChange={(event) => onRepoNameChange(event.target.value)}
            placeholder={locale === "zh-CN" ? "仓库标识" : "Repo"}
            aria-label={locale === "zh-CN" ? "仓库标识" : "Repository slug"}
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

      <nav aria-label={locale === "zh-CN" ? "会话历史列表" : "Session history list"}>
        <ul className="pm-session-list" aria-label={locale === "zh-CN" ? "会话选择器" : "Session picker"}>
          <li>
            <Button
              variant="unstyled"
              className={`pm-session-item${!intakeId ? " is-active" : ""}`}
              data-testid="pm-session-item-draft"
              disabled={chatFlowBusy}
              onClick={handleDraftSessionClick}
              aria-current={!intakeId ? "page" : undefined}
              data-draft-focus-only="true"
              aria-label={locale === "zh-CN" ? "草稿会话，聚焦输入框" : "Draft session, focus the composer"}
            >
              <div className="pm-session-item-row">
                <strong className="pm-session-id">{locale === "zh-CN" ? "草稿会话（开始输入）" : "Draft session (start typing)"}</strong>
              </div>
              <span className="pm-session-meta">
                {locale === "zh-CN"
                  ? "这里只会聚焦输入框。发送第一条请求后，系统才会创建正式会话。"
                  : "Focuses the composer only. Sending the first request creates the formal session."}
              </span>
            </Button>
          </li>
          {historyBusy && sessionHistory.length === 0 ? (
            <li className="pm-session-loading">
              <div role="status" aria-live="polite">
                <p>{locale === "zh-CN" ? "正在加载会话历史" : "Loading session history"}</p>
                <div className="skeleton skeleton-row" />
                <div className="skeleton skeleton-row" />
              </div>
            </li>
          ) : sessionHistory.length === 0 ? (
            <li className="pm-session-empty">
              {locale === "zh-CN" ? "当前还没有历史会话。先发送第一条请求开始。" : "No previous sessions yet. Send the first request to start."}
            </li>
          ) : (
            sessionHistory.map((session) => {
              const isActive = session.pm_session_id === intakeId;
              const miniChain = buildSessionMiniChain(session);
              const sessionDisplayLabel = buildSessionDisplayLabel(session);
              const sessionCompactId = compactSessionId(session.pm_session_id);
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
                    aria-label={locale === "zh-CN" ? `历史会话 ${session.pm_session_id}` : `Historical session ${session.pm_session_id}`}
                  >
                    <div className="pm-session-item-row">
                      <strong className="pm-session-id" title={session.pm_session_id}>
                        {sessionDisplayLabel}
                      </strong>
                      <span className="pm-mini-chain" aria-hidden="true">
                        {miniChain.map((state, index) => (
                          <span key={index} className={`pm-mini-node is-${state}`} />
                        ))}
                      </span>
                    </div>
                    <span className="pm-session-meta">
                      {`ID ${sessionCompactId} · ${summarizeSession(session)}`}
                    </span>
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
