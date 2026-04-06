from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import evaluate_superpowers_gate
from cortexpilot_orch.gates.diff_gate import validate_diff
from cortexpilot_orch.gates.reviewer_gate import snapshot_worktree, validate_reviewer_isolation
from cortexpilot_orch.gates.tests_gate import run_acceptance_tests, run_evals_gate
from cortexpilot_orch.scheduler import (
    gate_orchestration,
    policy_pipeline,
    runtime_utils,
    scheduler_bridge,
    test_pipeline,
    task_execution_runtime_helpers,
    core_helpers,
)
from cortexpilot_orch.store.run_store import RunStore

_append_gate_failed = gate_orchestration.append_gate_failed
_extract_user_request = core_helpers.extract_user_request
_extract_evidence_refs = core_helpers.extract_evidence_refs
_sha256_text = core_helpers.sha256_text

_extract_test_logs = test_pipeline.extract_test_logs
_cleanup_test_artifacts = test_pipeline.cleanup_test_artifacts

_schema_path = runtime_utils.schema_path
_schema_root = runtime_utils.schema_root
_collect_diff_text = runtime_utils.collect_diff_text
_git = runtime_utils.git


def _build_result(
    *,
    ok: bool,
    attempt: int,
    failure_reason: str,
    runner_summary: str,
    diff_gate_result: dict[str, Any] | None,
    tests_result: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    task_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_gate_result: dict[str, Any] | None,
    head_ref: str,
    superpowers_gate_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "attempt": attempt,
        "failure_reason": failure_reason,
        "runner_summary": runner_summary,
        "diff_gate_result": diff_gate_result,
        "tests_result": tests_result,
        "review_report": review_report,
        "task_result": task_result,
        "test_report": test_report,
        "review_gate_result": review_gate_result,
        "head_ref": head_ref,
        "superpowers_gate_result": superpowers_gate_result,
    }


def run_runner_fix_review_flow(
    *,
    run_id: str,
    task_id: str,
    store: RunStore,
    contract: dict[str, Any],
    worktree_path: Path,
    allowed_paths: list[str],
    baseline_ref: str,
    mock_mode: bool,
    policy_pack: str,
    network_policy: str,
    runner_name: str,
    mcp_only: bool,
    profile: str,
    assigned_agent: dict[str, Any],
    repo_root: Path,
    reviewer: Any,
    start_ts: str,
    attempt: int,
    select_runner_fn: Callable[[dict[str, Any], RunStore], Any] = scheduler_bridge.select_runner,
    scoped_revert_fn: Callable[[Path, list[str]], dict[str, Any]] = scheduler_bridge.scoped_revert,
    validate_diff_fn: Callable[..., dict[str, Any]] = validate_diff,
    run_acceptance_tests_fn: Callable[..., dict[str, Any]] = run_acceptance_tests,
    run_evals_gate_fn: Callable[..., dict[str, Any]] = run_evals_gate,
) -> dict[str, Any]:
    _ = start_ts
    superpowers_gate_result = evaluate_superpowers_gate(contract)
    if superpowers_gate_result.get("required"):
        gate_ok = bool(superpowers_gate_result.get("ok"))
        store.append_event(
            run_id,
            {
                "level": "INFO" if gate_ok else "ERROR",
                "event": "SUPERPOWERS_GATE_PASS" if gate_ok else "SUPERPOWERS_GATE_FAIL",
                "run_id": run_id,
                "meta": superpowers_gate_result,
            },
        )
        if not gate_ok:
            _append_gate_failed(
                store,
                run_id,
                "superpowers_gate",
                "superpowers methodology gate violation",
                extra=superpowers_gate_result,
            )
            return _build_result(
                ok=False,
                attempt=attempt,
                failure_reason="superpowers gate violation",
                runner_summary="",
                diff_gate_result=None,
                tests_result=None,
                review_report=None,
                task_result=None,
                test_report=None,
                review_gate_result=None,
                head_ref="",
                superpowers_gate_result=superpowers_gate_result,
            )

    return task_execution_runtime_helpers.run_runner_fix_review_flow_runtime(
        run_id=run_id,
        task_id=task_id,
        store=store,
        contract=contract,
        worktree_path=worktree_path,
        allowed_paths=allowed_paths,
        baseline_ref=baseline_ref,
        mock_mode=mock_mode,
        policy_pack=policy_pack,
        network_policy=network_policy,
        runner_name=runner_name,
        mcp_only=mcp_only,
        profile=profile,
        assigned_agent=assigned_agent,
        repo_root=repo_root,
        reviewer=reviewer,
        attempt=attempt,
        build_result_fn=_build_result,
        select_runner_fn=select_runner_fn,
        scoped_revert_fn=scoped_revert_fn,
        validate_diff_fn=validate_diff_fn,
        run_acceptance_tests_fn=run_acceptance_tests_fn,
        run_evals_gate_fn=run_evals_gate_fn,
        append_gate_failed_fn=_append_gate_failed,
        extract_test_logs_fn=_extract_test_logs,
        cleanup_test_artifacts_fn=_cleanup_test_artifacts,
        schema_path_fn=_schema_path,
        schema_root_fn=_schema_root,
        collect_diff_text_fn=_collect_diff_text,
        git_fn=_git,
        extract_user_request_fn=_extract_user_request,
        extract_evidence_refs_fn=_extract_evidence_refs,
        sha256_text_fn=_sha256_text,
        codex_shell_policy_fn=policy_pipeline.codex_shell_policy,
        acceptance_tests_fn=policy_pipeline.acceptance_tests,
        forbidden_actions_fn=policy_pipeline.forbidden_actions,
        max_retries_fn=scheduler_bridge.max_retries,
        retry_backoff_fn=scheduler_bridge.retry_backoff,
        apply_rollback_fn=scheduler_bridge.apply_rollback,
        snapshot_worktree_fn=snapshot_worktree,
        validate_reviewer_isolation_fn=validate_reviewer_isolation,
    ) | {"superpowers_gate_result": superpowers_gate_result}
