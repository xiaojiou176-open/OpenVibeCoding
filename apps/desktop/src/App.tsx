import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FolderGit2, GitBranch } from "lucide-react";
import { Toaster, toast } from "sonner";
import { getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import {
  detectPreferredUiLocale,
  persistPreferredUiLocale,
  toggleUiLocale,
} from "@cortexpilot/frontend-shared/uiLocale";
import { Button } from "./components/ui/Button";
import { AppSidebar } from "./components/layout/AppSidebar";
import { useDesktopData } from "./hooks/useDesktopData";
import { resolveHotkey } from "./hotkeys";
import { createIntake, fetchTaskPacks, postDesktopPmMessage, type DesktopSessionSummary } from "./lib/api";
import {
  GENERAL_TASK_TEMPLATE,
  buildTaskPackTemplatePayload,
  findTaskPackByTemplate,
  mergeTaskPackFieldStateByTemplate,
  type ExecutionPlanReport,
  type JsonValue,
  type TaskPackManifest,
} from "./lib/types";
import { sanitizeUiError } from "./lib/uiError";
import { trackPmSendAttempt, trackPmSendBlocked, trackPmStarterPromptUsed } from "./lib/uxTelemetry";
import {
  PM_PHASES,
  WORKSPACES,
  createSeedTimeline,
  nextLayoutMode,
  type ChatMessage,
  type LayoutMode,
} from "./lib/desktopUi";
import { PmShellContent } from "./features/pm-shell/PmShellContent";
import {
  CHAIN_PANEL_IDLE_DELAY_MS,
  COMPOSER_MAX_CHARS,
  DRAFT_SAVE_INTERVAL_MS,
  FIRST_SESSION_ALLOWED_PATHS,
  ONBOARDING_STORAGE_KEY,
  SCROLL_FOLLOW_THRESHOLD_PX,
  draftStorageKey,
  isAbortRequestError,
  isTimeoutRequestError,
} from "./features/pm-shell/constants";
import { getDesktopPageTitle, renderDesktopPage, type DesktopPageKey } from "./features/pm-shell/desktopPages";
import { previewIntake } from "./lib/api";
import {
  buildComposerPlaceholder,
  buildPmChainGraph,
  buildSendDisabledReason,
  getStarterPrompts,
} from "./features/pm-shell/viewModel";

export type { DesktopPageKey } from "./features/pm-shell/desktopPages";

function App() {
  // ── Navigation ──
  const [activePage, setActivePage] = useState<DesktopPageKey>("pm");
  const [detailRunId, setDetailRunId] = useState("");
  const [detailWorkflowId, setDetailWorkflowId] = useState("");
  const [detailSessionId, setDetailSessionId] = useState("");

  // ── PM state (kept from original) ──
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(WORKSPACES[0]?.id ?? null);
  const [activeSessionId, setActiveSessionId] = useState("");
  const [composerInput, setComposerInput] = useState("");
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("dialog");
  const [drawerVisible, setDrawerVisible] = useState(true);
  const [drawerPinned, setDrawerPinned] = useState(true);
  const [chainDisplayMode, setChainDisplayMode] = useState<"compact" | "detail">("detail");
  const [selectedNodeId, setSelectedNodeId] = useState<string>("pm");
  const [nodeDrawerOpen, setNodeDrawerOpen] = useState(false);
  const [showRawNodeOutput, setShowRawNodeOutput] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<"pending" | "accepted" | "rework">("pending");
  const [diffViewerOpen, setDiffViewerOpen] = useState(false);
  const [criticalBlocker, setCriticalBlocker] = useState<{ title: string; description: string } | null>(null);
  const [recoverableDraft, setRecoverableDraft] = useState<{ key: string; value: string } | null>(null);
  const [isUserNearBottom, setIsUserNearBottom] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const [timelineBySession, setTimelineBySession] = useState<Record<string, ChatMessage[]>>({});
  const [generationSessionId, setGenerationSessionId] = useState("");
  const [phaseText, setPhaseText] = useState<(typeof PM_PHASES)[number]>("Understanding the request...");
  const [streamingText, setStreamingText] = useState("");
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [onboardingVisible, setOnboardingVisible] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [sessionUpdatedAt, setSessionUpdatedAt] = useState<Record<string, number>>({});
  const [isOffline, setIsOffline] = useState(typeof navigator !== "undefined" ? !navigator.onLine : false);
  const [chainPanelReady, setChainPanelReady] = useState(false);
  const [nonPmStylesReady, setNonPmStylesReady] = useState(false);
  const [creatingFirstSession, setCreatingFirstSession] = useState(false);
  const [firstSessionBootstrapError, setFirstSessionBootstrapError] = useState("");
  const [pendingBootstrapSessionId, setPendingBootstrapSessionId] = useState("");
  const [taskPacks, setTaskPacks] = useState<TaskPackManifest[]>([]);
  const [taskPacksLoading, setTaskPacksLoading] = useState(false);
  const [taskPacksError, setTaskPacksError] = useState("");
  const [taskTemplate, setTaskTemplate] = useState<string>(GENERAL_TASK_TEMPLATE);
  const [taskPackFieldValuesByTemplate, setTaskPackFieldValuesByTemplate] = useState<Record<string, Record<string, string>>>({});
  const [executionPlanPreview, setExecutionPlanPreview] = useState<ExecutionPlanReport | null>(null);
  const [executionPlanPreviewLoading, setExecutionPlanPreviewLoading] = useState(false);
  const [executionPlanPreviewError, setExecutionPlanPreviewError] = useState("");
  const [uiLocale, setUiLocale] = useState<UiLocale>("en");

  const phaseTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pendingRequestRef = useRef<{ requestId: number; sessionId: string; controller: AbortController } | null>(null);
  const requestSequenceRef = useRef(0);
  const userStoppedRequestIdsRef = useRef<Set<number>>(new Set());
  const pendingReplyRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamClearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messageIdRef = useRef(2);
  const alertDigestRef = useRef("");
  const chatThreadRef = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const chainPanelRef = useRef<HTMLElement | null>(null);
  const criticalDialogRef = useRef<HTMLDivElement | null>(null);
  const criticalDialogPrevFocusRef = useRef<HTMLElement | null>(null);
  const createConversationRef = useRef<() => void>(() => {});
  const previousTimelineLengthRef = useRef(0);
  const hasPlayedActionSoundRef = useRef(false);
  const nonPmStylesLoaderRef = useRef<Promise<unknown> | null>(null);

  const isChainPopout = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("chain-popout") === "1";
  }, []);

  const liveErrorActivePage = useMemo<"overview" | "sessions" | "gates">(() => {
    if (activePage === "overview") {
      return "overview";
    }
    if (activePage === "pm") {
      return "overview";
    }
    if (activePage === "change-gates") {
      return "gates";
    }
    if (activePage === "command-tower" || activePage === "ct-session-detail") {
      return "sessions";
    }
    return "sessions";
  }, [activePage]);

  const { overviewMetrics, sessions, alerts, liveError, refreshNow } = useDesktopData(liveErrorActivePage);

  // ── Navigation handlers ──
  const navigate = useCallback((page: DesktopPageKey) => { setActivePage(page); }, []);
  const navigateToRun = useCallback((runId: string) => { setDetailRunId(runId); setActivePage("run-detail"); }, []);
  const navigateToWorkflow = useCallback((wfId: string) => { setDetailWorkflowId(wfId); setActivePage("workflow-detail"); }, []);
  const navigateToSession = useCallback((sid: string) => { setDetailSessionId(sid); setActivePage("ct-session-detail"); }, []);

  // ── Effects (from original) ──
  useEffect(() => {
    if (typeof window === "undefined") return;
    setOnboardingVisible(window.localStorage.getItem(ONBOARDING_STORAGE_KEY) !== "1");
  }, []);

  useEffect(() => {
    setUiLocale(detectPreferredUiLocale());
  }, []);

  useEffect(() => { const t = window.setInterval(() => setNowMs(Date.now()), 60_000); return () => window.clearInterval(t); }, []);
  useEffect(() => {
    if (isChainPopout) {
      setChainPanelReady(true);
      return;
    }
    if (activePage !== "pm" || layoutMode === "focus" || chainPanelReady) return;
    if (typeof window.requestIdleCallback === "function") {
      const idle = window.requestIdleCallback(() => setChainPanelReady(true), { timeout: 1200 });
      return () => window.cancelIdleCallback(idle);
    }
    const timer = window.setTimeout(() => setChainPanelReady(true), CHAIN_PANEL_IDLE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [activePage, chainPanelReady, isChainPopout, layoutMode]);

  useEffect(() => {
    if (activePage === "pm" || nonPmStylesReady) return;
    if (!nonPmStylesLoaderRef.current) {
      nonPmStylesLoaderRef.current = import("./styles.non-pm.css");
    }
    void nonPmStylesLoaderRef.current.then(() => setNonPmStylesReady(true));
  }, [activePage, nonPmStylesReady]);

  const playTone = useCallback((kind: "critical" | "action") => {
    if (!soundEnabled || typeof window === "undefined") return;
    const Ctor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return;
    try { const ctx = new Ctor(); const osc = ctx.createOscillator(); const g = ctx.createGain(); osc.type = "sine"; osc.frequency.value = kind === "critical" ? 840 : 520; g.gain.value = 0.03; osc.connect(g); g.connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + (kind === "critical" ? 0.22 : 0.16)); setTimeout(() => void ctx.close(), 300); } catch (e) { console.debug("playTone failed:", e); }
  }, [soundEnabled]);

  const workspace = useMemo(() => WORKSPACES.find((w) => w.id === activeWorkspaceId) ?? null, [activeWorkspaceId]);
  const uiCopy = useMemo(() => getUiCopy(uiLocale), [uiLocale]);
  const selectedTaskPack = useMemo(() => findTaskPackByTemplate(taskPacks, taskTemplate), [taskPacks, taskTemplate]);
  const taskPackFieldValues = taskPackFieldValuesByTemplate[taskTemplate] || {};
  const activeDraftKey = useMemo(() => (!workspace || !activeSessionId) ? "" : draftStorageKey(workspace.id, activeSessionId), [workspace, activeSessionId]);
  const sessionItems = useMemo<DesktopSessionSummary[]>(() => sessions, [sessions]);

  const setTaskPackFieldValue = useCallback((fieldId: string, value: string) => {
    setTaskPackFieldValuesByTemplate((previous) => ({
      ...previous,
      [taskTemplate]: {
        ...(previous[taskTemplate] || {}),
        [fieldId]: value,
      },
    }));
  }, [taskTemplate]);

  useEffect(() => {
    if (sessionItems.length === 0) {
      if (pendingBootstrapSessionId) {
        setActiveSessionId(pendingBootstrapSessionId);
        setTimelineBySession((p) => p[pendingBootstrapSessionId] ? p : { ...p, [pendingBootstrapSessionId]: createSeedTimeline(pendingBootstrapSessionId) });
        return;
      }
      setActiveSessionId("");
      return;
    }
    if (pendingBootstrapSessionId && sessionItems.some((s) => s.pm_session_id === pendingBootstrapSessionId)) {
      setPendingBootstrapSessionId("");
    }
    setFirstSessionBootstrapError("");
    setActiveSessionId((p) => sessionItems.some((s) => s.pm_session_id === p) ? p : sessionItems[0]?.pm_session_id ?? p);
    setTimelineBySession((p) => { const n = { ...p }; for (const s of sessionItems) { if (!n[s.pm_session_id]) n[s.pm_session_id] = createSeedTimeline(s.pm_session_id); } return n; });
  }, [sessionItems, pendingBootstrapSessionId]);

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
      } catch (error) {
        if (cancelled) return;
        setTaskPacks([]);
        setTaskPacksError(sanitizeUiError(error, "Task packs unavailable"));
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
  }, []);

  // Alert injection
  useEffect(() => {
    if (alerts.length === 0 || !activeSessionId) return;
    const critical = alerts.filter((a) => String(a.severity || "").toLowerCase() === "critical");
    if (critical.length === 0) return;
    const digest = critical.map((a) => `${a.code || "code"}:${a.message || "message"}`).join("|");
    if (digest === alertDigestRef.current) return;
    alertDigestRef.current = digest;
    const c = critical[0];
    const msg = sanitizeUiError(c.message || "", "A critical policy gate failed");
    appendMessage(activeSessionId, { role: "pm", content: "A critical gate issue was detected. Auto-merge is paused until you make the next decision.", embeds: [{ id: `alert-${Date.now()}`, kind: "alert", linkedNodeId: "gate", title: c.code || "CRITICAL GATE", level: "critical", description: msg, action: "Review the failure details before deciding whether to retry or roll back." }] });
    setCriticalBlocker({ title: c.code || "CRITICAL GATE", description: msg });
    playTone("critical");
    toast.error("A CRITICAL gate alert was added to the conversation");
  }, [alerts, activeSessionId, playTone]);

  // Escape critical blocker
  const closeCriticalBlocker = useCallback(() => {
    setCriticalBlocker(null);
    setReviewDecision("rework");
  }, []);

  const getCriticalDialogFocusable = useCallback((): HTMLElement[] => {
    if (!criticalDialogRef.current) {
      return [];
    }
    return Array.from(
      criticalDialogRef.current.querySelectorAll<HTMLElement>(
        'button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
      ),
    ).filter((item) => !item.hasAttribute("disabled"));
  }, []);

  useEffect(() => {
    if (!criticalBlocker) {
      return;
    }
    if (!criticalDialogPrevFocusRef.current) {
      criticalDialogPrevFocusRef.current = document.activeElement as HTMLElement | null;
    }
    const moveFocusInsideDialog = () => {
      const focusables = getCriticalDialogFocusable();
      if (focusables.length > 0 && !criticalDialogRef.current?.contains(document.activeElement)) {
        focusables[0]?.focus();
      } else if (focusables.length === 0) {
        criticalDialogRef.current?.focus();
      }
    };
    moveFocusInsideDialog();
    const focusSyncFrame = window.requestAnimationFrame(() => {
      moveFocusInsideDialog();
    });
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeCriticalBlocker();
        return;
      }
      if (e.key !== "Tab" || !criticalDialogRef.current) {
        return;
      }
      const tabbables = getCriticalDialogFocusable();
      if (tabbables.length === 0) {
        e.preventDefault();
        criticalDialogRef.current.focus();
        return;
      }
      const first = tabbables[0];
      const last = tabbables[tabbables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const activeInside = Boolean(active && criticalDialogRef.current.contains(active));
      if (!activeInside) {
        e.preventDefault();
        (e.shiftKey ? last : first)?.focus();
        return;
      }
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    const onFocusIn = (event: FocusEvent) => {
      const target = event.target as Node | null;
      if (!criticalDialogRef.current || !target) {
        return;
      }
      if (!criticalDialogRef.current.contains(target)) {
        moveFocusInsideDialog();
      }
    };
    window.addEventListener("keydown", h);
    window.addEventListener("focusin", onFocusIn);
    return () => {
      window.cancelAnimationFrame(focusSyncFrame);
      window.removeEventListener("keydown", h);
      window.removeEventListener("focusin", onFocusIn);
      const previous = criticalDialogPrevFocusRef.current;
      if (previous && document.contains(previous)) {
        previous.focus();
      }
      criticalDialogPrevFocusRef.current = null;
    };
  }, [criticalBlocker, closeCriticalBlocker, getCriticalDialogFocusable]);

  // Draft recovery
  useEffect(() => {
    if (!activeDraftKey || typeof window === "undefined") { setRecoverableDraft(null); return; }
    const saved = window.localStorage.getItem(activeDraftKey);
    if (!saved || saved.trim().length === 0 || saved === composerInput) { setRecoverableDraft(null); return; }
    setRecoverableDraft({ key: activeDraftKey, value: saved });
  }, [activeDraftKey, composerInput]);

  // Draft save
  useEffect(() => {
    if (!activeDraftKey || typeof window === "undefined") return;
    if (composerInput.trim().length === 0) { window.localStorage.removeItem(activeDraftKey); return; }
    const persist = () => window.localStorage.setItem(activeDraftKey, composerInput);
    persist();
    const t = window.setInterval(persist, DRAFT_SAVE_INTERVAL_MS);
    return () => { window.clearInterval(t); persist(); };
  }, [activeDraftKey, composerInput]);

  // Keyboard shortcuts
  useEffect(() => {
    const h = (event: KeyboardEvent) => {
      if (criticalBlocker) return;
      const isCommandTowerPageAltShift = activePage === "command-tower" && event.altKey && event.shiftKey && !event.metaKey && !event.ctrlKey;
      const isCtSessionPageAlt = activePage === "ct-session-detail" && event.altKey && !event.metaKey && !event.ctrlKey;
      if (isCommandTowerPageAltShift || isCtSessionPageAlt) {
        return;
      }
      const action = resolveHotkey(event, ["overview", "sessions", "gates", "review", "settings"]);
      if (action.kind === "none") return;
      const target = event.target as HTMLElement | null;
      const editable = target?.isContentEditable || ["textarea", "input", "select"].includes(target?.tagName?.toLowerCase() || "");
      const metaSafe = action.kind === "toggle_layout_mode" || action.kind === "open_chain_popout" || action.kind === "focus_input";
      if (editable && !metaSafe) return;
      event.preventDefault();
      if (action.kind === "new_conversation") { createConversationRef.current(); return; }
      if (action.kind === "open_search") { navigate("search"); return; }
      if (action.kind === "focus_input") { navigate("pm"); composerRef.current?.focus(); return; }
      if (action.kind === "focus_chain") { navigate("pm"); setLayoutMode("chain"); chainPanelRef.current?.focus(); return; }
      if (action.kind === "toggle_sidebar") return; // sidebar is always visible now
      if (action.kind === "switch_recent_session") { const s = sessionItems[action.index]; if (s) { setActiveSessionId(s.pm_session_id); navigate("pm"); } return; }
      if (action.kind === "refresh") { refreshNow(); toast.success("Live refresh triggered"); return; }
      if (action.kind === "toggle_drawer") { setDrawerVisible((v) => !v); return; }
      if (action.kind === "toggle_pin") { setDrawerPinned((v) => !v); return; }
      if (action.kind === "toggle_layout_mode") { setLayoutMode((v) => nextLayoutMode(v)); return; }
      if (action.kind === "open_chain_popout") { window.open(`${window.location.pathname}?chain-popout=1`, "_blank", "width=980,height=760"); toast("Command Chain opened in a separate window"); return; }
      if (action.kind === "set_page") {
        if (action.page === "overview") navigate("overview");
        if (action.page === "sessions") navigate("pm");
        if (action.page === "gates") navigate("change-gates");
        if (action.page === "review") navigate("reviews");
        if (action.page === "settings") navigate("policies");
        return;
      }
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [activePage, criticalBlocker, refreshNow, sessionItems, navigate]);

  // Network
  useEffect(() => { const sync = () => setIsOffline(!navigator.onLine); window.addEventListener("online", sync, { passive: true }); window.addEventListener("offline", sync, { passive: true }); return () => { window.removeEventListener("online", sync); window.removeEventListener("offline", sync); }; }, []);

  // Scroll
  function scrollChatToBottom(behavior: ScrollBehavior = "auto") { const n = chatThreadRef.current; if (!n) return; n.scrollTo ? n.scrollTo({ top: n.scrollHeight, behavior }) : (n.scrollTop = n.scrollHeight); }
  useEffect(() => { setUnreadCount(0); setIsUserNearBottom(true); previousTimelineLengthRef.current = (timelineBySession[activeSessionId] || []).length; requestAnimationFrame(() => scrollChatToBottom("auto")); }, [activeSessionId]);
  useEffect(() => { const n = chatThreadRef.current; if (!n) return; const h = () => { const d = n.scrollHeight - n.scrollTop - n.clientHeight; const near = d < SCROLL_FOLLOW_THRESHOLD_PX; setIsUserNearBottom(near); if (near) setUnreadCount(0); }; n.addEventListener("scroll", h, { passive: true }); return () => n.removeEventListener("scroll", h); }, [activeSessionId]);

  const activeTimeline = timelineBySession[activeSessionId] || [];
  useEffect(() => { const cl = activeTimeline.length; const pl = previousTimelineLengthRef.current; if (cl > pl && !isUserNearBottom) setUnreadCount((c) => c + (cl - pl)); previousTimelineLengthRef.current = cl; if (isUserNearBottom) requestAnimationFrame(() => scrollChatToBottom("smooth")); }, [activeTimeline.length, isUserNearBottom, streamingText]);
  useEffect(() => {
    return () => {
      if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
      if (pendingRequestRef.current) {
        pendingRequestRef.current.controller.abort();
        pendingRequestRef.current = null;
      }
      if (pendingReplyRef.current) {
        clearTimeout(pendingReplyRef.current);
        pendingReplyRef.current = null;
      }
      if (streamClearTimerRef.current) {
        clearTimeout(streamClearTimerRef.current);
        streamClearTimerRef.current = null;
      }
    };
  }, []);

  const hasActiveGeneration = generationSessionId.length > 0 || isSendingMessage;
  const activeSessionGenerating = generationSessionId === activeSessionId;
  const hasPendingDecision = activeTimeline.some((m) => (m.embeds || []).some((e) => e.kind === "decision" && !e.selected));

  useEffect(() => { if (hasPendingDecision && !hasPlayedActionSoundRef.current) { playTone("action"); hasPlayedActionSoundRef.current = true; return; } if (!hasPendingDecision) hasPlayedActionSoundRef.current = false; }, [hasPendingDecision, playTone]);

  const messageAnchorByNode = useMemo(() => { const a: Record<string, string | undefined> = {}; for (const m of activeTimeline) { for (const e of m.embeds || []) { if (!a[e.linkedNodeId]) a[e.linkedNodeId] = m.id; } if (m.role === "pm") a.pm = m.id; } return a; }, [activeTimeline]);

  // Chain graph
  const chainGraph = useMemo(
    () => buildPmChainGraph({ alerts, activeSessionGenerating, phaseText, selectedNodeId }),
    [alerts, activeSessionGenerating, phaseText, selectedNodeId]
  );

  const composerPlaceholder = useMemo(
    () =>
      buildComposerPlaceholder({
        hasWorkspace: Boolean(workspace),
        activeSessionId,
        hasActiveGeneration,
        hasPendingDecision,
        activeTimelineLength: activeTimeline.length,
      }),
    [workspace, activeSessionId, hasActiveGeneration, hasPendingDecision, activeTimeline.length]
  );

  const composerLength = composerInput.length;
  const composerOverLimit = composerLength > COMPOSER_MAX_CHARS;
  const starterPrompts = useMemo(() => getStarterPrompts(), []);
  const sendDisabledReason = useMemo(
    () =>
      buildSendDisabledReason({
        hasWorkspace: Boolean(workspace),
        activeSessionId,
        isOffline,
        hasActiveGeneration,
        composerOverLimit,
        composerInput,
        composerMaxChars: COMPOSER_MAX_CHARS,
      }),
    [workspace, activeSessionId, isOffline, hasActiveGeneration, composerOverLimit, composerInput]
  );
  const canSend = sendDisabledReason === null;

  function autoResizeComposer() { const i = composerRef.current; if (!i) return; i.style.height = "auto"; i.style.height = `${Math.max(96, Math.min(i.scrollHeight, 220))}px`; }
  useEffect(() => { autoResizeComposer(); }, [composerInput]);
  useEffect(() => {
    if (activePage !== "pm" || !workspace || !activeSessionId || hasActiveGeneration) return;
    composerRef.current?.focus();
  }, [activePage, workspace, activeSessionId, hasActiveGeneration]);

  function nextMessageId(prefix: string): string { const v = messageIdRef.current; messageIdRef.current += 1; return `${prefix}-${v}`; }
  function appendMessage(sessionId: string, message: Omit<ChatMessage, "id">) {
    setTimelineBySession((p) => ({ ...p, [sessionId]: [...(p[sessionId] || createSeedTimeline(sessionId)), { id: nextMessageId(message.role), ...message }] }));
    setSessionUpdatedAt((p) => ({ ...p, [sessionId]: Date.now() }));
  }
  function chooseDecision(messageId: string, embedId: string, optionId: string) {
    setTimelineBySession((p) => { const cur = p[activeSessionId] || []; return { ...p, [activeSessionId]: cur.map((m) => m.id !== messageId || !m.embeds ? m : { ...m, embeds: m.embeds.map((e) => (e.kind !== "decision" || e.id !== embedId) ? e : { ...e, selected: optionId }) }) }; });
    const sel = activeTimeline.flatMap((m) => m.embeds || []).find((e) => e.kind === "decision" && e.id === embedId);
    const opt = sel && sel.kind === "decision" ? sel.options.find((o) => o.id === optionId) : undefined;
    appendMessage(activeSessionId, { role: "pm", content: `Decision received: ${opt?.title || optionId}. I will continue with that path.` });
  }

  function handleReportAccept() { setReviewDecision("accepted"); appendMessage(activeSessionId, { role: "pm", content: "Decision recorded: accept and merge. Moving into pre-release verification." }); toast.success("Moved into the pre-merge verification flow"); }
  function handleReportRework() { setReviewDecision("rework"); appendMessage(activeSessionId, { role: "pm", content: "Decision recorded: request changes. The TL will reassign and report back." }); toast("Moved back into the revision flow"); }
  function restoreDraft() { if (!recoverableDraft) return; setComposerInput(recoverableDraft.value); setRecoverableDraft(null); toast.success("Draft restored"); }
  function discardDraft() { if (!recoverableDraft || typeof window === "undefined") return; window.localStorage.removeItem(recoverableDraft.key); setRecoverableDraft(null); toast("Draft discarded"); }
  function dismissOnboarding() { if (typeof window !== "undefined") window.localStorage.setItem(ONBOARDING_STORAGE_KEY, "1"); setOnboardingVisible(false); }

  async function sendMessage() {
    const trimmedInput = composerInput.trim();
    trackPmSendAttempt({
      sessionId: activeSessionId,
      workspaceId: workspace?.id ?? null,
      isOffline,
      hasActiveGeneration,
      composerLength: composerInput.length,
      isEmpty: trimmedInput.length === 0,
      isOverLimit: composerOverLimit,
    });
    if (!workspace) {
      trackPmSendBlocked({ sessionId: activeSessionId, workspaceId: null, reason: "workspace_missing" });
      toast.error("Choose a workspace before sending a message.");
      return;
    }
    if (!activeSessionId) {
      trackPmSendBlocked({ sessionId: activeSessionId, workspaceId: workspace.id, reason: "session_missing" });
      toast.error("Create the first session in desktop first. If that fails, open Dashboard /pm and create it manually.");
      return;
    }
    if (isOffline) {
      trackPmSendBlocked({ sessionId: activeSessionId, workspaceId: workspace.id, reason: "offline" });
      toast.error("Reconnect before sending a message.");
      return;
    }
    if (pendingRequestRef.current || isSendingMessage) {
      trackPmSendBlocked({ sessionId: activeSessionId, workspaceId: workspace.id, reason: "request_in_flight" });
      return;
    }
    const content = trimmedInput;
    const targetSessionId = activeSessionId;
    if (!content || hasActiveGeneration || composerOverLimit) {
      trackPmSendBlocked({
        sessionId: activeSessionId,
        workspaceId: workspace.id,
        reason: !content ? "empty_message" : hasActiveGeneration ? "generation_active" : "composer_over_limit",
      });
      if (composerOverLimit) toast.error(`Shorten the input to ${COMPOSER_MAX_CHARS} characters or fewer before sending.`);
      return;
    }
    appendMessage(targetSessionId, { role: "user", content });
    setComposerInput(""); if (activeDraftKey && typeof window !== "undefined") window.localStorage.removeItem(activeDraftKey);
    if (streamClearTimerRef.current) {
      clearTimeout(streamClearTimerRef.current);
      streamClearTimerRef.current = null;
    }
    setUnreadCount(0); setGenerationSessionId(targetSessionId); setPhaseText(PM_PHASES[0]); setStreamingText("");
    setIsSendingMessage(true);
    const controller = new AbortController();
    const requestId = requestSequenceRef.current + 1;
    requestSequenceRef.current = requestId;
    pendingRequestRef.current = { requestId, sessionId: targetSessionId, controller };
    if (phaseTimerRef.current) clearInterval(phaseTimerRef.current);
    if (pendingReplyRef.current) { clearTimeout(pendingReplyRef.current); pendingReplyRef.current = null; }
    let phaseIndex = 0;
    phaseTimerRef.current = setInterval(() => { phaseIndex = (phaseIndex + 1) % PM_PHASES.length; setPhaseText(PM_PHASES[phaseIndex]); }, 1200);
    pendingReplyRef.current = setTimeout(() => { pendingReplyRef.current = null; }, 60000);
    try {
      const res = await postDesktopPmMessage(targetSessionId, { message: content, strict_acceptance: true }, controller.signal);
      const pmMsg = res.message || "The TL finished decomposition and the workers are now executing.";
      setStreamingText(pmMsg); setReviewDecision("pending");
      appendMessage(targetSessionId, { role: "pm", content: "Request received. I am handing it to the TL for breakdown and execution.", embeds: [{ id: `delegation-${Date.now()}`, kind: "delegation", linkedNodeId: "tl", title: "Delegated to Tech Lead", task: content, plan: "Break the work into Backend / Frontend / Reviewer lanes and run them in parallel", status: "TL is analyzing..." }] });
      appendMessage(targetSessionId, { role: "pm", content: pmMsg });
      toast.success("The PM response was added to the session");
    } catch (error) {
      if (isAbortRequestError(error)) {
        if (!userStoppedRequestIdsRef.current.has(requestId)) {
          appendMessage(targetSessionId, { role: "pm", content: "This message send was cancelled. You can continue with a new instruction right away." });
          toast("The current send was cancelled");
        }
        return;
      }
      const fallback = isTimeoutRequestError(error) ? "Message delivery timed out" : "The backend message channel failed";
      const errorMsg = sanitizeUiError(error, fallback);
      appendMessage(targetSessionId, { role: "pm", content: "The backend message channel is temporarily unavailable, so I switched into a local safe fallback mode.", embeds: [{ id: `alert-${Date.now()}`, kind: "alert", linkedNodeId: "gate", title: "Message channel fallback", level: "warning", description: errorMsg, action: "Continue locally, or fix the API and retry." }] });
      toast.error("Continue locally, or fix the API and try sending again.");
    } finally {
      const isCurrentRequest = pendingRequestRef.current?.requestId === requestId;
      userStoppedRequestIdsRef.current.delete(requestId);
      if (!isCurrentRequest) return;
      if (phaseTimerRef.current) { clearInterval(phaseTimerRef.current); phaseTimerRef.current = null; }
      if (pendingReplyRef.current) { clearTimeout(pendingReplyRef.current); pendingReplyRef.current = null; }
      pendingRequestRef.current = null;
      setGenerationSessionId("");
      setIsSendingMessage(false);
      setPhaseText("Summarizing results...");
      if (streamClearTimerRef.current) {
        clearTimeout(streamClearTimerRef.current);
      }
      streamClearTimerRef.current = setTimeout(() => {
        if (requestSequenceRef.current !== requestId) return;
        setStreamingText("");
        streamClearTimerRef.current = null;
      }, 1200);
    }
  }

  function stopGeneration() {
    const currentRequest = pendingRequestRef.current;
    if (!currentRequest) return;
    userStoppedRequestIdsRef.current.add(currentRequest.requestId);
    currentRequest.controller.abort(); pendingRequestRef.current = null;
    if (pendingReplyRef.current) { clearTimeout(pendingReplyRef.current); pendingReplyRef.current = null; }
    if (phaseTimerRef.current) { clearInterval(phaseTimerRef.current); phaseTimerRef.current = null; }
    if (streamClearTimerRef.current) { clearTimeout(streamClearTimerRef.current); streamClearTimerRef.current = null; }
    setStreamingText("");
    setIsSendingMessage(false);
    setGenerationSessionId(""); setPhaseText("Understanding the request...");
    appendMessage(currentRequest.sessionId, { role: "pm", content: "The current generation was stopped. The existing context is preserved and you can continue with a new instruction." });
    toast("Current generation stopped");
  }

  function openSessionFallbackCta() {
    if (typeof window !== "undefined") {
      window.open(`${window.location.origin}/pm`, "_blank", "noopener,noreferrer");
    }
    toast("Create the first session manually in Dashboard /pm with objective + allowed_paths.");
  }

  function buildFirstSessionPayload(): Record<string, JsonValue> {
    const payload: Record<string, JsonValue> = {
      objective: `Create the first session in ${workspace?.repo || "workspace"}/${workspace?.branch || "branch"} and finish one smallest-possible verifiable task.`,
      allowed_paths: [...FIRST_SESSION_ALLOWED_PATHS],
    };
    if (selectedTaskPack) {
      payload.task_template = selectedTaskPack.task_template;
      payload.template_payload = buildTaskPackTemplatePayload(
        selectedTaskPack,
        taskPackFieldValuesByTemplate[selectedTaskPack.task_template] || {},
      );
      payload.objective = "";
    }
    return payload;
  }

  async function previewFirstSessionInDesktop() {
    if (!workspace) {
      toast.error("Choose a workspace before previewing the first session.");
      return;
    }
    if (isOffline) {
      toast.error("Reconnect before previewing the first session.");
      return;
    }
    setExecutionPlanPreviewLoading(true);
    setExecutionPlanPreviewError("");
    try {
      const preview = await previewIntake(buildFirstSessionPayload());
      setExecutionPlanPreview(preview);
      toast.success("Flight Plan preview refreshed.");
    } catch (error) {
      const reason = sanitizeUiError(error, "Previewing the first session failed");
      setExecutionPlanPreview(null);
      setExecutionPlanPreviewError(reason);
      toast.error("Flight Plan preview failed.");
    } finally {
      setExecutionPlanPreviewLoading(false);
    }
  }

  async function createFirstSessionInDesktop() {
    if (!workspace) {
      toast.error("Choose a workspace before clicking \"Create first session in desktop\".");
      return;
    }
    if (isOffline) {
      toast.error("Reconnect before clicking \"Create first session in desktop\".");
      return;
    }
    if (creatingFirstSession) return;
    setCreatingFirstSession(true);
    setFirstSessionBootstrapError("");
    try {
      const payload = buildFirstSessionPayload();
      const response = await createIntake(payload);
      const intakeId = typeof response.intake_id === "string" ? response.intake_id.trim() : "";
      if (!intakeId) {
        const fallback = "Open Dashboard /pm and create the first session manually with objective + allowed_paths.";
        setFirstSessionBootstrapError(fallback);
        toast.error(fallback);
        return;
      }
      setPendingBootstrapSessionId(intakeId);
      setActiveSessionId(intakeId);
      setTimelineBySession((p) => p[intakeId] ? p : { ...p, [intakeId]: createSeedTimeline(intakeId) });
      navigate("pm");
      refreshNow();
      toast.success("The first session was created in desktop. Add the objective details and send the first message.");
    } catch (error) {
      const reason = sanitizeUiError(error, "Creating the first session in desktop failed");
      setFirstSessionBootstrapError(`Open Dashboard /pm and create the first session manually with objective + allowed_paths. (${reason})`);
      toast.error("Open Dashboard /pm to continue.");
    } finally {
      setCreatingFirstSession(false);
    }
  }

  function createConversation() {
    const first = sessions[0];
    if (!first) {
      void createFirstSessionInDesktop();
      return;
    }
    setActiveSessionId(first.pm_session_id); setComposerInput(""); setRecoverableDraft(null); navigate("pm"); toast.success("Switched to the latest session. Continue by typing the next request.");
  }

  useEffect(() => {
    createConversationRef.current = createConversation;
  }, [sessions, activeWorkspaceId, creatingFirstSession, isOffline, pendingBootstrapSessionId]);

  function cycleWorkspace() { if (WORKSPACES.length === 0) return; const i = WORKSPACES.findIndex((w) => w.id === activeWorkspaceId); const n = WORKSPACES[(i + 1) % WORKSPACES.length]; if (n) { setActiveWorkspaceId(n.id); toast(`Workspace switched: ${n.repo}`); } }
  function cycleBranch() { if (!workspace) return; const c = WORKSPACES.filter((w) => w.repo === workspace.repo); if (c.length <= 1) { toast("No alternate branch is available for this workspace"); return; } const i = c.findIndex((w) => w.id === workspace.id); const n = c[(i + 1) % c.length]; if (n) { setActiveWorkspaceId(n.id); toast(`Branch switched: ${n.branch}`); } }

  const pmShellProps = {
    onboardingVisible, dismissOnboarding, isOffline, liveError, workspace, activeSessionId, activeSessionGenerating, phaseText, refreshNow,
    drawerVisible, drawerPinned, setDrawerVisible, setDrawerPinned, activeTimeline, chatThreadRef, streamingText,
    creatingFirstSession, firstSessionBootstrapError, firstSessionAllowedPath: FIRST_SESSION_ALLOWED_PATHS[0],
    taskPacks, taskPacksLoading, taskPacksError, taskTemplate, setTaskTemplate, selectedTaskPack, taskPackFieldValues, setTaskPackFieldValue,
    executionPlanPreview, executionPlanPreviewLoading, executionPlanPreviewError,
    onCreateFirstSession: () => void createFirstSessionInDesktop(), onOpenSessionFallback: openSessionFallbackCta,
    onPreviewFirstSession: () => void previewFirstSessionInDesktop(),
    chooseDecision, recoverableDraft, restoreDraft, discardDraft, composerRef, composerInput, setComposerInput,
    onComposerEnterSend: () => void sendMessage(), composerPlaceholder, composerLength, composerMaxChars: COMPOSER_MAX_CHARS,
    composerOverLimit, canSend, sendDisabledReason, starterPrompts,
    onApplyStarterPrompt: (prompt: string) => {
      trackPmStarterPromptUsed({
        promptIndex: starterPrompts.indexOf(prompt),
        promptLength: prompt.length,
        sessionId: activeSessionId,
        workspaceId: workspace?.id ?? null
      });
      setComposerInput(prompt);
      requestAnimationFrame(() => composerRef.current?.focus());
    },
    hasActiveGeneration, stopGeneration, isUserNearBottom, unreadCount,
    onBackToBottom: () => { scrollChatToBottom("smooth"); setUnreadCount(0); setIsUserNearBottom(true); },
    layoutMode, setLayoutMode, chainPanelReady, chainPanelRef, chainDisplayMode, setChainDisplayMode, chainGraph,
    selectedNodeId, setSelectedNodeId, nodeDrawerOpen, setNodeDrawerOpen, setShowRawNodeOutput, showRawNodeOutput,
    messageAnchorByNode, reviewDecision, setReviewDecision, diffViewerOpen, setDiffViewerOpen,
    onReportAccept: handleReportAccept, onReportRework: handleReportRework,
    cycleWorkspace, cycleBranch, soundEnabled, setSoundEnabled, overviewMetrics, alerts,
  };
  const pmPageContent = <PmShellContent {...pmShellProps} isChainPopout={false} />;

  // Chain popout mode
  if (isChainPopout) {
    return (
      <main className="app-body" aria-label={uiCopy.desktop.shellAriaLabel}>
        <Toaster position="bottom-right" visibleToasts={3} closeButton />
        <PmShellContent {...pmShellProps} isChainPopout />
      </main>
    );
  }

  const shouldHoldNonPmPage = activePage !== "pm" && !nonPmStylesReady;

  return (
    <main className="app-body" aria-label={uiCopy.desktop.shellAriaLabel}>
      <a className="skip-link" href="#desktop-main-content">
        {uiCopy.desktop.skipToMainContent}
      </a>
      <Toaster position="bottom-right" visibleToasts={3} closeButton />
      <div className="app-shell">
        <AppSidebar activePage={activePage} onNavigate={navigate} locale={uiLocale} />
        <div className="app-main">
          <header className="topbar" data-tauri-drag-region>
            <h1 className="topbar-title">{getDesktopPageTitle(activePage, uiLocale)}</h1>
            <div className="workspace-picker no-drag" role="group" aria-label={uiCopy.desktop.workspacePickerLabel}>
              <Button variant="secondary" className="workspace-trigger" onClick={cycleWorkspace}><FolderGit2 size={14} aria-hidden="true" />{workspace ? workspace.repo : uiCopy.desktop.selectWorkspace}</Button>
              <Button variant="ghost" className="workspace-trigger" onClick={cycleBranch}><GitBranch size={14} aria-hidden="true" />{workspace ? workspace.branch : "-"}</Button>
              <Button
                variant="ghost"
                className="workspace-trigger"
                aria-label={uiCopy.desktop.localeToggleAriaLabel}
                onClick={() => {
                  setUiLocale((previous) => {
                    const next = toggleUiLocale(previous);
                    persistPreferredUiLocale(next);
                    return next;
                  });
                }}
              >
                {uiCopy.desktop.localeToggleButtonLabel}
              </Button>
            </div>
          </header>
          <div className="app-page-content" id="desktop-main-content">
            {shouldHoldNonPmPage ? (
              <section className="chat-panel" aria-label="Page styles loading">
                <p className="shortcut-hint">{uiCopy.desktop.loadingPageStyles}</p>
              </section>
            ) : (
              <Suspense fallback={<section className="api-card"><p>{uiCopy.desktop.loadingPage}</p></section>}>
                {renderDesktopPage({
                  activePage,
                  uiLocale,
                  pmPageContent,
                  detailRunId,
                  detailWorkflowId,
                  detailSessionId,
                  navigate,
                  navigateToRun,
                  navigateToWorkflow,
                  navigateToSession,
                  setActivePage,
                })}
              </Suspense>
            )}
          </div>
        </div>
      </div>

      {/* Critical blocker overlay */}
      {criticalBlocker && (
        <div
          ref={criticalDialogRef}
          className="overlay-modal critical-blocker"
          role="dialog"
          aria-modal="true"
          aria-label="Critical blocker alert"
          tabIndex={-1}
        >
          <article className="overlay-card critical-card">
            <h2>CRITICAL GATE</h2>
            <p><strong>{criticalBlocker.title}</strong></p>
            <p>{criticalBlocker.description}</p>
            <p>Until you confirm, the system stays in review-before-merge blocker mode.</p>
            <div className="quick-actions"><Button variant="destructive" fullWidth autoFocus onClick={closeCriticalBlocker}>I understand. Move to manual adjudication.</Button></div>
          </article>
        </div>
      )}
    </main>
  );
}

export default App;
