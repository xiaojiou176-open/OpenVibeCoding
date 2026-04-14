from __future__ import annotations

from pathlib import Path

from openvibecoding_orch.scheduler import scheduler as scheduler_module
from openvibecoding_orch.scheduler import task_build_pipeline


def _base_args(run_dir: Path, status: str) -> dict:
    diff_gate = {"ok": status == "SUCCESS", "violations": [] if status == "SUCCESS" else ["diff failed"]}
    policy_gate = {"passed": status == "SUCCESS", "violations": [] if status == "SUCCESS" else ["policy"]}
    review_report = {"verdict": "PASS" if status == "SUCCESS" else "FAIL"}
    review_gate_result = {"ok": status == "SUCCESS"}
    tests_result = {"ok": status == "SUCCESS", "reason": "tests failed" if status != "SUCCESS" else ""}

    return {
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt": 1,
        "producer_agent": {"role": "WORKER", "agent_id": "worker-1"},
        "status": status,
        "started_at": "2026-02-08T01:00:00Z",
        "finished_at": "2026-02-08T01:00:05Z",
        "summary": "done" if status == "SUCCESS" else "",
        "failure_reason": "" if status == "SUCCESS" else "failed",
        "diff_gate": diff_gate,
        "policy_gate": policy_gate,
        "review_report": review_report,
        "review_gate_result": review_gate_result,
        "tests_result": tests_result,
        "baseline_ref": "HEAD~1",
        "head_ref": "HEAD",
        "run_dir": run_dir,
    }


def _expected_from_pipeline(args: dict) -> dict:
    producer = {"role": scheduler_module._task_result_role(args["producer_agent"]), "agent_id": "worker-1"}
    changed_files = scheduler_module._artifact_ref_from_path("diff_name_only", args["run_dir"], "diff_name_only.txt")
    patch = scheduler_module._artifact_ref_from_path("patch", args["run_dir"], "patch.diff")
    return task_build_pipeline.build_task_result(
        run_id=args["run_id"],
        task_id=args["task_id"],
        attempt=args["attempt"],
        producer=producer,
        status=args["status"],
        started_at=args["started_at"],
        finished_at=args["finished_at"],
        summary=args["summary"],
        failure_reason=args["failure_reason"],
        diff_gate=args["diff_gate"],
        policy_gate=args["policy_gate"],
        review_report=args["review_report"],
        review_gate_result=args["review_gate_result"],
        tests_result=args["tests_result"],
        baseline_ref=args["baseline_ref"],
        head_ref=args["head_ref"],
        changed_files=changed_files,
        patch=patch,
    )


def test_scheduler_build_task_result_parity_success(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "diff_name_only.txt").write_text("README.md\n", encoding="utf-8")
    (run_dir / "patch.diff").write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")

    args = _base_args(run_dir, status="SUCCESS")
    actual = scheduler_module._build_task_result(**args)
    expected = _expected_from_pipeline(args)

    assert actual == expected


def test_scheduler_build_task_result_parity_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "diff_name_only.txt").write_text("README.md\n", encoding="utf-8")
    (run_dir / "patch.diff").write_text("diff --git a/README.md b/README.md\n", encoding="utf-8")

    args = _base_args(run_dir, status="FAILURE")
    actual = scheduler_module._build_task_result(**args)
    expected = _expected_from_pipeline(args)

    assert actual == expected
