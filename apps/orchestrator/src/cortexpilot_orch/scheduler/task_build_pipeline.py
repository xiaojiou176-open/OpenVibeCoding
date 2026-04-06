from __future__ import annotations

from typing import Any


def _gate_result(passed: bool, violations: list[str] | None = None) -> dict[str, Any]:
    return {"passed": passed, "violations": violations or []}


def build_task_result(
    run_id: str,
    task_id: str,
    attempt: int,
    producer: dict[str, Any],
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
    changed_files: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    diff_passed = bool(diff_gate and diff_gate.get("ok"))
    diff_violations = diff_gate.get("violations", []) if isinstance(diff_gate, dict) else ["diff_gate_missing"]

    review_ok = bool(review_report and review_report.get("verdict") == "PASS")
    review_violations: list[str] = []
    if review_report and review_report.get("verdict") != "PASS":
        review_violations.append(f"verdict:{review_report.get('verdict')}")
    if review_gate_result and not review_gate_result.get("ok", True):
        review_violations.append("reviewer_isolation")

    tests_passed = bool(tests_result and tests_result.get("ok", False))
    tests_violations = []
    if tests_result and not tests_result.get("ok", True):
        reason = tests_result.get("reason", "tests failed")
        tests_violations.append(str(reason))
    if not tests_result:
        tests_violations.append("tests_missing")

    summary_text = summary if summary else (failure_reason or "completed")
    next_steps = (
        {"suggested_action": "none", "notes": "n/a"}
        if status == "SUCCESS"
        else {"suggested_action": "investigate", "notes": failure_reason or "see logs"}
    )

    baseline = baseline_ref or "UNKNOWN"
    head = head_ref or baseline_ref or "UNKNOWN"

    failure: dict[str, Any] | None = None
    if status != "SUCCESS" and failure_reason:
        failure = {"message": failure_reason}

    return {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": attempt,
        "producer": producer,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "summary": summary_text,
        "artifacts": [],
        "git": {
            "baseline_ref": baseline,
            "head_ref": head,
            "changed_files": changed_files,
            "patch": patch,
        },
        "gates": {
            "diff_gate": _gate_result(diff_passed, list(diff_violations) if diff_violations else []),
            "policy_gate": policy_gate,
            "review_gate": _gate_result(review_ok and not review_violations, review_violations),
            "tests_gate": _gate_result(tests_passed, tests_violations),
        },
        "next_steps": next_steps,
        "failure": failure,
    }


def build_work_report(
    run_id: str,
    task_id: str,
    status: str,
    diff_gate: dict[str, Any] | None,
    tests_result: dict[str, Any] | None,
    review_report: dict[str, Any] | None,
) -> dict[str, Any]:
    diff_summary = ""
    if diff_gate and isinstance(diff_gate, dict):
        changed = diff_gate.get("changed_files") or []
        if isinstance(changed, list) and changed:
            diff_summary = ", ".join(str(item) for item in changed)
    return {
        "task_id": task_id,
        "run_id": run_id,
        "attempt": 0,
        "role": "WORKER",
        "status": "success" if status == "SUCCESS" else "fail",
        "patch_ref": "patch.diff",
        "diff_summary": diff_summary,
        "evidence_refs": {
            "test_report": "reports/test_report.json" if tests_result else "",
            "review_report": "reports/review_report.json" if review_report else "",
            "task_result": "reports/task_result.json",
        },
        "failure_reason": "" if status == "SUCCESS" else "see manifest.failure_reason",
        "gates": {
            "diff_gate": {
                "passed": bool(diff_gate and diff_gate.get("ok")),
                "violations": diff_gate.get("violations", []) if diff_gate else [],
            }
        },
    }
