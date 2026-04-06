"use client";

import PMIntakeCenterPanel from "./PMIntakeCenterPanel";
import PMIntakeLeftSidebar from "./PMIntakeLeftSidebar";
import PMIntakeRightSidebar from "./PMIntakeRightSidebar";
import { usePMIntakeActions } from "../hooks/usePMIntakeActions";
import { usePMIntakeData } from "../hooks/usePMIntakeData";
import { usePMIntakeView } from "../hooks/usePMIntakeView";

export default function PMIntakeFeature() {
  const state = usePMIntakeData();
  const actions = usePMIntakeActions(state);
  const view = usePMIntakeView(state, actions);
  const chatSessionIsolation = "chatLogBySession";

  return (
    <main
      className={`pm-claude-page pm-layout-${state.layoutMode}`}
      aria-labelledby="pm-page-title"
      data-chat-session-isolation={chatSessionIsolation}
    >
      <section className="sr-only" aria-label="PM 起步动作" lang="zh-CN">
        <ul>
          <li>填写仓库路径</li>
          <li>输入第一条需求</li>
          <li>开始生成计划</li>
        </ul>
      </section>
      <h1 id="pm-page-title" className="sr-only">
        PM workspace
      </h1>
      <PMIntakeLeftSidebar
        intakeId={state.intakeId}
        chatFlowBusy={state.chatFlowBusy}
        newConversationBusy={state.newConversationBusy}
        onStartNewConversation={() => void actions.handleStartNewConversation()}
        workspacePath={state.workspacePath}
        repoName={state.repoName}
        onWorkspacePathChange={state.setWorkspacePath}
        onRepoNameChange={state.setRepoName}
        stage={view.pmJourneyContext.stage}
        sessionHistoryError={state.sessionHistoryError}
        newConversationError={state.newConversationError}
        newConversationNotice={state.newConversationNotice}
        historyBusy={state.historyBusy}
        sessionHistory={state.sessionHistory}
        onSessionSelect={actions.handleSessionSelect}
        onFocusInput={() => {
          state.chatInputRef.current?.focus();
        }}
      />
      <PMIntakeCenterPanel
        layoutMode={state.layoutMode}
        onLayoutModeChange={state.setLayoutMode}
        pmStageText={view.pmStageText}
        pmJourneyContext={view.pmJourneyContext}
        onPrimaryStageAction={view.handlePrimaryStageAction}
        onFillTemplate={view.applyExampleTemplate}
        chatFlowBusy={state.chatFlowBusy}
        chatError={state.chatError}
        chatNotice={state.chatNotice}
        firstRunStage={view.firstRunStage}
        headerHint={view.headerHint}
        firstRunNextCta={view.firstRunNextCta}
        intakeId={state.intakeId}
        chatHistoryBusy={state.chatHistoryBusy}
        chatLog={state.chatLog}
        liveRole={state.liveRole}
        hoveredChainRole={state.hoveredChainRole}
        onHoveredChainRoleChange={view.setHoveredChainRole}
        chatStickToBottom={state.chatStickToBottom}
        chatUnreadCount={state.chatUnreadCount}
        onScrollToBottom={view.scrollChatToBottom}
        workspaceBound={state.workspaceBound}
        chatInput={state.chatInput}
        onChatInputChange={state.setChatInput}
        onSend={() => void actions.handleChatSend()}
        chatBusy={state.chatBusy}
        onStopGeneration={view.requestStopGeneration}
        chatPlaceholder={view.chatPlaceholder}
        chatInputRef={state.chatInputRef}
        chatLogRef={state.chatLogRef}
        onChatScroll={view.handleChatScroll}
        chainNodes={view.chainNodes}
      />
      <PMIntakeRightSidebar
        pmJourneyContext={view.pmJourneyContext}
        runId={state.runId}
        intakeId={state.intakeId}
        liveRole={state.liveRole}
        currentSessionStatus={String(view.currentSession?.status || "")}
        chainNodes={view.chainNodes}
        hoveredChainRole={state.hoveredChainRole}
        onHoveredChainRoleChange={view.setHoveredChainRole}
        progressFeed={state.progressFeed}
        questions={state.questions}
        taskTemplate={state.taskTemplate}
        onTaskTemplateChange={state.setTaskTemplate}
        taskPacks={state.taskPacks}
        taskPacksLoading={state.taskPacksLoading}
        taskPacksError={state.taskPacksError}
        taskPackFieldValues={state.taskPackFieldValues}
        onTaskPackFieldChange={state.setTaskPackFieldValue}
        requesterRole={state.requesterRole}
        onRequesterRoleChange={state.setRequesterRole}
        browserPreset={state.browserPreset}
        onBrowserPresetChange={state.setBrowserPreset}
        canUseCustomPreset={state.canUseCustomPreset}
        customBrowserPolicy={state.customBrowserPolicy}
        onCustomBrowserPolicyChange={state.setCustomBrowserPolicy}
        error={state.error}
        objective={state.objective}
        onObjectiveChange={state.setObjective}
        allowedPaths={state.allowedPaths}
        onAllowedPathsChange={state.setAllowedPaths}
        constraints={state.constraints}
        onConstraintsChange={state.setConstraints}
        searchQueries={state.searchQueries}
        onSearchQueriesChange={state.setSearchQueries}
        chatFlowBusy={state.chatFlowBusy}
        onCreate={() => void actions.handleCreate()}
        onAnswer={() => void actions.handleAnswer()}
        onPreview={() => void actions.handlePreview()}
        onRun={() => void actions.handleRun()}
        hasIntakeId={Boolean(state.intakeId)}
        plan={state.plan}
        taskChain={state.taskChain}
        executionPlanPreview={state.executionPlanPreview}
        executionPlanPreviewBusy={state.executionPlanPreviewBusy}
        executionPlanPreviewError={state.executionPlanPreviewError}
        chainPanelRef={state.chainPanelRef}
      />
    </main>
  );
}
