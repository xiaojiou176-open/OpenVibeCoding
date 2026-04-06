from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.scheduler import (
    artifact_refs,
    core_helpers,
    evidence_pipeline,
    gate_orchestration,
    report_builders,
    test_pipeline,
)
from cortexpilot_orch.scheduler.runtime_utils import schema_root, write_manifest
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.temporal.manager import notify_run_completed
from cortexpilot_orch.worktrees import manager as worktree_manager
from cortexpilot_orch.locks.locker import release_lock

try:
    from tooling.search_pipeline import write_evidence_bundle
except ModuleNotFoundError:
    def write_evidence_bundle(
        run_id: str,
        query: str,
        summary: str,
        results: list[dict[str, Any]],
        *,
        requested_by: dict[str, Any] | None = None,
        limitations: list[str] | None = None,
        store: RunStore | None = None,
    ) -> None:
        if store is None:
            return
        payload = {
            "query": query,
            "summary": summary,
            "results": results,
            "requested_by": requested_by or {},
            "limitations": limitations or [],
        }
        store.write_report(run_id, "evidence_bundle", payload)


def finalize_run(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
    status: str,
    failure_reason: str,
    manifest: dict[str, Any],
    attempt: int,
    start_ts: str,
    tests_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    policy_gate_result: dict[str, Any] | None,
    integrated_gate: dict[str, Any] | None,
    network_gate: dict[str, Any] | None,
    mcp_gate: dict[str, Any] | None,
    sampling_gate: dict[str, Any] | None,
    tool_gate: dict[str, Any] | None,
    human_approval_required: bool,
    human_approved: bool | None,
    contract: dict[str, Any],
    runner_summary: str,
    diff_gate_result: dict[str, Any] | None,
    review_gate_result: dict[str, Any] | None,
    baseline_ref: str,
    head_ref: str,
    search_request: dict[str, Any] | None,
    tamper_request: dict[str, Any] | None,
    task_result: dict[str, Any] | None,
    now_ts_fn: Callable[[], str],
    ensure_text_file_fn: Callable[[Path], None],
    contract_validator_cls: type[Any],
    schema_root_fn: Callable[[], Path],
    build_test_report_stub_fn: Callable[..., dict[str, Any]],
    build_review_report_stub_fn: Callable[..., dict[str, Any]],
    build_policy_gate_fn: Callable[..., dict[str, Any]],
    build_task_result_fn: Callable[..., dict[str, Any]],
    build_work_report_fn: Callable[..., dict[str, Any]],
    build_evidence_report_fn: Callable[..., dict[str, Any]],
    append_gate_failed_fn: Callable[..., None],
    write_evidence_bundle_fn: Callable[..., None],
    manifest_task_role_fn: Callable[[dict[str, Any] | None], str],
    artifact_ref_from_path_fn: Callable[..., dict[str, Any]],
    collect_evidence_hashes_fn: Callable[[Path], dict[str, str]],
    artifact_refs_from_hashes_fn: Callable[[Path, dict[str, str]], list[dict[str, Any]]],
    write_manifest_fn: Callable[[RunStore, str, dict[str, Any]], None],
    notify_run_completed_fn: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> None:
    finished_at = now_ts_fn()
    manifest["finished_at"] = finished_at
    manifest["status"] = status
    if failure_reason:
        manifest["failure_reason"] = failure_reason
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "STATE_TRANSITION",
            "run_id": run_id,
            "meta": {"status": status},
        },
    )
    run_dir = store._runs_root / run_id
    report_validator = contract_validator_cls(schema_root=schema_root_fn())

    ensure_text_file_fn(run_dir / "patch.diff")
    ensure_text_file_fn(run_dir / "diff_name_only.txt")

    if test_report is None:
        test_status = "SKIPPED"
        if tests_result:
            test_status = "PASS" if tests_result.get("ok") else "FAIL"
        test_report = build_test_report_stub_fn(
            run_id,
            task_id,
            attempt,
            start_ts,
            finished_at,
            test_status,
            failure_reason if test_status != "PASS" else "",
        )
        try:
            report_validator.validate_report(test_report, "test_report.v1.json")
        except Exception as exc:  # noqa: BLE001
            failure_reason = failure_reason or f"test_report schema invalid: {exc}"
            status = "FAILURE"
            append_gate_failed_fn(
                store,
                run_id,
                "schema_validation",
                str(exc),
                schema="test_report.v1.json",
                path="reports/test_report.json",
            )
        else:
            store.write_report(run_id, "test_report", test_report)

    if review_report is None:
        review_verdict = "BLOCKED" if failure_reason else "PASS"
        review_report = build_review_report_stub_fn(
            run_id,
            task_id,
            attempt,
            finished_at,
            review_verdict,
            failure_reason,
        )
        try:
            report_validator.validate_report(review_report, "review_report.v1.json")
        except Exception as exc:  # noqa: BLE001
            failure_reason = failure_reason or f"review_report schema invalid: {exc}"
            status = "FAILURE"
            append_gate_failed_fn(
                store,
                run_id,
                "schema_validation",
                str(exc),
                schema="review_report.v1.json",
                path="reports/review_report.json",
            )
        else:
            store.write_report(run_id, "review_report", review_report)

    policy_gate = policy_gate_result or build_policy_gate_fn(
        integrated_gate,
        network_gate,
        mcp_gate,
        sampling_gate,
        tool_gate,
        human_approval_required,
        human_approved,
    )

    task_status = "SUCCESS" if status == "SUCCESS" else "FAILED"
    final_task_result = build_task_result_fn(
        run_id,
        task_id,
        attempt,
        contract.get("assigned_agent", {}) if isinstance(contract, dict) else None,
        task_status,
        start_ts,
        finished_at,
        runner_summary,
        failure_reason,
        diff_gate_result,
        policy_gate,
        review_report,
        review_gate_result,
        tests_result,
        baseline_ref,
        head_ref,
        run_dir,
    )
    try:
        report_validator.validate_report(final_task_result, "task_result.v1.json")
    except Exception as exc:  # noqa: BLE001
        failure_reason = failure_reason or f"task_result schema invalid: {exc}"
        status = "FAILURE"
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            str(exc),
            schema="task_result.v1.json",
            path="reports/task_result.json",
        )
    else:
        store.write_report(run_id, "task_result", final_task_result)
        store.write_task_result(run_id, task_id, final_task_result)

    try:
        work_report = build_work_report_fn(
            run_id,
            task_id,
            status,
            diff_gate_result,
            tests_result,
            review_report,
        )
        report_validator.validate_report(work_report, "work_report.v1.json")
        store.write_report(run_id, "work_report", work_report)
    except Exception as exc:  # noqa: BLE001
        failure_reason = failure_reason or f"work_report schema invalid: {exc}"
        status = "FAILURE"
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            str(exc),
            schema="work_report.v1.json",
            path="reports/work_report.json",
        )

    if not search_request:
        requested_by = contract.get("assigned_agent", {}) if isinstance(contract, dict) else {}
        write_evidence_bundle_fn(
            run_id,
            "no search executed",
            "no search executed",
            [],
            requested_by=requested_by,
            limitations=["no search executed"],
            store=store,
        )

    try:
        extra_required: list[str] = []
        if tamper_request:
            extra_required.append("artifacts/tampermonkey_results.json")
        evidence_report = build_evidence_report_fn(run_dir, extra_required if extra_required else None)
        report_validator.validate_report(evidence_report, "evidence_report.v1.json")
        store.write_report(run_id, "evidence_report", evidence_report)
    except Exception as exc:  # noqa: BLE001
        failure_reason = failure_reason or f"evidence_report schema invalid: {exc}"
        status = "FAILURE"
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            str(exc),
            schema="evidence_report.v1.json",
            path="reports/evidence_report.json",
        )

    if isinstance(manifest.get("repo"), dict):
        manifest["repo"]["baseline_ref"] = baseline_ref or manifest["repo"].get("baseline_ref") or "UNKNOWN"
        if head_ref:
            manifest["repo"]["final_ref"] = head_ref

    task_role = manifest_task_role_fn(contract.get("assigned_agent", {}) if isinstance(contract, dict) else None)
    task_status_manifest = "SUCCESS" if status == "SUCCESS" else "FAILED"
    contract_ref = artifact_ref_from_path_fn("contract", run_dir, "contract.json", "application/json")
    result_ref = artifact_ref_from_path_fn("task_result", run_dir, "reports/task_result.json", "application/json")
    review_ref = artifact_ref_from_path_fn("review_report", run_dir, "reports/review_report.json", "application/json")
    test_ref = artifact_ref_from_path_fn("test_report", run_dir, "reports/test_report.json", "application/json")
    assigned_agent = contract.get("assigned_agent", {}) if isinstance(contract, dict) else {}
    thread_id_value = assigned_agent.get("codex_thread_id", "")
    if isinstance(task_result, dict):
        refs = task_result.get("evidence_refs")
        if isinstance(refs, dict):
            thread_id_value = refs.get("thread_id") or refs.get("codex_thread_id") or thread_id_value

    manifest["tasks"] = [
        {
            "task_id": task_id,
            "role": task_role,
            "assigned_agent_id": assigned_agent.get("agent_id", ""),
            "thread_id": thread_id_value or "",
            "status": task_status_manifest,
            "contract": contract_ref,
            "result": result_ref,
            "review_report": review_ref,
            "test_report": test_ref,
        }
    ]

    manifest["evidence_hashes"] = collect_evidence_hashes_fn(run_dir)
    manifest["artifacts"] = artifact_refs_from_hashes_fn(run_dir, manifest["evidence_hashes"])
    integrity = manifest.get("integrity") if isinstance(manifest.get("integrity"), dict) else {}
    if (run_dir / "events.hashchain.jsonl").exists():
        integrity["events_hashchain_path"] = "events.hashchain.jsonl"
        manifest["integrity"] = integrity
    manifest["status"] = status
    if failure_reason:
        manifest["failure_reason"] = failure_reason
    if isinstance(manifest.get("workflow"), dict):
        manifest["workflow"]["status"] = status
        workflow_snapshot = dict(manifest["workflow"])
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "WORKFLOW_STATUS",
                "run_id": run_id,
                "meta": workflow_snapshot,
            },
        )
    try:
        report_validator.validate_report(manifest, "run_manifest.v1.json")
    except Exception as exc:  # noqa: BLE001
        failure_reason = failure_reason or f"manifest schema invalid: {exc}"
        status = "FAILURE"
        manifest["status"] = status
        manifest["failure_reason"] = failure_reason
        if isinstance(manifest.get("workflow"), dict):
            manifest["workflow"]["status"] = status
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            str(exc),
            schema="run_manifest.v1.json",
            path="manifest.json",
        )
    write_manifest_fn(store, run_id, manifest)

    temporal_done = notify_run_completed_fn(
        run_id,
        {
            "run_id": run_id,
            "task_id": task_id,
            "status": status,
        },
    )
    store.append_event(
        run_id,
        {
            "level": "INFO" if temporal_done.get("ok") else "ERROR",
            "event": "TEMPORAL_NOTIFY_DONE",
            "run_id": run_id,
            "meta": temporal_done,
        },
    )


def finalize_execute_task_run(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
    locked: bool,
    allowed_paths: list[str],
    worktree_path: Path | None,
    status: str,
    failure_reason: str,
    manifest: dict[str, Any],
    attempt: int,
    start_ts: str,
    tests_result: dict[str, Any] | None,
    test_report: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
    policy_gate_result: dict[str, Any] | None,
    integrated_gate: dict[str, Any] | None,
    network_gate: dict[str, Any] | None,
    mcp_gate: dict[str, Any] | None,
    sampling_gate: dict[str, Any] | None,
    tool_gate: dict[str, Any] | None,
    human_approval_required: bool,
    human_approved: bool | None,
    contract: dict[str, Any],
    runner_summary: str,
    diff_gate_result: dict[str, Any] | None,
    review_gate_result: dict[str, Any] | None,
    baseline_ref: str,
    head_ref: str,
    search_request: dict[str, Any] | None,
    tamper_request: dict[str, Any] | None,
    task_result: dict[str, Any] | None,
) -> None:
    if locked:
        release_lock(allowed_paths)
    if worktree_path is not None:
        worktree_manager.remove_worktree(run_id, task_id)
    store.clear_active_contract(run_id)
    finalize_run(
        store=store,
        run_id=run_id,
        task_id=task_id,
        status=status,
        failure_reason=failure_reason,
        manifest=manifest,
        attempt=attempt,
        start_ts=start_ts,
        tests_result=tests_result,
        test_report=test_report,
        review_report=review_report,
        policy_gate_result=policy_gate_result,
        integrated_gate=integrated_gate,
        network_gate=network_gate,
        mcp_gate=mcp_gate,
        sampling_gate=sampling_gate,
        tool_gate=tool_gate,
        human_approval_required=human_approval_required,
        human_approved=human_approved,
        contract=contract,
        runner_summary=runner_summary,
        diff_gate_result=diff_gate_result,
        review_gate_result=review_gate_result,
        baseline_ref=baseline_ref,
        head_ref=head_ref,
        search_request=search_request,
        tamper_request=tamper_request,
        task_result=task_result,
        now_ts_fn=core_helpers.now_ts,
        ensure_text_file_fn=core_helpers.ensure_text_file,
        contract_validator_cls=ContractValidator,
        schema_root_fn=schema_root,
        build_test_report_stub_fn=test_pipeline.build_test_report_stub,
        build_review_report_stub_fn=test_pipeline.build_review_report_stub,
        build_policy_gate_fn=gate_orchestration.build_policy_gate,
        build_task_result_fn=report_builders.build_task_result,
        build_work_report_fn=report_builders.build_work_report,
        build_evidence_report_fn=report_builders.build_evidence_report,
        append_gate_failed_fn=gate_orchestration.append_gate_failed,
        write_evidence_bundle_fn=write_evidence_bundle,
        manifest_task_role_fn=core_helpers.manifest_task_role,
        artifact_ref_from_path_fn=artifact_refs.artifact_ref_from_path,
        collect_evidence_hashes_fn=evidence_pipeline.collect_evidence_hashes,
        artifact_refs_from_hashes_fn=artifact_refs.artifact_refs_from_hashes,
        write_manifest_fn=write_manifest,
        notify_run_completed_fn=notify_run_completed,
    )
