from pathlib import Path

from cortexpilot_orch.runners.agents_runner import (
    AgentsRunner,
    _build_codex_payload,
    _extract_binding_from_result,
    _resolve_session_binding,
)
from cortexpilot_orch.runners.codex_runner import (
    CodexRunner,
    _codex_allowed,
    _codex_flags,
    _extract_session_id,
    _extract_thread_id,
)
from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.store.session_map import SessionAliasStore

from .test_agents_and_codex_runner_detailed import _base_contract


def test_agents_runner_helpers(tmp_path: Path, monkeypatch) -> None:
    contract = _base_contract("task_helper")
    payload = _build_codex_payload(contract, "do it", tmp_path)
    assert payload["prompt"] == "do it"
    assert payload["cwd"] == str(tmp_path)
    assert payload["sandbox"] == "workspace-write"
    assert payload["approval-policy"] == "on-request"

    alias_path = tmp_path / "alias_map.json"
    monkeypatch.setenv("CORTEXPILOT_SESSION_ALIAS_PATH", str(alias_path))
    store = SessionAliasStore()
    store.set_alias("agent-1", "session-x", thread_id="thread-x", note="seed")
    thread_id, session_id = _resolve_session_binding(contract)
    assert thread_id == "thread-x"
    assert session_id == "session-x"

    bound_thread, bound_session = _extract_binding_from_result({"evidence_refs": {"thread_id": "t1", "session_id": "s1"}})
    assert bound_thread == "t1"
    assert bound_session == "s1"


def test_codex_runner_helpers() -> None:
    contract = _base_contract("task_flags")
    flags = _codex_flags(contract)
    assert "--sandbox" in flags
    assert "--ask-for-approval" not in flags
    assert _codex_allowed(contract) is True
    assert _codex_allowed({"tool_permissions": {"mcp_tools": []}}) is False

    payload = {"payload": {"threadId": "t2", "sessionId": "s2"}}
    assert _extract_thread_id(payload) == "t2"
    assert _extract_session_id(payload) == "s2"


def test_agents_runner_missing_instruction(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_missing_instruction")
    contract = _base_contract("task_missing_instruction")
    contract["inputs"]["spec"] = ""
    contract.pop("instruction", None)
    contract.pop("objective", None)
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path, tmp_path / "missing.json", mock_mode=True)
    assert result["status"] == "FAILED"
    assert "missing instruction" in result["summary"]


def test_agents_runner_codex_not_allowed(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_denied")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    contract = _base_contract("task_codex_denied")
    contract["tool_permissions"]["mcp_tools"] = []
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path, tmp_path / "missing.json", mock_mode=True)
    assert result["status"] == "FAILED"
    assert "codex mcp tool not allowed" in result["summary"]
    events = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_TOOL_DENIED" in events


def test_agents_runner_schema_missing(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_schema_missing")
    runner = AgentsRunner(store)
    result = runner.run_contract(_base_contract("task_schema_missing"), tmp_path, tmp_path / "nope.json", mock_mode=False)
    assert result["status"] == "FAILED"
    assert "schema path missing" in result["summary"]


def test_agents_runner_contract_invalid(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_contract_invalid")
    contract = _base_contract("task_contract_invalid")
    contract["allowed_paths"] = []
    runner = AgentsRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    result = runner.run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "contract schema validation failed" in result["summary"]


def test_agents_runner_mock_result_schema_invalid(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_mock_invalid")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    runner = AgentsRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    result = runner.run_contract(_base_contract("task_mock_invalid"), tmp_path, schema_path, mock_mode=True)
    assert result["status"] == "SUCCESS"


def test_codex_runner_missing_instruction_and_denied(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_missing_instruction")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    contract = _base_contract("task_codex_missing_instruction")
    contract["inputs"]["spec"] = ""
    runner = CodexRunner(store)
    result = runner.run_contract(contract, tmp_path, tmp_path / "schemas" / "task_result.v1.json", mock_mode=True)
    assert result["status"] == "FAILED"
    assert "missing instruction" in result["summary"]

    contract = _base_contract("task_codex_denied")
    contract["tool_permissions"]["mcp_tools"] = []
    result = runner.run_contract(contract, tmp_path, tmp_path / "schemas" / "task_result.v1.json", mock_mode=True)
    assert result["status"] == "FAILED"
    assert "codex mcp tool not allowed" in result["summary"]


def test_codex_runner_schema_missing_and_contract_invalid(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_schema_missing")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    runner = CodexRunner(store)

    result = runner.run_contract(_base_contract("task_codex_schema_missing"), tmp_path, tmp_path / "nope.json", mock_mode=False)
    assert result["status"] == "FAILED"
    assert "schema path missing" in result["summary"]

    bad_contract = _base_contract("task_codex_invalid_contract")
    bad_contract["allowed_paths"] = []
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    result = runner.run_contract(bad_contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "contract schema validation failed" in result["summary"]


def test_codex_runner_mock_result_schema_invalid(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_codex_mock_invalid")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    runner = CodexRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    result = runner.run_contract(_base_contract("task_codex_mock_invalid"), tmp_path, schema_path, mock_mode=True)
    assert result["status"] == "SUCCESS"
