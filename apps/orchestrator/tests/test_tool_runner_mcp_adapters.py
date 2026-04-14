from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openvibecoding_orch.runners.tool_runner import ToolRunner
from openvibecoding_orch.store.run_store import RunStore


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


def _write_active_contract(store: RunStore, run_id: str, mcp_tools: list[str], monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(store._runs_root.parent))
    contract = {
        "task_id": "adapter_task",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "owner"},
        "assigned_agent": {"role": "WORKER", "agent_id": "worker"},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "patch", "type": "patch", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": ["rm -rf"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": mcp_tools,
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "worktree_drop", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": run_id, "paths": {}},
    }
    store.write_active_contract(run_id, contract)


def _read_events(tmp_path: Path, run_id: str) -> list[dict]:
    events_path = tmp_path / run_id / "events.jsonl"
    return [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _first_event(events: list[dict], event_name: str) -> dict:
    for entry in events:
        if entry.get("event") == event_name:
            return entry
    raise AssertionError(f"missing event: {event_name}")


def test_tool_runner_adapter_denied_when_not_allowed(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_adapter_denied")
    _write_active_contract(store, run_id, ["sampling"], monkeypatch)

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("aider", {"prompt": "hello"})
    assert result["ok"] is False
    assert result["error"] == "mcp tool not allowed"
    assert result["reason"] == "tool not allowed"

    events = _read_events(tmp_path, run_id)
    denied_event = _first_event(events, "MCP_TOOL_DENIED")
    assert denied_event.get("meta", {}).get("tool") == "aider"
    assert denied_event.get("meta", {}).get("task_id") == "adapter_task"
    assert denied_event.get("meta", {}).get("denied_reason") == "tool not allowed"


def test_tool_runner_adapter_allowed_success(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_adapter_allowed_success")
    _write_active_contract(store, run_id, ["aider"], monkeypatch)
    captured: dict[str, object] = {}

    def _record(call_run_id: str, tool_name: str, payload: dict[str, object]) -> None:
        captured["run_id"] = call_run_id
        captured["tool_name"] = tool_name
        captured["payload"] = payload

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.mcp_adapter.record_mcp_call", _record)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.tool_runner.execute_mcp_adapter",
        lambda *_args, **_kwargs: {
            "ok": True,
            "adapter": "aider",
            "command": "aider",
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 1,
        },
    )

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("aider", {"prompt": "ship it"})
    assert result["ok"] is True
    assert result["adapter"] == "aider"
    assert captured["run_id"] == run_id
    assert captured["tool_name"] == "aider"
    assert captured["payload"] == {"prompt": "ship it"}

    events = _read_events(tmp_path, run_id)
    used_event = _first_event(events, "TOOL_USED")
    assert used_event.get("meta", {}).get("tool") == "mcp"
    assert used_event.get("meta", {}).get("task_id") == "adapter_task"


def test_tool_runner_adapter_allowed_execution_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_adapter_allowed_failure")
    _write_active_contract(store, run_id, ["aider"], monkeypatch)

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.mcp_adapter.record_mcp_call", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.tool_runner.execute_mcp_adapter",
        lambda *_args, **_kwargs: {
            "ok": False,
            "adapter": "aider",
            "command": "aider",
            "exit_code": 2,
            "stdout": "",
            "stderr": "adapter bridge down",
            "error": "adapter bridge down",
            "reason": "adapter bridge down",
            "duration_ms": 1,
        },
    )

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("aider", {"prompt": "retry"})
    assert result["ok"] is False
    assert result["error"] == "adapter bridge down"
    assert result["reason"] == "adapter bridge down"

    events = _read_events(tmp_path, run_id)
    failure_event = _first_event(events, "TOOL_FAILURE")
    assert failure_event.get("meta", {}).get("tool") == "mcp"
    assert failure_event.get("meta", {}).get("task_id") == "adapter_task"


def test_tool_runner_adapter_alias_allowed_with_canonical_permission(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_adapter_alias_allowed")
    _write_active_contract(store, run_id, ["open_interpreter"], monkeypatch)
    captured: dict[str, object] = {}

    def _record(call_run_id: str, tool_name: str, payload: dict[str, object]) -> None:
        captured["run_id"] = call_run_id
        captured["tool_name"] = tool_name
        captured["payload"] = payload

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.mcp_adapter.record_mcp_call", _record)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.tool_runner.execute_mcp_adapter",
        lambda *_args, **_kwargs: {
            "ok": True,
            "adapter": "open_interpreter",
            "command": "open-interpreter",
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 1,
        },
    )

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("open-interpreter", {"prompt": "ship it"})
    assert result["ok"] is True
    assert result["adapter"] == "open_interpreter"
    assert captured["run_id"] == run_id
    assert captured["tool_name"] == "open_interpreter"
    assert captured["payload"] == {"prompt": "ship it"}


def test_tool_runner_non_adapter_tool_fails_closed(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("run_non_adapter_fail_closed")
    _write_active_contract(store, run_id, ["codex"], monkeypatch)

    monkeypatch.setattr("openvibecoding_orch.runners.tool_runner.mcp_adapter.record_mcp_call", lambda *_args, **_kwargs: None)

    runner = ToolRunner(run_id, store)
    result = runner.run_mcp("codex", {"payload": {}})

    assert result["ok"] is False
    assert result["reason"] == "non-adapter mcp execution is not supported"
    assert result["error"] == "non-adapter mcp execution is not supported"

    events = _read_events(tmp_path, run_id)
    unavailable_event = _first_event(events, "MCP_TOOL_EXECUTION_UNAVAILABLE")
    assert unavailable_event.get("meta", {}).get("tool") == "codex"
    assert unavailable_event.get("meta", {}).get("task_id") == "adapter_task"
