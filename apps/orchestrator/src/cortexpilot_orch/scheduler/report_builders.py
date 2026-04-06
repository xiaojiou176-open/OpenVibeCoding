from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.scheduler import artifact_refs, core_helpers, evidence_pipeline, task_build_pipeline


def build_task_result(
    run_id: str,
    task_id: str,
    attempt: int,
    producer_agent: dict[str, Any] | None,
    status: str,
    started_at: str,
    finished_at: str,
    summary: str,
    failure_reason: str,
    diff_gate: dict[str, Any] | None,
    policy_gate: dict[str, Any],
    review_report: dict[str, Any] | None,
    review_gate_result: dict[str, Any] | None,
    tests_result: dict[str, Any] | None,
    baseline_ref: str,
    head_ref: str,
    run_dir: Path,
) -> dict[str, Any]:
    producer_role = core_helpers.task_result_role(producer_agent)
    producer_id = (
        producer_agent.get("agent_id")
        if isinstance(producer_agent, dict) and producer_agent.get("agent_id")
        else "orchestrator"
    )
    producer: dict[str, Any] = {"role": producer_role, "agent_id": producer_id}
    if isinstance(producer_agent, dict):
        thread_id = producer_agent.get("codex_thread_id")
        if isinstance(thread_id, str) and thread_id.strip():
            producer["codex_thread_id"] = thread_id

    changed_files = artifact_refs.artifact_ref_from_path("diff_name_only", run_dir, "diff_name_only.txt")
    patch = artifact_refs.artifact_ref_from_path("patch", run_dir, "patch.diff")

    return task_build_pipeline.build_task_result(
        run_id=run_id,
        task_id=task_id,
        attempt=attempt,
        producer=producer,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        failure_reason=failure_reason,
        diff_gate=diff_gate,
        policy_gate=policy_gate,
        review_report=review_report,
        review_gate_result=review_gate_result,
        tests_result=tests_result,
        baseline_ref=baseline_ref,
        head_ref=head_ref,
        changed_files=changed_files,
        patch=patch,
    )


def build_work_report(
    run_id: str,
    task_id: str,
    status: str,
    diff_gate: dict[str, Any] | None,
    tests_result: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return task_build_pipeline.build_work_report(
        run_id=run_id,
        task_id=task_id,
        status=status,
        diff_gate=diff_gate,
        tests_result=tests_result,
        review_report=review_report,
    )


def build_evidence_report(run_dir: Path, extra_required: list[str] | None = None) -> dict[str, Any]:
    return evidence_pipeline.build_evidence_report(run_dir, extra_required)
