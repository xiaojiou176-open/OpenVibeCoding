from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.runners import agents_contract_flow, agents_stream_flow
from cortexpilot_orch.scheduler import manifest_lifecycle


class _ContractStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


class _ContractRunner:
    calls: list[dict[str, Any]] = []

    def __init__(self, run_store: _ContractStore) -> None:
        self.run_store = run_store

    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        _ContractRunner.calls.append(
            {
                "task_id": contract.get("task_id"),
                "worktree_path": str(worktree_path),
                "schema_path": str(schema_path),
                "mock_mode": mock_mode,
            }
        )
        return {"status": "SUCCESS", "source": "legacy_runner"}


def _contract_workflow_payloads(store: _ContractStore) -> list[dict[str, Any]]:
    return [
        item["payload"].get("payload", {})
        for item in store.events
        if item["payload"].get("event_type") == "WORKFLOW_STATUS"
    ]


def _contract_langgraph_success(
    contract: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    run_store: _ContractStore,
    mock_mode: bool,
) -> dict[str, Any]:
    return {
        "task_id": contract.get("task_id", "task"),
        "status": "SUCCESS",
        "summary": "langgraph-contract-subflow",
        "evidence_refs": {
            "worktree": str(worktree_path),
            "schema": str(schema_path),
            "mock_mode": mock_mode,
            "events": len(run_store.events),
        },
        "failure": None,
    }


@pytest.mark.parametrize(
    ("scenario", "contract", "env_flag", "expect_langgraph", "decision_source"),
    [
        (
            "contract_enabled",
            {
                "run_id": "run_contract_enabled",
                "task_id": "task_contract_enabled",
                "subflow": {"engine": "langgraph", "enabled": True},
            },
            None,
            True,
            "contract.subflow.enabled",
        ),
        (
            "contract_disabled",
            {
                "run_id": "run_contract_disabled",
                "task_id": "task_contract_disabled",
                "subflow": {"engine": "langgraph", "enabled": False},
            },
            None,
            False,
            "contract.subflow.enabled",
        ),
        (
            "env_enabled",
            {"run_id": "run_env_enabled", "task_id": "task_env_enabled"},
            "1",
            True,
            "env.CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW",
        ),
        (
            "env_disabled",
            {"run_id": "run_env_disabled", "task_id": "task_env_disabled"},
            "0",
            False,
            "env.CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW",
        ),
    ],
)
def test_contract_subflow_enable_disable_matrix(
    monkeypatch,
    tmp_path: Path,
    scenario: str,
    contract: dict[str, Any],
    env_flag: str | None,
    expect_langgraph: bool,
    decision_source: str,
) -> None:
    _ContractRunner.calls = []
    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _ContractRunner)

    if env_flag is None:
        monkeypatch.delenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", raising=False)
    else:
        monkeypatch.setenv("CORTEXPILOT_LANGGRAPH_CONTRACT_SUBFLOW", env_flag)

    if expect_langgraph:
        monkeypatch.setattr(
            agents_contract_flow,
            "_resolve_langgraph_executor",
            lambda: _contract_langgraph_success,
        )
    else:
        monkeypatch.setattr(
            agents_contract_flow,
            "_resolve_langgraph_executor",
            lambda: pytest.fail(f"langgraph executor should not be used in {scenario}"),
        )

    store = _ContractStore()
    result = agents_contract_flow.run_agents_contract(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
        mock_mode=True,
    )

    payloads = _contract_workflow_payloads(store)
    assert payloads
    assert payloads[0]["stage"] == "route_selected"
    assert payloads[0]["decision_source"] == decision_source

    if expect_langgraph:
        assert result["summary"] == "langgraph-contract-subflow"
        assert _ContractRunner.calls == []
        assert [item["stage"] for item in payloads] == [
            "route_selected",
            "subflow_started",
            "subflow_completed",
        ]
        assert payloads[0]["route"] == "langgraph_subflow"
    else:
        assert result["source"] == "legacy_runner"
        assert len(_ContractRunner.calls) == 1
        assert [item["stage"] for item in payloads] == ["route_selected"]
        assert payloads[0]["route"] == "legacy_runner"


class _StreamStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


class _StreamRunner:
    calls: list[dict[str, Any]] = []

    def __init__(self, run_store: _StreamStore) -> None:
        self.run_store = run_store

    def run_contract(
        self,
        contract: dict[str, Any],
        worktree_path: Path,
        schema_path: Path,
        mock_mode: bool = False,
    ) -> dict[str, Any]:
        _StreamRunner.calls.append(
            {
                "task_id": contract.get("task_id"),
                "worktree_path": str(worktree_path),
                "schema_path": str(schema_path),
                "mock_mode": mock_mode,
            }
        )
        return {"status": "SUCCESS", "source": "legacy_runner"}


def _stream_subgraph_raise(**_kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("subgraph failed")


def _stream_subgraph_non_dict(**_kwargs: Any) -> dict[str, Any]:
    return {"wrong": "shape"}["missing"]


def _stream_events(store: _StreamStore, event_name: str) -> list[dict[str, Any]]:
    return [item["payload"] for item in store.events if item["payload"].get("event") == event_name]


@pytest.mark.parametrize(
    ("scenario", "runner_spec", "expected_reason"),
    [
        (
            "invalid_runner_spec",
            "not_a_valid_runner_spec",
            "invalid_subgraph_config",
        ),
        (
            "subgraph_runtime_failure",
            f"{__name__}:_stream_subgraph_raise",
            "subgraph_failed",
        ),
        (
            "subgraph_result_invalid",
            f"{__name__}:_stream_subgraph_non_dict",
            "subgraph_failed",
        ),
    ],
)
def test_stream_subgraph_failure_fallback_matrix(
    monkeypatch,
    tmp_path: Path,
    scenario: str,
    runner_spec: str,
    expected_reason: str,
) -> None:
    _StreamRunner.calls = []
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _StreamRunner)

    contract = {
        "run_id": f"run_stream_{scenario}",
        "task_id": f"task_stream_{scenario}",
        "stream_subgraph": {
            "enabled": True,
            "provider": "langgraph",
            "runner": runner_spec,
            "name": f"matrix_{scenario}",
        },
    }
    store = _StreamStore()

    result = agents_stream_flow.run_agents_stream(
        contract,
        tmp_path / "worktree",
        tmp_path / "schema.json",
        store,
    )

    assert result["source"] == "legacy_runner"
    assert len(_StreamRunner.calls) == 1

    selected = _stream_events(store, "RUNNER_SELECTED")
    fallback = _stream_events(store, "TEMPORAL_WORKFLOW_FALLBACK")
    assert selected, f"missing RUNNER_SELECTED for {scenario}"
    assert fallback, f"missing fallback event for {scenario}"
    assert fallback[0]["meta"]["reason"] == expected_reason
    assert fallback[0]["meta"]["fallback_runner"] == "agents_runner.run_contract"
    assert selected[0]["meta"]["stream_contract"] == "sse_compatible_v1"


class _LifecycleStore:
    def __init__(self) -> None:
        self.manifest = {"status": "RUNNING"}
        self.events: list[dict[str, Any]] = []
        self.reports: dict[str, dict[str, Any]] = {}

    def read_manifest(self, _run_id: str) -> dict[str, Any]:
        return dict(self.manifest)

    def write_manifest(self, _run_id: str, payload: dict[str, Any]) -> None:
        self.manifest = dict(payload)

    def append_event(self, _run_id: str, payload: dict[str, Any]) -> None:
        self.events.append(dict(payload))

    def write_report(self, _run_id: str, report_type: str, payload: dict[str, Any]) -> None:
        self.reports[report_type] = dict(payload)


@pytest.mark.parametrize(
    (
        "scenario",
        "strict_gate",
        "execution_status",
        "expected_gate_blocked",
        "expected_fallback_applied",
        "expected_rollback_applied",
        "expected_manifest_status",
    ),
    [
        (
            "optional_failure",
            False,
            "FAILURE",
            False,
            True,
            True,
            "RUNNING",
        ),
        (
            "strict_failure",
            True,
            "ERROR",
            True,
            False,
            False,
            "FAILURE",
        ),
        (
            "optional_success",
            False,
            "SUCCESS",
            False,
            False,
            False,
            "RUNNING",
        ),
        (
            "strict_success",
            True,
            "SUCCESS",
            False,
            False,
            False,
            "RUNNING",
        ),
    ],
)
def test_lifecycle_gate_optional_vs_strict_matrix(
    scenario: str,
    strict_gate: bool,
    execution_status: str,
    expected_gate_blocked: bool,
    expected_fallback_applied: bool,
    expected_rollback_applied: bool,
    expected_manifest_status: str,
) -> None:
    store = _LifecycleStore()
    snapshot = {"status": "RUNNING", "task_id": f"task_lifecycle_{scenario}"}

    decision = manifest_lifecycle.evaluate_subgraph_lifecycle_gate(
        store,
        f"run_lifecycle_{scenario}",
        snapshot,
        execution_meta={
            "status": execution_status,
            "error": f"{scenario}_error",
            "chain_id": "chain_p1",
            "step_name": "worker_subgraph",
            "subgraph_id": "sg_matrix",
            "rollback_manifest": snapshot,
        },
        capability_override={
            "enabled": True,
            "strict_gate": strict_gate,
            "fallback_to_legacy": True,
        },
    )

    assert decision["enabled"] is True
    assert decision["strict_gate"] is strict_gate
    assert decision["gate_blocked"] is expected_gate_blocked
    assert decision["fallback_applied"] is expected_fallback_applied
    assert decision["rollback_applied"] is expected_rollback_applied
    assert decision["compatibility_mode"] == "subgraph"
    assert store.manifest["status"] == expected_manifest_status
    assert "subgraph_lifecycle" in store.reports

    gate_events = [item for item in store.events if item.get("event") == "gate_failed"]
    rollback_events = [item for item in store.events if item.get("event") == "ROLLBACK_APPLIED"]
    if expected_gate_blocked:
        assert gate_events
    else:
        assert not gate_events
    if expected_rollback_applied:
        assert rollback_events
    else:
        assert not rollback_events
