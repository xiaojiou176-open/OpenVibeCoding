import { useState, type RefObject } from "react";
import PmStageActionPanel from "../../../components/pm/PmStageActionPanel";
import PmStageHeader from "../../../components/pm/PmStageHeader";
import { Button } from "../../../components/ui/button";
import { Textarea } from "../../../components/ui/input";
import PmChatCard from "./PmChatCard";
import {
  chatItemLinkRole,
  LAYOUT_MODE_LABELS,
  shortTime,
  type ChainNode,
  type ChatItem,
  type PMLayoutMode,
} from "./PMIntakeFeature.shared";

type PmJourneyContext = Parameters<typeof PmStageHeader>[0]["context"];

type Props = {
  layoutMode: PMLayoutMode;
  onLayoutModeChange: (mode: PMLayoutMode) => void;
  pmStageText: string;
  pmJourneyContext: PmJourneyContext;
  onPrimaryStageAction: () => void;
  onFillTemplate: () => void;
  chatFlowBusy: boolean;
  chatError: string;
  chatNotice: string;
  firstRunStage: string;
  headerHint: string;
  firstRunNextCta: string;
  intakeId: string;
  chatHistoryBusy: boolean;
  chatLog: ChatItem[];
  liveRole: string;
  hoveredChainRole: ChainNode["role"] | null;
  onHoveredChainRoleChange: (role: ChainNode["role"] | null) => void;
  chatStickToBottom: boolean;
  chatUnreadCount: number;
  onScrollToBottom: () => void;
  workspaceBound: boolean;
  chatInput: string;
  onChatInputChange: (value: string) => void;
  onSend: () => void;
  chatBusy: boolean;
  onStopGeneration: () => void;
  chatPlaceholder: string;
  chatInputRef: RefObject<HTMLTextAreaElement | null>;
  chatLogRef: RefObject<HTMLDivElement | null>;
  onChatScroll: (node: HTMLDivElement) => void;
  chainNodes: ChainNode[];
};

export default function PMIntakeCenterPanel(props: Props) {
  const {
    layoutMode,
    onLayoutModeChange,
    pmStageText,
    pmJourneyContext,
    onPrimaryStageAction,
    onFillTemplate,
    chatFlowBusy,
    chatError,
    chatNotice,
    firstRunStage,
    headerHint,
    firstRunNextCta,
    intakeId,
    chatHistoryBusy,
    chatLog,
    liveRole,
    hoveredChainRole,
    onHoveredChainRoleChange,
    chatStickToBottom,
    chatUnreadCount,
    onScrollToBottom,
    workspaceBound,
    chatInput,
    onChatInputChange,
    onSend,
    chatBusy,
    onStopGeneration,
    chatPlaceholder,
    chatInputRef,
    chatLogRef,
    onChatScroll,
    chainNodes,
  } = props;

  const shortenSessionId = (sessionId: string) =>
    sessionId.length <= 16 ? sessionId : `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`;
  const canSubmit = !chatFlowBusy && !chatBusy && workspaceBound && chatInput.trim().length > 0;
  const isDraftSession = !intakeId;
  const isFirstSendReady = isDraftSession && canSubmit;
  const discoverPrimaryCta = isFirstSendReady ? "Next: send the drafted request" : "Next: enter the first request";
  const activeSessionLabel = intakeId ? `Session: ${shortenSessionId(intakeId)}` : "Session: Draft";
  const [layoutFeedback, setLayoutFeedback] = useState(LAYOUT_MODE_LABELS[layoutMode]);
  const stagePrimaryActionLabel =
    pmJourneyContext.stage === "discover"
      ? isFirstSendReady
        ? "Send first request"
        : "Start first request"
      : pmJourneyContext.primaryAction;
  const displayJourneyContext =
    pmJourneyContext.stage === "discover"
      ? { ...pmJourneyContext, primaryAction: stagePrimaryActionLabel }
      : pmJourneyContext;

  function handleLayoutModeSelection(mode: PMLayoutMode) {
    if (layoutMode === mode) {
      setLayoutFeedback(LAYOUT_MODE_LABELS[mode]);
      return;
    }
    onLayoutModeChange(mode);
    setLayoutFeedback(LAYOUT_MODE_LABELS[mode]);
  }

  return (
    <section className="pm-claude-center" aria-label="PM conversation area" id="pm-layout-view-panel">
      <header className="pm-chat-topbar">
        <div className="pm-layout-tabs" role="tablist" aria-label="Layout mode">
          {(Object.keys(LAYOUT_MODE_LABELS) as PMLayoutMode[]).map((mode) => (
            <Button
              key={mode}
              variant="unstyled"
              className={`pm-layout-tab pm-focus-visible${layoutMode === mode ? " is-active" : ""}`}
              onClick={() => handleLayoutModeSelection(mode)}
              role="tab"
              aria-selected={layoutMode === mode}
              aria-controls="pm-layout-view-panel"
              id={`pm-layout-tab-${mode}`}
              tabIndex={layoutMode === mode ? 0 : -1}
              data-layout-mode={mode}
            >
              {LAYOUT_MODE_LABELS[mode]}
            </Button>
          ))}
        </div>
        <span className="pm-stage-indicator" role="status" aria-live="polite">{pmStageText}</span>
        <span className="pm-stage-indicator" role="status" aria-live="polite" data-testid="pm-center-session-indicator">
          {activeSessionLabel}
        </span>
        {layoutMode === "dialog" ? (
          <span className="pm-stage-indicator" role="status" aria-live="polite" data-testid="pm-center-layout-feedback">
            Layout: {layoutFeedback}
          </span>
        ) : null}
      </header>
      <PmStageHeader context={displayJourneyContext} />
      <PmStageActionPanel
        context={displayJourneyContext}
        onPrimaryAction={() => onPrimaryStageAction()}
        onFillTemplate={() => onFillTemplate()}
        disabled={chatFlowBusy}
      />

      {chatError && <p className="alert alert-danger" role="alert">{chatError}</p>}
      {chatNotice && <p className="alert alert-success" role="status" aria-live="polite">{chatNotice}</p>}
      <section className="pm-context-card">
        <p className="pm-context-card-title">First-run path: send request -&gt; answer clarifiers -&gt; type /run</p>
        <p className="pm-context-card-desc">{firstRunStage} · {headerHint}</p>
        <div className="pm-actions">
          <Button
            variant="default"
            onClick={() => onPrimaryStageAction()}
            data-testid="pm-context-primary-action"
            disabled={chatFlowBusy}
          >
            {displayJourneyContext.stage === "discover" ? discoverPrimaryCta : firstRunNextCta}
          </Button>
          {displayJourneyContext.stage === "discover" ? (
            <Button
              variant="ghost"
              onClick={() => {
                if (isFirstSendReady) {
                  onSend();
                  return;
                }
                onFillTemplate();
              }}
              data-testid={isFirstSendReady ? "pm-context-send-first" : "pm-context-fill-template"}
              disabled={chatFlowBusy || (isFirstSendReady && !canSubmit)}
            >
              {isFirstSendReady ? "Send first request now" : "Fill example and focus composer"}
            </Button>
          ) : null}
        </div>
      </section>
      {layoutMode === "dialog" && displayJourneyContext.stage === "discover" ? (
        <section className="pm-stage-spotlight is-discover" aria-label="Discover stage guide">
          <h3>Define the goal before opening a session</h3>
          <p>The first message should include the goal, acceptance criteria, and scope constraints. That keeps Clarify short.</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "clarify" ? (
        <section className="pm-stage-spotlight is-clarify" aria-label="Clarify stage guide">
          <h3>Answer clarifying questions first</h3>
          <p>Finish the clarifiers before doing anything else. Once they are cleared, the flow moves into Execute automatically.</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "execute" ? (
        <section className="pm-stage-spotlight is-execute" aria-label="Execute stage guide">
          <h3>Execution is live, watch the chain and exceptions</h3>
          <p>You can keep sending messages with extra constraints. The system will route incremental work to TL and Worker.</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "verify" ? (
        <section className="pm-stage-spotlight is-verify" aria-label="Verify stage guide">
          <h3>Results are ready. Prepare the verdict.</h3>
          <p>Review the replay and key evidence first, then decide whether to archive, retry, or continue iterating.</p>
        </section>
      ) : null}

      <div
        ref={chatLogRef}
        className="pm-chat-log"
        role="log"
        aria-live="polite"
        aria-busy={chatFlowBusy || chatHistoryBusy}
        onScroll={(event) => onChatScroll(event.currentTarget)}
      >
        {chatHistoryBusy && chatLog.length === 0 ? (
          <div className="pm-empty-state" role="status" aria-live="polite">
            <div className="skeleton skeleton-chat-loading-primary" />
            <div className="skeleton skeleton-chat-loading-secondary" />
          </div>
        ) : chatLog.length === 0 ? (
          <div className="pm-empty-state">
            <p className="pm-empty-title">{intakeId ? "No messages in this session yet" : "No session yet. Send the first request"}</p>
            <p className="pm-empty-hint">
              {intakeId ? "Send a request, or type /run to start execution." : "Send the first request and I will create the session automatically."}
            </p>
          </div>
        ) : (
          chatLog.map((item, index) => {
            const linkRole = chatItemLinkRole(item, liveRole);
            const linked = hoveredChainRole !== null && linkRole === hoveredChainRole;
            const dimmed = hoveredChainRole !== null && !linked;
            const chatSeq = Math.min(index, 10);
            const previous = index > 0 ? chatLog[index - 1] : null;
            const previousTs = previous ? new Date(previous.createdAt).getTime() : Number.NaN;
            const currentTs = new Date(item.createdAt).getTime();
            const gapMinutes =
              Number.isFinite(previousTs) && Number.isFinite(currentTs)
                ? Math.floor((currentTs - previousTs) / (60 * 1000))
                : 0;
            return (
              <div
                key={item.id}
                className={`pm-chat-message-wrap pm-chat-seq-${chatSeq}${linked ? " is-linked" : ""}${dimmed ? " is-dimmed" : ""}`}
                role={linkRole ? "button" : undefined}
                aria-label={linkRole ? `Highlight messages linked to ${linkRole}` : undefined}
                aria-pressed={linkRole ? linked : undefined}
                onMouseEnter={() => {
                  if (linkRole) onHoveredChainRoleChange(linkRole);
                }}
                onMouseLeave={() => onHoveredChainRoleChange(null)}
                onFocus={() => {
                  if (linkRole) onHoveredChainRoleChange(linkRole);
                }}
                onBlur={() => onHoveredChainRoleChange(null)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    onHoveredChainRoleChange(null);
                    return;
                  }
                  if ((event.key === "Enter" || event.key === " ") && linkRole) {
                    event.preventDefault();
                    onHoveredChainRoleChange(linkRole);
                  }
                }}
                tabIndex={linkRole ? 0 : -1}
              >
                {gapMinutes >= 8 && (
                  <div className="pm-time-fold" role="note">
                    {"--- "}
                    {gapMinutes} min
                    {" ---"}
                  </div>
                )}
                <article className={`pm-chat-bubble ${item.role === "PM" ? "is-pm" : "is-cortexpilot"} is-${item.kind}`}>
                  <header className="pm-bubble-header">
                    <span className="pm-bubble-role">{item.role === "PM" ? "You" : "CortexPilot Command Tower"}</span>
                    <time className="pm-bubble-time">{shortTime(item.createdAt)}</time>
                  </header>
                  <p className="pm-bubble-text">{item.text}</p>
                  {item.card ? <PmChatCard kind={item.kind} card={item.card} /> : null}
                </article>
              </div>
            );
          })
        )}
      </div>

      {!chatStickToBottom && (
        <Button
          variant="unstyled"
          className="pm-scroll-fab pm-focus-visible"
          onClick={() => onScrollToBottom()}
          aria-label={chatUnreadCount > 0 ? `Back to bottom, ${chatUnreadCount} new messages` : "Back to bottom"}
          title={chatUnreadCount > 0 ? `Back to bottom (${chatUnreadCount})` : "Back to bottom"}
        >
          {chatUnreadCount > 0 && <span className="pm-scroll-fab-badge">{chatUnreadCount}</span>}
          <span className="sr-only">
            Back to bottom{chatUnreadCount > 0 ? ` (${chatUnreadCount})` : ""}
          </span>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 3v10M4 9l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Button>
      )}

      {!workspaceBound && (
        <section className="pm-context-card">
          <p className="pm-context-card-title">Select a workspace to start</p>
          <p className="pm-context-card-desc">Fill in the Workspace path and Repo slug on the left first.</p>
        </section>
      )}

      <footer className="pm-chat-composer">
        <div className="pm-composer-inner">
          <label className="sr-only" htmlFor="pm-chat-input">
            PM composer
          </label>
          <Textarea
            variant="unstyled"
            id="pm-chat-input"
            name="message"
            ref={chatInputRef}
            value={chatInput}
            onChange={(event) => onChatInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && canSubmit) {
                event.preventDefault();
                onSend();
              }
            }}
            rows={1}
            className="pm-chat-input"
            aria-label="PM composer"
            placeholder={chatPlaceholder}
            disabled={chatFlowBusy || !workspaceBound}
          />
          <div className="pm-composer-actions">
            {chatBusy ? (
              <Button
                variant="secondary"
                className="pm-stop-btn"
                onClick={() => onStopGeneration()}
                aria-label="Stop generation"
                title="Cancel current request"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">
                  <rect x="2" y="2" width="10" height="10" rx="2" />
                </svg>
              </Button>
            ) : (
              <Button
                variant="default"
                className="pm-send-btn"
                onClick={() => onSend()}
                disabled={!canSubmit}
                aria-label="Send"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path d="M14 2L7 9M14 2l-5 12-2-5-5-2 12-5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </Button>
            )}
          </div>
        </div>
        <p className="pm-composer-hint">Press Enter to send, Shift+Enter for a newline; type /run to start execution</p>
      </footer>

      {layoutMode === "dialog" && (
        <section className="pm-chain-inline-summary" aria-label="Command Chain summary">
          <div className="pm-chain-inline-head">
            <strong>Chain</strong>
            <Button variant="ghost" onClick={() => onLayoutModeChange("split")} data-testid="pm-chain-inline-expand">
              Expand
            </Button>
          </div>
          <div className="pm-chain-inline-flow" role="list">
            {chainNodes.map((node) => (
              <span key={node.role} className={`pm-chain-inline-node is-${node.state}`} role="listitem">
                {node.label}
              </span>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}
