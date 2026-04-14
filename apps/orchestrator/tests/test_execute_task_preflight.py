from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from openvibecoding_orch.scheduler import execute_task_preflight


def _mk_fn(tag: str):
    def _fn(*args: Any, **kwargs: Any) -> Any:
        return {"tag": tag, "args": args, "kwargs": kwargs}

    return _fn


def _build_preflight_module(*, should_raise: bool) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    module = SimpleNamespace()
    module.core_helpers = SimpleNamespace(detect_agents_overrides=_mk_fn("orig-detect-agents-overrides"))
    module.artifact_pipeline = SimpleNamespace(
        collect_patch_artifacts=_mk_fn("orig-collect-patch-artifacts"),
        should_apply_dependency_patches=_mk_fn("orig-should-apply-dependency-patches"),
        apply_dependency_patches=_mk_fn("orig-apply-dependency-patches"),
    )
    module.scheduler_bridge = SimpleNamespace(
        load_search_requests=_mk_fn("orig-load-search-requests"),
        load_browser_tasks=_mk_fn("orig-load-browser-tasks"),
        load_tampermonkey_tasks=_mk_fn("orig-load-tampermonkey-tasks"),
        await_human_approval=_mk_fn("orig-await-human-approval"),
        requires_human_approval=_mk_fn("orig-requires-human-approval"),
    )
    module.find_wide_paths = _mk_fn("orig-find-wide-paths")
    module.validate_integrated_tools = _mk_fn("orig-validate-integrated-tools")
    module.validate_mcp_concurrency = _mk_fn("orig-validate-mcp-concurrency")
    module.validate_mcp_tools = _mk_fn("orig-validate-mcp-tools")
    module.requires_network_items = _mk_fn("orig-requires-network-items")
    module.validate_network_policy = _mk_fn("orig-validate-network-policy")
    module.validate_sampling_policy = _mk_fn("orig-validate-sampling-policy")
    module.validate_command = _mk_fn("orig-validate-command")
    module.acquire_lock_with_cleanup = _mk_fn("orig-acquire-lock-with-cleanup")
    module.release_lock = _mk_fn("orig-release-lock")
    module.resolve_lock_ttl = _mk_fn("orig-resolve-lock-ttl")

    calls: dict[str, Any] = {}

    def _prepare_runtime_and_policy_gates(**kwargs: Any) -> dict[str, Any]:
        calls["kwargs"] = kwargs
        calls["injected"] = {
            "load_search_requests": module.scheduler_bridge.load_search_requests,
            "load_browser_tasks": module.scheduler_bridge.load_browser_tasks,
            "load_tampermonkey_tasks": module.scheduler_bridge.load_tampermonkey_tasks,
            "await_human_approval": module.scheduler_bridge.await_human_approval,
            "requires_human_approval": module.scheduler_bridge.requires_human_approval,
        }
        if should_raise:
            raise RuntimeError("boom")
        return {"ok": True}

    module.prepare_runtime_and_policy_gates = _prepare_runtime_and_policy_gates

    original = {
        "find_wide_paths": module.find_wide_paths,
        "validate_integrated_tools": module.validate_integrated_tools,
        "validate_mcp_concurrency": module.validate_mcp_concurrency,
        "validate_mcp_tools": module.validate_mcp_tools,
        "requires_network_items": module.requires_network_items,
        "validate_network_policy": module.validate_network_policy,
        "validate_sampling_policy": module.validate_sampling_policy,
        "validate_command": module.validate_command,
        "acquire_lock_with_cleanup": module.acquire_lock_with_cleanup,
        "release_lock": module.release_lock,
        "resolve_lock_ttl": module.resolve_lock_ttl,
        "detect_agents_overrides": module.core_helpers.detect_agents_overrides,
        "collect_patch_artifacts": module.artifact_pipeline.collect_patch_artifacts,
        "should_apply_dependency_patches": module.artifact_pipeline.should_apply_dependency_patches,
        "apply_dependency_patches": module.artifact_pipeline.apply_dependency_patches,
        "load_search_requests": module.scheduler_bridge.load_search_requests,
        "load_browser_tasks": module.scheduler_bridge.load_browser_tasks,
        "load_tampermonkey_tasks": module.scheduler_bridge.load_tampermonkey_tasks,
        "await_human_approval": module.scheduler_bridge.await_human_approval,
        "requires_human_approval": module.scheduler_bridge.requires_human_approval,
    }
    return module, calls, original


def test_prepare_runtime_and_policy_gates_restores_bindings_after_success() -> None:
    preflight_module, calls, original = _build_preflight_module(should_raise=False)
    injected_search = _mk_fn("injected-search")
    injected_browser = _mk_fn("injected-browser")
    injected_tamper = _mk_fn("injected-tamper")
    injected_await = _mk_fn("injected-await")
    injected_requires = _mk_fn("injected-requires")

    result = execute_task_preflight.prepare_runtime_and_policy_gates(
        preflight_gate_pipeline_module=preflight_module,
        find_wide_paths_fn=_mk_fn("new-find"),
        validate_integrated_tools_fn=_mk_fn("new-integrated"),
        validate_mcp_concurrency_fn=_mk_fn("new-mcp-concurrency"),
        validate_mcp_tools_fn=_mk_fn("new-mcp-tools"),
        requires_network_items_fn=_mk_fn("new-network-items"),
        validate_network_policy_fn=_mk_fn("new-network-policy"),
        validate_sampling_policy_fn=_mk_fn("new-sampling"),
        validate_command_fn=_mk_fn("new-command"),
        acquire_lock_with_cleanup_fn=_mk_fn("new-acquire-lock"),
        release_lock_fn=_mk_fn("new-release-lock"),
        resolve_lock_ttl_fn=_mk_fn("new-resolve-ttl"),
        detect_agents_overrides_fn=_mk_fn("new-detect-overrides"),
        collect_patch_artifacts_fn=_mk_fn("new-collect-artifacts"),
        should_apply_dependency_patches_fn=_mk_fn("new-should-apply-patches"),
        apply_dependency_patches_fn=_mk_fn("new-apply-patches"),
        load_search_requests_fn=injected_search,
        load_browser_tasks_fn=injected_browser,
        load_tampermonkey_tasks_fn=injected_tamper,
        await_human_approval_fn=injected_await,
        requires_human_approval_fn=injected_requires,
        run_id="run-1",
    )

    assert result == {"ok": True}
    assert calls["kwargs"] == {"run_id": "run-1"}
    assert calls["injected"]["load_search_requests"] is injected_search
    assert calls["injected"]["load_browser_tasks"] is injected_browser
    assert calls["injected"]["load_tampermonkey_tasks"] is injected_tamper
    assert calls["injected"]["await_human_approval"] is injected_await
    assert calls["injected"]["requires_human_approval"] is injected_requires

    assert preflight_module.find_wide_paths is original["find_wide_paths"]
    assert preflight_module.validate_integrated_tools is original["validate_integrated_tools"]
    assert preflight_module.validate_mcp_concurrency is original["validate_mcp_concurrency"]
    assert preflight_module.validate_mcp_tools is original["validate_mcp_tools"]
    assert preflight_module.requires_network_items is original["requires_network_items"]
    assert preflight_module.validate_network_policy is original["validate_network_policy"]
    assert preflight_module.validate_sampling_policy is original["validate_sampling_policy"]
    assert preflight_module.validate_command is original["validate_command"]
    assert preflight_module.acquire_lock_with_cleanup is original["acquire_lock_with_cleanup"]
    assert preflight_module.release_lock is original["release_lock"]
    assert preflight_module.resolve_lock_ttl is original["resolve_lock_ttl"]
    assert preflight_module.core_helpers.detect_agents_overrides is original["detect_agents_overrides"]
    assert preflight_module.artifact_pipeline.collect_patch_artifacts is original["collect_patch_artifacts"]
    assert (
        preflight_module.artifact_pipeline.should_apply_dependency_patches
        is original["should_apply_dependency_patches"]
    )
    assert preflight_module.artifact_pipeline.apply_dependency_patches is original["apply_dependency_patches"]
    assert preflight_module.scheduler_bridge.load_search_requests is original["load_search_requests"]
    assert preflight_module.scheduler_bridge.load_browser_tasks is original["load_browser_tasks"]
    assert preflight_module.scheduler_bridge.load_tampermonkey_tasks is original["load_tampermonkey_tasks"]
    assert preflight_module.scheduler_bridge.await_human_approval is original["await_human_approval"]
    assert preflight_module.scheduler_bridge.requires_human_approval is original["requires_human_approval"]


def test_prepare_runtime_and_policy_gates_restores_bindings_after_failure() -> None:
    preflight_module, _, original = _build_preflight_module(should_raise=True)

    try:
        execute_task_preflight.prepare_runtime_and_policy_gates(
            preflight_gate_pipeline_module=preflight_module,
            find_wide_paths_fn=_mk_fn("new-find"),
            validate_integrated_tools_fn=_mk_fn("new-integrated"),
            validate_mcp_concurrency_fn=_mk_fn("new-mcp-concurrency"),
            validate_mcp_tools_fn=_mk_fn("new-mcp-tools"),
            requires_network_items_fn=_mk_fn("new-network-items"),
            validate_network_policy_fn=_mk_fn("new-network-policy"),
            validate_sampling_policy_fn=_mk_fn("new-sampling"),
            validate_command_fn=_mk_fn("new-command"),
            acquire_lock_with_cleanup_fn=_mk_fn("new-acquire-lock"),
            release_lock_fn=_mk_fn("new-release-lock"),
            resolve_lock_ttl_fn=_mk_fn("new-resolve-ttl"),
            detect_agents_overrides_fn=_mk_fn("new-detect-overrides"),
            collect_patch_artifacts_fn=_mk_fn("new-collect-artifacts"),
            should_apply_dependency_patches_fn=_mk_fn("new-should-apply-patches"),
            apply_dependency_patches_fn=_mk_fn("new-apply-patches"),
            load_search_requests_fn=_mk_fn("new-search"),
            load_browser_tasks_fn=_mk_fn("new-browser"),
            load_tampermonkey_tasks_fn=_mk_fn("new-tamper"),
            await_human_approval_fn=_mk_fn("new-await"),
            requires_human_approval_fn=_mk_fn("new-requires"),
        )
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("prepare_runtime_and_policy_gates should re-raise pipeline errors")

    assert preflight_module.find_wide_paths is original["find_wide_paths"]
    assert preflight_module.validate_integrated_tools is original["validate_integrated_tools"]
    assert preflight_module.validate_mcp_concurrency is original["validate_mcp_concurrency"]
    assert preflight_module.validate_mcp_tools is original["validate_mcp_tools"]
    assert preflight_module.requires_network_items is original["requires_network_items"]
    assert preflight_module.validate_network_policy is original["validate_network_policy"]
    assert preflight_module.validate_sampling_policy is original["validate_sampling_policy"]
    assert preflight_module.validate_command is original["validate_command"]
    assert preflight_module.acquire_lock_with_cleanup is original["acquire_lock_with_cleanup"]
    assert preflight_module.release_lock is original["release_lock"]
    assert preflight_module.resolve_lock_ttl is original["resolve_lock_ttl"]
    assert preflight_module.core_helpers.detect_agents_overrides is original["detect_agents_overrides"]
    assert preflight_module.artifact_pipeline.collect_patch_artifacts is original["collect_patch_artifacts"]
    assert (
        preflight_module.artifact_pipeline.should_apply_dependency_patches
        is original["should_apply_dependency_patches"]
    )
    assert preflight_module.artifact_pipeline.apply_dependency_patches is original["apply_dependency_patches"]
    assert preflight_module.scheduler_bridge.load_search_requests is original["load_search_requests"]
    assert preflight_module.scheduler_bridge.load_browser_tasks is original["load_browser_tasks"]
    assert preflight_module.scheduler_bridge.load_tampermonkey_tasks is original["load_tampermonkey_tasks"]
    assert preflight_module.scheduler_bridge.await_human_approval is original["await_human_approval"]
    assert preflight_module.scheduler_bridge.requires_human_approval is original["requires_human_approval"]
