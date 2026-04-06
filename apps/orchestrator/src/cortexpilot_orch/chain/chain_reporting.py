from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.chain.chain_lifecycle import _build_lifecycle_summary
from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.store.run_store import RunStore


def _resolve_chain_failure_reason(
    *,
    final_status: str,
    step_reports: list[dict[str, Any]],
    lifecycle_violations: list[str],
    interrupted: bool,
    interruption_reason: str,
) -> str:
    if final_status not in {"FAILURE", "PARTIAL"}:
        return ""
    if interrupted and str(interruption_reason).strip():
        return str(interruption_reason).strip()
    for step in step_reports:
        if str(step.get("status", "")).strip().upper() != "FAILURE":
            continue
        reason = str(step.get("failure_reason", "")).strip()
        if reason:
            return reason
    if lifecycle_violations:
        return "; ".join(str(item).strip() for item in lifecycle_violations if str(item).strip())
    return "chain failed"


def _collect_chain_timeout_summary(
    store: RunStore,
    chain_run_id: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    events_path = store._run_dir(chain_run_id) / "events.jsonl"
    if not events_path.exists():
        return {
            "count": 0,
            "timed_out_steps": [],
            "timeout_sec": None,
            "timeout_sec_values": [],
            "timed_out_commands": [],
        }

    step_name_by_index = {index: str(step.get("name", f"step_{index}")) for index, step in enumerate(steps)}
    timed_out_steps: list[str] = []
    timed_out_commands: list[list[str]] = []
    timeout_sec_values: list[float] = []

    with events_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = line.strip()
            if not row:
                continue
            try:
                event = json.loads(row)
            except json.JSONDecodeError:
                continue
            if str(event.get("event", "")).strip() != "CHAIN_SUBPROCESS_TIMEOUT":
                continue
            meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
            cmd_raw = meta.get("cmd")
            cmd = [str(item) for item in cmd_raw if str(item).strip()] if isinstance(cmd_raw, list) else []
            timed_out_commands.append(cmd)

            timeout_raw = meta.get("timeout_sec")
            if isinstance(timeout_raw, (int, float)) and float(timeout_raw) > 0:
                timeout_sec_values.append(float(timeout_raw))

            step_name = ""
            for token in cmd:
                match = re.search(r"chain_step_(\d+)_", Path(token).name)
                if not match:
                    continue
                index = int(match.group(1))
                step_name = step_name_by_index.get(index, "")
                if step_name:
                    break
            if step_name and step_name not in timed_out_steps:
                timed_out_steps.append(step_name)

    unique_timeout_values: list[float] = []
    for value in timeout_sec_values:
        if value not in unique_timeout_values:
            unique_timeout_values.append(value)

    timeout_sec: float | None = unique_timeout_values[0] if len(unique_timeout_values) == 1 else None
    return {
        "count": len(timed_out_commands),
        "timed_out_steps": timed_out_steps,
        "timeout_sec": timeout_sec,
        "timeout_sec_values": unique_timeout_values,
        "timed_out_commands": timed_out_commands,
    }


def emit_chain_final_report(
    *,
    store: RunStore,
    validator: ContractValidator,
    manifest: dict[str, Any],
    run_id: str,
    chain_id: str,
    steps: list[dict[str, Any]],
    step_reports: list[dict[str, Any]],
    strategy: dict[str, Any],
    chain_owner_agent: dict[str, Any],
    start_ts: str,
    final_status: str,
    interrupted: bool = False,
    interruption_reason: str = "",
    now_ts_factory: Callable[[], str],
) -> dict[str, Any]:
    lifecycle_summary, lifecycle_violations = _build_lifecycle_summary(
        store,
        chain_owner_agent,
        step_reports,
        strategy,
    )
    if lifecycle_summary.get("enforce") and lifecycle_violations and final_status != "FAILURE":
        final_status = "FAILURE"

    failure_reason = _resolve_chain_failure_reason(
        final_status=final_status,
        step_reports=step_reports,
        lifecycle_violations=lifecycle_violations,
        interrupted=interrupted,
        interruption_reason=interruption_reason,
    )

    store.append_event(
        run_id,
        {
            "level": "INFO" if not lifecycle_violations else "WARN",
            "event": "CHAIN_LIFECYCLE_EVALUATED",
            "run_id": run_id,
            "meta": {
                "is_complete": lifecycle_summary.get("is_complete", False),
                "enforce": lifecycle_summary.get("enforce", False),
                "violations": lifecycle_violations,
                "reviewers": lifecycle_summary.get("reviewers", {}),
                "tests": lifecycle_summary.get("tests", {}),
                "failure_reason": failure_reason,
            },
        },
    )

    timeout_summary = _collect_chain_timeout_summary(store, run_id, steps)
    report = {
        "chain_id": chain_id,
        "run_id": run_id,
        "status": final_status,
        "steps": step_reports,
        "lifecycle": lifecycle_summary,
        "timeouts": timeout_summary,
        "timestamps": {"started_at": start_ts, "finished_at": now_ts_factory()},
    }

    try:
        validator.validate_report(report, "chain_report.v1.json")
    except Exception as exc:  # noqa: BLE001
        store.append_event(
            run_id,
            {
                "level": "WARN",
                "event": "CHAIN_REPORT_SCHEMA_INVALID",
                "run_id": run_id,
                "meta": {"error": str(exc), "status": final_status},
            },
        )

    store.write_report(run_id, "chain_report", report)

    manifest["end_ts"] = now_ts_factory()
    manifest["status"] = final_status
    if failure_reason:
        manifest["failure_reason"] = failure_reason
    else:
        manifest.pop("failure_reason", None)
    store.write_manifest(run_id, manifest)

    completed_meta = {
        "status": final_status,
        "steps": len(step_reports),
        "lifecycle_complete": lifecycle_summary.get("is_complete", False),
    }
    if failure_reason:
        completed_meta["failure_reason"] = failure_reason
    if interrupted:
        completed_meta["interrupted"] = True
        completed_meta["interruption_reason"] = interruption_reason
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "CHAIN_COMPLETED",
            "run_id": run_id,
            "meta": completed_meta,
        },
    )
    return report
