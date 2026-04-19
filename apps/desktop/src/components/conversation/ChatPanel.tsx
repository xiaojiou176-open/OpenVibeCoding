import { lazy, Suspense, type RefObject } from "react";
import { ArrowUp } from "lucide-react";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { previewFlightPlanCopilotBrief } from "../../lib/api";
import { Button } from "../ui/Button";
import { Input, Select, Textarea } from "../ui/Input";
import { DesktopFlightPlanCopilotPanel } from "../copilot/DesktopFlightPlanCopilotPanel";
import { OnboardingBanner } from "./OnboardingBanner";
import { renderChatEmbed, type ChatMessage, type Workspace } from "../../lib/desktopUi";
import {
  GENERAL_TASK_TEMPLATE,
  type ExecutionPlanReport,
  type TaskPackFieldDefinition,
  type TaskPackManifest,
} from "../../lib/types";

const LazyMarkdownMessage = lazy(async () => {
  const module = await import("./MarkdownMessage");
  return { default: module.MarkdownMessage };
});

function shouldRenderMarkdown(content: string): boolean {
  return (
    content.includes("```") ||
    /`[^`]+`/.test(content) ||
    /^\s{0,3}#{1,6}\s/m.test(content) ||
    /^\s*>\s/m.test(content) ||
    /^\s*([-*+]|\d+\.)\s/m.test(content) ||
    /\[[^\]]+\]\([^)]+\)/.test(content) ||
    /(^|\n)\|.+\|/.test(content) ||
    /(\*\*[^*]+\*\*|__[^_]+__)/.test(content)
  );
}

function compactPreviewList(values: string[], limit = 3): string {
  const filtered = values.map((value) => value.trim()).filter(Boolean);
  if (filtered.length === 0) {
    return "-";
  }
  if (filtered.length <= limit) {
    return filtered.join(", ");
  }
  return `${filtered.slice(0, limit).join(", ")} +${filtered.length - limit} more`;
}

function summarizeFlightPlanTriggers(report: ExecutionPlanReport, isZh: boolean): string {
  const triggers: string[] = [];
  if (report.search_queries.length > 0) {
    triggers.push(isZh ? `检索（${report.search_queries.length}）` : `Search (${report.search_queries.length})`);
  }
  if (report.task_template === "page_brief" || report.browser_policy_preset === "custom" || Boolean(report.effective_browser_policy)) {
    triggers.push(isZh ? "浏览器" : "Browser");
  }
  if (report.requires_human_approval) {
    triggers.push(isZh ? "人工审批" : "Manual approval");
  }
  return triggers.length > 0 ? triggers.join(", ") : isZh ? "当前没有预测到额外能力触发。" : "No extra capability trigger predicted.";
}

type ChatPanelProps = {
  onboardingVisible: boolean;
  dismissOnboarding: () => void;
  isOffline: boolean;
  liveError: string;
  workspace: Workspace | null;
  activeSessionId: string;
  activeSessionGenerating: boolean;
  phaseText: string;
  refreshNow: () => void;
  drawerVisible: boolean;
  drawerPinned: boolean;
  setDrawerVisible: (updater: (value: boolean) => boolean) => void;
  setDrawerPinned: (updater: (value: boolean) => boolean) => void;
  activeTimeline: ChatMessage[];
  chatThreadRef: RefObject<HTMLElement | null>;
  streamingText: string;
  reportActions: {
    onAccept?: (embedId: string) => void;
    onRework?: (embedId: string) => void;
    onViewDiff?: (embedId: string) => void;
  };
  creatingFirstSession: boolean;
  firstSessionBootstrapError: string;
  firstSessionAllowedPath: string;
  taskPacks?: TaskPackManifest[];
  taskPacksLoading?: boolean;
  taskPacksError?: string;
  taskTemplate?: string;
  onTaskTemplateChange?: (value: string) => void;
  selectedTaskPack?: TaskPackManifest | null;
  taskPackFieldValues?: Record<string, string>;
  onTaskPackFieldChange?: (fieldId: string, value: string) => void;
  executionPlanPreview?: ExecutionPlanReport | null;
  executionPlanPreviewLoading?: boolean;
  executionPlanPreviewError?: string;
  onCreateFirstSession: () => void;
  onOpenSessionFallback: () => void;
  onPreviewFirstSession?: () => void;
  chooseDecision: (messageId: string, embedId: string, optionId: string) => void;
  recoverableDraft: { key: string; value: string } | null;
  restoreDraft: () => void;
  discardDraft: () => void;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  composerInput: string;
  setComposerInput: (value: string) => void;
  onComposerEnterSend: () => void;
  composerPlaceholder: string;
  composerLength: number;
  composerMaxChars: number;
  composerOverLimit: boolean;
  canSend: boolean;
  sendDisabledReason: string | null;
  starterPrompts: string[];
  onApplyStarterPrompt: (prompt: string) => void;
  hasActiveGeneration: boolean;
  stopGeneration: () => void;
  isUserNearBottom: boolean;
  unreadCount: number;
  onBackToBottom: () => void;
};

export function ChatPanel({
  onboardingVisible,
  dismissOnboarding,
  isOffline,
  liveError,
  workspace,
  activeSessionId,
  activeSessionGenerating,
  phaseText,
  refreshNow,
  drawerVisible,
  drawerPinned,
  setDrawerVisible,
  setDrawerPinned,
  activeTimeline,
  chatThreadRef,
  streamingText,
  reportActions,
  creatingFirstSession,
  firstSessionBootstrapError,
  firstSessionAllowedPath,
  taskPacks = [],
  taskPacksLoading = false,
  taskPacksError = "",
  taskTemplate = GENERAL_TASK_TEMPLATE,
  onTaskTemplateChange = () => {},
  selectedTaskPack = null,
  taskPackFieldValues = {},
  onTaskPackFieldChange = () => {},
  executionPlanPreview = null,
  executionPlanPreviewLoading = false,
  executionPlanPreviewError = "",
  onCreateFirstSession,
  onOpenSessionFallback,
  onPreviewFirstSession,
  chooseDecision,
  recoverableDraft,
  restoreDraft,
  discardDraft,
  composerRef,
  composerInput,
  setComposerInput,
  onComposerEnterSend,
  composerPlaceholder,
  composerLength,
  composerMaxChars,
  composerOverLimit,
  canSend,
  sendDisabledReason,
  starterPrompts,
  onApplyStarterPrompt,
  hasActiveGeneration,
  stopGeneration,
  isUserNearBottom,
  unreadCount,
  onBackToBottom
}: ChatPanelProps) {
  const isZh = detectPreferredUiLocale() === "zh-CN";
  const hasUserMessage = activeTimeline.some((item) => item.role === "user");
  const nextStepLabel = !activeSessionId
    ? (isZh ? "步骤 0：先创建首个会话" : "Step 0: create the first session")
    : !hasUserMessage
    ? (isZh ? "步骤 1：发送第一条请求" : "Step 1: send the first request")
    : activeSessionGenerating
      ? (isZh ? "下一步：等待当前阶段完成" : "Next: wait for this stage to finish")
      : (isZh ? "步骤 2：输入 /run 开始" : "Step 2: type /run to begin");

  function focusComposerWithTemplate(): void {
    if (!activeSessionId) {
      onCreateFirstSession();
      return;
    }
    composerRef.current?.focus();
    if (!hasUserMessage && !composerInput.trim()) {
      setComposerInput(`objective: Complete a first task in ${firstSessionAllowedPath} that can be verified within 3 minutes.\nallowed_paths: ["${firstSessionAllowedPath}"]`);
    } else if (!activeSessionGenerating && !composerInput.trim()) {
      setComposerInput("/run");
    }
  }

  function renderTaskPackField(field: TaskPackFieldDefinition) {
    const fieldValue = taskPackFieldValues[field.field_id] ?? "";
    if (field.control === "textarea") {
      return (
        <label key={field.field_id} className="row-start-gap-2">
          <span className="mono text-sm fw-500">{field.label}</span>
          <Textarea
            value={fieldValue}
            onChange={(event) => onTaskPackFieldChange(field.field_id, event.target.value)}
            rows={field.field_id === "sources" ? 4 : 3}
            placeholder={field.placeholder}
          />
          {field.help_text ? <span className="shortcut-hint">{field.help_text}</span> : null}
        </label>
      );
    }
    if (field.control === "select") {
      return (
        <label key={field.field_id} className="row-start-gap-2">
          <span className="mono text-sm fw-500">{field.label}</span>
          <Select value={fieldValue} onChange={(event) => onTaskPackFieldChange(field.field_id, event.target.value)}>
            {(field.options || []).map((option) => (
              <option key={`${field.field_id}-${option.value}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          {field.help_text ? <span className="shortcut-hint">{field.help_text}</span> : null}
        </label>
      );
    }
    return (
      <label key={field.field_id} className="row-start-gap-2">
        <span className="mono text-sm fw-500">{field.label}</span>
        <Input
          type={field.control === "number" ? "number" : field.control === "url" ? "url" : "text"}
          min={field.control === "number" ? field.min : undefined}
          max={field.control === "number" ? field.max : undefined}
          value={fieldValue}
          onChange={(event) => onTaskPackFieldChange(field.field_id, event.target.value)}
          placeholder={field.placeholder}
        />
        {field.help_text ? <span className="shortcut-hint">{field.help_text}</span> : null}
      </label>
    );
  }

  return (
    <section className="chat-panel" aria-label={isZh ? "对话面板" : "Conversation panel"}>
      <OnboardingBanner
        visible={onboardingVisible}
        phaseText={activeSessionGenerating ? phaseText : hasUserMessage ? (isZh ? "已准备好执行 /run" : "Ready for /run") : (isZh ? "等待首条请求" : "Waiting for the first request")}
        nextStepLabel={nextStepLabel}
        onNextStep={focusComposerWithTemplate}
        onDismiss={dismissOnboarding}
      />
      {isOffline ? (
        <section className="alert-warning" role="alert">
          {isZh ? "你当前离线，网络恢复后会自动继续同步。" : "You are offline. Sync will resume automatically when the network returns."}
        </section>
      ) : null}
      {liveError ? (
        <section className="alert-warning" role="alert" aria-live="polite">
          {liveError}
        </section>
      ) : null}
      {!workspace ? (
        <section className="workspace-empty" aria-label={isZh ? "空工作区状态" : "Empty workspace state"}>
          <h2>{isZh ? "开始对话前先选择工作区" : "Select a workspace before starting the conversation"}</h2>
          <p>{isZh ? "每个工作区都代表一个仓库和一套代理配置。" : "Each workspace represents one repository and one agent configuration."}</p>
        </section>
      ) : (
        <>
          <section className="chat-toolbar" aria-label={isZh ? "会话工具栏" : "Session toolbar"}>
            <p>
              <strong>{workspace.repo}</strong> / {workspace.branch} · {isZh ? "会话" : "Session"} {activeSessionId || (isZh ? "尚未创建" : "not created yet")}
            </p>
            <p className="shortcut-hint" role="status" aria-live="polite">
              {!activeSessionId ? (isZh ? "发送消息前先创建首个会话" : "Create the first session before sending a message") : activeSessionGenerating ? phaseText : (isZh ? "PM 已准备好接收你的下一条指令" : "The PM is ready for your next instruction")}
            </p>
            {activeSessionGenerating ? (
              <p className="shortcut-hint" role="note" aria-live="polite">{isZh ? "正在同步会话数据..." : "Syncing session data..."}</p>
            ) : null}
            <p className="shortcut-hint" role="note">
              <kbd>Cmd/Ctrl+\\</kbd> {isZh ? "切换布局" : "toggle layout"} · <kbd>Cmd/Ctrl+Shift+D</kbd> {isZh ? "弹出命令链" : "pop out Chain"}
            </p>
            <div className="quick-actions" role="group" aria-label={isZh ? "实时快捷动作" : "Live quick actions"}>
              <Button variant="secondary" onClick={() => refreshNow()}>{isZh ? "立即刷新" : "Refresh now"}</Button>
              <Button variant="secondary" aria-pressed={drawerVisible} onClick={() => setDrawerVisible((value) => !value)}>
                {drawerVisible ? (isZh ? "隐藏抽屉" : "Hide drawer") : (isZh ? "显示抽屉" : "Show drawer")}
              </Button>
              <Button
                variant={drawerPinned ? "primary" : "ghost"}
                aria-pressed={drawerPinned}
                onClick={() => setDrawerPinned((value) => !value)}
              >
                {drawerPinned ? (isZh ? "抽屉已固定" : "Drawer pinned") : (isZh ? "抽屉未固定" : "Drawer unpinned")}
              </Button>
            </div>
          </section>
          {!activeSessionId ? (
            <section className="workspace-empty" aria-label={isZh ? "首会话空状态" : "First-session empty state"}>
              <h2>{isZh ? "先在桌面端创建首个会话，再发送请求" : "Create the first session in desktop before sending a request"}</h2>
              <p>{isZh ? <>桌面端会提交最小 intake（<code>objective</code> + <code>allowed_paths</code>）或你选中的 task-pack 载荷。</> : <>Desktop submits either the smallest intake (<code>objective</code> + <code>allowed_paths</code>) or a selected task-pack payload.</>}</p>
              <p className="shortcut-hint">{isZh ? <>默认 <code>allowed_paths</code>：<code>{firstSessionAllowedPath}</code></> : <>Default <code>allowed_paths</code>: <code>{firstSessionAllowedPath}</code></>}</p>
              {taskPacksError ? (
                <p className="composer-state-note" role="alert">
                  {taskPacksError}
                </p>
              ) : null}
              <div className="row-start-gap-2">
                <label className="row-start-gap-2">
                  <span className="mono text-sm fw-500">{isZh ? "任务包" : "Task pack"}</span>
                  <Select
                    value={taskTemplate}
                    onChange={(event) => onTaskTemplateChange(event.target.value)}
                    aria-label={isZh ? "桌面任务包" : "Desktop task pack"}
                  >
                    {taskPacksLoading ? <option value={taskTemplate}>{isZh ? "正在加载任务包..." : "Loading task packs..."}</option> : null}
                    {taskPacks.map((pack) => (
                      <option key={pack.pack_id} value={pack.task_template}>
                        {pack.ui_hint?.default_label || pack.task_template}
                      </option>
                    ))}
                    <option value={GENERAL_TASK_TEMPLATE}>{GENERAL_TASK_TEMPLATE}</option>
                  </Select>
                </label>
                {selectedTaskPack ? (
                  <>
                    <p className="shortcut-hint">{selectedTaskPack.description}</p>
                    {selectedTaskPack.evidence_contract?.primary_report ? (
                      <p className="shortcut-hint">{isZh ? "主报告：" : "Primary report: "} {selectedTaskPack.evidence_contract.primary_report}</p>
                    ) : null}
                    <div className="stack-gap-3">
                      {selectedTaskPack.input_fields.map((field) => renderTaskPackField(field))}
                    </div>
                  </>
                ) : null}
              </div>
              {firstSessionBootstrapError ? (
                <p className="composer-state-note" role="alert" aria-live="assertive">
                  {firstSessionBootstrapError}
                </p>
              ) : null}
              {executionPlanPreviewError ? (
                <p className="composer-state-note" role="alert" aria-live="assertive">
                  {executionPlanPreviewError}
                </p>
              ) : null}
              {executionPlanPreview ? (
                <div className="stack-gap-2" aria-label={isZh ? "桌面 Flight Plan 预览" : "Desktop Flight Plan preview"}>
                  <p className="shortcut-hint"><strong>{isZh ? "Flight Plan：" : "Flight Plan:"}</strong> {executionPlanPreview.summary}</p>
                  <p className="shortcut-hint">
                    <strong>{isZh ? "清单：" : "Checklist:"}</strong> {executionPlanPreview.objective}
                  </p>
                  <p className="shortcut-hint">
                    {isZh ? "范围边界：" : "Scope boundary:"} {executionPlanPreview.allowed_paths.length} {isZh ? "条允许路径，起始为" : "allowed path entries, starting with"} {compactPreviewList(executionPlanPreview.allowed_paths)}
                  </p>
                  <p className="shortcut-hint">
                    {isZh ? "预期输出：" : "Expected outputs:"} {isZh ? "报告" : "reports"} {compactPreviewList(executionPlanPreview.predicted_reports)}；{isZh ? "产物" : "artifacts"} {compactPreviewList(executionPlanPreview.predicted_artifacts)}
                  </p>
                  <p className="shortcut-hint">
                    {isZh ? "审批风险：" : "Approval risk:"} {executionPlanPreview.requires_human_approval ? (isZh ? "很可能需要人工审批。" : "Manual approval likely.") : (isZh ? "当前不预期需要人工审批。" : "No manual approval expected.")}
                  </p>
                  <p className="shortcut-hint">
                    {isZh ? "能力触发：" : "Capability triggers:"} {summarizeFlightPlanTriggers(executionPlanPreview, isZh)}
                  </p>
                  {executionPlanPreview.warnings?.length ? (
                    <p className="shortcut-hint">{isZh ? "风险门：" : "Risk gates:"} {executionPlanPreview.warnings.join(" | ")}</p>
                  ) : null}
                  <DesktopFlightPlanCopilotPanel
                    title={isZh ? "Flight Plan 副驾" : "Flight Plan copilot"}
                    intro={isZh ? "生成一份只停留在建议层的预跑前简报，依据是当前 Flight Plan 预览、预期输出、能力触发与风险门。" : "Generate one advisory-only pre-run brief grounded in the current Flight Plan preview, expected outputs, capability triggers, and risk gates."}
                    buttonLabel={isZh ? "解释这份 Flight Plan" : "Explain this Flight Plan"}
                    loadBrief={() => previewFlightPlanCopilotBrief(executionPlanPreview, activeSessionId)}
                  />
                </div>
              ) : null}
              <div className="quick-actions">
                <Button variant="secondary" onClick={onPreviewFirstSession} disabled={isOffline || executionPlanPreviewLoading}>
                  {executionPlanPreviewLoading ? (isZh ? "正在预览 Flight Plan..." : "Previewing Flight Plan...") : (isZh ? "预览 Flight Plan" : "Preview Flight Plan")}
                </Button>
                <Button variant="primary" onClick={onCreateFirstSession} disabled={isOffline || creatingFirstSession}>
                  {creatingFirstSession ? (isZh ? "正在在桌面端创建首个会话..." : "Creating the first session in desktop...") : (isZh ? "在桌面端创建首个会话" : "Create first session in desktop")}
                </Button>
                <Button variant="secondary" onClick={onOpenSessionFallback}>{isZh ? "打开 Dashboard /pm 手动创建" : "Open Dashboard /pm and create it manually"}</Button>
              </div>
            </section>
          ) : null}
          <section
            ref={chatThreadRef}
            className="chat-thread"
            aria-label={isZh ? "会话消息" : "Session messages"}
            role="log"
            aria-live="polite"
            aria-relevant="additions text"
            aria-busy={activeSessionGenerating}
          >
            {!activeSessionId ? (
              <p className="drawer-mode-note">{isZh ? '当前还没有会话。先点击“在桌面端创建首个会话”。如果失败，再打开 Dashboard /pm 手动创建。' : 'No session exists yet. Click "Create first session in desktop" first. If that fails, open Dashboard /pm and create it manually.'}</p>
            ) : activeTimeline.length === 0 ? (
              <p className="drawer-mode-note">{isZh ? "这个会话还没有消息。在下面输入请求并按 Enter 发送。" : "This session has no messages yet. Enter a request below and press Enter to send."}</p>
            ) : (
              activeTimeline.map((item) => (
                <article
                  key={item.id}
                  data-message-id={item.id}
                  className={`chat-bubble ${item.role === "user" ? "is-user" : "is-pm"}`.trim()}
                >
                  <strong>{item.role === "user" ? (isZh ? "你" : "You") : "OpenVibeCoding Command Tower PM"}</strong>
                  <div className="markdown-content">
                    {shouldRenderMarkdown(item.content) ? (
                      <Suspense fallback={<p className="chat-plain-text">{item.content}</p>}>
                        <LazyMarkdownMessage content={item.content} />
                      </Suspense>
                    ) : (
                      <p className="chat-plain-text">{item.content}</p>
                    )}
                  </div>
                  {(item.embeds || []).map((embed) => renderChatEmbed(item, embed, chooseDecision, reportActions))}
                </article>
              ))
            )}
            {activeSessionGenerating ? (
              <article className="chat-bubble is-pm typing-bubble" aria-live="polite">
                <strong>OpenVibeCoding Command Tower PM</strong>
                <p>{streamingText || phaseText}</p>
              </article>
            ) : null}
          </section>
          <section className="chat-composer" aria-label={isZh ? "消息输入区" : "Message composer"}>
            <label htmlFor="desktop-chat-input">{isZh ? "继续对话" : "Continue the conversation"}</label>
            {recoverableDraft ? (
              <section className="alert-warning draft-recovery" role="status" aria-live="polite">
                <p>{isZh ? "发现一份未发送草稿，要恢复吗？" : "An unsent draft was found. Restore it?"}</p>
                <div className="quick-actions">
                  <Button variant="secondary" onClick={restoreDraft}>{isZh ? "恢复草稿" : "Restore draft"}</Button>
                  <Button variant="destructive" onClick={discardDraft}>{isZh ? "丢弃草稿" : "Discard draft"}</Button>
                </div>
              </section>
            ) : null}
            <Textarea
              ref={composerRef}
              id="desktop-chat-input"
              value={composerInput}
              onChange={(event) => setComposerInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                  event.preventDefault();
                  onComposerEnterSend();
                }
              }}
              rows={1}
              maxLength={composerMaxChars}
              placeholder={composerPlaceholder}
              disabled={!workspace || isOffline}
            />
            {!hasUserMessage && starterPrompts.length > 0 ? (
              <div className="starter-prompts" role="group" aria-label={isZh ? "起步请求模板" : "Starter request templates"}>
                {starterPrompts.map((prompt) => (
                  <Button
                    key={prompt}
                    type="button"
                    unstyled
                    className="starter-prompt"
                    onClick={() => onApplyStarterPrompt(prompt)}
                    disabled={!workspace || isOffline || hasActiveGeneration}
                  >
                    {prompt}
                  </Button>
                ))}
              </div>
            ) : null}
            <div className="composer-meta">
              <p className="shortcut-hint" role="note">{isZh ? "按 Enter 发送，Shift+Enter 换行。" : "Press Enter to send. Use Shift+Enter for a new line."}</p>
              <span className={`status-badge ${composerOverLimit ? "status-critical" : "status-running"}`}>
                {composerLength}/{composerMaxChars}
              </span>
            </div>
            {sendDisabledReason ? (
              <p className="composer-state-note" role="status" aria-live="polite">
                {sendDisabledReason}
              </p>
            ) : null}
            <div className="quick-actions">
              <Button
                variant="primary"
                onClick={onComposerEnterSend}
                disabled={!canSend}
              >
                <ArrowUp size={16} aria-hidden="true" />
                {isZh ? "发送消息" : "Send message"}
              </Button>
              {!isUserNearBottom || unreadCount > 0 ? (
                <Button variant="secondary" onClick={onBackToBottom} disabled={activeTimeline.length === 0}>
                  {(isZh ? "回到底部" : "Back to bottom")}{unreadCount > 0 ? ` (${unreadCount})` : ""}
                </Button>
              ) : null}
              <Button variant="ghost" onClick={stopGeneration} disabled={!hasActiveGeneration}>
                {isZh ? "停止生成" : "Stop generation"}
              </Button>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
