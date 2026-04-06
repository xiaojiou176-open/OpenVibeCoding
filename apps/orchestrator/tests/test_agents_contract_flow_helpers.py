from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from cortexpilot_orch.runners import agents_contract_flow


class _Store:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append((run_id, event))


class _RaisingStore:
    def append_event(self, _run_id: str, _event: dict[str, Any]) -> None:
        raise RuntimeError("append failed")


def _workflow_payloads(store: _Store) -> list[dict[str, Any]]:
    return [
        event["payload"]
        for _, event in store.events
        if event.get("event") == "WORKFLOW_STATUS"
    ]


def test_contract_helper_primitives(monkeypatch) -> None:
    assert agents_contract_flow._as_bool(1) is True
    assert agents_contract_flow._as_bool(0.0) is False
    assert agents_contract_flow._contract_task_id({}) == "task"
    assert agents_contract_flow._contract_task_id({"task_id": " x "}) == "x"
    assert agents_contract_flow._contract_attempt({"attempt": "2"}) is None
    assert agents_contract_flow._contract_attempt({"attempt": 2}) == 2

    assert agents_contract_flow._langgraph_requested({"subflow": {"engine": "legacy", "enabled": True}}) == (
        False,
        "contract.subflow.engine",
    )
    assert agents_contract_flow._langgraph_requested({"subflow": {"engine": "langgraph"}}) == (
        True,
        "contract.subflow.engine",
    )
    assert agents_contract_flow._langgraph_requested({"langgraph": {"enabled": True}}) == (
        True,
        "contract.langgraph.enabled",
    )

    monkeypatch.setenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", "yes")
    assert agents_contract_flow._langgraph_requested({}) == (
        True,
        "env.CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW",
    )

    monkeypatch.setenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", "")
    assert agents_contract_flow._langgraph_requested({}) == (False, "default")



def test_append_workflow_audit_event_fail_closed_paths() -> None:
    # append_event missing -> should no-op
    agents_contract_flow._append_workflow_audit_event(
        object(),
        {},
        level="INFO",
        stage="route_selected",
        route="legacy_runner",
        details=None,
    )

    # append_event raises -> should be swallowed
    agents_contract_flow._append_workflow_audit_event(
        _RaisingStore(),
        {"run_id": "r1"},
        level="WARN",
        stage="fallback_to_legacy",
        route="legacy_runner",
        details={"reason": "x"},
    )



def test_resolve_langgraph_executor_paths(monkeypatch) -> None:
    monkeypatch.setattr(agents_contract_flow, "import_module", lambda _name: (_ for _ in ()).throw(ImportError("x")))
    assert agents_contract_flow._resolve_langgraph_executor() is None

    module = SimpleNamespace(run_langgraph_contract_subflow="not-callable")
    monkeypatch.setattr(agents_contract_flow, "import_module", lambda _name: module)
    assert agents_contract_flow._resolve_langgraph_executor() is None

    def _callable_executor(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "SUCCESS"}

    module_callable = SimpleNamespace(run_langgraph_contract_subflow=_callable_executor)
    monkeypatch.setattr(agents_contract_flow, "import_module", lambda _name: module_callable)
    assert agents_contract_flow._resolve_langgraph_executor() is _callable_executor



def test_langgraph_failure_details() -> None:
    assert agents_contract_flow._langgraph_result_failed({"status": "blocked"}) is True
    assert agents_contract_flow._langgraph_result_failed({"failure": {"message": "x"}}) is True
    assert agents_contract_flow._langgraph_result_failed({"status": "success", "failure": None}) is False

    assert agents_contract_flow._langgraph_failure_details({"failure": "invalid"}) == {}
    assert agents_contract_flow._langgraph_failure_details({"failure": {"error_type": "  ", "message": ""}}) == {}
    assert agents_contract_flow._langgraph_failure_details(
        {"failure": {"error_type": "X", "message": "boom"}}
    ) == {"subflow_error_type": "X", "subflow_failure_message": "boom"}



def test_run_agents_contract_fallbacks_for_executor_missing_and_invalid_result(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    class _Runner:
        def __init__(self, _store: _Store) -> None:
            return None

        def run_contract(
            self,
            contract: dict[str, Any],
            worktree_path: Path,
            schema_path: Path,
            mock_mode: bool = False,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "task_id": contract.get("task_id"),
                    "worktree": str(worktree_path),
                    "schema": str(schema_path),
                    "mock_mode": mock_mode,
                }
            )
            return {"path": "legacy", "status": "SUCCESS"}

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _Runner)

    contract = {"task_id": "task-1", "run_id": "run-1", "subflow": {"engine": "langgraph", "enabled": True}}

    # executor missing
    store_missing = _Store()
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: None)
    result_missing = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store_missing,
        mock_mode=True,
    )
    assert result_missing["path"] == "legacy"
    payloads_missing = _workflow_payloads(store_missing)
    assert any(p.get("fallback_reason") == "langgraph_executor_unavailable" for p in payloads_missing)

    # executor returns invalid non-dict
    def _invalid_executor(*_args: Any, **_kwargs: Any) -> Any:
        return "invalid"

    store_invalid = _Store()
    monkeypatch.setattr(agents_contract_flow, "_resolve_langgraph_executor", lambda: _invalid_executor)
    result_invalid = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store_invalid,
        mock_mode=False,
    )
    assert result_invalid["path"] == "legacy"
    payloads_invalid = _workflow_payloads(store_invalid)
    fallback = next(p for p in payloads_invalid if p.get("stage") == "fallback_to_legacy")
    assert fallback["fallback_reason"] == "langgraph_result_invalid"
    assert fallback["result_type"] == "str"
