"use client";

import { DEFAULT_UI_LOCALE, getUiCopy } from "@openvibecoding/frontend-shared/uiCopy";
import Link from "next/link";
import ContractViewer from "../ContractViewer";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import {
  formatBindingReadModelLabel,
  formatRoleBindingRuntimeCapabilitySummary,
  formatRoleBindingRuntimeSummary,
  type EventRecord,
  type RunContract,
  type RunDetailPayload,
} from "../../lib/types";
import type { LifecycleBadge, LiveMode, LiveTransport } from "./runDetailHelpers";
import { badgeVariantForStage, liveBadgeVariant, liveLabel, toArray, toDisplayText, toObject } from "./runDetailHelpers";

type RunDetailStatusContractCardProps = {
  run: RunDetailPayload;
  schemaVersion: string;
  observability: Record<string, unknown>;
  traceId: string;
  traceUrl: string;
  workflowId: string;
  workflowStatus: string;
  terminalStatus: string;
  liveMode: LiveMode;
  liveEnabled: boolean;
  onToggleLive: () => void;
  liveTransport: LiveTransport;
  liveIntervalMs: number;
  liveLagMs: number;
  lastRefreshAt: string;
  liveError: string;
  lifecycleRail: LifecycleBadge[];
  pendingApprovals: EventRecord[];
  evidenceHashes: Record<string, unknown>;
  manifestArtifacts: unknown[];
  completionGovernanceReport: Record<string, unknown>;
  planningContracts: Array<Record<string, unknown>>;
  planningContractsError: string;
  unblockTasks: Array<Record<string, unknown>>;
  unblockTasksError: string;
  contextPackArtifact: Record<string, unknown> | null;
  harnessRequestArtifact: Record<string, unknown> | null;
  onOpenLogs: () => void;
  onOpenReports: () => void;
  failedTerminalActionFeedback: string;
};

export default function RunDetailStatusContractCard({
  run,
  schemaVersion,
  observability,
  traceId,
  traceUrl,
  workflowId,
  workflowStatus,
  terminalStatus,
  liveMode,
  liveEnabled,
  onToggleLive,
  liveTransport,
  liveIntervalMs,
  liveLagMs,
  lastRefreshAt,
  liveError,
  lifecycleRail,
  pendingApprovals,
  evidenceHashes,
  manifestArtifacts,
  completionGovernanceReport,
  planningContracts,
  planningContractsError,
  unblockTasks,
  unblockTasksError,
  contextPackArtifact,
  harnessRequestArtifact,
  onOpenLogs,
  onOpenReports,
  failedTerminalActionFeedback,
}: RunDetailStatusContractCardProps) {
  const bindingReadModelCopy = getUiCopy(DEFAULT_UI_LOCALE).desktop.runDetail.bindingReadModel;
  const completionGovernanceCopy = getUiCopy(DEFAULT_UI_LOCALE).desktop.runDetail.completionGovernance;
  const terminal = terminalStatus.toUpperCase();
  const isTerminal = terminal === "FAILED" || terminal === "ERROR" || terminal === "SUCCESS" || terminal === "DONE" || terminal === "REJECTED";
  const isFailedTerminal = terminal === "FAILED" || terminal === "ERROR" || terminal === "REJECTED";
  const allowedPaths = toArray(run.allowed_paths);
  const evidenceEntries = Object.entries(toObject(evidenceHashes));
  const artifactList = toArray(manifestArtifacts);
  const artifactNames = artifactList
    .map((item) => {
      const record = toObject(item);
      const artifactName = typeof record.name === "string" ? record.name : typeof record.path === "string" ? record.path : "";
      return artifactName.trim();
    })
    .filter(Boolean);
  const lifecycleArtifactLabels = [
    artifactNames.includes("prompt_artifact") || artifactNames.includes("artifacts/prompt_artifact.json")
      ? "Prompt artifact"
      : "",
    artifactNames.includes("planning_wave_plan") || artifactNames.includes("artifacts/planning_wave_plan.json")
      ? "Wave plan"
      : "",
    artifactNames.includes("planning_worker_prompt_contracts") ||
    artifactNames.includes("artifacts/planning_worker_prompt_contracts.json")
      ? "Worker prompt contracts"
      : "",
    artifactNames.includes("planning_unblock_tasks") || artifactNames.includes("artifacts/planning_unblock_tasks.json")
      ? "Unblock tasks"
      : "",
  ].filter(Boolean);
  const continuationOnIncomplete = Array.from(
    new Set(
      planningContracts
        .map((contract) => toDisplayText(toObject(contract.continuation_policy).on_incomplete))
        .filter((value) => value !== "-"),
    ),
  );
  const continuationOnBlocked = Array.from(
    new Set(
      planningContracts
        .map((contract) => toDisplayText(toObject(contract.continuation_policy).on_blocked))
        .filter((value) => value !== "-"),
    ),
  );
  const doneChecks = Array.from(
    new Set(
      planningContracts.flatMap((contract) =>
        toArray(toObject(contract.done_definition).acceptance_checks as unknown[] | null | undefined)
          .map((value) => toDisplayText(value))
          .filter((value) => value !== "-"),
      ),
    ),
  );
  const roleBindingReadModel = run.role_binding_read_model;
  const runtimeCompletionGovernance = toObject(completionGovernanceReport);
  const hasRuntimeCompletionGovernance = Object.keys(runtimeCompletionGovernance).length > 0;
  const runtimeDodChecker = toObject(runtimeCompletionGovernance.dod_checker);
  const runtimeReplyAuditor = toObject(runtimeCompletionGovernance.reply_auditor);
  const runtimeContinuationDecision = toObject(runtimeCompletionGovernance.continuation_decision);
  const runtimeContextPack = toObject(runtimeCompletionGovernance.context_pack);
  const runtimeHarnessRequest = toObject(runtimeCompletionGovernance.harness_request);
  const contextPackRecord = toObject(contextPackArtifact);
  const harnessRequestRecord = toObject(harnessRequestArtifact);
  const runtimeDodRequiredChecks = Array.from(
    new Set(
      toArray(runtimeDodChecker.required_checks as unknown[] | null | undefined)
        .map((value) => toDisplayText(value))
        .filter((value) => value !== "-"),
    ),
  );
  const runtimeDodUnmetChecks = Array.from(
    new Set(
      toArray(runtimeDodChecker.unmet_checks as unknown[] | null | undefined)
        .map((value) => toDisplayText(value))
        .filter((value) => value !== "-"),
    ),
  );
  const unblockTaskOwners = Array.from(
    new Set(unblockTasks.map((task) => toDisplayText(task.owner)).filter((value) => value !== "-")),
  );
  const unblockTaskModes = Array.from(
    new Set(unblockTasks.map((task) => toDisplayText(task.mode)).filter((value) => value !== "-")),
  );
  const unblockTaskTriggers = Array.from(
    new Set(unblockTasks.map((task) => toDisplayText(task.trigger)).filter((value) => value !== "-")),
  );

  return (
    <Card>
      <h3>Status & Contract</h3>
      <div className="mono" data-testid="run-id">
        Run ID: {run.run_id}
      </div>
      <div className="mono" data-testid="task-id">
        Task ID: {run.task_id}
      </div>
      <div className="mono" data-testid="run-status">
        Status: {run.status}
      </div>
      <div className="mono">Failure reason: {toDisplayText(run?.manifest?.failure_reason)}</div>
      <div className="mono">Contract version: {schemaVersion}</div>
      <div className="mono">Orchestrator version: {toDisplayText(run?.manifest?.versions?.orchestrator)}</div>
      <div className="mono">Observability: {observability?.enabled ? "Enabled" : "Disabled"}</div>
      <div className="mono">Trace ID: {toDisplayText(traceId)}</div>
      {traceUrl ? (
        <div className="mono">
          Trace link:{" "}
          <a href={traceUrl} target="_blank" rel="noopener noreferrer">
            {traceUrl}
          </a>
        </div>
      ) : null}
      <div className="mono">
        Workflow ID:{" "}
        {workflowId ? <Link href={`/workflows/${encodeURIComponent(workflowId)}`}>{workflowId}</Link> : "-"}
      </div>
      <div className="mono">Workflow status: {toDisplayText(workflowStatus)}</div>
      <div className="mono">Terminal status: {toDisplayText(terminalStatus)}</div>
      <div className="run-detail-live-panel">
        <div className="run-detail-live-head">
          <Badge variant={isTerminal ? "success" : liveBadgeVariant(liveMode)}>
            {isTerminal ? "Terminal snapshot" : liveLabel(liveMode)}
          </Badge>
          {isTerminal ? null : (
            <Button variant="secondary" aria-label={liveEnabled ? "Pause live refresh" : "Resume live refresh"} onClick={onToggleLive}>
              {liveEnabled ? "Pause live" : "Resume live"}
            </Button>
          )}
        </div>
        <div className="mono">Live transport: {liveTransport}</div>
        <div className="mono">Refresh interval (ms): {liveIntervalMs}</div>
        <div className="mono">Event lag (ms): {liveLagMs}</div>
        <div className="mono">Last refresh: {toDisplayText(lastRefreshAt)}</div>
        {liveError ? (
          <div className="mono run-detail-live-error" role="alert" aria-live="assertive">
            {liveError}
          </div>
        ) : null}
      </div>
      {isFailedTerminal ? (
        <div className="run-detail-section" data-testid="failed-terminal-actions">
          <strong>Failure diagnostics</strong>
          <div className="run-detail-inline-gap-lg">
            <Button variant="secondary" onClick={onOpenReports}>
              Open diagnostic report
            </Button>
            <Button variant="secondary" onClick={onOpenLogs}>
              Open execution logs
            </Button>
          </div>
          {failedTerminalActionFeedback ? (
            <div
              className="mono muted"
              role="status"
              aria-live="polite"
              data-testid="failed-terminal-action-feedback"
            >
              {failedTerminalActionFeedback}
            </div>
          ) : null}
        </div>
      ) : null}
      {lifecycleRail.length > 0 ? (
        <>
          <div className="mono run-detail-section-label">Lifecycle rail (PM -&gt; TL -&gt; Worker agents -&gt; Review agents -&gt; Tests -&gt; TL -&gt; PM)</div>
          <div className="run-detail-chip-row">
            {lifecycleRail.map((item) => (
              <Badge key={item.key} variant={badgeVariantForStage(item.status)} title={item.detail}>
                {item.label}: {item.detail}
              </Badge>
            ))}
          </div>
        </>
      ) : null}
      {pendingApprovals.length > 0 ? (
        <div className="alert alert-danger run-detail-alert-gap">
          <div className="mono">Detected {pendingApprovals.length} HUMAN_APPROVAL_REQUIRED event{pendingApprovals.length === 1 ? "" : "s"}.</div>
          <div className="mono run-detail-inline-gap">Open the manual approvals page to unblock the run and continue.</div>
          <div className="run-detail-inline-gap-lg">
            <Button asChild>
              <Link href="/god-mode">Open manual approvals</Link>
            </Button>
          </div>
        </div>
      ) : null}
      <div className="mono" data-testid="allowed-paths-label">
        Allowed paths:
      </div>
      <div className="mono muted">{allowedPaths.length} path{allowedPaths.length === 1 ? "" : "s"}</div>
      <details>
        <summary className="mono">Expand path details</summary>
        <pre className="mono" data-testid="allowed-paths-content">
          {JSON.stringify(allowedPaths, null, 2)}
        </pre>
      </details>
      <div className="mono">Evidence hashes:</div>
      <div className="mono muted">{evidenceEntries.length} key{evidenceEntries.length === 1 ? "" : "s"}</div>
      <details>
        <summary className="mono">Expand evidence hashes</summary>
        <pre className="mono">{JSON.stringify(toObject(evidenceHashes), null, 2)}</pre>
      </details>
      {roleBindingReadModel ? (
        <div className="run-detail-section" data-testid="run-role-binding-read-model">
          <div className="mono run-detail-section-label">{bindingReadModelCopy.title}</div>
          <div className="mono">{bindingReadModelCopy.authority}: {toDisplayText(roleBindingReadModel.authority)}</div>
          <div className="mono">{bindingReadModelCopy.source}: {toDisplayText(roleBindingReadModel.source)}</div>
          <div className="mono">
            {bindingReadModelCopy.executionAuthority}: {toDisplayText(roleBindingReadModel.execution_authority)}
          </div>
          <div className="mono">
            {bindingReadModelCopy.skillsBundle}: {formatBindingReadModelLabel(roleBindingReadModel.skills_bundle_ref)}
          </div>
          <div className="mono">
            {bindingReadModelCopy.mcpBundle}: {formatBindingReadModelLabel(roleBindingReadModel.mcp_bundle_ref)}
          </div>
          <div className="mono">
            {bindingReadModelCopy.runtimeBinding}: {formatRoleBindingRuntimeSummary(roleBindingReadModel)}
          </div>
          <div className="mono">
            {bindingReadModelCopy.runtimeCapability}: {toDisplayText(roleBindingReadModel.runtime_binding?.capability?.lane)}
          </div>
          <div className="mono">
            {bindingReadModelCopy.toolExecution}: {formatRoleBindingRuntimeCapabilitySummary(roleBindingReadModel)}
          </div>
          <div className="mono muted">
            {bindingReadModelCopy.readOnlyNote}
          </div>
        </div>
      ) : null}
      {hasRuntimeCompletionGovernance || planningContracts.length > 0 || planningContractsError || unblockTasks.length > 0 || unblockTasksError ? (
        <div className="run-detail-section" data-testid="run-completion-governance-summary">
          <div className="mono run-detail-section-label">{completionGovernanceCopy.title}</div>
          {hasRuntimeCompletionGovernance ? (
            <div data-testid="run-completion-governance-report">
              <div className="mono run-detail-section-label">{completionGovernanceCopy.runtimeTitle}</div>
              <div className="mono">{completionGovernanceCopy.overallVerdict}: {toDisplayText(runtimeCompletionGovernance.overall_verdict)}</div>
              <div className="mono">{completionGovernanceCopy.reportAuthority}: {toDisplayText(runtimeCompletionGovernance.authority)}</div>
              <div className="mono">{completionGovernanceCopy.reportSource}: {toDisplayText(runtimeCompletionGovernance.source)}</div>
              <div className="mono">{completionGovernanceCopy.reportExecutionAuthority}: {toDisplayText(runtimeCompletionGovernance.execution_authority)}</div>
              <div className="mono">{completionGovernanceCopy.dodChecker}: {toDisplayText(runtimeDodChecker.status)}</div>
              {toDisplayText(runtimeDodChecker.summary) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.dodSummary}: {toDisplayText(runtimeDodChecker.summary)}</div>
              ) : null}
              {runtimeDodRequiredChecks.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.dodRequiredChecks}: {runtimeDodRequiredChecks.join(" / ")}</div>
              ) : null}
              {runtimeDodUnmetChecks.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.dodUnmetChecks}: {runtimeDodUnmetChecks.join(" / ")}</div>
              ) : null}
              <div className="mono">{completionGovernanceCopy.replyAuditor}: {toDisplayText(runtimeReplyAuditor.status)}</div>
              {toDisplayText(runtimeReplyAuditor.summary) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.replySummary}: {toDisplayText(runtimeReplyAuditor.summary)}</div>
              ) : null}
              <div className="mono">{completionGovernanceCopy.continuationDecision}: {toDisplayText(runtimeContinuationDecision.selected_action)}</div>
              {toDisplayText(runtimeContinuationDecision.summary) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.continuationSummary}: {toDisplayText(runtimeContinuationDecision.summary)}</div>
              ) : null}
              {toDisplayText(runtimeContinuationDecision.action_source) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.actionSource}: {toDisplayText(runtimeContinuationDecision.action_source)}</div>
              ) : null}
              {toDisplayText(runtimeContinuationDecision.unblock_task_id) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.selectedUnblockTask}: {toDisplayText(runtimeContinuationDecision.unblock_task_id)}</div>
              ) : null}
              <div className="mono">{completionGovernanceCopy.contextPack}: {toDisplayText(runtimeContextPack.status)}</div>
              {toDisplayText(runtimeContextPack.summary) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.contextPackSummary}: {toDisplayText(runtimeContextPack.summary)}</div>
              ) : null}
              {toDisplayText(contextPackRecord.pack_id) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.contextPackId}: {toDisplayText(contextPackRecord.pack_id)}</div>
              ) : null}
              {toDisplayText(contextPackRecord.trigger_reason) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.contextPackTrigger}: {toDisplayText(contextPackRecord.trigger_reason)}</div>
              ) : null}
              <div className="mono">{completionGovernanceCopy.harnessRequest}: {toDisplayText(runtimeHarnessRequest.status)}</div>
              {toDisplayText(runtimeHarnessRequest.summary) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.harnessRequestSummary}: {toDisplayText(runtimeHarnessRequest.summary)}</div>
              ) : null}
              {toDisplayText(harnessRequestRecord.request_id) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.harnessRequestId}: {toDisplayText(harnessRequestRecord.request_id)}</div>
              ) : null}
              {toDisplayText(harnessRequestRecord.scope) !== "-" ? (
                <div className="mono">{completionGovernanceCopy.harnessRequestScope}: {toDisplayText(harnessRequestRecord.scope)}</div>
              ) : null}
              {harnessRequestRecord.approval_required !== undefined ? (
                <div className="mono">{completionGovernanceCopy.harnessRequestApproval}: {toDisplayText(harnessRequestRecord.approval_required)}</div>
              ) : null}
              <div className="mono muted">{completionGovernanceCopy.runtimeNote}</div>
            </div>
          ) : null}
          {planningContracts.length > 0 || planningContractsError || unblockTasks.length > 0 || unblockTasksError ? (
            <>
              {hasRuntimeCompletionGovernance ? (
                <div className="mono run-detail-section-label">{completionGovernanceCopy.planningFallbackTitle}</div>
              ) : null}
              <div className="mono">{completionGovernanceCopy.workerPromptContracts}: {planningContracts.length}</div>
              {unblockTasks.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.unblockTasks}: {unblockTasks.length}</div>
              ) : null}
              {continuationOnIncomplete.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.onIncomplete}: {continuationOnIncomplete.join(" / ")}</div>
              ) : null}
              {continuationOnBlocked.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.onBlocked}: {continuationOnBlocked.join(" / ")}</div>
              ) : null}
              {doneChecks.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.doneChecks}: {doneChecks.join(" / ")}</div>
              ) : null}
              {unblockTaskOwners.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.unblockOwner}: {unblockTaskOwners.join(" / ")}</div>
              ) : null}
              {unblockTaskModes.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.unblockMode}: {unblockTaskModes.join(" / ")}</div>
              ) : null}
              {unblockTaskTriggers.length > 0 ? (
                <div className="mono">{completionGovernanceCopy.unblockTrigger}: {unblockTaskTriggers.join(" / ")}</div>
              ) : null}
              {planningContractsError || unblockTasksError ? (
                <div className="mono muted">{planningContractsError || unblockTasksError}</div>
              ) : (
                <div className="mono muted">{completionGovernanceCopy.advisoryNote}</div>
              )}
            </>
          ) : null}
        </div>
      ) : null}
      <div className="mono">Manifest artifacts:</div>
      <div className="mono muted">{artifactList.length} artifact{artifactList.length === 1 ? "" : "s"}</div>
      {lifecycleArtifactLabels.length > 0 ? (
        <div className="mono">Lifecycle artifacts: {lifecycleArtifactLabels.join(" / ")}</div>
      ) : null}
      <details>
        <summary className="mono">Expand artifact list</summary>
        <pre className="mono">{JSON.stringify(artifactList, null, 2)}</pre>
      </details>
      <ContractViewer contract={(run.contract ?? {}) as RunContract} schemaVersion={schemaVersion} />
    </Card>
  );
}
