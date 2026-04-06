from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.runners import agents_stream_flow


class _FakeRunner:
    calls: list[dict[str, Any]] = []

    def __init__(self, run_store) -> None:
        self.run_store = run_store

    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        _FakeRunner.calls.append(
            {
                "contract": dict(contract),
                "worktree_path": str(worktree_path),
                "schema_path": str(schema_path),
                "mock_mode": mock_mode,
            }
        )
        return {"status": "SUCCESS", "source": "default_runner"}


class _FakeRunStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


def _subgraph_success(**kwargs) -> dict[str, Any]:
    contract = kwargs["contract"]
    return {"status": "SUCCESS", "source": "langgraph_subgraph", "task_id": contract.get("task_id")}


def _subgraph_failure(**_kwargs) -> dict[str, Any]:
    raise RuntimeError("subgraph exploded")


def _subgraph_success_positional(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: Any,
) -> dict[str, Any]:
    del worktree_path, schema_path, run_store
    return {"status": "SUCCESS", "source": "langgraph_subgraph_positional", "task_id": contract.get("task_id")}


def _subgraph_failed_result(**kwargs) -> dict[str, Any]:
    contract = kwargs["contract"]
    return {
        "status": "FAILED",
        "source": "langgraph_subgraph",
        "task_id": contract.get("task_id"),
        "failure": {"message": "subgraph rejected"},
    }


def _base_contract() -> dict[str, Any]:
    return {"run_id": "run_stream_p1", "task_id": "task_stream_p1"}


def test_stream_flow_keeps_default_runner_without_subgraph(monkeypatch, tmp_path: Path) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    store = _FakeRunStore()
    result = agents_stream_flow.run_agents_stream(
        _base_contract(),
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "default_runner"
    assert len(_FakeRunner.calls) == 1
    assert _FakeRunner.calls[0]["mock_mode"] is False
    assert store.events == []


def test_stream_flow_uses_langgraph_subgraph_when_enabled(monkeypatch, tmp_path: Path) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    contract = _base_contract()
    contract["stream_subgraph"] = {
        "enabled": True,
        "provider": "langgraph",
        "runner": f"{__name__}:_subgraph_success",
        "name": "p1_stream_subgraph",
    }
    store = _FakeRunStore()

    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "langgraph_subgraph"
    assert _FakeRunner.calls == []
    selected_events = [
        item["payload"]
        for item in store.events
        if item["payload"].get("event") == "RUNNER_SELECTED"
    ]
    assert selected_events
    assert selected_events[0]["meta"]["strategy"] == "p1_stream_subgraph"
    assert selected_events[0]["meta"]["stream_contract"] == "sse_compatible_v1"


def test_stream_flow_supports_positional_subgraph_runner_signature(monkeypatch, tmp_path: Path) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    contract = _base_contract()
    contract["stream_subgraph"] = {
        "enabled": True,
        "provider": "langgraph",
        "runner": f"{__name__}:_subgraph_success_positional",
    }
    store = _FakeRunStore()

    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "langgraph_subgraph_positional"
    assert _FakeRunner.calls == []
    fallback_events = [
        item["payload"]
        for item in store.events
        if item["payload"].get("event") == "TEMPORAL_WORKFLOW_FALLBACK"
    ]
    assert fallback_events == []


def test_stream_flow_fallback_on_subgraph_failure_with_audit(monkeypatch, tmp_path: Path) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    contract = _base_contract()
    contract["stream_subgraph"] = {
        "enabled": True,
        "provider": "langgraph",
        "runner": f"{__name__}:_subgraph_failure",
        "name": "p1_stream_subgraph",
    }
    store = _FakeRunStore()

    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "default_runner"
    assert len(_FakeRunner.calls) == 1
    fallback_events = [
        item["payload"]
        for item in store.events
        if item["payload"].get("event") == "TEMPORAL_WORKFLOW_FALLBACK"
    ]
    assert fallback_events
    meta = fallback_events[0]["meta"]
    assert meta["reason"] == "subgraph_failed"
    assert meta["fallback_runner"] == "agents_runner.run_contract"


def test_stream_flow_fallback_on_subgraph_failed_result_with_audit(monkeypatch, tmp_path: Path) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    contract = _base_contract()
    contract["stream_subgraph"] = {
        "enabled": True,
        "provider": "langgraph",
        "runner": f"{__name__}:_subgraph_failed_result",
        "name": "p1_stream_subgraph",
    }
    store = _FakeRunStore()

    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "default_runner"
    assert len(_FakeRunner.calls) == 1
    fallback_events = [
        item["payload"]
        for item in store.events
        if item["payload"].get("event") == "TEMPORAL_WORKFLOW_FALLBACK"
    ]
    assert fallback_events
    meta = fallback_events[0]["meta"]
    assert meta["reason"] == "subgraph_result_failed"
    assert meta["subgraph_status"] == "FAILED"
    assert meta["subgraph_failure_message"] == "subgraph rejected"


def test_resolve_subgraph_config_checks_stream_and_extensions() -> None:
    from_stream = {
        "stream": {
            "subgraph": {"enabled": True},
        }
    }
    assert agents_stream_flow._resolve_subgraph_config(from_stream) == {"enabled": True}

    from_extensions = {
        "extensions": {
            "langgraph_subgraph": {"enabled": True, "provider": "langgraph"},
        }
    }
    assert agents_stream_flow._resolve_subgraph_config(from_extensions) == {
        "enabled": True,
        "provider": "langgraph",
    }


def test_subgraph_enabled_and_failure_detail_helpers() -> None:
    assert agents_stream_flow._subgraph_enabled(None) is False
    assert agents_stream_flow._subgraph_enabled({"enabled": False}) is False
    assert agents_stream_flow._subgraph_enabled({"enabled": True}) is True
    assert agents_stream_flow._subgraph_enabled({"enabled": True, "provider": "LANGGRAPH"}) is True
    assert agents_stream_flow._subgraph_enabled({"enabled": True, "provider": "other"}) is False

    assert agents_stream_flow._subgraph_result_failed({"status": " blocked "}) is True
    assert agents_stream_flow._subgraph_result_failed({"status": "SUCCESS", "failure": {}}) is False
    assert agents_stream_flow._subgraph_result_failed({"status": "SUCCESS", "failure": {"message": "x"}}) is True

    assert agents_stream_flow._subgraph_failure_details({"failure": "bad"}) == {}
    assert agents_stream_flow._subgraph_failure_details(
        {"failure": {"error_type": "  TypeX  ", "message": "  denied  "}}
    ) == {
        "subgraph_error_type": "TypeX",
        "subgraph_failure_message": "denied",
    }


def test_extract_run_and_task_id_and_append_audit_event_guard_paths() -> None:
    run_id, task_id = agents_stream_flow._extract_run_and_task_id(
        {
            "meta": {"run_id": "meta-run"},
            "task_id": 1,
        }
    )
    assert run_id == "meta-run"
    assert task_id == ""

    class _NoAppend:
        pass

    agents_stream_flow._append_audit_event(
        _NoAppend(),  # type: ignore[arg-type]
        "run_1",
        "task_1",
        event="RUNNER_SELECTED",
        level="INFO",
        meta={"k": "v"},
    )

    class _BrokenStore:
        def append_event(self, _run_id: str, _payload: dict[str, Any]) -> None:
            raise RuntimeError("append failed")

    agents_stream_flow._append_audit_event(
        _BrokenStore(),  # type: ignore[arg-type]
        "run_1",
        "task_1",
        event="RUNNER_SELECTED",
        level="INFO",
        meta={"k": "v"},
    )


def test_resolve_subgraph_runner_and_execute_helper_branches(tmp_path: Path) -> None:
    runner = agents_stream_flow._resolve_subgraph_runner({"runner": _subgraph_success})
    assert runner is _subgraph_success

    via_entrypoint = agents_stream_flow._resolve_subgraph_runner(
        {"entrypoint": f"{__name__}:_subgraph_success"}
    )
    assert via_entrypoint is _subgraph_success

    via_handler = agents_stream_flow._resolve_subgraph_runner(
        {"handler": f"{__name__}:_subgraph_success"}
    )
    assert via_handler is _subgraph_success

    with pytest.raises(ValueError, match="runner must be"):
        agents_stream_flow._resolve_subgraph_runner({"runner": "bad-spec"})

    with pytest.raises(ValueError, match="callable not found"):
        agents_stream_flow._resolve_subgraph_runner(
            {"runner": "importlib:no_such_attr"}
        )

    with pytest.raises(TypeError, match="must return dict"):
        agents_stream_flow._execute_subgraph_runner(
            lambda **_kwargs: "invalid",  # type: ignore[return-value]
            _base_contract(),
            tmp_path / "wt",
            tmp_path / "schema.json",
            _FakeRunStore(),  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="boom"):
        agents_stream_flow._execute_subgraph_runner(
            lambda **_kwargs: (_ for _ in ()).throw(TypeError("boom")),
            _base_contract(),
            tmp_path / "wt",
            tmp_path / "schema.json",
            _FakeRunStore(),  # type: ignore[arg-type]
        )


def test_signature_compat_marker_detection() -> None:
    assert agents_stream_flow._is_runner_signature_compat_error(
        TypeError("got an unexpected keyword argument 'contract'")
    )
    assert agents_stream_flow._is_runner_signature_compat_error(
        TypeError("missing 1 required positional argument")
    )
    assert not agents_stream_flow._is_runner_signature_compat_error(TypeError("plain boom"))


def test_stream_flow_uses_nested_stream_config_and_context_run_id_for_fallback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _FakeRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    contract = {
        "context": {"run_id": "nested_run"},
        "task_id": "nested_task",
        "stream": {
            "subgraph": {
                "enabled": True,
                "provider": "langgraph",
                "runner": "invalid",
                "id": "nested_strategy",
            }
        },
    }
    store = _FakeRunStore()
    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "wt",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "default_runner"
    assert len(_FakeRunner.calls) == 1
    fallback_events = [
        item
        for item in store.events
        if item["payload"].get("event") == "TEMPORAL_WORKFLOW_FALLBACK"
    ]
    assert fallback_events
    assert fallback_events[0]["run_id"] == "nested_run"
    assert fallback_events[0]["payload"]["meta"]["reason"] == "invalid_subgraph_config"
    assert fallback_events[0]["payload"]["meta"]["strategy"] == "nested_strategy"
