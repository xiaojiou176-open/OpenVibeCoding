from __future__ import annotations

from typing import Any

from openvibecoding_orch.scheduler import manifest_lifecycle


class _DummyStore:
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


def test_resolve_subgraph_capability_defaults_disabled() -> None:
    capability = manifest_lifecycle.resolve_subgraph_capability()
    assert capability["enabled"] is False
    assert capability["strict_gate"] is False
    assert capability["fallback_to_legacy"] is True
    assert capability["source"] == "default"


def test_evaluate_subgraph_lifecycle_gate_optional_failure_rolls_back() -> None:
    store = _DummyStore()
    snapshot = {"status": "RUNNING", "task_id": "task_1"}
    decision = manifest_lifecycle.evaluate_subgraph_lifecycle_gate(
        store,
        "run_1",
        snapshot,
        execution_meta={
            "status": "FAILURE",
            "error": "node timeout",
            "chain_id": "chain_a",
            "step_name": "worker_subgraph",
            "subgraph_id": "sg_1",
            "rollback_manifest": snapshot,
        },
        capability_override={"enabled": True, "strict_gate": False, "fallback_to_legacy": True},
    )

    assert decision["enabled"] is True
    assert decision["gate_blocked"] is False
    assert decision["fallback_applied"] is True
    assert decision["rollback_applied"] is True
    assert store.manifest["status"] == "RUNNING"
    assert any(item.get("event") == "ROLLBACK_APPLIED" for item in store.events)
    assert store.reports["subgraph_lifecycle"]["decision"]["fallback_applied"] is True


def test_evaluate_subgraph_lifecycle_gate_strict_failure_blocks() -> None:
    store = _DummyStore()
    snapshot = {"status": "RUNNING", "task_id": "task_2"}
    decision = manifest_lifecycle.evaluate_subgraph_lifecycle_gate(
        store,
        "run_2",
        snapshot,
        execution_meta={"status": "ERROR", "error": "subgraph panic"},
        capability_override={"enabled": True, "strict_gate": True, "fallback_to_legacy": True},
    )

    assert decision["enabled"] is True
    assert decision["gate_blocked"] is True
    assert decision["fallback_applied"] is False
    assert decision["rollback_applied"] is False
    assert store.manifest["status"] == "FAILURE"
    assert "subgraph lifecycle gate blocked" in store.manifest["failure_reason"]
    assert any(item.get("event") == "gate_failed" for item in store.events)


def test_evaluate_subgraph_lifecycle_gate_disabled_keeps_legacy_behavior() -> None:
    store = _DummyStore()
    snapshot = {"status": "RUNNING", "task_id": "task_3"}
    decision = manifest_lifecycle.evaluate_subgraph_lifecycle_gate(
        store,
        "run_3",
        snapshot,
        execution_meta={"status": "FAILURE", "error": "ignored when disabled"},
    )

    assert decision["enabled"] is False
    assert decision["compatibility_mode"] == "legacy"
    assert decision["gate_blocked"] is False
    assert decision["fallback_applied"] is False
    assert decision["rollback_applied"] is False
    assert store.manifest["status"] == "RUNNING"
