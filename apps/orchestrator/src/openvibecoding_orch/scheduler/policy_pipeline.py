from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_RESTRICTED_MCP_ROLES = {"PM", "TECH_LEAD", "REVIEWER"}
_TOOL_PERMISSION_OVERRIDE_ORDER = {
    "tool_permissions.filesystem": "contract.tool_permissions.filesystem -> registry.defaults.sandbox",
    "tool_permissions.shell": "contract.tool_permissions.shell -> registry.defaults.approval_policy",
    "tool_permissions.network": "contract.tool_permissions.network -> registry.defaults.network",
    "tool_permissions.mcp_tools": "contract.tool_permissions.mcp_tools -> registry.capabilities.mcp_tools",
}


def allowed_paths(contract: dict[str, Any]) -> list[str]:
    paths = contract.get("allowed_paths", [])
    return paths if isinstance(paths, list) else []


def forbidden_actions(contract: dict[str, Any]) -> list[str]:
    actions = contract.get("forbidden_actions", [])
    return actions if isinstance(actions, list) else []


def acceptance_tests(contract: dict[str, Any]) -> list[dict[str, Any]]:
    tests = contract.get("acceptance_tests", [])
    return tests if isinstance(tests, list) else []


def tool_permissions(contract: dict[str, Any]) -> dict[str, Any]:
    payload = contract.get("tool_permissions", {})
    return payload if isinstance(payload, dict) else {}


def _normalize_network_policy_value(value: Any) -> str:
    if not isinstance(value, str):
        return "deny"
    normalized = value.strip().lower()
    if normalized == "enabled":
        return "allow"
    if normalized in {"deny", "on-request", "allow"}:
        return normalized
    return "deny"


def network_policy(contract: dict[str, Any]) -> str:
    policy = tool_permissions(contract).get("network", "deny")
    if not isinstance(policy, str):
        return "deny"
    return _normalize_network_policy_value(policy)


def shell_policy(contract: dict[str, Any]) -> str:
    policy = tool_permissions(contract).get("shell", "untrusted")
    if not isinstance(policy, str):
        return "untrusted"
    return policy.strip().lower()


def filesystem_policy(contract: dict[str, Any]) -> str:
    policy = tool_permissions(contract).get("filesystem", "read-only")
    if not isinstance(policy, str):
        return "read-only"
    return policy.strip().lower()


def codex_shell_policy(contract: dict[str, Any]) -> dict[str, str | bool]:
    requested = shell_policy(contract)
    current_network_policy = network_policy(contract)
    effective = requested
    overridden = False
    if current_network_policy == "deny" and requested in {"untrusted", "on-request", "on-failure"}:
        effective = "never"
        overridden = True
    return {
        "requested_shell": requested,
        "effective_shell": effective,
        "network_policy": current_network_policy,
        "overridden": overridden,
    }


def mcp_only_enabled() -> bool:
    raw = os.getenv("OPENVIBECODING_MCP_ONLY", "1").strip().lower()
    return raw in {"1", "true", "yes"}


def allow_codex_exec() -> bool:
    raw = os.getenv("OPENVIBECODING_ALLOW_CODEX_EXEC", "").strip().lower()
    return raw in {"1", "true", "yes"}


def default_policy_pack_for_role(role: str) -> str:
    role = role.upper()
    if role in {"PM", "TECH_LEAD"}:
        return "high"
    if role in {"UI_UX", "FRONTEND", "BACKEND", "AI", "SECURITY", "INFRA", "OPS", "TEST"}:
        return "medium"
    if role in {"REVIEWER", "TEST_RUNNER"}:
        return "medium"
    if role in {"SEARCHER", "RESEARCHER"}:
        return "medium"
    return "low"


def find_registry_entry(registry: dict[str, Any] | None, agent: dict[str, Any]) -> dict[str, Any] | None:
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


def resolve_codex_home(entry: dict[str, Any] | None, repo_root: Path) -> tuple[str | None, str]:
    if not isinstance(entry, dict):
        return None, "codex_home missing for assigned agent"
    raw = entry.get("codex_home")
    if not isinstance(raw, str) or not raw.strip():
        return None, "codex_home missing for assigned agent"
    expanded = os.path.expandvars(os.path.expanduser(raw.strip()))
    if "$" in expanded:
        return None, f"codex_home unresolved: {raw}"
    path = Path(expanded)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    if not path.exists():
        return None, f"codex_home not found: {path}"
    if not path.is_dir():
        return None, f"codex_home not a directory: {path}"
    return str(path), ""


def coerce_value(current: str | None, default: str | None, order_map: dict[str, int]) -> tuple[str | None, bool]:
    if default is None:
        return current, False
    if current is None:
        return default, False
    if current not in order_map or default not in order_map:
        return current, False
    if order_map[current] <= order_map[default]:
        return current, False
    return default, True


def apply_role_defaults(
    contract: dict[str, Any],
    registry: dict[str, Any] | None,
    filesystem_order: dict[str, int],
    shell_order: dict[str, int],
    network_order: dict[str, int],
) -> tuple[dict[str, Any], list[str]]:
    assigned_agent = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
    entry = find_registry_entry(registry, assigned_agent)
    permissions = contract.get("tool_permissions") if isinstance(contract.get("tool_permissions"), dict) else {}
    if not entry:
        return dict(permissions), []

    role = agent_role(assigned_agent)
    defaults = entry.get("defaults") if isinstance(entry.get("defaults"), dict) else {}
    capabilities = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
    updated = dict(permissions)
    violations: list[str] = []

    fs_value, fs_changed = coerce_value(updated.get("filesystem"), defaults.get("sandbox"), filesystem_order)
    if fs_value is not None:
        updated["filesystem"] = fs_value
    if fs_changed:
        violations.append("tool_permissions.filesystem")

    shell_value, shell_changed = coerce_value(updated.get("shell"), defaults.get("approval_policy"), shell_order)
    if shell_value is not None:
        updated["shell"] = shell_value
    if shell_changed:
        violations.append("tool_permissions.shell")

    current_network = _normalize_network_policy_value(updated.get("network"))
    default_network = _normalize_network_policy_value(defaults.get("network"))
    network_value, network_changed = coerce_value(current_network, default_network, network_order)
    if network_value is not None:
        updated["network"] = network_value
    if network_changed:
        violations.append("tool_permissions.network")

    allowed_tools = capabilities.get("mcp_tools") if isinstance(capabilities.get("mcp_tools"), list) else None
    tools = updated.get("mcp_tools")
    if isinstance(allowed_tools, list):
        allowed_set = {str(item).strip() for item in allowed_tools if str(item).strip()}
        if isinstance(tools, list) and tools:
            filtered = [item for item in tools if str(item).strip() in allowed_set]
            if len(filtered) != len(tools):
                violations.append("tool_permissions.mcp_tools")
            updated["mcp_tools"] = filtered
        else:
            updated["mcp_tools"] = list(allowed_set)
    elif role in _RESTRICTED_MCP_ROLES:
        existing = updated.get("mcp_tools")
        if isinstance(existing, list) and existing:
            violations.append("tool_permissions.mcp_tools")
        updated["mcp_tools"] = []

    return updated, violations


def agent_role(agent: dict[str, Any]) -> str:
    role = agent.get("role") if isinstance(agent, dict) else ""
    if not isinstance(role, str):
        return ""
    return role.strip().upper()


def resolve_policy_pack(contract: dict[str, Any]) -> str:
    raw = contract.get("policy_pack")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    assigned = contract.get("assigned_agent", {}) if isinstance(contract, dict) else {}
    role = agent_role(assigned)
    return default_policy_pack_for_role(role)


def mcp_tools(contract: dict[str, Any]) -> list[str]:
    tools = tool_permissions(contract).get("mcp_tools", [])
    return tools if isinstance(tools, list) else []


def is_search_role(role: str) -> bool:
    return role in {"SEARCHER", "RESEARCHER"}


def override_order_graph() -> dict[str, str]:
    """Return deterministic override precedence used by apply_role_defaults."""
    return dict(_TOOL_PERMISSION_OVERRIDE_ORDER)


def build_override_breakpoints(violations: list[str]) -> list[str]:
    """Convert raw violation keys into user-facing override breakpoints."""
    messages: list[str] = []
    for key in violations:
        order = _TOOL_PERMISSION_OVERRIDE_ORDER.get(key)
        if order:
            messages.append(f"{key}: {order}")
    return messages
