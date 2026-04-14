from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.store.run_store import RunStore


def run_review_stage(
    *,
    run_id: str,
    task_id: str,
    attempt: int,
    store: RunStore,
    contract: dict[str, Any],
    worktree_path: Path,
    baseline_ref: str,
    head_ref: str,
    diff_text: str,
    test_report: dict[str, Any] | None,
    assigned_agent: dict[str, Any],
    reviewer: Any,
    append_gate_failed_fn: Callable[..., None],
    schema_root_fn: Callable[[], Path],
    snapshot_worktree_fn: Callable[[Path], dict[str, Any]],
    validate_reviewer_isolation_fn: Callable[[Path, dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    report_validator = ContractValidator(schema_root=schema_root_fn())
    review_snapshot = snapshot_worktree_fn(worktree_path)
    reviewer_mode = os.getenv("OPENVIBECODING_REVIEWER_MODE", "local").strip().lower()
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "REVIEWER_MODE_SELECTED",
            "run_id": run_id,
            "meta": {"mode": reviewer_mode},
        },
    )
    inputs_meta = {
        "baseline_ref": baseline_ref,
        "head_ref": head_ref,
    }
    reviewer_meta = {
        "agent_id": assigned_agent.get("agent_id", "reviewer"),
        "codex_thread_id": assigned_agent.get("codex_thread_id", ""),
    }
    review_input = test_report or {"status": "ERROR", "artifacts": []}
    review_report = None
    if reviewer_mode == "codex":
        try:
            from openvibecoding_orch.reviewer.reviewer import CodexReviewer

            reviewer_meta["sandbox_mode"] = "read-only"
            review_report = CodexReviewer().review_task(
                contract,
                diff_text,
                review_input,
                worktree_path,
                reviewer_meta=reviewer_meta,
                inputs_meta=inputs_meta,
            )
        except Exception as exc:  # noqa: BLE001
            store.append_event(
                run_id,
                {
                    "level": "WARN",
                    "event": "REVIEWER_FALLBACK",
                    "run_id": run_id,
                    "meta": {"error": str(exc)},
                },
            )
            review_report = reviewer.review_task(
                contract,
                diff_text,
                review_input,
                reviewer_meta=reviewer_meta,
                inputs_meta=inputs_meta,
            )
    else:
        review_report = reviewer.review_task(
            contract,
            diff_text,
            review_input,
            reviewer_meta=reviewer_meta,
            inputs_meta=inputs_meta,
        )
    audit_only = contract.get("audit_only") is True
    if audit_only and not diff_text.strip():
        review_report["verdict"] = "PASS"
        review_report["summary"] = "diff is empty; allowed-empty-diff rule applied"
        review_report["notes"] = "No code change was produced, so the allowed-empty-diff rule was applied."
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "REVIEWER_EMPTY_DIFF_OVERRIDE",
                "run_id": run_id,
                "meta": {"applied": True, "audit_only": True},
            },
        )
    review_report["run_id"] = run_id
    review_report["attempt"] = attempt
    try:
        report_validator.validate_report(review_report, "review_report.v1.json")
    except Exception as exc:  # noqa: BLE001
        failure_reason = f"review_report schema invalid: {exc}"
        append_gate_failed_fn(
            store,
            run_id,
            "schema_validation",
            failure_reason,
            schema="review_report.v1.json",
            path="reports/review_report.json",
        )
        return {
            "ok": False,
            "failure_reason": failure_reason,
            "review_report": review_report,
            "review_gate_result": None,
        }
    review_gate = validate_reviewer_isolation_fn(worktree_path, review_snapshot)
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "REVIEWER_GATE_RESULT",
            "run_id": run_id,
            "meta": review_gate,
        },
    )
    if not review_gate.get("ok", False):
        append_gate_failed_fn(
            store,
            run_id,
            "reviewer_gate",
            "reviewer isolation violation",
            extra=review_gate if isinstance(review_gate, dict) else None,
        )
        return {
            "ok": False,
            "failure_reason": "reviewer isolation violation",
            "review_report": review_report,
            "review_gate_result": review_gate,
        }
    store.write_report(run_id, "review_report", review_report)
    store.write_review_report(run_id, task_id, review_report)
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "REVIEW_RESULT",
            "run_id": run_id,
            "meta": review_report,
        },
    )
    if review_report.get("verdict") != "PASS":
        return {
            "ok": False,
            "failure_reason": "review failed",
            "review_report": review_report,
            "review_gate_result": review_gate,
        }
    return {
        "ok": True,
        "failure_reason": "",
        "review_report": review_report,
        "review_gate_result": review_gate,
    }
