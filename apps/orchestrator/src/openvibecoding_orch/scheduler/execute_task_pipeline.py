from __future__ import annotations

import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.scheduler.execute_task_preflight import (
    maybe_execute_temporal_workflow,
    prepare_runtime_and_policy_gates,
)
from openvibecoding_orch.scheduler.execute_task_types import ExecutionRuntimeState, ExecutionSetup


@contextmanager
def isolated_execution_env() -> Any:
    snapshot_openvibecoding_run_id = os.environ.get("OPENVIBECODING_RUN_ID")
    snapshot_openvibecoding_trace_id = os.environ.get("OPENVIBECODING_TRACE_ID")
    snapshot_openvibecoding_codex_profile = os.environ.get("OPENVIBECODING_CODEX_PROFILE")
    snapshot_openvibecoding_codex_version = os.environ.get("OPENVIBECODING_CODEX_VERSION")
    snapshot_openvibecoding_network_approved = os.environ.get("OPENVIBECODING_NETWORK_APPROVED")
    snapshot_codex_home = os.environ.get("CODEX_HOME")
    try:
        yield
    finally:
        if snapshot_openvibecoding_run_id is None:
            os.environ.pop("OPENVIBECODING_RUN_ID", None)
        else:
            os.environ["OPENVIBECODING_RUN_ID"] = snapshot_openvibecoding_run_id
        if snapshot_openvibecoding_trace_id is None:
            os.environ.pop("OPENVIBECODING_TRACE_ID", None)
        else:
            os.environ["OPENVIBECODING_TRACE_ID"] = snapshot_openvibecoding_trace_id
        if snapshot_openvibecoding_codex_profile is None:
            os.environ.pop("OPENVIBECODING_CODEX_PROFILE", None)
        else:
            os.environ["OPENVIBECODING_CODEX_PROFILE"] = snapshot_openvibecoding_codex_profile
        if snapshot_openvibecoding_codex_version is None:
            os.environ.pop("OPENVIBECODING_CODEX_VERSION", None)
        else:
            os.environ["OPENVIBECODING_CODEX_VERSION"] = snapshot_openvibecoding_codex_version
        if snapshot_openvibecoding_network_approved is None:
            os.environ.pop("OPENVIBECODING_NETWORK_APPROVED", None)
        else:
            os.environ["OPENVIBECODING_NETWORK_APPROVED"] = snapshot_openvibecoding_network_approved
        if snapshot_codex_home is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = snapshot_codex_home


def prepare_execution_setup(
    *,
    repo_root: Path,
    store: RunStore,
    contract: dict[str, Any],
    mock_mode: bool,
    run_store_cls: type[RunStore],
    allow_codex_exec_fn: Callable[[], bool],
    mcp_only_enabled_fn: Callable[[], bool],
    resolve_policy_pack_fn: Callable[[dict[str, Any]], str],
    pick_profile_fn: Callable[[], str | None],
    build_log_refs_fn: Callable[[str, str, Path, str], dict[str, Any]],
    extract_user_request_fn: Callable[[dict[str, Any]], str],
    now_ts_fn: Callable[[], str],
    tool_version_fn: Callable[[list[str]], str],
    trace_url_fn: Callable[[str, str], str],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
    contract_state_writer_cls: type[Any],
    hash_contract_fn: Callable[[dict[str, Any]], str],
    write_contract_signature_fn: Callable[..., Any],
) -> ExecutionSetup:
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
    runtime_runner = str(runtime_options.get("runner", "")).strip().lower()
    runner_name = runtime_runner or os.getenv("OPENVIBECODING_RUNNER", "agents").strip().lower()
    allow_codex_exec = allow_codex_exec_fn()
    parent_task_id = str(contract.get("parent_task_id", "")).strip()
    diagnostic_root_override = os.getenv("OPENVIBECODING_DIAGNOSTIC_RUNS_ROOT", "").strip()
    runs_root_override = os.getenv("OPENVIBECODING_RUNS_ROOT", "").strip()
    diagnostic_mode = (
        runner_name == "codex"
        and allow_codex_exec
        and not parent_task_id
        and (bool(diagnostic_root_override) or not bool(runs_root_override))
        and (not mock_mode or bool(diagnostic_root_override))
    )
    if diagnostic_mode:
        raw_root = diagnostic_root_override or ".runtime-cache/openvibecoding/runs_diagnostic"
        diagnostic_root = Path(raw_root) if raw_root else Path(".runtime-cache/openvibecoding/runs_diagnostic")
        store = run_store_cls(runs_root=diagnostic_root)

    task_id = contract.get("task_id", "task")
    run_id = store.create_run(task_id)
    trace_id = uuid.uuid4().hex

    mcp_only = mcp_only_enabled_fn()
    workflow_id = os.getenv("OPENVIBECODING_TEMPORAL_WORKFLOW_ID", "").strip()
    workflow_info: dict[str, Any] | None = None
    if workflow_id:
        workflow_info = {
            "workflow_id": workflow_id,
            "task_queue": os.getenv("OPENVIBECODING_TEMPORAL_TASK_QUEUE", "openvibecoding-orch"),
            "namespace": os.getenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "default"),
            "status": "RUNNING",
        }

    contract = json.loads(json.dumps(contract, ensure_ascii=False))
    assigned_agent = contract.get("assigned_agent", {}) if isinstance(contract.get("assigned_agent"), dict) else {}
    policy_pack = resolve_policy_pack_fn(contract)
    contract["policy_pack"] = policy_pack

    profile = os.getenv("OPENVIBECODING_CODEX_PROFILE", "").strip()
    if not profile:
        profile = pick_profile_fn() or ""
    contract["log_refs"] = build_log_refs_fn(run_id, task_id, store._runs_root, trace_id)

    store.write_trace_id(run_id, trace_id)

    start_ts = now_ts_fn()
    codex_version = tool_version_fn(["codex", "--version"])
    git_version = tool_version_fn(["git", "--version"])
    user_request = extract_user_request_fn(contract) or "missing spec"
    trace_url = trace_url_fn(trace_id, run_id)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "created_at": start_ts,
        "status": "RUNNING",
        "user_request": user_request,
        "trace_id": trace_id,
        "diagnostic": diagnostic_mode,
        "runner": {
            "name": runner_name,
            "mcp_only": mcp_only,
            "profile": profile,
        },
        "policy_pack": policy_pack,
        "repo": {
            "root": str(repo_root),
            "baseline_ref": "",
        },
        "versions": {
            "contracts_schema": "v1",
            "orchestrator": os.getenv("OPENVIBECODING_ORCHESTRATOR_VERSION", "local"),
            "codex_cli": codex_version or "unknown",
            "python": sys.version.split()[0],
            "node": os.getenv("OPENVIBECODING_NODE_VERSION", ""),
        },
        "tasks": [],
        "artifacts": [],
        "evidence_hashes": {},
        "trace_id": trace_id,
        "trace": {"trace_id": trace_id, "trace_url": trace_url} if trace_url else {"trace_id": trace_id},
    }
    if workflow_info:
        manifest["workflow"] = workflow_info
    write_manifest_fn(store, run_id, manifest)
    state_writer = contract_state_writer_cls(
        store=store,
        run_id=run_id,
        task_id=task_id,
        contract=contract,
        manifest=manifest,
        hash_contract_fn=hash_contract_fn,
        write_manifest_fn=write_manifest_fn,
        write_contract_signature_fn=write_contract_signature_fn,
        now_ts_fn=now_ts_fn,
    )
    return ExecutionSetup(
        store=store,
        contract=contract,
        run_id=run_id,
        task_id=task_id,
        trace_id=trace_id,
        manifest=manifest,
        state_writer=state_writer,
        runner_name=runner_name,
        allow_codex_exec=allow_codex_exec,
        mcp_only=mcp_only,
        workflow_id=workflow_id,
        workflow_info=workflow_info,
        assigned_agent=assigned_agent,
        policy_pack=policy_pack,
        profile=profile,
        start_ts=start_ts,
        codex_version=codex_version,
        git_version=git_version,
        trace_url=trace_url,
        diagnostic_mode=diagnostic_mode,
    )


def run_execution_pipeline(
    *,
    run_id: str,
    task_id: str,
    store: RunStore,
    contract: dict[str, Any],
    repo_root: Path,
    mock_mode: bool,
    assigned_agent: dict[str, Any],
    policy_pack: str,
    runner_name: str,
    mcp_only: bool,
    profile: str,
    reviewer: Any,
    start_ts: str,
    manifest: dict[str, Any],
    state_writer: Any,
    baseline_commit_fn: Callable[[Path], str],
    resolve_baseline_ref_fn: Callable[[dict[str, Any], str], str],
    load_agent_registry_fn: Callable[[Path, Path], tuple[dict[str, Any] | None, str | None]],
    validate_assigned_agent_fn: Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]],
    find_registry_entry_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | None],
    resolve_codex_home_fn: Callable[[dict[str, Any] | None, Path], tuple[str | None, str | None]],
    agent_role_fn: Callable[[dict[str, Any]], str],
    tool_permissions_fn: Callable[[dict[str, Any]], Any],
    network_policy_fn: Callable[[dict[str, Any]], str],
    append_policy_violation_fn: Callable[..., None],
    gate_result_fn: Callable[[bool, list[str] | None], dict[str, Any]],
    schema_root_fn: Callable[[], Path],
    per_run_codex_home_enabled_fn: Callable[[], bool],
    materialize_codex_home_fn: Callable[[Path, str, Path], Path],
    apply_role_defaults_fn: Callable[[dict[str, Any], dict[str, Any] | None], tuple[dict[str, Any], list[str]]],
    write_running_contract_manifest_fn: Callable[..., None],
    manifest_task_role_fn: Callable[[dict[str, Any] | None], str],
    artifact_ref_from_path_fn: Callable[..., dict[str, Any]],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
    prepare_runtime_and_policy_gates_fn: Callable[..., dict[str, Any]],
    run_optional_tool_requests_fn: Callable[..., str],
    run_search_pipeline_fn: Callable[..., dict[str, Any]],
    run_browser_tasks_fn: Callable[..., dict[str, Any]],
    run_tampermonkey_tasks_fn: Callable[..., dict[str, Any]],
    run_sampling_requests_fn: Callable[..., dict[str, Any]],
    run_runner_fix_review_flow_fn: Callable[..., dict[str, Any]],
    select_runner_fn: Callable[..., Any],
    scoped_revert_fn: Callable[[Path, list[str]], dict[str, Any]],
    validate_diff_fn: Callable[..., dict[str, Any]],
    run_acceptance_tests_fn: Callable[..., dict[str, Any]],
    run_evals_gate_fn: Callable[..., dict[str, Any]],
    task_execution_pipeline_module: Any,
    snapshot_worktree_fn: Callable[..., dict[str, Any]],
    validate_reviewer_isolation_fn: Callable[..., dict[str, Any]],
    collect_diff_text_fn: Callable[[Path], str],
    git_fn: Callable[..., str],
    extract_test_logs_fn: Callable[..., str],
    cleanup_test_artifacts_fn: Callable[..., None],
    tool_runner_cls: type[ToolRunner] = ToolRunner,
) -> ExecutionRuntimeState:
    state = ExecutionRuntimeState()
    try:
        baseline_commit = baseline_commit_fn(repo_root)
    except Exception as exc:  # noqa: BLE001
        state.failure_reason = f"baseline_commit_missing: {exc}"
        store.append_event(
            run_id,
            {
                "level": "ERROR",
                "event": "BASELINE_COMMIT_MISSING",
                "run_id": run_id,
                "meta": {"error": state.failure_reason},
            },
        )
        state_writer.persist(failure_reason=state.failure_reason, write_signature=True)
        return state

    state.baseline_ref = resolve_baseline_ref_fn(contract, baseline_commit)
    rollback = contract.get("rollback", {})
    if isinstance(rollback, dict):
        rollback["baseline_ref"] = state.baseline_ref
        if rollback.get("strategy") == "git_revert_commit":
            target_ref = rollback.get("target_ref")
            if not isinstance(target_ref, str) or not target_ref.strip():
                rollback["target_ref"] = state.baseline_ref
                store.append_event(
                    run_id,
                    {
                        "level": "WARN",
                        "event": "ROLLBACK_SEMANTICS_DEPRECATED",
                        "run_id": run_id,
                        "meta": {
                            "strategy": "git_revert_commit",
                            "target_ref": state.baseline_ref,
                            "note": "rollback.target_ref missing; fallback to baseline_ref",
                        },
                    },
                )
        contract["rollback"] = rollback

    registry, registry_error = load_agent_registry_fn(repo_root, schema_root_fn())
    if registry_error:
        state.failure_reason = registry_error
        append_policy_violation_fn(
            store,
            run_id,
            registry_error,
            extra={"reason": registry_error, "path": "agent_registry.json"},
        )
        state.policy_gate_result = gate_result_fn(False, [registry_error])
        state_writer.persist(
            baseline_ref_for_manifest=state.baseline_ref,
            baseline_commit=baseline_commit,
        )
        return state

    ok, registry_violation = validate_assigned_agent_fn(registry or {}, assigned_agent)
    if not ok:
        state.failure_reason = registry_violation
        append_policy_violation_fn(
            store,
            run_id,
            registry_violation,
            extra={"reason": registry_violation, "path": "agent_registry.json"},
        )
        state.policy_gate_result = gate_result_fn(False, [registry_violation])
        state_writer.persist(
            baseline_ref_for_manifest=state.baseline_ref,
            baseline_commit=baseline_commit,
        )
        return state

    entry = find_registry_entry_fn(registry or {}, assigned_agent)
    if not mock_mode:
        codex_home, codex_error = resolve_codex_home_fn(entry, repo_root)
        if codex_error:
            state.failure_reason = codex_error
            append_policy_violation_fn(
                store,
                run_id,
                codex_error,
                extra={"reason": codex_error, "path": "agent_registry.json"},
            )
            state.policy_gate_result = gate_result_fn(False, [codex_error])
            state_writer.persist(
                baseline_ref_for_manifest=state.baseline_ref,
                baseline_commit=baseline_commit,
            )
            return state
        if codex_home:
            if per_run_codex_home_enabled_fn():
                runtime_root = Path(os.getenv("OPENVIBECODING_RUNTIME_ROOT", repo_root / ".runtime-cache/openvibecoding")).resolve()
                codex_home = str(materialize_codex_home_fn(Path(codex_home), run_id, runtime_root))
            os.environ["CODEX_HOME"] = codex_home
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "CODEX_HOME_BOUND",
                    "run_id": run_id,
                    "meta": {"codex_home": codex_home, "role": agent_role_fn(assigned_agent)},
                },
            )

    original_permissions = json.loads(json.dumps(tool_permissions_fn(contract), ensure_ascii=False))
    updated_permissions, violations = apply_role_defaults_fn(contract, registry)
    contract["tool_permissions"] = updated_permissions
    if violations:
        append_policy_violation_fn(
            store,
            run_id,
            "tool_permissions exceed role defaults",
            extra={
                "violations": violations,
                "role": agent_role_fn(assigned_agent),
                "original": original_permissions,
                "applied": updated_permissions,
            },
        )

    state_writer.persist(
        baseline_ref_for_manifest=state.baseline_ref,
        baseline_commit=baseline_commit,
    )

    write_running_contract_manifest_fn(
        store=store,
        run_id=run_id,
        task_id=task_id,
        manifest=manifest,
        assigned_agent=assigned_agent,
        run_dir=store._runs_root / run_id,
        manifest_task_role_fn=manifest_task_role_fn,
        artifact_ref_from_path_fn=artifact_ref_from_path_fn,
        write_manifest_fn=write_manifest_fn,
    )

    preflight_result = prepare_runtime_and_policy_gates_fn(
        run_id=run_id,
        task_id=task_id,
        store=store,
        contract=contract,
        repo_root=repo_root,
        baseline_commit=baseline_commit,
        baseline_ref=state.baseline_ref,
        assigned_agent=assigned_agent,
    )
    state.worktree_path = preflight_result["worktree_path"]
    state.locked = preflight_result["locked"]
    state.allowed_paths = preflight_result["allowed_paths"]
    state.policy_gate_result = preflight_result["policy_gate_result"]
    state.integrated_gate = preflight_result["integrated_gate"]
    state.network_gate = preflight_result["network_gate"]
    state.mcp_gate = preflight_result["mcp_gate"]
    state.sampling_gate = preflight_result["sampling_gate"]
    state.tool_gate = preflight_result["tool_gate"]
    state.human_approval_required = preflight_result["human_approval_required"]
    state.human_approved = preflight_result["human_approved"]
    state.search_request = preflight_result["search_request"]
    state.browser_request = preflight_result["browser_request"]
    state.tamper_request = preflight_result["tamper_request"]
    state.sampling_request = preflight_result["sampling_request"]
    state.failure_reason = preflight_result["failure_reason"]
    if not preflight_result["ok"]:
        return state

    tool_runner = tool_runner_cls(run_id, store)
    contract_browser_policy = contract.get("browser_policy") if isinstance(contract.get("browser_policy"), dict) else None
    state.failure_reason = run_optional_tool_requests_fn(
        run_id=run_id,
        store=store,
        tool_runner=tool_runner,
        assigned_agent=assigned_agent,
        contract_browser_policy=contract_browser_policy,
        search_request=state.search_request,
        browser_request=state.browser_request,
        tamper_request=state.tamper_request,
        sampling_request=state.sampling_request,
        run_search_pipeline_fn=run_search_pipeline_fn,
        run_browser_tasks_fn=run_browser_tasks_fn,
        run_tampermonkey_tasks_fn=run_tampermonkey_tasks_fn,
        run_sampling_requests_fn=run_sampling_requests_fn,
    )
    if state.failure_reason:
        return state

    assigned_role = agent_role_fn(assigned_agent)
    if assigned_role in {"SEARCHER", "RESEARCHER"} and state.search_request is not None:
        state.runner_summary = "Search pipeline completed successfully."
        state.status = "SUCCESS"
        return state

    task_execution_pipeline_module.snapshot_worktree = snapshot_worktree_fn
    task_execution_pipeline_module.validate_reviewer_isolation = validate_reviewer_isolation_fn
    task_execution_pipeline_module._collect_diff_text = collect_diff_text_fn
    task_execution_pipeline_module._git = git_fn
    task_execution_pipeline_module._extract_test_logs = extract_test_logs_fn
    task_execution_pipeline_module._cleanup_test_artifacts = cleanup_test_artifacts_fn

    flow_result = run_runner_fix_review_flow_fn(
        run_id=run_id,
        task_id=task_id,
        store=store,
        contract=contract,
        worktree_path=state.worktree_path,
        allowed_paths=state.allowed_paths,
        baseline_ref=state.baseline_ref,
        mock_mode=mock_mode,
        policy_pack=policy_pack,
        network_policy=network_policy_fn(contract),
        runner_name=runner_name,
        mcp_only=mcp_only,
        profile=profile,
        assigned_agent=assigned_agent,
        repo_root=repo_root,
        reviewer=reviewer,
        start_ts=start_ts,
        attempt=state.attempt,
        select_runner_fn=select_runner_fn,
        scoped_revert_fn=scoped_revert_fn,
        validate_diff_fn=validate_diff_fn,
        run_acceptance_tests_fn=run_acceptance_tests_fn,
        run_evals_gate_fn=run_evals_gate_fn,
    )
    state.attempt = flow_result["attempt"]
    state.failure_reason = flow_result["failure_reason"]
    state.runner_summary = flow_result["runner_summary"]
    state.diff_gate_result = flow_result["diff_gate_result"]
    state.tests_result = flow_result["tests_result"]
    state.review_report = flow_result["review_report"]
    state.task_result = flow_result["task_result"]
    state.test_report = flow_result["test_report"]
    state.review_gate_result = flow_result["review_gate_result"]
    state.head_ref = flow_result["head_ref"]
    if not flow_result["ok"]:
        return state

    state.status = "SUCCESS"
    return state
