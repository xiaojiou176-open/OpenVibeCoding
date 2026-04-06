from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.runners.common import resolve_run_id
from cortexpilot_orch.store.run_store import RunStore


_LANGGRAPH_MODULE = "cortexpilot_orch.runners.langgraph_contract_subflow"
_LANGGRAPH_ENTRYPOINT = "run_langgraph_contract_subflow"
_LANGGRAPH_FLAG_ENV = "CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW"
_LANGGRAPH_TRUE_SET = {"1", "true", "yes", "on"}
_FAILED_STATUSES = {"FAILED", "ERROR", "BLOCKED"}

LanggraphContractExecutor = Callable[
    [dict[str, Any], Path, Path, RunStore, bool],
    dict[str, Any],
]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _LANGGRAPH_TRUE_SET
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _contract_task_id(contract: dict[str, Any]) -> str:
    value = contract.get("task_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "task"


def _contract_attempt(contract: dict[str, Any]) -> int | None:
    value = contract.get("attempt")
    return value if isinstance(value, int) else None


def _append_workflow_audit_event(
    run_store: RunStore,
    contract: dict[str, Any],
    *,
    level: str,
    stage: str,
    route: str,
    details: dict[str, Any] | None = None,
) -> None:
    append_event = getattr(run_store, "append_event", None)
    if not callable(append_event):
        return

    run_id = resolve_run_id(contract)
    payload: dict[str, Any] = {
        "flow": "agents_contract_flow",
        "subflow_engine": "langgraph",
        "stage": stage,
        "route": route,
        "api_compatibility": "preserved",
    }
    if isinstance(details, dict) and details:
        payload.update(details)

    event = {
        "level": level,
        "event": "WORKFLOW_STATUS",
        "event_type": "WORKFLOW_STATUS",
        "run_id": run_id,
        "task_id": _contract_task_id(contract),
        "attempt": _contract_attempt(contract),
        "context": payload,
        "payload": payload,
    }

    try:
        append_event(run_id, event)
    except Exception:
        return


def _resolve_langgraph_executor() -> LanggraphContractExecutor | None:
    try:
        module = import_module(_LANGGRAPH_MODULE)
    except Exception:
        return None
    candidate = getattr(module, _LANGGRAPH_ENTRYPOINT, None)
    return candidate if callable(candidate) else None


def _langgraph_requested(contract: dict[str, Any]) -> tuple[bool, str]:
    subflow = contract.get("subflow")
    if isinstance(subflow, dict):
        engine_raw = subflow.get("engine")
        has_engine = isinstance(engine_raw, str) and bool(engine_raw.strip())
        has_enabled = "enabled" in subflow
        if has_engine or has_enabled:
            engine = engine_raw.strip().lower() if has_engine else "langgraph"
            if engine != "langgraph":
                return False, "contract.subflow.engine"
            if not has_enabled:
                return True, "contract.subflow.engine"
            return _as_bool(subflow.get("enabled")), "contract.subflow.enabled"

    langgraph = contract.get("langgraph")
    if isinstance(langgraph, dict) and "enabled" in langgraph:
        return _as_bool(langgraph.get("enabled")), "contract.langgraph.enabled"

    env_flag = os.getenv(_LANGGRAPH_FLAG_ENV, "")
    if env_flag.strip():
        return _as_bool(env_flag), f"env.{_LANGGRAPH_FLAG_ENV}"

    return False, "default"


def _langgraph_result_failed(result: dict[str, Any]) -> bool:
    status = result.get("status")
    if isinstance(status, str) and status.strip().upper() in _FAILED_STATUSES:
        return True
    failure_payload = result.get("failure")
    return bool(failure_payload)


def _langgraph_failure_details(result: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    failure_payload = result.get("failure")
    if not isinstance(failure_payload, dict):
        return details
    error_type = failure_payload.get("error_type")
    if isinstance(error_type, str) and error_type.strip():
        details["subflow_error_type"] = error_type.strip()
    message = failure_payload.get("message")
    if isinstance(message, str) and message.strip():
        details["subflow_failure_message"] = message.strip()
    return details


def run_agents_contract(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: RunStore,
    mock_mode: bool = False,
) -> dict[str, Any]:
    runner = AgentsRunner(run_store)
    use_langgraph, decision_source = _langgraph_requested(contract)
    selected_route = "langgraph_subflow" if use_langgraph else "legacy_runner"
    _append_workflow_audit_event(
        run_store,
        contract,
        level="INFO",
        stage="route_selected",
        route=selected_route,
        details={"decision_source": decision_source},
    )

    if not use_langgraph:
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    langgraph_executor = _resolve_langgraph_executor()
    if langgraph_executor is None:
        _append_workflow_audit_event(
            run_store,
            contract,
            level="WARN",
            stage="fallback_to_legacy",
            route="legacy_runner",
            details={
                "decision_source": decision_source,
                "fallback_reason": "langgraph_executor_unavailable",
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    _append_workflow_audit_event(
        run_store,
        contract,
        level="INFO",
        stage="subflow_started",
        route="langgraph_subflow",
        details={"decision_source": decision_source},
    )

    try:
        langgraph_result = langgraph_executor(
            contract,
            worktree_path,
            schema_path,
            run_store,
            mock_mode,
        )
    except Exception as exc:
        _append_workflow_audit_event(
            run_store,
            contract,
            level="WARN",
            stage="fallback_to_legacy",
            route="legacy_runner",
            details={
                "decision_source": decision_source,
                "fallback_reason": "langgraph_subflow_exception",
                "exception_type": type(exc).__name__,
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    if not isinstance(langgraph_result, dict):
        _append_workflow_audit_event(
            run_store,
            contract,
            level="WARN",
            stage="fallback_to_legacy",
            route="legacy_runner",
            details={
                "decision_source": decision_source,
                "fallback_reason": "langgraph_result_invalid",
                "result_type": type(langgraph_result).__name__,
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    if _langgraph_result_failed(langgraph_result):
        failure_details = _langgraph_failure_details(langgraph_result)
        _append_workflow_audit_event(
            run_store,
            contract,
            level="WARN",
            stage="fallback_to_legacy",
            route="legacy_runner",
            details={
                "decision_source": decision_source,
                "fallback_reason": "langgraph_result_failed",
                "subflow_status": str(langgraph_result.get("status", "")),
                **failure_details,
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=mock_mode)

    _append_workflow_audit_event(
        run_store,
        contract,
        level="INFO",
        stage="subflow_completed",
        route="langgraph_subflow",
        details={
            "decision_source": decision_source,
            "subflow_status": str(langgraph_result.get("status", "SUCCESS")),
        },
    )
    return langgraph_result
