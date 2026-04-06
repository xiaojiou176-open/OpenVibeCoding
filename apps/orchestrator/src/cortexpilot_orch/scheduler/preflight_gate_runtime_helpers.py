from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import gate_orchestration
from cortexpilot_orch.scheduler.preflight_gate_types import BuildResultFn, PreflightOps, PreflightState
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.worktrees import manager as worktree_manager

def run_preflight_pipeline(
    *,
    run_id: str,
    task_id: str,
    store: RunStore,
    contract: dict[str, Any],
    repo_root: Path,
    baseline_commit: str,
    assigned_agent: dict[str, Any],
    ops: PreflightOps,
    build_result: BuildResultFn,
) -> dict[str, Any]:
    state = PreflightState()
    def finish(ok: bool) -> dict[str, Any]:
        return build_result(
            ok=ok,
            failure_reason=state.failure_reason,
            worktree_path=state.worktree_path,
            locked=state.locked,
            allowed_paths=state.allowed_paths,
            policy_gate_result=state.policy_gate_result,
            integrated_gate=state.integrated_gate,
            network_gate=state.network_gate,
            mcp_gate=state.mcp_gate,
            sampling_gate=state.sampling_gate,
            tool_gate=state.tool_gate,
            human_approval_required=state.human_approval_required,
            human_approved=state.human_approved,
            search_request=state.search_request,
            browser_request=state.browser_request,
            tamper_request=state.tamper_request,
            sampling_request=state.sampling_request,
        )
    def rebuild_policy_gate() -> None:
        state.policy_gate_result = gate_orchestration.build_policy_gate(
            state.integrated_gate,
            state.network_gate,
            state.mcp_gate,
            state.sampling_gate,
            state.tool_gate,
            state.human_approval_required,
            state.human_approved,
        )
    state.override_paths = list(ops.detect_agents_overrides(repo_root))
    if state.override_paths:
        store.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "AGENTS_OVERRIDE_DETECTED",
                "run_id": run_id,
                "meta": {"paths": state.override_paths},
            },
        )
    state.worktree_path = worktree_manager.create_worktree(run_id, task_id, baseline_commit)
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "WORKTREE_CREATED",
            "run_id": run_id,
            "meta": {"path": str(state.worktree_path)},
        },
    )
    store.write_worktree_ref(run_id, state.worktree_path)
    state.allowed_paths = ops.allowed_paths(contract)
    state.wide_paths = ops.find_wide_paths(state.allowed_paths)
    auto_cleanup = ops.auto_lock_cleanup_requested()
    ttl_sec, ttl_source = ops.resolve_lock_ttl(auto_cleanup)
    if auto_cleanup:
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "LOCK_AUTO_CLEANUP_ATTEMPT",
                "run_id": run_id,
                "meta": {
                    "allowed_paths": state.allowed_paths,
                    "ttl_sec": ttl_sec,
                    "ttl_source": ttl_source,
                },
            },
        )
    lock_ok, cleaned, remaining = ops.acquire_lock_with_cleanup(
        state.allowed_paths,
        auto_cleanup=auto_cleanup,
    )
    if cleaned:
        store.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "LOCK_AUTO_CLEANUP_RELEASED",
                "run_id": run_id,
                "meta": {
                    "released": cleaned,
                    "remaining": remaining,
                    "ttl_sec": ttl_sec,
                    "ttl_source": ttl_source,
                },
            },
        )
    if not lock_ok:
        state.failure_reason = "lock acquisition failed"
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "lock_gate",
            state.failure_reason,
            extra={
                "allowed_paths": state.allowed_paths,
                "auto_cleanup": auto_cleanup,
                "remaining": remaining,
            },
        )
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "LOCK_FAILED",
                "run_id": run_id,
                "meta": {
                    "reason": state.failure_reason,
                    "auto_cleanup": auto_cleanup,
                    "remaining": remaining,
                },
            },
        )
        return finish(False)
    state.locked = True
    inputs = contract.get("inputs", {})
    artifacts = inputs.get("artifacts") if isinstance(inputs, dict) else None
    patch_paths = ops.collect_patch_artifacts(artifacts, repo_root, state.worktree_path)
    if patch_paths and ops.should_apply_dependency_patches(contract):
        if not ops.apply_dependency_patches(state.worktree_path, patch_paths, store, run_id):
            state.failure_reason = "dependency patch apply failed"
            return finish(False)
    state.search_request, search_error = ops.load_search_requests(contract, repo_root)
    state.browser_request, browser_error = ops.load_browser_tasks(contract, repo_root)
    state.tamper_request, tamper_error = ops.load_tampermonkey_tasks(contract, repo_root)
    state.sampling_request, sampling_error = ops.load_sampling_requests(contract, repo_root)
    for error in [search_error, browser_error, tamper_error, sampling_error]:
        if error:
            state.failure_reason = f"tool requests invalid: {error}"
            gate_orchestration.append_policy_violation(
                store,
                run_id,
                state.failure_reason,
                extra={"reason": error, "path": "inputs.artifacts"},
            )
            state.policy_gate_result = gate_orchestration.gate_result(False, [state.failure_reason])
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "TOOL_REQUEST_INVALID",
                    "run_id": run_id,
                    "meta": {"reason": error},
                },
            )
            return finish(False)

    if state.search_request:
        owner_role = ops.agent_role(contract.get("owner_agent", {}))
        assigned_role = ops.agent_role(contract.get("assigned_agent", {}))
        if owner_role == "PM":
            state.failure_reason = "search forbidden for PM owner"
            gate_orchestration.append_policy_violation(
                store,
                run_id,
                state.failure_reason,
                extra={"owner_role": owner_role},
            )
            state.policy_gate_result = gate_orchestration.gate_result(False, [state.failure_reason])
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "SEARCH_OWNER_FORBIDDEN",
                    "run_id": run_id,
                    "meta": {"owner_role": owner_role},
                },
            )
            return finish(False)
        if not ops.is_search_role(assigned_role):
            state.failure_reason = "search requires SEARCHER/RESEARCHER role"
            gate_orchestration.append_policy_violation(
                store,
                run_id,
                state.failure_reason,
                extra={"assigned_role": assigned_role},
            )
            state.policy_gate_result = gate_orchestration.gate_result(False, [state.failure_reason])
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "SEARCH_ROLE_FORBIDDEN",
                    "run_id": run_id,
                    "meta": {"assigned_role": assigned_role},
                },
            )
            return finish(False)
    requested_tools: list[str] = ["codex"]
    if state.search_request:
        requested_tools.append("search")
    if state.browser_request:
        requested_tools.append("browser")
    if state.tamper_request:
        requested_tools.append("tampermonkey")
    if state.sampling_request:
        requested_tools.append("sampling")
        sampling_declared_tools = state.sampling_request.get("requested_tools")
        if isinstance(sampling_declared_tools, list):
            for item in sampling_declared_tools:
                tool_name = str(item).strip()
                if tool_name:
                    requested_tools.append(tool_name)
    requested_tools = list(dict.fromkeys(requested_tools))
    state.integrated_gate = ops.validate_integrated_tools(repo_root, requested_tools)
    store.append_event(
        run_id,
        {
            "level": "INFO" if state.integrated_gate["ok"] else "ERROR",
            "event": "INTEGRATED_GATE_RESULT",
            "run_id": run_id,
            "meta": state.integrated_gate,
        },
    )
    if not state.integrated_gate["ok"]:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "integrated_gate",
            "tool not integrated",
            extra=state.integrated_gate if isinstance(state.integrated_gate, dict) else None,
        )
        state.failure_reason = "tool not integrated"
        rebuild_policy_gate()
        return finish(False)
    mcp_mode = os.getenv("CORTEXPILOT_MCP_CONCURRENCY_MODE", "single")
    mcp_concurrency = ops.validate_mcp_concurrency(mcp_mode)
    store.append_event(
        run_id,
        {
            "level": "INFO" if mcp_concurrency.get("ok") else "ERROR",
            "event": "MCP_CONCURRENCY_CHECK",
            "run_id": run_id,
            "meta": mcp_concurrency,
        },
    )
    if not mcp_concurrency.get("ok") and os.getenv("CORTEXPILOT_MCP_CONCURRENCY_REQUIRED", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "mcp_concurrency_gate",
            "mcp concurrency validation failed",
            extra=mcp_concurrency if isinstance(mcp_concurrency, dict) else None,
        )
        state.failure_reason = "mcp concurrency validation failed"
        rebuild_policy_gate()
        return finish(False)
    network_policy = ops.network_policy(contract)
    filesystem_policy = ops.filesystem_policy(contract)
    requires_network = ops.requires_network_items(
        [
            state.search_request.get("queries") if state.search_request else [],
            state.browser_request.get("tasks") if state.browser_request else [],
            state.tamper_request.get("tasks") if state.tamper_request else [],
        ]
    )
    wide_paths_required = bool(state.wide_paths)
    force_unlock = ops.force_unlock_requested()
    dangerous_fs = filesystem_policy == "danger-full-access"
    override_paths_required = bool(state.override_paths)
    state.human_approval_required = (
        ops.requires_human_approval(contract, requires_network)
        or wide_paths_required
        or force_unlock
        or dangerous_fs
        or override_paths_required
    )
    if state.human_approval_required:
        reasons: list[str] = []
        actions: list[str] = []
        verify_steps: list[str] = [
            'After the work is complete, click the "I have finished" button on the God Mode page',
        ]
        if requires_network and network_policy == "on-request":
            reasons.append("network on-request requires approval")
            actions.append("Approve network access or provide the required network credentials")
        if wide_paths_required:
            reasons.append("allowed_paths too wide")
            actions.append("Confirm the allowed path scope or narrow the allowed_paths set")
        if force_unlock:
            reasons.append("force unlock requested")
            actions.append("Acknowledge the possible concurrency risk after releasing the lock")
        if dangerous_fs:
            reasons.append("filesystem danger-full-access requested")
            actions.append("Confirm that danger-full-access filesystem permission is allowed")
        if override_paths_required:
            reasons.append("override paths requested")
            actions.append("Confirm the requested override path scope")
        timeout_sec = ops.god_mode_timeout_sec()
        approved = ops.await_human_approval(
            run_id,
            store,
            reason=reasons,
            actions=actions,
            verify_steps=verify_steps,
            resume_step="policy_gate",
        )
        state.human_approved = approved
        if approved and requires_network and network_policy == "on-request":
            os.environ["CORTEXPILOT_NETWORK_APPROVED"] = "1"
        if approved and force_unlock:
            ops.release_lock(state.allowed_paths)
            store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "LOCK_FORCE_RELEASED",
                    "run_id": run_id,
                    "meta": {"allowed_paths": state.allowed_paths},
                },
            )
        if approved and dangerous_fs:
            gate_orchestration.append_policy_violation(
                store,
                run_id,
                "danger-full-access approved by god mode",
                extra={"path": "tool_permissions.filesystem"},
            )
        if approved and override_paths_required:
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "AGENTS_OVERRIDE_APPROVED",
                    "run_id": run_id,
                    "meta": {"paths": state.override_paths},
                },
            )
        if not approved:
            if timeout_sec > 0:
                gate_orchestration.append_gate_failed(
                    store,
                    run_id,
                    "human_approval_gate",
                    "human approval timeout",
                    extra={"timeout_sec": timeout_sec},
                )
            if force_unlock:
                state.failure_reason = "force unlock requires approval"
                gate_orchestration.append_gate_failed(
                    store,
                    run_id,
                    "force_unlock_gate",
                    state.failure_reason,
                    extra={"allowed_paths": state.allowed_paths},
                )
            elif override_paths_required:
                state.failure_reason = "agents override requires approval"
                gate_orchestration.append_gate_failed(
                    store,
                    run_id,
                    "agents_override_gate",
                    state.failure_reason,
                    extra={"paths": state.override_paths},
                )
            elif dangerous_fs:
                state.failure_reason = "danger-full-access requires approval"
                gate_orchestration.append_policy_violation(
                    store,
                    run_id,
                    state.failure_reason,
                    extra={"path": "tool_permissions.filesystem"},
                )
            elif wide_paths_required:
                state.failure_reason = "wide paths require human approval"
                gate_orchestration.append_policy_violation(
                    store,
                    run_id,
                    state.failure_reason,
                    extra={"wide_paths": state.wide_paths},
                )
            else:
                state.failure_reason = "human approval required"
            rebuild_policy_gate()
            return finish(False)
    state.network_gate = ops.validate_network_policy(
        network_policy,
        requires_network,
        approved_override=bool(state.human_approved),
    )
    store.append_event(
        run_id,
        {
            "level": "INFO" if state.network_gate["ok"] else "ERROR",
            "event": "NETWORK_GATE_RESULT",
            "run_id": run_id,
            "meta": state.network_gate,
        },
    )
    if not state.network_gate["ok"]:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "network_gate",
            "network gate violation",
            extra=state.network_gate if isinstance(state.network_gate, dict) else None,
        )
        state.failure_reason = "network gate violation"
        rebuild_policy_gate()
        return finish(False)
    allowed_mcp_tools = ops.mcp_tools(contract)
    state.mcp_gate = ops.validate_mcp_tools(allowed_mcp_tools, allowed_mcp_tools, repo_root=repo_root)
    store.append_event(
        run_id,
        {
            "level": "INFO" if state.mcp_gate["ok"] else "ERROR",
            "event": "MCP_TOOL_GATE_RESULT",
            "run_id": run_id,
            "meta": state.mcp_gate,
        },
    )
    if not state.mcp_gate["ok"]:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "mcp_gate",
            "mcp tool gate violation",
            extra=state.mcp_gate if isinstance(state.mcp_gate, dict) else None,
        )
        state.failure_reason = "mcp tool gate violation"
        rebuild_policy_gate()
        return finish(False)
    state.sampling_gate = ops.validate_sampling_policy(ops.mcp_tools(contract))
    store.append_event(
        run_id,
        {
            "level": "INFO" if state.sampling_gate["ok"] else "ERROR",
            "event": "MCP_SAMPLING_GATE_RESULT",
            "run_id": run_id,
            "meta": state.sampling_gate,
        },
    )
    if not state.sampling_gate["ok"]:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "sampling_gate",
            "mcp sampling gate violation",
            extra=state.sampling_gate if isinstance(state.sampling_gate, dict) else None,
        )
        state.failure_reason = "mcp sampling gate violation"
        rebuild_policy_gate()
        return finish(False)
    cmd_label = "codex exec"
    if isinstance(assigned_agent.get("codex_thread_id"), str) and assigned_agent.get("codex_thread_id", "").strip():
        cmd_label = "codex exec resume"
    state.tool_gate = ops.validate_command(
        cmd_label,
        ops.forbidden_actions(contract),
        network_policy=network_policy,
        policy_pack=contract.get("policy_pack", ""),
        repo_root=repo_root,
    )
    if not state.tool_gate["ok"]:
        gate_orchestration.append_gate_failed(
            store,
            run_id,
            "tool_gate",
            "tool gate violation",
            extra=state.tool_gate if isinstance(state.tool_gate, dict) else None,
        )
        state.failure_reason = "tool gate violation"
        rebuild_policy_gate()
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "TOOL_GATE_RESULT",
                "run_id": run_id,
                "meta": state.tool_gate,
            },
        )
        return finish(False)
    return finish(True)
