import { useState, type RefObject } from "react";
import PmStageActionPanel from "../../../components/pm/PmStageActionPanel";
import PmStageHeader from "../../../components/pm/PmStageHeader";
import { useDashboardLocale } from "../../../components/DashboardLocaleContext";
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
  const { locale } = useDashboardLocale();
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
  const layoutModeLabels =
    locale === "zh-CN"
      ? {
          dialog: "聊天优先",
          split: "分栏",
          chain: "链路优先",
          focus: "聚焦聊天",
        }
      : LAYOUT_MODE_LABELS;
  const copy =
    locale === "zh-CN"
      ? {
          discoverNext: "下一步：输入第一条请求",
          discoverSend: "发送第一条请求",
          sessionPrefix: "会话",
          draftSession: "草稿",
          layoutPrefix: "布局",
          firstRunTitle: "首轮路径：发送请求 -> 回答澄清 -> 输入 /run",
          sendNow: "立即发送第一条请求",
          fillExample: "填入示例并聚焦输入框",
          discoverGuideLabel: "发现阶段指南",
          discoverGuideTitle: "先把目标写清，再开正式会话",
          discoverGuideDesc: "第一条消息至少要包含目标、验收标准和范围约束，这样澄清阶段才不会变长。",
          clarifyGuideLabel: "澄清阶段指南",
          clarifyGuideTitle: "先完成澄清，再进入执行",
          clarifyGuideDesc: "先把澄清问题回答完。澄清清空后，流程会自动进入执行阶段。",
          executeGuideLabel: "执行阶段指南",
          executeGuideTitle: "执行已经开始，先看链路和异常",
          executeGuideDesc: "你可以继续补充约束，系统会把增量工作继续分发给 TL 和 Worker。",
          verifyGuideLabel: "验真阶段指南",
          verifyGuideTitle: "结果已回流，准备给结论",
          verifyGuideDesc: "先看 replay 和关键证据，再决定归档、重试，还是继续迭代。",
          backToBottom: "回到底部",
          newMessages: (count: number) => `回到底部，${count} 条新消息`,
          backToBottomWithCount: (count: number) => `回到底部（${count}）`,
          workspaceHint: "先在左侧填好仓库路径和仓库标识。",
          composerLabel: "PM 输入框",
          stopGeneration: "停止生成",
          cancelRequest: "取消当前请求",
          conversationArea: "PM 对话区域",
          layoutMode: "布局模式",
        }
      : {
          discoverNext: "Next: enter the first request",
          discoverSend: "Send first request",
          sessionPrefix: "Session",
          draftSession: "Draft",
          layoutPrefix: "Layout",
          firstRunTitle: "First-run path: send request -> answer clarifiers -> type /run",
          sendNow: "Send first request now",
          fillExample: "Fill example and focus composer",
          discoverGuideLabel: "Discover stage guide",
          discoverGuideTitle: "Define the goal before opening a session",
          discoverGuideDesc: "The first message should include the goal, acceptance criteria, and scope constraints. That keeps Clarify short.",
          clarifyGuideLabel: "Clarify stage guide",
          clarifyGuideTitle: "Answer clarifying questions first",
          clarifyGuideDesc: "Finish the clarifiers before doing anything else. Once they are cleared, the flow moves into Execute automatically.",
          executeGuideLabel: "Execute stage guide",
          executeGuideTitle: "Execution is live, watch the chain and exceptions",
          executeGuideDesc: "You can keep sending messages with extra constraints. The system will route incremental work to TL and Worker.",
          verifyGuideLabel: "Verify stage guide",
          verifyGuideTitle: "Results are ready. Prepare the verdict.",
          verifyGuideDesc: "Review the replay and key evidence first, then decide whether to archive, retry, or continue iterating.",
          backToBottom: "Back to bottom",
          newMessages: (count: number) => `Back to bottom, ${count} new messages`,
          backToBottomWithCount: (count: number) => `Back to bottom (${count})`,
          workspaceHint: "Fill in the Workspace path and Repo slug on the left first.",
          composerLabel: "PM composer",
          stopGeneration: "Stop generation",
          cancelRequest: "Cancel current request",
          conversationArea: "PM conversation area",
          layoutMode: "Layout mode",
        };

  const shortenSessionId = (sessionId: string) =>
    sessionId.length <= 16 ? sessionId : `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`;
  const canSubmit = !chatFlowBusy && !chatBusy && workspaceBound && chatInput.trim().length > 0;
  const isDraftSession = !intakeId;
  const isFirstSendReady = isDraftSession && canSubmit;
  const discoverPrimaryCta = isFirstSendReady
    ? locale === "zh-CN"
      ? "下一步：发送当前草稿请求"
      : "Next: send the drafted request"
    : copy.discoverNext;
  const activeSessionLabel = intakeId
    ? `${copy.sessionPrefix}: ${shortenSessionId(intakeId)}`
    : `${copy.sessionPrefix}: ${copy.draftSession}`;
  const [layoutFeedback, setLayoutFeedback] = useState(layoutModeLabels[layoutMode]);
  const stagePrimaryActionLabel =
    pmJourneyContext.stage === "discover"
      ? isFirstSendReady
        ? copy.discoverSend
        : "Start first request"
      : pmJourneyContext.primaryAction;
  const displayJourneyContext =
    pmJourneyContext.stage === "discover"
      ? { ...pmJourneyContext, primaryAction: stagePrimaryActionLabel }
      : pmJourneyContext;
  const missionCopy =
    displayJourneyContext.stage === "discover"
      ? locale === "zh-CN"
        ? {
            title: "先把第一条任务送进系统",
            desc: "这一屏只做一件事：把目标、验收口径和范围约束写清，然后发出第一条请求。",
          }
        : {
            title: "Send the first real task into the system",
            desc: "This screen should do one thing well: define the goal, acceptance bar, and scope, then send the first request.",
          }
      : displayJourneyContext.stage === "clarify"
        ? locale === "zh-CN"
          ? {
              title: "先完成澄清，再让系统继续跑",
              desc: "现在的唯一主动作是把澄清问题答完，别同时分心去看旁支信息。",
            }
          : {
              title: "Finish clarifiers before you ask the system for more",
              desc: "The only job right now is to clear the open clarifiers before you split attention elsewhere.",
            }
        : displayJourneyContext.stage === "execute"
          ? locale === "zh-CN"
            ? {
                title: "执行已经开始，盯住链路和异常",
                desc: "把中心注意力留给 chain、异常和下一步约束，不要让次级控件抢戏。",
              }
            : {
                title: "Execution is live, so watch the chain and the anomalies",
                desc: "Keep your attention on the chain, the exceptions, and the next constraint instead of secondary controls.",
              }
          : locale === "zh-CN"
            ? {
                title: "结果已回流，先给结论再继续",
                desc: "先看 replay 和关键证据，再决定归档、重试，还是继续迭代。",
              }
            : {
                title: "Results are back, so decide before you drift",
                desc: "Review replay and the key evidence first, then decide whether to archive, retry, or continue.",
              };

  function handleLayoutModeSelection(mode: PMLayoutMode) {
    if (layoutMode === mode) {
      setLayoutFeedback(layoutModeLabels[mode]);
      return;
    }
    onLayoutModeChange(mode);
    setLayoutFeedback(layoutModeLabels[mode]);
  }

  function handleChatCardOptionSelect(option: { label: string }) {
    const current = chatInput.trim();
    const nextValue = current.length > 0 ? current : `${option.label}\n`;
    onChatInputChange(nextValue);
    chatInputRef.current?.focus();
  }

  return (
    <section className="pm-claude-center" aria-label={copy.conversationArea} id="pm-layout-view-panel">
      <header className="pm-chat-topbar">
        <div className="pm-layout-tabs" role="tablist" aria-label={copy.layoutMode}>
          {(Object.keys(layoutModeLabels) as PMLayoutMode[]).map((mode) => (
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
              {layoutModeLabels[mode]}
            </Button>
          ))}
        </div>
        <span className="pm-stage-indicator" role="status" aria-live="polite">{pmStageText}</span>
        <span className="pm-stage-indicator" role="status" aria-live="polite" data-testid="pm-center-session-indicator">
          {activeSessionLabel}
        </span>
        {layoutMode === "dialog" ? (
          <span className="pm-stage-indicator" role="status" aria-live="polite" data-testid="pm-center-layout-feedback">
            {copy.layoutPrefix}: {layoutFeedback}
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
      <section className="pm-context-card pm-mission-card">
        <div className="pm-mission-head">
          <div className="pm-mission-copy">
            <span className="pm-mission-kicker">Mission room</span>
            <p className="pm-context-card-title">{missionCopy.title}</p>
            <p className="pm-context-card-desc">{missionCopy.desc}</p>
          </div>
          <span className="pm-mission-stage">{pmStageText}</span>
        </div>
        <div className="pm-mission-grid" aria-label={locale === "zh-CN" ? "当前任务线索" : "Current mission signals"}>
          <div className="pm-mission-fact">
            <span className="pm-mission-fact-label">{locale === "zh-CN" ? "当前会话" : "Current session"}</span>
            <strong>{activeSessionLabel}</strong>
          </div>
          <div className="pm-mission-fact">
            <span className="pm-mission-fact-label">{locale === "zh-CN" ? "下一步" : "Next move"}</span>
            <strong>{displayJourneyContext.stage === "discover" ? discoverPrimaryCta : firstRunNextCta}</strong>
          </div>
          <div className="pm-mission-fact">
            <span className="pm-mission-fact-label">{locale === "zh-CN" ? "操作焦点" : "Operator focus"}</span>
            <strong>{headerHint}</strong>
          </div>
        </div>
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
              {isFirstSendReady ? copy.sendNow : copy.fillExample}
            </Button>
          ) : null}
        </div>
      </section>
      {layoutMode === "dialog" && displayJourneyContext.stage === "discover" ? (
        <section className="pm-stage-spotlight is-discover" aria-label={copy.discoverGuideLabel}>
          <h3>{copy.discoverGuideTitle}</h3>
          <p>{copy.discoverGuideDesc}</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "clarify" ? (
        <section className="pm-stage-spotlight is-clarify" aria-label={copy.clarifyGuideLabel}>
          <h3>{copy.clarifyGuideTitle}</h3>
          <p>{copy.clarifyGuideDesc}</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "execute" ? (
        <section className="pm-stage-spotlight is-execute" aria-label={copy.executeGuideLabel}>
          <h3>{copy.executeGuideTitle}</h3>
          <p>{copy.executeGuideDesc}</p>
        </section>
      ) : null}
      {layoutMode === "dialog" && displayJourneyContext.stage === "verify" ? (
        <section className="pm-stage-spotlight is-verify" aria-label={copy.verifyGuideLabel}>
          <h3>{copy.verifyGuideTitle}</h3>
          <p>{copy.verifyGuideDesc}</p>
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
            <p className="pm-empty-title">
              {intakeId
                ? locale === "zh-CN" ? "当前会话里还没有消息" : "No messages in this session yet"
                : locale === "zh-CN" ? "当前还没有会话。先发送第一条请求" : "No session yet. Send the first request"}
            </p>
            <p className="pm-empty-hint">
              {intakeId
                ? locale === "zh-CN" ? "发送一条请求，或输入 /run 开始执行。" : "Send a request, or type /run to start execution."
                : locale === "zh-CN" ? "发送第一条请求后，系统会自动创建会话。" : "Send the first request and I will create the session automatically."}
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
                <article className={`pm-chat-bubble ${item.role === "PM" ? "is-pm" : "is-openvibecoding"} is-${item.kind}`}>
                  <header className="pm-bubble-header">
                    <span className="pm-bubble-role">
                      {item.role === "PM"
                        ? locale === "zh-CN" ? "你" : "You"
                        : locale === "zh-CN" ? "OpenVibeCoding 指挥塔" : "OpenVibeCoding Command Tower"}
                    </span>
                    <time className="pm-bubble-time">{shortTime(item.createdAt)}</time>
                  </header>
                  <p className="pm-bubble-text">{item.text}</p>
                  {item.card ? (
                    <PmChatCard
                      kind={item.kind}
                      card={item.card}
                      onOptionSelect={item.kind === "decision" ? handleChatCardOptionSelect : undefined}
                    />
                  ) : null}
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
          aria-label={chatUnreadCount > 0 ? copy.newMessages(chatUnreadCount) : copy.backToBottom}
          title={chatUnreadCount > 0 ? copy.backToBottomWithCount(chatUnreadCount) : copy.backToBottom}
        >
          {chatUnreadCount > 0 && <span className="pm-scroll-fab-badge">{chatUnreadCount}</span>}
          <span className="sr-only">
            {copy.backToBottom}{chatUnreadCount > 0 ? ` (${chatUnreadCount})` : ""}
          </span>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 3v10M4 9l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Button>
      )}

      {!workspaceBound && (
        <section className="pm-context-card">
          <p className="pm-context-card-title">{locale === "zh-CN" ? "先选择工作区再开始" : "Select a workspace to start"}</p>
          <p className="pm-context-card-desc">{copy.workspaceHint}</p>
        </section>
      )}

      <footer className="pm-chat-composer">
        <div className="pm-composer-inner">
          <label className="sr-only" htmlFor="pm-chat-input">
            {copy.composerLabel}
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
            aria-label={copy.composerLabel}
            placeholder={chatPlaceholder}
            disabled={chatFlowBusy || !workspaceBound}
          />
          <div className="pm-composer-actions">
            {chatBusy ? (
              <Button
                variant="secondary"
                className="pm-stop-btn"
                onClick={() => onStopGeneration()}
                aria-label={copy.stopGeneration}
                title={copy.cancelRequest}
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
