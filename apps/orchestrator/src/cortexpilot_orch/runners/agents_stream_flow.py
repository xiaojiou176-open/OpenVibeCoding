from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.store.run_store import RunStore


_LANGGRAPH_PROVIDER = "langgraph"
_SUBGRAPH_CONFIG_KEYS = ("stream_subgraph", "langgraph_subgraph")
_RUNNER_SPEC_KEYS = ("runner", "entrypoint", "handler")
_FAILED_STATUSES = {"FAILED", "ERROR", "BLOCKED"}


def _resolve_subgraph_config(contract: dict[str, Any]) -> dict[str, Any] | None:
    for key in _SUBGRAPH_CONFIG_KEYS:
        value = contract.get(key)
        if isinstance(value, dict):
            return value
    stream_config = contract.get("stream")
    if isinstance(stream_config, dict):
        value = stream_config.get("subgraph") or stream_config.get("langgraph_subgraph")
        if isinstance(value, dict):
            return value
    extensions_config = contract.get("extensions")
    if isinstance(extensions_config, dict):
        value = extensions_config.get("langgraph_subgraph")
        if isinstance(value, dict):
            return value
    return None


def _subgraph_enabled(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    if not bool(config.get("enabled")):
        return False
    provider = config.get("provider")
    if provider is None:
        return True
    return isinstance(provider, str) and provider.strip().lower() == _LANGGRAPH_PROVIDER


def _extract_run_and_task_id(contract: dict[str, Any]) -> tuple[str | None, str]:
    run_id: str | None = None
    raw_run_id = contract.get("run_id")
    if isinstance(raw_run_id, str) and raw_run_id.strip():
        run_id = raw_run_id.strip()
    else:
        for key in ("meta", "context"):
            bucket = contract.get(key)
            if isinstance(bucket, dict):
                nested = bucket.get("run_id")
                if isinstance(nested, str) and nested.strip():
                    run_id = nested.strip()
                    break
    task_id = contract.get("task_id")
    if not isinstance(task_id, str):
        task_id = ""
    return run_id, task_id


def _append_audit_event(
    run_store: RunStore,
    run_id: str | None,
    task_id: str,
    *,
    event: str,
    level: str,
    meta: dict[str, Any],
) -> None:
    if not run_id or not hasattr(run_store, "append_event"):
        return
    payload: dict[str, Any] = {
        "level": level,
        "event": event,
        "run_id": run_id,
        "meta": dict(meta),
    }
    if task_id:
        payload["task_id"] = task_id
    try:
        run_store.append_event(run_id, payload)
    except Exception:  # noqa: BLE001
        return


def _is_runner_signature_compat_error(exc: TypeError) -> bool:
    message = str(exc)
    signature_markers = (
        "unexpected keyword argument",
        "positional arguments but",
        "required positional argument",
        "got multiple values for argument",
    )
    return any(marker in message for marker in signature_markers)


def _subgraph_result_failed(result: dict[str, Any]) -> bool:
    status = result.get("status")
    if isinstance(status, str) and status.strip().upper() in _FAILED_STATUSES:
        return True
    return bool(result.get("failure"))


def _subgraph_failure_details(result: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    failure_payload = result.get("failure")
    if not isinstance(failure_payload, dict):
        return details
    error_type = failure_payload.get("error_type")
    if isinstance(error_type, str) and error_type.strip():
        details["subgraph_error_type"] = error_type.strip()
    message = failure_payload.get("message")
    if isinstance(message, str) and message.strip():
        details["subgraph_failure_message"] = message.strip()
    return details


def _resolve_subgraph_runner(config: dict[str, Any]) -> Callable[..., dict[str, Any]]:
    runner_spec: Any | None = None
    for key in _RUNNER_SPEC_KEYS:
        candidate = config.get(key)
        if candidate is not None:
            runner_spec = candidate
            break
    if callable(runner_spec):
        return runner_spec
    if not isinstance(runner_spec, str) or ":" not in runner_spec:
        raise ValueError("langgraph subgraph runner must be '<module>:<callable>'")
    module_name, _, attr_name = runner_spec.partition(":")
    if not module_name or not attr_name:
        raise ValueError("langgraph subgraph runner spec is invalid")
    module = importlib.import_module(module_name)
    runner = getattr(module, attr_name, None)
    if not callable(runner):
        raise ValueError(f"langgraph subgraph callable not found: {runner_spec}")
    return runner


def _execute_subgraph_runner(
    runner: Callable[..., dict[str, Any]],
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: RunStore,
) -> dict[str, Any]:
    try:
        result = runner(
            contract=contract,
            worktree_path=worktree_path,
            schema_path=schema_path,
            run_store=run_store,
        )
    except TypeError as exc:
        if not _is_runner_signature_compat_error(exc):
            raise
        result = runner(contract, worktree_path, schema_path, run_store)
    if not isinstance(result, dict):
        raise TypeError("langgraph subgraph runner must return dict result")
    return result


def run_agents_stream(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: RunStore,
) -> dict[str, Any]:
    runner = AgentsRunner(run_store)
    subgraph_config = _resolve_subgraph_config(contract)
    if not _subgraph_enabled(subgraph_config):
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=False)

    run_id, task_id = _extract_run_and_task_id(contract)
    strategy = "langgraph_subgraph"
    if isinstance(subgraph_config, dict):
        named_strategy = subgraph_config.get("name") or subgraph_config.get("id")
        if isinstance(named_strategy, str) and named_strategy.strip():
            strategy = named_strategy.strip()

    _append_audit_event(
        run_store,
        run_id,
        task_id,
        event="RUNNER_SELECTED",
        level="INFO",
        meta={
            "runner": "langgraph_subgraph",
            "strategy": strategy,
            "source": "agents_stream_flow",
            "stream_contract": "sse_compatible_v1",
            "fallback_runner": "agents_runner.run_contract",
        },
    )

    try:
        subgraph_runner = _resolve_subgraph_runner(subgraph_config)
    except Exception as exc:  # noqa: BLE001
        _append_audit_event(
            run_store,
            run_id,
            task_id,
            event="TEMPORAL_WORKFLOW_FALLBACK",
            level="WARN",
            meta={
                "source": "agents_stream_flow",
                "strategy": strategy,
                "reason": "invalid_subgraph_config",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "fallback_runner": "agents_runner.run_contract",
                "stream_contract": "sse_compatible_v1",
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=False)

    try:
        subgraph_result = _execute_subgraph_runner(
            subgraph_runner,
            contract,
            worktree_path,
            schema_path,
            run_store,
        )
    except Exception as exc:  # noqa: BLE001
        _append_audit_event(
            run_store,
            run_id,
            task_id,
            event="TEMPORAL_WORKFLOW_FALLBACK",
            level="WARN",
            meta={
                "source": "agents_stream_flow",
                "strategy": strategy,
                "reason": "subgraph_failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
                "fallback_runner": "agents_runner.run_contract",
                "stream_contract": "sse_compatible_v1",
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=False)

    if _subgraph_result_failed(subgraph_result):
        _append_audit_event(
            run_store,
            run_id,
            task_id,
            event="TEMPORAL_WORKFLOW_FALLBACK",
            level="WARN",
            meta={
                "source": "agents_stream_flow",
                "strategy": strategy,
                "reason": "subgraph_result_failed",
                "subgraph_status": str(subgraph_result.get("status", "")),
                **_subgraph_failure_details(subgraph_result),
                "fallback_runner": "agents_runner.run_contract",
                "stream_contract": "sse_compatible_v1",
            },
        )
        return runner.run_contract(contract, worktree_path, schema_path, mock_mode=False)

    return subgraph_result
