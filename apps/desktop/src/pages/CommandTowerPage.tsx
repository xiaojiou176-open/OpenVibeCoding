import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import type { DesktopWorkMode } from "@cortexpilot/frontend-api-contract/ui-flow";
import type {
  CommandTowerOverviewPayload,
  CommandTowerAlertsPayload,
  CommandTowerAlert,
  PmSessionSummary,
  PmSessionStatus,
} from "../lib/types";
import { fetchCommandTowerOverview, fetchCommandTowerAlerts, fetchPmSessions } from "../lib/api";
import { statusLabelZh, badgeClass } from "../lib/statusPresentation";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Input, Select } from "../components/ui/Input";

/* ─── constants ─── */
const BASE_INTERVAL_MS = 1500;
const MAX_INTERVAL_MS = 8000;
const REQUEST_TIMEOUT_MS = 6000;

type LiveMode = "running" | "backoff" | "paused";
type SortMode = "updated_desc" | "created_desc" | "failed_desc" | "blocked_desc";
type FocusMode = "all" | "high_risk" | "blocked" | "running";
type SectionFetchStatus = "ok" | "error";
type BadgeVariant = "default" | "success" | "warning" | "failed" | "running";

const STATUS_OPTIONS: PmSessionStatus[] = ["active", "paused", "done", "failed", "archived"];
const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: "updated_desc", label: "Updated recently" },
  { value: "created_desc", label: "Created recently" },
  { value: "failed_desc", label: "Most failures" },
  { value: "blocked_desc", label: "Most blocked" },
];
/* ─── helpers ─── */
function statusLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  const labels: Record<string, string> = {
    active: "Active",
    archived: "Archived",
    blocked: "Blocked",
    done: "Done",
    failed: "Failed",
    paused: "Paused",
    running: "Running",
    success: "Success",
  };
  return labels[normalized] || statusLabelZh(status);
}
function liveBadgeVariant(mode: LiveMode): BadgeVariant {
  if (mode === "backoff") return "failed";
  return "running";
}
function alertsStatusBadgeVariant(status: CommandTowerAlertsPayload["status"]): BadgeVariant {
  if (status === "critical") return "failed";
  if (status === "degraded") return "warning";
  return "success";
}
function sectionBadgeVariant(status: SectionFetchStatus): BadgeVariant {
  return status === "ok" ? "success" : "failed";
}
export function CommandTowerPage({
  onNavigateToSession,
  locale = DEFAULT_UI_LOCALE,
}: {
  onNavigateToSession?: (sessionId: string) => void;
  locale?: UiLocale;
}) {
  const commandTowerCopy = getUiCopy(locale).desktop.commandTower;
  const shellEyebrow = locale === "zh-CN" ? "OpenVibeCoding / 实时指挥塔" : "OpenVibeCoding / live command tower";
  const liveBadgeTextResolved = (mode: LiveMode) =>
    mode === "paused"
      ? commandTowerCopy.badges.paused
      : mode === "backoff"
        ? commandTowerCopy.badges.backoff
        : commandTowerCopy.badges.liveRefresh;
  const sectionStatusText = (status: SectionFetchStatus) =>
    status === "ok" ? commandTowerCopy.sectionLabels.healthy : commandTowerCopy.sectionLabels.issue;
  const focusOptions = [
    { value: "all" as const, label: commandTowerCopy.focusLabels.all },
    { value: "high_risk" as const, label: commandTowerCopy.focusLabels.highRisk },
    { value: "blocked" as const, label: commandTowerCopy.focusLabels.blocked },
    { value: "running" as const, label: commandTowerCopy.focusLabels.running },
  ];
  const workMode: DesktopWorkMode = "execute";
  /* ─── core data ─── */
  const [overview, setOverview] = useState<CommandTowerOverviewPayload | null>(null);
  const [sessions, setSessions] = useState<PmSessionSummary[]>([]);
  const [alerts, setAlerts] = useState<CommandTowerAlert[]>([]);
  const [alertsStatus, setAlertsStatus] = useState<CommandTowerAlertsPayload["status"]>("healthy");

  /* ─── live engine ─── */
  const [liveMode, setLiveMode] = useState<LiveMode>("running");
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [lastSuccessfulUpdated, setLastSuccessfulUpdated] = useState("");
  const [sectionStatus, setSectionStatus] = useState<{ overview: SectionFetchStatus; sessions: SectionFetchStatus; alerts: SectionFetchStatus }>({ overview: "ok", sessions: "ok", alerts: "ok" });

  /* ─── filter state ─── */
  const [draftStatuses, setDraftStatuses] = useState<PmSessionStatus[]>([]);
  const [draftProjectKey, setDraftProjectKey] = useState("");
  const [draftSort, setDraftSort] = useState<SortMode>("updated_desc");
  const [focusMode, setFocusMode] = useState<FocusMode>("all");

  const [appliedStatuses, setAppliedStatuses] = useState<PmSessionStatus[]>([]);
  const [appliedProjectKey, setAppliedProjectKey] = useState("");
  const [appliedSort, setAppliedSort] = useState<SortMode>("updated_desc");
  const [refreshToken, setRefreshToken] = useState(0);

  /* ─── drawer ─── */
  const [drawerCollapsed, setDrawerCollapsed] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [actionFeedback, setActionFeedback] = useState("");
  const [loading, setLoading] = useState(true);

  const intervalRef = useRef(BASE_INTERVAL_MS);
  const projectInputRef = useRef<HTMLInputElement | null>(null);
  const refreshRequestIdRef = useRef(0);

  const openSessionById = useCallback((sessionId: string) => {
    onNavigateToSession?.(sessionId);
  }, [onNavigateToSession]);

  const handleSessionActionKeyDown = useCallback((event: ReactKeyboardEvent<HTMLButtonElement>, sessionId: string) => {
    if (event.key === "Enter" || event.key === " " || event.key === "Space" || event.key === "Spacebar") {
      event.preventDefault();
      openSessionById(sessionId);
    }
  }, [openSessionById]);

  /* ─── filter actions ─── */
  const toggleDraftStatus = (status: PmSessionStatus) => {
    setDraftStatuses((prev) => prev.includes(status) ? prev.filter((s) => s !== status) : [...prev, status]);
  };
  const applyFilters = () => {
    setAppliedStatuses(draftStatuses);
    setAppliedProjectKey(draftProjectKey.trim());
    setAppliedSort(draftSort);
    setRefreshToken((p) => p + 1);
  };
  const resetFilters = () => {
    setDraftStatuses([]); setDraftProjectKey(""); setDraftSort("updated_desc");
    setAppliedStatuses([]); setAppliedProjectKey(""); setAppliedSort("updated_desc");
    setRefreshToken((p) => p + 1);
  };
  const handleFilterKeyDown = (e: ReactKeyboardEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (e.key === "Enter") { e.preventDefault(); applyFilters(); }
    if (e.key === "Escape") { e.preventDefault(); resetFilters(); }
  };

  /* ─── refreshAll ─── */
  const refreshAll = useCallback(async (signal: AbortSignal, requestId?: number) => {
    const activeRequestId = requestId ?? refreshRequestIdRef.current + 1;
    refreshRequestIdRef.current = activeRequestId;
    const settled = await Promise.allSettled([
      fetchCommandTowerOverview({ signal, timeoutMs: REQUEST_TIMEOUT_MS }),
      fetchPmSessions({ status: appliedStatuses.length > 0 ? appliedStatuses : undefined, projectKey: appliedProjectKey || undefined, sort: appliedSort, limit: 100, signal, timeoutMs: REQUEST_TIMEOUT_MS }),
      fetchCommandTowerAlerts({ signal, timeoutMs: REQUEST_TIMEOUT_MS }),
    ]);
    if (refreshRequestIdRef.current !== activeRequestId) {
      return { stale: true as const, partialFailure: false, errorMessage: "" };
    }
    let successCount = 0;
    let firstError = "";
    const snap: typeof sectionStatus = { overview: "error", sessions: "error", alerts: "error" };

    if (settled[0].status === "fulfilled") { successCount++; snap.overview = "ok"; setOverview(settled[0].value); }
    else if (!firstError) firstError = settled[0].reason instanceof Error ? settled[0].reason.message : String(settled[0].reason);

    if (settled[1].status === "fulfilled") { successCount++; snap.sessions = "ok"; setSessions(Array.isArray(settled[1].value) ? settled[1].value : []); }
    else if (!firstError) firstError = settled[1].reason instanceof Error ? settled[1].reason.message : String(settled[1].reason);

    if (settled[2].status === "fulfilled") {
      successCount++; snap.alerts = "ok";
      setAlerts(settled[2].value.alerts || []);
      setAlertsStatus(settled[2].value.status || "healthy");
    } else if (!firstError) firstError = settled[2].reason instanceof Error ? settled[2].reason.message : String(settled[2].reason);

    setSectionStatus(snap);
    if (successCount === 3) setLastSuccessfulUpdated(new Date().toISOString());
    if (successCount === 0) throw new Error(firstError || "Refresh failed: every request was unsuccessful");
    return { stale: false as const, partialFailure: successCount < 3, errorMessage: firstError };
  }, [appliedProjectKey, appliedSort, appliedStatuses]);

  /* ─── manual refresh ─── */
  const refreshNow = useCallback(async () => {
    if (isRefreshing) return;
    const controller = new AbortController();
    setIsRefreshing(true);
    try {
      const requestId = refreshRequestIdRef.current + 1;
      const result = await refreshAll(controller.signal, requestId);
      if (result.stale) return;
      if (result.partialFailure) {
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
        if (liveEnabled) setLiveMode("backoff");
        if (result.errorMessage) setErrorMessage(result.errorMessage);
      } else {
        setErrorMessage(""); intervalRef.current = BASE_INTERVAL_MS;
        if (liveEnabled) setLiveMode("running");
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
      if (liveEnabled) setLiveMode("backoff");
    } finally { setIsRefreshing(false); setLoading(false); }
  }, [isRefreshing, liveEnabled, refreshAll]);

  /* ─── live polling loop ─── */
  useEffect(() => {
    if (!liveEnabled) { setLiveMode("paused"); return; }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const tick = async () => {
      if (cancelled) return;
      controller = new AbortController();
      try {
        const requestId = refreshRequestIdRef.current + 1;
        const result = await refreshAll(controller.signal, requestId);
        if (cancelled || result.stale) return;
        if (result.partialFailure) {
          intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
          setLiveMode("backoff");
          if (result.errorMessage) setErrorMessage(result.errorMessage);
        } else {
          setErrorMessage(""); intervalRef.current = BASE_INTERVAL_MS; setLiveMode("running");
        }
      } catch (err) {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : String(err));
        intervalRef.current = Math.min(intervalRef.current * 2, MAX_INTERVAL_MS);
        setLiveMode("backoff");
      } finally {
        setLoading(false);
        if (!cancelled && liveEnabled) timer = setTimeout(tick, intervalRef.current);
      }
    };
    timer = setTimeout(tick, 0);
    return () => { cancelled = true; controller?.abort(); if (timer) clearTimeout(timer); };
  }, [liveEnabled, refreshAll, refreshToken]);

  /* ─── export / copy ─── */
  const exportFailedSessions = useCallback(() => {
    const failed = sessions.filter((s) => String(s.status || "") === "failed");
    const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), total: failed.length, sessions: failed }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `ct-failed-${Date.now()}.json`; a.click();
    URL.revokeObjectURL(url);
    setActionFeedback("Exported failed sessions.");
  }, [sessions]);

  const copyCurrentViewLink = useCallback(async () => {
    try {
      const text = JSON.stringify({ statuses: appliedStatuses, project: appliedProjectKey, sort: appliedSort, focus: focusMode, live: liveEnabled }, null, 2);
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      setActionFeedback("Copied the current view settings.");
    } catch { setActionFeedback("Copy failed."); }
  }, [appliedProjectKey, appliedSort, appliedStatuses, focusMode, liveEnabled]);

  const openPrimarySession = useCallback(() => {
    const target = sessions[0]?.pm_session_id;
    if (!target) {
      setActionFeedback("No session is ready to open.");
      return;
    }
    onNavigateToSession?.(target);
    setActionFeedback(`Opened session ${target}.`);
  }, [onNavigateToSession, sessions]);
  const openWebAnalysis = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    const { protocol, hostname, port } = window.location;
    const webPort = port === "1420" ? "3100" : port;
    const webUrl = `${protocol}//${hostname}${webPort ? `:${webPort}` : ""}/command-tower`;
    window.open(webUrl, "_blank", "noopener,noreferrer");
    setActionFeedback("Opened the web deep-analysis view.");
  }, []);

  /* ─── keyboard shortcuts ─── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!e.altKey || !e.shiftKey || e.repeat) return;
      const target = e.target as HTMLElement | null;
      if (target?.isContentEditable || ["input", "textarea", "select"].includes(target?.tagName?.toLowerCase() || "")) return;
      const key = e.key.toLowerCase();
      if (key === "r") { e.preventDefault(); void refreshNow(); setActionFeedback("Triggered refresh now."); }
      else if (key === "l") { e.preventDefault(); setLiveEnabled((p) => { const n = !p; setActionFeedback(n ? "Live refresh resumed." : "Live refresh paused."); return n; }); }
      else if (key === "e") { e.preventDefault(); exportFailedSessions(); }
      else if (key === "c") { e.preventDefault(); void copyCurrentViewLink(); }
      else if (key === "f") { e.preventDefault(); projectInputRef.current?.focus(); setActionFeedback("Focused the project key input."); }
      else if (key === "d") { e.preventDefault(); setDrawerCollapsed((p) => { setActionFeedback(!p ? "Collapsed the right drawer." : "Expanded the right drawer."); return !p; }); }
      else if (key === "1") { e.preventDefault(); setFocusMode("all"); setActionFeedback(`Focus: ${commandTowerCopy.focusLabels.all.toLowerCase()}.`); }
      else if (key === "2") { e.preventDefault(); setFocusMode("high_risk"); setActionFeedback(`Focus: ${commandTowerCopy.focusLabels.highRisk.toLowerCase()}.`); }
      else if (key === "3") { e.preventDefault(); setFocusMode("blocked"); setActionFeedback(`Focus: ${commandTowerCopy.focusLabels.blocked.toLowerCase()}.`); }
      else if (key === "4") { e.preventDefault(); setFocusMode("running"); setActionFeedback(`Focus: ${commandTowerCopy.focusLabels.running.toLowerCase()}.`); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [copyCurrentViewLink, exportFailedSessions, refreshNow]);

  /* ─── action feedback auto-dismiss ─── */
  useEffect(() => {
    if (!actionFeedback) return;
    const t = setTimeout(() => setActionFeedback(""), 3500);
    return () => clearTimeout(t);
  }, [actionFeedback]);

  /* ─── derived ─── */
  const draftChanged = draftSort !== appliedSort || draftProjectKey.trim() !== appliedProjectKey || draftStatuses.length !== appliedStatuses.length || draftStatuses.some((s) => !appliedStatuses.includes(s));
  const appliedFilterCount = appliedStatuses.length + (appliedProjectKey ? 1 : 0);
  const hasAppliedFilters = appliedFilterCount > 0;

  const alertsSeverity = useMemo(() => {
    const s = { critical: 0, warning: 0, info: 0 };
    for (const a of alerts) {
      const sev = String(a?.severity || "").toLowerCase();
      if (sev === "critical") s.critical++;
      else if (sev === "warning") s.warning++;
      else s.info++;
    }
    return s;
  }, [alerts]);

  const sessionsSummary = useMemo(() => {
    let failed = 0, blocked = 0, running = 0;
    for (const s of sessions) {
      if (s.failed_runs > 0) failed++;
      if (s.blocked_runs > 0) blocked++;
      if (s.running_runs > 0) running++;
    }
    return { total: sessions.length, failed, blocked, running };
  }, [sessions]);

  const visibleSessions = useMemo(() => {
    if (focusMode === "high_risk") return sessions.filter((s) => s.failed_runs > 0);
    if (focusMode === "blocked") return sessions.filter((s) => s.blocked_runs > 0);
    if (focusMode === "running") return sessions.filter((s) => s.running_runs > 0);
    return sessions;
  }, [focusMode, sessions]);

  const focusLabel = focusOptions.find((o) => o.value === focusMode)?.label || commandTowerCopy.focusLabels.all;

  const refreshHealth = useMemo(() => {
    const ok = Object.values(sectionStatus).filter((v) => v === "ok").length;
    if (ok === 3 && !errorMessage) return { label: commandTowerCopy.refreshHealth.fullSuccess, variant: "success" as const };
    if (ok === 0) return { label: commandTowerCopy.refreshHealth.fullFailure, variant: "failed" as const };
    return { label: commandTowerCopy.refreshHealth.partialSuccess(ok), variant: "warning" as const };
  }, [commandTowerCopy.refreshHealth, errorMessage, sectionStatus]);

  const freshness = useMemo(() => {
    if (!lastSuccessfulUpdated) return "No successful refresh recorded yet";
    const diff = Math.max(0, Math.floor((Date.now() - Date.parse(lastSuccessfulUpdated)) / 1000));
    if (diff < 60) return `Refreshed ${diff}s ago`;
    if (diff < 3600) return `Refreshed ${Math.floor(diff / 60)}m ago`;
    return `Refreshed ${Math.floor(diff / 3600)}h ago`;
  }, [lastSuccessfulUpdated, liveMode]);

  const drawerPrompts = useMemo(() => {
    const p: string[] = [];
    if (alertsSeverity.critical > 0) p.push(`Detected ${alertsSeverity.critical} critical alerts. Prioritize them first.`);
    if (errorMessage) p.push("A refresh issue is active. Trigger a manual refresh to confirm whether it persists.");
    if (draftChanged) p.push("There is a filter draft that has not been applied yet.");
    if (sessionsSummary.failed > 0 || sessionsSummary.blocked > 0) p.push(`High-risk ${sessionsSummary.failed}, blocked ${sessionsSummary.blocked}. Use focus mode to narrow the list.`);
    if (!liveEnabled) p.push("Live refresh is paused. Resume it after triage.");
    if (p.length === 0) p.push("The surface is stable. Run a routine refresh and sample-check a session.");
    return p.slice(0, 4);
  }, [alertsSeverity.critical, draftChanged, errorMessage, liveEnabled, sessionsSummary.blocked, sessionsSummary.failed]);

  /* ─── loading skeleton ─── */
  if (loading) return (
    <div className="content">
      <div className="section-header">
        <div>
          <p className="cell-sub mono muted">{shellEyebrow}</p>
          <h1 className="page-title">{commandTowerCopy.title}</h1>
          <p className="page-subtitle">Loading live session monitoring and operator context...</p>
        </div>
      </div>
      <div className="skeleton-stack-lg">
        <div className="stats-grid"><div className="skeleton skeleton-card" /><div className="skeleton skeleton-card" /><div className="skeleton skeleton-card" /><div className="skeleton skeleton-card" /></div>
        <div className="skeleton skeleton-card-tall" />
        <div className="skeleton skeleton-row" />
        <div className="skeleton skeleton-row" />
      </div>
    </div>
  );

  return (
    <div className="content">
      {/* ─── Header ─── */}
      <div className="section-header">
        <div>
          <p className="cell-sub mono muted">{shellEyebrow}</p>
          <h1 className="page-title">{commandTowerCopy.title}</h1>
          <p className="page-subtitle">{commandTowerCopy.subtitle}</p>
          <p className="mono muted text-xs">{commandTowerCopy.currentModePrefix} {workMode}</p>
        </div>
        <div className="ct-header-badges">
          <Badge variant={liveBadgeVariant(liveMode)}>{liveBadgeTextResolved(liveMode)}</Badge>
          <Badge variant={alertsStatusBadgeVariant(alertsStatus)}>{commandTowerCopy.badges.sloPrefix}{alertsStatus}</Badge>
        </div>
      </div>

      {/* ─── Action Bar ─── */}
      <div className="ct-action-bar">
        <Button variant="primary" onClick={refreshNow} disabled={isRefreshing}>
          {isRefreshing ? commandTowerCopy.actions.refreshing : commandTowerCopy.actions.refreshProgress}
        </Button>
        <Button onClick={() => setLiveEnabled((p) => !p)}>
          {liveEnabled ? commandTowerCopy.actions.pauseAutoRefresh : commandTowerCopy.actions.resumeAutoRefresh}
        </Button>
        <Button onClick={openPrimarySession} disabled={sessions.length === 0}>
          {commandTowerCopy.actions.resumeWork}
        </Button>
      </div>

      {/* ─── Action Feedback ─── */}
      {actionFeedback && (
        <div role="status" aria-live="polite" className="ct-action-feedback">
          {actionFeedback}
        </div>
      )}
      <div className="row-gap-2">
        <Button variant="ghost" onClick={() => setAdvancedMode((p) => !p)} aria-expanded={advancedMode}>
          {advancedMode ? commandTowerCopy.actions.hideAdvancedDetail : commandTowerCopy.actions.showAdvancedDetail}
        </Button>
        <Button variant="ghost" onClick={openWebAnalysis}>
          {commandTowerCopy.actions.openWebDeepAnalysis}
        </Button>
      </div>

      {overview && (
        <div className="stats-grid">
          <article className="metric-card"><p className="metric-label">{commandTowerCopy.metrics.totalSessions}</p><p className="metric-value">{overview.total_sessions}</p></article>
          <article className="metric-card"><p className="metric-label">{commandTowerCopy.metrics.active}</p><p className="metric-value metric-value--primary">{overview.active_sessions}</p></article>
          <article className="metric-card"><p className="metric-label">{commandTowerCopy.metrics.failed}</p><p className="metric-value metric-value--danger">{overview.failed_sessions}</p></article>
          <article className="metric-card"><p className="metric-label">{commandTowerCopy.metrics.blocked}</p><p className="metric-value metric-value--warning">{overview.blocked_sessions}</p></article>
        </div>
      )}
      <p className="mono muted" role="status" aria-live="polite">
        {refreshHealth.label} · {freshness}
      </p>

      {/* ─── Focus View ─── */}
      <div role="group" aria-label="Focus view switcher" className="ct-focus-group">
        {focusOptions.map((opt) => (
          <Button key={opt.value} variant={focusMode === opt.value ? "primary" : "ghost"} aria-pressed={focusMode === opt.value} onClick={() => setFocusMode(opt.value)}>
            {opt.label}
            {opt.value === "all" && <span className="ct-focus-count">{sessionsSummary.total}</span>}
            {opt.value === "high_risk" && <span className="ct-focus-count">{sessionsSummary.failed}</span>}
            {opt.value === "blocked" && <span className="ct-focus-count">{sessionsSummary.blocked}</span>}
            {opt.value === "running" && <span className="ct-focus-count">{sessionsSummary.running}</span>}
          </Button>
        ))}
      </div>

      {/* ─── Health Status Bar ─── */}
      <div className="ct-health-bar" role="status" aria-live="polite">
        <Badge variant={refreshHealth.variant}>{refreshHealth.label}</Badge>
        <Badge variant="success">{freshness}</Badge>
        <Badge variant={sectionBadgeVariant(sectionStatus.overview)}>{commandTowerCopy.sectionLabels.overview} {sectionStatusText(sectionStatus.overview)}</Badge>
        <Badge variant={sectionBadgeVariant(sectionStatus.sessions)}>{commandTowerCopy.sectionLabels.sessions} {sectionStatusText(sectionStatus.sessions)}</Badge>
        <Badge variant={sectionBadgeVariant(sectionStatus.alerts)}>{commandTowerCopy.sectionLabels.alerts} {sectionStatusText(sectionStatus.alerts)}</Badge>
      </div>

      <section className="ct-web-handoff" aria-label="Web analysis handoff">
        <p>
          {commandTowerCopy.webHandoffIntro}{" "}
          <Button variant="ghost" onClick={openWebAnalysis}>
            {commandTowerCopy.webAnalysisView}
          </Button>
          .
        </p>
      </section>

      {/* ─── Error Banner ─── */}
      {errorMessage && (
        <div className="alert alert-danger ct-error-banner" role="alert">
          <div className="stack-gap-2">
            <div className="row-gap-2">
              <Badge variant="failed">{commandTowerCopy.errorIssueBadge}</Badge>
              <span className="mono text-xs">{errorMessage}</span>
            </div>
            <p className="muted text-xs">{commandTowerCopy.errorRecommendedAction}</p>
            <div className="row-gap-2">
              <Button variant="primary" onClick={refreshNow} disabled={isRefreshing}>
                {isRefreshing ? commandTowerCopy.retrying : commandTowerCopy.retryRefresh}
              </Button>
              <Button variant="ghost" onClick={() => setLiveEnabled(false)}>{commandTowerCopy.pauseLiveTriage}</Button>
            </div>
          </div>
        </div>
      )}

      {advancedMode ? (
        <>
          <div className="row-gap-2">
            <span className="muted text-xs">{commandTowerCopy.collapsedHint}</span>
          </div>

          {/* ─── Filter Console ─── */}
          <Card className="ct-filter-card">
            <div className="row-between">
              <div>
                <h3 className="card-title-reset text-base fw-600">{commandTowerCopy.filterTitle}</h3>
                <p className="ct-filter-hint">{commandTowerCopy.filterHint}</p>
              </div>
              {draftChanged && <Badge variant="warning">{commandTowerCopy.draftNotApplied}</Badge>}
            </div>
            <div className="ct-filter-controls">
              <fieldset className="ct-filter-fieldset" aria-label={commandTowerCopy.statusLegend}>
                <legend className="ct-filter-legend">{commandTowerCopy.statusLegend}</legend>
                {STATUS_OPTIONS.map((st) => (
                  <label key={st} className="ct-filter-check">
                    <input type="checkbox" checked={draftStatuses.includes(st)} onChange={() => toggleDraftStatus(st)} />
                    <span>{st}</span>
                  </label>
                ))}
              </fieldset>
              <label className="ct-filter-group">
                <span className="ct-filter-label">{commandTowerCopy.projectKey}</span>
                <Input ref={projectInputRef} className="ct-filter-input" value={draftProjectKey} onChange={(e) => setDraftProjectKey(e.target.value)} onKeyDown={handleFilterKeyDown} placeholder="cortexpilot" />
              </label>
              <label className="ct-filter-group ct-filter-group-sort">
                <span className="ct-filter-label">{commandTowerCopy.sort}</span>
                <Select className="ct-filter-input" value={draftSort} onChange={(e) => setDraftSort(e.target.value as SortMode)} onKeyDown={handleFilterKeyDown}>
                  {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </Select>
              </label>
              <div className="row-gap-2">
                <Button variant="primary" onClick={applyFilters} disabled={!draftChanged}>{commandTowerCopy.apply}</Button>
                <Button variant="ghost" onClick={resetFilters}>{commandTowerCopy.reset}</Button>
              </div>
            </div>
          </Card>
        </>
      ) : null}

      {/* ─── Filter / Focus Empty States ─── */}
      {sessions.length === 0 && hasAppliedFilters && (
        <div className="empty-state-stack"><p className="text-secondary">{commandTowerCopy.noSessionsForFilters}</p><Button onClick={resetFilters}>{commandTowerCopy.reset}</Button></div>
      )}
      {visibleSessions.length === 0 && sessions.length > 0 && focusMode !== "all" && (
        <div className="empty-state-stack"><p className="text-secondary">{commandTowerCopy.noSessionsForFocus}</p><Button onClick={() => setFocusMode("all")}>{commandTowerCopy.viewAll}</Button></div>
      )}

      {/* ─── Main Layout: Sessions + Drawer ─── */}
      <div className="ct-home-layout">
        {/* Main area */}
        <div className="ct-main-workspace">
          {/* Session Board */}
          <div className="app-section">
            <div className="section-header">
              <div>
                <h2 className="section-title">{commandTowerCopy.sessionBoardTitle}</h2>
                <p className="ct-session-count">{"Showing "}{visibleSessions.length}{" / "}{sessionsSummary.total}{" sessions"}</p>
              </div>
              <Badge>{focusLabel}</Badge>
            </div>
            {visibleSessions.length === 0 ? (
              <div className="empty-state-stack">
                <p className="muted">{commandTowerCopy.noSessionsYet}</p>
                <div className="row-gap-2">
                  <Button variant="primary" onClick={refreshNow} disabled={isRefreshing}>
                    {isRefreshing ? commandTowerCopy.actions.refreshing : commandTowerCopy.refreshNow}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setFocusMode("all");
                      resetFilters();
                    }}
                  >
                    {commandTowerCopy.viewAllSessions}
                  </Button>
                </div>
              </div>
            ) : (
              <Card className="table-card">
                <table className="run-table">
                  <thead><tr><th>Session ID</th><th>Objective</th><th>Status</th><th>Runs</th><th>Updated at</th></tr></thead>
                  <tbody>
                    {visibleSessions.map((s) => {
                      const rowClass = s.status === "failed" ? "session-row--failed" : s.failed_runs > 0 ? "session-row--failed" : s.blocked_runs > 0 ? "session-row--blocked" : s.running_runs > 0 ? "session-row--running" : "";
                      return (
<tr
  key={s.pm_session_id}
  className={rowClass}
>
<td className="mono text-xs">
  {onNavigateToSession ? (
    <Button
      variant="ghost"
      aria-label={`Open session ${s.pm_session_id}`}
      onClick={() => openSessionById(s.pm_session_id)}
      onKeyDown={(event) => handleSessionActionKeyDown(event, s.pm_session_id)}
    >
      {s.pm_session_id.slice(0, 12)}
    </Button>
  ) : (
    s.pm_session_id.slice(0, 12)
  )}
</td>
                          <td className="cell-primary ct-objective-ellipsis">{s.objective || "-"}</td>
                          <td><Badge className={badgeClass(s.status)}>{statusLabel(s.status)}</Badge></td>
                          <td>
                            <span className="ct-runs-summary">
                              {s.run_count}{" total / "}<span className="text-success">{s.success_runs}</span>{" success / "}<span className="text-danger">{s.failed_runs}</span>{" failed"}
                            </span>
                          </td>
                          <td className="muted">{s.updated_at ? new Date(s.updated_at).toLocaleString("en-US") : "-"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Card>
            )}
          </div>

          {/* Top Blockers */}
          {overview?.top_blockers && overview.top_blockers.length > 0 && (
            <div className="app-section">
              <h2 className="section-title">Blocking hotspots</h2>
              <div className="stack-gap-2">
                {overview.top_blockers.map((b) => (
                  <Card key={b.pm_session_id} className="ct-blocker-card">
                    <div className="row-between">
                      <span className="mono text-xs">{b.pm_session_id.slice(0, 12)}</span>
                      <Badge className={badgeClass(b.status)}>{statusLabel(b.status)}</Badge>
                    </div>
                    <p className="ct-blocker-objective">{b.objective || "-"}</p>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ─── Drawer Panel ─── */}
        {advancedMode && !drawerCollapsed && (
          <aside className="ct-drawer-panel" role="complementary" aria-label={commandTowerCopy.drawer.ariaLabel}>
            <div className="ct-drawer-header">
              <span className="ct-drawer-title">{commandTowerCopy.drawer.title}</span>
              <Button variant="ghost" className="ct-drawer-close-btn" onClick={() => setDrawerCollapsed(true)} aria-label={commandTowerCopy.drawer.close}>
                {"x"}
              </Button>
            </div>

            {/* Status row */}
            <div className="ct-drawer-status-row">
              <Badge variant={liveBadgeVariant(liveMode)}>{liveBadgeTextResolved(liveMode)}</Badge>
              <Badge variant={alertsStatusBadgeVariant(alertsStatus)}>{alertsStatus}</Badge>
              <Badge variant={refreshHealth.variant}>{refreshHealth.label}</Badge>
            </div>

            {/* Quick actions */}
            <div className="ct-drawer-section">
              <h4 className="ct-drawer-title-xs">{commandTowerCopy.drawer.quickActions}</h4>
              <div className="ct-drawer-mini-actions">
                <Button className="ct-drawer-mini-btn" onClick={refreshNow} disabled={isRefreshing}>{isRefreshing ? "..." : commandTowerCopy.refreshNow} <kbd className="ct-kbd-mini">Alt+Shift+R</kbd></Button>
                <Button className="ct-drawer-mini-btn" onClick={() => setLiveEnabled((p) => !p)}>{liveEnabled ? commandTowerCopy.drawer.paused : commandTowerCopy.drawer.running} <kbd className="ct-kbd-mini">Alt+Shift+L</kbd></Button>
                <Button className="ct-drawer-mini-btn" onClick={exportFailedSessions}>{commandTowerCopy.drawer.export} <kbd className="ct-kbd-mini">Alt+Shift+E</kbd></Button>
                <Button className="ct-drawer-mini-btn" onClick={() => void copyCurrentViewLink()}>{commandTowerCopy.drawer.copy} <kbd className="ct-kbd-mini">Alt+Shift+C</kbd></Button>
              </div>
            </div>

            {/* Health */}
            <div className="ct-drawer-section">
              <h4 className="ct-drawer-title-xs">{commandTowerCopy.drawer.health}</h4>
              <div className="ct-drawer-health-list">
                <div className="ct-drawer-health-row">
                  <span className="muted">{commandTowerCopy.badges.liveRefresh}</span>
                  <Badge variant={liveBadgeVariant(liveMode)}>{liveEnabled ? commandTowerCopy.drawer.running : commandTowerCopy.drawer.paused}</Badge>
                </div>
                <div className="ct-drawer-health-row">
                  <span className="muted">{commandTowerCopy.badges.sloPrefix.trim()}</span>
                  <Badge variant={alertsStatusBadgeVariant(alertsStatus)}>{alertsStatus.toUpperCase()}</Badge>
                </div>
                <div className="ct-drawer-health-row">
                  <span className="muted">{commandTowerCopy.drawer.focusHits}</span>
                  <Badge variant="success">{focusLabel} ({visibleSessions.length}/{sessionsSummary.total})</Badge>
                </div>
                <div className="ct-drawer-health-row">
                  <span className="muted">{commandTowerCopy.drawer.filterState}</span>
                  <Badge variant={hasAppliedFilters ? "running" : "warning"}>{hasAppliedFilters ? `${appliedFilterCount} ${commandTowerCopy.apply.toLowerCase()}` : commandTowerCopy.drawer.allFilters}</Badge>
                </div>
              </div>
              <div className="ct-drawer-tags">
                <Badge variant={sectionBadgeVariant(sectionStatus.overview)}>{commandTowerCopy.sectionLabels.overview} {sectionStatusText(sectionStatus.overview)}</Badge>
                <Badge variant={sectionBadgeVariant(sectionStatus.sessions)}>{commandTowerCopy.sectionLabels.sessions} {sectionStatusText(sectionStatus.sessions)}</Badge>
                <Badge variant={sectionBadgeVariant(sectionStatus.alerts)}>{commandTowerCopy.sectionLabels.alerts} {sectionStatusText(sectionStatus.alerts)}</Badge>
              </div>
            </div>

            {/* Inspection prompts */}
            <div className="ct-drawer-section">
              <h4 className="ct-drawer-title-xs">{commandTowerCopy.drawer.inspectionPrompts}</h4>
              <ul className="ct-drawer-prompt-list">
                {drawerPrompts.map((p) => (
                  <li key={p} className="ct-drawer-prompt-item">{p}</li>
                ))}
              </ul>
            </div>

            {/* Alerts */}
            <div className="ct-drawer-section">
              <div className="row-between">
                <h4 className="ct-drawer-title-xs">{commandTowerCopy.drawer.alerts}</h4>
                <Badge>{alertsSeverity.critical > 0 ? commandTowerCopy.drawer.criticalCount(alertsSeverity.critical) : commandTowerCopy.drawer.records(alerts.length)}</Badge>
              </div>
              {alerts.length === 0 ? (
                <div className="empty-state-stack">
                  <p className="ct-empty-hint">{commandTowerCopy.drawer.noAlerts}</p>
                  <Button variant="ghost" onClick={refreshNow} disabled={isRefreshing}>
                    {isRefreshing ? commandTowerCopy.actions.refreshing : commandTowerCopy.drawer.reviewAlertState}
                  </Button>
                </div>
              ) : (
                <div className="ct-alert-list">
                  {alerts.map((a, i) => {
                    const sev = typeof a?.severity === "string" && a.severity.trim() ? a.severity.toUpperCase() : "UNKNOWN";
                    const code = typeof a?.code === "string" && a.code.trim() ? a.code : "UNKNOWN_CODE";
                    const msg = typeof a?.message === "string" && a.message.trim() ? a.message : "No alert details.";
                    const sevVariant: BadgeVariant = sev === "CRITICAL" ? "failed" : sev === "WARNING" ? "warning" : "default";
                    return (
                      <div key={`${code}-${i}`} className="ct-alert-item">
                        <div className="ct-alert-head"><Badge variant={sevVariant}>{sev}</Badge><code className="ct-alert-code">{code}</code></div>
                        <p className="ct-alert-msg">{msg}</p>
                        {a.suggested_action && <p className="ct-alert-suggestion">{a.suggested_action}</p>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
