from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path
from typing import Any

from openvibecoding_orch.runners.agents_runner import AgentsRunner
from openvibecoding_orch.runners.app_server_runner import AppServerRunner
from openvibecoding_orch.runners.codex_runner import CodexRunner
from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.scheduler import core_helpers, rollback_pipeline, tool_execution_pipeline
from openvibecoding_orch.store.run_store import RunStore
from tooling.tampermonkey.runner import run_tampermonkey


def run_search_pipeline(
    run_id: str,
    tool_runner: ToolRunner,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    if len(args) == 3:
        store, request, requested_by = args
    elif len(args) == 2:
        request, requested_by = args
        store = kwargs.get("store") or RunStore()
    else:
        raise TypeError("run_search_pipeline expected (run_id, tool_runner, store, request, requested_by)")
    return tool_execution_pipeline.run_search_pipeline(
        run_id=run_id,
        tool_runner=tool_runner,
        store=store,
        request=request,
        requested_by=requested_by,
        contract_policy=kwargs.get("contract_policy"),
    )


def run_sampling_requests(
    run_id: str,
    tool_runner: ToolRunner,
    store: RunStore,
    request: dict[str, Any],
) -> dict[str, Any]:
    return tool_execution_pipeline.run_sampling_requests(
        run_id=run_id,
        tool_runner=tool_runner,
        store=store,
        request=request,
    )


def run_browser_tasks(
    run_id: str,
    tool_runner: ToolRunner,
    store: RunStore,
    request: dict[str, Any],
    requested_by: dict[str, Any] | None = None,
    contract_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return tool_execution_pipeline.run_browser_tasks(
        run_id=run_id,
        tool_runner=tool_runner,
        store=store,
        request=request,
        now_ts=core_helpers.now_ts,
        requested_by=requested_by,
        contract_policy=contract_policy,
    )


def run_tampermonkey_tasks(
    run_id: str,
    request: dict[str, Any],
    store: RunStore,
    requested_by: dict[str, Any] | None = None,
    contract_policy: dict[str, Any] | None = None,
    run_tampermonkey_fn: Any = run_tampermonkey,
) -> dict[str, Any]:
    return tool_execution_pipeline.run_tampermonkey_tasks(
        run_id=run_id,
        request=request,
        store=store,
        run_tampermonkey_fn=run_tampermonkey_fn,
        requested_by=requested_by,
        contract_policy=contract_policy,
    )


def run_optional_tool_requests(
    *,
    run_id: str,
    store: RunStore,
    tool_runner: ToolRunner,
    assigned_agent: dict[str, Any],
    contract_browser_policy: dict[str, Any] | None,
    search_request: dict[str, Any] | None,
    browser_request: dict[str, Any] | None,
    tamper_request: dict[str, Any] | None,
    sampling_request: dict[str, Any] | None,
    run_search_pipeline_fn: Any,
    run_browser_tasks_fn: Any,
    run_tampermonkey_tasks_fn: Any,
    run_sampling_requests_fn: Any,
) -> str:
    if search_request:
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_PARALLEL_POLICY",
                "run_id": run_id,
                "meta": {
                    "parallel": search_request.get("parallel"),
                    "providers": search_request.get("providers"),
                },
            },
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_VERIFY_POLICY",
                "run_id": run_id,
                "meta": {
                    "verify": search_request.get("verify"),
                },
            },
        )
        search_result = run_search_pipeline_fn(
            run_id,
            tool_runner,
            store,
            search_request,
            assigned_agent,
            contract_policy=contract_browser_policy,
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "SEARCH_PIPELINE_RESULT",
                "run_id": run_id,
                "meta": search_result,
            },
        )
        if not search_result.get("ok", True):
            return "search pipeline failed"

    if browser_request:
        browser_result = run_browser_tasks_fn(
            run_id,
            tool_runner,
            store,
            browser_request,
            requested_by=assigned_agent,
            contract_policy=contract_browser_policy,
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "BROWSER_TASKS_RESULT",
                "run_id": run_id,
                "meta": browser_result,
            },
        )
        if not browser_result.get("ok", True):
            return "browser tasks failed"

    if tamper_request:
        tamper_result = run_tampermonkey_tasks_fn(
            run_id,
            tamper_request,
            store,
            requested_by=assigned_agent,
            contract_policy=contract_browser_policy,
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "TAMPERMONKEY_TASKS_RESULT",
                "run_id": run_id,
                "meta": tamper_result,
            },
        )
        if not tamper_result.get("ok", True):
            return "tampermonkey tasks failed"

    if sampling_request:
        sampling_result = run_sampling_requests_fn(run_id, tool_runner, store, sampling_request)
        store.append_event(
            run_id,
            {
                "level": "INFO" if sampling_result.get("ok", True) else "ERROR",
                "event": "MCP_SAMPLING_REQUEST",
                "run_id": run_id,
                "meta": sampling_result,
            },
        )
        if not sampling_result.get("ok", True):
            return "sampling requests failed"

    return ""


def apply_rollback(worktree: Path, rollback: dict[str, Any]) -> dict[str, Any]:
    return rollback_pipeline.apply_rollback(worktree, rollback)


def scoped_revert(worktree: Path, paths: list[str]) -> dict[str, Any]:
    return rollback_pipeline.scoped_revert(worktree, paths)


_SUPPORTED_RUNTIME_OPTION_RUNNERS = {"agents", "app-server", "app_server", "codex", "claude"}
_ADAPTER_RUNTIME_RUNNERS = {"codex", "claude"}
_RUNNER_ALIASES = {"app_server": "app-server"}
_SUPPORTED_RUNNERS_TEXT = "agents, app-server/app_server, codex, claude"


def _normalize_runner_name(raw_runner: Any, default: str) -> str:
    token = str(raw_runner or "").strip().lower()
    normalized = token or default
    return _RUNNER_ALIASES.get(normalized, normalized)


def _build_runner_via_execution_adapter(
    contract: dict[str, Any],
    store: RunStore,
    runner_name: str,
) -> object | None:
    if runner_name not in _ADAPTER_RUNTIME_RUNNERS:
        return None
    try:
        execution_adapter = import_module("openvibecoding_orch.runners.execution_adapter")
    except ModuleNotFoundError:
        return None
    for factory_name in (
        "build_execution_adapter",
        "create_runner",
        "build_runner",
        "create_execution_runner",
        "build_execution_runner",
    ):
        factory = getattr(execution_adapter, factory_name, None)
        if not callable(factory):
            continue
        call_variants = (
            lambda: factory(run_store=store, runner_name=runner_name),
            lambda: factory(run_store=store, runner=runner_name),
            lambda: factory(runner=runner_name, store=store, contract=contract),
            lambda: factory(runner_name=runner_name, store=store, contract=contract),
            lambda: factory(runner=runner_name, store=store),
            lambda: factory(runner_name=runner_name, store=store),
            lambda: factory(runner_name, store, contract),
            lambda: factory(runner_name, store),
        )
        for call in call_variants:
            try:
                return call()
            except TypeError:
                continue
    return None


def select_runner(contract: dict[str, Any], store: RunStore) -> object:
    runtime_options = contract.get("runtime_options") if isinstance(contract.get("runtime_options"), dict) else {}
    runtime_runner = str(runtime_options.get("runner", "")).strip().lower()
    if runtime_runner and runtime_runner not in _SUPPORTED_RUNTIME_OPTION_RUNNERS:
        raise ValueError(
            f"unsupported runtime_options.runner: {runtime_runner} (supported: {_SUPPORTED_RUNNERS_TEXT})"
        )
    runner_name = _normalize_runner_name(runtime_runner, _normalize_runner_name(os.getenv("OPENVIBECODING_RUNNER"), "agents"))
    adapter_runner = _build_runner_via_execution_adapter(contract, store, runner_name)
    if adapter_runner is not None:
        if not hasattr(adapter_runner, "run_contract"):
            raise TypeError("execution_adapter runner must implement run_contract")
        return adapter_runner
    if runner_name == "agents" or runner_name == "claude":
        return AgentsRunner(store)
    if runner_name == "app-server":
        return AppServerRunner(store)
    if runner_name == "codex":
        return CodexRunner(store)
    raise ValueError(f"unsupported runner: {runner_name} (supported: {_SUPPORTED_RUNNERS_TEXT})")


def max_retries(contract: dict[str, Any]) -> int:
    return rollback_pipeline.max_retries(contract)


def retry_backoff(contract: dict[str, Any]) -> int:
    return rollback_pipeline.retry_backoff(contract)


_STRICT_TRUTHY = {"1", "true", "yes", "y", "on"}


def _coerce_strict(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _STRICT_TRUTHY:
            return True
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def execute_replay_action(
    *,
    runner: Any,
    action: str,
    run_id: str,
    store: RunStore,
    event: str,
    baseline_run_id: str | None = None,
    strict: bool | None = None,
) -> dict[str, Any]:
    try:
        if action == "replay":
            return runner.replay(run_id, baseline_run_id=baseline_run_id)
        if action == "verify":
            return runner.verify(run_id, strict=_coerce_strict(strict))
        if action == "reexecute":
            return runner.reexecute(run_id, strict=_coerce_strict(strict))
        raise ValueError(f"unsupported replay action: {action}")
    except Exception as exc:  # noqa: BLE001
        run_dir = store._runs_root / run_id
        if (run_dir / "manifest.json").exists():
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": event,
                    "run_id": run_id,
                    "meta": {"error": str(exc)},
                },
            )
        return {"run_id": run_id, "status": "fail", "error": str(exc)}
