#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "docs" / "api" / "openapi.cortexpilot.json"
CONTRACT_DIR = ROOT / "packages" / "frontend-api-contract"
GENERATED_DIR = CONTRACT_DIR / "generated"


def _load_contract_extension() -> dict:
    payload = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    ext = payload.get("x-cortexpilot-frontend-contract")
    if not isinstance(ext, dict):
        raise SystemExit(f"missing x-cortexpilot-frontend-contract in {OPENAPI_PATH}")
    return ext


def _json_js(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _tuple_union(values: list[str]) -> tuple[str, str]:
    tuple_literal = ", ".join(f'"{item}"' for item in values)
    union_literal = " | ".join(f'"{item}"' for item in values)
    return tuple_literal, union_literal


def build_index_js(ext: dict) -> str:
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

export const FRONTEND_API_CONTRACT = { _json_js({
    "defaultApiBase": ext["defaultApiBase"],
    "envKeys": ext["envKeys"],
    "headers": ext["headers"],
    "network": ext["network"],
    "query": ext["query"],
    "paths": ext["paths"],
    "readModels": ext["readModels"],
}) };

export const PM_SESSION_SORT_OPTIONS = { _json_js(ext["pmSessionSortOptions"]) };

function normalizeToken(value, defaultToken) {{
  const token = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (token) return token;
  return defaultToken ? defaultToken.trim().toLowerCase() : "";
}}

export function mapBadgeByToken(token, mapping, fallback, defaultToken) {{
  const normalized = normalizeToken(token, defaultToken);
  if (normalized && Object.prototype.hasOwnProperty.call(mapping, normalized)) {{
    return mapping[normalized];
  }}
  return fallback;
}}

export * from "./ui-flow.js";
"""


def build_index_cjs(ext: dict) -> str:
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

"use strict";

const uiFlow = require("./ui-flow.cjs");

const FRONTEND_API_CONTRACT = { _json_js({
    "defaultApiBase": ext["defaultApiBase"],
    "envKeys": ext["envKeys"],
    "headers": ext["headers"],
    "network": ext["network"],
    "query": ext["query"],
    "paths": ext["paths"],
    "readModels": ext["readModels"],
}) };

const PM_SESSION_SORT_OPTIONS = { _json_js(ext["pmSessionSortOptions"]) };

function normalizeToken(value, defaultToken) {{
  const token = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (token) return token;
  return defaultToken ? defaultToken.trim().toLowerCase() : "";
}}

function mapBadgeByToken(token, mapping, fallback, defaultToken) {{
  const normalized = normalizeToken(token, defaultToken);
  if (normalized && Object.prototype.hasOwnProperty.call(mapping, normalized)) {{
    return mapping[normalized];
  }}
  return fallback;
}}

module.exports = {{
  FRONTEND_API_CONTRACT,
  PM_SESSION_SORT_OPTIONS,
  mapBadgeByToken,
  ...uiFlow,
}};
"""


def build_index_dts(ext: dict) -> str:
    sort_tuple, sort_union = _tuple_union(ext["pmSessionSortOptions"])
    read_models = ext["readModels"]
    binding_status_tuple, binding_status_union = _tuple_union(read_models["bindingStatuses"])
    binding_validation_tuple, binding_validation_union = _tuple_union(read_models["bindingValidationModes"])
    execution_authority_tuple, execution_authority_union = _tuple_union(read_models["executionAuthorities"])
    runtime_status_tuple, runtime_status_union = _tuple_union(read_models["runtimeBindingStatuses"])
    runtime_scope_tuple, runtime_scope_union = _tuple_union(read_models["runtimeBindingAuthorityScopes"])
    runtime_runner_tuple, runtime_runner_union = _tuple_union(read_models["runtimeBindingSourceRunners"])
    runtime_provider_tuple, runtime_provider_union = _tuple_union(read_models["runtimeBindingSourceProviders"])
    runtime_model_tuple, runtime_model_union = _tuple_union(read_models["runtimeBindingSourceModels"])
    role_binding_authority_tuple, role_binding_authority_union = _tuple_union(read_models["roleBindingAuthorities"])
    role_binding_source_tuple, role_binding_source_union = _tuple_union(read_models["roleBindingSources"])
    role_config_authority_tuple, role_config_authority_union = _tuple_union(read_models["roleConfigAuthorities"])
    role_config_field_mode_tuple, role_config_field_mode_union = _tuple_union(read_models["roleConfigFieldModes"])
    role_config_overlay_state_tuple, role_config_overlay_state_union = _tuple_union(read_models["roleConfigOverlayStates"])
    role_config_validation_tuple, role_config_validation_union = _tuple_union(read_models["roleConfigValidationModes"])
    runtime_capability_status_tuple, runtime_capability_status_union = _tuple_union(read_models["runtimeCapabilityStatuses"])
    runtime_capability_lane_tuple, runtime_capability_lane_union = _tuple_union(read_models["runtimeCapabilityLanes"])
    runtime_capability_provider_status_tuple, runtime_capability_provider_status_union = _tuple_union(read_models["runtimeCapabilityProviderStatuses"])
    runtime_capability_tool_exec_tuple, runtime_capability_tool_exec_union = _tuple_union(read_models["runtimeCapabilityToolExecutionStates"])
    workflow_authority_tuple, workflow_authority_union = _tuple_union(read_models["workflowCaseAuthorities"])
    workflow_source_tuple, workflow_source_union = _tuple_union(read_models["workflowCaseSources"])
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

export declare const FRONTEND_API_CONTRACT: {{
  readonly defaultApiBase: "{ext["defaultApiBase"]}";
  readonly envKeys: readonly [
    {", ".join(f'"{item}"' for item in ext["envKeys"])}
  ];
  readonly headers: {{
    readonly requestId: "{ext["headers"]["requestId"]}";
    readonly traceId: "{ext["headers"]["traceId"]}";
    readonly traceparent: "{ext["headers"]["traceparent"]}";
    readonly runId: "{ext["headers"]["runId"]}";
  }};
  readonly network: {{
    readonly fetchCredentials: "{ext["network"]["fetchCredentials"]}";
    readonly eventSourceWithCredentials: {str(ext["network"]["eventSourceWithCredentials"]).lower()};
  }};
  readonly query: {{
    readonly status: "{ext["query"]["status"]}";
    readonly statusArray: "{ext["query"]["statusArray"]}";
    readonly types: "{ext["query"]["types"]}";
    readonly typesArray: "{ext["query"]["typesArray"]}";
    readonly runIds: "{ext["query"]["runIds"]}";
    readonly runIdsArray: "{ext["query"]["runIdsArray"]}";
  }};
  readonly paths: {{
    readonly commandTowerOverview: "{ext["paths"]["commandTowerOverview"]}";
    readonly commandTowerAlerts: "{ext["paths"]["commandTowerAlerts"]}";
    readonly runs: "{ext["paths"]["runs"]}";
    readonly runDetail: "{ext["paths"]["runDetail"]}";
    readonly runEvents: "{ext["paths"]["runEvents"]}";
    readonly runEventsStream: "{ext["paths"]["runEventsStream"]}";
    readonly runDiff: "{ext["paths"]["runDiff"]}";
    readonly runReports: "{ext["paths"]["runReports"]}";
    readonly agents: "{ext["paths"]["agents"]}";
    readonly agentStatus: "{ext["paths"]["agentStatus"]}";
    readonly roleConfig: "{ext["paths"]["roleConfig"]}";
    readonly roleConfigPreview: "{ext["paths"]["roleConfigPreview"]}";
    readonly roleConfigApply: "{ext["paths"]["roleConfigApply"]}";
    readonly contracts: "{ext["paths"]["contracts"]}";
    readonly queue: "{ext["paths"]["queue"]}";
    readonly queueEnqueuePreview: "{ext["paths"]["queueEnqueuePreview"]}";
    readonly queueCancel: "{ext["paths"]["queueCancel"]}";
    readonly workflows: "{ext["paths"]["workflows"]}";
    readonly workflowDetail: "{ext["paths"]["workflowDetail"]}";
    readonly pmSessions: "{ext["paths"]["pmSessions"]}";
    readonly pmSessionMessages: "{ext["paths"]["pmSessionMessages"]}";
  }};
  readonly readModels: {{
    readonly bindingStatuses: readonly [{binding_status_tuple}];
    readonly bindingValidationModes: readonly [{binding_validation_tuple}];
    readonly executionAuthorities: readonly [{execution_authority_tuple}];
    readonly runtimeBindingStatuses: readonly [{runtime_status_tuple}];
    readonly runtimeBindingAuthorityScopes: readonly [{runtime_scope_tuple}];
    readonly runtimeBindingSourceRunners: readonly [{runtime_runner_tuple}];
    readonly runtimeBindingSourceProviders: readonly [{runtime_provider_tuple}];
    readonly runtimeBindingSourceModels: readonly [{runtime_model_tuple}];
    readonly roleBindingAuthorities: readonly [{role_binding_authority_tuple}];
    readonly roleBindingSources: readonly [{role_binding_source_tuple}];
    readonly roleConfigAuthorities: readonly [{role_config_authority_tuple}];
    readonly roleConfigFieldModes: readonly [{role_config_field_mode_tuple}];
    readonly roleConfigOverlayStates: readonly [{role_config_overlay_state_tuple}];
    readonly roleConfigValidationModes: readonly [{role_config_validation_tuple}];
    readonly runtimeCapabilityStatuses: readonly [{runtime_capability_status_tuple}];
    readonly runtimeCapabilityLanes: readonly [{runtime_capability_lane_tuple}];
    readonly runtimeCapabilityProviderStatuses: readonly [{runtime_capability_provider_status_tuple}];
    readonly runtimeCapabilityToolExecutionStates: readonly [{runtime_capability_tool_exec_tuple}];
    readonly workflowCaseAuthorities: readonly [{workflow_authority_tuple}];
    readonly workflowCaseSources: readonly [{workflow_source_tuple}];
  }};
}};
export declare const PM_SESSION_SORT_OPTIONS: readonly [{sort_tuple}];
export type PmSessionSort = {sort_union};
export type BadgeTone = "running" | "warning" | "completed" | "critical";
export type BadgePresentation = {{
  tone: BadgeTone;
  label: string;
}};
export declare function mapBadgeByToken(
  token: string | undefined | null,
  mapping: Readonly<Record<string, BadgePresentation>>,
  fallback: BadgePresentation,
  defaultToken?: string,
): BadgePresentation;
export type FrontendApiContract = typeof FRONTEND_API_CONTRACT;
export type BindingReadModelStatus = {binding_status_union};
export type BindingValidationMode = {binding_validation_union};
export type ExecutionAuthority = {execution_authority_union};
export type RuntimeBindingStatus = {runtime_status_union};
export type RuntimeBindingAuthorityScope = {runtime_scope_union};
export type RuntimeBindingSourceRunner = {runtime_runner_union};
export type RuntimeBindingSourceProvider = {runtime_provider_union};
export type RuntimeBindingSourceModel = {runtime_model_union};
export type RoleBindingReadModelAuthority = {role_binding_authority_union};
export type RoleBindingReadModelSource = {role_binding_source_union};
export type RoleConfigAuthority = {role_config_authority_union};
export type RoleConfigFieldMode = {role_config_field_mode_union};
export type RoleConfigOverlayState = {role_config_overlay_state_union};
export type RoleConfigValidationMode = {role_config_validation_union};
export type RuntimeCapabilityStatus = {runtime_capability_status_union};
export type RuntimeCapabilityLane = {runtime_capability_lane_union};
export type RuntimeCapabilityProviderStatus = {runtime_capability_provider_status_union};
export type RuntimeCapabilityToolExecutionState = {runtime_capability_tool_exec_union};
export type WorkflowCaseReadModelAuthority = {workflow_authority_union};
export type WorkflowCaseReadModelSource = {workflow_source_union};
export type RuntimeBindingSourceSummary = {{
  runner: RuntimeBindingSourceRunner;
  provider: RuntimeBindingSourceProvider;
  model: RuntimeBindingSourceModel;
}};
export type RuntimeBindingValueSummary = {{
  runner: string | null;
  provider: string | null;
  model: string | null;
}};
export type RoleConfigEditableValues = {{
  system_prompt_ref: string | null;
  skills_bundle_ref: string | null;
  mcp_bundle_ref: string | null;
  runtime_binding: RuntimeBindingValueSummary;
}};
export type RuntimeCapabilitySummary = {{
  status: RuntimeCapabilityStatus;
  lane: RuntimeCapabilityLane;
  compat_api_mode: string;
  provider_status: RuntimeCapabilityProviderStatus;
  provider_inventory_id: string | null;
  tool_execution: RuntimeCapabilityToolExecutionState;
  notes: string[];
}};
export type SkillsBundleReadModel = {{
  status: BindingReadModelStatus;
  ref: string | null;
  bundle_id: string | null;
  resolved_skill_set: string[];
  validation: BindingValidationMode;
}};
export type McpBundleReadModel = {{
  status: BindingReadModelStatus;
  ref: string | null;
  resolved_mcp_tool_set: string[];
  validation: BindingValidationMode;
}};
export type RuntimeBindingReadModel = {{
  status: RuntimeBindingStatus;
  authority_scope: RuntimeBindingAuthorityScope;
  source: RuntimeBindingSourceSummary;
  summary: RuntimeBindingValueSummary;
  capability?: RuntimeCapabilitySummary;
}};
export type RoleBindingReadModel = {{
  authority: RoleBindingReadModelAuthority;
  source: RoleBindingReadModelSource;
  execution_authority: ExecutionAuthority;
  skills_bundle_ref: SkillsBundleReadModel;
  mcp_bundle_ref: McpBundleReadModel;
  runtime_binding: RuntimeBindingReadModel;
}};
export type WorkflowCaseReadModel = {{
  authority: WorkflowCaseReadModelAuthority;
  source: WorkflowCaseReadModelSource;
  execution_authority: ExecutionAuthority;
  workflow_id: string;
  source_run_id: string;
  role_binding_summary: RoleBindingReadModel;
}};
export type AgentCatalogRecord = {{
  agent_id: string | null;
  role: string | null;
  sandbox: string | null;
  approval_policy: string | null;
  network: string | null;
  mcp_tools: string[];
  notes: string | null;
  lock_count: number;
  locked_paths: string[];
}};
export type AgentLockRecord = {{
  lock_id?: string | null;
  run_id?: string | null;
  agent_id?: string | null;
  role?: string | null;
  path?: string | null;
  ts?: string | null;
}};
export type RoleCatalogRecord = {{
  role: string;
  purpose: string | null;
  system_prompt_ref: string | null;
  handoff_eligible: boolean;
  required_downstream_roles: string[];
  fail_closed_conditions: string[];
  registered_agent_count: number;
  locked_agent_count: number;
  role_binding_read_model: RoleBindingReadModel;
}};
export type AgentCatalogPayload = {{
  agents: AgentCatalogRecord[];
  locks: AgentLockRecord[];
  role_catalog: RoleCatalogRecord[];
}};
export type AgentStatusRecord = {{
  run_id: string;
  task_id: string | null;
  agent_id: string;
  role: string;
  stage: string;
  worktree: string;
  allowed_paths: string[];
  locked_paths: string[];
  current_files: string[];
}};
export type AgentStatusPayload = {{
  agents: AgentStatusRecord[];
}};
export type RoleConfigFieldModeMap = {{
  purpose: RoleConfigFieldMode;
  system_prompt_ref: RoleConfigFieldMode;
  skills_bundle_ref: RoleConfigFieldMode;
  mcp_bundle_ref: RoleConfigFieldMode;
  runtime_binding: RoleConfigFieldMode;
  role_binding_summary: RoleConfigFieldMode;
  role_binding_read_model: RoleConfigFieldMode;
  workflow_case_read_model: RoleConfigFieldMode;
  execution_authority: RoleConfigFieldMode;
}};
export type RoleConfigSurface = {{
  authority: RoleConfigAuthority;
  persisted_source: string;
  overlay_state: RoleConfigOverlayState;
  field_modes: RoleConfigFieldModeMap;
  editable_now: RoleConfigEditableValues;
  registry_defaults: RoleConfigEditableValues;
  persisted_values: RoleConfigEditableValues;
  validation: RoleConfigValidationMode;
  preview_supported: boolean;
  apply_supported: boolean;
  execution_authority: ExecutionAuthority;
  runtime_capability: RuntimeCapabilitySummary;
}};
export type RoleConfigPreviewChange = {{
  field: string;
  mode: RoleConfigFieldMode;
  current: string | null;
  next: string | null;
}};
export type RoleConfigPreviewResponse = {{
  role: string;
  authority: RoleConfigAuthority;
  validation: RoleConfigValidationMode;
  can_apply: boolean;
  current_surface: RoleConfigSurface;
  preview_surface: RoleConfigSurface;
  changes: RoleConfigPreviewChange[];
}};
export type RoleConfigApplyResponse = {{
  role: string;
  saved: boolean;
  validation: RoleConfigValidationMode;
  surface: RoleConfigSurface;
}};
export type ContractCatalogRecordStatus = "structured" | "raw" | "read-failed";
export type ContractCatalogRecord = {{
  source: string | null;
  path: string;
  record_status: ContractCatalogRecordStatus;
  task_id: string | null;
  run_id: string | null;
  allowed_paths: string[];
  acceptance_tests: string[];
  tool_permissions: Record<string, unknown> | null;
  owner_agent_id: string | null;
  owner_role: string | null;
  assigned_agent_id: string | null;
  assigned_role: string | null;
  execution_authority: ExecutionAuthority | null;
  role_binding_read_model: RoleBindingReadModel | null;
  payload: Record<string, unknown> | null;
  raw_preview: string | null;
}};
export {{
  PM_JOURNEY_STAGES,
  COMMAND_TOWER_PRIORITY_LANES,
  DESKTOP_WORK_MODES,
}} from "./ui-flow";
export type {{
  PmJourneyStage,
  PmJourneyContext,
  CommandTowerPriorityLane,
  DesktopWorkMode,
}} from "./ui-flow";
"""


def build_ui_flow_js(ext: dict) -> str:
    ui_flow = ext["uiFlow"]
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

export const PM_JOURNEY_STAGES = { _json_js(ui_flow["pmJourneyStages"]) };
export const COMMAND_TOWER_PRIORITY_LANES = { _json_js(ui_flow["commandTowerPriorityLanes"]) };
export const DESKTOP_WORK_MODES = { _json_js(ui_flow["desktopWorkModes"]) };
"""


def build_ui_flow_cjs(ext: dict) -> str:
    ui_flow = ext["uiFlow"]
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

"use strict";

const PM_JOURNEY_STAGES = { _json_js(ui_flow["pmJourneyStages"]) };
const COMMAND_TOWER_PRIORITY_LANES = { _json_js(ui_flow["commandTowerPriorityLanes"]) };
const DESKTOP_WORK_MODES = { _json_js(ui_flow["desktopWorkModes"]) };

module.exports = {{
  PM_JOURNEY_STAGES,
  COMMAND_TOWER_PRIORITY_LANES,
  DESKTOP_WORK_MODES,
}};
"""


def build_ui_flow_dts(ext: dict) -> str:
    ui_flow = ext["uiFlow"]
    stages_tuple, stages_union = _tuple_union(ui_flow["pmJourneyStages"])
    lanes_tuple, lanes_union = _tuple_union(ui_flow["commandTowerPriorityLanes"])
    modes_tuple, modes_union = _tuple_union(ui_flow["desktopWorkModes"])
    return f"""// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

export declare const PM_JOURNEY_STAGES: readonly [{stages_tuple}];
export type PmJourneyStage = {stages_union};

export type PmJourneyContext = {{
  stage: PmJourneyStage;
  reason: string;
  primaryAction: string;
  secondaryActions: string[];
}};

export declare const COMMAND_TOWER_PRIORITY_LANES: readonly [{lanes_tuple}];
export type CommandTowerPriorityLane = {lanes_union};

export declare const DESKTOP_WORK_MODES: readonly [{modes_tuple}];
export type DesktopWorkMode = {modes_union};
"""


def main() -> int:
    ext = _load_contract_extension()
    outputs = {
        GENERATED_DIR / "index.js": build_index_js(ext),
        GENERATED_DIR / "index.cjs": build_index_cjs(ext),
        GENERATED_DIR / "index.d.ts": build_index_dts(ext),
        GENERATED_DIR / "ui-flow.js": build_ui_flow_js(ext),
        GENERATED_DIR / "ui-flow.cjs": build_ui_flow_cjs(ext),
        GENERATED_DIR / "ui-flow.d.ts": build_ui_flow_dts(ext),
    }
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    print("generated frontend api contract artifacts from docs/api/openapi.cortexpilot.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
