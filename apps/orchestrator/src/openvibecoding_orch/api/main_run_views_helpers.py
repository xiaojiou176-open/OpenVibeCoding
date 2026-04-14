from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.contract.role_config_registry import effective_role_contract_defaults


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in value:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def list_diff_gate(
    *,
    runs_root: Path,
    read_events_fn: Callable[[str], list[dict]],
    read_json_fn: Callable[[Path, object], object],
) -> list[dict]:
    def _safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return float("-inf")

    results = []
    for run_dir in sorted(runs_root.glob("*"), key=_safe_mtime, reverse=True):
        run_id = run_dir.name
        try:
            events = read_events_fn(run_id)
            last = next((ev for ev in reversed(events) if ev.get("event") == "DIFF_GATE_RESULT"), None)
            manifest = read_json_fn(run_dir / "manifest.json", {})
            contract = read_json_fn(run_dir / "contract.json", {})
            failure_reason = manifest.get("failure_reason") if isinstance(manifest, dict) else ""
            failure_text = str(failure_reason or "").lower()
            if not last and "diff gate" not in failure_text and "allowed_paths" not in failure_text:
                continue
            results.append(
                {
                    "run_id": run_id,
                    "diff_gate": last.get("context") if isinstance(last, dict) else {},
                    "status": manifest.get("status") if isinstance(manifest, dict) else "",
                    "failure_reason": failure_reason,
                    "allowed_paths": contract.get("allowed_paths", []) if isinstance(contract, dict) else [],
                }
            )
        except OSError:
            continue
    return results


def list_reports_by_name(*, runs_root: Path, report_name: str) -> list[dict]:
    results = []
    for run_dir in runs_root.glob("*"):
        run_id = run_dir.name
        report_path = run_dir / "reports" / report_name
        if not report_path.exists():
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"raw": report_path.read_text(encoding="utf-8")}
        results.append({"run_id": run_id, "report": payload})
    return results


def list_agents(
    *,
    load_agent_registry_fn: Callable[[], dict],
    load_locks_fn: Callable[[], list[dict]],
    build_role_binding_summary_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict:
    registry = load_agent_registry_fn()
    locks = load_locks_fn()
    lock_map: dict[tuple[str, str], list[str]] = {}
    for item in locks:
        agent_id = str(item.get("agent_id", "") or "")
        role = str(item.get("role", "") or "")
        if not agent_id or not role:
            continue
        key = (agent_id, role)
        lock_map.setdefault(key, []).append(str(item.get("path", "")))

    agents: list[dict[str, Any]] = []
    role_map: dict[str, list[dict[str, Any]]] = {}
    for entry in registry.get("agents", []):
        if not isinstance(entry, dict):
            continue
        agent_id = str(entry.get("agent_id", ""))
        role = str(entry.get("role", ""))
        locked = lock_map.get((agent_id, role), [])
        defaults = entry.get("defaults") if isinstance(entry.get("defaults"), dict) else {}
        capabilities = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        payload = {
            "agent_id": agent_id or None,
            "role": role or None,
            "sandbox": _normalize_optional_text(defaults.get("sandbox")),
            "approval_policy": _normalize_optional_text(defaults.get("approval_policy")),
            "network": _normalize_optional_text(defaults.get("network")),
            "mcp_tools": _normalize_string_list(capabilities.get("mcp_tools")),
            "notes": _normalize_optional_text(capabilities.get("notes")),
            "lock_count": len(locked),
            "locked_paths": locked,
        }
        agents.append(payload)
        if role:
            role_map.setdefault(role, []).append(payload)

    role_contracts = registry.get("role_contracts") if isinstance(registry.get("role_contracts"), dict) else {}
    role_catalog: list[dict[str, Any]] = []
    for role in sorted(set(role_map) | set(role_contracts)):
        try:
            role_defaults = effective_role_contract_defaults(role, registry=registry)
        except ValueError:
            fallback_defaults = role_contracts.get(role) if isinstance(role_contracts.get(role), dict) else {}
            role_defaults = fallback_defaults
        role_agents = role_map.get(role, [])
        role_catalog.append(
            {
                "role": role,
                "purpose": _normalize_optional_text(role_defaults.get("purpose")),
                "system_prompt_ref": _normalize_optional_text(role_defaults.get("system_prompt_ref")),
                "handoff_eligible": bool(role_defaults.get("handoff_eligible")),
                "required_downstream_roles": _normalize_string_list(role_defaults.get("required_downstream_roles")),
                "fail_closed_conditions": _normalize_string_list(role_defaults.get("fail_closed_conditions")),
                "registered_agent_count": len(role_agents),
                "locked_agent_count": sum(1 for item in role_agents if int(item.get("lock_count") or 0) > 0),
                "role_binding_read_model": build_role_binding_summary_fn(
                    {
                        "assigned_agent": {
                            "role": role,
                            "agent_id": role_agents[0].get("agent_id") if role_agents else f"catalog-{role.lower()}",
                        },
                        "role_contract": role_defaults,
                    }
                ),
            }
        )
    return {"agents": agents, "locks": locks, "role_catalog": role_catalog}


def list_agents_status(
    *,
    run_id: str | None,
    runs_root: Path,
    load_worktrees_fn: Callable[[], list[dict]],
    load_locks_fn: Callable[[], list[dict]],
    load_contract_fn: Callable[[str], dict],
    read_events_fn: Callable[[str], list[dict]],
    derive_stage_fn: Callable[[list[dict], dict], str],
) -> dict:
    worktrees = load_worktrees_fn()
    worktree_map = {item.get("run_id", ""): item.get("path", "") for item in worktrees if isinstance(item, dict)}
    locks = load_locks_fn()
    lock_map: dict[str, list[str]] = {}
    for item in locks:
        rid = str(item.get("run_id", "") or "")
        if not rid:
            continue
        lock_map.setdefault(rid, []).append(str(item.get("path", "")))

    agents_status: list[dict] = []
    for run_dir in runs_root.glob("*"):
        current_run_id = run_dir.name
        if run_id and current_run_id != run_id:
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        contract = load_contract_fn(current_run_id)
        assigned = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
        events = read_events_fn(current_run_id)
        stage = derive_stage_fn(events, manifest if isinstance(manifest, dict) else {})
        diff_path = run_dir / "diff_name_only.txt"
        current_files: list[str] = []
        if diff_path.exists():
            current_files = [line.strip() for line in diff_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        agents_status.append(
            {
                "run_id": current_run_id,
                "task_id": manifest.get("task_id") if isinstance(manifest, dict) else "",
                "agent_id": assigned.get("agent_id", ""),
                "role": assigned.get("role", ""),
                "stage": stage,
                "worktree": worktree_map.get(current_run_id, ""),
                "allowed_paths": contract.get("allowed_paths", []) if isinstance(contract, dict) else [],
                "locked_paths": lock_map.get(current_run_id, []),
                "current_files": current_files,
            }
        )
    return {"agents": agents_status}


def list_policies(
    *,
    load_agent_registry_fn: Callable[[], dict],
    load_command_allowlist_fn: Callable[[], dict],
    load_forbidden_actions_fn: Callable[[], dict],
    load_tool_registry_fn: Callable[[], dict],
    load_control_plane_runtime_policy_fn: Callable[[], dict],
) -> dict:
    return {
        "agent_registry": load_agent_registry_fn(),
        "command_allowlist": load_command_allowlist_fn(),
        "forbidden_actions": load_forbidden_actions_fn(),
        "tool_registry": load_tool_registry_fn(),
        "control_plane_runtime_policy": load_control_plane_runtime_policy_fn(),
    }


def list_locks(*, load_locks_fn: Callable[[], list[dict]]) -> list[dict]:
    return load_locks_fn()


def release_locks(*, paths: list[str], release_lock_fn: Callable[[list[str]], None]) -> dict[str, Any]:
    sanitized_paths: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str):
            continue
        path = raw.strip()
        if not path or path in seen:
            continue
        sanitized_paths.append(path)
        seen.add(path)
    release_lock_fn(sanitized_paths)
    return {"ok": True, "released_paths": sanitized_paths}


def list_worktrees(*, load_worktrees_fn: Callable[[], list[dict]]) -> list[dict]:
    return load_worktrees_fn()
