import { lazy, Suspense, useMemo } from "react";
import { FolderGit2, GitBranch } from "lucide-react";
import type { Edge, Node, NodeMouseHandler } from "@xyflow/react";
import { toast } from "sonner";
import { detectPreferredUiLocale } from "@openvibecoding/frontend-shared/uiLocale";
import { Button } from "../../components/ui/Button";
import { ChatPanel } from "../../components/conversation/ChatPanel";
import { NodeDetailDrawer } from "../../components/chain/NodeDetailDrawer";
import { DiffReviewModal } from "../../components/review/DiffReviewModal";
import { ContextDrawer } from "../../components/layout/ContextDrawer";
import type { DesktopAlert, DesktopSessionSummary } from "../../lib/api";
import type { ExecutionPlanReport, TaskPackManifest } from "../../lib/types";
import type { OverviewMetric } from "../../hooks/useDesktopData";
import type { ChainNodeData, ChatMessage, LayoutMode, Workspace } from "../../lib/desktopUi";

const LazyChainPanel = lazy(async () => {
  const module = await import("../../components/chain/ChainPanel");
  return { default: module.ChainPanel };
});

type PmShellContentProps = {
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
  setDrawerVisible: React.Dispatch<React.SetStateAction<boolean>>;
  setDrawerPinned: React.Dispatch<React.SetStateAction<boolean>>;
  activeTimeline: ChatMessage[];
  chatThreadRef: React.MutableRefObject<HTMLElement | null>;
  streamingText: string;
  creatingFirstSession: boolean;
  firstSessionBootstrapError: string;
  firstSessionAllowedPath: string;
  taskPacks: TaskPackManifest[];
  taskPacksLoading: boolean;
  taskPacksError: string;
  taskTemplate: string;
  setTaskTemplate: React.Dispatch<React.SetStateAction<string>>;
  selectedTaskPack: TaskPackManifest | null;
  taskPackFieldValues: Record<string, string>;
  setTaskPackFieldValue: (fieldId: string, value: string) => void;
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
  composerRef: React.MutableRefObject<HTMLTextAreaElement | null>;
  composerInput: string;
  setComposerInput: React.Dispatch<React.SetStateAction<string>>;
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
  layoutMode: LayoutMode;
  setLayoutMode: React.Dispatch<React.SetStateAction<LayoutMode>>;
  chainPanelReady: boolean;
  chainPanelRef: React.MutableRefObject<HTMLElement | null>;
  chainDisplayMode: "compact" | "detail";
  setChainDisplayMode: React.Dispatch<React.SetStateAction<"compact" | "detail">>;
  chainGraph: { nodes: Node<ChainNodeData>[]; edges: Edge[] };
  selectedNodeId: string;
  setSelectedNodeId: React.Dispatch<React.SetStateAction<string>>;
  nodeDrawerOpen: boolean;
  setNodeDrawerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setShowRawNodeOutput: React.Dispatch<React.SetStateAction<boolean>>;
  showRawNodeOutput: boolean;
  messageAnchorByNode: Record<string, string | undefined>;
  reviewDecision: "pending" | "accepted" | "rework";
  setReviewDecision: React.Dispatch<React.SetStateAction<"pending" | "accepted" | "rework">>;
  diffViewerOpen: boolean;
  setDiffViewerOpen: React.Dispatch<React.SetStateAction<boolean>>;
  onReportAccept: () => void;
  onReportRework: () => void;
  cycleWorkspace: () => void;
  cycleBranch: () => void;
  soundEnabled: boolean;
  setSoundEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  overviewMetrics: OverviewMetric[];
  alerts: DesktopAlert[];
  isChainPopout: boolean;
};

function ChainFallback({ chainPanelRef, message }: { chainPanelRef: React.MutableRefObject<HTMLElement | null>; message: string }) {
  const isZh = detectPreferredUiLocale() === "zh-CN";
  return (
    <section ref={chainPanelRef} className="chain-panel" aria-label={isZh ? "Command Chain 面板" : "Command Chain panel"} tabIndex={-1}>
      <header className="chain-toolbar">
        <h2>{isZh ? "命令链" : "Command Chain"}</h2>
      </header>
      <p className="shortcut-hint">{message}</p>
    </section>
  );
}

export function PmShellContent({
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
  creatingFirstSession,
  firstSessionBootstrapError,
  firstSessionAllowedPath,
  taskPacks,
  taskPacksLoading,
  taskPacksError,
  taskTemplate,
  setTaskTemplate,
  selectedTaskPack,
  taskPackFieldValues,
  setTaskPackFieldValue,
  executionPlanPreview = null,
  executionPlanPreviewLoading = false,
  executionPlanPreviewError = "",
  onCreateFirstSession,
  onOpenSessionFallback,
  onPreviewFirstSession = () => {},
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
  onBackToBottom,
  layoutMode,
  setLayoutMode,
  chainPanelReady,
  chainPanelRef,
  chainDisplayMode,
  setChainDisplayMode,
  chainGraph,
  selectedNodeId,
  setSelectedNodeId,
  nodeDrawerOpen,
  setNodeDrawerOpen,
  setShowRawNodeOutput,
  showRawNodeOutput,
  messageAnchorByNode,
  reviewDecision,
  setReviewDecision,
  diffViewerOpen,
  setDiffViewerOpen,
  onReportAccept,
  onReportRework,
  cycleWorkspace,
  cycleBranch,
  soundEnabled,
  setSoundEnabled,
  overviewMetrics,
  alerts,
  isChainPopout,
}: PmShellContentProps) {
  const isZh = detectPreferredUiLocale() === "zh-CN";
  const reportActions = {
    onAccept: onReportAccept,
    onRework: onReportRework,
    onViewDiff: () => setDiffViewerOpen(true),
  };

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    setSelectedNodeId(node.id);
    setNodeDrawerOpen(true);
    setShowRawNodeOutput(false);
    const targetMessageId = messageAnchorByNode[node.id];
    if (!targetMessageId) return;
    const target = document.querySelector(`[data-message-id="${targetMessageId}"]`) as HTMLElement | null;
    target?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  };

  const onNodeDoubleClick: NodeMouseHandler = (_event, node) => {
    setSelectedNodeId(node.id);
    setNodeDrawerOpen(true);
    setShowRawNodeOutput(true);
    setLayoutMode("chain");
  };

  const selectedNode = chainGraph.nodes.find((node) => node.id === selectedNodeId);
  const nodeLinkedMessages = activeTimeline.filter((message) =>
    (message.embeds || []).some((embed) => embed.linkedNodeId === selectedNodeId)
  );
  const nodeRawOutput = useMemo(
    () => nodeLinkedMessages.map((message) => message.content).join("\n\n").trim(),
    [nodeLinkedMessages]
  );

  if (isChainPopout) {
    return (
      <main className="desktop-shell chain-popout" aria-label={isZh ? "命令链弹出窗口" : "Command Chain pop-out window"}>
        <header className="titlebar" data-tauri-drag-region>
          <div className="titlebar-pill" aria-hidden="true" />
          <h1>{isZh ? "命令链" : "Command Chain"}</h1>
        </header>
        <Suspense fallback={<ChainFallback chainPanelRef={chainPanelRef} message={isZh ? "正在加载命令链视图..." : "Loading the chain view..."} />}>
          <LazyChainPanel
            chainPanelRef={chainPanelRef}
            chainDisplayMode={chainDisplayMode}
            setChainDisplayMode={setChainDisplayMode}
            focusChainMode={() => setLayoutMode("chain")}
            nodes={chainGraph.nodes}
            edges={chainGraph.edges}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            selectedNodeId={selectedNodeId}
          />
        </Suspense>
      </main>
    );
  }

  return (
    <>
      <div className="pm-workspace-bar">
        <div className="workspace-picker no-drag" role="group" aria-label={isZh ? "工作区选择器" : "Workspace picker"}>
          <Button variant="secondary" className="workspace-trigger" onClick={cycleWorkspace} aria-label={isZh ? "切换工作区" : "Switch workspace"}>
            <FolderGit2 size={14} aria-hidden="true" />
            {workspace ? workspace.repo : isZh ? "选择工作区" : "Select workspace"}
          </Button>
          <Button variant="ghost" className="workspace-trigger" onClick={cycleBranch} aria-label={isZh ? "切换分支" : "Switch branch"}>
            <GitBranch size={14} aria-hidden="true" />
            {workspace ? workspace.branch : "-"}
          </Button>
          <span className="status-badge status-running">{"●"} {workspace?.activeAgents ?? 0} {isZh ? "个代理" : "agents"}</span>
        </div>
      </div>
      <section className={`main-panel mode-${layoutMode}`} aria-label={isZh ? "主要交互区" : "Primary interaction area"}>
        <ChatPanel
          onboardingVisible={onboardingVisible}
          dismissOnboarding={dismissOnboarding}
          isOffline={isOffline}
          liveError={liveError}
          workspace={workspace}
          activeSessionId={activeSessionId}
          activeSessionGenerating={activeSessionGenerating}
          phaseText={phaseText}
          refreshNow={refreshNow}
          drawerVisible={drawerVisible}
          drawerPinned={drawerPinned}
          setDrawerVisible={setDrawerVisible}
          setDrawerPinned={setDrawerPinned}
          activeTimeline={activeTimeline}
          chatThreadRef={chatThreadRef}
          streamingText={streamingText}
          reportActions={reportActions}
          creatingFirstSession={creatingFirstSession}
          firstSessionBootstrapError={firstSessionBootstrapError}
          firstSessionAllowedPath={firstSessionAllowedPath}
          taskPacks={taskPacks}
          taskPacksLoading={taskPacksLoading}
          taskPacksError={taskPacksError}
          taskTemplate={taskTemplate}
          onTaskTemplateChange={setTaskTemplate}
          selectedTaskPack={selectedTaskPack}
          taskPackFieldValues={taskPackFieldValues}
          onTaskPackFieldChange={setTaskPackFieldValue}
          executionPlanPreview={executionPlanPreview}
          executionPlanPreviewLoading={executionPlanPreviewLoading}
          executionPlanPreviewError={executionPlanPreviewError}
          onCreateFirstSession={onCreateFirstSession}
          onOpenSessionFallback={onOpenSessionFallback}
          onPreviewFirstSession={onPreviewFirstSession}
          chooseDecision={chooseDecision}
          recoverableDraft={recoverableDraft}
          restoreDraft={restoreDraft}
          discardDraft={discardDraft}
          composerRef={composerRef}
          composerInput={composerInput}
          setComposerInput={setComposerInput}
          onComposerEnterSend={onComposerEnterSend}
          composerPlaceholder={composerPlaceholder}
          composerLength={composerLength}
          composerMaxChars={composerMaxChars}
          composerOverLimit={composerOverLimit}
          canSend={canSend}
          sendDisabledReason={sendDisabledReason}
          starterPrompts={starterPrompts}
          onApplyStarterPrompt={onApplyStarterPrompt}
          hasActiveGeneration={hasActiveGeneration}
          stopGeneration={stopGeneration}
          isUserNearBottom={isUserNearBottom}
          unreadCount={unreadCount}
          onBackToBottom={onBackToBottom}
        />
        {layoutMode !== "focus" && (
          <Suspense fallback={<ChainFallback chainPanelRef={chainPanelRef} message={isZh ? "正在加载命令链视图..." : "Loading the chain view..."} />}>
            {chainPanelReady ? (
              <LazyChainPanel
                chainPanelRef={chainPanelRef}
                chainDisplayMode={chainDisplayMode}
                setChainDisplayMode={setChainDisplayMode}
                focusChainMode={() => {
                  setLayoutMode("chain");
                  toast(isZh ? "已切换到命令链优先模式" : "Switched to chain-first mode");
                }}
                nodes={chainGraph.nodes}
                edges={chainGraph.edges}
                onNodeClick={onNodeClick}
                onNodeDoubleClick={onNodeDoubleClick}
                selectedNodeId={selectedNodeId}
              />
            ) : (
              <ChainFallback chainPanelRef={chainPanelRef} message={isZh ? "正在初始化命令链引擎..." : "Initializing the chain engine..."} />
            )}
          </Suspense>
        )}
        {layoutMode === "focus" && (
          <Button unstyled className="chain-peek" type="button" onClick={() => setLayoutMode("split")} aria-label={isZh ? "展开命令链" : "Expand Command Chain"}>
            {isZh ? "展开命令链" : "Expand chain"}
          </Button>
        )}
      </section>
      {drawerVisible && (
        <ContextDrawer
          visible={drawerVisible}
          pinned={drawerPinned}
          soundEnabled={soundEnabled}
          setSoundEnabled={setSoundEnabled}
          overviewMetrics={overviewMetrics}
          alerts={alerts}
        />
      )}
      <NodeDetailDrawer
        open={nodeDrawerOpen}
        selectedNodeId={selectedNodeId}
        selectedNode={selectedNode}
        reviewDecision={reviewDecision}
        showRawNodeOutput={showRawNodeOutput}
        nodeRawOutput={nodeRawOutput}
        onClose={() => setNodeDrawerOpen(false)}
        onToggleRaw={() => setShowRawNodeOutput((value) => !value)}
        onOpenDiff={() => setDiffViewerOpen(true)}
      />
      <DiffReviewModal
        open={diffViewerOpen}
        reviewDecision={reviewDecision}
        onClose={() => setDiffViewerOpen(false)}
        onAccept={onReportAccept}
        onRework={onReportRework}
      />
    </>
  );
}
