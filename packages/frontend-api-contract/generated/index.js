// GENERATED FILE. DO NOT EDIT.
// Source: docs/api/openapi.cortexpilot.json

export const FRONTEND_API_CONTRACT = {
  "defaultApiBase": "http://127.0.0.1:10000",
  "envKeys": [
    "NEXT_PUBLIC_CORTEXPILOT_API_BASE",
    "NEXT_PUBLIC_CORTEXPILOT_API_BASE",
    "VITE_CORTEXPILOT_API_BASE",
    "VITE_CORTEXPILOT_API_BASE",
    "CORTEXPILOT_API_BASE",
    "CORTEXPILOT_API_BASE"
  ],
  "headers": {
    "requestId": "x-request-id",
    "traceId": "x-trace-id",
    "traceparent": "traceparent",
    "runId": "x-cortexpilot-run-id"
  },
  "network": {
    "fetchCredentials": "include",
    "eventSourceWithCredentials": true
  },
  "query": {
    "status": "status",
    "statusArray": "status[]",
    "types": "types",
    "typesArray": "types[]",
    "runIds": "run_ids",
    "runIdsArray": "run_ids[]"
  },
  "paths": {
    "commandTowerOverview": "/api/command-tower/overview",
    "commandTowerAlerts": "/api/command-tower/alerts",
    "runs": "/api/runs",
    "runDetail": "/api/runs/{run_id}",
    "runEvents": "/api/runs/{run_id}/events",
    "runEventsStream": "/api/runs/{run_id}/events/stream",
    "runDiff": "/api/runs/{run_id}/diff",
    "runReports": "/api/runs/{run_id}/reports",
    "agents": "/api/agents",
    "agentStatus": "/api/agents/status",
    "roleConfig": "/api/agents/roles/{role}/config",
    "roleConfigPreview": "/api/agents/roles/{role}/config/preview",
    "roleConfigApply": "/api/agents/roles/{role}/config/apply",
    "contracts": "/api/contracts",
    "queue": "/api/queue",
    "queueEnqueuePreview": "/api/queue/from-run/{run_id}/preview",
    "queueCancel": "/api/queue/{queue_id}/cancel",
    "workflows": "/api/workflows",
    "workflowDetail": "/api/workflows/{workflow_id}",
    "pmSessions": "/api/pm/sessions",
    "pmSessionMessages": "/api/pm/sessions/{pm_session_id}/messages"
  },
  "readModels": {
    "bindingStatuses": [
      "unresolved",
      "resolved",
      "registry-backed"
    ],
    "bindingValidationModes": [
      "fail-closed"
    ],
    "executionAuthorities": [
      "task_contract"
    ],
    "runtimeBindingStatuses": [
      "unresolved",
      "partially-resolved",
      "contract-derived"
    ],
    "runtimeBindingAuthorityScopes": [
      "contract-derived-read-model"
    ],
    "runtimeBindingSourceRunners": [
      "runtime_options.runner",
      "role_contract.runtime_binding.runner",
      "unresolved"
    ],
    "runtimeBindingSourceProviders": [
      "runtime_options.provider",
      "role_contract.runtime_binding.provider",
      "unresolved"
    ],
    "runtimeBindingSourceModels": [
      "env.CORTEXPILOT_CODEX_MODEL",
      "env.CORTEXPILOT_PROVIDER_MODEL",
      "role_contract.runtime_binding.model",
      "unresolved"
    ],
    "roleBindingAuthorities": [
      "contract-derived-read-model"
    ],
    "roleBindingSources": [
      "persisted from contract",
      "derived from compiled role_contract and runtime inputs; not an execution authority surface"
    ],
    "roleConfigAuthorities": [
      "repo-owned-role-config"
    ],
    "roleConfigFieldModes": [
      "editable-now",
      "derived-read-only",
      "authority-source",
      "reserved-for-later"
    ],
    "roleConfigOverlayStates": [
      "repo-owned-defaults"
    ],
    "roleConfigValidationModes": [
      "fail-closed"
    ],
    "runtimeCapabilityStatuses": [
      "previewable"
    ],
    "runtimeCapabilityLanes": [
      "standard-provider-path",
      "switchyard-chat-compatible"
    ],
    "runtimeCapabilityProviderStatuses": [
      "unresolved",
      "allowlisted",
      "unsupported"
    ],
    "runtimeCapabilityToolExecutionStates": [
      "provider-path-required",
      "fail-closed"
    ],
    "workflowCaseAuthorities": [
      "workflow-case-read-model"
    ],
    "workflowCaseSources": [
      "latest linked run manifest.role_binding_summary"
    ]
  }
};

export const PM_SESSION_SORT_OPTIONS = [
  "updated_desc",
  "created_desc",
  "failed_desc",
  "blocked_desc"
];

function normalizeToken(value, defaultToken) {
  const token = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (token) return token;
  return defaultToken ? defaultToken.trim().toLowerCase() : "";
}

export function mapBadgeByToken(token, mapping, fallback, defaultToken) {
  const normalized = normalizeToken(token, defaultToken);
  if (normalized && Object.prototype.hasOwnProperty.call(mapping, normalized)) {
    return mapping[normalized];
  }
  return fallback;
}

export * from "./ui-flow.js";
