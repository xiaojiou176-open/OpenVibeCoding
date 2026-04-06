from __future__ import annotations

from typing import Any

from cortexpilot_orch.scheduler import core_helpers
from cortexpilot_orch.store.run_store import RunStore


def gate_result(passed: bool, violations: list[str] | None = None) -> dict[str, Any]:
    return core_helpers.gate_result(passed, violations)


def append_gate_failed(
    store: RunStore,
    run_id: str,
    gate: str,
    reason: str,
    schema: str | None = None,
    path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    core_helpers.append_gate_failed(store, run_id, gate, reason, schema=schema, path=path, extra=extra)


def append_policy_violation(
    store: RunStore,
    run_id: str,
    reason: str,
    path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    core_helpers.append_policy_violation(store, run_id, reason, path=path, extra=extra)


def build_policy_gate(
    integrated_gate: dict[str, Any] | None,
    network_gate: dict[str, Any] | None,
    mcp_gate: dict[str, Any] | None,
    sampling_gate: dict[str, Any] | None,
    tool_gate: dict[str, Any] | None,
    human_approval_required: bool,
    human_approved: bool | None,
) -> dict[str, Any]:
    return core_helpers.build_policy_gate(
        integrated_gate,
        network_gate,
        mcp_gate,
        sampling_gate,
        tool_gate,
        human_approval_required,
        human_approved,
    )
