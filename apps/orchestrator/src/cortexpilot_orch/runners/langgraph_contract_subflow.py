from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.runners import common as runner_common
from cortexpilot_orch.store.run_store import RunStore


_LANGGRAPH_GRAPH_MODULE = "langgraph.graph"
_LANGGRAPH_RUNTIME_REASON_MISSING = "langgraph_runtime_missing"
_LANGGRAPH_RUNTIME_REASON_INCOMPATIBLE = "langgraph_runtime_incompatible"
_LANGGRAPH_RUNTIME_REASON_EXECUTION_ERROR = "langgraph_execution_error"
_LANGGRAPH_RUNTIME_REASON_INVALID_RESULT = "langgraph_invalid_result"
_SUBFLOW_ROUTE = "langgraph_subflow"

_FAILED_STATUSES = {"FAILED", "BLOCKED"}

LanggraphExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def _task_id(contract: dict[str, Any]) -> str:
    value = contract.get("task_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "task"


def _attempt(contract: dict[str, Any]) -> int | None:
    value = contract.get("attempt")
    return value if isinstance(value, int) else None


def _append_subflow_event(
    run_store: RunStore,
    contract: dict[str, Any],
    *,
    level: str,
    stage: str,
    details: dict[str, Any],
) -> None:
    append_event = getattr(run_store, "append_event", None)
    if not callable(append_event):
        return

    run_id = runner_common.resolve_run_id(contract)
    payload: dict[str, Any] = {
        "flow": "agents_contract_flow",
        "subflow_engine": "langgraph",
        "subflow": "langgraph_contract_subflow",
        "stage": stage,
        "route": _SUBFLOW_ROUTE,
        "api_compatibility": "preserved",
    }
    payload.update(details)

    event = {
        "level": level,
        "event": "WORKFLOW_STATUS",
        "event_type": "WORKFLOW_STATUS",
        "run_id": run_id,
        "task_id": _task_id(contract),
        "attempt": _attempt(contract),
        "context": payload,
        "payload": payload,
    }
    try:
        append_event(run_id, event)
    except Exception:
        return


def _merge_evidence_refs(
    payload_refs: Any,
    audit_meta: dict[str, Any],
) -> dict[str, Any]:
    evidence_refs: dict[str, Any] = {}
    if isinstance(payload_refs, dict):
        evidence_refs.update(payload_refs)
    evidence_refs["subflow_audit"] = audit_meta
    return evidence_refs


def _build_failure_result(
    contract: dict[str, Any],
    *,
    reason: str,
    error_type: str,
    audit_meta: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "task_id": _task_id(contract),
        "status": "FAILED",
        "summary": reason,
        "failure": {"message": reason, "error_type": error_type},
        "evidence_refs": _merge_evidence_refs({}, audit_meta),
    }
    return runner_common.coerce_task_result(
        payload,
        contract,
        payload["evidence_refs"],
        "FAILED",
        reason,
    )


def _resolve_langgraph_executor() -> tuple[LanggraphExecutor | None, str | None]:
    try:
        graph_module = import_module(_LANGGRAPH_GRAPH_MODULE)
    except Exception:
        return None, _LANGGRAPH_RUNTIME_REASON_MISSING

    state_graph_cls = getattr(graph_module, "StateGraph", None)
    start_node = getattr(graph_module, "START", None)
    end_node = getattr(graph_module, "END", None)
    if not callable(state_graph_cls) or start_node is None or end_node is None:
        return None, _LANGGRAPH_RUNTIME_REASON_INCOMPATIBLE

    def _executor(initial_state: dict[str, Any]) -> dict[str, Any]:
        workflow = state_graph_cls(dict)

        def _contract_node(state: dict[str, Any]) -> dict[str, Any]:
            task_id = state.get("task_id") if isinstance(state.get("task_id"), str) else "task"
            mock_mode = bool(state.get("mock_mode"))
            return {
                "task_id": task_id,
                "status": "SUCCESS",
                "summary": "langgraph contract subflow executed",
                "mock_mode": mock_mode,
            }

        workflow.add_node("contract_task", _contract_node)
        workflow.add_edge(start_node, "contract_task")
        workflow.add_edge("contract_task", end_node)
        compiled_graph = workflow.compile()
        result = compiled_graph.invoke(dict(initial_state))
        if not isinstance(result, dict):
            raise TypeError("langgraph subflow result must be dict")
        return result

    return _executor, None


def run_langgraph_contract_subflow(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: RunStore,
    mock_mode: bool = False,
) -> dict[str, Any]:
    del schema_path

    task_id = _task_id(contract)
    audit_base = {
        "engine": "langgraph",
        "subflow": "contract",
        "task_id": task_id,
        "mock_mode": bool(mock_mode),
    }

    _append_subflow_event(
        run_store,
        contract,
        level="INFO",
        stage="subflow_started",
        details={**audit_base, "mode": "attempt"},
    )

    executor, unresolved_reason = _resolve_langgraph_executor()
    if executor is None:
        degraded_audit = {
            **audit_base,
            "mode": "degraded",
            "degraded": True,
            "reason": unresolved_reason or _LANGGRAPH_RUNTIME_REASON_MISSING,
        }
        _append_subflow_event(
            run_store,
            contract,
            level="WARN",
            stage="subflow_degraded",
            details=degraded_audit,
        )
        reason = f"langgraph contract subflow unavailable: {degraded_audit['reason']}"
        return _build_failure_result(
            contract,
            reason=reason,
            error_type=degraded_audit["reason"],
            audit_meta=degraded_audit,
        )

    input_state = {
        "task_id": task_id,
        "instruction": runner_common.extract_instruction(contract, worktree_path),
        "mock_mode": bool(mock_mode),
    }

    try:
        raw_result = executor(input_state)
    except Exception as exc:
        failed_audit = {
            **audit_base,
            "mode": "failed",
            "degraded": True,
            "reason": _LANGGRAPH_RUNTIME_REASON_EXECUTION_ERROR,
            "exception_type": type(exc).__name__,
        }
        _append_subflow_event(
            run_store,
            contract,
            level="WARN",
            stage="subflow_failed",
            details=failed_audit,
        )
        reason = f"langgraph contract subflow execution failed: {type(exc).__name__}"
        return _build_failure_result(
            contract,
            reason=reason,
            error_type=_LANGGRAPH_RUNTIME_REASON_EXECUTION_ERROR,
            audit_meta=failed_audit,
        )

    if not isinstance(raw_result, dict):
        invalid_audit = {
            **audit_base,
            "mode": "failed",
            "degraded": True,
            "reason": _LANGGRAPH_RUNTIME_REASON_INVALID_RESULT,
            "result_type": type(raw_result).__name__,
        }
        _append_subflow_event(
            run_store,
            contract,
            level="WARN",
            stage="subflow_failed",
            details=invalid_audit,
        )
        reason = f"langgraph contract subflow returned invalid result: {type(raw_result).__name__}"
        return _build_failure_result(
            contract,
            reason=reason,
            error_type=_LANGGRAPH_RUNTIME_REASON_INVALID_RESULT,
            audit_meta=invalid_audit,
        )

    status = runner_common.normalize_status(raw_result.get("status"), "SUCCESS")
    completed_audit = {
        **audit_base,
        "mode": "executed",
        "degraded": False,
        "status": status,
    }

    payload = {
        "task_id": raw_result.get("task_id") or task_id,
        "status": status,
        "summary": raw_result.get("summary") or "langgraph contract subflow executed",
        "failure": raw_result.get("failure"),
        "evidence_refs": _merge_evidence_refs(raw_result.get("evidence_refs"), completed_audit),
    }
    if isinstance(raw_result.get("contracts"), list):
        payload["contracts"] = [item for item in raw_result["contracts"] if isinstance(item, dict)]
    if isinstance(raw_result.get("handoff_payload"), dict):
        payload["handoff_payload"] = dict(raw_result["handoff_payload"])

    if status in _FAILED_STATUSES and not isinstance(payload.get("failure"), dict):
        payload["failure"] = {
            "message": str(payload.get("summary") or "langgraph contract subflow failed")
        }

    _append_subflow_event(
        run_store,
        contract,
        level="WARN" if status in _FAILED_STATUSES else "INFO",
        stage="subflow_completed",
        details=completed_audit,
    )

    failure_reason: str | None = None
    if status in _FAILED_STATUSES:
        failure_reason = str(payload.get("summary") or "langgraph contract subflow failed")

    return runner_common.coerce_task_result(
        payload,
        contract,
        payload["evidence_refs"],
        "SUCCESS",
        failure_reason,
    )


__all__ = ["run_langgraph_contract_subflow"]
