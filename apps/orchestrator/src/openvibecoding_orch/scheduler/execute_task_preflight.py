from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.store.run_store import RunStore


def maybe_execute_temporal_workflow(
    *,
    repo_root: Path,
    store: RunStore,
    contract_path: Path,
    contract: dict[str, Any],
    mock_mode: bool,
    run_workflow_fn: Callable[[Path, Path, bool], Any],
    temporal_required_fn: Callable[[], bool],
    ensure_evidence_bundle_placeholder_fn: Callable[[RunStore, str, dict[str, Any], str], None],
) -> tuple[str | None, str]:
    temporal_workflow = os.getenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "").strip().lower() in {"1", "true", "yes"}
    in_temporal_activity = os.getenv("OPENVIBECODING_TEMPORAL_ACTIVITY", "").strip().lower() in {"1", "true", "yes"}
    if not temporal_workflow or in_temporal_activity:
        return None, ""

    try:
        result = run_workflow_fn(repo_root, contract_path, mock_mode)
        if isinstance(result, dict) and result.get("run_id"):
            return str(result["run_id"]), ""
        raise RuntimeError("temporal workflow returned no run_id")
    except Exception as exc:  # noqa: BLE001
        if temporal_required_fn():
            run_id = store.create_run(contract.get("task_id", "task"))
            failure_manifest = {
                "run_id": run_id,
                "task_id": contract.get("task_id", "task"),
                "status": "FAILURE",
                "failure_reason": f"temporal workflow failed: {exc}",
            }
            store.write_contract(run_id, contract)
            store.write_manifest(run_id, failure_manifest)
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "TEMPORAL_WORKFLOW_FAILED",
                    "run_id": run_id,
                    "meta": {"error": str(exc)},
                },
            )
            ensure_evidence_bundle_placeholder_fn(
                store,
                run_id,
                contract,
                f"temporal workflow failed: {exc}",
            )
            return run_id, ""
        return None, str(exc)


def prepare_runtime_and_policy_gates(
    *,
    preflight_gate_pipeline_module: Any,
    find_wide_paths_fn: Callable[..., Any],
    validate_integrated_tools_fn: Callable[..., Any],
    validate_mcp_concurrency_fn: Callable[..., Any],
    validate_mcp_tools_fn: Callable[..., Any],
    requires_network_items_fn: Callable[..., Any],
    validate_network_policy_fn: Callable[..., Any],
    validate_sampling_policy_fn: Callable[..., Any],
    validate_command_fn: Callable[..., Any],
    acquire_lock_with_cleanup_fn: Callable[..., Any],
    release_lock_fn: Callable[..., Any],
    resolve_lock_ttl_fn: Callable[..., Any],
    detect_agents_overrides_fn: Callable[..., Any],
    collect_patch_artifacts_fn: Callable[..., Any],
    should_apply_dependency_patches_fn: Callable[..., Any],
    apply_dependency_patches_fn: Callable[..., Any],
    load_search_requests_fn: Callable[..., Any],
    load_browser_tasks_fn: Callable[..., Any],
    load_tampermonkey_tasks_fn: Callable[..., Any],
    await_human_approval_fn: Callable[..., Any],
    requires_human_approval_fn: Callable[..., Any],
    **kwargs: Any,
) -> dict[str, Any]:
    preflight_module = preflight_gate_pipeline_module
    original_bindings = {
        "find_wide_paths": preflight_module.find_wide_paths,
        "validate_integrated_tools": preflight_module.validate_integrated_tools,
        "validate_mcp_concurrency": preflight_module.validate_mcp_concurrency,
        "validate_mcp_tools": preflight_module.validate_mcp_tools,
        "requires_network_items": preflight_module.requires_network_items,
        "validate_network_policy": preflight_module.validate_network_policy,
        "validate_sampling_policy": preflight_module.validate_sampling_policy,
        "validate_command": preflight_module.validate_command,
        "acquire_lock_with_cleanup": preflight_module.acquire_lock_with_cleanup,
        "release_lock": preflight_module.release_lock,
        "resolve_lock_ttl": preflight_module.resolve_lock_ttl,
        "detect_agents_overrides": preflight_module.core_helpers.detect_agents_overrides,
        "collect_patch_artifacts": preflight_module.artifact_pipeline.collect_patch_artifacts,
        "should_apply_dependency_patches": preflight_module.artifact_pipeline.should_apply_dependency_patches,
        "apply_dependency_patches": preflight_module.artifact_pipeline.apply_dependency_patches,
        "load_search_requests": preflight_module.scheduler_bridge.load_search_requests,
        "load_browser_tasks": preflight_module.scheduler_bridge.load_browser_tasks,
        "load_tampermonkey_tasks": preflight_module.scheduler_bridge.load_tampermonkey_tasks,
        "await_human_approval": preflight_module.scheduler_bridge.await_human_approval,
        "requires_human_approval": preflight_module.scheduler_bridge.requires_human_approval,
    }
    try:
        preflight_module.find_wide_paths = find_wide_paths_fn
        preflight_module.validate_integrated_tools = validate_integrated_tools_fn
        preflight_module.validate_mcp_concurrency = validate_mcp_concurrency_fn
        preflight_module.validate_mcp_tools = validate_mcp_tools_fn
        preflight_module.requires_network_items = requires_network_items_fn
        preflight_module.validate_network_policy = validate_network_policy_fn
        preflight_module.validate_sampling_policy = validate_sampling_policy_fn
        preflight_module.validate_command = validate_command_fn
        preflight_module.acquire_lock_with_cleanup = acquire_lock_with_cleanup_fn
        preflight_module.release_lock = release_lock_fn
        preflight_module.resolve_lock_ttl = resolve_lock_ttl_fn
        preflight_module.core_helpers.detect_agents_overrides = detect_agents_overrides_fn
        preflight_module.artifact_pipeline.collect_patch_artifacts = collect_patch_artifacts_fn
        preflight_module.artifact_pipeline.should_apply_dependency_patches = should_apply_dependency_patches_fn
        preflight_module.artifact_pipeline.apply_dependency_patches = apply_dependency_patches_fn
        preflight_module.scheduler_bridge.load_search_requests = load_search_requests_fn
        preflight_module.scheduler_bridge.load_browser_tasks = load_browser_tasks_fn
        preflight_module.scheduler_bridge.load_tampermonkey_tasks = load_tampermonkey_tasks_fn
        preflight_module.scheduler_bridge.await_human_approval = await_human_approval_fn
        preflight_module.scheduler_bridge.requires_human_approval = requires_human_approval_fn
        return preflight_module.prepare_runtime_and_policy_gates(**kwargs)
    finally:
        preflight_module.find_wide_paths = original_bindings["find_wide_paths"]
        preflight_module.validate_integrated_tools = original_bindings["validate_integrated_tools"]
        preflight_module.validate_mcp_concurrency = original_bindings["validate_mcp_concurrency"]
        preflight_module.validate_mcp_tools = original_bindings["validate_mcp_tools"]
        preflight_module.requires_network_items = original_bindings["requires_network_items"]
        preflight_module.validate_network_policy = original_bindings["validate_network_policy"]
        preflight_module.validate_sampling_policy = original_bindings["validate_sampling_policy"]
        preflight_module.validate_command = original_bindings["validate_command"]
        preflight_module.acquire_lock_with_cleanup = original_bindings["acquire_lock_with_cleanup"]
        preflight_module.release_lock = original_bindings["release_lock"]
        preflight_module.resolve_lock_ttl = original_bindings["resolve_lock_ttl"]
        preflight_module.core_helpers.detect_agents_overrides = original_bindings["detect_agents_overrides"]
        preflight_module.artifact_pipeline.collect_patch_artifacts = original_bindings["collect_patch_artifacts"]
        preflight_module.artifact_pipeline.should_apply_dependency_patches = original_bindings[
            "should_apply_dependency_patches"
        ]
        preflight_module.artifact_pipeline.apply_dependency_patches = original_bindings["apply_dependency_patches"]
        preflight_module.scheduler_bridge.load_search_requests = original_bindings["load_search_requests"]
        preflight_module.scheduler_bridge.load_browser_tasks = original_bindings["load_browser_tasks"]
        preflight_module.scheduler_bridge.load_tampermonkey_tasks = original_bindings["load_tampermonkey_tasks"]
        preflight_module.scheduler_bridge.await_human_approval = original_bindings["await_human_approval"]
        preflight_module.scheduler_bridge.requires_human_approval = original_bindings["requires_human_approval"]
