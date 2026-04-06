"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { buildTaskPackFieldStateForPack, findTaskPackByTemplate } from "../../../lib/types";
import { resolvePmJourneyContext } from "../../../lib/pmStageResolver";
import { usePMLayoutShortcuts } from "./usePMLayoutShortcuts";
import {
  buildChainNodes,
  isNearBottom,
} from "../components/PMIntakeFeature.shared";
import {
  resolveChatPlaceholder,
  resolveFirstRunNextCta,
  resolveFirstRunStage,
  resolveHeaderHint,
  resolvePmStageText,
} from "../components/PMIntakeFeature.derived";
import type { usePMIntakeData } from "./usePMIntakeData";
import type { usePMIntakeActions } from "./usePMIntakeActions";

type PMIntakeDataState = ReturnType<typeof usePMIntakeData>;
type PMIntakeActionState = ReturnType<typeof usePMIntakeActions>;

export function usePMIntakeView(state: PMIntakeDataState, actions: PMIntakeActionState) {
  const {
    workspaceBound,
    intakeId,
    questions,
    runId,
    copyVariant,
    chatFlowBusy,
    chatBusy,
    busy,
    chatHistoryBusy,
    liveRole,
    chatLog,
    progressFeed,
    plan,
    taskChain,
    sessionHistory,
    setHoveredChainRole,
    activeChatSessionId,
    lastChatLengthRef,
    chatStickToBottom,
    setChatStickToBottom,
    setChatUnreadCount,
    chatLogRef,
    chatAbortRef,
    chatInputRef,
    chainPanelRef,
    setChatError,
    chatInput,
    setChatInput,
    setChatNotice,
    taskPacks = [],
    layoutMode,
    setLayoutMode,
    setTaskTemplate,
    setTaskPackFieldValuesByTemplate = () => {},
    setNewsDigestTopic,
    setNewsDigestSources,
    setNewsDigestTimeRange,
    setNewsDigestMaxResults,
  } = state;

  const currentSession = useMemo(
    () => sessionHistory.find((item) => item.pm_session_id === intakeId) || null,
    [sessionHistory, intakeId],
  );
  const preferredTemplateAppliedRef = useRef(false);

  const headerHint = useMemo(
    () => resolveHeaderHint({ workspaceBound, intakeId, questionsLength: questions.length, runId }),
    [workspaceBound, intakeId, questions.length, runId],
  );

  const firstRunStage = useMemo(
    () => resolveFirstRunStage({ workspaceBound, intakeId, questionsLength: questions.length, runId }),
    [workspaceBound, intakeId, questions.length, runId],
  );

  const firstRunNextCta = useMemo(
    () => resolveFirstRunNextCta({ workspaceBound, intakeId, questionsLength: questions.length, runId }),
    [workspaceBound, intakeId, questions.length, runId],
  );

  const pmJourneyContext = useMemo(
    () =>
      resolvePmJourneyContext({
        intakeId,
        runId,
        sessionStatus: currentSession?.status,
        questions,
        hasUserMessage: chatLog.some((item) => item.role === "PM"),
        hasEvidence:
          Boolean(runId) ||
          Boolean(plan) ||
          Boolean(taskChain) ||
          progressFeed.length > 0 ||
          Boolean(currentSession && currentSession.run_count > 0),
      }),
    [chatLog, currentSession, intakeId, plan, progressFeed.length, questions, runId, taskChain],
  );

  const chainNodes = useMemo(() => {
    const status = String(currentSession?.status || "active");
    return buildChainNodes(liveRole, status);
  }, [liveRole, currentSession?.status]);

  const chatPlaceholder = useMemo(
    () =>
      resolveChatPlaceholder({
        copyVariant,
        workspaceBound,
        intakeId,
        questionsLength: questions.length,
        chatFlowBusy,
        currentSessionStatus: String(currentSession?.status || ""),
        runId,
      }),
    [copyVariant, workspaceBound, intakeId, questions.length, chatFlowBusy, currentSession?.status, runId],
  );

  const pmStageText = useMemo(
    () =>
      resolvePmStageText({
        chatBusy,
        busy,
        chatHistoryBusy,
        intakeId,
        questionsLength: questions.length,
        liveRole,
        runId,
      }),
    [chatBusy, busy, chatHistoryBusy, intakeId, questions.length, liveRole, runId],
  );

  const scrollChatToBottom = useCallback(() => {
    const node = chatLogRef.current;
    if (!node) {
      return;
    }
    if (typeof node.scrollTo === "function") {
      node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
    } else {
      node.scrollTop = node.scrollHeight;
    }
    setChatStickToBottom(true);
    setChatUnreadCount(0);
  }, [chatLogRef, setChatStickToBottom, setChatUnreadCount]);

  const handleChatScroll = useCallback(
    (node: HTMLDivElement) => {
      const nearBottom = isNearBottom(node);
      setChatStickToBottom(nearBottom);
      if (nearBottom) {
        setChatUnreadCount(0);
      }
    },
    [setChatStickToBottom, setChatUnreadCount],
  );

  const requestStopGeneration = useCallback(() => {
    const controller = chatAbortRef.current;
    if (!controller || controller.signal.aborted) {
      setChatNotice("There is no active request to cancel.");
      return;
    }
    controller.abort();
    setChatNotice("Cancelling the active request...");
  }, [chatAbortRef, setChatNotice]);

  const applyExampleTemplate = useCallback(() => {
    const preferredPack = findTaskPackByTemplate(taskPacks, "news_digest") || taskPacks[0] || null;
    if (preferredPack) {
      setTaskTemplate(preferredPack.task_template);
      setTaskPackFieldValuesByTemplate((previous) => ({
        ...previous,
        [preferredPack.task_template]: buildTaskPackFieldStateForPack(
          preferredPack,
          previous[preferredPack.task_template] || {},
        ),
      }));
    } else {
      setTaskTemplate("news_digest");
      setNewsDigestTopic("Seattle tech and AI");
      setNewsDigestSources("theverge.com\ntechcrunch.com\nopenai.com/blog");
      setNewsDigestTimeRange("24h");
      setNewsDigestMaxResults("5");
    }
    setChatInput((current) => current.trim() || "Please create a public-read-only Seattle tech and AI news digest with auditable sources and evidence.");
    chatInputRef.current?.focus();
    setChatError("");
    setChatNotice(`Filled the ${(preferredPack?.task_template || "news_digest")} example. Send it as-is or keep editing.`);
  }, [
    taskPacks,
    setTaskTemplate,
    setTaskPackFieldValuesByTemplate,
    setNewsDigestTopic,
    setNewsDigestSources,
    setNewsDigestTimeRange,
    setNewsDigestMaxResults,
    setChatInput,
    chatInputRef,
    setChatError,
    setChatNotice,
  ]);

  useEffect(() => {
    if (preferredTemplateAppliedRef.current || typeof window === "undefined") {
      return;
    }
    const preferredTemplate = new URLSearchParams(window.location.search).get("template");
    if (!preferredTemplate) {
      return;
    }
    const preferredPack = findTaskPackByTemplate(taskPacks, preferredTemplate);
    if (!preferredPack) {
      return;
    }
    preferredTemplateAppliedRef.current = true;
    setTaskTemplate(preferredPack.task_template);
    setTaskPackFieldValuesByTemplate((previous) => ({
      ...previous,
      [preferredPack.task_template]: buildTaskPackFieldStateForPack(
        preferredPack,
        previous[preferredPack.task_template] || {},
      ),
    }));
    setChatNotice(`Loaded the ${preferredPack.task_template} public example. Preview the Flight Plan or send it as-is.`);
  }, [taskPacks, setTaskTemplate, setTaskPackFieldValuesByTemplate, setChatNotice]);

  const handlePrimaryStageAction = useCallback(() => {
    chatInputRef.current?.focus();
    if (runId) {
      scrollChatToBottom();
      return;
    }
    if (!workspaceBound) {
      setChatError("Bind Workspace and Repo first.");
      return;
    }
    if (!intakeId) {
      if (!chatInput.trim()) {
        setChatError("Enter a request first, or click \"Fill example\".");
        return;
      }
      void actions.handleChatSend();
      return;
    }
    if (questions.length > 0) {
      if (!chatInput.trim()) {
        setChatError("Answer the clarifying question in the composer before sending.");
        return;
      }
      void actions.handleChatSend();
      return;
    }
    if (!runId) {
      void actions.handleRun();
      return;
    }
    scrollChatToBottom();
  }, [chatInputRef, runId, scrollChatToBottom, workspaceBound, setChatError, intakeId, chatInput, actions, questions.length]);

  usePMLayoutShortcuts({
    chatFlowBusy,
    layoutMode,
    setLayoutMode,
    onStartNewConversation: actions.handleStartNewConversation,
    chatInputRef,
    chainPanelRef,
  });

  useEffect(() => {
    lastChatLengthRef.current = chatLog.length;
    setChatUnreadCount(0);
    setChatStickToBottom(true);
  }, [activeChatSessionId, lastChatLengthRef, setChatUnreadCount, setChatStickToBottom]);

  useEffect(() => {
    const delta = chatLog.length - lastChatLengthRef.current;
    lastChatLengthRef.current = chatLog.length;
    if (chatLog.length === 0 || delta <= 0) {
      return;
    }
    if (chatStickToBottom) {
      scrollChatToBottom();
      return;
    }
    setChatUnreadCount((value) => value + delta);
  }, [chatLog.length, chatStickToBottom, lastChatLengthRef, scrollChatToBottom, setChatUnreadCount]);

  return {
    currentSession,
    headerHint,
    firstRunStage,
    firstRunNextCta,
    pmJourneyContext,
    chainNodes,
    chatPlaceholder,
    pmStageText,
    scrollChatToBottom,
    handleChatScroll,
    requestStopGeneration,
    applyExampleTemplate,
    handlePrimaryStageAction,
    setHoveredChainRole,
  };
}
