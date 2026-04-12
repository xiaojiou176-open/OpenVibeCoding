import type {
  AgentCatalogPayload,
  AgentCatalogRecord,
  AgentStatusPayload,
  AgentStatusRecord,
  BindingReadModelStatus,
  BindingValidationMode,
  ContractCatalogRecord,
  McpBundleReadModel,
  RoleCatalogRecord,
  RoleBindingReadModel,
  RoleConfigApplyResponse,
  RoleConfigAuthority,
  RoleConfigEditableValues,
  RoleConfigFieldMode,
  RoleConfigFieldModeMap,
  RoleConfigOverlayState,
  RoleConfigPreviewChange,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
  RoleConfigValidationMode,
  RuntimeBindingReadModel,
  RuntimeCapabilityLane,
  RuntimeCapabilityProviderStatus,
  RuntimeCapabilityStatus,
  RuntimeCapabilitySummary,
  RuntimeCapabilityToolExecutionState,
  RuntimeBindingSourceSummary,
  RuntimeBindingValueSummary,
  SkillsBundleReadModel,
  WorkflowCaseReadModel,
} from "../frontend-api-contract";

export type {
  AgentCatalogPayload,
  AgentCatalogRecord,
  AgentStatusPayload,
  AgentStatusRecord,
  BindingReadModelStatus,
  BindingValidationMode,
  ContractCatalogRecord,
  McpBundleReadModel,
  RoleCatalogRecord,
  RoleBindingReadModel,
  RoleConfigApplyResponse,
  RoleConfigAuthority,
  RoleConfigEditableValues,
  RoleConfigFieldMode,
  RoleConfigFieldModeMap,
  RoleConfigOverlayState,
  RoleConfigPreviewChange,
  RoleConfigPreviewResponse,
  RoleConfigSurface,
  RoleConfigValidationMode,
  RuntimeBindingReadModel,
  RuntimeCapabilityLane,
  RuntimeCapabilityProviderStatus,
  RuntimeCapabilityStatus,
  RuntimeCapabilitySummary,
  RuntimeCapabilityToolExecutionState,
  RuntimeBindingSourceSummary,
  RuntimeBindingValueSummary,
  SkillsBundleReadModel,
  WorkflowCaseReadModel,
};

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };
export type PublicTaskTemplate = string;
export type NewsDigestTimeRange = "24h" | "7d" | "30d";
export type NewsDigestTemplatePayload = {
  topic: string;
  sources: string[];
  time_range: NewsDigestTimeRange;
  max_results: number;
};
export type TopicBriefTemplatePayload = {
  topic: string;
  time_range: NewsDigestTimeRange;
  max_results: number;
};
export type PageBriefTemplatePayload = {
  url: string;
  focus: string;
};
export type TaskPackFieldControl = "text" | "textarea" | "url" | "select" | "number";
export type TaskPackFieldValueCodec = "string" | "string_list" | "integer";
export type TaskPackFieldOption = {
  value: string;
  label: string;
  description?: string;
};
export type TaskPackFieldDefinition = {
  field_id: string;
  label: string;
  control: TaskPackFieldControl;
  required?: boolean;
  placeholder?: string;
  help_text?: string;
  default_value?: string | number;
  value_codec?: TaskPackFieldValueCodec;
  options?: TaskPackFieldOption[];
  min?: number;
  max?: number;
};
export type TaskPackManifest = {
  pack_id: string;
  version: string;
  title: string;
  description: string;
  visibility: "public" | "internal";
  entry_mode: "pm_intake";
  task_template: string;
  input_fields: TaskPackFieldDefinition[];
  ui_hint: {
    surface_group: string;
    default_label?: string;
  };
  evidence_contract?: {
    primary_report?: string;
    requires_search_requests?: boolean;
    requires_browser_requests?: boolean;
  };
};
export type NewsDigestItem = {
  title: string;
  url: string;
  publisher?: string;
  provider?: string;
  snippet?: string;
};
export type NewsDigestResult = {
  task_template: "news_digest";
  generated_at: string;
  status: "SUCCESS" | "EMPTY" | "FAILED";
  topic: string;
  time_range: NewsDigestTimeRange;
  requested_sources: string[];
  max_results: number;
  summary: string;
  sources: NewsDigestItem[];
  evidence_refs: {
    raw: string;
    purified: string;
    verification: string;
    evidence_bundle: string;
  };
  failure_reason_zh?: string;
};
export type TopicBriefResult = {
  task_template: "topic_brief";
  generated_at: string;
  status: "SUCCESS" | "EMPTY" | "FAILED";
  topic: string;
  time_range: NewsDigestTimeRange;
  requested_sources: string[];
  max_results: number;
  summary: string;
  sources: NewsDigestItem[];
  evidence_refs: {
    raw: string;
    purified: string;
    verification: string;
    evidence_bundle: string;
  };
  failure_reason_zh?: string;
};
export type PageBriefResult = {
  task_template: "page_brief";
  generated_at: string;
  status: "SUCCESS" | "EMPTY" | "FAILED";
  url: string;
  resolved_url: string;
  page_title: string;
  focus: string;
  summary: string;
  key_points: string[];
  screenshot_artifact?: string;
  failure_reason_zh?: string;
};

export type WorkflowInfo = {
  workflow_id?: string;
  status?: string;
};

export type AgentRef = {
  role?: string;
  agent_id?: string;
};

export type RunContract = {
  task_id?: string;
  run_id?: string;
  task_template?: PublicTaskTemplate;
  template_payload?: Record<string, JsonValue>;
  allowed_paths?: string[];
  acceptance_tests?: string[];
  tool_permissions?: Record<string, JsonValue>;
  owner_agent?: AgentRef;
  assigned_agent?: AgentRef;
  rollback?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
};

export type ExecutionPlanReport = {
  report_type: "execution_plan_report";
  generated_at: string;
  task_template?: string;
  objective: string;
  summary: string;
  browser_policy_preset?: string;
  effective_browser_policy?: Record<string, JsonValue>;
  questions: string[];
  warnings: string[];
  notes: string[];
  assigned_role: string;
  assigned_agent_id?: string;
  allowed_paths: string[];
  acceptance_tests: Array<Record<string, JsonValue>>;
  search_queries: string[];
  predicted_reports: string[];
  predicted_artifacts: string[];
  runtime_capability_summary?: RuntimeCapabilitySummary;
  requires_human_approval: boolean;
  plan?: JsonValue;
  plan_bundle?: JsonValue;
  task_chain?: JsonValue;
  wave_plan?: JsonValue;
  worker_prompt_contracts?: JsonValue[];
  unblock_tasks?: JsonValue[];
  contract_preview: RunContract;
};

export type OperatorCopilotBrief = {
  report_type: "operator_copilot_brief";
  generated_at: string;
  scope?: "run" | "workflow" | "flight_plan";
  subject_id: string;
  run_id?: string;
  workflow_id?: string;
  intake_id?: string;
  status: "OK" | "UNAVAILABLE";
  summary: string;
  likely_cause: string;
  compare_takeaway: string;
  proof_takeaway: string;
  incident_takeaway: string;
  queue_takeaway: string;
  approval_takeaway: string;
  recommended_actions: string[];
  top_risks: string[];
  questions_answered: string[];
  used_truth_surfaces: string[];
  limitations: string[];
  provider: string;
  model: string;
};

export type FlightPlanCopilotBrief = {
  report_type: "flight_plan_copilot_brief";
  generated_at: string;
  status: "OK" | "UNAVAILABLE";
  summary: string;
  risk_takeaway: string;
  capability_takeaway: string;
  approval_takeaway: string;
  recommended_actions: string[];
  top_risks: string[];
  questions_answered: string[];
  used_truth_surfaces: string[];
  limitations: string[];
  provider: string;
  model: string;
};

export type RunManifest = {
  failure_reason?: string;
  versions?: { contracts_schema?: string; orchestrator?: string };
  trace_id?: string;
  trace?: { trace_id?: string; trace_url?: string };
  workflow?: WorkflowInfo;
  role_binding_summary?: RoleBindingReadModel;
  evidence_hashes?: Record<string, JsonValue>;
  artifacts?: JsonValue[];
  observability?: { enabled?: boolean };
  chain_id?: string;
  [key: string]: JsonValue | undefined;
};

export type RunSummary = {
  run_id: string;
  task_id: string;
  status: string;
  workflow_status?: string;
  created_at?: string;
  start_ts?: string;
  owner_agent_id?: string;
  owner_role?: string;
  assigned_agent_id?: string;
  assigned_role?: string;
  last_event_ts?: string;
  failure_reason?: string;
  failure_class?: string;
  outcome_type?: string;
  outcome_label_zh?: string;
  failure_summary_zh?: string;
  action_hint_zh?: string;
  failure_code?: string;
  failure_stage?: string;
  root_event?: string;
};

export type RunDetailPayload = RunSummary & {
  allowed_paths?: string[];
  contract?: RunContract;
  manifest?: RunManifest;
  role_binding_read_model?: RoleBindingReadModel;
  news_digest_result?: NewsDigestResult;
  topic_brief_result?: TopicBriefResult;
  page_brief_result?: PageBriefResult;
};

export type EventRecord = {
  ts?: string;
  event?: string;
  event_type?: string;
  level?: string;
  task_id?: string;
  run_id?: string;
  _run_id?: string;
  trace_id?: string;
  context?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
};

export type ReportRecord = {
  name: string;
  data: JsonValue;
};

export type ToolCallRecord = {
  tool?: string;
  status?: string;
  task_id?: string;
  duration_ms?: number;
  error?: string;
  args?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
};

export type ContractRecord = ContractCatalogRecord;

export type WorkflowRun = {
  run_id: string;
  status?: string;
  created_at?: string;
  task_id?: string;
};

export type WorkflowRecord = {
  workflow_id: string;
  name?: string;
  title?: string;
  status?: string;
  namespace?: string;
  task_queue?: string;
  objective?: string;
  owner_pm?: string;
  project_key?: string;
  verdict?: string;
  summary?: string;
  updated_at?: string;
  created_at?: string;
  pm_session_ids?: string[];
  run_ids?: string[];
  case_source?: string;
  case_updated_at?: string;
  workflow_case_read_model?: WorkflowCaseReadModel;
  runs?: WorkflowRun[];
};

function bindingReadModelLabel(
  ref: string | null | undefined,
  bundleId: string | null | undefined,
  status: string | undefined,
): string {
  const normalizedRef = String(ref || "").trim();
  const normalizedBundleId = String(bundleId || "").trim();
  const label = normalizedBundleId || normalizedRef || "-";
  return `${label} (${String(status || "-")})`;
}

export function formatBindingReadModelLabel(
  binding: SkillsBundleReadModel | McpBundleReadModel | null | undefined,
): string {
  if (!binding) {
    return "- (-)";
  }
  return bindingReadModelLabel(
    binding.ref,
    "bundle_id" in binding ? binding.bundle_id : null,
    binding.status,
  );
}

export function formatRoleBindingRuntimeSummary(
  roleBindingSummary: RoleBindingReadModel | null | undefined,
): string {
  const runtimeSummary = roleBindingSummary?.runtime_binding?.summary;
  const runner = String(runtimeSummary?.runner || "-");
  const provider = String(runtimeSummary?.provider || "-");
  const model = String(runtimeSummary?.model || "-");
  return `${runner} / ${provider} / ${model}`;
}

export function formatRoleBindingRuntimeCapabilitySummary(
  roleBindingSummary: RoleBindingReadModel | null | undefined,
): string {
  const capability = roleBindingSummary?.runtime_binding?.capability;
  if (!capability) {
    return "- / -";
  }
  return `${capability.lane} / ${capability.tool_execution}`;
}

export type QueueItemRecord = {
  queue_id: string;
  task_id: string;
  owner?: string;
  contract_path?: string;
  workflow_id?: string;
  source_run_id?: string;
  status: string;
  priority?: number;
  scheduled_at?: string;
  deadline_at?: string;
  run_id?: string;
  created_at?: string;
  claimed_at?: string;
  completed_at?: string;
  eligible?: boolean;
  queue_state?: string;
  sla_state?: string;
  waiting_reason?: string;
};

export const GENERAL_TASK_TEMPLATE = "general";

function splitTaskPackList(raw: string): string[] {
  return raw
    .split(/\r?\n|,/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeTaskPackFieldStringValue(field: TaskPackFieldDefinition, raw: unknown): string {
  if (Array.isArray(raw)) {
    return raw
      .map((item) => String(item ?? "").trim())
      .filter(Boolean)
      .join("\n");
  }
  if (raw === null || raw === undefined) {
    return "";
  }
  if (typeof raw === "number" || typeof raw === "boolean") {
    return String(raw);
  }
  if (typeof raw === "string") {
    return raw;
  }
  return field.value_codec === "integer" ? "0" : "";
}

export function getTaskPackFieldDefaultValue(field: TaskPackFieldDefinition): string {
  return normalizeTaskPackFieldStringValue(field, field.default_value);
}

export function findTaskPackByTemplate(
  taskPacks: TaskPackManifest[],
  taskTemplate: string | null | undefined,
): TaskPackManifest | null {
  const normalized = String(taskTemplate || "").trim().toLowerCase();
  if (!normalized || normalized === GENERAL_TASK_TEMPLATE) {
    return null;
  }
  return taskPacks.find((pack) => String(pack.task_template || "").trim().toLowerCase() === normalized) || null;
}

export function buildTaskPackFieldStateForPack(
  pack: TaskPackManifest | null | undefined,
  currentValues: Record<string, string> = {},
): Record<string, string> {
  if (!pack) {
    return { ...currentValues };
  }
  const nextValues = { ...currentValues };
  for (const field of pack.input_fields || []) {
    if (!(field.field_id in nextValues)) {
      nextValues[field.field_id] = getTaskPackFieldDefaultValue(field);
    }
  }
  return nextValues;
}

export function mergeTaskPackFieldStateByTemplate(
  taskPacks: TaskPackManifest[],
  currentValuesByTemplate: Record<string, Record<string, string>> = {},
): Record<string, Record<string, string>> {
  const nextValuesByTemplate = { ...currentValuesByTemplate };
  for (const pack of taskPacks) {
    nextValuesByTemplate[pack.task_template] = buildTaskPackFieldStateForPack(
      pack,
      currentValuesByTemplate[pack.task_template] || {},
    );
  }
  return nextValuesByTemplate;
}

export function buildTaskPackTemplatePayload(
  pack: TaskPackManifest,
  fieldValues: Record<string, string> = {},
): Record<string, JsonValue> {
  const payload: Record<string, JsonValue> = {};
  for (const field of pack.input_fields || []) {
    const rawValue = String(fieldValues[field.field_id] ?? getTaskPackFieldDefaultValue(field));
    const trimmed = rawValue.trim();
    if (!trimmed) {
      if (field.required) {
        throw new Error(`${field.label} is required`);
      }
      continue;
    }
    if (field.value_codec === "integer") {
      const parsed = Number.parseInt(trimmed, 10);
      if (!Number.isFinite(parsed)) {
        throw new Error(`${field.label} must be an integer`);
      }
      const boundedMin = typeof field.min === "number" ? Math.max(parsed, field.min) : parsed;
      const boundedValue = typeof field.max === "number" ? Math.min(boundedMin, field.max) : boundedMin;
      payload[field.field_id] = boundedValue;
      continue;
    }
    if (field.value_codec === "string_list") {
      const items = splitTaskPackList(trimmed);
      if (field.required && items.length === 0) {
        throw new Error(`${field.label} is required`);
      }
      payload[field.field_id] = items;
      continue;
    }
    payload[field.field_id] = trimmed;
  }
  return payload;
}

export function hydrateTaskPackFieldStateFromPayload(
  pack: TaskPackManifest | null | undefined,
  templatePayload: Record<string, JsonValue> | null | undefined,
  currentValues: Record<string, string> = {},
): Record<string, string> {
  const nextValues = buildTaskPackFieldStateForPack(pack, currentValues);
  if (!pack || !templatePayload) {
    return nextValues;
  }
  for (const field of pack.input_fields || []) {
    if (!(field.field_id in templatePayload)) {
      continue;
    }
    nextValues[field.field_id] = normalizeTaskPackFieldStringValue(field, templatePayload[field.field_id]);
  }
  return nextValues;
}

export type WorkflowDetailPayload = {
  workflow: WorkflowRecord;
  runs: WorkflowRun[];
  events: EventRecord[];
};

export type PmSessionStatus = "active" | "paused" | "done" | "failed" | "archived";

export type PmSessionSummary = {
  pm_session_id: string;
  objective?: string;
  owner_pm?: string;
  project_key?: string;
  session_source?: string;
  status: PmSessionStatus;
  created_at?: string;
  updated_at?: string;
  closed_at?: string;
  run_count: number;
  running_runs: number;
  failed_runs: number;
  success_runs: number;
  latest_run_id?: string;
  current_role?: string;
  current_step?: string;
  blocked_runs: number;
};

export type PmSessionRun = {
  run_id: string;
  task_id?: string;
  status?: string;
  failure_reason?: string;
  workflow_id?: string;
  created_at?: string;
  finished_at?: string;
  last_event_ts?: string;
  blocked?: boolean;
  current_role?: string;
  current_step?: string;
  binding_type?: string;
  bound_at?: string;
};

export type PmSessionDetailPayload = {
  session: PmSessionSummary;
  run_ids: string[];
  runs: PmSessionRun[];
  bindings?: Array<{
    pm_session_id: string;
    run_id: string;
    binding_type: string;
    bound_at?: string;
  }>;
  blockers?: Array<{
    run_id: string;
    task_id?: string;
    status?: string;
    current_role?: string;
    current_step?: string;
  }>;
};

export type PmSessionConversationEdge = {
  from_role?: string;
  to_role?: string;
  run_id?: string;
  ts?: string;
  event_ref?: string;
  count?: number;
};

export type PmSessionConversationGraphPayload = {
  pm_session_id: string;
  window: string;
  group_by_role?: boolean;
  nodes: string[];
  edges: PmSessionConversationEdge[];
  stats: {
    node_count: number;
    edge_count: number;
  };
};

export type PmSessionMetricsPayload = {
  pm_session_id: string;
  run_count: number;
  running_runs: number;
  failed_runs: number;
  success_runs: number;
  blocked_runs: number;
  failure_rate: number;
  blocked_ratio: number;
  avg_duration_seconds: number;
  avg_recovery_seconds: number;
  cycle_time_seconds: number;
  mttr_seconds: number;
};

export type CommandTowerOverviewPayload = {
  generated_at: string;
  total_sessions: number;
  active_sessions: number;
  failed_sessions: number;
  blocked_sessions: number;
  failed_ratio: number;
  blocked_ratio: number;
  failure_trend_30m: number;
  slo_targets?: Record<string, number>;
  top_blockers: PmSessionSummary[];
};

export type CommandTowerAlert = {
  code: string;
  severity: "info" | "warning" | "critical";
  message: string;
  suggested_action?: string;
};

export type CommandTowerAlertsPayload = {
  generated_at: string;
  status: "healthy" | "degraded" | "critical";
  slo_targets?: Record<string, number>;
  alerts: CommandTowerAlert[];
};
