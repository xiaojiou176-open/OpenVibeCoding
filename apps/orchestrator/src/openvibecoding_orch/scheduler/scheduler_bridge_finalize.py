from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.scheduler import (
    artifact_refs,
    completion_governance,
    core_helpers,
    evidence_pipeline,
    gate_orchestration,
    report_builders,
    test_pipeline,
)
from openvibecoding_orch.scheduler.runtime_utils import schema_root, write_manifest
from openvibecoding_orch.queue.store import QueueStore
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.temporal.manager import notify_run_completed
from openvibecoding_orch.worktrees import manager as worktree_manager
from openvibecoding_orch.locks.locker import release_lock

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

    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _append_input_artifact(
        follow_up_contract: dict[str, Any],
        *,
        name: str,
        uri: str,
        sha256: str,
    ) -> None:
        inputs = follow_up_contract.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {"spec": "", "artifacts": []}
        artifacts = inputs.get("artifacts")
        if not isinstance(artifacts, list):
            artifacts = []
        artifacts.append({"name": name, "uri": uri, "sha256": sha256})
        inputs["artifacts"] = artifacts
        follow_up_contract["inputs"] = inputs

    def _build_follow_up_contract(
        *,
        task_id_override: str,
        spec: str,
        preserve_thread: bool,
    ) -> dict[str, Any]:
        follow_up_contract = json.loads(json.dumps(contract, ensure_ascii=False))
        follow_up_contract["task_id"] = task_id_override
        follow_up_contract["parent_task_id"] = task_id
        inputs = follow_up_contract.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {"spec": spec, "artifacts": []}
        inputs["spec"] = spec
        if not isinstance(inputs.get("artifacts"), list):
            inputs["artifacts"] = []
        follow_up_contract["inputs"] = inputs
        if not preserve_thread:
            assigned_agent = follow_up_contract.get("assigned_agent")
            if isinstance(assigned_agent, dict):
                assigned_agent.pop("codex_thread_id", None)
            owner_agent = follow_up_contract.get("owner_agent")
            if isinstance(owner_agent, dict):
                owner_agent.pop("codex_thread_id", None)
        return follow_up_contract

    def _queue_follow_up_contract(
        *,
        follow_up_contract: dict[str, Any],
        artifact_name: str,
        task_id_for_queue: str,
        reason: str,
    ) -> dict[str, Any]:
        artifact_path = store.write_artifact(
            run_id,
            artifact_name,
            json.dumps(follow_up_contract, ensure_ascii=False, indent=2),
        )
        queue_store = QueueStore(queue_path=run_dir.parent.parent / "queue.jsonl")
        owner_agent = contract.get("owner_agent") if isinstance(contract.get("owner_agent"), dict) else {}
        assigned_agent = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
        workflow_meta = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else {}
        queue_item = queue_store.enqueue(
            artifact_path.resolve(),
            task_id_for_queue,
            owner=str(owner_agent.get("agent_id") or assigned_agent.get("agent_id") or "").strip(),
            metadata={
                "workflow_id": str(workflow_meta.get("workflow_id") or "").strip(),
                "source_run_id": run_id,
                "priority": 0,
                "reason": reason,
                **_wake_policy_queue_metadata(reason=reason),
            },
        )
        return {
            "artifact_path": str(artifact_path),
            "queue_item": queue_item,
        }

    def _load_wake_policy() -> tuple[dict[str, Any], str]:
        default_ref = "policies/control_plane_runtime_policy.json#/wake_policy"
        default_policy = {
            "primary_mode": "event_driven",
            "fallback_mode": "polling",
            "active_wave_interval_seconds": 60,
            "idle_interval_min_seconds": 300,
            "idle_interval_max_seconds": 600,
        }
        artifact_path = run_dir / "artifacts" / "planning_wave_plan.json"
        if not artifact_path.exists():
            return default_policy, default_ref
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default_policy, default_ref
        if not isinstance(payload, dict):
            return default_policy, default_ref
        wake_policy_ref = str(payload.get("wake_policy_ref") or default_ref).strip() or default_ref
        policy_path_text, _, fragment = wake_policy_ref.partition("#")
        candidate = (Path(__file__).resolve().parents[5] / policy_path_text).resolve()
        if not candidate.exists():
            return default_policy, wake_policy_ref
        try:
            policy_payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default_policy, wake_policy_ref
        node: Any = policy_payload
        if fragment:
            for part in fragment.lstrip("/").split("/"):
                if not part:
                    continue
                if not isinstance(node, dict):
                    return default_policy, wake_policy_ref
                node = node.get(part)
        if not isinstance(node, dict):
            return default_policy, wake_policy_ref
        merged = dict(default_policy)
        for key in default_policy:
            if key in node:
                merged[key] = node[key]
        return merged, wake_policy_ref

    def _iso_or_now(value: str) -> datetime:
        normalized = str(value or "").strip()
        if normalized:
            try:
                return datetime.fromisoformat(normalized.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    def _wake_policy_queue_metadata(*, reason: str) -> dict[str, Any]:
        wake_policy, wake_policy_ref = _load_wake_policy()
        base_dt = _iso_or_now(finished_at)
        try:
            active_seconds = max(int(wake_policy.get("active_wave_interval_seconds") or 60), 1)
        except (TypeError, ValueError):
            active_seconds = 60
        try:
            idle_min_seconds = max(int(wake_policy.get("idle_interval_min_seconds") or 300), 1)
        except (TypeError, ValueError):
            idle_min_seconds = 300
        try:
            idle_max_seconds = max(int(wake_policy.get("idle_interval_max_seconds") or 600), idle_min_seconds)
        except (TypeError, ValueError):
            idle_max_seconds = max(idle_min_seconds, 600)
        if reason == "completion_governance_on_incomplete":
            scheduled_at = base_dt
            deadline_at = base_dt + timedelta(seconds=active_seconds)
            wake_stage = "active_wave"
        else:
            scheduled_at = base_dt + timedelta(seconds=idle_min_seconds)
            deadline_at = base_dt + timedelta(seconds=idle_max_seconds)
            wake_stage = "polling_fallback"
        return {
            "scheduled_at": scheduled_at.isoformat(),
            "deadline_at": deadline_at.isoformat(),
            "wake_policy_ref": wake_policy_ref,
            "wake_primary_mode": str(wake_policy.get("primary_mode") or "event_driven"),
            "wake_fallback_mode": str(wake_policy.get("fallback_mode") or "polling"),
            "wake_stage": wake_stage,
        }

    if isinstance(final_task_result, dict):
        final_task_result["status"] = "SUCCESS" if status == "SUCCESS" else "FAILED"
        final_task_result["failure"] = {"message": failure_reason} if failure_reason else None
        if not final_task_result.get("summary") and failure_reason:
            final_task_result["summary"] = failure_reason

    (
        completion_governance_report,
        updated_unblock_tasks,
        context_pack_artifact,
        harness_request_artifact,
    ) = completion_governance.evaluate_completion_governance(
        contract=contract,
        run_dir=run_dir,
        task_result=final_task_result if isinstance(final_task_result, dict) else task_result,
        test_report=test_report,
        review_report=review_report,
        status=status,
        failure_reason=failure_reason,
        generated_at=finished_at,
    )
    try:
        report_validator.validate_report(completion_governance_report, "completion_governance_report.v1.json")
    except Exception as exc:  # noqa: BLE001
        failure_reason = failure_reason or f"completion_governance_report schema invalid: {exc}"
        status = "FAILURE"
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            str(exc),
            schema="completion_governance_report.v1.json",
            path="reports/completion_governance_report.json",
        )
    else:
        if updated_unblock_tasks is not None:
            store.write_artifact(
                run_id,
                "planning_unblock_tasks.json",
                json.dumps(updated_unblock_tasks, ensure_ascii=False, indent=2),
            )
        if context_pack_artifact is not None:
            context_pack_path = store.write_artifact(
                run_id,
                "context_pack.json",
                json.dumps(context_pack_artifact, ensure_ascii=False, indent=2),
            )
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "CONTEXT_PACK_GENERATED",
                    "run_id": run_id,
                    "meta": {
                        "pack_id": context_pack_artifact.get("pack_id"),
                        "trigger_reason": context_pack_artifact.get("trigger_reason"),
                    },
                },
            )
        if harness_request_artifact is not None:
            store.write_artifact(
                run_id,
                "harness_request.json",
                json.dumps(harness_request_artifact, ensure_ascii=False, indent=2),
            )
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "HARNESS_REQUEST_CREATED",
                    "run_id": run_id,
                    "meta": {
                        "request_id": harness_request_artifact.get("request_id"),
                        "scope": harness_request_artifact.get("scope"),
                        "approval_required": harness_request_artifact.get("approval_required"),
                    },
                },
            )
        if isinstance(final_task_result, dict):
            continuation_decision = completion_governance_report.get("continuation_decision", {})
            if isinstance(continuation_decision, dict):
                selected_action = str(continuation_decision.get("selected_action") or "").strip()
                if selected_action == "reply_auditor_reprompt_and_continue_same_session":
                    follow_up_contract = _build_follow_up_contract(
                        task_id_override=f"continue-{task_id}",
                        spec=(
                            "Continue the same session after completion governance marked the reply incomplete. "
                            f"Follow-up reason: {str(continuation_decision.get('summary') or '').strip()}"
                        ),
                        preserve_thread=True,
                    )
                    if context_pack_artifact is not None:
                        context_pack_text = json.dumps(context_pack_artifact, ensure_ascii=False, indent=2)
                        _append_input_artifact(
                            follow_up_contract,
                            name="context_pack.json",
                            uri=str(context_pack_path),
                            sha256=_sha256_text(context_pack_text),
                        )
                    follow_up_queue = _queue_follow_up_contract(
                        follow_up_contract=follow_up_contract,
                        artifact_name="continuation_task_contract.json",
                        task_id_for_queue=str(follow_up_contract.get("task_id") or f"continue-{task_id}"),
                        reason="completion_governance_on_incomplete",
                    )
                    continuation_decision["summary"] = (
                        f"{str(continuation_decision.get('summary') or '').strip()} "
                        f"Queued follow-up contract at {follow_up_queue['artifact_path']}."
                    ).strip()
                    continuation_decision["action_source"] = "continuation_policy.on_incomplete"
                    store.append_event(
                        run_id,
                        {
                            "level": "INFO",
                            "event": "CONTINUATION_QUEUED",
                            "run_id": run_id,
                            "meta": {
                                "task_id": follow_up_contract.get("task_id"),
                                "queue_id": follow_up_queue["queue_item"].get("queue_id"),
                            },
                        },
                    )
                elif selected_action == "spawn_independent_temporary_unblock_task" and updated_unblock_tasks is not None:
                    selected_unblock_task = next(
                        (
                            item
                            for item in updated_unblock_tasks
                            if str(item.get("unblock_task_id") or "").strip()
                            == str(continuation_decision.get("unblock_task_id") or "").strip()
                        ),
                        {},
                    )
                    if isinstance(selected_unblock_task, dict) and selected_unblock_task:
                        unblock_spec = (
                            f"{str(selected_unblock_task.get('objective') or '').strip()} "
                            f"Reason: {str(selected_unblock_task.get('reason') or '').strip()} "
                            f"Scope: {str(selected_unblock_task.get('scope_hint') or '').strip()}"
                        ).strip()
                        unblock_contract = _build_follow_up_contract(
                            task_id_override=str(selected_unblock_task.get("unblock_task_id") or f"unblock-{task_id}"),
                            spec=unblock_spec,
                            preserve_thread=False,
                        )
                        unblock_queue = _queue_follow_up_contract(
                            follow_up_contract=unblock_contract,
                            artifact_name="unblock_task_contract.json",
                            task_id_for_queue=str(unblock_contract.get("task_id") or f"unblock-{task_id}"),
                            reason="completion_governance_on_blocked",
                        )
                        continuation_decision["summary"] = (
                            f"{str(continuation_decision.get('summary') or '').strip()} "
                            f"Queued unblock contract at {unblock_queue['artifact_path']}."
                        ).strip()
                        store.append_event(
                            run_id,
                            {
                                "level": "INFO",
                                "event": "UNBLOCK_TASK_QUEUED",
                                "run_id": run_id,
                                "meta": {
                                    "unblock_task_id": unblock_contract.get("task_id"),
                                    "queue_id": unblock_queue["queue_item"].get("queue_id"),
                                },
                            },
                        )
                final_task_result["next_steps"] = {
                    "suggested_action": str(continuation_decision.get("selected_action") or "none"),
                    "notes": str(continuation_decision.get("summary") or "n/a"),
                }
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
        store.write_report(run_id, "completion_governance_report", completion_governance_report)
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "COMPLETION_GOVERNANCE_EVALUATED",
                "run_id": run_id,
                "meta": {
                    "overall_verdict": completion_governance_report.get("overall_verdict"),
                    "selected_action": completion_governance_report.get("continuation_decision", {}).get("selected_action"),
                },
            },
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
