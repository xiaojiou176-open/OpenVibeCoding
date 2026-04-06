from __future__ import annotations

import os
import platform
import sys
from functools import partial
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import (
    ContractValidator,
    hash_contract,
    find_wide_paths,
    resolve_agent_registry_path,
    check_schema_registry,
)
from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.gates.diff_gate import validate_diff
from cortexpilot_orch.gates.reviewer_gate import snapshot_worktree, validate_reviewer_isolation
from cortexpilot_orch.gates.integrated_gate import validate_integrated_tools
from cortexpilot_orch.gates.mcp_concurrency_gate import validate_mcp_concurrency
from cortexpilot_orch.gates.mcp_gate import validate_mcp_tools
from cortexpilot_orch.gates.network_gate import requires_network_items, validate_network_policy
from cortexpilot_orch.gates.sampling_gate import validate_sampling_policy
from cortexpilot_orch.gates.tests_gate import run_acceptance_tests, run_evals_gate
from cortexpilot_orch.gates.tool_gate import validate_command
from cortexpilot_orch.locks.locker import acquire_lock_with_cleanup, release_lock, resolve_lock_ttl
from cortexpilot_orch.observability.logger import log_event
from cortexpilot_orch.observability.tracer import trace_span, ensure_tracing, tracing_status
from cortexpilot_orch.replay.replayer import ReplayRunner
from cortexpilot_orch.reviewer.reviewer import Reviewer
from cortexpilot_orch.temporal.manager import notify_run_started, temporal_required
from cortexpilot_orch.temporal.runner import run_workflow
from cortexpilot_orch.runners.tool_runner import ToolRunner
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.transport.codex_profile_pool import pick_profile
from cortexpilot_orch.scheduler import artifact_refs, gate_orchestration
from cortexpilot_orch.scheduler import (
    approval_flow,
    artifact_pipeline,
    evidence_pipeline,
    preflight_gate_pipeline,
    policy_pipeline,
    report_builders,
    rollback_pipeline,
    runtime_utils,
    scheduler_bridge,
    execute_task_pipeline,
    test_pipeline,
    task_execution_pipeline,
    tool_execution_pipeline,
    core_helpers,
)
from tooling.tampermonkey.runner import run_tampermonkey

_FILESYSTEM_ORDER = core_helpers.FILESYSTEM_ORDER
_SHELL_ORDER = core_helpers.SHELL_ORDER
_NETWORK_ORDER = core_helpers.NETWORK_ORDER
_now_ts = core_helpers.now_ts
_trace_url = core_helpers.trace_url
_normalize_role = core_helpers.normalize_role
_task_result_role = core_helpers.task_result_role
_manifest_task_role = core_helpers.manifest_task_role
_artifact_ref_from_path = artifact_refs.artifact_ref_from_path
_artifact_refs_from_hashes = artifact_refs.artifact_refs_from_hashes
_detect_agents_overrides = core_helpers.detect_agents_overrides
_per_run_codex_home_enabled = core_helpers.per_run_codex_home_enabled
_materialize_codex_home = core_helpers.materialize_codex_home
_gate_result = gate_orchestration.gate_result
_append_gate_failed = gate_orchestration.append_gate_failed
_append_policy_violation = gate_orchestration.append_policy_violation
_build_policy_gate = gate_orchestration.build_policy_gate
_extract_user_request = core_helpers.extract_user_request
_collect_patch_artifacts = artifact_pipeline.collect_patch_artifacts
_should_apply_dependency_patches = artifact_pipeline.should_apply_dependency_patches
_apply_dependency_patches = artifact_pipeline.apply_dependency_patches
_extract_test_logs = test_pipeline.extract_test_logs
_cleanup_test_artifacts = test_pipeline.cleanup_test_artifacts
_hash_events = evidence_pipeline.hash_events
_collect_evidence_hashes = evidence_pipeline.collect_evidence_hashes
_build_task_result = report_builders.build_task_result
_ensure_evidence_bundle_placeholder = evidence_pipeline.ensure_evidence_bundle_placeholder
_git = runtime_utils.git
_git_allow_nonzero = runtime_utils.git_allow_nonzero
_collect_diff_text = runtime_utils.collect_diff_text
_baseline_commit = runtime_utils.baseline_commit
_tool_version = runtime_utils.tool_version
_read_contract = runtime_utils.read_contract
_schema_root = runtime_utils.schema_root
_write_manifest = runtime_utils.write_manifest
_write_contract_signature = runtime_utils.write_contract_signature
_resolve_baseline_ref = runtime_utils.resolve_baseline_ref
_build_log_refs = runtime_utils.build_log_refs
_llm_params_snapshot = runtime_utils.llm_params_snapshot
_apply_role_defaults = partial(
    scheduler_bridge.apply_role_defaults,
    filesystem_order=_FILESYSTEM_ORDER,
    shell_order=_SHELL_ORDER,
    network_order=_NETWORK_ORDER,
)

_requires_human_approval = scheduler_bridge.requires_human_approval
_await_human_approval = scheduler_bridge.await_human_approval
_safe_artifact_path = scheduler_bridge.safe_artifact_path
_load_json_artifact = scheduler_bridge.load_json_artifact
_load_search_requests = scheduler_bridge.load_search_requests
_load_browser_tasks = scheduler_bridge.load_browser_tasks
_load_tampermonkey_tasks = scheduler_bridge.load_tampermonkey_tasks
_run_search_pipeline = scheduler_bridge.run_search_pipeline
_run_sampling_requests = scheduler_bridge.run_sampling_requests
_run_browser_tasks = scheduler_bridge.run_browser_tasks
_run_optional_tool_requests = scheduler_bridge.run_optional_tool_requests
_run_tampermonkey_tasks = partial(
    scheduler_bridge.run_tampermonkey_tasks,
    run_tampermonkey_fn=lambda *args, **kwargs: run_tampermonkey(*args, **kwargs),
)
_apply_rollback = scheduler_bridge.apply_rollback
_scoped_revert = scheduler_bridge.scoped_revert
_select_runner = scheduler_bridge.select_runner
_max_retries = scheduler_bridge.max_retries
_retry_backoff = scheduler_bridge.retry_backoff
_run_runner_fix_review_flow = task_execution_pipeline.run_runner_fix_review_flow
_execute_replay_action = scheduler_bridge.execute_replay_action
_ContractStateWriter = scheduler_bridge.ContractStateWriter
_notify_temporal_start_and_fail_if_required = scheduler_bridge.notify_temporal_start_and_fail_if_required
_write_running_contract_manifest = scheduler_bridge.write_running_contract_manifest
_finalize_execute_task_run = scheduler_bridge.finalize_execute_task_run
_prepare_execution_setup = execute_task_pipeline.prepare_execution_setup
_run_execution_pipeline = execute_task_pipeline.run_execution_pipeline
_ExecutionRuntimeState = execute_task_pipeline.ExecutionRuntimeState
_maybe_execute_temporal_workflow = execute_task_pipeline.maybe_execute_temporal_workflow


def _prepare_runtime_and_policy_gates(**kwargs: Any) -> dict[str, Any]:
    return execute_task_pipeline.prepare_runtime_and_policy_gates(
        preflight_gate_pipeline_module=preflight_gate_pipeline,
        find_wide_paths_fn=find_wide_paths,
        validate_integrated_tools_fn=validate_integrated_tools,
        validate_mcp_concurrency_fn=validate_mcp_concurrency,
        validate_mcp_tools_fn=validate_mcp_tools,
        requires_network_items_fn=requires_network_items,
        validate_network_policy_fn=validate_network_policy,
        validate_sampling_policy_fn=validate_sampling_policy,
        validate_command_fn=validate_command,
        acquire_lock_with_cleanup_fn=acquire_lock_with_cleanup,
        release_lock_fn=release_lock,
        resolve_lock_ttl_fn=resolve_lock_ttl,
        detect_agents_overrides_fn=_detect_agents_overrides,
        collect_patch_artifacts_fn=_collect_patch_artifacts,
        should_apply_dependency_patches_fn=_should_apply_dependency_patches,
        apply_dependency_patches_fn=_apply_dependency_patches,
        load_search_requests_fn=_load_search_requests,
        load_browser_tasks_fn=_load_browser_tasks,
        load_tampermonkey_tasks_fn=_load_tampermonkey_tasks,
        await_human_approval_fn=_await_human_approval,
        requires_human_approval_fn=_requires_human_approval,
        **kwargs,
    )


def _append_run_event(
    store: RunStore,
    run_id: str,
    *,
    level: str,
    event: str,
    meta: dict[str, Any],
) -> None:
    store.append_event(run_id, {"level": level, "event": event, "run_id": run_id, "meta": meta})


class Orchestrator:
    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root
        self._store = RunStore()
        self._validator = ContractValidator()
        self._reviewer = Reviewer()

    def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, Any]:
        runner = ReplayRunner(self._store, self._validator)
        return _execute_replay_action(
            runner=runner,
            action="replay",
            run_id=run_id,
            baseline_run_id=baseline_run_id,
            store=self._store,
            event="REPLAY_FAILED",
        )

    def replay_verify(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        runner = ReplayRunner(self._store, self._validator)
        return _execute_replay_action(
            runner=runner,
            action="verify",
            run_id=run_id,
            strict=strict,
            store=self._store,
            event="REPLAY_VERIFY_FAILED",
        )

    def replay_reexec(self, run_id: str, strict: bool = True) -> dict[str, Any]:
        runner = ReplayRunner(self._store, self._validator)
        return _execute_replay_action(
            runner=runner,
            action="reexecute",
            run_id=run_id,
            strict=strict,
            store=self._store,
            event="REEXEC_RESULT",
        )

    def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict[str, Any]:
        runner = ChainRunner(self._repo_root, self._store, self.execute_task)
        return runner.run_chain(chain_path, mock_mode=mock_mode)

    @trace_span("orchestrator.execute_task")
    def execute_task(self, contract_path: Path, mock_mode: bool = False) -> str:
        contract_path = contract_path.resolve()
        contract = self._validator.validate_contract(_read_contract(contract_path))
        log_event("INFO", "scheduler", "EXECUTE_TASK", run_id="", meta={"contract": str(contract_path)})

        store = self._store
        temporal_run_id, temporal_fallback_error = _maybe_execute_temporal_workflow(
            repo_root=self._repo_root,
            store=store,
            contract_path=contract_path,
            contract=contract,
            mock_mode=mock_mode,
            run_workflow_fn=run_workflow,
            temporal_required_fn=temporal_required,
            ensure_evidence_bundle_placeholder_fn=_ensure_evidence_bundle_placeholder,
        )
        if temporal_run_id:
            return temporal_run_id

        setup = _prepare_execution_setup(
            repo_root=self._repo_root,
            store=store,
            contract=contract,
            mock_mode=mock_mode,
            run_store_cls=RunStore,
            allow_codex_exec_fn=policy_pipeline.allow_codex_exec,
            mcp_only_enabled_fn=policy_pipeline.mcp_only_enabled,
            resolve_policy_pack_fn=policy_pipeline.resolve_policy_pack,
            pick_profile_fn=pick_profile,
            build_log_refs_fn=_build_log_refs,
            extract_user_request_fn=_extract_user_request,
            now_ts_fn=_now_ts,
            tool_version_fn=_tool_version,
            trace_url_fn=_trace_url,
            write_manifest_fn=_write_manifest,
            contract_state_writer_cls=_ContractStateWriter,
            hash_contract_fn=hash_contract,
            write_contract_signature_fn=_write_contract_signature,
        )
        store = setup.store
        contract = setup.contract
        run_id = setup.run_id
        task_id = setup.task_id
        trace_id = setup.trace_id
        manifest: dict[str, Any] | None = setup.manifest
        state_writer = setup.state_writer
        runner_name = setup.runner_name
        allow_codex_exec = setup.allow_codex_exec
        mcp_only = setup.mcp_only
        workflow_id = setup.workflow_id
        workflow_info = setup.workflow_info
        assigned_agent = setup.assigned_agent
        policy_pack = setup.policy_pack
        profile = setup.profile
        start_ts = setup.start_ts
        codex_version = setup.codex_version
        git_version = setup.git_version
        trace_url = setup.trace_url
        try:
            observability = ensure_tracing()
        except Exception as exc:  # noqa: BLE001
            failure_reason = f"observability required: {exc}"
            _append_policy_violation(
                store,
                run_id,
                    failure_reason,
                    extra={"path": "observability", "required": True},
                )
            state_writer.persist(
                mark_failure_manifest=True,
                failure_reason=failure_reason,
                write_signature=True,
                ensure_evidence_bundle_fn=_ensure_evidence_bundle_placeholder,
            )
            return run_id
        manifest["observability"] = observability
        _write_manifest(store, run_id, manifest)
        if not observability.get("enabled"):
            _append_run_event(store, run_id, level="INFO", event="OBSERVABILITY_DISABLED", meta=observability)
        _ensure_evidence_bundle_placeholder(store, run_id, contract, "evidence bundle placeholder")
        if workflow_info:
            _append_run_event(store, run_id, level="INFO", event="WORKFLOW_BOUND", meta=dict(workflow_info))
        store.write_meta(
            run_id,
            {
                "run_id": run_id,
                "task_id": task_id,
                "start_ts": start_ts,
                "repo_root": str(self._repo_root),
                "python": sys.version,
                "platform": platform.platform(),
                "tool_versions": {
                    "codex": codex_version,
                    "git": git_version,
                },
                "llm_params": _llm_params_snapshot(contract, runner_name, codex_version),
                "trace_id": trace_id,
                "trace_url": trace_url,
                "workflow_id": workflow_id,
            },
        )

        schema_status = check_schema_registry(self._repo_root / "schemas")
        _append_run_event(
            store, run_id, level="INFO" if schema_status.get("status") == "ok" else "WARN", event="SCHEMA_REGISTRY_CHECK", meta=schema_status
        )

        if policy_pack:
            _append_run_event(
                store,
                run_id,
                level="INFO",
                event="POLICY_PACK_SELECTED",
                meta={"policy_pack": policy_pack, "role": policy_pipeline.agent_role(assigned_agent)},
            )

        if mcp_only:
            _append_run_event(
                store,
                run_id,
                level="INFO",
                event="MCP_ONLY_ENFORCED",
                meta={
                    "runner": runner_name,
                    "mock_mode": mock_mode,
                    "allow_codex_exec": allow_codex_exec,
                },
            )

        if mcp_only and runner_name != "agents" and not mock_mode and not allow_codex_exec:
            failure_reason = "mcp-only enforced: non-agents runner blocked"
            _append_run_event(
                store,
                run_id,
                level="ERROR",
                event="MCP_ONLY_BLOCKED",
                meta={"runner": runner_name, "reason": failure_reason},
            )
            state_writer.persist(mark_failure_manifest=True, failure_reason=failure_reason, write_signature=True)
            return run_id

        should_exit_after_temporal_start = _notify_temporal_start_and_fail_if_required(
            run_id=run_id,
            task_id=task_id,
            runner_name=runner_name,
            trace_id=trace_id,
            store=store,
            manifest=manifest,
            now_ts_fn=_now_ts,
            write_manifest_fn=_write_manifest,
            notify_run_started_fn=notify_run_started,
            temporal_required_fn=temporal_required,
        )
        if should_exit_after_temporal_start:
            return run_id

        _append_run_event(
            store,
            run_id,
            level="INFO",
            event="STEP_STARTED",
            meta={"contract": str(contract_path)},
        )
        if temporal_fallback_error:
            _append_run_event(
                store,
                run_id,
                level="WARN",
                event="TEMPORAL_WORKFLOW_FALLBACK",
                meta={"error": temporal_fallback_error},
            )

        execution_state = _ExecutionRuntimeState()

        try:
            with execute_task_pipeline.isolated_execution_env():
                os.environ["CORTEXPILOT_RUN_ID"] = run_id
                os.environ["CORTEXPILOT_TRACE_ID"] = trace_id
                os.environ["CORTEXPILOT_CODEX_VERSION"] = codex_version
                if profile:
                    os.environ["CORTEXPILOT_CODEX_PROFILE"] = profile
                else:
                    os.environ.pop("CORTEXPILOT_CODEX_PROFILE", None)
                execution_state = _run_execution_pipeline(
                    run_id=run_id,
                    task_id=task_id,
                    store=store,
                    contract=contract,
                    repo_root=self._repo_root,
                    mock_mode=mock_mode,
                    assigned_agent=assigned_agent,
                    policy_pack=policy_pack,
                    runner_name=runner_name,
                    mcp_only=mcp_only,
                    profile=profile,
                    reviewer=self._reviewer,
                    start_ts=start_ts,
                    manifest=manifest or {},
                    state_writer=state_writer,
                    baseline_commit_fn=_baseline_commit,
                    resolve_baseline_ref_fn=_resolve_baseline_ref,
                    load_agent_registry_fn=artifact_pipeline.load_agent_registry,
                    validate_assigned_agent_fn=artifact_pipeline.validate_assigned_agent,
                    find_registry_entry_fn=policy_pipeline.find_registry_entry,
                    resolve_codex_home_fn=policy_pipeline.resolve_codex_home,
                    agent_role_fn=policy_pipeline.agent_role,
                    tool_permissions_fn=policy_pipeline.tool_permissions,
                    network_policy_fn=policy_pipeline.network_policy,
                    append_policy_violation_fn=_append_policy_violation,
                    gate_result_fn=_gate_result,
                    schema_root_fn=_schema_root,
                    per_run_codex_home_enabled_fn=_per_run_codex_home_enabled,
                    materialize_codex_home_fn=_materialize_codex_home,
                    apply_role_defaults_fn=_apply_role_defaults,
                    write_running_contract_manifest_fn=_write_running_contract_manifest,
                    manifest_task_role_fn=_manifest_task_role,
                    artifact_ref_from_path_fn=_artifact_ref_from_path,
                    write_manifest_fn=_write_manifest,
                    prepare_runtime_and_policy_gates_fn=_prepare_runtime_and_policy_gates,
                    run_optional_tool_requests_fn=_run_optional_tool_requests,
                    run_search_pipeline_fn=_run_search_pipeline,
                    run_browser_tasks_fn=_run_browser_tasks,
                    run_tampermonkey_tasks_fn=_run_tampermonkey_tasks,
                    run_sampling_requests_fn=_run_sampling_requests,
                    run_runner_fix_review_flow_fn=_run_runner_fix_review_flow,
                    select_runner_fn=_select_runner,
                    scoped_revert_fn=_scoped_revert,
                    validate_diff_fn=validate_diff,
                    run_acceptance_tests_fn=run_acceptance_tests,
                    run_evals_gate_fn=run_evals_gate,
                    task_execution_pipeline_module=task_execution_pipeline,
                    snapshot_worktree_fn=snapshot_worktree,
                    validate_reviewer_isolation_fn=validate_reviewer_isolation,
                    collect_diff_text_fn=_collect_diff_text,
                    git_fn=_git,
                    extract_test_logs_fn=_extract_test_logs,
                    cleanup_test_artifacts_fn=_cleanup_test_artifacts,
                    tool_runner_cls=ToolRunner,
                )
            return run_id
        except Exception as exc:  # noqa: BLE001
            execution_state.failure_reason = str(exc)
            import traceback
            tb = traceback.format_exc()
            _append_run_event(
                store,
                run_id,
                level="ERROR",
                event="EXCEPTION",
                meta={"error": execution_state.failure_reason, "traceback": tb},
            )
            return run_id
        finally:
            _finalize_execute_task_run(
                store=store,
                run_id=run_id,
                task_id=task_id,
                locked=execution_state.locked,
                allowed_paths=execution_state.allowed_paths,
                worktree_path=execution_state.worktree_path,
                status=execution_state.status,
                failure_reason=execution_state.failure_reason,
                manifest=manifest,
                attempt=execution_state.attempt,
                start_ts=start_ts,
                tests_result=execution_state.tests_result,
                test_report=execution_state.test_report,
                review_report=execution_state.review_report,
                policy_gate_result=execution_state.policy_gate_result,
                integrated_gate=execution_state.integrated_gate,
                network_gate=execution_state.network_gate,
                mcp_gate=execution_state.mcp_gate,
                sampling_gate=execution_state.sampling_gate,
                tool_gate=execution_state.tool_gate,
                human_approval_required=execution_state.human_approval_required,
                human_approved=execution_state.human_approved,
                contract=contract,
                runner_summary=execution_state.runner_summary,
                diff_gate_result=execution_state.diff_gate_result,
                review_gate_result=execution_state.review_gate_result,
                baseline_ref=execution_state.baseline_ref,
                head_ref=execution_state.head_ref,
                search_request=execution_state.search_request,
                tamper_request=execution_state.tamper_request,
                task_result=execution_state.task_result,
            )


__all__ = ["Orchestrator"]
