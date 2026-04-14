from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.scheduler import task_execution_review_helpers
from openvibecoding_orch.store.run_store import RunStore

_TRUTHY_VALUES = {"1", "true", "yes", "y", "on"}
_FALSY_VALUES = {"0", "false", "no", "n", "off"}


@dataclass
class RunnerFixReviewState:
    failure_reason: str = ""
    runner_summary: str = ""
    diff_gate_result: dict[str, Any] | None = None
    tests_result: dict[str, Any] | None = None
    review_report: dict[str, Any] | None = None
    task_result: dict[str, Any] | None = None
    test_report: dict[str, Any] | None = None
    review_gate_result: dict[str, Any] | None = None
    head_ref: str = ""
    diff_text: str = ""
    attempt: int = 0


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUTHY_VALUES:
            return True
        if normalized in _FALSY_VALUES:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def run_runner_fix_review_flow_runtime(
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
    attempt: int,
    build_result_fn: Callable[..., dict[str, Any]],
    select_runner_fn: Callable[[dict[str, Any], RunStore], Any],
    scoped_revert_fn: Callable[[Path, list[str]], dict[str, Any]],
    validate_diff_fn: Callable[..., dict[str, Any]],
    run_acceptance_tests_fn: Callable[..., dict[str, Any]],
    run_evals_gate_fn: Callable[..., dict[str, Any]],
    append_gate_failed_fn: Callable[..., None],
    extract_test_logs_fn: Callable[..., tuple[str, str, str]],
    cleanup_test_artifacts_fn: Callable[..., None],
    schema_path_fn: Callable[[], Path],
    schema_root_fn: Callable[[], Path],
    collect_diff_text_fn: Callable[[Path], str],
    git_fn: Callable[..., str],
    extract_user_request_fn: Callable[[dict[str, Any]], str],
    extract_evidence_refs_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    sha256_text_fn: Callable[[str], str],
    codex_shell_policy_fn: Callable[[dict[str, Any]], dict[str, Any]],
    acceptance_tests_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    forbidden_actions_fn: Callable[[dict[str, Any]], list[str]],
    max_retries_fn: Callable[[dict[str, Any]], int],
    retry_backoff_fn: Callable[[dict[str, Any]], int],
    apply_rollback_fn: Callable[[Path, dict[str, Any]], dict[str, Any]],
    snapshot_worktree_fn: Callable[[Path], dict[str, Any]],
    validate_reviewer_isolation_fn: Callable[[Path, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    state = RunnerFixReviewState(attempt=attempt)
    runner = select_runner_fn(contract, store)
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "RUNNER_SELECTED",
            "run_id": run_id,
            "meta": {
                "runner": runner.__class__.__name__,
                "runner_name": runner_name,
                "mcp_only": mcp_only,
                "profile": profile,
            },
        },
    )
    codex_policy = codex_shell_policy_fn(contract)
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "NETWORK_POLICY_CODEX_BLOCKED" if codex_policy["overridden"] else "NETWORK_POLICY_CODEX_ALLOW",
            "run_id": run_id,
            "meta": codex_policy,
        },
    )
    report_validator = ContractValidator(schema_root=schema_root_fn())
    max_retries = max_retries_fn(contract)
    current_contract = dict(contract)

    def finish(ok: bool) -> dict[str, Any]:
        return build_result_fn(
            ok=ok,
            attempt=state.attempt,
            failure_reason=state.failure_reason,
            runner_summary=state.runner_summary,
            diff_gate_result=state.diff_gate_result,
            tests_result=state.tests_result,
            review_report=state.review_report,
            task_result=state.task_result,
            test_report=state.test_report,
            review_gate_result=state.review_gate_result,
            head_ref=state.head_ref,
        )

    while True:
        if state.attempt > 0:
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "FIX_LOOP_ATTEMPT",
                    "run_id": run_id,
                    "meta": {"attempt": state.attempt, "max_retries": max_retries},
                },
            )

        result = runner.run_contract(
            current_contract,
            worktree_path,
            schema_path_fn(),
            mock_mode=mock_mode,
        )
        if result.get("status") != "SUCCESS":
            state.failure_reason = result.get("summary") or result.get("failure_reason", "runner failed")
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "RUNNER_FAILED",
                    "run_id": run_id,
                    "meta": result,
                },
            )
            return finish(False)

        state.head_ref = git_fn(["git", "rev-parse", "HEAD"], cwd=worktree_path)
        state.task_result = dict(result)
        try:
            store.write_artifact(
                run_id,
                "agent_task_result.json",
                json.dumps(state.task_result, ensure_ascii=False, indent=2),
            )
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "AGENT_TASK_RESULT_SNAPSHOT",
                    "run_id": run_id,
                    "meta": {"path": "artifacts/agent_task_result.json"},
                },
            )
        except Exception:  # noqa: BLE001
            pass
        state.runner_summary = str(state.task_result.get("summary", "") or "")
        evidence_refs = extract_evidence_refs_fn(state.task_result)
        llm_snapshot = {
            "runner": runner.__class__.__name__,
            "instruction_sha256": sha256_text_fn(extract_user_request_fn(contract)),
            "instruction_final_sha256": evidence_refs.get("instruction_final_sha256", ""),
            "handoff_chain": evidence_refs.get("handoff_chain", []),
            "thread_id": evidence_refs.get("thread_id") or evidence_refs.get("codex_thread_id") or "",
            "session_id": evidence_refs.get("session_id") or evidence_refs.get("codex_session_id") or "",
        }
        store.write_llm_snapshot(run_id, llm_snapshot)
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "LLM_SNAPSHOT_WRITTEN",
                "run_id": run_id,
                "meta": llm_snapshot,
            },
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "TASK_RESULT_RECORDED",
                "run_id": run_id,
                "meta": {"status": state.task_result.get("status") if state.task_result else ""},
            },
        )

        diff_gate = validate_diff_fn(
            worktree_path,
            allowed_paths,
            baseline_ref=baseline_ref,
        )
        if (
            isinstance(diff_gate, dict)
            and not diff_gate.get("ok")
            and os.getenv("OPENVIBECODING_DIFF_GATE_SCOPED_REVERT", "").strip().lower()
            in {"1", "true", "yes"}
        ):
            revert_result = scoped_revert_fn(worktree_path, diff_gate.get("violations", []))
            store.append_event(
                run_id,
                {
                    "level": "INFO" if revert_result.get("ok") else "ERROR",
                    "event": "DIFF_GATE_SCOPED_REVERT",
                    "run_id": run_id,
                    "meta": revert_result,
                },
            )
            if revert_result.get("ok"):
                diff_gate = validate_diff_fn(
                    worktree_path,
                    allowed_paths,
                    baseline_ref=baseline_ref,
                )
        if isinstance(diff_gate, dict):
            diff_gate["allowed_paths"] = list(allowed_paths)
        state.diff_gate_result = diff_gate
        state.diff_text = collect_diff_text_fn(worktree_path)
        store.write_diff(run_id, state.diff_text)
        store.write_git_patch(run_id, task_id, state.diff_text)
        store.write_diff_names(run_id, diff_gate.get("changed_files", []))
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "DIFF_GATE_RESULT",
                "run_id": run_id,
                "meta": diff_gate,
            },
        )
        if not diff_gate["ok"]:
            append_gate_failed_fn(
                store,
                run_id,
                "diff_gate",
                "diff gate violation",
                extra=diff_gate if isinstance(diff_gate, dict) else None,
            )
            state.failure_reason = "diff gate violation"
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "DIFF_GATE_FAIL",
                    "run_id": run_id,
                    "meta": diff_gate,
                },
            )
            rollback_result = apply_rollback_fn(worktree_path, contract.get("rollback", {}))
            store.append_event(
                run_id,
                {
                    "level": "INFO" if rollback_result.get("ok") else "ERROR",
                    "event": "ROLLBACK_APPLIED",
                    "run_id": run_id,
                    "meta": rollback_result,
                },
            )
            return finish(False)

        runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
        strict_nontrivial_override = None
        if "strict_acceptance" in runtime_options:
            strict_nontrivial_override = _coerce_optional_bool(runtime_options.get("strict_acceptance"))
        state.tests_result = run_acceptance_tests_fn(
            worktree_path,
            acceptance_tests_fn(contract),
            forbidden_actions=forbidden_actions_fn(contract),
            network_policy=network_policy,
            policy_pack=policy_pack,
            strict_nontrivial=strict_nontrivial_override,
        )
        evals_enabled = os.getenv("OPENVIBECODING_EVALS_ENABLED", "").strip().lower() in {"1", "true", "yes"}
        evals_result: dict[str, Any] | None = None
        if evals_enabled:
            evals_result = run_evals_gate_fn(
                repo_root,
                worktree_path,
                forbidden_actions=forbidden_actions_fn(contract),
                network_policy=network_policy,
                policy_pack=policy_pack,
            )
            report = evals_result.get("report") if isinstance(evals_result, dict) else None
            if isinstance(report, dict):
                store.write_report(run_id, "evals_report", report)
            store.append_event(
                run_id,
                {
                    "level": "INFO" if evals_result.get("ok") else "ERROR",
                    "event": "EVAL_GATE_RESULT",
                    "run_id": run_id,
                    "meta": evals_result,
                },
            )
            if not evals_result.get("ok", False):
                state.tests_result["ok"] = False
                state.tests_result["reason"] = "evals failed"
                state.tests_result["evals"] = evals_result
        if state.tests_result.get("reports"):
            normalized_reports = []
            for report in state.tests_result["reports"]:
                payload = dict(report)
                if not payload.get("task_id"):
                    payload["task_id"] = task_id
                payload["run_id"] = run_id
                payload["attempt"] = state.attempt
                try:
                    report_validator.validate_report(payload, "test_report.v1.json")
                except Exception as exc:  # noqa: BLE001
                    state.failure_reason = f"test_report schema invalid: {exc}"
                    append_gate_failed_fn(
                        store,
                        run_id,
                        "schema_validation",
                        state.failure_reason,
                        schema="test_report.v1.json",
                        path="reports/test_report.json",
                    )
                    return finish(False)
                normalized_reports.append(payload)
            state.test_report = dict(normalized_reports[0])
            store.write_report(run_id, "test_report", state.test_report)
            store.write_ci_report(run_id, task_id, state.tests_result)
            cmd_str, stdout_text, stderr_text = extract_test_logs_fn(state.test_report, worktree_path)
            if cmd_str or stdout_text or stderr_text:
                store.write_tests_logs(run_id, cmd_str, stdout_text, stderr_text)
        else:
            store.write_ci_report(run_id, task_id, state.tests_result)
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "TEST_RESULT",
                "run_id": run_id,
                "meta": state.tests_result,
            },
        )
        if state.tests_result["ok"]:
            break

        if state.attempt >= max_retries:
            state.failure_reason = "tests failed after retries"
            append_gate_failed_fn(
                store,
                run_id,
                "tests_gate",
                state.failure_reason,
                extra=state.tests_result if isinstance(state.tests_result, dict) else None,
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "FIX_LOOP_EXHAUSTED",
                    "run_id": run_id,
                    "meta": {"attempt": state.attempt, "max_retries": max_retries},
                },
            )
            return finish(False)

        if state.test_report:
            cleanup_test_artifacts_fn(state.test_report, worktree_path)

        error_blob = json.dumps(state.tests_result, ensure_ascii=False)
        current_contract = json.loads(json.dumps(contract, ensure_ascii=False))
        current_contract["parent_task_id"] = contract.get("task_id")
        inputs = current_contract.get("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {"spec": "", "artifacts": []}
        inputs["spec"] = (
            "Fix failing tests. Use the error log to update code. "
            f"Error log: {error_blob}"
        )
        artifacts = inputs.get("artifacts")
        if not isinstance(artifacts, list):
            artifacts = []
        artifact_name = f"tests_failed_attempt_{state.attempt + 1}.json"
        artifact_path = store.write_artifact(run_id, artifact_name, error_blob)
        artifacts.append(
            {
                "name": artifact_name,
                "uri": str(artifact_path),
                "sha256": sha256_text_fn(error_blob),
            }
        )
        inputs["artifacts"] = artifacts
        current_contract["inputs"] = inputs
        store.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "FIX_LOOP_TRIGGERED",
                "run_id": run_id,
                "meta": {"attempt": state.attempt + 1, "error_log": state.tests_result},
            },
        )
        backoff = retry_backoff_fn(contract)
        if backoff > 0:
            time.sleep(backoff)
        state.attempt += 1

    review_result = task_execution_review_helpers.run_review_stage(
        run_id=run_id,
        task_id=task_id,
        attempt=state.attempt,
        store=store,
        contract=contract,
        worktree_path=worktree_path,
        baseline_ref=baseline_ref,
        head_ref=state.head_ref,
        diff_text=state.diff_text,
        test_report=state.test_report,
        assigned_agent=assigned_agent,
        reviewer=reviewer,
        append_gate_failed_fn=append_gate_failed_fn,
        schema_root_fn=schema_root_fn,
        snapshot_worktree_fn=snapshot_worktree_fn,
        validate_reviewer_isolation_fn=validate_reviewer_isolation_fn,
    )
    state.review_report = review_result["review_report"]
    state.review_gate_result = review_result["review_gate_result"]
    state.failure_reason = review_result["failure_reason"]
    if not review_result["ok"]:
        return finish(False)
    return finish(True)
