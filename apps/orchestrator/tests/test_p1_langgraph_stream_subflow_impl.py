from __future__ import annotations

from pathlib import Path
from typing import Any

from openvibecoding_orch.runners import langgraph_stream_subflow


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


def _base_contract() -> dict[str, Any]:
    return {"run_id": "run_stream_subflow_p1", "task_id": "task_stream_subflow_p1"}


def _events(store: _DummyStore, name: str) -> list[dict[str, Any]]:
    return [item["payload"] for item in store.events if item["payload"].get("event") == name]


def test_stream_subflow_fallbacks_when_langgraph_missing(monkeypatch, tmp_path: Path) -> None:
    class _FakeRunner:
        def __init__(self, run_store: _DummyStore) -> None:
            self.run_store = run_store

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> dict[str, Any]:
            assert contract["task_id"] == "task_stream_subflow_p1"
            assert worktree_path == tmp_path / "worktree"
            assert schema_path == tmp_path / "schema.json"
            assert mock_mode is False
            return {"task_id": contract["task_id"], "status": "SUCCESS", "summary": "delegated"}

    monkeypatch.setattr(langgraph_stream_subflow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(langgraph_stream_subflow.importlib.util, "find_spec", lambda _name: None)

    store = _DummyStore()
    result = langgraph_stream_subflow.run_langgraph_stream_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["status"] == "SUCCESS"
    assert result["stream_contract"] == "sse_compatible_v1"
    assert result["stream_subflow"]["degraded"] is True
    assert result["stream_subflow"]["mode"] == "fallback_legacy_runner"
    fallback_events = _events(store, "TEMPORAL_WORKFLOW_FALLBACK")
    assert fallback_events
    assert fallback_events[0]["meta"]["reason"] == "langgraph_dependency_missing"


def test_stream_subflow_keeps_auditable_contract_when_langgraph_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _FakeRunner:
        def __init__(self, run_store: _DummyStore) -> None:
            self.run_store = run_store

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> dict[str, Any]:
            del worktree_path, schema_path, mock_mode
            return {
                "task_id": contract["task_id"],
                "status": "OK",
                "summary": "native-ready",
                "evidence_refs": {"thread_id": "th_1"},
                "failure": None,
            }

    monkeypatch.setattr(langgraph_stream_subflow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(langgraph_stream_subflow.importlib.util, "find_spec", lambda _name: object())

    store = _DummyStore()
    result = langgraph_stream_subflow.run_langgraph_stream_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["status"] == "SUCCESS"
    assert result["stream_subflow"]["degraded"] is False
    assert result["stream_subflow"]["mode"] == "delegated_legacy_runner"
    assert result["evidence_refs"]["thread_id"] == "th_1"
    assert _events(store, "TEMPORAL_WORKFLOW_FALLBACK") == []
    workflow_events = _events(store, "WORKFLOW_STATUS")
    assert workflow_events
    stages = [item["payload"]["stage"] for item in workflow_events]
    assert stages == ["route_selected", "subflow_started", "subflow_completed"]


def test_stream_subflow_returns_failed_payload_when_delegate_crashes(monkeypatch, tmp_path: Path) -> None:
    class _BrokenRunner:
        def __init__(self, run_store: _DummyStore) -> None:
            self.run_store = run_store

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> dict[str, Any]:
            del contract, worktree_path, schema_path, mock_mode
            raise RuntimeError("boom")

    monkeypatch.setattr(langgraph_stream_subflow, "AgentsRunner", _BrokenRunner)
    monkeypatch.setattr(langgraph_stream_subflow.importlib.util, "find_spec", lambda _name: object())

    store = _DummyStore()
    result = langgraph_stream_subflow.run_langgraph_stream_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["message"] == "langgraph stream subflow delegate failed"
    failed_events = _events(store, "TEMPORAL_WORKFLOW_FAILED")
    assert failed_events
    assert failed_events[0]["meta"]["reason"] == "legacy_runner_exception"


def test_stream_subflow_marks_failure_when_delegate_returns_invalid_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _InvalidRunner:
        def __init__(self, run_store: _DummyStore) -> None:
            self.run_store = run_store

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> str:
            del contract, worktree_path, schema_path, mock_mode
            return "invalid"

    monkeypatch.setattr(langgraph_stream_subflow, "AgentsRunner", _InvalidRunner)
    monkeypatch.setattr(langgraph_stream_subflow.importlib.util, "find_spec", lambda _name: object())

    store = _DummyStore()
    result = langgraph_stream_subflow.run_langgraph_stream_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["message"] == "langgraph stream subflow delegate returned invalid result"
    assert result["stream_subflow"]["mode"] == "delegate_invalid_result"
    failed_events = _events(store, "TEMPORAL_WORKFLOW_FAILED")
    assert failed_events
    assert failed_events[0]["meta"]["reason"] == "legacy_runner_result_invalid"


def test_stream_subflow_records_failed_status_from_delegate(monkeypatch, tmp_path: Path) -> None:
    class _FailedRunner:
        def __init__(self, run_store: _DummyStore) -> None:
            self.run_store = run_store

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> dict[str, Any]:
            del worktree_path, schema_path, mock_mode
            return {
                "task_id": contract["task_id"],
                "status": "FAILED",
                "summary": "delegate failed status",
                "failure": {"message": "delegate failed status", "error_type": "DelegateFailure"},
            }

    monkeypatch.setattr(langgraph_stream_subflow, "AgentsRunner", _FailedRunner)
    monkeypatch.setattr(langgraph_stream_subflow.importlib.util, "find_spec", lambda _name: object())

    store = _DummyStore()
    result = langgraph_stream_subflow.run_langgraph_stream_subflow(
        _base_contract(),
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["status"] == "FAILED"
    assert result["failure"]["message"] == "delegate failed status"
    failed_events = _events(store, "TEMPORAL_WORKFLOW_FAILED")
    assert failed_events
    assert failed_events[0]["meta"]["reason"] == "legacy_runner_failed_status"
    assert failed_events[0]["meta"]["subflow_status"] == "FAILED"
    workflow_events = _events(store, "WORKFLOW_STATUS")
    assert workflow_events
    stages = [item["payload"]["stage"] for item in workflow_events]
    assert stages[-1] == "subflow_failed"
