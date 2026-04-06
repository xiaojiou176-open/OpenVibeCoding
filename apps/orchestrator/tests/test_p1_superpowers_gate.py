from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cortexpilot_orch.contract.validator import ContractValidator, evaluate_superpowers_gate
from cortexpilot_orch.scheduler import task_execution_pipeline


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append((run_id, event))


def _output_schema_artifact(role: str = "worker") -> dict[str, str]:
    schema_root = REPO_ROOT / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    return {
        "name": f"output_schema.{role.lower()}",
        "uri": f"schemas/{schema_name}",
        "sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
    }


def _contract_base() -> dict[str, Any]:
    return {
        "task_id": "task-superpowers-01",
        "task_type": "IMPLEMENT",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "inputs": {"spec": "实现 superpowers methodology gate", "artifacts": [_output_schema_artifact("worker")]},
        "required_outputs": [{"name": "patch.diff", "type": "patch", "acceptance": "produce audited patch"}],
        "allowed_paths": ["apps/orchestrator/src/cortexpilot_orch/contract/validator.py"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "smoke", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["edit-01-cursor-compat"],
        "timeout_retry": {"timeout_sec": 60, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": ["superpowers://required"],
        "log_refs": {"run_id": "run-sp-1", "paths": {}},
    }


def _enable_superpowers_stages(contract: dict[str, Any]) -> dict[str, Any]:
    payload = dict(contract)
    payload["required_outputs"] = [
        {"name": "task_plan.md", "type": "report", "acceptance": "plan reviewed and approved"},
        {"name": "patch.diff", "type": "patch", "acceptance": "produce audited patch"},
    ]
    payload["handoff_chain"] = {
        "enabled": True,
        "roles": ["TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"],
        "max_handoffs": 4,
    }
    payload["acceptance_tests"] = [
        {
            "name": "gate-check",
            "cmd": "pytest -q apps/orchestrator/tests/test_p1_superpowers_gate.py -k validator",
            "must_pass": True,
        }
    ]
    return payload


def test_evaluate_superpowers_gate_machine_readable_violation() -> None:
    decision = evaluate_superpowers_gate(_contract_base())
    assert decision["required"] is True
    assert decision["ok"] is False
    assert decision["stages"]["spec"]["ok"] is True
    codes = {item["code"] for item in decision["violations"]}
    assert {"missing_plan_evidence", "invalid_handoff_chain", "missing_reviewer_stage", "missing_test_stage"} <= codes


def test_validator_rejects_superpowers_gate_violation() -> None:
    validator = ContractValidator()
    with pytest.raises(ValueError, match="superpowers gate violation"):
        validator.validate_contract(_contract_base())


def test_validator_accepts_superpowers_gate_complete_contract() -> None:
    validator = ContractValidator()
    validated = validator.validate_contract(_enable_superpowers_stages(_contract_base()))
    assert validated["task_id"] == "task-superpowers-01"


def test_task_execution_pipeline_rejects_superpowers_gate_before_runner(monkeypatch) -> None:
    store = _DummyStore()
    runtime_called = {"value": False}

    def _runtime_should_not_run(**_: Any) -> dict[str, Any]:
        runtime_called["value"] = True
        return {}

    monkeypatch.setattr(
        task_execution_pipeline.task_execution_runtime_helpers,
        "run_runner_fix_review_flow_runtime",
        _runtime_should_not_run,
    )

    result = task_execution_pipeline.run_runner_fix_review_flow(
        run_id="run-superpowers-fail",
        task_id="task-superpowers-01",
        store=store,
        contract=_contract_base(),
        worktree_path=Path.cwd(),
        allowed_paths=["apps/orchestrator/src/cortexpilot_orch/contract/validator.py"],
        baseline_ref="HEAD",
        mock_mode=True,
        policy_pack="low",
        network_policy="deny",
        runner_name="codex",
        mcp_only=False,
        profile="default",
        assigned_agent={"role": "WORKER", "agent_id": "agent-1"},
        repo_root=Path.cwd(),
        reviewer=object(),
        start_ts="2026-02-14T00:00:00Z",
        attempt=0,
    )

    assert runtime_called["value"] is False
    assert result["ok"] is False
    assert result["failure_reason"] == "superpowers gate violation"
    assert result["superpowers_gate_result"]["required"] is True
    assert result["superpowers_gate_result"]["ok"] is False
    events = [item[1]["event"] for item in store.events]
    assert "SUPERPOWERS_GATE_FAIL" in events
    assert "gate_failed" in events


def test_task_execution_pipeline_passes_superpowers_gate_and_runs_runtime(monkeypatch) -> None:
    store = _DummyStore()
    runtime_called = {"value": False}

    def _runtime_stub(**_: Any) -> dict[str, Any]:
        runtime_called["value"] = True
        return {
            "ok": True,
            "attempt": 1,
            "failure_reason": "",
            "runner_summary": "ok",
            "diff_gate_result": {"ok": True},
            "tests_result": {"ok": True},
            "review_report": {"verdict": "PASS"},
            "task_result": {"status": "SUCCESS"},
            "test_report": {"status": "PASS"},
            "review_gate_result": {"ok": True},
            "head_ref": "HEAD",
        }

    monkeypatch.setattr(
        task_execution_pipeline.task_execution_runtime_helpers,
        "run_runner_fix_review_flow_runtime",
        _runtime_stub,
    )

    result = task_execution_pipeline.run_runner_fix_review_flow(
        run_id="run-superpowers-pass",
        task_id="task-superpowers-01",
        store=store,
        contract=_enable_superpowers_stages(_contract_base()),
        worktree_path=Path.cwd(),
        allowed_paths=["apps/orchestrator/src/cortexpilot_orch/contract/validator.py"],
        baseline_ref="HEAD",
        mock_mode=True,
        policy_pack="low",
        network_policy="deny",
        runner_name="codex",
        mcp_only=False,
        profile="default",
        assigned_agent={"role": "WORKER", "agent_id": "agent-1"},
        repo_root=Path.cwd(),
        reviewer=object(),
        start_ts="2026-02-14T00:00:00Z",
        attempt=1,
    )

    assert runtime_called["value"] is True
    assert result["ok"] is True
    assert result["superpowers_gate_result"]["required"] is True
    assert result["superpowers_gate_result"]["ok"] is True
    events = [item[1]["event"] for item in store.events]
    assert "SUPERPOWERS_GATE_PASS" in events
