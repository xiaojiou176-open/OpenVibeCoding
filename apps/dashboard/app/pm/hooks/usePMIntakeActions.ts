"use client";

import { useCallback, useEffect, useRef } from "react";
import {
  GENERAL_TASK_TEMPLATE,
  buildTaskPackTemplatePayload,
  findTaskPackByTemplate,
  hydrateTaskPackFieldStateFromPayload,
  mergeTaskPackFieldStateByTemplate,
} from "../../../lib/types";
import {
  answerIntake,
  createIntake,
  fetchPmSession,
  fetchPmSessionEvents,
  fetchPmSessions,
  fetchTaskPacks,
  previewIntake,
  runIntake,
} from "../../../lib/api";
import { runChatSendFlow } from "../components/PMIntakeFeature.actions";
import {
  asString,
  asStringArray,
  buildChatTimeline,
  buildProgressFeed,
  DEFAULT_ACCEPTANCE_TESTS,
  DEFAULT_ALLOWED_PATHS,
  DEFAULT_MCP_TOOL_SET,
  errorDetail,
  inferActiveRole,
  isRequestAborted,
  PM_INTAKE_REQUEST_TIMEOUT_MS,
  sanitizeErrorMessage,
  splitLines,
} from "../components/PMIntakeFeature.shared";
import { usePersistedWorkspaceBindings } from "./usePersistedWorkspaceBindings";
import type { JsonValue, PmSessionSummary } from "../../../lib/types";
import type { usePMIntakeData } from "./usePMIntakeData";

type PMIntakeDataState = ReturnType<typeof usePMIntakeData>;

const PM_SESSION_QUERY_KEY = "pm_session_id";
const NEW_CONVERSATION_REFRESH_TIMEOUT_MS = 10_000;

function syncSessionQueryParam(sessionId: string) {
  if (typeof window === "undefined") {
    return;
  }
  const nextUrl = new URL(window.location.href);
  if (sessionId.trim()) {
    nextUrl.searchParams.set(PM_SESSION_QUERY_KEY, sessionId.trim());
  } else {
    nextUrl.searchParams.delete(PM_SESSION_QUERY_KEY);
  }
  const nextHref = `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
  const currentHref = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (nextHref !== currentHref) {
    window.history.replaceState(window.history.state, "", nextHref);
  }
}

function readSessionFromUrl(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.search
    ? new URLSearchParams(window.location.search).get(PM_SESSION_QUERY_KEY)?.trim() || ""
    : "";
}

export function usePMIntakeActions(state: PMIntakeDataState) {
  const {
    intakeId,
    runId,
    busy,
    chatBusy,
    chatFlowBusy,
    questions,
    answers,
    objective,
    allowedPaths,
    constraints,
    searchQueries,
    taskTemplate,
    taskPackFieldValuesByTemplate,
    workspacePath,
    repoName,
    requesterRole,
    browserPreset,
    customBrowserPolicy,
    effectiveBrowserPolicy,
    canUseCustomPreset,
    activeChatSessionId,
    chatInput,
    activeSessionRef,
    historySyncTokenRef,
    liveSyncTokenRef,
    chatAbortRef,
    newConversationTxnRef,
    newConversationInFlightRef,
    rotateSessionRequestGuard,
    appendChat,
    moveDraftChatToSession,
    mergeSessionChat,
    resetConversation,
    setHistoryBusy,
    setSessionHistoryError,
    setSessionHistory,
    setChatHistoryBusy,
    setChatError,
    setBrowserPreset,
    setRunId,
    setLiveRole,
    setProgressFeed,
    setError,
    setChatNotice,
    setBusy,
    setIntakeId,
    setQuestions,
    setPlan,
    setTaskChain,
    setExecutionPlanPreview,
    setExecutionPlanPreviewBusy,
    setExecutionPlanPreviewError,
    taskPacks,
    setTaskPacks,
    setTaskPacksLoading,
    setTaskPacksError,
    setTaskPackFieldValuesByTemplate,
    setTaskTemplate,
    setEffectiveBrowserPolicy,
    setObjective,
    setChatInput,
    setChatBusy,
    setNewConversationBusy,
    setNewConversationError,
    setNewConversationNotice,
    sessionHistory,
    executionPlanPreviewBusy,
  } = state;

  const urlBootstrapSessionRef = useRef("");
  const sessionSwitchInFlightRef = useRef("");

  usePersistedWorkspaceBindings({
    workspacePath,
    repoName,
    setWorkspacePath: state.setWorkspacePath,
    setRepoName: state.setRepoName,
  });

  const refreshSessionHistory = useCallback(async (): Promise<boolean> => {
    setHistoryBusy(true);
    setSessionHistoryError("");
    try {
      let sessions: PmSessionSummary[] = [];
      let loaded = false;
      let lastError: unknown = null;
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        try {
          sessions = await fetchPmSessions({ limit: 20, sort: "updated_desc", timeoutMs: 30000 });
          loaded = true;
          break;
        } catch (error) {
          lastError = error;
          if (attempt < 2) {
            await new Promise((resolve) => setTimeout(resolve, 400));
          }
        }
      }
      if (!loaded) {
        throw lastError ?? new Error("Failed to load session history");
      }
      setSessionHistory(Array.isArray(sessions) ? sessions : []);
      return true;
    } catch (cause) {
      console.error(`[pm-intake] load sessions failed: ${errorDetail(cause)}`);
      setSessionHistoryError(sanitizeErrorMessage(cause, "Failed to load session history"));
      return false;
    } finally {
      setHistoryBusy(false);
    }
  }, [setHistoryBusy, setSessionHistoryError, setSessionHistory]);

  const hydrateSessionContext = useCallback(
    async (sessionId: string): Promise<boolean> => {
      const normalizedSessionId = sessionId.trim();
      if (!normalizedSessionId) {
        return false;
      }
      const token = liveSyncTokenRef.current;
      const [detailResult, eventsResult] = await Promise.allSettled([
        fetchPmSession(normalizedSessionId),
        fetchPmSessionEvents(normalizedSessionId, { limit: 120, tail: true }),
      ]);
      if (activeSessionRef.current !== normalizedSessionId || liveSyncTokenRef.current !== token) {
        return false;
      }
      const detail = detailResult.status === "fulfilled" ? detailResult.value : null;
      const events = eventsResult.status === "fulfilled" ? eventsResult.value : [];
      const detailLoaded = detailResult.status === "fulfilled";
      if (detailResult.status !== "fulfilled") {
        console.error(`[pm-intake] hydrate session detail failed: ${errorDetail(detailResult.reason)} (intake=${normalizedSessionId})`);
      }
      if (eventsResult.status !== "fulfilled") {
        console.error(`[pm-intake] hydrate session events failed: ${errorDetail(eventsResult.reason)} (intake=${normalizedSessionId})`);
      }
      if (!detailLoaded) {
        return false;
      }
      const latestRunId = typeof detail?.session?.latest_run_id === "string" ? detail.session.latest_run_id : "";
      setRunId(latestRunId || "");
      setLiveRole(inferActiveRole(events, String(detail?.session?.current_role || "")));
      mergeSessionChat(normalizedSessionId, buildChatTimeline(events));
      setProgressFeed(buildProgressFeed(events));
      setChatError("");
      return true;
    },
    [
      activeSessionRef,
      liveSyncTokenRef,
      setRunId,
      setLiveRole,
      mergeSessionChat,
      setProgressFeed,
      setChatError,
    ],
  );

  useEffect(() => {
    void refreshSessionHistory();
  }, [refreshSessionHistory]);

  useEffect(() => {
    let cancelled = false;
    async function loadTaskPacks() {
      setTaskPacksLoading(true);
      setTaskPacksError("");
      try {
        const packs = await fetchTaskPacks();
        if (cancelled) return;
        const resolvedPacks = Array.isArray(packs) ? packs : [];
        setTaskPacks(resolvedPacks);
        setTaskPackFieldValuesByTemplate((previous) => mergeTaskPackFieldStateByTemplate(resolvedPacks, previous));
        if (!findTaskPackByTemplate(resolvedPacks, taskTemplate) && resolvedPacks.length > 0 && taskTemplate !== GENERAL_TASK_TEMPLATE) {
          setTaskTemplate(resolvedPacks[0].task_template);
        }
      } catch (error) {
        if (cancelled) return;
        setTaskPacks([]);
        setTaskPacksError(sanitizeErrorMessage(error, "Task packs unavailable"));
      } finally {
        if (!cancelled) {
          setTaskPacksLoading(false);
        }
      }
    }
    void loadTaskPacks();
    return () => {
      cancelled = true;
    };
  }, [setTaskPacks, setTaskPacksError, setTaskPacksLoading, setTaskPackFieldValuesByTemplate, setTaskTemplate, taskTemplate]);

  useEffect(() => {
    const fromUrl = readSessionFromUrl();
    if (!fromUrl || urlBootstrapSessionRef.current === fromUrl || intakeId) {
      return;
    }
    const matched = sessionHistory.find((item) => item.pm_session_id === fromUrl);
    if (!matched) {
      return;
    }
    urlBootstrapSessionRef.current = fromUrl;
    rotateSessionRequestGuard(fromUrl);
    setIntakeId(fromUrl);
    setRunId("");
    setPlan(null);
    setTaskChain(null);
    setExecutionPlanPreview(null);
    setExecutionPlanPreviewError("");
    setEffectiveBrowserPolicy(null);
    setLiveRole("");
    setProgressFeed([]);
    setQuestions([]);
    setChatError("");
    setChatNotice(`Restored session ${fromUrl}`);
    void hydrateSessionContext(fromUrl).then((ok) => {
      if (!ok && activeSessionRef.current === fromUrl) {
        setChatError("Failed to load session details. Please retry.");
        setChatNotice("Failed to restore the session. Please retry.");
      }
    });
  }, [
    sessionHistory,
    intakeId,
    rotateSessionRequestGuard,
    setIntakeId,
    setRunId,
    setPlan,
    setTaskChain,
    setEffectiveBrowserPolicy,
    setLiveRole,
    setProgressFeed,
    setQuestions,
    setChatError,
    setChatNotice,
    hydrateSessionContext,
  ]);

  useEffect(() => {
    activeSessionRef.current = intakeId;
  }, [activeSessionRef, intakeId]);

  useEffect(() => {
    return () => {
      chatAbortRef.current?.abort();
      chatAbortRef.current = null;
    };
  }, [chatAbortRef]);

  useEffect(() => {
    if (!intakeId) {
      setProgressFeed([]);
      return;
    }
    let cancelled = false;
    const token = historySyncTokenRef.current + 1;
    historySyncTokenRef.current = token;
    const sessionId = intakeId;
    const loadChatTimeline = async () => {
      setChatHistoryBusy(true);
      try {
        const events = await fetchPmSessionEvents(sessionId, { limit: 200, tail: true });
        if (cancelled || historySyncTokenRef.current !== token || activeSessionRef.current !== sessionId) {
          return;
        }
        mergeSessionChat(sessionId, buildChatTimeline(events));
        setChatError("");
      } catch (cause) {
        if (cancelled || historySyncTokenRef.current !== token || activeSessionRef.current !== sessionId) {
          return;
        }
        const message = sanitizeErrorMessage(cause, "Failed to load session messages");
        setChatError(message);
      } finally {
        if (!cancelled && historySyncTokenRef.current === token) {
          setChatHistoryBusy(false);
        }
      }
    };
    void loadChatTimeline();
    return () => {
      cancelled = true;
    };
  }, [
    intakeId,
    setProgressFeed,
    historySyncTokenRef,
    setChatHistoryBusy,
    activeSessionRef,
    mergeSessionChat,
    setChatError,
  ]);

  useEffect(() => {
    if (browserPreset === "custom" && !canUseCustomPreset) {
      setBrowserPreset("safe");
    }
  }, [browserPreset, canUseCustomPreset, setBrowserPreset]);

  useEffect(() => {
    if (!intakeId) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;
    let liveSyncInFlight = false;
    let liveSyncQueued = false;
    const token = liveSyncTokenRef.current + 1;
    liveSyncTokenRef.current = token;
    const sessionId = intakeId;
    const runLiveSync = async () => {
      if (liveSyncInFlight) {
        liveSyncQueued = true;
        return;
      }
      liveSyncInFlight = true;
      try {
        const [detailResult, eventsResult] = await Promise.allSettled([
          fetchPmSession(sessionId),
          fetchPmSessionEvents(sessionId, { limit: 120, tail: true }),
        ]);
        if (cancelled || liveSyncTokenRef.current !== token || activeSessionRef.current !== sessionId) {
          return;
        }
        const detail = detailResult.status === "fulfilled" ? detailResult.value : null;
        const events = eventsResult.status === "fulfilled" ? eventsResult.value : [];
        if (detailResult.status !== "fulfilled") {
          console.error(`[pm-intake] sync session detail failed: ${errorDetail(detailResult.reason)} (intake=${sessionId})`);
        }
        if (eventsResult.status !== "fulfilled") {
          console.error(`[pm-intake] sync session events failed: ${errorDetail(eventsResult.reason)} (intake=${sessionId})`);
        }
        const latestRunId = typeof detail?.session?.latest_run_id === "string" ? detail.session.latest_run_id : "";
        setRunId(latestRunId || "");
        setLiveRole(inferActiveRole(events, String(detail?.session?.current_role || "")));
        mergeSessionChat(sessionId, buildChatTimeline(events));
        setProgressFeed(buildProgressFeed(events));
      } catch (cause) {
        if (!cancelled && liveSyncTokenRef.current === token && activeSessionRef.current === sessionId) {
          console.error(`[pm-intake] sync session live state failed: ${errorDetail(cause)} (intake=${sessionId})`);
        }
      } finally {
        liveSyncInFlight = false;
        if (!cancelled && liveSyncTokenRef.current === token && activeSessionRef.current === sessionId && liveSyncQueued) {
          liveSyncQueued = false;
          void runLiveSync();
        } else if (liveSyncQueued) {
          liveSyncQueued = false;
        }
      }
    };
    void runLiveSync();
    timer = setInterval(() => {
      void runLiveSync();
    }, 2500);
    return () => {
      cancelled = true;
      liveSyncQueued = false;
      if (timer) {
        clearInterval(timer);
      }
    };
  }, [intakeId, liveSyncTokenRef, activeSessionRef, setRunId, setLiveRole, mergeSessionChat, setProgressFeed]);

  const buildIntakePayload = useCallback(
    (nextObjective: string): Record<string, JsonValue> => {
      const workspace = workspacePath.trim();
      const repo = repoName.trim();
      if (!workspace || !repo) {
        throw new Error("Workspace path and repository name must be bound first");
      }
      const selectedTaskPack = findTaskPackByTemplate(taskPacks, taskTemplate);
      const normalizedAllowedPaths = splitLines(allowedPaths);
      const payload: Record<string, JsonValue> = {
        objective: nextObjective.trim(),
        allowed_paths: normalizedAllowedPaths.length > 0 ? normalizedAllowedPaths : [...DEFAULT_ALLOWED_PATHS],
        constraints: [`workspace=${workspace}`, `repo=${repo}`, ...splitLines(constraints)],
        search_queries: splitLines(searchQueries),
        mcp_tool_set: [...DEFAULT_MCP_TOOL_SET],
        acceptance_tests: DEFAULT_ACCEPTANCE_TESTS,
        browser_policy_preset: selectedTaskPack ? "safe" : browserPreset,
        requester_role: requesterRole,
      };
      if (selectedTaskPack) {
        payload.task_template = selectedTaskPack.task_template;
        payload.template_payload = buildTaskPackTemplatePayload(
          selectedTaskPack,
          taskPackFieldValuesByTemplate[selectedTaskPack.task_template] || {},
        );
      }
      if (!selectedTaskPack && browserPreset === "custom") {
        try {
          payload.browser_policy = JSON.parse(customBrowserPolicy);
        } catch {
          throw new Error("Custom browser policy JSON is invalid");
        }
      }
      return payload;
    },
    [
      workspacePath,
      repoName,
      allowedPaths,
      constraints,
      searchQueries,
      taskTemplate,
      taskPackFieldValuesByTemplate,
      taskPacks,
      browserPreset,
      requesterRole,
      customBrowserPolicy,
    ],
  );

  const syncIntakeResult = useCallback(
    (response: Record<string, JsonValue>) => {
      const nextIntakeId = asString(response.intake_id);
      const nextQuestions = asStringArray(response.questions);
      rotateSessionRequestGuard(nextIntakeId);
      setIntakeId(nextIntakeId);
      setQuestions(nextQuestions);
      setPlan(response.plan || null);
      setTaskChain(response.task_chain || null);
      setExecutionPlanPreview(null);
      setExecutionPlanPreviewError("");
      const nextTaskTemplate = asString(response.task_template);
      const nextTemplatePayload =
        response.template_payload && typeof response.template_payload === "object"
          ? (response.template_payload as Record<string, JsonValue>)
          : null;
      if (nextTaskTemplate) {
        const matchedPack = findTaskPackByTemplate(taskPacks, nextTaskTemplate);
        if (matchedPack) {
          setTaskPackFieldValuesByTemplate((previous) => ({
            ...previous,
            [matchedPack.task_template]: hydrateTaskPackFieldStateFromPayload(
              matchedPack,
              nextTemplatePayload,
              previous[matchedPack.task_template] || {},
            ),
          }));
        }
        setTaskTemplate(nextTaskTemplate);
      } else {
        setTaskTemplate(GENERAL_TASK_TEMPLATE);
      }
      setEffectiveBrowserPolicy(response.effective_browser_policy ?? null);
      syncSessionQueryParam(nextIntakeId);
      void refreshSessionHistory();
      return { nextIntakeId, nextQuestions };
    },
    [
      rotateSessionRequestGuard,
      setIntakeId,
      setQuestions,
      setPlan,
      setTaskChain,
      setTaskTemplate,
      setTaskPackFieldValuesByTemplate,
      setEffectiveBrowserPolicy,
      taskPacks,
      refreshSessionHistory,
    ],
  );

  const handleRun = useCallback(async () => {
    if (!intakeId) {
      setError("Create a PM session first.");
      return;
    }
    if (chatBusy || busy) {
      return;
    }
    setError("");
    setChatNotice("");
    setBusy(true);
    try {
      const response = await runIntake(intakeId, {}, { timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS });
      const nextRunId = asString(response.run_id);
      setRunId(nextRunId);
      setChatNotice(`Execution started (run_id: ${nextRunId || "-"})`);
      appendChat("CortexPilot Command Tower", `Execution started, run_id: ${nextRunId || "(empty)"}`, activeChatSessionId, {
        kind: "delegation",
        card: {
          title: "Delegated to Tech Lead",
          subtitle: "TL is breaking down the work and routing it to workers.",
          bullets: ["Goal: execute the current PM session plan", `run_id: ${nextRunId || "-"}`],
          actions: ["View full contract", "Expand details"],
        },
      });
      void refreshSessionHistory();
    } catch (cause) {
      if (isRequestAborted(cause)) {
        setChatNotice("Request cancelled.");
        appendChat("CortexPilot Command Tower", "Cancelled the active request.", activeChatSessionId, {
          kind: "alert",
          card: { title: "Request cancelled", subtitle: "The active execution stopped. Existing context is preserved." },
        });
        return;
      }
      console.error(`[pm-intake] run failed: ${errorDetail(cause)} (intake=${intakeId || "-"}, run=${runId || "-"})`);
      setError(sanitizeErrorMessage(cause, "Start execution failed"));
      setChatNotice("");
      appendChat("CortexPilot Command Tower", `Execution trigger failed: ${sanitizeErrorMessage(cause, "Start execution failed")}`, activeChatSessionId, {
        kind: "alert",
        card: { title: "Gate alert", subtitle: sanitizeErrorMessage(cause, "Start execution failed") },
      });
    } finally {
      setBusy(false);
    }
  }, [
    intakeId,
    chatBusy,
    busy,
    setError,
    setChatNotice,
    setBusy,
    setRunId,
    appendChat,
    activeChatSessionId,
    refreshSessionHistory,
    runId,
  ]);

  const handleCreate = useCallback(async () => {
    if (chatBusy || busy) {
      return;
    }
    setError("");
    setChatNotice("");
    setBusy(true);
    try {
      const payload = buildIntakePayload(objective);
      const response = await createIntake(payload, { timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS });
      const { nextIntakeId, nextQuestions } = syncIntakeResult(response);
      setRunId("");
      setChatNotice(
        nextQuestions.length > 0
          ? `Session ${nextIntakeId} created. ${nextQuestions.length} clarifiers remaining.`
          : `Session ${nextIntakeId} created. Type /run to start execution.`,
      );
    } catch (cause) {
      setError(sanitizeErrorMessage(cause, "Create failed"));
      setChatNotice("");
    } finally {
      setBusy(false);
    }
  }, [chatBusy, busy, setError, setChatNotice, setBusy, buildIntakePayload, objective, syncIntakeResult, setRunId]);

  const handleAnswer = useCallback(async () => {
    if (!intakeId) {
      setError("Create a PM session first.");
      return;
    }
    if (chatBusy || busy) {
      return;
    }
    setError("");
    setChatNotice("");
    setBusy(true);
    try {
      const response = await answerIntake(intakeId, { answers: splitLines(answers) }, { timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS });
      const nextQuestions = asStringArray(response.questions);
      setQuestions(nextQuestions);
      setPlan(response.plan || null);
      setTaskChain(response.task_chain || null);
      setExecutionPlanPreview(null);
      setExecutionPlanPreviewError("");
      setEffectiveBrowserPolicy(response.effective_browser_policy ?? effectiveBrowserPolicy);
      setChatNotice(nextQuestions.length > 0 ? `Answer saved. ${nextQuestions.length} clarifiers remaining.` : "Key details are complete. Keep chatting or type /run.");
    } catch (cause) {
      setError(sanitizeErrorMessage(cause, "Generate plan failed"));
      setChatNotice("");
    } finally {
      setBusy(false);
    }
  }, [
    intakeId,
    chatBusy,
    busy,
    setError,
    setChatNotice,
    setBusy,
    answers,
    setQuestions,
    setPlan,
    setTaskChain,
    setEffectiveBrowserPolicy,
    effectiveBrowserPolicy,
  ]);

  const handlePreview = useCallback(async () => {
    if (chatBusy || busy || executionPlanPreviewBusy) {
      return;
    }
    setError("");
    setExecutionPlanPreviewError("");
    setExecutionPlanPreviewBusy(true);
    try {
      const payload = {
        ...buildIntakePayload(objective),
        answers: splitLines(answers),
      };
      const response = await previewIntake(payload, { timeoutMs: PM_INTAKE_REQUEST_TIMEOUT_MS });
      setExecutionPlanPreview(response);
      setChatNotice("Flight Plan ready. Review the predicted contract, gates, and output surface before starting execution.");
    } catch (cause) {
      setExecutionPlanPreview(null);
      setExecutionPlanPreviewError(sanitizeErrorMessage(cause, "Flight Plan preview failed"));
    } finally {
      setExecutionPlanPreviewBusy(false);
    }
  }, [
    chatBusy,
    busy,
    executionPlanPreviewBusy,
    setError,
    setExecutionPlanPreviewError,
    setExecutionPlanPreviewBusy,
    buildIntakePayload,
    objective,
    answers,
    setExecutionPlanPreview,
    setChatNotice,
  ]);

  const handleChatSend = useCallback(async () => {
    await runChatSendFlow({
      chatInput,
      chatFlowBusy,
      intakeId,
      runId,
      activeChatSessionId,
      questions,
      effectiveBrowserPolicy,
      chatAbortRef,
      buildIntakePayload,
      syncIntakeResult,
      moveDraftChatToSession,
      appendChat,
      refreshSessionHistory: () => {
        void refreshSessionHistory();
      },
      setObjective,
      setRunId,
      setQuestions,
      setPlan,
      setTaskChain,
      setEffectiveBrowserPolicy,
      setChatInput,
      setChatBusy,
      setChatError,
      setChatNotice,
      logError: (message) => {
        console.error(`${message} (intake=${intakeId || "-"}, run=${runId || "-"})`);
      },
    });
  }, [
    chatInput,
    chatFlowBusy,
    intakeId,
    runId,
    activeChatSessionId,
    questions,
    effectiveBrowserPolicy,
    chatAbortRef,
    buildIntakePayload,
    syncIntakeResult,
    moveDraftChatToSession,
    appendChat,
    refreshSessionHistory,
    setObjective,
    setRunId,
    setQuestions,
    setPlan,
    setTaskChain,
    setEffectiveBrowserPolicy,
    setChatInput,
    setChatBusy,
    setChatError,
    setChatNotice,
  ]);

  const handleStartNewConversation = useCallback(async () => {
    if (newConversationInFlightRef.current || state.newConversationBusy || chatFlowBusy) {
      setNewConversationNotice("New chat creation is already in progress. Please wait.");
      return;
    }
    newConversationInFlightRef.current = true;
    const txnId = newConversationTxnRef.current + 1;
    newConversationTxnRef.current = txnId;
    setNewConversationBusy(true);
    setNewConversationError("");
    setNewConversationNotice("Creating a new draft chat...");
    try {
      resetConversation();
      setSessionHistoryError("");
      setError("");
      setChatNotice("Created a local draft session. Sending the first request will persist it.");
      const ok = await Promise.race<boolean>([
        refreshSessionHistory(),
        new Promise<boolean>((resolve) => {
          setTimeout(() => resolve(false), NEW_CONVERSATION_REFRESH_TIMEOUT_MS);
        }),
      ]);
      if (newConversationTxnRef.current !== txnId) {
        return;
      }
      if (!ok) {
        setNewConversationError("Session list refresh timed out or failed, but you can still send the first request.");
        setNewConversationNotice("");
      } else {
        setNewConversationNotice("Created a local draft session. Sending the first request will persist it.");
      }
      syncSessionQueryParam("");
      state.chatInputRef.current?.focus();
    } catch (cause) {
      if (newConversationTxnRef.current !== txnId) {
        return;
      }
      setNewConversationError(sanitizeErrorMessage(cause, "Failed to create a new chat"));
      setNewConversationNotice("");
    } finally {
      if (newConversationTxnRef.current === txnId) {
        setNewConversationBusy(false);
        newConversationInFlightRef.current = false;
      }
    }
  }, [
    newConversationInFlightRef,
    state.newConversationBusy,
    chatFlowBusy,
    setNewConversationNotice,
    newConversationTxnRef,
    setNewConversationBusy,
    setNewConversationError,
    resetConversation,
    setSessionHistoryError,
    setError,
    setChatNotice,
    refreshSessionHistory,
    state.chatInputRef,
  ]);

  const handleSessionSelect = useCallback(
    (sessionId: string) => {
      const normalizedSessionId = sessionId.trim();
      if (!normalizedSessionId) {
        return;
      }
      if (normalizedSessionId === intakeId) {
        setChatNotice(`Already in session ${sessionId}`);
        return;
      }
      if (sessionSwitchInFlightRef.current === normalizedSessionId) {
        return;
      }
      const hasSessionInHistory = sessionHistory.some((item) => item.pm_session_id === normalizedSessionId);
      if (!hasSessionInHistory) {
        setChatError("Session is stale. Refresh and try again.");
        setChatNotice("Session list updated. Refreshing now.");
        void refreshSessionHistory();
        return;
      }
      sessionSwitchInFlightRef.current = normalizedSessionId;
      rotateSessionRequestGuard(normalizedSessionId);
      setIntakeId(normalizedSessionId);
      setRunId("");
      setPlan(null);
      setTaskChain(null);
      setExecutionPlanPreview(null);
      setExecutionPlanPreviewError("");
      setEffectiveBrowserPolicy(null);
      setLiveRole("");
      setProgressFeed([]);
      setQuestions([]);
      setChatError("");
      setChatNotice(`Switching to session ${normalizedSessionId}...`);
      syncSessionQueryParam(normalizedSessionId);
      void hydrateSessionContext(normalizedSessionId)
        .then((ok) => {
          if (activeSessionRef.current !== normalizedSessionId) {
            return;
          }
          if (ok) {
            setChatNotice(`Switched to session ${normalizedSessionId}`);
            return;
          }
          setChatError("Failed to load session details. Please retry.");
          setChatNotice(`Failed to switch to session ${normalizedSessionId}. Please retry.`);
          void refreshSessionHistory();
        })
        .finally(() => {
          if (sessionSwitchInFlightRef.current === normalizedSessionId) {
            sessionSwitchInFlightRef.current = "";
          }
        });
    },
    [
      intakeId,
      sessionHistory,
      rotateSessionRequestGuard,
      setIntakeId,
      setRunId,
      setPlan,
      setTaskChain,
      setEffectiveBrowserPolicy,
      setLiveRole,
      setProgressFeed,
      setQuestions,
      setChatError,
      setChatNotice,
      hydrateSessionContext,
      activeSessionRef,
      refreshSessionHistory,
    ],
  );

  useEffect(() => {
    if (sessionSwitchInFlightRef.current && sessionSwitchInFlightRef.current === intakeId) {
      // keep in-flight id until hydration settles
      return;
    }
    if (!sessionSwitchInFlightRef.current) {
      return;
    }
    if (activeSessionRef.current !== sessionSwitchInFlightRef.current) {
      sessionSwitchInFlightRef.current = "";
    }
  }, [intakeId, activeSessionRef]);

  return {
    refreshSessionHistory,
    buildIntakePayload,
    syncIntakeResult,
    handlePreview,
    handleRun,
    handleCreate,
    handleAnswer,
    handleChatSend,
    handleStartNewConversation,
    handleSessionSelect,
  };
}
