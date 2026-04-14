from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from openvibecoding_orch.contract.validator import (
    ContractValidator,
    _load_agent_registry,
    _validate_ref_path,
    validate_role_config_fields,
)
from openvibecoding_orch.runners.provider_capability import (
    ProviderResolutionError,
    resolve_compat_api_mode,
    resolve_runtime_base_url_from_env,
    resolve_runtime_provider,
)


ROLE_CONFIG_REGISTRY_ENV = "OPENVIBECODING_ROLE_CONFIG_REGISTRY"
ROLE_CONFIG_REGISTRY_FILE = "policies/role_config_registry.json"
ROLE_CONFIG_AUTHORITY = "repo-owned-role-config"
ROLE_CONFIG_FIELD_MODES = {
    "purpose": "reserved-for-later",
    "system_prompt_ref": "editable-now",
    "skills_bundle_ref": "editable-now",
    "mcp_bundle_ref": "editable-now",
    "runtime_binding": "editable-now",
    "role_binding_summary": "derived-read-only",
    "role_binding_read_model": "derived-read-only",
    "workflow_case_read_model": "derived-read-only",
    "execution_authority": "authority-source",
}
_SUPPORTED_RUNTIME_OPTION_RUNNERS = {"agents", "app-server", "app_server", "codex", "claude"}


def resolve_role_config_registry_path(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[5]
    override = os.getenv(ROLE_CONFIG_REGISTRY_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        return (root / path).resolve() if not path.is_absolute() else path
    return root / ROLE_CONFIG_REGISTRY_FILE


def default_role_config_registry() -> dict[str, Any]:
    return {
        "version": "v1",
        "roles": {},
    }


def _normalize_optional_ref(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _normalize_runtime_binding(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, Mapping) else {}
    return {
        "runner": _normalize_optional_ref(raw.get("runner")),
        "provider": _normalize_optional_ref(raw.get("provider")),
        "model": _normalize_optional_ref(raw.get("model")),
    }


def load_role_config_registry(repo_root: Path | None = None) -> dict[str, Any]:
    path = resolve_role_config_registry_path(repo_root)
    if not path.exists():
        return default_role_config_registry()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else default_role_config_registry()


def _roles_map(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    roles = payload.get("roles") if isinstance(payload, Mapping) else {}
    return roles if isinstance(roles, dict) else {}


def _normalize_role_key(role: str | None) -> str:
    return str(role or "").strip().upper()


def _role_contracts_map(registry: Mapping[str, Any] | None) -> dict[str, Any]:
    role_contracts = registry.get("role_contracts") if isinstance(registry, Mapping) else {}
    return role_contracts if isinstance(role_contracts, dict) else {}


def assert_known_role(role: str, *, registry: Mapping[str, Any] | None = None) -> str:
    role_key = _normalize_role_key(role)
    if not role_key:
        raise ValueError("Role config validation failed: role is required")
    registry_payload = registry if isinstance(registry, Mapping) else _load_agent_registry()
    if role_key not in _role_contracts_map(registry_payload):
        raise ValueError(f"Role config validation failed: unknown role `{role_key}`")
    return role_key


def effective_role_contract_defaults(
    role: str,
    *,
    registry: Mapping[str, Any] | None = None,
    role_config_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    registry_payload = registry if isinstance(registry, Mapping) else _load_agent_registry()
    role_key = assert_known_role(role, registry=registry_payload)
    role_contracts = registry_payload.get("role_contracts") if isinstance(registry_payload, Mapping) else {}
    base = role_contracts.get(role_key) if isinstance(role_contracts, dict) and isinstance(role_contracts.get(role_key), dict) else {}
    base_payload = deepcopy(base)
    config_payload = role_config_registry if isinstance(role_config_registry, Mapping) else load_role_config_registry()
    role_entry = _roles_map(config_payload).get(role_key)
    if not isinstance(role_entry, Mapping):
        return base_payload
    merged = dict(base_payload)
    for key in ("system_prompt_ref", "skills_bundle_ref", "mcp_bundle_ref"):
        if key in role_entry:
            merged[key] = _normalize_optional_ref(role_entry.get(key))
    if "runtime_binding" in role_entry:
        merged["runtime_binding"] = _normalize_runtime_binding(role_entry.get("runtime_binding"))
    elif "runtime_binding" not in merged:
        merged["runtime_binding"] = _normalize_runtime_binding(None)
    return merged


def validate_role_config_registry(payload: dict[str, Any]) -> dict[str, Any]:
    validator = ContractValidator()
    validator.validate_report(payload, "role_config_registry.v1.json")
    registry = _load_agent_registry()
    for role, entry in _roles_map(payload).items():
        role_key = assert_known_role(role, registry=registry)
        if not isinstance(entry, Mapping):
            raise ValueError(f"Role config validation failed: role `{role_key}` payload invalid")
        _validate_ref_path(entry.get("system_prompt_ref"), "role_config.system_prompt_ref")
        if entry.get("skills_bundle_ref") is not None:
            _validate_ref_path(entry.get("skills_bundle_ref"), "role_config.skills_bundle_ref")
        if entry.get("mcp_bundle_ref") is not None:
            _validate_ref_path(entry.get("mcp_bundle_ref"), "role_config.mcp_bundle_ref")
        runtime_binding = _normalize_runtime_binding(entry.get("runtime_binding"))
        runner = str(runtime_binding.get("runner") or "").strip().lower()
        if runner and runner not in _SUPPORTED_RUNTIME_OPTION_RUNNERS:
            raise ValueError(f"Role config validation failed: unsupported runner `{runner}`")
        provider = str(runtime_binding.get("provider") or "").strip()
        if provider:
            try:
                resolve_runtime_provider(provider)
            except ProviderResolutionError as exc:
                raise ValueError(f"Role config validation failed: {exc}") from exc
    return payload


def write_role_config_registry(payload: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    validated = validate_role_config_registry(payload)
    path = resolve_role_config_registry_path(repo_root)
    path.write_text(json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return validated


def update_role_config_entry(role: str, entry: Mapping[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    payload = load_role_config_registry(repo_root)
    roles = _roles_map(payload)
    updated_roles = dict(roles)
    updated_roles[_normalize_role_key(role)] = {
        "system_prompt_ref": _normalize_optional_ref(entry.get("system_prompt_ref")),
        "skills_bundle_ref": _normalize_optional_ref(entry.get("skills_bundle_ref")),
        "mcp_bundle_ref": _normalize_optional_ref(entry.get("mcp_bundle_ref")),
        "runtime_binding": _normalize_runtime_binding(entry.get("runtime_binding")),
    }
    next_payload = {
        "version": "v1",
        "roles": updated_roles,
    }
    return write_role_config_registry(next_payload, repo_root)


def build_runtime_capability_summary(runtime_binding: Mapping[str, Any] | None) -> dict[str, Any]:
    normalized = _normalize_runtime_binding(runtime_binding)
    base_url = resolve_runtime_base_url_from_env()
    compat_api_mode = resolve_compat_api_mode("responses", base_url=base_url)
    provider = str(normalized.get("provider") or "").strip()
    provider_status = "unresolved"
    provider_inventory_id = None
    if provider:
        try:
            normalized_provider = resolve_runtime_provider(provider)
        except ProviderResolutionError:
            provider_status = "unsupported"
        else:
            provider_status = "allowlisted"
            provider_inventory_id = normalized_provider
    lane = "standard-provider-path"
    if compat_api_mode == "chat_completions":
        lane = "switchyard-chat-compatible"
    tool_execution = "provider-path-required"
    if compat_api_mode == "chat_completions":
        tool_execution = "fail-closed"
    return {
        "status": "previewable",
        "lane": lane,
        "compat_api_mode": compat_api_mode,
        "provider_status": provider_status,
        "provider_inventory_id": provider_inventory_id,
        "tool_execution": tool_execution,
        "notes": [
            "Chat-style compatibility may differ from tool-execution capability.",
            "Execution authority remains task_contract even when role defaults change.",
        ],
    }


def build_role_config_surface(
    role: str,
    *,
    registry: Mapping[str, Any] | None = None,
    role_config_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    registry_payload = registry if isinstance(registry, Mapping) else _load_agent_registry()
    role_key = assert_known_role(role, registry=registry_payload)
    effective_defaults = effective_role_contract_defaults(
        role_key,
        registry=registry_payload,
        role_config_registry=role_config_registry,
    )
    role_contracts = registry_payload.get("role_contracts") if isinstance(registry_payload, Mapping) else {}
    base_defaults = role_contracts.get(role_key) if isinstance(role_contracts, dict) and isinstance(role_contracts.get(role_key), dict) else {}
    config_payload = role_config_registry if isinstance(role_config_registry, Mapping) else load_role_config_registry()
    overlay_role = _roles_map(config_payload).get(role_key)
    role_entry = overlay_role if isinstance(overlay_role, Mapping) else {}
    runtime_binding = _normalize_runtime_binding(effective_defaults.get("runtime_binding"))
    return {
        "authority": ROLE_CONFIG_AUTHORITY,
        "persisted_source": ROLE_CONFIG_REGISTRY_FILE,
        "overlay_state": "repo-owned-defaults",
        "field_modes": dict(ROLE_CONFIG_FIELD_MODES),
        "editable_now": {
            "system_prompt_ref": _normalize_optional_ref(effective_defaults.get("system_prompt_ref")),
            "skills_bundle_ref": _normalize_optional_ref(effective_defaults.get("skills_bundle_ref")),
            "mcp_bundle_ref": _normalize_optional_ref(effective_defaults.get("mcp_bundle_ref")),
            "runtime_binding": runtime_binding,
        },
        "registry_defaults": {
            "system_prompt_ref": _normalize_optional_ref(base_defaults.get("system_prompt_ref")),
            "skills_bundle_ref": _normalize_optional_ref(base_defaults.get("skills_bundle_ref")),
            "mcp_bundle_ref": _normalize_optional_ref(base_defaults.get("mcp_bundle_ref")),
            "runtime_binding": _normalize_runtime_binding(base_defaults.get("runtime_binding")),
        },
        "persisted_values": {
            "system_prompt_ref": _normalize_optional_ref(role_entry.get("system_prompt_ref")),
            "skills_bundle_ref": _normalize_optional_ref(role_entry.get("skills_bundle_ref")),
            "mcp_bundle_ref": _normalize_optional_ref(role_entry.get("mcp_bundle_ref")),
            "runtime_binding": _normalize_runtime_binding(role_entry.get("runtime_binding")),
        },
        "validation": "fail-closed",
        "preview_supported": True,
        "apply_supported": True,
        "execution_authority": "task_contract",
        "runtime_capability": build_runtime_capability_summary(runtime_binding),
    }


def _stringified_change_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _build_role_config_change_summary(
    current_surface: Mapping[str, Any],
    preview_surface: Mapping[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    current_values = current_surface.get("editable_now") if isinstance(current_surface.get("editable_now"), Mapping) else {}
    preview_values = preview_surface.get("editable_now") if isinstance(preview_surface.get("editable_now"), Mapping) else {}
    for field in ("system_prompt_ref", "skills_bundle_ref", "mcp_bundle_ref"):
        current_value = _stringified_change_value(current_values.get(field))
        preview_value = _stringified_change_value(preview_values.get(field))
        if current_value == preview_value:
            continue
        changes.append(
            {
                "field": field,
                "mode": ROLE_CONFIG_FIELD_MODES.get(field, "editable-now"),
                "current": current_value,
                "next": preview_value,
            }
        )
    current_runtime = (
        current_values.get("runtime_binding")
        if isinstance(current_values.get("runtime_binding"), Mapping)
        else {}
    )
    preview_runtime = (
        preview_values.get("runtime_binding")
        if isinstance(preview_values.get("runtime_binding"), Mapping)
        else {}
    )
    for field in ("runner", "provider", "model"):
        current_value = _stringified_change_value(current_runtime.get(field))
        preview_value = _stringified_change_value(preview_runtime.get(field))
        if current_value == preview_value:
            continue
        changes.append(
            {
                "field": f"runtime_binding.{field}",
                "mode": ROLE_CONFIG_FIELD_MODES.get("runtime_binding", "editable-now"),
                "current": current_value,
                "next": preview_value,
            }
        )
    return changes


def preview_role_config_entry(
    role: str,
    entry: Mapping[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    registry = _load_agent_registry()
    role_key = assert_known_role(role, registry=registry)
    normalized_entry = validate_role_config_fields(dict(entry))
    current_registry = load_role_config_registry(repo_root)
    current_surface = build_role_config_surface(
        role_key,
        registry=registry,
        role_config_registry=current_registry,
    )
    preview_registry = deepcopy(current_registry)
    preview_roles = dict(_roles_map(preview_registry))
    preview_roles[role_key] = normalized_entry
    preview_payload = {
        "version": "v1",
        "roles": preview_roles,
    }
    validate_role_config_registry(preview_payload)
    preview_surface = build_role_config_surface(
        role_key,
        registry=registry,
        role_config_registry=preview_payload,
    )
    return {
        "role": role_key,
        "authority": ROLE_CONFIG_AUTHORITY,
        "validation": "fail-closed",
        "can_apply": True,
        "current_surface": current_surface,
        "preview_surface": preview_surface,
        "changes": _build_role_config_change_summary(current_surface, preview_surface),
    }


def apply_role_config_entry(
    role: str,
    entry: Mapping[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    role_key = assert_known_role(role)
    normalized_entry = validate_role_config_fields(dict(entry))
    updated_registry = update_role_config_entry(role_key, normalized_entry, repo_root)
    surface = build_role_config_surface(role_key, role_config_registry=updated_registry)
    return {
        "role": role_key,
        "saved": True,
        "validation": "fail-closed",
        "surface": surface,
    }
