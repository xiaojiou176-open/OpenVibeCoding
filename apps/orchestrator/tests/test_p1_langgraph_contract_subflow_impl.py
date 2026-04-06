from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.runners import langgraph_contract_subflow


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


def _workflow_payloads(store: _DummyStore) -> list[dict[str, Any]]:
    return [
        item["payload"]["payload"]
        for item in store.events
        if item.get("payload", {}).get("event_type") == "WORKFLOW_STATUS"
    ]


def _base_contract() -> dict[str, Any]:
    return {
        "run_id": "run_p1_subflow",
        "task_id": "task_p1_subflow",
        "instruction": "minimal contract subflow",
    }


def test_subflow_degrades_gracefully_when_langgraph_runtime_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        langgraph_contract_subflow,
        "_resolve_langgraph_executor",
        lambda: (None, "langgraph_runtime_missing"),
    )
    store = _DummyStore()

    result = langgraph_contract_subflow.run_langgraph_contract_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["error_type"] == "langgraph_runtime_missing"
    audit = result["evidence_refs"]["subflow_audit"]
    assert audit["degraded"] is True
    assert audit["mode"] == "degraded"
    payloads = _workflow_payloads(store)
    assert any(item["stage"] == "subflow_degraded" for item in payloads)
    assert all(item["route"] == "langgraph_subflow" for item in payloads)


def test_subflow_returns_success_result_when_executor_succeeds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def _executor(state: dict[str, Any]) -> dict[str, Any]:
        calls.append(dict(state))
        return {
            "task_id": state["task_id"],
            "status": "SUCCESS",
            "summary": "executor-ok",
            "evidence_refs": {"trace_id": "trace-1"},
        }

    monkeypatch.setattr(
        langgraph_contract_subflow,
        "_resolve_langgraph_executor",
        lambda: (_executor, None),
    )
    store = _DummyStore()

    result = langgraph_contract_subflow.run_langgraph_contract_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=True,
    )

    assert result["status"] == "SUCCESS"
    assert result["summary"] == "executor-ok"
    assert result["failure"] is None
    assert calls and calls[0]["mock_mode"] is True
    audit = result["evidence_refs"]["subflow_audit"]
    assert audit["degraded"] is False
    assert audit["status"] == "SUCCESS"
    payloads = _workflow_payloads(store)
    assert [item["stage"] for item in payloads] == ["subflow_started", "subflow_completed"]
    assert all(item["route"] == "langgraph_subflow" for item in payloads)


def test_subflow_catches_executor_exception_and_returns_failed_result(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def _broken_executor(_state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        langgraph_contract_subflow,
        "_resolve_langgraph_executor",
        lambda: (_broken_executor, None),
    )
    store = _DummyStore()

    result = langgraph_contract_subflow.run_langgraph_contract_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["error_type"] == "langgraph_execution_error"
    assert result["evidence_refs"]["subflow_audit"]["reason"] == "langgraph_execution_error"
    payloads = _workflow_payloads(store)
    assert any(item["stage"] == "subflow_failed" for item in payloads)
    assert all(item["route"] == "langgraph_subflow" for item in payloads)


def test_subflow_reports_invalid_executor_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        langgraph_contract_subflow,
        "_resolve_langgraph_executor",
        lambda: (lambda _state: "invalid", None),
    )
    store = _DummyStore()

    result = langgraph_contract_subflow.run_langgraph_contract_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["error_type"] == "langgraph_invalid_result"
    payloads = _workflow_payloads(store)
    assert any(item["stage"] == "subflow_failed" for item in payloads)


def test_subflow_failed_status_enriches_failure_and_filters_payload(monkeypatch, tmp_path: Path) -> None:
    def _failed_executor(_state: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "BLOCKED",
            "summary": "blocked by guard",
            "failure": "not-a-dict",
            "evidence_refs": "invalid",
            "contracts": [{"id": "ok"}, "drop-me"],
            "handoff_payload": {"owner": "pm"},
        }

    monkeypatch.setattr(
        langgraph_contract_subflow,
        "_resolve_langgraph_executor",
        lambda: (_failed_executor, None),
    )
    store = _DummyStore()

    result = langgraph_contract_subflow.run_langgraph_contract_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "BLOCKED"
    assert result["failure"]["message"] == "blocked by guard"
    assert result["contracts"] == [{"id": "ok"}]
    assert result["handoff_payload"] == {"owner": "pm"}
    assert "subflow_audit" in result["evidence_refs"]
    payloads = _workflow_payloads(store)
    completed = [item for item in payloads if item["stage"] == "subflow_completed"]
    assert completed
    assert completed[0]["status"] == "BLOCKED"


def test_append_subflow_event_ignores_missing_or_broken_append_event() -> None:
    class _NoAppend:
        pass

    langgraph_contract_subflow._append_subflow_event(
        _NoAppend(),  # type: ignore[arg-type]
        {"run_id": "run_1"},
        level="INFO",
        stage="subflow_started",
        details={"x": "y"},
    )

    class _Broken:
        def append_event(self, _run_id: str, _event: dict[str, Any]) -> None:
            raise RuntimeError("append failed")

    langgraph_contract_subflow._append_subflow_event(
        _Broken(),  # type: ignore[arg-type]
        {"run_id": "run_1", "task_id": " "},
        level="INFO",
        stage="subflow_started",
        details={"x": "y"},
    )


def test_resolve_langgraph_executor_handles_incompatible_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        langgraph_contract_subflow,
        "import_module",
        lambda _name: SimpleNamespace(START="start", END="end"),
    )
    executor, reason = langgraph_contract_subflow._resolve_langgraph_executor()
    assert executor is None
    assert reason == "langgraph_runtime_incompatible"


def test_resolve_langgraph_executor_builds_executor_and_validates_result(monkeypatch) -> None:
    class _Compiled:
        def __init__(self, node):
            self.node = node

        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return self.node(state)

    class _StateGraph:
        def __init__(self, _state_type: type) -> None:
            self.node = None

        def add_node(self, _name: str, fn):
            self.node = fn

        def add_edge(self, _src, _dst) -> None:
            return None

        def compile(self) -> _Compiled:
            return _Compiled(self.node)

    monkeypatch.setattr(
        langgraph_contract_subflow,
        "import_module",
        lambda _name: SimpleNamespace(StateGraph=_StateGraph, START="S", END="E"),
    )

    executor, reason = langgraph_contract_subflow._resolve_langgraph_executor()
    assert reason is None
    assert executor is not None
    result = executor({"task_id": "task_x", "mock_mode": 1})
    assert result["task_id"] == "task_x"
    assert result["mock_mode"] is True
    fallback_task_id_result = executor({"task_id": 123})
    assert fallback_task_id_result["task_id"] == "task"


def test_resolve_langgraph_executor_raises_when_compiled_result_not_dict(monkeypatch) -> None:
    class _CompiledInvalid:
        def invoke(self, _state: dict[str, Any]) -> str:
            return "invalid"

    class _StateGraphInvalid:
        def __init__(self, _state_type: type) -> None:
            self.node = None

        def add_node(self, _name: str, fn):
            self.node = fn

        def add_edge(self, _src, _dst) -> None:
            return None

        def compile(self) -> _CompiledInvalid:
            return _CompiledInvalid()

    monkeypatch.setattr(
        langgraph_contract_subflow,
        "import_module",
        lambda _name: SimpleNamespace(StateGraph=_StateGraphInvalid, START="S", END="E"),
    )

    executor, reason = langgraph_contract_subflow._resolve_langgraph_executor()
    assert reason is None
    assert executor is not None
    with pytest.raises(TypeError, match="must be dict"):
        executor({"task_id": "task_x"})
