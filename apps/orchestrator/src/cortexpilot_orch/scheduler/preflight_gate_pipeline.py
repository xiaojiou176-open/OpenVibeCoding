from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import find_wide_paths
from cortexpilot_orch.gates.integrated_gate import validate_integrated_tools
from cortexpilot_orch.gates.mcp_concurrency_gate import validate_mcp_concurrency
from cortexpilot_orch.gates.mcp_gate import validate_mcp_tools
from cortexpilot_orch.gates.network_gate import requires_network_items, validate_network_policy
from cortexpilot_orch.gates.sampling_gate import validate_sampling_policy
from cortexpilot_orch.gates.tool_gate import validate_command
from cortexpilot_orch.locks.locker import acquire_lock_with_cleanup, release_lock, resolve_lock_ttl
from cortexpilot_orch.scheduler import approval_flow, artifact_pipeline, core_helpers, policy_pipeline, scheduler_bridge
from cortexpilot_orch.scheduler.preflight_gate_runtime_helpers import run_preflight_pipeline
from cortexpilot_orch.scheduler.preflight_gate_types import PreflightOps
from cortexpilot_orch.store.run_store import RunStore


def _build_result(
    *,
    ok: bool,
    failure_reason: str,
    worktree_path: Path | None,
    locked: bool,
    allowed_paths: list[str],
    policy_gate_result: dict[str, Any] | None,
    integrated_gate: dict[str, Any] | None,
    network_gate: dict[str, Any] | None,
    mcp_gate: dict[str, Any] | None,
    sampling_gate: dict[str, Any] | None,
    tool_gate: dict[str, Any] | None,
    human_approval_required: bool,
    human_approved: bool | None,
    search_request: dict[str, Any] | None,
    browser_request: dict[str, Any] | None,
    tamper_request: dict[str, Any] | None,
    sampling_request: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "failure_reason": failure_reason,
        "worktree_path": worktree_path,
        "locked": locked,
        "allowed_paths": list(allowed_paths),
        "policy_gate_result": policy_gate_result,
        "integrated_gate": integrated_gate,
        "network_gate": network_gate,
        "mcp_gate": mcp_gate,
        "sampling_gate": sampling_gate,
        "tool_gate": tool_gate,
        "human_approval_required": human_approval_required,
        "human_approved": human_approved,
        "search_request": search_request,
        "browser_request": browser_request,
        "tamper_request": tamper_request,
        "sampling_request": sampling_request,
    }


def prepare_runtime_and_policy_gates(
    *,
    run_id: str,
    task_id: str,
    store: RunStore,
    contract: dict[str, Any],
    repo_root: Path,
    baseline_commit: str,
    baseline_ref: str,
    assigned_agent: dict[str, Any],
) -> dict[str, Any]:
    _ = baseline_ref
    ops = PreflightOps(
        find_wide_paths=find_wide_paths,
        validate_integrated_tools=validate_integrated_tools,
        validate_mcp_concurrency=validate_mcp_concurrency,
        validate_mcp_tools=validate_mcp_tools,
        requires_network_items=requires_network_items,
        validate_network_policy=validate_network_policy,
        validate_sampling_policy=validate_sampling_policy,
        validate_command=validate_command,
        acquire_lock_with_cleanup=acquire_lock_with_cleanup,
        release_lock=release_lock,
        resolve_lock_ttl=resolve_lock_ttl,
        detect_agents_overrides=core_helpers.detect_agents_overrides,
        collect_patch_artifacts=artifact_pipeline.collect_patch_artifacts,
        should_apply_dependency_patches=artifact_pipeline.should_apply_dependency_patches,
        apply_dependency_patches=artifact_pipeline.apply_dependency_patches,
        load_sampling_requests=artifact_pipeline.load_sampling_requests,
        load_search_requests=scheduler_bridge.load_search_requests,
        load_browser_tasks=scheduler_bridge.load_browser_tasks,
        load_tampermonkey_tasks=scheduler_bridge.load_tampermonkey_tasks,
        requires_human_approval=scheduler_bridge.requires_human_approval,
        await_human_approval=scheduler_bridge.await_human_approval,
        auto_lock_cleanup_requested=approval_flow.auto_lock_cleanup_requested,
        force_unlock_requested=approval_flow.force_unlock_requested,
        god_mode_timeout_sec=approval_flow.god_mode_timeout_sec,
        allowed_paths=policy_pipeline.allowed_paths,
        agent_role=policy_pipeline.agent_role,
        is_search_role=policy_pipeline.is_search_role,
        network_policy=policy_pipeline.network_policy,
        filesystem_policy=policy_pipeline.filesystem_policy,
        mcp_tools=policy_pipeline.mcp_tools,
        forbidden_actions=policy_pipeline.forbidden_actions,
    )
    return run_preflight_pipeline(
        run_id=run_id,
        task_id=task_id,
        store=store,
        contract=contract,
        repo_root=repo_root,
        baseline_commit=baseline_commit,
        assigned_agent=assigned_agent,
        ops=ops,
        build_result=_build_result,
    )
