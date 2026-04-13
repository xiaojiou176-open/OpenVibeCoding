import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { DEFAULT_UI_LOCALE, getUiCopy, type UiLocale } from "@cortexpilot/frontend-shared/uiCopy";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
  type RunDetailPayload,
  type EventRecord,
  type ReportRecord,
  type ToolCallRecord,
  type JsonValue,
  type RunSummary,
} from "../lib/types";
import {
  fetchRun, fetchEvents, fetchDiff, fetchReports, fetchToolCalls, fetchChainSpec,
  fetchAgentStatus, fetchRuns, fetchArtifact, rollbackRun, rejectRun, replayRun, promoteEvidence, fetchOperatorCopilotBrief,
  type EventsStream,
  openEventsStream,
} from "../lib/api";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";
import {
  statusLabelDesktop,
  badgeVariant,
  statusDotClass,
  outcomeSemanticLabel,
  outcomeSemanticBadgeVariant,
  outcomeActionHint,
  outcomeSemantic,
  formatDesktopDateTime,
} from "../lib/statusPresentation";
import { toast } from "sonner";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Card, CardBody, CardHeader, CardTitle } from "../components/ui/Card";
import { Select } from "../components/ui/Input";
import { DesktopCopilotPanel } from "../components/copilot/DesktopCopilotPanel";

const RUN_COPILOT_QUESTIONS = [
  "Why did this run fail or get blocked?",
  "What changed compared with the baseline?",
  "What is the next operator action?",
  "Where is the workflow or queue risk right now?",
];

type RunDetailTab = "events" | "diff" | "reports" | "tools" | "chain" | "contract" | "replay";

type RunDetailPageProps = {
  runId: string;
  onBack: () => void;
  onOpenCompare?: () => void;
  locale?: UiLocale;
};

/* ─── helpers ─── */
function asRecord(value: unknown): Record<string, JsonValue> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, JsonValue>) : {};
}
function toArr<T>(v: T[] | undefined | null): T[] { return Array.isArray(v) ? v : []; }
function toStr(v: unknown, fallback = "-"): string { return typeof v === "string" && v.trim() ? v.trim() : fallback; }
function asNumber(value: JsonValue | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
function eventDedupeKey(event: EventRecord): string {
  const maybeTrace = event.trace_id ?? "";
  const maybeTs = event.ts ?? "";
  const maybeEvent = event.event ?? event.event_type ?? "";
  return `${maybeTs}|${maybeEvent}|${String(maybeTrace)}`;
}
function dedupeAndSortEvents(items: EventRecord[]): EventRecord[] {
  const seen = new Set<string>();
  const deduped: EventRecord[] = [];
  for (const item of items) {
    const key = eventDedupeKey(item);
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(item);
  }
  return deduped.sort((a, b) => (a.ts || "").localeCompare(b.ts || ""));
}

const TERMINAL_RUN_STATUS = new Set([
  "success",
  "done",
  "passed",
  "failed",
  "failure",
  "error",
  "rejected",
  "completed",
  "cancelled",
  "stopped",
  "archived",
]);

const TERMINAL_EVENT_NAMES = new Set([
  "RUN_COMPLETED",
  "RUN_FAILED",
  "RUN_REJECTED",
  "RUN_CANCELLED",
  "RUN_ARCHIVED",
  "TASK_RUN_COMPLETED",
  "TASK_RUN_FAILED",
]);

function isTerminalStatus(status: unknown): boolean {
  return typeof status === "string" && TERMINAL_RUN_STATUS.has(status.toLowerCase());
}

function isTerminalEvent(event: EventRecord): boolean {
  const name = typeof event.event === "string" ? event.event : event.event_type;
  return typeof name === "string" && TERMINAL_EVENT_NAMES.has(name.toUpperCase());
}

export function RunDetailPage({ runId, onBack, onOpenCompare = () => {}, locale = DEFAULT_UI_LOCALE }: RunDetailPageProps) {
  const runDetailCopy = getUiCopy(locale).desktop.runDetail;
  const completionGovernanceCopy = runDetailCopy.completionGovernance;
  const [run, setRun] = useState<RunDetailPayload | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [diff, setDiff] = useState("");
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [toolCalls, setToolCalls] = useState<ToolCallRecord[]>([]);
  const [chainSpec, setChainSpec] = useState<Record<string, JsonValue> | null>(null);
  const [agentStatus, setAgentStatus] = useState<Array<Record<string, unknown>>>([]);
  const [availableRuns, setAvailableRuns] = useState<RunSummary[]>([]);
  const [baselineRunId, setBaselineRunId] = useState("");
  const [replayResult, setReplayResult] = useState<Record<string, JsonValue> | null>(null);
  const [planningContracts, setPlanningContracts] = useState<Array<Record<string, JsonValue>>>([]);
  const [unblockTasks, setUnblockTasks] = useState<Array<Record<string, JsonValue>>>([]);
  const [contextPackArtifact, setContextPackArtifact] = useState<Record<string, JsonValue> | null>(null);
  const [harnessRequestArtifact, setHarnessRequestArtifact] = useState<Record<string, JsonValue> | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<RunDetailTab>("events");
  const [actionBusy, setActionBusy] = useState(false);
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [liveTransport, setLiveTransport] = useState<"sse" | "polling">("sse");
  const [expandedEvent, setExpandedEvent] = useState<number | null>(null);

  const eventsRef = useRef<EventRecord[]>([]);
  const loadTokenRef = useRef(0);

  const toggleExpandedEvent = useCallback((index: number) => {
    setExpandedEvent((prev) => (prev === index ? null : index));
  }, []);

  /* ─── initial load ─── */
  const load = useCallback(async () => {
    const loadToken = loadTokenRef.current + 1;
    loadTokenRef.current = loadToken;
    setLoading(true);
    setError("");
    try {
      const [runResult, eventsResult] = await Promise.allSettled([fetchRun(runId), fetchEvents(runId)]);
      if (loadToken !== loadTokenRef.current) {
        return;
      }
      if (runResult.status !== "fulfilled") {
        throw runResult.reason;
      }
      const runData = runResult.value;
      const eventsData = eventsResult.status === "fulfilled" ? eventsResult.value : [];
      setRun(runData);
      const sortedEvents = dedupeAndSortEvents(toArr(eventsData));
      setEvents(sortedEvents);
      eventsRef.current = sortedEvents;
      if (eventsResult.status !== "fulfilled") {
        console.warn(`[RunDetailPage] initial events refresh failed: ${uiErrorDetail(eventsResult.reason)}`);
      }

      // parallel secondary loads
      const [diffRes, reportsRes, toolsRes, chainRes, agentRes, runsRes] = await Promise.allSettled([
        fetchDiff(runId),
        fetchReports(runId),
        fetchToolCalls(runId),
        fetchChainSpec(runId),
        fetchAgentStatus(runId),
        fetchRuns(),
      ]);
      if (loadToken !== loadTokenRef.current) {
        return;
      }
      if (diffRes.status === "fulfilled") setDiff(diffRes.value.diff || "");
      if (reportsRes.status === "fulfilled") setReports(toArr(reportsRes.value));
      if (toolsRes.status === "fulfilled") setToolCalls(toArr(toolsRes.value?.data));
      if (chainRes.status === "fulfilled") setChainSpec((chainRes.value?.data as Record<string, JsonValue>) || null);
      if (agentRes.status === "fulfilled") {
        const d = agentRes.value as { agents?: Array<Record<string, unknown>> };
        setAgentStatus(toArr(d?.agents));
      }
      if (runsRes.status === "fulfilled") setAvailableRuns(toArr(runsRes.value));

      const artifacts = toArr((runData as any)?.manifest?.artifacts);
      const hasPlanningContractsArtifact = artifacts.some((item) => {
        const record = asRecord(item);
        return toStr(record.name, "") === "planning_worker_prompt_contracts" || toStr(record.path, "") === "artifacts/planning_worker_prompt_contracts.json";
      });
      const hasUnblockTasksArtifact = artifacts.some((item) => {
        const record = asRecord(item);
        return toStr(record.name, "") === "planning_unblock_tasks" || toStr(record.path, "") === "artifacts/planning_unblock_tasks.json";
      });
      const hasContextPackArtifact = artifacts.some((item) => {
        const record = asRecord(item);
        return toStr(record.name, "") === "context_pack" || toStr(record.path, "") === "artifacts/context_pack.json";
      });
      const hasHarnessRequestArtifact = artifacts.some((item) => {
        const record = asRecord(item);
        return toStr(record.name, "") === "harness_request" || toStr(record.path, "") === "artifacts/harness_request.json";
      });

      const [planningContractsArtifactRes, unblockTasksArtifactRes, contextPackArtifactRes, harnessRequestArtifactRes] = await Promise.allSettled([
        hasPlanningContractsArtifact
          ? fetchArtifact(runId, "planning_worker_prompt_contracts.json")
          : Promise.resolve(null),
        hasUnblockTasksArtifact
          ? fetchArtifact(runId, "planning_unblock_tasks.json")
          : Promise.resolve(null),
        hasContextPackArtifact
          ? fetchArtifact(runId, "context_pack.json")
          : Promise.resolve(null),
        hasHarnessRequestArtifact
          ? fetchArtifact(runId, "harness_request.json")
          : Promise.resolve(null),
      ]);
      if (loadToken !== loadTokenRef.current) {
        return;
      }
      setPlanningContracts(
        planningContractsArtifactRes.status === "fulfilled" && planningContractsArtifactRes.value
          ? toArr(planningContractsArtifactRes.value.data as Array<Record<string, JsonValue>>)
          : [],
      );
      setUnblockTasks(
        unblockTasksArtifactRes.status === "fulfilled" && unblockTasksArtifactRes.value
          ? toArr(unblockTasksArtifactRes.value.data as Array<Record<string, JsonValue>>)
          : [],
      );
      setContextPackArtifact(
        contextPackArtifactRes.status === "fulfilled" && contextPackArtifactRes.value && contextPackArtifactRes.value.data && typeof contextPackArtifactRes.value.data === "object"
          ? (contextPackArtifactRes.value.data as Record<string, JsonValue>)
          : null,
      );
      setHarnessRequestArtifact(
        harnessRequestArtifactRes.status === "fulfilled" && harnessRequestArtifactRes.value && harnessRequestArtifactRes.value.data && typeof harnessRequestArtifactRes.value.data === "object"
          ? (harnessRequestArtifactRes.value.data as Record<string, JsonValue>)
          : null,
      );
    } catch (err) {
      setError(sanitizeUiError(err, "Run detail failed to load"));
    } finally {
      if (loadToken === loadTokenRef.current) {
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    setLiveTransport("sse");
    setLiveEnabled(true);
  }, [runId]);

  useEffect(() => {
    if (isTerminalStatus(run?.status)) {
      setLiveEnabled(false);
    }
  }, [run?.status]);

  /* ─── live SSE ─── */
  useEffect(() => {
    if (!liveEnabled || !run || liveTransport !== "sse" || isTerminalStatus(run.status)) return;

    let es: EventsStream | null = null;
    try {
      es = openEventsStream(runId, { tail: true });
      es.onmessage = (msg) => {
        try {
          const evt = JSON.parse(msg.data) as EventRecord;
          setEvents((prev) => {
            const next = dedupeAndSortEvents([...prev, evt]);
            eventsRef.current = next;
            return next;
          });
          if (isTerminalEvent(evt)) {
            setLiveEnabled(false);
          }
        } catch (e) { console.debug("[RunDetailPage] SSE message parse failed:", e); }
      };
      es.onerror = () => {
        console.warn("[RunDetailPage] SSE disconnected, switching to polling fallback.");
        es?.close();
        setLiveTransport("polling");
      };
    } catch (error) {
      console.warn("[RunDetailPage] SSE unavailable, switching to polling fallback.", error);
      setLiveTransport("polling");
    }

    return () => { es?.close(); };
  }, [liveEnabled, liveTransport, run, runId]);

  /* ─── polling fallback ─── */
  useEffect(() => {
    if (!liveEnabled || !run || liveTransport !== "polling") return;
    if (isTerminalStatus(run.status)) {
      setLiveEnabled(false);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const [runResult, eventsResult] = await Promise.allSettled([fetchRun(runId), fetchEvents(runId)]);
        if (cancelled) return;
        const runData = runResult.status === "fulfilled" ? runResult.value : run;
        const sortedEvents =
          eventsResult.status === "fulfilled"
            ? dedupeAndSortEvents(toArr(eventsResult.value))
            : eventsRef.current;

        if (runResult.status === "fulfilled") {
          setRun(runResult.value);
        } else {
          console.warn(`[RunDetailPage] polling run refresh failed: ${uiErrorDetail(runResult.reason)}`);
        }
        if (eventsResult.status === "fulfilled") {
          setEvents(sortedEvents);
          eventsRef.current = sortedEvents;
        } else {
          console.warn(`[RunDetailPage] polling events refresh failed: ${uiErrorDetail(eventsResult.reason)}`);
        }
        if (isTerminalStatus(runData?.status) || sortedEvents.some(isTerminalEvent)) {
          setLiveEnabled(false);
          return;
        }
      } catch (error) {
        if (!cancelled) {
          console.warn("[RunDetailPage] polling refresh failed.", error);
        }
      }
      if (!cancelled) {
        timer = setTimeout(() => { void poll(); }, 2000);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [liveEnabled, liveTransport, run, runId]);

  /* ─── actions ─── */
  async function handleAction(action: "rollback" | "reject" | "replay" | "promote") {
    setActionBusy(true);
    try {
      if (action === "rollback") await rollbackRun(runId);
      else if (action === "reject") await rejectRun(runId);
      else if (action === "promote") await promoteEvidence(runId);
      else {
        const result = await replayRun(runId, baselineRunId || undefined);
        setReplayResult(result);
      }
      const successMessage = {
        rollback: "Rollback completed. Next step: refresh and confirm the run returned to a healthy state.",
        reject: "Reject completed. Next step: return to the list and continue with the next item.",
        replay: "Replay comparison completed. Next step: open Replay result to inspect the delta.",
        promote: "Evidence promotion completed. Next step: verify bundle completeness in Reports.",
      }[action];
      toast.success(successMessage);
      void load();
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      toast.error(`Action did not complete: ${detail}. Next step: retry it, and if it still fails, return to the list and re-open the run.`);
    } finally {
      setActionBusy(false);
    }
  }

  /* ─── loading / error ─── */
  if (loading) return (
    <div className="content">
      <div className="skeleton-stack-lg">
        <div className="skeleton skeleton-card-tall" />
        <div className="skeleton skeleton-row" />
        <div className="skeleton skeleton-row" />
        <div className="skeleton skeleton-row" />
      </div>
    </div>
  );
  if (error) return (
    <div className="content">
      <div className="alert alert-danger">
        <div className="stack-gap-2">
          <p>{runDetailCopy.loadErrorPrefix} {error}</p>
          <p className="muted text-xs">{runDetailCopy.loadErrorNextStep}</p>
        </div>
      </div>
      <div className="row-gap-2">
        <Button variant="primary" onClick={() => void load()}>{runDetailCopy.retryLoad}</Button>
        <Button onClick={onBack}>{runDetailCopy.backToList}</Button>
      </div>
    </div>
  );
  if (!run) return (
    <div className="content">
      <div className="empty-state-stack">
        <p className="muted">{runDetailCopy.noDetailPayload}</p>
        <p className="muted text-xs">{runDetailCopy.noDetailNextStep}</p>
        <div className="row-gap-2">
          <Button variant="primary" onClick={() => void load()}>{runDetailCopy.retryLoad}</Button>
          <Button onClick={onBack}>{runDetailCopy.backToList}</Button>
        </div>
      </div>
    </div>
  );

  /* ─── derived data ─── */
  const testReport = reports.find(r => r.name === "test_report.json")?.data;
  const reviewReport = reports.find(r => r.name === "review_report.json")?.data;
  const evidenceReport = reports.find(r => r.name === "evidence_report.json")?.data;
  const incidentPack = reports.find(r => r.name === "incident_pack.json")?.data as Record<string, JsonValue> | undefined;
  const proofPack = reports.find(r => r.name === "proof_pack.json")?.data as Record<string, JsonValue> | undefined;
  const completionGovernanceReport = asRecord(reports.find(r => r.name === "completion_governance_report.json")?.data);
  const runCompareReport = asRecord(reports.find(r => r.name === "run_compare_report.json")?.data);
  const compareSummary = asRecord(runCompareReport.compare_summary);
  const chainReport = reports.find(r => r.name === "chain_report.json")?.data;
  const workReport = reports.find(r => r.name === "work_report.json")?.data;
  const taskResult = reports.find(r => r.name === "task_result.json")?.data;
  const compareSummaryDeltaCount =
    asNumber(compareSummary.mismatched_count) +
    asNumber(compareSummary.missing_count) +
    asNumber(compareSummary.extra_count);
  const traceId = toStr(run.manifest?.trace_id, toStr(run.manifest?.trace?.trace_id));
  const workflowId = toStr(run.manifest?.workflow?.workflow_id);
  const roleBindingReadModel = run.role_binding_read_model;
  const isTerminal = isTerminalStatus(run.status);
  const pendingApprovals = events.filter(ev => (ev.event || "").toUpperCase() === "HUMAN_APPROVAL_REQUIRED");
  const continuationOnIncomplete = Array.from(
    new Set(
      planningContracts
        .map((contract) => toStr(asRecord(asRecord(contract).continuation_policy).on_incomplete, ""))
        .filter(Boolean),
    ),
  );
  const continuationOnBlocked = Array.from(
    new Set(
      planningContracts
        .map((contract) => toStr(asRecord(asRecord(contract).continuation_policy).on_blocked, ""))
        .filter(Boolean),
    ),
  );
  const doneChecks = Array.from(
    new Set(
      planningContracts.flatMap((contract) =>
        toArr(asRecord(asRecord(contract).done_definition).acceptance_checks as unknown[] | null | undefined)
          .map((item) => toStr(item, ""))
          .filter(Boolean),
      ),
    ),
  );
  const unblockOwners = Array.from(new Set(unblockTasks.map((task) => toStr(asRecord(task).owner, "")).filter(Boolean)));
  const unblockModes = Array.from(new Set(unblockTasks.map((task) => toStr(asRecord(task).mode, "")).filter(Boolean)));
  const unblockTriggers = Array.from(new Set(unblockTasks.map((task) => toStr(asRecord(task).trigger, "")).filter(Boolean)));
  const hasRuntimeCompletionGovernance = Object.keys(completionGovernanceReport).length > 0;
  const runtimeDodChecker = asRecord(completionGovernanceReport.dod_checker);
  const runtimeReplyAuditor = asRecord(completionGovernanceReport.reply_auditor);
  const runtimeContinuationDecision = asRecord(completionGovernanceReport.continuation_decision);
  const runtimeContextPack = asRecord(completionGovernanceReport.context_pack);
  const runtimeHarnessRequest = asRecord(completionGovernanceReport.harness_request);
  const contextPackRecord = asRecord(contextPackArtifact);
  const harnessRequestRecord = asRecord(harnessRequestArtifact);
  const runtimeDodRequiredChecks = Array.from(
    new Set(
      toArr(runtimeDodChecker.required_checks as unknown[] | null | undefined)
        .map((item) => toStr(item, ""))
        .filter(Boolean),
    ),
  );
  const runtimeDodUnmetChecks = Array.from(
    new Set(
      toArr(runtimeDodChecker.unmet_checks as unknown[] | null | undefined)
        .map((item) => toStr(item, ""))
        .filter(Boolean),
    ),
  );
  const semanticType = outcomeSemantic(run.outcome_type, run.status, run.failure_class, run.failure_code);
  const outcomeSemanticText = outcomeSemanticLabel(
    run.outcome_type,
    run.outcome_label_zh,
    run.status,
    locale,
    run.failure_class,
    run.failure_code,
  );
  const actionHintText = outcomeActionHint(
    run.action_hint_zh,
    run.outcome_type,
    run.status,
    locale,
    run.failure_class,
    run.failure_code,
  );

  const tabs: { key: RunDetailTab; label: string }[] = [
    { key: "events", label: runDetailCopy.tabs.events(events.length) },
    { key: "diff", label: runDetailCopy.tabs.diff },
    { key: "reports", label: runDetailCopy.tabs.reports(reports.length) },
    { key: "tools", label: runDetailCopy.tabs.tools(toolCalls.length) },
    { key: "chain", label: runDetailCopy.tabs.chain },
    { key: "contract", label: runDetailCopy.tabs.contract },
    { key: "replay", label: runDetailCopy.tabs.replay },
  ];

  return (
    <div className="content">
      {/* Header */}
      <div className="section-header">
        <div>
          <Button variant="ghost" className="mb-2" onClick={onBack}>{runDetailCopy.backToList}</Button>
          <h1 className="page-title mono run-detail-title">{run.run_id}</h1>
          <p className="page-subtitle">{runDetailCopy.taskLabelPrefix} {run.task_id}</p>
        </div>
        <div className="row-start-gap-2">
          <Badge variant={badgeVariant(run.status)}>{statusLabelDesktop(run.status, locale)}</Badge>
          <Button
            variant={liveEnabled && !isTerminal ? "primary" : "ghost"}
            onClick={() => setLiveEnabled(p => !p)}
            title={liveEnabled && !isTerminal ? runDetailCopy.liveTogglePauseTitle : runDetailCopy.liveToggleResumeTitle}
            disabled={isTerminal}
          >
            {liveEnabled && !isTerminal ? runDetailCopy.liveModeActive : runDetailCopy.liveModePaused}
          </Button>
        </div>
      </div>

      {/* Pending approvals alert */}
      {pendingApprovals.length > 0 && (
        <div className="alert alert-danger mb-4">
          {runDetailCopy.pendingApprovalWithCount(pendingApprovals.length)}
        </div>
      )}
      {semanticType === "manual_pending" && pendingApprovals.length === 0 && (
        <div className="alert alert-danger mb-4">
          {runDetailCopy.pendingApprovalWithoutCount}
        </div>
      )}

      <div className="mb-5">
        <DesktopCopilotPanel
          title={runDetailCopy.operatorCopilotTitle}
          intro={runDetailCopy.operatorCopilotIntro}
          buttonLabel={runDetailCopy.operatorCopilotButton}
          questionSet={RUN_COPILOT_QUESTIONS}
          loadBrief={() => fetchOperatorCopilotBrief(runId)}
        />
      </div>

      {/* Summary cards row */}
      <div className="grid-3 mb-5">
        {/* Status + Contract card */}
        <Card>
          <CardHeader><CardTitle className="card-title-reset">{runDetailCopy.summaryCards.overviewTitle}</CardTitle></CardHeader>
          <CardBody>
            <div className="data-list">
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.runId}</span><span className="data-list-value mono">{run.run_id}</span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.taskId}</span><span className="data-list-value">{run.task_id}</span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.status}</span><span className="data-list-value"><span className="status-inline"><span className={statusDotClass(run.status)} /><Badge variant={badgeVariant(run.status)}>{statusLabelDesktop(run.status, locale)}</Badge></span></span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.executionSemantic}</span><span className="data-list-value"><Badge variant={outcomeSemanticBadgeVariant(run.outcome_type, run.status, run.failure_class, run.failure_code)}>{outcomeSemanticText}</Badge></span></div>
              {run.failure_code && <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.failureCode}</span><span className="data-list-value mono">{run.failure_code}</span></div>}
              {run.failure_summary_zh && <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.failureSummary}</span><span className="data-list-value cell-danger">{run.failure_summary_zh}</span></div>}
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.nextAction}</span><span className="data-list-value">{actionHintText}</span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.currentOwner}</span><span className="data-list-value mono">{toStr(run.owner_agent_id)} ({toStr(run.owner_role)})</span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.assignedExecution}</span><span className="data-list-value mono">{toStr(run.assigned_agent_id)} ({toStr(run.assigned_role)})</span></div>
              <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.createdAt}</span><span className="data-list-value">{formatDesktopDateTime(run.created_at, locale)}</span></div>
              {traceId !== "-" && <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.traceId}</span><span className="data-list-value mono">{traceId}</span></div>}
              {workflowId !== "-" && <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.workflow}</span><span className="data-list-value mono">{workflowId}</span></div>}
              {run.failure_reason && <div className="data-list-row"><span className="data-list-label">{runDetailCopy.fieldLabels.failureReason}</span><span className="data-list-value cell-danger">{run.failure_reason}</span></div>}
            </div>
            {roleBindingReadModel ? (
              <div className="stack-gap-2 mt-3" data-testid="run-detail-role-binding-read-model">
                <div className="muted text-xs fw-500">{runDetailCopy.bindingReadModel.title}</div>
                <div className="data-list">
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.authority}</span><span className="data-list-value mono">{toStr(roleBindingReadModel.authority)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.source}</span><span className="data-list-value mono">{toStr(roleBindingReadModel.source)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.executionAuthority}</span><span className="data-list-value mono">{toStr(roleBindingReadModel.execution_authority)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.skillsBundle}</span><span className="data-list-value mono">{formatBindingReadModelLabel(roleBindingReadModel.skills_bundle_ref)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.mcpBundle}</span><span className="data-list-value mono">{formatBindingReadModelLabel(roleBindingReadModel.mcp_bundle_ref)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.runtimeBinding}</span><span className="data-list-value mono">{formatRoleBindingRuntimeSummary(roleBindingReadModel)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.runtimeCapability}</span><span className="data-list-value mono">{toStr(roleBindingReadModel.runtime_binding?.capability?.lane)}</span></div>
                  <div className="data-list-row"><span className="data-list-label">{runDetailCopy.bindingReadModel.toolExecution}</span><span className="data-list-value mono">{formatRoleBindingRuntimeCapabilitySummary(roleBindingReadModel)}</span></div>
                </div>
                <div className="muted text-xs">{runDetailCopy.bindingReadModel.readOnlyNote}</div>
              </div>
            ) : null}
            {hasRuntimeCompletionGovernance || planningContracts.length > 0 || unblockTasks.length > 0 ? (
              <div className="stack-gap-2 mt-3" data-testid="run-detail-completion-governance">
                <div className="muted text-xs fw-500">{completionGovernanceCopy.title}</div>
                {hasRuntimeCompletionGovernance ? (
                  <>
                    <div className="muted text-xs fw-500">{completionGovernanceCopy.runtimeTitle}</div>
                    <div className="data-list" data-testid="run-detail-completion-governance-report">
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.overallVerdict}</span><span className="data-list-value mono">{toStr(completionGovernanceReport.overall_verdict)}</span></div>
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.reportAuthority}</span><span className="data-list-value mono">{toStr(completionGovernanceReport.authority)}</span></div>
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.reportSource}</span><span className="data-list-value mono">{toStr(completionGovernanceReport.source)}</span></div>
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.reportExecutionAuthority}</span><span className="data-list-value mono">{toStr(completionGovernanceReport.execution_authority)}</span></div>
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.dodChecker}</span><span className="data-list-value mono">{toStr(runtimeDodChecker.status)}</span></div>
                      {toStr(runtimeDodChecker.summary, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.dodSummary}</span><span className="data-list-value">{toStr(runtimeDodChecker.summary, "")}</span></div>
                      ) : null}
                      {runtimeDodRequiredChecks.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.dodRequiredChecks}</span><span className="data-list-value mono">{runtimeDodRequiredChecks.join(" / ")}</span></div>
                      ) : null}
                      {runtimeDodUnmetChecks.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.dodUnmetChecks}</span><span className="data-list-value mono">{runtimeDodUnmetChecks.join(" / ")}</span></div>
                      ) : null}
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.replyAuditor}</span><span className="data-list-value mono">{toStr(runtimeReplyAuditor.status)}</span></div>
                      {toStr(runtimeReplyAuditor.summary, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.replySummary}</span><span className="data-list-value">{toStr(runtimeReplyAuditor.summary, "")}</span></div>
                      ) : null}
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.continuationDecision}</span><span className="data-list-value mono">{toStr(runtimeContinuationDecision.selected_action)}</span></div>
                      {toStr(runtimeContinuationDecision.summary, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.continuationSummary}</span><span className="data-list-value">{toStr(runtimeContinuationDecision.summary, "")}</span></div>
                      ) : null}
                      {toStr(runtimeContinuationDecision.action_source, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.actionSource}</span><span className="data-list-value mono">{toStr(runtimeContinuationDecision.action_source, "")}</span></div>
                      ) : null}
                      {toStr(runtimeContinuationDecision.unblock_task_id, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.selectedUnblockTask}</span><span className="data-list-value mono">{toStr(runtimeContinuationDecision.unblock_task_id, "")}</span></div>
                      ) : null}
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.contextPack}</span><span className="data-list-value mono">{toStr(runtimeContextPack.status)}</span></div>
                      {toStr(runtimeContextPack.summary, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.contextPackSummary}</span><span className="data-list-value">{toStr(runtimeContextPack.summary, "")}</span></div>
                      ) : null}
                      {toStr(contextPackRecord.pack_id, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.contextPackId}</span><span className="data-list-value mono">{toStr(contextPackRecord.pack_id, "")}</span></div>
                      ) : null}
                      {toStr(contextPackRecord.trigger_reason, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.contextPackTrigger}</span><span className="data-list-value mono">{toStr(contextPackRecord.trigger_reason, "")}</span></div>
                      ) : null}
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.harnessRequest}</span><span className="data-list-value mono">{toStr(runtimeHarnessRequest.status)}</span></div>
                      {toStr(runtimeHarnessRequest.summary, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.harnessRequestSummary}</span><span className="data-list-value">{toStr(runtimeHarnessRequest.summary, "")}</span></div>
                      ) : null}
                      {toStr(harnessRequestRecord.request_id, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.harnessRequestId}</span><span className="data-list-value mono">{toStr(harnessRequestRecord.request_id, "")}</span></div>
                      ) : null}
                      {toStr(harnessRequestRecord.scope, "") ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.harnessRequestScope}</span><span className="data-list-value mono">{toStr(harnessRequestRecord.scope, "")}</span></div>
                      ) : null}
                      {harnessRequestRecord.approval_required !== undefined ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.harnessRequestApproval}</span><span className="data-list-value mono">{toStr(harnessRequestRecord.approval_required)}</span></div>
                      ) : null}
                    </div>
                    <div className="muted text-xs">{completionGovernanceCopy.runtimeNote}</div>
                  </>
                ) : null}
                {planningContracts.length > 0 || unblockTasks.length > 0 ? (
                  <>
                    {hasRuntimeCompletionGovernance ? (
                      <div className="muted text-xs fw-500">{completionGovernanceCopy.planningFallbackTitle}</div>
                    ) : null}
                    <div className="data-list">
                      <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.workerPromptContracts}</span><span className="data-list-value mono">{planningContracts.length}</span></div>
                      {unblockTasks.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.unblockTasks}</span><span className="data-list-value mono">{unblockTasks.length}</span></div>
                      ) : null}
                      {continuationOnIncomplete.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.onIncomplete}</span><span className="data-list-value mono">{continuationOnIncomplete.join(" / ")}</span></div>
                      ) : null}
                      {continuationOnBlocked.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.onBlocked}</span><span className="data-list-value mono">{continuationOnBlocked.join(" / ")}</span></div>
                      ) : null}
                      {doneChecks.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.doneChecks}</span><span className="data-list-value mono">{doneChecks.join(" / ")}</span></div>
                      ) : null}
                      {unblockOwners.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.unblockOwner}</span><span className="data-list-value mono">{unblockOwners.join(" / ")}</span></div>
                      ) : null}
                      {unblockModes.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.unblockMode}</span><span className="data-list-value mono">{unblockModes.join(" / ")}</span></div>
                      ) : null}
                      {unblockTriggers.length > 0 ? (
                        <div className="data-list-row"><span className="data-list-label">{completionGovernanceCopy.unblockTrigger}</span><span className="data-list-value mono">{unblockTriggers.join(" / ")}</span></div>
                      ) : null}
                    </div>
                    <div className="muted text-xs">{completionGovernanceCopy.advisoryNote}</div>
                  </>
                ) : null}
              </div>
            ) : null}
          </CardBody>
        </Card>

        {/* Agent status card */}
        <Card>
          <CardHeader><CardTitle className="card-title-reset">{runDetailCopy.summaryCards.executionRolesTitle}</CardTitle></CardHeader>
          <CardBody>
            {agentStatus.length === 0 ? (
              <div className="empty-state-stack">
                <p className="muted">{runDetailCopy.emptyStates.noExecutionRoleStatus}</p>
                <p className="muted text-xs">{runDetailCopy.emptyStates.executionRolesNextStep}</p>
                <Button onClick={() => void load()}>{runDetailCopy.emptyStates.retryFetch}</Button>
              </div>
            ) : (
              <div className="data-list">
                {agentStatus.map((agent, i) => {
                  const agentStatusText = typeof agent.status === "string" ? agent.status : "";
                  return (
                    <div key={i} className="data-list-row">
                      <span className="data-list-label mono">{toStr(agent.role as string)}</span>
                      <span className="data-list-value">
                        <span className="status-inline">
                          <span className={statusDotClass(agentStatusText)} />
                          <Badge variant={badgeVariant(agentStatusText)}>{statusLabelDesktop(agentStatusText, locale)}</Badge>
                        </span>
                        {typeof agent.agent_id === "string" && (
                          <span className="mono muted ml-2 text-xs">
                            {agent.agent_id}
                          </span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </CardBody>
        </Card>

        {/* Evidence hashes card */}
        <Card>
          <CardHeader><CardTitle className="card-title-reset">{runDetailCopy.summaryCards.evidenceTitle}</CardTitle></CardHeader>
          <CardBody>
            {run.manifest?.evidence_hashes ? (
              <div className="data-list">
                {Object.entries(run.manifest.evidence_hashes as Record<string, unknown>).slice(0, 8).map(([key, val]) => (
                  <div key={key} className="data-list-row">
                    <span className="data-list-label mono text-xs">{key}</span>
                    <span className="data-list-value mono text-xs">{String(val).slice(0, 16)}...</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state-stack">
                <p className="muted">{runDetailCopy.emptyStates.noEvidenceSummary}</p>
                <p className="muted text-xs">{runDetailCopy.emptyStates.evidenceNextStep}</p>
                <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshData}</Button>
              </div>
            )}
            <div className="mt-3 row-gap-2">
              <Button className="text-xs" disabled={actionBusy} onClick={() => handleAction("promote")}>{runDetailCopy.actionBar.promoteEvidence}</Button>
            </div>
          </CardBody>
        </Card>
      </div>

      {/* Actions bar */}
      <div className="row-gap-2 mb-4">
        <Button variant="secondary" disabled={actionBusy} onClick={() => handleAction("rollback")}>{runDetailCopy.actionBar.rollback}</Button>
        <Button variant="destructive" disabled={actionBusy} onClick={() => handleAction("reject")}>{runDetailCopy.actionBar.reject}</Button>
        <Button disabled={actionBusy} onClick={load}>{runDetailCopy.actionBar.refresh}</Button>
      </div>

      {/* Tabs */}
      <div className="nav">
        {tabs.map((tab) => (
          <Button key={tab.key} variant={activeTab === tab.key ? "primary" : "ghost"} onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </Button>
        ))}
      </div>

      {/* Tab: Events */}
      {activeTab === "events" && (
        <Card className="table-card">
          {events.length === 0 ? (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noEvents}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.eventsNextStep}</p>
              <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshEvents}</Button>
            </div>
          ) : (
            <table className="run-table">
              <thead><tr><th>{runDetailCopy.tableHeaders.time}</th><th>{runDetailCopy.tableHeaders.event}</th><th>{runDetailCopy.tableHeaders.level}</th><th>{runDetailCopy.tableHeaders.taskId}</th></tr></thead>
              <tbody>
                {events.map((evt, i) => (
                  <Fragment key={`${evt.ts}-${i}`}>
                    <tr
                      className={evt.context ? "clickable-row" : ""}
                    >
                      <td className="muted">{formatDesktopDateTime(evt.ts, locale)}</td>
                      <td className="cell-primary">
                        {evt.context ? (
                          <Button
                            variant="ghost"
                            aria-expanded={expandedEvent === i}
                            aria-label={`View event details ${evt.event || evt.event_type || "event"}`}
                            onClick={() => toggleExpandedEvent(i)}
                          >
                            {evt.event || evt.event_type || "-"}
                          </Button>
                        ) : (
                          evt.event || evt.event_type || "-"
                        )}
                      </td>
                      <td><Badge variant={badgeVariant(evt.level)}>{evt.level || "-"}</Badge></td>
                      <td className="mono">{evt.task_id || "-"}</td>
                    </tr>
                    {expandedEvent === i && evt.context && (
                      <tr><td colSpan={4}><pre className="pre-reset text-xs pre-scroll-300">{JSON.stringify(evt.context, null, 2)}</pre></td></tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {/* Tab: Diff */}
      {activeTab === "diff" && (
        <Card>
          {diff ? (
            <pre className="pre-scroll-500">{diff}</pre>
          ) : (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noDiff}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.diffNextStep}</p>
              <div className="row-gap-2">
                <Button onClick={() => void load()}>{runDetailCopy.retryLoad}</Button>
                <Button variant="ghost" onClick={() => setActiveTab("events")}>{runDetailCopy.emptyStates.backToEventTimeline}</Button>
              </div>
            </div>
          )}
          {run.allowed_paths && run.allowed_paths.length > 0 && (
            <div className="p-3-4 border-top-subtle">
              <span className="muted text-xs fw-500">{runDetailCopy.fieldLabels.allowedPaths}: </span>
              <span className="chip-list inline-flex">
                {run.allowed_paths.map((p) => <span key={p} className="chip">{p}</span>)}
              </span>
            </div>
          )}
        </Card>
      )}

      {/* Tab: Reports */}
      {activeTab === "reports" && (
        <Card>
          {reports.length === 0 ? (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noReports}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.reportsNextStep}</p>
              <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshReports}</Button>
            </div>
          ) : (
            <div className="stack-gap-3 p-3">
              {reports.map((r, i) => (
                <details key={`${r.name}-${i}`} className="collapsible">
                  <summary>{r.name}</summary>
                  <div className="collapsible-body"><pre>{typeof r.data === "string" ? r.data : JSON.stringify(r.data, null, 2)}</pre></div>
                </details>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Tab: Tool Calls */}
      {activeTab === "tools" && (
        <Card className="table-card">
          {toolCalls.length === 0 ? (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noToolCalls}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.toolCallsNextStep}</p>
              <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshToolCalls}</Button>
            </div>
          ) : (
            <table className="run-table">
              <thead><tr><th>{runDetailCopy.tableHeaders.tool}</th><th>{runDetailCopy.tableHeaders.status}</th><th>{runDetailCopy.tableHeaders.taskId}</th><th>{runDetailCopy.tableHeaders.duration}</th><th>{runDetailCopy.tableHeaders.error}</th></tr></thead>
              <tbody>
                {toolCalls.map((tc, i) => (
                  <tr key={i} className={tc.status === "error" ? "session-row--failed" : ""}>
                    <td className="cell-primary mono">{tc.tool || "-"}</td>
                    <td><Badge variant={badgeVariant(tc.status)}>{statusLabelDesktop(tc.status || "", locale)}</Badge></td>
                    <td className="mono muted">{tc.task_id || "-"}</td>
                    <td className="muted">{tc.duration_ms != null ? `${tc.duration_ms}ms` : "-"}</td>
                    <td className={tc.error ? "cell-danger" : "muted"}>{tc.error || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {/* Tab: Chain */}
      {activeTab === "chain" && (
        <Card>
          {chainSpec || chainReport ? (
            <div className="stack-gap-3 p-3">
              {chainSpec && (
                <details className="collapsible" open>
                  <summary>{runDetailCopy.emptyStates.chainSpecTitle}</summary>
                  <div className="collapsible-body"><pre>{JSON.stringify(chainSpec, null, 2)}</pre></div>
                </details>
              )}
              {chainReport && (
                <details className="collapsible">
                  <summary>{runDetailCopy.emptyStates.chainReportTitle}</summary>
                  <div className="collapsible-body"><pre>{JSON.stringify(chainReport, null, 2)}</pre></div>
                </details>
              )}
            </div>
          ) : (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noChainFlow}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.chainNextStep}</p>
              <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshChain}</Button>
            </div>
          )}
        </Card>
      )}

      {/* Tab: Contract */}
      {activeTab === "contract" && (
        <Card>
          {run.contract ? (
            <pre>{JSON.stringify(run.contract, null, 2)}</pre>
          ) : (
            <div className="empty-state-stack">
              <p className="muted">{runDetailCopy.emptyStates.noContractSnapshot}</p>
              <p className="muted text-xs">{runDetailCopy.emptyStates.contractNextStep}</p>
              <Button onClick={() => void load()}>{runDetailCopy.emptyStates.refreshContract}</Button>
            </div>
          )}
        </Card>
      )}

      {/* Tab: Replay */}
      {activeTab === "replay" && (
        <Card>
          <CardBody className="stack-gap-4">
            <div>
              <h3 className="card-title-reset text-base mb-2">{runDetailCopy.emptyStates.replayTitle}</h3>
              <p className="muted text-sm">{runDetailCopy.emptyStates.replayDescription}</p>
            </div>
            <div className="row-start-gap-2">
              <Select className="flex-1 input-max-400" value={baselineRunId} onChange={(e) => setBaselineRunId(e.target.value)}>
                <option value="">{runDetailCopy.emptyStates.selectBaselineRun}</option>
                {availableRuns.filter(r => r.run_id !== runId).map(r => (
                  <option key={r.run_id} value={r.run_id}>{r.run_id.slice(0, 12)} - {r.task_id} ({statusLabelDesktop(r.status, locale)})</option>
                ))}
              </Select>
              <Button variant="primary" disabled={actionBusy} onClick={() => handleAction("replay")}>
                {runDetailCopy.emptyStates.runReplay}
              </Button>
            </div>
            {replayResult && (
              <details className="collapsible" open>
                <summary>{runDetailCopy.emptyStates.replayResult}</summary>
                <div className="collapsible-body"><pre>{JSON.stringify(replayResult, null, 2)}</pre></div>
              </details>
            )}
            {Object.keys(compareSummary).length > 0 && (
              <div className="grid-2">
                <Card>
                  <CardHeader><CardTitle>{runDetailCopy.emptyStates.compareDecisionTitle}</CardTitle></CardHeader>
                  <CardBody>
                    <div className="stack-gap-2">
                      <p className="muted">
                        {compareSummaryDeltaCount === 0
                          ? runDetailCopy.emptyStates.compareAligned
                          : runDetailCopy.emptyStates.compareNeedsReview}
                      </p>
                      <p className="muted text-sm">{runDetailCopy.emptyStates.compareNextStep}</p>
                    </div>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader><CardTitle>{runDetailCopy.emptyStates.actionContextTitle}</CardTitle></CardHeader>
                  <CardBody>
                    {incidentPack?.summary ? <p className="muted">{runDetailCopy.emptyStates.incidentPrefix} {String(incidentPack.summary)}</p> : null}
                    {proofPack?.summary ? <p className="muted">{runDetailCopy.emptyStates.proofPrefix} {String(proofPack.summary)}</p> : null}
                    {!incidentPack?.summary && !proofPack?.summary ? (
                      <p className="muted">{runDetailCopy.emptyStates.noProofIncident}</p>
                    ) : null}
                  </CardBody>
                </Card>
              </div>
            )}
            {Object.keys(compareSummary).length > 0 && (
              <details className="collapsible" open>
                <summary>{runDetailCopy.emptyStates.compareSummaryTitle}</summary>
                <div className="collapsible-body"><pre>{JSON.stringify(compareSummary, null, 2)}</pre></div>
              </details>
            )}
            {Object.keys(compareSummary).length > 0 && (
              <Button variant="secondary" onClick={onOpenCompare}>{runDetailCopy.emptyStates.openCompareSurface}</Button>
            )}
            {proofPack && (
              <details className="collapsible" open>
                <summary>{runDetailCopy.emptyStates.proofPackTitle}</summary>
                <div className="collapsible-body"><pre>{JSON.stringify(proofPack, null, 2)}</pre></div>
              </details>
            )}
            {/* Key reports for quick reference */}
            {(testReport || reviewReport || evidenceReport || workReport || taskResult) && (
              <div>
                <h4 className="card-title-reset text-sm muted mb-2">{runDetailCopy.emptyStates.relatedReportsTitle}</h4>
                <div className="stack-gap-2">
                  {testReport && <details className="collapsible"><summary>{runDetailCopy.emptyStates.testReportTitle}</summary><div className="collapsible-body"><pre>{JSON.stringify(testReport, null, 2)}</pre></div></details>}
                  {reviewReport && <details className="collapsible"><summary>{runDetailCopy.emptyStates.reviewReportTitle}</summary><div className="collapsible-body"><pre>{JSON.stringify(reviewReport, null, 2)}</pre></div></details>}
                  {evidenceReport && <details className="collapsible"><summary>{runDetailCopy.emptyStates.evidenceReportTitle}</summary><div className="collapsible-body"><pre>{JSON.stringify(evidenceReport, null, 2)}</pre></div></details>}
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}
