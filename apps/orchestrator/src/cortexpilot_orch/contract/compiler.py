from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator, _resolve_ref_fragment, resolve_agent_registry_path
from cortexpilot_orch.contract.role_config_registry import build_runtime_capability_summary

_FORBIDDEN_POLICY_FILE = "policies/forbidden_actions.json"
_SKILLS_BUNDLE_REGISTRY_FILE = "policies/skills_bundle_registry.json"
_ROLE_CONFIG_REGISTRY_FILE = "policies/role_config_registry.json"
_REGISTRY_BACKED_REF_PREFIXES = (
    "policies/agent_registry.json#",
    f"{_SKILLS_BUNDLE_REGISTRY_FILE}#",
)

# NOTE: Default shell policy stays `deny` to preserve the SSOT minimum-permission baseline.
_DEFAULT_TOOL_PERMISSIONS: dict[str, Any] = {
    "filesystem": "workspace-write",
    "shell": "deny",
    "network": "deny",
    "mcp_tools": ["codex"],
}

_DEFAULT_TIMEOUT_RETRY: dict[str, Any] = {
    "timeout_sec": 900,
    "max_retries": 0,
    "retry_backoff_sec": 0,
}

_DEFAULT_ROLLBACK: dict[str, Any] = {
    "strategy": "git_reset_hard",
    "baseline_ref": "HEAD",
}

_DEFAULT_LOG_REFS: dict[str, Any] = {
    "run_id": "",
    "paths": {
        "codex_jsonl": "",
        "codex_transcript": "",
        "git_diff": "",
        "tests_log": "",
        "trace_id": "",
    },
}

_DEFAULT_REQUIRED_OUTPUT = {
    "name": "patch.diff",
    "type": "patch",
    "acceptance": "generate auditable code changes",
}
_DEFAULT_ACCEPTANCE_TESTS = [
    {"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True},
]

_OUTPUT_SCHEMA_BY_ROLE: dict[str, str] = {
    "REVIEWER": "review_report.v1.json",
    "TEST_RUNNER": "test_report.v1.json",
    "TEST": "test_report.v1.json",
}


_FILESYSTEM_ORDER = {"read-only": 0, "workspace-write": 1, "danger-full-access": 2}
_NETWORK_ORDER = {"deny": 0, "on-request": 1, "allow": 2}
_SHELL_ORDER = {"deny": 0, "never": 0, "untrusted": 1, "on-request": 2}


def _default_owner_agent() -> dict[str, Any]:
    return {
        "role": "WORKER",
        "agent_id": "agent-1",
        "codex_thread_id": "",
    }


def _default_assigned_agent(owner_agent: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(owner_agent, dict):
        role = owner_agent.get("role")
        if role in {"WORKER", "REVIEWER", "TEST_RUNNER", "TEST", "AI", "SECURITY", "INFRA", "OPS"}:
            return owner_agent
    return {
        "role": "WORKER",
        "agent_id": "agent-1",
        "codex_thread_id": "",
    }


def _output_schema_name_for_role(role: str | None) -> str:
    role_key = (role or "").strip().upper()
    return _OUTPUT_SCHEMA_BY_ROLE.get(role_key, "agent_task_result.v1.json")


def _output_schema_role_key(role: str | None) -> str:
    role_key = (role or "").strip().lower()
    return role_key or "worker"


def _build_output_schema_artifact(role: str | None, schema_root: Path) -> dict[str, Any]:
    schema_name = _output_schema_name_for_role(role)
    schema_path = schema_root / schema_name
    if not schema_path.exists():
        raise ValueError(f"output schema missing: {schema_path}")
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    role_key = _output_schema_role_key(role)
    return {
        "name": f"output_schema.{role_key}",
        "uri": f"schemas/{schema_name}",
        "sha256": sha,
    }


def _inject_output_schema_artifact(
    artifacts: list[Any],
    role: str | None,
    schema_root: Path,
) -> list[Any]:
    role_key = _output_schema_role_key(role)
    candidates = {f"output_schema.{role_key}", "output_schema"}
    filtered: list[Any] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            filtered.append(artifact)
            continue
        name = artifact.get("name")
        if isinstance(name, str) and name.strip() in candidates:
            continue
        filtered.append(artifact)
    filtered.append(_build_output_schema_artifact(role, schema_root))
    return filtered


def _resolve_assigned_agent(plan: dict[str, Any], owner_agent: dict[str, Any] | None) -> dict[str, Any]:
    assigned = plan.get("assigned_agent")
    if isinstance(assigned, dict) and assigned.get("role") and assigned.get("agent_id"):
        return assigned
    return _default_assigned_agent(owner_agent)


def _load_forbidden_actions() -> list[str]:
    repo_root = Path(__file__).resolve().parents[5]
    policy_path = repo_root / _FORBIDDEN_POLICY_FILE
    if not policy_path.exists():
        return []
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    actions = payload.get("forbidden_actions") if isinstance(payload, dict) else []
    return [str(item).strip() for item in actions if str(item).strip()]


def _load_agent_registry() -> dict[str, Any] | None:
    path = resolve_agent_registry_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"agent_registry invalid: {exc}") from exc
    ContractValidator().validate_report(payload, "agent_registry.v1.json")
    return payload if isinstance(payload, dict) else None


def _load_role_config_registry() -> dict[str, Any] | None:
    repo_root = Path(__file__).resolve().parents[5]
    path = repo_root / _ROLE_CONFIG_REGISTRY_FILE
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"role_config_registry invalid: {exc}") from exc
    ContractValidator().validate_report(payload, "role_config_registry.v1.json")
    return payload if isinstance(payload, dict) else None


def _find_registry_entry(registry: dict[str, Any] | None, agent: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(registry, dict):
        return None
    entries = registry.get("agents") if isinstance(registry.get("agents"), list) else []
    role = agent.get("role")
    agent_id = agent.get("agent_id")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("role") == role and entry.get("agent_id") == agent_id:
            return entry
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("role") == role:
            return entry
    return None


def _coerce_value(current: str | None, default: str | None, order_map: dict[str, int]) -> str | None:
    if default is None:
        return current
    if current is None:
        return default
    if current not in order_map or default not in order_map:
        return current
    return current if order_map[current] <= order_map[default] else default


def _normalize_role_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip().upper() for item in raw if str(item).strip()]


def _normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalize_optional_ref(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _find_role_contract_defaults(registry: dict[str, Any] | None, role: str | None) -> dict[str, Any]:
    if not isinstance(registry, dict) or not isinstance(role, str) or not role.strip():
        return {}
    role_contracts = registry.get("role_contracts")
    if not isinstance(role_contracts, dict):
        return {}
    payload = role_contracts.get(role.strip().upper())
    return payload if isinstance(payload, dict) else {}


def _find_role_config_defaults(registry: dict[str, Any] | None, role: str | None) -> dict[str, Any]:
    if not isinstance(registry, dict) or not isinstance(role, str) or not role.strip():
        return {}
    roles = registry.get("roles")
    if not isinstance(roles, dict):
        return {}
    payload = roles.get(role.strip().upper())
    return payload if isinstance(payload, dict) else {}


def _merge_role_config_defaults(base_defaults: dict[str, Any], role_config_defaults: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_defaults)
    for key in ("system_prompt_ref", "skills_bundle_ref", "mcp_bundle_ref"):
        if key in role_config_defaults:
            merged[key] = role_config_defaults.get(key)
    runtime_binding = role_config_defaults.get("runtime_binding")
    if isinstance(runtime_binding, dict):
        merged["runtime_binding"] = {
            "runner": _normalize_optional_ref(runtime_binding.get("runner")),
            "provider": _normalize_optional_ref(runtime_binding.get("provider")),
            "model": _normalize_optional_ref(runtime_binding.get("model")),
        }
    return merged


def _runtime_binding(contract: dict[str, Any], role_defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
    role_runtime_binding = role_defaults.get("runtime_binding") if isinstance(role_defaults, dict) and isinstance(role_defaults.get("runtime_binding"), dict) else {}
    runner = str(runtime_options.get("runner") or "").strip() or _normalize_optional_ref(role_runtime_binding.get("runner"))
    provider = str(runtime_options.get("provider") or "").strip() or _normalize_optional_ref(role_runtime_binding.get("provider"))
    model = (
        os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip()
        or os.getenv("CORTEXPILOT_PROVIDER_MODEL", "").strip()
        or _normalize_optional_ref(role_runtime_binding.get("model"))
        or None
    )
    return {
        "runner": runner,
        "provider": provider,
        "model": model,
    }


def _binding_summary_status(ref: str | None) -> str:
    if not ref:
        return "unresolved"
    if any(ref.startswith(prefix) for prefix in _REGISTRY_BACKED_REF_PREFIXES):
        return "registry-backed"
    return "resolved"


def _resolve_skills_bundle_summary(ref: str | None) -> dict[str, Any]:
    if not ref or not ref.startswith(f"{_SKILLS_BUNDLE_REGISTRY_FILE}#"):
        return {"bundle_id": None, "resolved_skill_set": []}
    path_text, fragment = ref.split("#", 1)
    bundle_path = Path(__file__).resolve().parents[5] / path_text
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        resolved = _resolve_ref_fragment(payload, fragment)
    except (OSError, json.JSONDecodeError, ValueError):
        return {"bundle_id": None, "resolved_skill_set": []}
    if not isinstance(resolved, dict):
        return {"bundle_id": None, "resolved_skill_set": []}
    raw_skills = resolved.get("skills", [])
    skills_list = raw_skills if isinstance(raw_skills, list) else []
    skills = [
        str(item).strip()
        for item in skills_list
        if isinstance(item, str) and str(item).strip()
    ]
    bundle_id = str(resolved.get("bundle_id") or "").strip() or None
    return {
        "bundle_id": bundle_id,
        "resolved_skill_set": skills,
    }


def _resolve_mcp_bundle_summary(ref: str | None) -> dict[str, Any]:
    if not ref or not ref.startswith("policies/agent_registry.json#"):
        return {"resolved_mcp_tool_set": []}
    path_text, fragment = ref.split("#", 1)
    bundle_path = Path(__file__).resolve().parents[5] / path_text
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        resolved = _resolve_ref_fragment(payload, fragment)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"role_contract.mcp_bundle_ref invalid: {exc}") from exc
    if not isinstance(resolved, list):
        raise ValueError("role_contract.mcp_bundle_ref invalid: resolved payload must be a list")
    return {
        "resolved_mcp_tool_set": [
            str(item).strip()
            for item in resolved
            if isinstance(item, str) and str(item).strip()
        ]
    }


def _runtime_binding_sources(contract: dict[str, Any], runtime_binding: dict[str, Any]) -> dict[str, str]:
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
    runner = str(runtime_options.get("runner") or "").strip()
    provider = str(runtime_options.get("provider") or "").strip()
    model = str(runtime_binding.get("model") or "").strip()
    role_runtime_binding = (
        contract.get("role_contract", {}).get("runtime_binding")
        if isinstance(contract.get("role_contract"), dict)
        and isinstance(contract.get("role_contract", {}).get("runtime_binding"), dict)
        else {}
    )
    return {
        "runner": "runtime_options.runner"
        if runner
        else ("role_contract.runtime_binding.runner" if role_runtime_binding.get("runner") else "unresolved"),
        "provider": "runtime_options.provider"
        if provider
        else ("role_contract.runtime_binding.provider" if role_runtime_binding.get("provider") else "unresolved"),
        "model": "env.CORTEXPILOT_CODEX_MODEL"
        if os.getenv("CORTEXPILOT_CODEX_MODEL", "").strip()
        else (
            "env.CORTEXPILOT_PROVIDER_MODEL"
            if os.getenv("CORTEXPILOT_PROVIDER_MODEL", "").strip()
            else ("role_contract.runtime_binding.model" if model else "unresolved")
        ),
    }


def _runtime_binding_status(runtime_binding: dict[str, Any]) -> str:
    populated = [value for value in runtime_binding.values() if str(value or "").strip()]
    if not populated:
        return "unresolved"
    if len(populated) == len(runtime_binding):
        return "contract-derived"
    return "partially-resolved"


def build_role_binding_summary(contract: dict[str, Any]) -> dict[str, Any]:
    role_contract = contract.get("role_contract") if isinstance(contract.get("role_contract"), dict) else {}
    if not role_contract:
        role_contract = _build_role_contract(contract, _load_agent_registry())
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    role = str(
        assigned_agent.get("role")
        or (role_contract.get("identity", {}) if isinstance(role_contract.get("identity"), dict) else {}).get("role")
        or ""
    ).strip().upper()
    role_contract = _merge_role_config_defaults(
        role_contract,
        _find_role_config_defaults(_load_role_config_registry(), role),
    )
    skills_bundle_ref = _normalize_optional_ref(role_contract.get("skills_bundle_ref"))
    skills_bundle_summary = _resolve_skills_bundle_summary(skills_bundle_ref)
    mcp_bundle_ref = _normalize_optional_ref(role_contract.get("mcp_bundle_ref"))
    resolved_mcp_tools = _normalize_string_list(role_contract.get("resolved_mcp_tool_set")) or _resolve_mcp_bundle_summary(mcp_bundle_ref).get("resolved_mcp_tool_set", [])
    runtime_binding_raw = role_contract.get("runtime_binding") if isinstance(role_contract.get("runtime_binding"), dict) else {}
    runtime_binding = {
        "runner": _normalize_optional_ref(runtime_binding_raw.get("runner")),
        "provider": _normalize_optional_ref(runtime_binding_raw.get("provider")),
        "model": _normalize_optional_ref(runtime_binding_raw.get("model")),
    }
    return {
        "authority": "contract-derived-read-model",
        "source": "derived from compiled role_contract and runtime inputs; not an execution authority surface",
        "execution_authority": "task_contract",
        "skills_bundle_ref": {
            "status": _binding_summary_status(skills_bundle_ref),
            "ref": skills_bundle_ref,
            "bundle_id": skills_bundle_summary.get("bundle_id"),
            "resolved_skill_set": skills_bundle_summary.get("resolved_skill_set", []),
            "validation": "fail-closed",
        },
        "mcp_bundle_ref": {
            "status": _binding_summary_status(mcp_bundle_ref),
            "ref": mcp_bundle_ref,
            "resolved_mcp_tool_set": resolved_mcp_tools,
            "validation": "fail-closed",
        },
        "runtime_binding": {
            "status": _runtime_binding_status(runtime_binding),
            "authority_scope": "contract-derived-read-model",
            "source": _runtime_binding_sources(contract, runtime_binding),
            "summary": runtime_binding,
            "capability": build_runtime_capability_summary(runtime_binding),
        },
    }


def build_prompt_artifact(
    contract: dict[str, Any],
    *,
    run_id: str = "",
    task_id: str = "",
) -> dict[str, Any]:
    role_contract = contract.get("role_contract") if isinstance(contract.get("role_contract"), dict) else {}
    if not role_contract:
        role_contract = _build_role_contract(contract, _load_agent_registry())
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    role = str(
        assigned_agent.get("role")
        or (role_contract.get("identity", {}) if isinstance(role_contract.get("identity"), dict) else {}).get("role")
        or "WORKER"
    ).strip().upper() or "WORKER"
    role_contract = _merge_role_config_defaults(
        role_contract,
        _find_role_config_defaults(_load_role_config_registry(), role),
    )
    identity = role_contract.get("identity") if isinstance(role_contract.get("identity"), dict) else {}
    runtime_binding_raw = role_contract.get("runtime_binding") if isinstance(role_contract.get("runtime_binding"), dict) else {}
    runtime_binding = {
        "runner": _normalize_optional_ref(runtime_binding_raw.get("runner")),
        "provider": _normalize_optional_ref(runtime_binding_raw.get("provider")),
        "model": _normalize_optional_ref(runtime_binding_raw.get("model")),
    }
    resolved_task_id = str(task_id or contract.get("task_id") or "").strip()
    return {
        "artifact_type": "prompt_artifact",
        "version": "v1",
        "source": "contract-derived",
        "execution_authority": "task_contract",
        "run_id": str(run_id or "").strip(),
        "task_id": resolved_task_id,
        "assigned_agent": {
            "role": role,
            "agent_id": str(identity.get("agent_id") or assigned_agent.get("agent_id") or "").strip(),
        },
        "purpose": str(role_contract.get("purpose") or "").strip(),
        "system_prompt_ref": _normalize_optional_ref(role_contract.get("system_prompt_ref")),
        "skills_bundle_ref": _normalize_optional_ref(role_contract.get("skills_bundle_ref")),
        "mcp_bundle_ref": _normalize_optional_ref(role_contract.get("mcp_bundle_ref")),
        "runtime_binding": runtime_binding,
        "role_binding_summary": build_role_binding_summary(contract),
    }


def _build_role_contract(contract: dict[str, Any], registry: dict[str, Any] | None) -> dict[str, Any]:
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    role = str(assigned_agent.get("role") or "WORKER").strip().upper() or "WORKER"
    agent_id = str(assigned_agent.get("agent_id") or "agent-1").strip() or "agent-1"
    base_defaults = _find_role_contract_defaults(registry, role)
    base_mcp_bundle_ref = _normalize_optional_ref(base_defaults.get("mcp_bundle_ref"))
    if base_mcp_bundle_ref:
        _resolve_mcp_bundle_summary(base_mcp_bundle_ref)
    defaults = _merge_role_config_defaults(
        base_defaults,
        _find_role_config_defaults(_load_role_config_registry(), role),
    )
    tool_permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
    handoff_chain = contract.get("handoff_chain") if isinstance(contract.get("handoff_chain"), dict) else {}
    chain_roles = _normalize_role_list(handoff_chain.get("roles"))
    try:
        max_handoffs = int(handoff_chain.get("max_handoffs")) if handoff_chain.get("max_handoffs") is not None else None
    except (TypeError, ValueError):
        max_handoffs = None
    mcp_bundle_ref = _normalize_optional_ref(defaults.get("mcp_bundle_ref"))
    resolved_mcp_from_ref = _resolve_mcp_bundle_summary(mcp_bundle_ref).get("resolved_mcp_tool_set", []) if mcp_bundle_ref else []
    resolved_mcp_tools = _normalize_string_list(contract.get("mcp_tool_set"))
    if not resolved_mcp_tools:
        resolved_mcp_tools = _normalize_string_list(tool_permissions.get("mcp_tools"))
    if not resolved_mcp_tools:
        resolved_mcp_tools = resolved_mcp_from_ref
    purpose = str(defaults.get("purpose") or f"Resolved {role.lower()} role contract.").strip()
    return {
        "identity": {
            "role": role,
            "agent_id": agent_id,
        },
        "purpose": purpose,
        "system_prompt_ref": _normalize_optional_ref(defaults.get("system_prompt_ref")),
        "skills_bundle_ref": _normalize_optional_ref(defaults.get("skills_bundle_ref")),
        "mcp_bundle_ref": _normalize_optional_ref(defaults.get("mcp_bundle_ref")),
        "runtime_binding": _runtime_binding(contract, defaults),
        "tool_permissions": {
            "filesystem": str(tool_permissions.get("filesystem") or "workspace-write").strip() or "workspace-write",
            "shell": str(tool_permissions.get("shell") or "deny").strip() or "deny",
            "network": str(tool_permissions.get("network") or "deny").strip() or "deny",
        },
        "resolved_mcp_tool_set": resolved_mcp_tools,
        "handoff": {
            "eligible": bool(defaults.get("handoff_eligible", False)),
            "required_downstream_roles": _normalize_role_list(defaults.get("required_downstream_roles")),
            "chain_roles": chain_roles,
            "max_handoffs": max_handoffs,
        },
        "fail_closed_conditions": [
            str(item).strip()
            for item in defaults.get("fail_closed_conditions", [])
            if str(item).strip()
        ]
        or ["Contract validation fails closed on missing role metadata."],
    }


def _apply_role_defaults(contract: dict[str, Any]) -> None:
    registry = _load_agent_registry()
    assigned_agent = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
    entry = _find_registry_entry(registry, assigned_agent)
    if not entry:
        return
    defaults = entry.get("defaults") if isinstance(entry.get("defaults"), dict) else {}
    capabilities = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
    tool_permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
    updated = dict(tool_permissions)
    updated["filesystem"] = _coerce_value(
        updated.get("filesystem"), defaults.get("sandbox"), _FILESYSTEM_ORDER
    )
    updated["shell"] = _coerce_value(
        updated.get("shell"), defaults.get("approval_policy"), _SHELL_ORDER
    )
    updated["network"] = _coerce_value(
        updated.get("network"), defaults.get("network"), _NETWORK_ORDER
    )
    allowed_tools = capabilities.get("mcp_tools") if isinstance(capabilities.get("mcp_tools"), list) else None
    tools = updated.get("mcp_tools")
    if isinstance(allowed_tools, list):
        allowed_set = {str(item).strip() for item in allowed_tools if str(item).strip()}
        if isinstance(tools, list) and tools:
            updated["mcp_tools"] = [item for item in tools if str(item).strip() in allowed_set]
        else:
            updated["mcp_tools"] = list(allowed_set)
    contract["tool_permissions"] = updated


def _apply_role_runtime_defaults(contract: dict[str, Any]) -> None:
    assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
    role = str(assigned_agent.get("role") or "").strip().upper()
    if not role:
        return
    role_defaults = _merge_role_config_defaults(
        _find_role_contract_defaults(_load_agent_registry(), role),
        _find_role_config_defaults(_load_role_config_registry(), role),
    )
    role_runtime_binding = (
        role_defaults.get("runtime_binding")
        if isinstance(role_defaults.get("runtime_binding"), dict)
        else {}
    )
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
    updated_runtime_options = dict(runtime_options)
    for key in ("runner", "provider", "model"):
        current_value = _normalize_optional_ref(updated_runtime_options.get(key))
        if current_value is not None:
            updated_runtime_options[key] = current_value
            continue
        default_value = _normalize_optional_ref(role_runtime_binding.get(key))
        if default_value is not None:
            updated_runtime_options[key] = default_value
    if updated_runtime_options:
        contract["runtime_options"] = updated_runtime_options


def sync_role_contract(contract: dict[str, Any]) -> dict[str, Any]:
    registry = _load_agent_registry()
    contract["role_contract"] = _build_role_contract(contract, registry)
    return contract


def compile_plan(plan: dict[str, Any]) -> dict[str, Any]:
    validator = ContractValidator()
    validator.validate_report(plan, "plan.schema.json")

    plan_id = str(plan.get("plan_id", "")).strip()
    task_id = str(plan.get("task_id") or plan_id).strip()
    if not task_id:
        raise ValueError("plan compile failed: missing task_id")

    owner_agent = plan.get("owner_agent") or _default_owner_agent()
    assigned_agent = _resolve_assigned_agent(plan, owner_agent)
    spec = str(plan.get("spec", "")).strip()
    artifacts = plan.get("artifacts") or []
    if not isinstance(artifacts, list):
        artifacts = []
    schema_root = Path(__file__).resolve().parents[5] / "schemas"
    role = assigned_agent.get("role") if isinstance(assigned_agent, dict) else None
    artifacts = _inject_output_schema_artifact(list(artifacts), role, schema_root)

    contract: dict[str, Any] = {
        "task_id": task_id,
        "owner_agent": owner_agent,
        "assigned_agent": assigned_agent,
        "inputs": {
            "spec": spec,
            "artifacts": artifacts,
        },
        "required_outputs": plan.get("required_outputs") or [_DEFAULT_REQUIRED_OUTPUT],
        "allowed_paths": plan.get("allowed_paths") or [],
        "forbidden_actions": plan.get("forbidden_actions") or _load_forbidden_actions(),
        "acceptance_tests": plan.get("acceptance_tests") or [],
        "tool_permissions": plan.get("tool_permissions") or _DEFAULT_TOOL_PERMISSIONS,
        "mcp_tool_set": plan.get("mcp_tool_set") or [],
        "timeout_retry": plan.get("timeout_retry") or _DEFAULT_TIMEOUT_RETRY,
        "rollback": plan.get("rollback") or _DEFAULT_ROLLBACK,
        "evidence_links": plan.get("evidence_links") or [],
        "log_refs": _DEFAULT_LOG_REFS,
    }

    task_type = plan.get("task_type")
    if isinstance(task_type, str) and task_type.strip():
        contract["task_type"] = task_type.strip()

    parent_task_id = plan.get("parent_task_id")
    if isinstance(parent_task_id, str) and parent_task_id.strip():
        contract["parent_task_id"] = parent_task_id

    audit_only = plan.get("audit_only")
    if isinstance(audit_only, bool):
        contract["audit_only"] = audit_only

    policy_pack = plan.get("policy_pack")
    if isinstance(policy_pack, str) and policy_pack.strip():
        contract["policy_pack"] = policy_pack.strip()

    runtime_options = plan.get("runtime_options")
    if isinstance(runtime_options, dict) and runtime_options:
        contract["runtime_options"] = dict(runtime_options)

    handoff_chain = plan.get("handoff_chain")
    if isinstance(handoff_chain, dict) and handoff_chain:
        contract["handoff_chain"] = dict(handoff_chain)

    browser_policy = plan.get("browser_policy")
    if isinstance(browser_policy, dict) and browser_policy:
        contract["browser_policy"] = dict(browser_policy)

    _apply_role_defaults(contract)
    _apply_role_runtime_defaults(contract)

    tests = contract.get("acceptance_tests")
    if not isinstance(tests, list) or not tests:
        contract["acceptance_tests"] = list(_DEFAULT_ACCEPTANCE_TESTS)

    sync_role_contract(contract)

    validator.validate_contract(contract)
    return contract


def compile_plan_text(plan_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(plan_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"plan compile failed: invalid json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("plan compile failed: payload must be object")
    return compile_plan(payload)
