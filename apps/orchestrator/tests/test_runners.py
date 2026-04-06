import hashlib
import json
import os
from pathlib import Path

from cortexpilot_orch.runners import app_server_runner as app_server_module
from cortexpilot_orch.runners import codex_runner as codex_module
from cortexpilot_orch.runners.app_server_runner import AppServerRunner
from cortexpilot_orch.runners.codex_runner import CodexRunner
from cortexpilot_orch.store.run_store import RunStore


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract() -> dict:
    return {
        "task_id": "task_mock_01",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_mock_runner_success(tmp_path: Path, monkeypatch):
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_mock")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    schema_root = tmp_path
    schema_path = schema_root / "task_result.v1.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": [
                    "task_id",
                    "status",
                    "summary",
                ],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    contract_schema = schema_root / "task_contract.v1.json"
    contract_schema.write_text(
        json.dumps({"type": "object", "additionalProperties": True}),
        encoding="utf-8",
    )

    class _NoopValidator:
        def __init__(self, schema_root: Path | None = None) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    monkeypatch.setattr(codex_module, "ContractValidator", _NoopValidator)

    contract = _base_contract()
    runner = CodexRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=True)

    assert result["status"] == "SUCCESS"
    assert (worktree / "mock_output.txt").exists()

    events_path = tmp_path / run_id / "events.jsonl"
    events_text = events_path.read_text(encoding="utf-8")
    assert "CODEX_MOCK_EVENT" in events_text


def test_app_server_mock_runner_success(tmp_path: Path, monkeypatch):
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_app_server_mock")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    schema_root = tmp_path
    schema_path = schema_root / "task_result.v1.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": [
                    "task_id",
                    "status",
                    "summary",
                ],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    contract_schema = schema_root / "task_contract.v1.json"
    contract_schema.write_text(
        json.dumps({"type": "object", "additionalProperties": True}),
        encoding="utf-8",
    )

    class _NoopValidator:
        def __init__(self, schema_root: Path | None = None) -> None:
            self.schema_root = schema_root

        def validate_contract(self, contract: dict) -> None:
            return None

    monkeypatch.setattr(app_server_module, "ContractValidator", _NoopValidator)

    contract = _base_contract()
    runner = AppServerRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=True)

    assert result["status"] == "SUCCESS"
    assert (worktree / "mock_output.txt").exists()

    events_path = tmp_path / run_id / "events.jsonl"
    events_text = events_path.read_text(encoding="utf-8")
    assert "APP_SERVER_MOCK_EVENT" in events_text


def test_runner_missing_instruction_fails(tmp_path: Path, monkeypatch):
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_fail")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    schema_root = tmp_path
    schema_path = schema_root / "task_result.v1.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": [
                    "task_id",
                    "status",
                    "summary",
                ],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    contract_schema = schema_root / "task_contract.v1.json"
    contract_schema.write_text(
        json.dumps({"type": "object", "additionalProperties": True}),
        encoding="utf-8",
    )

    contract = _base_contract()
    contract["inputs"] = {"spec": "", "artifacts": _output_schema_artifacts("worker")}

    runner = CodexRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "missing instruction" in result["summary"]


def test_runner_mcp_tools_denied(tmp_path: Path, monkeypatch):
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_denied")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    schema_root = tmp_path
    schema_path = schema_root / "task_result.v1.json"
    schema_path.write_text(
        json.dumps(
            {
                "type": "object",
                "required": [
                    "task_id",
                    "status",
                    "summary",
                ],
                "properties": {"task_id": {"type": "string"}},
                "additionalProperties": True,
            }
        ),
        encoding="utf-8",
    )
    contract_schema = schema_root / "task_contract.v1.json"
    contract_schema.write_text(
        json.dumps({"type": "object", "additionalProperties": True}),
        encoding="utf-8",
    )

    contract = _base_contract()
    contract["tool_permissions"]["mcp_tools"] = []

    runner = CodexRunner(store)
    result = runner.run_contract(contract, worktree, schema_path, mock_mode=True)

    assert result["status"] == "FAILED"
    assert "codex mcp tool not allowed" in result["summary"]
