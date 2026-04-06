from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.runners.common import failure_result, normalize_status, resolve_run_id
from cortexpilot_orch.store.run_store import RunStore


_LANGGRAPH_PACKAGE = "langgraph"
_STREAM_CONTRACT = "sse_compatible_v1"
_FAILED_STATUSES = {"FAILED", "ERROR", "BLOCKED"}


def _task_id(contract: dict[str, Any]) -> str:
    value = contract.get("task_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "task"


def _append_event(run_store: RunStore, run_id: str, payload: dict[str, Any]) -> None:
    append_event = getattr(run_store, "append_event", None)
    if not callable(append_event):
        return
    try:
        append_event(run_id, payload)
    except Exception:
        return


def _append_stream_audit_event(
    run_store: RunStore,
    run_id: str,
    task_id: str,
    *,
    level: str,
    event: str,
    meta: dict[str, Any],
) -> None:
    payload: dict[str, Any] = {
        "level": level,
        "event": event,
        "run_id": run_id,
        "task_id": task_id,
        "meta": dict(meta),
    }
    _append_event(run_store, run_id, payload)


def _append_workflow_status(
    run_store: RunStore,
    run_id: str,
    task_id: str,
    *,
    level: str,
    stage: str,
    route: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "flow": "langgraph_stream_subflow",
        "subflow_engine": "langgraph",
        "stream_contract": _STREAM_CONTRACT,
        "stage": stage,
        "route": route,
        "api_compatibility": "preserved",
    }
    if isinstance(details, dict) and details:
        payload.update(details)

    _append_event(
        run_store,
        run_id,
        {
            "level": level,
            "event": "WORKFLOW_STATUS",
            "event_type": "WORKFLOW_STATUS",
            "run_id": run_id,
            "task_id": task_id,
            "context": payload,
            "payload": payload,
        },
    )


def _stream_result_failed(result: dict[str, Any]) -> bool:
    status = result.get("status")
    if isinstance(status, str) and status.strip().upper() in _FAILED_STATUSES:
        return True
    return bool(result.get("failure"))


def _langgraph_available() -> bool:
    try:
        return importlib.util.find_spec(_LANGGRAPH_PACKAGE) is not None
    except Exception:
        return False


def _normalize_stream_result(
    result: dict[str, Any],
    contract: dict[str, Any],
    *,
    mode: str,
    degraded: bool,
) -> dict[str, Any]:
    normalized = dict(result)
    normalized["task_id"] = normalized.get("task_id") or _task_id(contract)
    normalized["status"] = normalize_status(normalized.get("status"), "SUCCESS")
    if not isinstance(normalized.get("summary"), str):
        normalized["summary"] = str(normalized.get("summary") or "")

    evidence_refs = normalized.get("evidence_refs")
    if not isinstance(evidence_refs, dict):
        normalized["evidence_refs"] = {}
    failure_payload = normalized.get("failure")
    if failure_payload is not None and not isinstance(failure_payload, dict):
        normalized["failure"] = {"message": str(failure_payload)}
    else:
        normalized["failure"] = failure_payload

    stream_subflow_meta = normalized.get("stream_subflow")
    if not isinstance(stream_subflow_meta, dict):
        stream_subflow_meta = {}
    stream_subflow_meta.update(
        {
            "engine": "langgraph",
            "mode": mode,
            "degraded": degraded,
            "source": "langgraph_stream_subflow",
        }
    )
    normalized["stream_subflow"] = stream_subflow_meta
    normalized["stream_contract"] = _STREAM_CONTRACT
    return normalized


def run_langgraph_stream_subflow(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: RunStore,
    mock_mode: bool = False,
) -> dict[str, Any]:
    run_id = resolve_run_id(contract)
    task_id = _task_id(contract)

    _append_stream_audit_event(
        run_store,
        run_id,
        task_id,
        level="INFO",
        event="RUNNER_SELECTED",
        meta={
            "runner": "langgraph_stream_subflow",
            "source": "langgraph_stream_subflow",
            "stream_contract": _STREAM_CONTRACT,
            "fallback_runner": "agents_runner.run_contract",
        },
    )
    _append_workflow_status(
        run_store,
        run_id,
        task_id,
        level="INFO",
        stage="route_selected",
        route="langgraph_stream_subflow",
    )

    langgraph_available = _langgraph_available()
    mode = "delegated_legacy_runner"
    degraded = False
    if not langgraph_available:
        mode = "fallback_legacy_runner"
        degraded = True
        _append_stream_audit_event(
            run_store,
            run_id,
            task_id,
            level="WARN",
            event="TEMPORAL_WORKFLOW_FALLBACK",
            meta={
                "source": "langgraph_stream_subflow",
                "reason": "langgraph_dependency_missing",
                "stream_contract": _STREAM_CONTRACT,
                "fallback_runner": "agents_runner.run_contract",
            },
        )
        _append_workflow_status(
            run_store,
            run_id,
            task_id,
            level="WARN",
            stage="fallback_to_legacy",
            route="legacy_runner",
            details={"fallback_reason": "langgraph_dependency_missing"},
        )
    else:
        _append_workflow_status(
            run_store,
            run_id,
            task_id,
            level="INFO",
            stage="subflow_started",
            route="langgraph_stream_subflow",
            details={"compatibility_mode": mode},
        )

    runner = AgentsRunner(run_store)
    try:
        base_result = runner.run_contract(
            contract,
            worktree_path,
            schema_path,
            mock_mode=mock_mode,
        )
    except Exception as exc:
        _append_stream_audit_event(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            event="TEMPORAL_WORKFLOW_FAILED",
            meta={
                "source": "langgraph_stream_subflow",
                "reason": "legacy_runner_exception",
                "error_type": type(exc).__name__,
                "stream_contract": _STREAM_CONTRACT,
            },
        )
        _append_workflow_status(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            stage="subflow_failed",
            route="legacy_runner",
            details={"failure_reason": "legacy_runner_exception"},
        )
        return _normalize_stream_result(
            failure_result(
                contract,
                "langgraph stream subflow delegate failed",
                {"error_type": type(exc).__name__},
            ),
            contract,
            mode="delegate_failed",
            degraded=True,
        )

    if not isinstance(base_result, dict):
        _append_stream_audit_event(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            event="TEMPORAL_WORKFLOW_FAILED",
            meta={
                "source": "langgraph_stream_subflow",
                "reason": "legacy_runner_result_invalid",
                "result_type": type(base_result).__name__,
                "stream_contract": _STREAM_CONTRACT,
            },
        )
        _append_workflow_status(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            stage="subflow_failed",
            route="legacy_runner",
            details={"failure_reason": "legacy_runner_result_invalid"},
        )
        return _normalize_stream_result(
            failure_result(
                contract,
                "langgraph stream subflow delegate returned invalid result",
                {"result_type": type(base_result).__name__},
            ),
            contract,
            mode="delegate_invalid_result",
            degraded=True,
        )

    normalized = _normalize_stream_result(
        base_result,
        contract,
        mode=mode,
        degraded=degraded,
    )

    if _stream_result_failed(normalized):
        failure_meta = normalized.get("failure")
        error_type = ""
        failure_message = ""
        if isinstance(failure_meta, dict):
            raw_error_type = failure_meta.get("error_type")
            raw_message = failure_meta.get("message")
            if isinstance(raw_error_type, str):
                error_type = raw_error_type
            if isinstance(raw_message, str):
                failure_message = raw_message
        _append_stream_audit_event(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            event="TEMPORAL_WORKFLOW_FAILED",
            meta={
                "source": "langgraph_stream_subflow",
                "reason": "legacy_runner_failed_status",
                "subflow_status": str(normalized.get("status", "")),
                "error_type": error_type,
                "failure_message": failure_message,
                "stream_contract": _STREAM_CONTRACT,
            },
        )
        _append_workflow_status(
            run_store,
            run_id,
            task_id,
            level="ERROR",
            stage="subflow_failed",
            route="legacy_runner" if degraded else "langgraph_stream_subflow",
            details={
                "failure_reason": "legacy_runner_failed_status",
                "subflow_status": str(normalized.get("status", "")),
            },
        )
        return normalized

    _append_workflow_status(
        run_store,
        run_id,
        task_id,
        level="INFO",
        stage="subflow_completed",
        route="legacy_runner" if degraded else "langgraph_stream_subflow",
        details={
            "compatibility_mode": mode,
            "degraded": degraded,
            "subflow_status": normalized.get("status", ""),
        },
    )
    return normalized
