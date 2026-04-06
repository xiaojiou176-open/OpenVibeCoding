import json
import sys
import types
from pathlib import Path

from cortexpilot_orch.runners import agents_runner

from .test_agents_runner_failure_matrix_extra import (
    _DummyMCPDefault,
    _DummyStreamResult,
    _install_fake_agents_sdk,
    _prepare_runner,
)


def test_agents_runner_shell_deny_policy_violation(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "task_id": "task_shell_deny",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)))
    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_shell_deny")
    contract["tool_permissions"]["shell"] = "deny"

    monkeypatch.setattr(agents_runner, "_contains_shell_request", lambda _snapshot: True)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "shell request detected" in result["summary"]


def test_agents_runner_shell_never_policy_violation(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "task_id": "task_shell_never",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)))
    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_shell_never")
    contract["tool_permissions"]["shell"] = "never"

    monkeypatch.setattr(agents_runner, "_contains_shell_request", lambda _snapshot: True)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "shell request detected" in result["summary"]


def test_agents_runner_handoff_invalid_event_branch(tmp_path: Path, monkeypatch) -> None:
    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_handoff_invalid")
    monkeypatch.setattr(agents_runner.ContractValidator, "validate_contract", lambda self, payload: payload)
    monkeypatch.setattr(agents_runner, "_validate_handoff_chain", lambda _contract: (False, "handoff chain invalid"))

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "handoff chain invalid" in result["summary"]
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_HANDOFF_INVALID" in events_text


def test_agents_runner_mock_readonly_branch(tmp_path: Path, monkeypatch) -> None:
    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_mock_readonly")
    monkeypatch.setattr(agents_runner.ContractValidator, "validate_contract", lambda self, payload: payload)
    monkeypatch.setattr(agents_runner, "_validate_handoff_chain", lambda _contract: (True, ""))
    contract["tool_permissions"]["filesystem"] = "read-only"

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=True)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENTS_MOCK_EVENT" in events_text
    assert "read_only" in events_text


def test_agents_runner_missing_provider_api_key_branch(tmp_path: Path, monkeypatch) -> None:
    class _Cfg:
        openai_api_key = ""
        gemini_api_key = ""
        equilibrium_api_key = ""
        agents_base_url = "https://api.openai.com/v1"
        agents_api = ""
        agents_model = "gpt-test"
        codex_model = "gpt-test"
        agents_store = False

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult("{}"))
    monkeypatch.setattr(agents_runner, "get_runner_config", lambda: _Cfg())
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_missing_key")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "missing LLM API key" in result["summary"]
    assert "API_KEY" in result["summary"] or "API key" in result["summary"]


def test_agents_runner_missing_provider_api_key_no_fallback(tmp_path: Path, monkeypatch) -> None:
    class _Cfg:
        openai_api_key = ""
        gemini_api_key = ""
        equilibrium_api_key = ""
        agents_base_url = ""
        agents_api = ""
        agents_model = "gpt-test"
        codex_model = "gpt-test"
        agents_store = False

    payload = {
        "task_id": "task_local_equilibrium",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)))
    monkeypatch.setattr(agents_runner, "get_runner_config", lambda: _Cfg())
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    probe_calls = {"count": 0}

    def _probe(_base_url: str, timeout_sec: float = 1.0) -> bool:
        del timeout_sec
        probe_calls["count"] += 1
        return True

    monkeypatch.setattr(agents_runner, "_equilibrium_healthcheck", _probe)

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_local_equilibrium")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "missing LLM API key" in result["summary"]
    assert probe_calls["count"] == 0


def test_agents_runner_gemini_client_setup_failed_branch(tmp_path: Path, monkeypatch) -> None:
    class _Cfg:
        openai_api_key = ""
        gemini_api_key = "test-key"
        equilibrium_api_key = ""
        agents_base_url = "https://api.openai.com/v1"
        agents_api = "responses"
        agents_model = "gpt-test"
        codex_model = "gpt-test"
        agents_store = False

    class _Agent:
        def __init__(self, name: str, instructions: str, mcp_servers: list, **kwargs) -> None:
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers
            self.kwargs = kwargs

    class _Runner:
        @staticmethod
        def run_streamed(*_args, **_kwargs):
            return _DummyStreamResult("{}")

    class _RunConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _ModelSettings:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = _Agent
    agents_mod.Runner = _Runner
    agents_mod.RunConfig = _RunConfig
    agents_mod.ModelSettings = _ModelSettings
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = lambda *_args, **_kwargs: None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = _DummyMCPDefault

    class _BrokenAsyncOpenAI:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("client init failed")

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = _BrokenAsyncOpenAI

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setattr(agents_runner, "get_runner_config", lambda: _Cfg())

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_client_setup_fail")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "agents sdk client setup failed" in result["summary"]


def test_agents_runner_shell_deny_without_request_still_succeeds(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "task_id": "task_shell_deny_ok",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)))
    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_shell_deny_ok")
    contract["tool_permissions"]["shell"] = "deny"
    monkeypatch.setattr(agents_runner, "_contains_shell_request", lambda _snapshot: False)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"


def test_agents_runner_empty_string_output_branch(tmp_path: Path, monkeypatch) -> None:
    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult("   "))
    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_empty_output")

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "missing output" in result["summary"]


def test_agents_runner_structured_output_text_nested_json_and_thread_event(tmp_path: Path, monkeypatch) -> None:
    nested_payload = {
        "task_id": "task_structured_nested",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    final_output = {"text": json.dumps(nested_payload, ensure_ascii=False)}

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(final_output))
    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_structured_nested")

    monkeypatch.setattr(
        agents_runner,
        "_extract_structured_content",
        lambda _snapshot: {"threadId": " thread-structured-1 "},
    )
    monkeypatch.setattr(agents_runner, "_extract_thread_id", lambda _snapshot: None)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_TOOL_RESULT" in events_text
    assert "thread-structured-1" in events_text
