from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import preflight_gate_runtime_helpers as helpers
from cortexpilot_orch.scheduler.preflight_gate_types import PreflightOps


class _FakeStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.worktree_refs: list[tuple[str, Path]] = []

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append(event)

    def write_worktree_ref(self, run_id: str, worktree_path: Path) -> None:
        self.worktree_refs.append((run_id, worktree_path))


def _build_result(**kwargs: Any) -> dict[str, Any]:
    return kwargs


def _build_ops(**overrides: Any) -> PreflightOps:
    defaults: dict[str, Any] = {
        "find_wide_paths": lambda allowed_paths: [],
        "validate_integrated_tools": lambda repo_root, requested_tools: {"ok": True, "tools": requested_tools},
        "validate_mcp_concurrency": lambda mode: {"ok": True, "mode": mode},
        "validate_mcp_tools": lambda mcp_tools, required, repo_root=None: {"ok": True},
        "requires_network_items": lambda items: False,
        "validate_network_policy": lambda policy, requires_network, approved_override=False: {
            "ok": True,
            "policy": policy,
            "requires_network": requires_network,
            "approved_override": approved_override,
        },
        "validate_sampling_policy": lambda mcp_tools: {"ok": True},
        "validate_command": lambda *args, **kwargs: {"ok": True},
        "acquire_lock_with_cleanup": lambda allowed_paths, auto_cleanup=False: (True, [], []),
        "release_lock": lambda allowed_paths: None,
        "resolve_lock_ttl": lambda auto_cleanup: (180, "default"),
        "detect_agents_overrides": lambda repo_root: [],
        "collect_patch_artifacts": lambda artifacts, repo_root, worktree_path: [],
        "should_apply_dependency_patches": lambda contract: False,
        "apply_dependency_patches": lambda worktree_path, patch_paths, store, run_id: True,
        "load_sampling_requests": lambda contract, repo_root: (None, None),
        "load_search_requests": lambda contract, repo_root: (None, None),
        "load_browser_tasks": lambda contract, repo_root: (None, None),
        "load_tampermonkey_tasks": lambda contract, repo_root: (None, None),
        "requires_human_approval": lambda contract, requires_network: False,
        "await_human_approval": lambda run_id, store, reason, actions, verify_steps, resume_step: True,
        "auto_lock_cleanup_requested": lambda: False,
        "force_unlock_requested": lambda: False,
        "god_mode_timeout_sec": lambda: 0,
        "allowed_paths": lambda contract: ["apps/orchestrator/tests"],
        "agent_role": lambda agent: str(agent.get("role", "")),
        "is_search_role": lambda role: role in {"SEARCHER", "RESEARCHER"},
        "network_policy": lambda contract: "deny",
        "filesystem_policy": lambda contract: "workspace-write",
        "mcp_tools": lambda contract: ["codex"],
        "forbidden_actions": lambda contract: [],
    }
    defaults.update(overrides)
    return PreflightOps(**defaults)


def _run_preflight(
    monkeypatch,
    tmp_path: Path,
    *,
    contract: dict[str, Any],
    ops: PreflightOps,
    assigned_agent: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], _FakeStore]:
    store = _FakeStore()
    monkeypatch.setattr(
        helpers.worktree_manager,
        "create_worktree",
        lambda run_id, task_id, baseline_commit: tmp_path / f"{task_id}-{baseline_commit}",
    )
    result = helpers.run_preflight_pipeline(
        run_id="run-preflight",
        task_id="task-preflight",
        store=store,
        contract=contract,
        repo_root=tmp_path,
        baseline_commit="base-ref",
        assigned_agent=assigned_agent or {"codex_thread_id": ""},
        ops=ops,
        build_result=_build_result,
    )
    return result, store


def _base_contract() -> dict[str, Any]:
    return {
        "inputs": {"artifacts": []},
        "owner_agent": {"role": "OWNER"},
        "assigned_agent": {"role": "SEARCHER"},
        "tool_permissions": {"filesystem": "workspace-write"},
        "policy_pack": "",
    }


def test_preflight_rejects_invalid_tool_request(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        load_search_requests=lambda _contract, _repo_root: (None, "search_requests.json invalid"),
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "tool requests invalid: search_requests.json invalid"
    assert result["policy_gate_result"]["passed"] is False
    assert any(ev.get("event") == "TOOL_REQUEST_INVALID" for ev in store.events)


def test_preflight_blocks_search_for_pm_owner(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    contract["owner_agent"] = {"role": "PM"}
    contract["assigned_agent"] = {"role": "SEARCHER"}
    ops = _build_ops(
        load_search_requests=lambda _contract, _repo_root: ({"queries": ["q"]}, None),
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "search forbidden for PM owner"
    assert result["policy_gate_result"]["passed"] is False
    assert any(ev.get("event") == "SEARCH_OWNER_FORBIDDEN" for ev in store.events)


def test_preflight_requires_approval_for_dangerous_filesystem(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    contract["tool_permissions"]["filesystem"] = "danger-full-access"
    ops = _build_ops(
        filesystem_policy=lambda _contract: "danger-full-access",
        await_human_approval=lambda *args, **kwargs: False,
        god_mode_timeout_sec=lambda: 30,
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["human_approval_required"] is True
    assert result["human_approved"] is False
    assert result["failure_reason"] == "danger-full-access requires approval"
    assert any(ev.get("event") == "gate_failed" for ev in store.events)


def test_preflight_success_with_sampling_and_force_unlock(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CORTEXPILOT_NETWORK_APPROVED", raising=False)
    requested_tools: list[str] = []
    released_paths: list[list[str]] = []
    command_labels: list[str] = []
    contract = _base_contract()
    contract["tool_permissions"]["network"] = "on-request"

    def _validate_integrated_tools(_repo_root: Path, tools: list[str]) -> dict[str, Any]:
        requested_tools.extend(tools)
        return {"ok": True, "tools": tools}

    def _release_lock(allowed_paths: list[str]) -> None:
        released_paths.append(list(allowed_paths))

    def _validate_command(cmd_label: str, *args, **kwargs) -> dict[str, Any]:
        command_labels.append(cmd_label)
        return {"ok": True}

    ops = _build_ops(
        load_sampling_requests=lambda _contract, _repo_root: (
            {"requested_tools": ["foo", "", "search"]},
            None,
        ),
        force_unlock_requested=lambda: True,
        requires_network_items=lambda _items: True,
        network_policy=lambda _contract: "on-request",
        await_human_approval=lambda *args, **kwargs: True,
        validate_integrated_tools=_validate_integrated_tools,
        release_lock=_release_lock,
        validate_command=_validate_command,
    )
    result, store = _run_preflight(
        monkeypatch,
        tmp_path,
        contract=contract,
        ops=ops,
        assigned_agent={"codex_thread_id": "thread-42"},
    )

    assert result["ok"] is True
    assert result["locked"] is True
    assert result["human_approval_required"] is True
    assert result["human_approved"] is True
    assert released_paths == [["apps/orchestrator/tests"]]
    assert command_labels == ["codex exec resume"]
    assert requested_tools == ["codex", "sampling", "foo", "search"]
    assert any(ev.get("event") == "LOCK_FORCE_RELEASED" for ev in store.events)
    assert any(ev.get("event") == "MCP_SAMPLING_GATE_RESULT" for ev in store.events)
    assert os.getenv("CORTEXPILOT_NETWORK_APPROVED") == "1"


def test_preflight_lock_failure_and_cleanup_events(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        auto_lock_cleanup_requested=lambda: True,
        acquire_lock_with_cleanup=lambda _paths, auto_cleanup=False: (
            False,
            ["stale-lock"],
            ["still-locked"],
        ),
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "lock acquisition failed"
    assert any(ev.get("event") == "LOCK_AUTO_CLEANUP_ATTEMPT" for ev in store.events)
    assert any(ev.get("event") == "LOCK_AUTO_CLEANUP_RELEASED" for ev in store.events)
    assert any(ev.get("event") == "LOCK_FAILED" for ev in store.events)


def test_preflight_dependency_patch_apply_failure(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        collect_patch_artifacts=lambda _artifacts, _repo_root, _worktree: [tmp_path / "dep.patch"],
        should_apply_dependency_patches=lambda _contract: True,
        apply_dependency_patches=lambda _worktree, _patches, _store, _run_id: False,
    )
    result, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "dependency patch apply failed"


def test_preflight_blocks_search_for_non_search_role(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    contract["assigned_agent"] = {"role": "WORKER"}
    ops = _build_ops(
        load_search_requests=lambda _contract, _repo_root: ({"queries": ["q"]}, None),
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "search requires SEARCHER/RESEARCHER role"
    assert any(ev.get("event") == "SEARCH_ROLE_FORBIDDEN" for ev in store.events)


def test_preflight_integrated_gate_failure(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        validate_integrated_tools=lambda _repo_root, _requested_tools: {"ok": False, "missing": ["sampling"]},
    )
    result, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "tool not integrated"
    assert result["policy_gate_result"]["passed"] is False


def test_preflight_mcp_concurrency_required_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORTEXPILOT_MCP_CONCURRENCY_REQUIRED", "true")
    contract = _base_contract()
    ops = _build_ops(
        validate_mcp_concurrency=lambda _mode: {"ok": False, "reason": "invalid mode"},
    )
    result, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "mcp concurrency validation failed"


def test_preflight_human_approval_rejects_override_paths(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        detect_agents_overrides=lambda _repo_root: ["apps/orchestrator/AGENTS.md"],
        await_human_approval=lambda *args, **kwargs: False,
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "agents override requires approval"
    assert any(ev.get("event") == "AGENTS_OVERRIDE_DETECTED" for ev in store.events)


def test_preflight_human_approval_rejects_wide_paths(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    ops = _build_ops(
        find_wide_paths=lambda _allowed_paths: ["apps/"],
        await_human_approval=lambda *args, **kwargs: False,
    )
    result, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is False
    assert result["failure_reason"] == "wide paths require human approval"


def test_preflight_human_approval_approved_with_dangerous_fs_and_override(
    monkeypatch, tmp_path: Path
) -> None:
    contract = _base_contract()
    contract["tool_permissions"]["filesystem"] = "danger-full-access"
    ops = _build_ops(
        filesystem_policy=lambda _contract: "danger-full-access",
        detect_agents_overrides=lambda _repo_root: ["apps/orchestrator/AGENTS.md"],
        await_human_approval=lambda *args, **kwargs: True,
    )
    result, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)

    assert result["ok"] is True
    assert result["human_approval_required"] is True
    assert result["human_approved"] is True
    assert any(ev.get("event") == "AGENTS_OVERRIDE_APPROVED" for ev in store.events)


def test_preflight_network_mcp_sampling_and_tool_gate_failures(monkeypatch, tmp_path: Path) -> None:
    contract = _base_contract()
    stage: dict[str, bool] = {"network": False, "mcp": False, "sampling": False, "tool": False}

    def _validate_network_policy(_policy, _requires_network, approved_override=False):
        del approved_override
        return {"ok": not stage["network"], "reason": "blocked"}

    def _validate_mcp_tools(_mcp_tools, _required, repo_root=None):
        del repo_root
        return {"ok": not stage["mcp"]}

    def _validate_sampling_policy(_mcp_tools):
        return {"ok": not stage["sampling"]}

    def _validate_command(*_args, **_kwargs):
        return {"ok": not stage["tool"], "reason": "forbidden"}

    ops = _build_ops(
        validate_network_policy=_validate_network_policy,
        validate_mcp_tools=_validate_mcp_tools,
        validate_sampling_policy=_validate_sampling_policy,
        validate_command=_validate_command,
    )

    stage["network"] = True
    result_network, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)
    assert result_network["ok"] is False
    assert result_network["failure_reason"] == "network gate violation"

    stage["network"] = False
    stage["mcp"] = True
    result_mcp, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)
    assert result_mcp["ok"] is False
    assert result_mcp["failure_reason"] == "mcp tool gate violation"

    stage["mcp"] = False
    stage["sampling"] = True
    result_sampling, _ = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)
    assert result_sampling["ok"] is False
    assert result_sampling["failure_reason"] == "mcp sampling gate violation"

    stage["sampling"] = False
    stage["tool"] = True
    result_tool, store = _run_preflight(monkeypatch, tmp_path, contract=contract, ops=ops)
    assert result_tool["ok"] is False
    assert result_tool["failure_reason"] == "tool gate violation"
    assert any(ev.get("event") == "TOOL_GATE_RESULT" for ev in store.events)
