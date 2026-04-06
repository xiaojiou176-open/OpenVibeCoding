import type { RefObject } from "react";
import PmStageContextPanel from "../../../components/pm/PmStageContextPanel";
import FlightPlanCopilotPanel from "../../../components/control-plane/FlightPlanCopilotPanel";
import { GENERAL_TASK_TEMPLATE, findTaskPackByTemplate, type TaskPackFieldDefinition } from "../../../lib/types";
import { statusVariant } from "../../../lib/statusPresentation";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input, Select, Textarea } from "../../../components/ui/input";
import type { BrowserPreset, ChainNode, ExecutionPlanReport, NewsDigestTimeRange, PMTaskTemplate, TaskPackManifest } from "./PMIntakeFeature.shared";

type PmJourneyContext = Parameters<typeof PmStageContextPanel>[0]["context"];

type Props = {
  pmJourneyContext: PmJourneyContext;
  runId: string;
  intakeId: string;
  liveRole: string;
  currentSessionStatus: string;
  chainNodes: ChainNode[];
  hoveredChainRole: ChainNode["role"] | null;
  onHoveredChainRoleChange: (role: ChainNode["role"] | null) => void;
  progressFeed: string[];
  questions: string[];
  taskTemplate?: PMTaskTemplate;
  onTaskTemplateChange?: (value: PMTaskTemplate) => void;
  taskPacks?: TaskPackManifest[];
  taskPacksLoading?: boolean;
  taskPacksError?: string;
  taskPackFieldValues?: Record<string, string>;
  onTaskPackFieldChange?: (fieldId: string, value: string) => void;
  newsDigestTopic?: string;
  onNewsDigestTopicChange?: (value: string) => void;
  newsDigestSources?: string;
  onNewsDigestSourcesChange?: (value: string) => void;
  newsDigestTimeRange?: NewsDigestTimeRange;
  onNewsDigestTimeRangeChange?: (value: NewsDigestTimeRange) => void;
  newsDigestMaxResults?: string;
  onNewsDigestMaxResultsChange?: (value: string) => void;
  pageBriefUrl?: string;
  onPageBriefUrlChange?: (value: string) => void;
  pageBriefFocus?: string;
  onPageBriefFocusChange?: (value: string) => void;
  requesterRole: string;
  onRequesterRoleChange: (value: string) => void;
  browserPreset: BrowserPreset;
  onBrowserPresetChange: (value: BrowserPreset) => void;
  canUseCustomPreset: boolean;
  customBrowserPolicy: string;
  onCustomBrowserPolicyChange: (value: string) => void;
  error: string;
  objective: string;
  onObjectiveChange: (value: string) => void;
  allowedPaths: string;
  onAllowedPathsChange: (value: string) => void;
  constraints: string;
  onConstraintsChange: (value: string) => void;
  searchQueries: string;
  onSearchQueriesChange: (value: string) => void;
  chatFlowBusy: boolean;
  onCreate: () => void;
  onAnswer: () => void;
  onPreview: () => void;
  onRun: () => void;
  hasIntakeId: boolean;
  plan: unknown;
  taskChain: unknown;
  executionPlanPreview: ExecutionPlanReport | null;
  executionPlanPreviewBusy: boolean;
  executionPlanPreviewError: string;
  chainPanelRef: RefObject<HTMLElement | null>;
};

function compactList(values: string[], limit = 3): string {
  const filtered = values.map((value) => value.trim()).filter(Boolean);
  if (filtered.length === 0) {
    return "-";
  }
  if (filtered.length <= limit) {
    return filtered.join(", ");
  }
  return `${filtered.slice(0, limit).join(", ")} +${filtered.length - limit} more`;
}

function summarizeAcceptanceChecks(report: ExecutionPlanReport): string {
  const checks = report.acceptance_tests
    .map((item, index) => {
      const record = (typeof item === "object" && item ? item : {}) as Record<string, unknown>;
      const label =
        (typeof record.name === "string" && record.name.trim()) ||
        (typeof record.cmd === "string" && record.cmd.trim()) ||
        (typeof record.command === "string" && record.command.trim()) ||
        `check ${index + 1}`;
      return label;
    })
    .filter(Boolean);
  return compactList(checks);
}

function summarizeCapabilityTriggers(report: ExecutionPlanReport): string[] {
  const triggers: string[] = [];
  if (report.search_queries.length > 0) {
    triggers.push(`Search (${report.search_queries.length} query${report.search_queries.length === 1 ? "" : "ies"})`);
  }
  if (
    report.task_template === "page_brief" ||
    report.browser_policy_preset === "custom" ||
    Boolean(report.effective_browser_policy) ||
    report.predicted_artifacts.some((item) => item.toLowerCase().includes("browser"))
  ) {
    triggers.push("Browser");
  }
  if (report.requires_human_approval) {
    triggers.push("Manual approval");
  }
  return triggers;
}

export default function PMIntakeRightSidebar(props: Props) {
  const {
    pmJourneyContext,
    runId,
    intakeId,
    liveRole,
    currentSessionStatus,
    chainNodes,
    hoveredChainRole,
    onHoveredChainRoleChange,
    progressFeed,
    questions,
    taskTemplate = "general",
    onTaskTemplateChange = () => {},
    taskPacks = [],
    taskPacksLoading = false,
    taskPacksError = "",
    taskPackFieldValues = {},
    onTaskPackFieldChange = () => {},
    newsDigestTopic = "",
    onNewsDigestTopicChange = () => {},
    newsDigestSources = "",
    onNewsDigestSourcesChange = () => {},
    newsDigestTimeRange = "24h",
    onNewsDigestTimeRangeChange = () => {},
    newsDigestMaxResults = "5",
    onNewsDigestMaxResultsChange = () => {},
    pageBriefUrl = "",
    onPageBriefUrlChange = () => {},
    pageBriefFocus = "",
    onPageBriefFocusChange = () => {},
    requesterRole,
    onRequesterRoleChange,
    browserPreset,
    onBrowserPresetChange,
    canUseCustomPreset,
    customBrowserPolicy,
    onCustomBrowserPolicyChange,
    error,
    objective,
    onObjectiveChange,
    allowedPaths,
    onAllowedPathsChange,
    constraints,
    onConstraintsChange,
    searchQueries,
    onSearchQueriesChange,
    chatFlowBusy,
    onCreate,
    onAnswer,
    onPreview,
    onRun,
    hasIntakeId,
    plan,
    taskChain,
    executionPlanPreview,
    executionPlanPreviewBusy,
    executionPlanPreviewError,
    chainPanelRef,
  } = props;
  const selectedTaskPack = findTaskPackByTemplate(taskPacks, taskTemplate);
  const resolvedTaskPackFieldValues =
    Object.keys(taskPackFieldValues).length > 0
      ? taskPackFieldValues
      : {
          topic: newsDigestTopic,
          sources: newsDigestSources,
          time_range: newsDigestTimeRange,
          max_results: newsDigestMaxResults,
          url: pageBriefUrl,
          focus: pageBriefFocus,
        };

  const handleTaskPackFieldChange = (fieldId: string, value: string) => {
    if (Object.keys(taskPackFieldValues).length > 0) {
      onTaskPackFieldChange(fieldId, value);
      return;
    }
    if (fieldId === "topic") {
      onNewsDigestTopicChange(value);
      return;
    }
    if (fieldId === "sources") {
      onNewsDigestSourcesChange(value);
      return;
    }
    if (fieldId === "time_range") {
      onNewsDigestTimeRangeChange(value as NewsDigestTimeRange);
      return;
    }
    if (fieldId === "max_results") {
      onNewsDigestMaxResultsChange(value);
      return;
    }
    if (fieldId === "url") {
      onPageBriefUrlChange(value);
      return;
    }
    if (fieldId === "focus") {
      onPageBriefFocusChange(value);
    }
  };

  const renderTaskPackField = (field: TaskPackFieldDefinition) => {
    const fieldValue = resolvedTaskPackFieldValues[field.field_id] ?? "";
    if (field.control === "textarea") {
      return (
        <label key={field.field_id} className="pm-field">
          <span className="pm-field-label">{field.label}</span>
          <Textarea
            variant="unstyled"
            value={fieldValue}
            onChange={(event) => handleTaskPackFieldChange(field.field_id, event.target.value)}
            rows={field.field_id === "sources" ? 4 : 3}
            className="pm-input pm-input-multiline"
            aria-label={field.label}
            placeholder={field.placeholder}
          />
          {field.help_text ? <span className="muted">{field.help_text}</span> : null}
        </label>
      );
    }
    if (field.control === "select") {
      return (
        <label key={field.field_id} className="pm-field">
          <span className="pm-field-label">{field.label}</span>
          <Select
            value={fieldValue}
            onChange={(event) => handleTaskPackFieldChange(field.field_id, event.target.value)}
            className="pm-input"
            aria-label={field.label}
          >
            {(field.options || []).map((option) => (
              <option key={`${field.field_id}-${option.value}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          {field.help_text ? <span className="muted">{field.help_text}</span> : null}
        </label>
      );
    }
    return (
      <label key={field.field_id} className="pm-field">
        <span className="pm-field-label">{field.label}</span>
        <Input
          variant="unstyled"
          type={field.control === "number" ? "number" : field.control === "url" ? "url" : "text"}
          min={field.control === "number" ? field.min : undefined}
          max={field.control === "number" ? field.max : undefined}
          value={fieldValue}
          onChange={(event) => handleTaskPackFieldChange(field.field_id, event.target.value)}
          className="pm-input"
          aria-label={field.label}
          placeholder={field.placeholder}
        />
        {field.help_text ? <span className="muted">{field.help_text}</span> : null}
      </label>
    );
  };

  const flightPlanCapabilityTriggers = executionPlanPreview ? summarizeCapabilityTriggers(executionPlanPreview) : [];
  const flightPlanAllowedPaths = executionPlanPreview ? compactList(executionPlanPreview.allowed_paths) : "-";
  const flightPlanPredictedReports = executionPlanPreview ? compactList(executionPlanPreview.predicted_reports) : "-";
  const flightPlanPredictedArtifacts = executionPlanPreview ? compactList(executionPlanPreview.predicted_artifacts) : "-";
  const flightPlanAcceptanceChecks = executionPlanPreview ? summarizeAcceptanceChecks(executionPlanPreview) : "-";

  return (
    <aside className="pm-claude-right" aria-label="Context sidebar">
      <PmStageContextPanel
        context={pmJourneyContext}
        runId={runId}
        intakeId={intakeId}
        liveRole={liveRole}
        sessionStatus={currentSessionStatus}
      />

      <section className="pm-chain-card" ref={chainPanelRef} tabIndex={-1} aria-label="Command Chain panel">
        <h2 className="pm-section-title">Command Chain</h2>
        <div className="pm-chain-flow" role="list" aria-label="Agent workflow">
          {chainNodes.map((node, index) => {
            const next = chainNodes[index + 1];
            const edgeState =
              node.state === "done" && (next?.state === "done" || next?.state === "active")
                ? "done"
                : node.state === "active"
                  ? "active"
                  : "idle";
            return (
              <div key={node.role} className="pm-chain-step" role="listitem">
                <Button
                  variant="unstyled"
                  className={`pm-chain-node is-${node.state}${hoveredChainRole === node.role ? " is-linked" : ""}${hoveredChainRole && hoveredChainRole !== node.role ? " is-dimmed" : ""}`}
                  aria-pressed={hoveredChainRole === node.role}
                  onMouseEnter={() => onHoveredChainRoleChange(node.role)}
                  onMouseLeave={() => onHoveredChainRoleChange(null)}
                  onFocus={() => onHoveredChainRoleChange(node.role)}
                  onBlur={() => onHoveredChainRoleChange(null)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onHoveredChainRoleChange(node.role);
                    }
                    if (event.key === "Escape") {
                      onHoveredChainRoleChange(null);
                    }
                  }}
                >
                  <div className="pm-chain-node-head">
                    <strong>{node.label}</strong>
                    <span>{node.state === "active" ? "Running" : node.state === "done" ? "Done" : "Idle"}</span>
                  </div>
                  <p>{node.hint}</p>
                </Button>
                {index < chainNodes.length - 1 && <div className={`pm-chain-edge is-${edgeState}`} aria-hidden="true" />}
              </div>
            );
          })}
        </div>

        {progressFeed.length > 0 && (
          <div className="pm-progress-feed" aria-label="Progress feed">
            <h3>Progress</h3>
            <ul className="pm-question-list">
              {progressFeed.map((line, index) => (
                <li key={`${line}-${index}`}>{line}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="pm-chain-card pm-runtime-card">
        <h2 className="pm-section-title">Runtime</h2>
        <div className="pm-runtime-grid">
          <div className="pm-runtime-row">
            <span className="pm-runtime-key">session</span>
            <code className="pm-runtime-val">{intakeId || "-"}</code>
          </div>
          <div className="pm-runtime-row">
            <span className="pm-runtime-key">run_id</span>
            <code className="pm-runtime-val">{runId || "-"}</code>
          </div>
          <div className="pm-runtime-row">
            <span className="pm-runtime-key">active</span>
            <code className="pm-runtime-val">{liveRole || "-"}</code>
          </div>
          <div className="pm-runtime-row">
            <span className="pm-runtime-key">status</span>
            <Badge variant={statusVariant(currentSessionStatus)}>
              {currentSessionStatus || "-"}
            </Badge>
          </div>
        </div>
      </section>

      {questions.length > 0 && (
        <section className="pm-chain-card">
          <h2 className="pm-section-title">Clarifiers</h2>
          <ul className="pm-question-list">
            {questions.map((q, i) => <li key={`${q}-${i}`}>{q}</li>)}
          </ul>
        </section>
      )}

      <section className="pm-chain-card">
        <h2 className="pm-section-title">Public task templates</h2>
        {taskPacksError ? <p className="alert alert-warning">{taskPacksError}</p> : null}
        <div className="pm-settings-grid">
          <label className="pm-field">
            <span className="pm-field-label">Template</span>
            <Select
              value={taskTemplate}
              onChange={(event) => onTaskTemplateChange(event.target.value as PMTaskTemplate)}
              className="pm-input"
              aria-label="Public task template"
            >
              {taskPacksLoading ? <option value={taskTemplate}>Loading task packs...</option> : null}
              {taskPacks.map((pack) => (
                <option key={pack.pack_id} value={pack.task_template}>
                  {pack.ui_hint?.default_label || pack.task_template}
                </option>
              ))}
              <option value={GENERAL_TASK_TEMPLATE}>{GENERAL_TASK_TEMPLATE}</option>
            </Select>
          </label>
          {selectedTaskPack ? (
            <div className="pm-field">
              <span className="pm-field-label">Pack summary</span>
              <p className="muted">
                {selectedTaskPack.description}
              </p>
              {selectedTaskPack.evidence_contract?.primary_report ? (
                <p className="muted">Primary report: {selectedTaskPack.evidence_contract.primary_report}</p>
              ) : null}
            </div>
          ) : null}
          {selectedTaskPack ? selectedTaskPack.input_fields.map((field) => renderTaskPackField(field)) : null}
        </div>
        <p className="muted">
          Public paths default to public, read-only, no-login sources. Advanced browser policy stays in the operator area instead of the default entrypoint.
        </p>
      </section>

      <details className="pm-chain-card">
        <summary className="pm-details-summary">Advanced / Operator parameters</summary>
        <div className="pm-settings-grid">
          <label className="pm-field">
            <span className="pm-field-label">Requester role</span>
            <Select value={requesterRole} onChange={(event) => onRequesterRoleChange(event.target.value)} className="pm-input" aria-label="Requester role">
              <option value="PM">PM</option>
              <option value="TECH_LEAD">TECH_LEAD</option>
              <option value="WORKER">WORKER</option>
              <option value="REVIEWER">REVIEWER</option>
              <option value="TESTER">TESTER</option>
              <option value="OPS">OPS</option>
              <option value="OWNER">OWNER</option>
              <option value="ARCHITECT">ARCHITECT</option>
            </Select>
          </label>
          <label className="pm-field">
            <span className="pm-field-label">Browser preset</span>
            <Select
              value={browserPreset}
              onChange={(event) => onBrowserPresetChange(event.target.value as BrowserPreset)}
              className="pm-input"
              aria-label="Browser preset"
            >
              <option value="safe">safe</option>
              <option value="balanced">balanced</option>
              <option value="aggressive">aggressive</option>
              <option value="custom" disabled={!canUseCustomPreset}>custom</option>
            </Select>
          </label>
        </div>
        {browserPreset === "custom" && (
          <Textarea
            variant="unstyled"
            value={customBrowserPolicy}
            onChange={(event) => onCustomBrowserPolicyChange(event.target.value)}
            rows={5}
            className="pm-input pm-input-multiline pm-code-input"
            aria-label="Custom browser policy JSON"
          />
        )}
      </details>

      <details className="pm-chain-card">
        <summary className="pm-details-summary">Advanced parameters</summary>
        {error && <p className="alert alert-danger" role="alert">{error}</p>}
        <div className="pm-settings-grid">
          <label className="pm-field">
            <span className="pm-field-label">Objective</span>
            <Textarea variant="unstyled" value={objective} onChange={(event) => onObjectiveChange(event.target.value)} rows={2} className="pm-input pm-input-multiline" />
          </label>
          <label className="pm-field">
            <span className="pm-field-label">Allowed paths</span>
            <Textarea variant="unstyled" value={allowedPaths} onChange={(event) => onAllowedPathsChange(event.target.value)} rows={2} className="pm-input pm-input-multiline" />
          </label>
          <label className="pm-field">
            <span className="pm-field-label">Constraints / preferences</span>
            <Textarea variant="unstyled" value={constraints} onChange={(event) => onConstraintsChange(event.target.value)} rows={2} className="pm-input pm-input-multiline" />
          </label>
          <label className="pm-field">
            <span className="pm-field-label">Search queries</span>
            <Textarea variant="unstyled" value={searchQueries} onChange={(event) => onSearchQueriesChange(event.target.value)} rows={2} className="pm-input pm-input-multiline" />
          </label>
        </div>
        <div className="pm-actions">
          <Button variant="ghost" disabled={chatFlowBusy} onClick={() => onCreate()}>
            Generate questions
          </Button>
          <Button variant="ghost" disabled={chatFlowBusy || !hasIntakeId} onClick={() => onAnswer()}>
            Generate plan
          </Button>
          <Button variant="secondary" disabled={chatFlowBusy || executionPlanPreviewBusy} onClick={() => onPreview()}>
            {executionPlanPreviewBusy ? "Building Flight Plan..." : "Preview Flight Plan"}
          </Button>
          <Button variant="default" disabled={chatFlowBusy || !hasIntakeId} onClick={() => onRun()}>
            Start execution
          </Button>
        </div>
        {executionPlanPreviewError ? (
          <p className="alert alert-danger" role="alert">
            {executionPlanPreviewError}
          </p>
        ) : null}
        {executionPlanPreview ? (
          <section className="pm-chain-card" aria-label="Flight Plan preview">
            <h3 className="pm-section-title">Flight Plan</h3>
            <p className="muted">
              Advisory only: use this checklist to understand the planned contract and gates before starting execution.
              The run bundle becomes the truth source only after execution actually starts.
            </p>
            <div className="mono">{executionPlanPreview.summary}</div>
            <div className="pm-runtime-grid">
              <div className="pm-runtime-row">
                <span className="pm-runtime-key">Owner</span>
                <code className="pm-runtime-val">{executionPlanPreview.assigned_role || "-"}</code>
              </div>
              <div className="pm-runtime-row">
                <span className="pm-runtime-key">Approval</span>
                <code className="pm-runtime-val">
                  {executionPlanPreview.requires_human_approval ? "Manual approval likely" : "No manual approval expected"}
                </code>
              </div>
              <div className="pm-runtime-row">
                <span className="pm-runtime-key">Reports</span>
                <code className="pm-runtime-val">{executionPlanPreview.predicted_reports.length}</code>
              </div>
              <div className="pm-runtime-row">
                <span className="pm-runtime-key">Artifacts</span>
                <code className="pm-runtime-val">{executionPlanPreview.predicted_artifacts.length}</code>
              </div>
            </div>
            <div className="stack-gap-2">
              <div>
                <strong>Sign-off checklist</strong>
                <ul className="pm-question-list">
                  <li>Contract summary: {executionPlanPreview.objective}</li>
                  <li>Scope boundary: {executionPlanPreview.allowed_paths.length} allowed path entries, starting with {flightPlanAllowedPaths}</li>
                  <li>Acceptance checks: {flightPlanAcceptanceChecks}</li>
                  <li>Expected outputs: reports {flightPlanPredictedReports}; artifacts {flightPlanPredictedArtifacts}</li>
                  <li>Approval risk: {executionPlanPreview.requires_human_approval ? "Manual approval is likely before completion." : "No manual approval is expected on the current plan."}</li>
                  <li>Capability triggers: {flightPlanCapabilityTriggers.length > 0 ? flightPlanCapabilityTriggers.join(", ") : "No extra tool trigger is predicted."}</li>
                </ul>
              </div>
              {executionPlanPreview.notes.length > 0 ? (
                <div>
                  <strong>Operator notes</strong>
                  <ul className="pm-question-list">
                    {executionPlanPreview.notes.map((note, index) => (
                      <li key={`${note}-${index}`}>{note}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
            {executionPlanPreview.questions.length > 0 ? (
              <>
                <strong>Clarifiers still open</strong>
                <ul className="pm-question-list">
                  {executionPlanPreview.questions.map((question, index) => (
                    <li key={`${question}-${index}`}>{question}</li>
                  ))}
                </ul>
              </>
            ) : null}
            {executionPlanPreview.warnings.length > 0 ? (
              <>
                <strong>Risk gates</strong>
                <ul className="pm-question-list">
                  {executionPlanPreview.warnings.map((warning, index) => (
                    <li key={`${warning}-${index}`}>{warning}</li>
                  ))}
                </ul>
              </>
            ) : null}
            <details>
              <summary className="pm-details-summary">Contract preview excerpts</summary>
              <div className="mono">allowed paths: {flightPlanAllowedPaths}</div>
              <div className="mono">acceptance checks: {flightPlanAcceptanceChecks}</div>
              <div className="mono">reports: {flightPlanPredictedReports}</div>
              <div className="mono">artifacts: {flightPlanPredictedArtifacts}</div>
              <div className="mono">
                assigned agent: {executionPlanPreview.contract_preview.assigned_agent?.role || executionPlanPreview.assigned_role || "-"}
              </div>
              <div className="mono">
                owner agent: {executionPlanPreview.contract_preview.owner_agent?.role || "-"}
              </div>
            </details>
            <FlightPlanCopilotPanel
              preview={executionPlanPreview}
              title="Flight Plan copilot"
              intro="Generate one advisory-only brief grounded in the current execution plan preview. This explains pre-run risk and expected proof surfaces; it does not replace run truth."
              buttonLabel="Explain this Flight Plan"
            />
          </section>
        ) : null}
        {plan || taskChain ? (
          <details>
            <summary className="pm-details-summary">Advanced planning payloads</summary>
            {plan ? <pre className="mono pm-code-block">{JSON.stringify(plan, null, 2)}</pre> : null}
            {taskChain ? <pre className="mono pm-code-block">{JSON.stringify(taskChain, null, 2)}</pre> : null}
          </details>
        ) : null}
      </details>
    </aside>
  );
}
