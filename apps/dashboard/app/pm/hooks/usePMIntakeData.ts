"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { resolveDashboardPmCopyVariantEnv } from "../../../lib/env";
import type { ExecutionPlanReport, PmSessionSummary, TaskPackManifest } from "../../../lib/types";
import {
  DRAFT_SESSION_ID,
  mergeChatTimeline,
  PRIVILEGED_CUSTOM_ROLES,
  resolvePmCopyVariant,
  type BrowserPreset,
  type ChainRole,
  type ChatCardPayload,
  type ChatItem,
  type ChatItemKind,
  type ChatRole,
  type PMLayoutMode,
  type PMTaskTemplate,
} from "../components/PMIntakeFeature.shared";

const DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE: Record<string, Record<string, string>> = {
  news_digest: {
    topic: "Seattle tech and AI",
    sources: "theverge.com\ntechcrunch.com\nopenai.com/blog",
    time_range: "24h",
    max_results: "5",
  },
  topic_brief: {
    topic: "Seattle tech and AI",
    time_range: "24h",
    max_results: "5",
  },
  page_brief: {
    url: "https://example.com",
    focus: "Summarize the page for a first-time reader.",
  },
};

const DEFAULT_TASK_PACKS: TaskPackManifest[] = [
  {
    pack_id: "news_digest",
    version: "v1",
    title: "Public News Digest",
    description: "Public, read-only digest over recent sources for one topic.",
    visibility: "public",
    entry_mode: "pm_intake",
    task_template: "news_digest",
    input_fields: [
      {
        field_id: "topic",
        label: "Topic",
        control: "text",
        required: true,
        placeholder: "e.g. Seattle tech and AI",
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.topic,
      },
      {
        field_id: "sources",
        label: "Source domains",
        control: "textarea",
        required: true,
        placeholder: "theverge.com\ntechcrunch.com\nopenai.com/blog",
        help_text: "One domain per line.",
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.sources,
        value_codec: "string_list",
      },
      {
        field_id: "time_range",
        label: "Time range",
        control: "select",
        required: true,
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.time_range,
        options: [
          { value: "24h", label: "24h" },
          { value: "7d", label: "7d" },
          { value: "30d", label: "30d" },
        ],
      },
      {
        field_id: "max_results",
        label: "Max results",
        control: "number",
        required: true,
        default_value: 5,
        value_codec: "integer",
        min: 1,
        max: 10,
      },
    ],
    ui_hint: { surface_group: "public_task_templates", default_label: "Public news digest" },
    evidence_contract: { primary_report: "news_digest_result.json", requires_search_requests: true, requires_browser_requests: false },
  },
  {
    pack_id: "topic_brief",
    version: "v1",
    title: "Public Topic Brief",
    description: "Public, read-only topic brief over a bounded recent time range.",
    visibility: "public",
    entry_mode: "pm_intake",
    task_template: "topic_brief",
    input_fields: [
      {
        field_id: "topic",
        label: "Topic",
        control: "text",
        required: true,
        placeholder: "e.g. Seattle tech and AI",
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.topic_brief.topic,
      },
      {
        field_id: "time_range",
        label: "Time range",
        control: "select",
        required: true,
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.topic_brief.time_range,
        options: [
          { value: "24h", label: "24h" },
          { value: "7d", label: "7d" },
          { value: "30d", label: "30d" },
        ],
      },
      {
        field_id: "max_results",
        label: "Max results",
        control: "number",
        required: true,
        default_value: 5,
        value_codec: "integer",
        min: 1,
        max: 10,
      },
    ],
    ui_hint: { surface_group: "public_task_templates", default_label: "Public topic brief" },
    evidence_contract: { primary_report: "topic_brief_result.json", requires_search_requests: true, requires_browser_requests: false },
  },
  {
    pack_id: "page_brief",
    version: "v1",
    title: "Public Page Brief",
    description: "Public, read-only page brief for a single URL.",
    visibility: "public",
    entry_mode: "pm_intake",
    task_template: "page_brief",
    input_fields: [
      {
        field_id: "url",
        label: "Page URL",
        control: "url",
        required: true,
        placeholder: "https://example.com",
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.page_brief.url,
      },
      {
        field_id: "focus",
        label: "Focus",
        control: "textarea",
        required: true,
        placeholder: "Summarize the page for a first-time reader.",
        default_value: DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.page_brief.focus,
      },
    ],
    ui_hint: { surface_group: "public_task_templates", default_label: "Public page brief" },
    evidence_contract: { primary_report: "page_brief_result.json", requires_search_requests: false, requires_browser_requests: true },
  },
];

export function usePMIntakeData() {
  const copyVariant = resolvePmCopyVariant(resolveDashboardPmCopyVariantEnv());
  const [layoutMode, setLayoutMode] = useState<PMLayoutMode>("dialog");
  const [taskTemplate, setTaskTemplate] = useState<PMTaskTemplate>("news_digest");
  const [objective, setObjective] = useState("");
  const [allowedPaths, setAllowedPaths] = useState("");
  const [constraints, setConstraints] = useState("");
  const [searchQueries, setSearchQueries] = useState("");
  const [taskPackFieldValuesByTemplate, setTaskPackFieldValuesByTemplate] = useState<Record<string, Record<string, string>>>(
    DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE,
  );
  const [answers, setAnswers] = useState("");
  const [intakeId, setIntakeId] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [plan, setPlan] = useState<unknown>(null);
  const [taskChain, setTaskChain] = useState<unknown>(null);
  const [executionPlanPreview, setExecutionPlanPreview] = useState<ExecutionPlanReport | null>(null);
  const [executionPlanPreviewBusy, setExecutionPlanPreviewBusy] = useState(false);
  const [executionPlanPreviewError, setExecutionPlanPreviewError] = useState("");
  const [taskPacks, setTaskPacks] = useState<TaskPackManifest[]>(DEFAULT_TASK_PACKS);
  const [taskPacksLoading, setTaskPacksLoading] = useState(false);
  const [taskPacksError, setTaskPacksError] = useState("");
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [browserPreset, setBrowserPreset] = useState<BrowserPreset>("safe");
  const [requesterRole, setRequesterRole] = useState("PM");
  const [customBrowserPolicy, setCustomBrowserPolicy] = useState(
    '{\n  "profile_mode": "allow_profile",\n  "stealth_mode": "plugin",\n  "human_behavior": {\n    "enabled": true,\n    "level": "medium"\n  }\n}',
  );
  const [effectiveBrowserPolicy, setEffectiveBrowserPolicy] = useState<unknown>(null);
  const [workspacePath, setWorkspacePath] = useState("apps/dashboard");
  const [repoName, setRepoName] = useState("openvibecoding");
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState("");
  const [chatNotice, setChatNotice] = useState("");
  const [chatLogBySession, setChatLogBySession] = useState<Record<string, ChatItem[]>>({});
  const [chatHistoryBusy, setChatHistoryBusy] = useState(false);
  const [sessionHistoryError, setSessionHistoryError] = useState("");
  const [sessionHistory, setSessionHistory] = useState<PmSessionSummary[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [newConversationBusy, setNewConversationBusy] = useState(false);
  const [newConversationError, setNewConversationError] = useState("");
  const [newConversationNotice, setNewConversationNotice] = useState("");
  const [liveRole, setLiveRole] = useState("");
  const [progressFeed, setProgressFeed] = useState<string[]>([]);
  const [chatStickToBottom, setChatStickToBottom] = useState(true);
  const [chatUnreadCount, setChatUnreadCount] = useState(0);
  const [hoveredChainRole, setHoveredChainRole] = useState<ChainRole | null>(null);

  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const chatInputRef = useRef<HTMLTextAreaElement | null>(null);
  const chainPanelRef = useRef<HTMLElement | null>(null);
  const chatAbortRef = useRef<AbortController | null>(null);
  const activeSessionRef = useRef("");
  const liveSyncTokenRef = useRef(0);
  const historySyncTokenRef = useRef(0);
  const newConversationTxnRef = useRef(0);
  const newConversationInFlightRef = useRef(false);
  const lastChatLengthRef = useRef(0);

  const normalizedRequesterRole = requesterRole.trim().toUpperCase();
  const canUseCustomPreset = PRIVILEGED_CUSTOM_ROLES.has(normalizedRequesterRole);
  const activeChatSessionId = intakeId || DRAFT_SESSION_ID;
  const chatLog = chatLogBySession[activeChatSessionId] || [];
  const chatFlowBusy = busy || chatBusy;
  const workspaceBound = workspacePath.trim().length > 0 && repoName.trim().length > 0;
  const taskPackFieldValues = taskPackFieldValuesByTemplate[taskTemplate] || {};

  const updateTaskPackFieldValues = useCallback(
    (template: string, updater: (currentValues: Record<string, string>) => Record<string, string>) => {
      setTaskPackFieldValuesByTemplate((previous) => ({
        ...previous,
        [template]: updater(previous[template] || {}),
      }));
    },
    [],
  );

  const setTaskPackFieldValue = useCallback(
    (fieldId: string, value: string) => {
      updateTaskPackFieldValues(taskTemplate, (currentValues) => ({
        ...currentValues,
        [fieldId]: value,
      }));
    },
    [taskTemplate, updateTaskPackFieldValues],
  );

  const newsDigestTopic = taskPackFieldValuesByTemplate.news_digest?.topic || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.topic;
  const setNewsDigestTopic = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("news_digest", (currentValues) => ({
        ...currentValues,
        topic: value,
      }));
    },
    [updateTaskPackFieldValues],
  );
  const newsDigestSources =
    taskPackFieldValuesByTemplate.news_digest?.sources || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.sources;
  const setNewsDigestSources = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("news_digest", (currentValues) => ({
        ...currentValues,
        sources: value,
      }));
    },
    [updateTaskPackFieldValues],
  );
  const newsDigestTimeRange =
    taskPackFieldValuesByTemplate.news_digest?.time_range || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.time_range;
  const setNewsDigestTimeRange = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("news_digest", (currentValues) => ({
        ...currentValues,
        time_range: value,
      }));
    },
    [updateTaskPackFieldValues],
  );
  const newsDigestMaxResults =
    taskPackFieldValuesByTemplate.news_digest?.max_results || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.news_digest.max_results;
  const setNewsDigestMaxResults = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("news_digest", (currentValues) => ({
        ...currentValues,
        max_results: value,
      }));
    },
    [updateTaskPackFieldValues],
  );
  const pageBriefUrl =
    taskPackFieldValuesByTemplate.page_brief?.url || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.page_brief.url;
  const setPageBriefUrl = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("page_brief", (currentValues) => ({
        ...currentValues,
        url: value,
      }));
    },
    [updateTaskPackFieldValues],
  );
  const pageBriefFocus =
    taskPackFieldValuesByTemplate.page_brief?.focus || DEFAULT_TASK_PACK_FIELD_VALUES_BY_TEMPLATE.page_brief.focus;
  const setPageBriefFocus = useCallback(
    (value: string) => {
      updateTaskPackFieldValues("page_brief", (currentValues) => ({
        ...currentValues,
        focus: value,
      }));
    },
    [updateTaskPackFieldValues],
  );

  const rotateSessionRequestGuard = useCallback((nextSessionId: string) => {
    activeSessionRef.current = nextSessionId;
    historySyncTokenRef.current += 1;
    liveSyncTokenRef.current += 1;
  }, []);

  const appendChat = useCallback(
    (
      role: ChatRole,
      text: string,
      sessionId = activeChatSessionId,
      options?: { kind?: ChatItemKind; card?: ChatCardPayload; createdAt?: string; origin?: "local" | "remote" },
    ) => {
      setChatLogBySession((previous) => {
        const nextSessionLog = previous[sessionId] || [];
        return {
          ...previous,
          [sessionId]: [
            ...nextSessionLog,
            {
              id: `${sessionId}-${nextSessionLog.length + 1}-${Date.now()}`,
              role,
              text,
              createdAt: options?.createdAt || new Date().toISOString(),
              kind: options?.kind || "message",
              origin: options?.origin || "local",
              card: options?.card,
            },
          ],
        };
      });
    },
    [activeChatSessionId],
  );

  const moveDraftChatToSession = useCallback((nextSessionId: string) => {
    setChatLogBySession((previous) => {
      const draftLog = previous[DRAFT_SESSION_ID] || [];
      if (draftLog.length === 0) {
        return previous;
      }
      const next = { ...previous };
      const existing = next[nextSessionId] || [];
      next[nextSessionId] = [...existing, ...draftLog];
      delete next[DRAFT_SESSION_ID];
      return next;
    });
  }, []);

  const mergeSessionChat = useCallback((sessionId: string, remoteChatItems: ChatItem[]) => {
    setChatLogBySession((previous) => {
      const localSessionChat = previous[sessionId] || [];
      const mergedChat = mergeChatTimeline(localSessionChat, remoteChatItems);
      if (mergedChat === localSessionChat) {
        return previous;
      }
      return {
        ...previous,
        [sessionId]: mergedChat,
      };
    });
  }, []);

  const resetConversation = useCallback(() => {
    rotateSessionRequestGuard("");
    setIntakeId("");
    setRunId("");
    setQuestions([]);
    setChatInput("");
    setChatError("");
    setChatNotice("");
    setExecutionPlanPreview(null);
    setExecutionPlanPreviewError("");
    setChatLogBySession((previous) => {
      const next = { ...previous };
      delete next[DRAFT_SESSION_ID];
      return next;
    });
    setPlan(null);
    setTaskChain(null);
    setEffectiveBrowserPolicy(null);
    setLiveRole("");
    setProgressFeed([]);
    setHoveredChainRole(null);
  }, [rotateSessionRequestGuard]);

  return {
    copyVariant,
    layoutMode,
    setLayoutMode,
    taskTemplate,
    setTaskTemplate,
    objective,
    setObjective,
    allowedPaths,
    setAllowedPaths,
    constraints,
    setConstraints,
    searchQueries,
    setSearchQueries,
    taskPackFieldValuesByTemplate,
    setTaskPackFieldValuesByTemplate,
    taskPackFieldValues,
    setTaskPackFieldValue,
    newsDigestTopic,
    setNewsDigestTopic,
    newsDigestSources,
    setNewsDigestSources,
    newsDigestTimeRange,
    setNewsDigestTimeRange,
    newsDigestMaxResults,
    setNewsDigestMaxResults,
    pageBriefUrl,
    setPageBriefUrl,
    pageBriefFocus,
    setPageBriefFocus,
    answers,
    setAnswers,
    intakeId,
    setIntakeId,
    questions,
    setQuestions,
    plan,
    setPlan,
    taskChain,
    setTaskChain,
    executionPlanPreview,
    setExecutionPlanPreview,
    executionPlanPreviewBusy,
    setExecutionPlanPreviewBusy,
    executionPlanPreviewError,
    setExecutionPlanPreviewError,
    taskPacks,
    setTaskPacks,
    taskPacksLoading,
    setTaskPacksLoading,
    taskPacksError,
    setTaskPacksError,
    runId,
    setRunId,
    error,
    setError,
    busy,
    setBusy,
    browserPreset,
    setBrowserPreset,
    requesterRole,
    setRequesterRole,
    customBrowserPolicy,
    setCustomBrowserPolicy,
    effectiveBrowserPolicy,
    setEffectiveBrowserPolicy,
    workspacePath,
    setWorkspacePath,
    repoName,
    setRepoName,
    chatInput,
    setChatInput,
    chatBusy,
    setChatBusy,
    chatError,
    setChatError,
    chatNotice,
    setChatNotice,
    chatLogBySession,
    setChatLogBySession,
    chatHistoryBusy,
    setChatHistoryBusy,
    sessionHistoryError,
    setSessionHistoryError,
    sessionHistory,
    setSessionHistory,
    historyBusy,
    setHistoryBusy,
    newConversationBusy,
    setNewConversationBusy,
    newConversationError,
    setNewConversationError,
    newConversationNotice,
    setNewConversationNotice,
    liveRole,
    setLiveRole,
    progressFeed,
    setProgressFeed,
    chatStickToBottom,
    setChatStickToBottom,
    chatUnreadCount,
    setChatUnreadCount,
    hoveredChainRole,
    setHoveredChainRole,
    chatLogRef,
    chatInputRef,
    chainPanelRef,
    chatAbortRef,
    activeSessionRef,
    liveSyncTokenRef,
    historySyncTokenRef,
    newConversationTxnRef,
    newConversationInFlightRef,
    lastChatLengthRef,
    canUseCustomPreset,
    activeChatSessionId,
    chatLog,
    chatFlowBusy,
    workspaceBound,
    rotateSessionRequestGuard,
    appendChat,
    moveDraftChatToSession,
    mergeSessionChat,
    resetConversation,
  };
}
