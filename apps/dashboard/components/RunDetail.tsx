"use client";

import { useEffect, useRef, useState } from "react";
import EventTimeline from "./EventTimeline";
import { Card } from "./ui/card";
import {
  fetchAgentStatus,
  fetchChainSpec,
  fetchEvents,
  fetchReports,
  fetchRuns,
  fetchToolCalls,
  openEventsStream,
  replayRun,
} from "../lib/api";
import type { EventRecord, ReportRecord, RunDetailPayload, RunSummary, ToolCallRecord } from "../lib/types";
import RunDetailAgentStatusCard from "./run-detail/RunDetailAgentStatusCard";
import RunDetailDetailPanel, { type RunDetailTab } from "./run-detail/RunDetailDetailPanel";
import RunDetailStatusContractCard from "./run-detail/RunDetailStatusContractCard";
import { useRunDetailLive } from "./run-detail/useRunDetailLive";
import {
  LIVE_BASE_INTERVAL_MS,
  deriveTerminalStatus,
  lifecycleBadges,
  sortEvents,
  toArray,
  toObject,
  toStringOr,
  type LifecycleSnapshot,
  type LiveMode,
  type LiveTransport,
} from "./run-detail/runDetailHelpers";
import { sanitizeUiError, uiErrorDetail } from "../lib/uiError";
import { sanitizeTraceUrl } from "../lib/safeUrl";

export {
  badgeVariantForStage,
  deriveTerminalStatus,
  eventIdentity,
  eventTimestamp,
  isTerminalStatus,
  latestEventTimestamp,
  lifecycleBadges,
  liveBadgeVariant,
  liveLabel,
  mergeEvents,
  normalizedStatus,
  sortEvents,
  toArray,
  toDisplayText,
  toObject,
  toStringOr,
} from "./run-detail/runDetailHelpers";

export default function RunDetail({
  run,
  events,
  diff,
  reports,
}: {
  run: RunDetailPayload;
  events: EventRecord[];
  diff: string;
  reports: ReportRecord[];
}) {
  const [tab, setTab] = useState<RunDetailTab>("diff");
  const [eventsState, setEventsState] = useState<EventRecord[]>(sortEvents(Array.isArray(events) ? events : []));
  const [reportsState, setReportsState] = useState<ReportRecord[]>(Array.isArray(reports) ? reports : []);
  const [chainSpec, setChainSpec] = useState<Record<string, unknown> | null>(null);
  const [baselineRunId, setBaselineRunId] = useState("");
  const [replayStatus, setReplayStatus] = useState<"idle" | "running" | "error" | "done">("idle");
  const [replayError, setReplayError] = useState("");
  const [availableRuns, setAvailableRuns] = useState<RunSummary[]>([]);
  const [availableRunsError, setAvailableRunsError] = useState("");
  const [availableRunsLoading, setAvailableRunsLoading] = useState(false);
  const [agentStatus, setAgentStatus] = useState<Array<Record<string, unknown>>>([]);
  const [agentStatusError, setAgentStatusError] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCallRecord[]>([]);
  const [toolCallsError, setToolCallsError] = useState("");
  const [toolCallsLoading, setToolCallsLoading] = useState(false);
  const [chainSpecError, setChainSpecError] = useState("");
  const [chainSpecLoading, setChainSpecLoading] = useState(false);
  const [liveEnabled, setLiveEnabled] = useState(true);
  const [liveMode, setLiveMode] = useState<LiveMode>("running");
  const [liveTransport, setLiveTransport] = useState<LiveTransport>("polling");
  const [liveError, setLiveError] = useState("");
  const [liveIntervalMs, setLiveIntervalMs] = useState(LIVE_BASE_INTERVAL_MS);
  const [liveLagMs, setLiveLagMs] = useState(0);
  const [lastRefreshAt, setLastRefreshAt] = useState("");
  const [failedTerminalActionFeedback, setFailedTerminalActionFeedback] = useState("");
  const [detailPanelFocusRequestKey, setDetailPanelFocusRequestKey] = useState(0);
  const [eventInspectFeedback, setEventInspectFeedback] = useState<{
    eventName: string;
    eventTs: string;
    status: "loading" | "success" | "error" | "info";
    message: string;
  } | null>(null);

  const eventsRef = useRef<EventRecord[]>(sortEvents(Array.isArray(events) ? events : []));
  const reportsRef = useRef<ReportRecord[]>(Array.isArray(reports) ? reports : []);

  const testReport = reportsState.find((r) => r.name === "test_report.json")?.data;
  const reviewReport = reportsState.find((r) => r.name === "review_report.json")?.data;
  const taskResult = reportsState.find((r) => r.name === "task_result.json")?.data;
  const workReport = reportsState.find((r) => r.name === "work_report.json")?.data;
  const evidenceReport = reportsState.find((r) => r.name === "evidence_report.json")?.data;
  const incidentPack = reportsState.find((r) => r.name === "incident_pack.json")?.data;
  const proofPack = reportsState.find((r) => r.name === "proof_pack.json")?.data;
  const replayReport = reportsState.find((r) => r.name === "replay_report.json")?.data as Record<string, unknown> | undefined;
  const runCompareReport = reportsState.find((r) => r.name === "run_compare_report.json")?.data;
  const chainReport = reportsState.find((r) => r.name === "chain_report.json")?.data;
  const chainLifecycle = ((chainReport as Record<string, unknown> | undefined)?.lifecycle || null) as LifecycleSnapshot | null;
  const lifecycleRail = lifecycleBadges(chainLifecycle);

  const evidence = replayReport?.evidence_hashes as
    | {
        mismatched?: Array<{ key?: string; baseline?: string; current?: string }>;
        missing?: string[];
        extra?: string[];
      }
    | undefined;
  const mismatched = toArray(evidence?.mismatched);
  const missing = toArray(evidence?.missing);
  const extra = toArray(evidence?.extra);

  const traceId = toStringOr(run?.manifest?.trace_id, toStringOr(run?.manifest?.trace?.trace_id, ""));
  const traceUrl = sanitizeTraceUrl(toStringOr(run?.manifest?.trace?.trace_url, ""));
  const workflowId = toStringOr(run?.manifest?.workflow?.workflow_id, "");
  const workflowStatus = toStringOr(run?.manifest?.workflow?.status, "");
  const schemaVersion = toStringOr(run?.manifest?.versions?.contracts_schema, "v1");
  const evidenceHashes = toObject(run?.manifest?.evidence_hashes);
  const manifestArtifacts = toArray(run?.manifest?.artifacts as unknown[] | undefined);
  const observability = toObject(run?.manifest?.observability);
  const summaryGroups = ["reports/", "events.jsonl", "contract.json", "other"];
  const summary = summaryGroups.map((group) => {
    const matchGroup = (key: string) => {
      if (group === "reports/") {
        return key.startsWith("reports/");
      }
      if (group === "events.jsonl") {
        return key === "events.jsonl";
      }
      if (group === "contract.json") {
        return key === "contract.json";
      }
      return !key.startsWith("reports/") && key !== "events.jsonl" && key !== "contract.json";
    };
    return {
      group,
      mismatched: mismatched.filter((item) => matchGroup(toStringOr(item.key, ""))).length,
      missing: missing.filter((item) => matchGroup(item)).length,
      extra: extra.filter((item) => matchGroup(item)).length,
    };
  });

  const toolEvents = toArray(eventsState).filter((ev) =>
    [
      "CODEX_CMD",
      "MCP_CALL",
      "TAMPERMONKEY_OUTPUT",
      "SEARCH_RESULTS",
      "SEARCH_VERIFICATION",
      "SEARCH_VERIFICATION_AI",
      "SEARCH_VERIFICATION_AI_RESULT",
    ].includes(toStringOr(ev.event, ""))
  );
  const pendingApprovals = toArray(eventsState).filter(
    (ev) => toStringOr(ev.event, "").toUpperCase() === "HUMAN_APPROVAL_REQUIRED"
  );
  const terminalStatus = deriveTerminalStatus(run.status, reportsState);
  const liveStatus = terminalStatus || run.status;

  useEffect(() => {
    eventsRef.current = eventsState;
  }, [eventsState]);

  useEffect(() => {
    reportsRef.current = reportsState;
  }, [reportsState]);

  useEffect(() => {
    let alive = true;
    async function loadRuns() {
      setAvailableRunsLoading(true);
      try {
        const data = await fetchRuns();
        if (alive) {
          setAvailableRuns(Array.isArray(data) ? data : []);
          setAvailableRunsError("");
        }
      } catch (err: unknown) {
        if (alive) {
          setAvailableRuns([]);
          console.error(`[run-detail] load runs failed: ${uiErrorDetail(err)}`);
          setAvailableRunsError(sanitizeUiError(err, "Run list unavailable"));
        }
      } finally {
        if (alive) {
          setAvailableRunsLoading(false);
        }
      }
    }
    void loadRuns();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    async function loadAgentStatus() {
      if (!run?.run_id) {
        return;
      }
      try {
        const data = (await fetchAgentStatus(run.run_id)) as { agents?: Array<Record<string, unknown>> };
        if (alive) {
          setAgentStatus(Array.isArray(data?.agents) ? data.agents : []);
          setAgentStatusError("");
        }
      } catch (err: unknown) {
        if (alive) {
          setAgentStatus([]);
          console.error(`[run-detail] load agent status failed: ${uiErrorDetail(err)}`);
          setAgentStatusError(sanitizeUiError(err, "Agent status unavailable"));
        }
      }
    }
    void loadAgentStatus();
    return () => {
      alive = false;
    };
  }, [run?.run_id]);

  useEffect(() => {
    let alive = true;
    async function loadChainSpec() {
      if (!run?.run_id) {
        return;
      }
      if (!chainReport && !run?.manifest?.chain_id) {
        return;
      }
      setChainSpecLoading(true);
      try {
        const data = await fetchChainSpec(run.run_id);
        if (alive) {
          setChainSpec((data?.data as Record<string, unknown> | null) || null);
          setChainSpecError("");
        }
      } catch (err: unknown) {
        if (alive) {
          setChainSpec(null);
          console.error(`[run-detail] load chain spec failed: ${uiErrorDetail(err)}`);
          setChainSpecError(sanitizeUiError(err, "Chain spec unavailable"));
        }
      } finally {
        if (alive) {
          setChainSpecLoading(false);
        }
      }
    }
    void loadChainSpec();
    return () => {
      alive = false;
    };
  }, [run?.run_id, chainReport, run?.manifest?.chain_id]);

  useEffect(() => {
    let alive = true;
    async function loadToolCalls() {
      if (!run?.run_id) {
        return;
      }
      setToolCallsLoading(true);
      try {
        const payload = await fetchToolCalls(run.run_id);
        if (alive) {
          setToolCalls(Array.isArray(payload?.data) ? payload.data : []);
          setToolCallsError("");
        }
      } catch (err: unknown) {
        console.error(`[run-detail] load tool calls failed: ${uiErrorDetail(err)}`);
        const message = sanitizeUiError(err, "Tool calls unavailable");
        if (alive) {
          setToolCalls([]);
          setToolCallsError(message);
        }
      } finally {
        if (alive) {
          setToolCallsLoading(false);
        }
      }
    }
    void loadToolCalls();
    return () => {
      alive = false;
    };
  }, [run?.run_id]);

  useRunDetailLive({
    runId: run?.run_id,
    runStatus: liveStatus,
    liveEnabled,
    eventsRef,
    reportsRef,
    setEventsState,
    setReportsState,
    setLiveMode,
    setLiveTransport,
    setLiveError,
    setLiveIntervalMs,
    setLiveLagMs,
    setLastRefreshAt,
  });

  async function handleEventInspect(event: EventRecord) {
    const eventName = toStringOr(event?.event, "").toUpperCase();
    const eventTs = toStringOr(event?.ts, "");
    if (!run?.run_id) {
      return;
    }
    if (eventName !== "WORKTREE_CREATED" && eventName !== "MCP_CONCURRENCY_CHECK" && eventName !== "RUNNER_SELECTED") {
      return;
    }
    setTab("logs");
    setDetailPanelFocusRequestKey((current) => current + 1);
    setToolCallsLoading(true);
    setEventInspectFeedback({
      eventName,
      eventTs,
      status: "loading",
      message: `Inspecting ${eventName}${eventTs ? ` (${eventTs})` : ""}. Loading related execution logs...`,
    });
    try {
      const payload = await fetchToolCalls(run.run_id);
      const nextToolCalls = Array.isArray(payload?.data) ? payload.data : [];
      setToolCalls(nextToolCalls);
      setToolCallsError("");
      setEventInspectFeedback({
        eventName,
        eventTs,
        status: "success",
        message:
          nextToolCalls.length > 0
            ? `Inspecting ${eventName}${eventTs ? ` (${eventTs})` : ""}. Found ${nextToolCalls.length} related execution log entr${nextToolCalls.length === 1 ? "y" : "ies"}.`
            : `Inspecting ${eventName}${eventTs ? ` (${eventTs})` : ""}. No related tool calls were found. The current event context is still available.`,
      });
    } catch (err: unknown) {
      console.error(`[run-detail] inspect event load tool calls failed: ${uiErrorDetail(err)}`);
      const message = sanitizeUiError(err, "Related execution logs unavailable");
      setToolCallsError("");
      setEventInspectFeedback({
        eventName,
        eventTs,
        status: "info",
        message: `Inspecting ${eventName}${eventTs ? ` (${eventTs})` : ""}. ${message}. The current panel context is unchanged.`,
      });
    } finally {
      setToolCallsLoading(false);
    }
  }

  async function refreshEvidence() {
    const [eventsResult, reportsResult] = await Promise.allSettled([fetchEvents(run.run_id), fetchReports(run.run_id)]);
    let refreshedAny = false;
    if (eventsResult.status === "fulfilled") {
      const nextEvents = sortEvents(Array.isArray(eventsResult.value) ? eventsResult.value : []);
      eventsRef.current = nextEvents;
      setEventsState(nextEvents);
      refreshedAny = true;
    } else {
      console.error(`[run-detail] refresh events failed: ${uiErrorDetail(eventsResult.reason)}`);
    }
    if (reportsResult.status === "fulfilled") {
      const nextReports = Array.isArray(reportsResult.value) ? reportsResult.value : [];
      reportsRef.current = nextReports;
      setReportsState(nextReports);
      refreshedAny = true;
    } else {
      console.error(`[run-detail] refresh reports failed: ${uiErrorDetail(reportsResult.reason)}`);
    }
    if (refreshedAny) {
      setLastRefreshAt(new Date().toISOString());
    }
    if (eventsResult.status !== "fulfilled" && reportsResult.status !== "fulfilled") {
      throw new Error("Replay refresh failed: neither events nor reports were updated");
    }
  }

  async function handleReplay() {
    setReplayStatus("running");
    setReplayError("");
    try {
      await replayRun(run.run_id, baselineRunId);
      await refreshEvidence();
      setReplayStatus("done");
    } catch (err: unknown) {
      console.error(`[run-detail] replay compare failed: ${uiErrorDetail(err)}`);
      const message = sanitizeUiError(err, "Replay comparison failed");
      setReplayStatus("error");
      setReplayError(message);
    }
  }

  function handleFailedTerminalAction(nextTab: RunDetailTab) {
    setTab(nextTab);
    setFailedTerminalActionFeedback(
      nextTab === "reports"
        ? "Switched to the reports tab below. Continue with the diagnostic report."
        : "Switched to the logs tab below. Continue with the execution log."
    );
    setDetailPanelFocusRequestKey((current) => current + 1);
  }

  return (
    <section className="app-section">
      <div className="section-header">
        <div>
          <h2>Run observation summary</h2>
          <p>Start with status and timeline, then drill into diff, logs, reports, and chain detail.</p>
        </div>
      </div>

      <div className="grid grid-3">
        <RunDetailAgentStatusCard agentStatusError={agentStatusError} agentStatus={agentStatus} />
        <RunDetailStatusContractCard
          run={run}
          schemaVersion={schemaVersion}
          observability={observability}
          traceId={traceId}
          traceUrl={traceUrl}
          workflowId={workflowId}
          workflowStatus={workflowStatus}
          terminalStatus={terminalStatus}
          liveMode={liveMode}
          liveEnabled={liveEnabled}
          onToggleLive={() => setLiveEnabled((prev) => !prev)}
          liveTransport={liveTransport}
          liveIntervalMs={liveIntervalMs}
          liveLagMs={liveLagMs}
          lastRefreshAt={lastRefreshAt}
          liveError={liveError}
          lifecycleRail={lifecycleRail}
          pendingApprovals={pendingApprovals}
          evidenceHashes={evidenceHashes}
          manifestArtifacts={manifestArtifacts}
          onOpenLogs={() => handleFailedTerminalAction("logs")}
          onOpenReports={() => handleFailedTerminalAction("reports")}
          failedTerminalActionFeedback={failedTerminalActionFeedback}
        />
        <Card asChild>
          <section className="app-section" aria-labelledby="event-timeline-title">
            <div className="section-header">
              <h3 data-testid="event-timeline-title" id="event-timeline-title">
                Event timeline
              </h3>
            </div>
            <EventTimeline events={toArray(eventsState)} onEventInspect={(event) => void handleEventInspect(event)} />
          </section>
        </Card>
      </div>

      <section className="app-section" aria-labelledby="run-detail-deep-dive-title">
        <div className="section-header">
          <div>
            <h3 id="run-detail-deep-dive-title">Evidence and execution detail</h3>
            <p>Switch tabs to inspect the diff, tool logs, audit reports, and chain snapshot.</p>
          </div>
        </div>
        {eventInspectFeedback ? (
          <div
            className={`mono ${eventInspectFeedback.status === "error" ? "run-detail-live-error" : "muted"}`}
            role={eventInspectFeedback.status === "error" ? "alert" : "status"}
            aria-live={eventInspectFeedback.status === "error" ? "assertive" : "polite"}
            data-testid="run-detail-event-inspect-feedback"
          >
            {eventInspectFeedback.message}
          </div>
        ) : null}
        <RunDetailDetailPanel
          tab={tab}
          onTabChange={setTab}
          focusRequestKey={detailPanelFocusRequestKey}
          diff={diff}
          allowedPaths={toArray(run.allowed_paths)}
          availableRunsLoading={availableRunsLoading}
          toolCallsLoading={toolCallsLoading}
          chainSpecLoading={chainSpecLoading}
          toolCallsError={toolCallsError}
          toolCalls={toolCalls}
          toolEvents={toolEvents}
          testReport={testReport}
          reviewReport={reviewReport}
          taskResult={taskResult}
          workReport={workReport}
          evidenceReport={evidenceReport}
          incidentPack={incidentPack}
          proofPack={proofPack}
          runCompareReport={runCompareReport}
          availableRunsError={availableRunsError}
          baselineRunId={baselineRunId}
          onBaselineRunIdChange={setBaselineRunId}
          availableRuns={availableRuns}
          onReplay={handleReplay}
          replayStatus={replayStatus}
          replayError={replayError}
          replayReport={replayReport}
          evidence={evidence}
          mismatched={mismatched}
          missing={missing}
          extra={extra}
          summary={summary}
          chainSpecError={chainSpecError}
          chainReport={chainReport}
          chainSpec={chainSpec}
          eventsState={eventsState}
        />
      </section>
    </section>
  );
}
