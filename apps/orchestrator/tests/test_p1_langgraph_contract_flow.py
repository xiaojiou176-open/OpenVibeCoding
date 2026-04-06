from __future__ import annotations

from pathlib import Path
from typing import Any

from cortexpilot_orch.runners import agents_contract_flow


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "event": payload})


def _workflow_payloads(store: _DummyStore) -> list[dict[str, Any]]:
    return [
        item["event"]["payload"]
        for item in store.events
        if item.get("event", {}).get("event_type") == "WORKFLOW_STATUS"
    ]


def test_contract_flow_default_path_keeps_legacy_runner(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

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
            calls.append(
                {
                    "contract": contract,
                    "worktree_path": str(worktree_path),
                    "schema_path": str(schema_path),
                    "mock_mode": mock_mode,
                }
            )
            return {"ok": True, "path": "legacy"}

    def _should_not_call() -> None:
        raise AssertionError("langgraph executor should not be used by default")

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", _should_not_call)
    monkeypatch.delenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", raising=False)

    contract = {"task_id": "task_legacy", "run_id": "run_legacy"}
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=True,
    )

    assert result == {"ok": True, "path": "legacy"}
    assert len(calls) == 1
    payloads = _workflow_payloads(store)
    assert payloads[0]["stage"] == "route_selected"
    assert payloads[0]["route"] == "legacy_runner"


def test_contract_flow_prefers_langgraph_when_enabled(monkeypatch, tmp_path: Path) -> None:
    runner_calls: list[dict[str, Any]] = []
    langgraph_calls: list[dict[str, Any]] = []

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
            runner_calls.append({"task_id": contract.get("task_id"), "mock_mode": mock_mode})
            return {"status": "SUCCESS", "task_id": contract.get("task_id", "task"), "path": "legacy"}

    def _fake_langgraph(
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        run_store: _DummyStore,
        mock_mode: bool,
    ) -> dict[str, Any]:
        langgraph_calls.append(
            {
                "task_id": contract.get("task_id"),
                "worktree_path": str(worktree_path),
                "schema_path": str(schema_path),
                "mock_mode": mock_mode,
            }
        )
        return {
            "task_id": contract.get("task_id", "task"),
            "status": "SUCCESS",
            "summary": "langgraph-path",
            "evidence_refs": {},
            "failure": None,
        }

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: _fake_langgraph)

    contract = {
        "task_id": "task_langgraph",
        "run_id": "run_langgraph",
        "subflow": {"engine": "langgraph", "enabled": True},
    }
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "SUCCESS"
    assert not runner_calls
    assert len(langgraph_calls) == 1
    payloads = _workflow_payloads(store)
    stages = [item["stage"] for item in payloads]
    assert stages == ["route_selected", "subflow_started", "subflow_completed"]
    assert all(item["route"] == "langgraph_subflow" for item in payloads if item["stage"] != "route_selected")


def test_contract_flow_enables_langgraph_when_subflow_enabled_without_engine(
    monkeypatch, tmp_path: Path
) -> None:
    runner_calls: list[dict[str, Any]] = []
    langgraph_calls: list[dict[str, Any]] = []

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
            runner_calls.append({"task_id": contract.get("task_id"), "mock_mode": mock_mode})
            return {"status": "SUCCESS", "task_id": contract.get("task_id", "task"), "path": "legacy"}

    def _fake_langgraph(
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        run_store: _DummyStore,
        mock_mode: bool,
    ) -> dict[str, Any]:
        langgraph_calls.append(
            {
                "task_id": contract.get("task_id"),
                "worktree_path": str(worktree_path),
                "schema_path": str(schema_path),
                "mock_mode": mock_mode,
            }
        )
        return {
            "task_id": contract.get("task_id", "task"),
            "status": "SUCCESS",
            "summary": "langgraph-path",
            "evidence_refs": {},
            "failure": None,
        }

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: _fake_langgraph)
    monkeypatch.delenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", raising=False)

    contract = {
        "task_id": "task_subflow_enabled_no_engine",
        "run_id": "run_subflow_enabled_no_engine",
        "subflow": {"enabled": True},
    }
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["status"] == "SUCCESS"
    assert not runner_calls
    assert len(langgraph_calls) == 1
    payloads = _workflow_payloads(store)
    assert payloads[0]["decision_source"] == "contract.subflow.enabled"
    assert payloads[0]["route"] == "langgraph_subflow"


def test_contract_flow_subflow_enabled_false_blocks_env_override(monkeypatch, tmp_path: Path) -> None:
    runner_calls: list[dict[str, Any]] = []

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
            runner_calls.append({"task_id": contract.get("task_id"), "mock_mode": mock_mode})
            return {"status": "SUCCESS", "task_id": contract.get("task_id", "task"), "path": "legacy"}

    def _should_not_call() -> None:
        raise AssertionError("langgraph executor should not be used when contract explicitly disables subflow")

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", _should_not_call)
    monkeypatch.setenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", "1")

    contract = {
        "task_id": "task_subflow_disabled_no_engine",
        "run_id": "run_subflow_disabled_no_engine",
        "subflow": {"enabled": False},
    }
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=True,
    )

    assert result["path"] == "legacy"
    assert len(runner_calls) == 1
    payloads = _workflow_payloads(store)
    assert payloads[0]["decision_source"] == "contract.subflow.enabled"
    assert payloads[0]["route"] == "legacy_runner"


def test_contract_flow_fallbacks_to_legacy_on_langgraph_exception(monkeypatch, tmp_path: Path) -> None:
    runner_calls: list[dict[str, Any]] = []

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
            runner_calls.append({"task_id": contract.get("task_id"), "mock_mode": mock_mode})
            return {"status": "SUCCESS", "task_id": contract.get("task_id", "task"), "path": "legacy"}

    def _raise_langgraph(
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        run_store: _DummyStore,
        mock_mode: bool,
    ) -> dict[str, Any]:
        raise RuntimeError("langgraph unavailable")

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: _raise_langgraph)

    contract = {
        "task_id": "task_fallback_exc",
        "run_id": "run_fallback_exc",
        "subflow": {"engine": "langgraph", "enabled": True},
    }
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=True,
    )

    assert result["path"] == "legacy"
    assert len(runner_calls) == 1
    payloads = _workflow_payloads(store)
    fallback_payload = next(item for item in payloads if item["stage"] == "fallback_to_legacy")
    assert fallback_payload["fallback_reason"] == "langgraph_subflow_exception"
    assert fallback_payload["route"] == "legacy_runner"


def test_contract_flow_fallbacks_to_legacy_on_failed_langgraph_result(
    monkeypatch, tmp_path: Path
) -> None:
    runner_calls: list[dict[str, Any]] = []

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
            runner_calls.append({"task_id": contract.get("task_id"), "mock_mode": mock_mode})
            return {"status": "SUCCESS", "task_id": contract.get("task_id", "task"), "path": "legacy"}

    def _failed_langgraph(
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        run_store: _DummyStore,
        mock_mode: bool,
    ) -> dict[str, Any]:
        return {
            "task_id": contract.get("task_id", "task"),
            "status": "FAILED",
            "summary": "langgraph-failed",
            "evidence_refs": {},
            "failure": {"message": "mock failure", "error_type": "mock_failed_type"},
        }

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: _failed_langgraph)

    contract = {
        "task_id": "task_fallback_failed",
        "run_id": "run_fallback_failed",
        "subflow": {"engine": "langgraph", "enabled": True},
    }
    store = _DummyStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=False,
    )

    assert result["path"] == "legacy"
    assert len(runner_calls) == 1
    payloads = _workflow_payloads(store)
    fallback_payload = next(item for item in payloads if item["stage"] == "fallback_to_legacy")
    assert fallback_payload["fallback_reason"] == "langgraph_result_failed"
    assert fallback_payload["subflow_status"] == "FAILED"
    assert fallback_payload["subflow_failure_message"] == "mock failure"
    assert fallback_payload["subflow_error_type"] == "mock_failed_type"
