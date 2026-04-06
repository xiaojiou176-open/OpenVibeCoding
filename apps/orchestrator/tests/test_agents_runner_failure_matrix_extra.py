import asyncio
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from cortexpilot_orch.runners import agents_runner
from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.store.run_store import RunStore


class _DummyRunConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _DummyModelSettings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class _DummyStreamResult:
    def __init__(self, final_output, events: list[object] | None = None) -> None:
        self.final_output = final_output
        self._events = events or []
        self._done = False

    async def stream_events(self):
        for event in self._events:
            yield event
        self._done = True

    def cancel(self, mode: str = "immediate") -> None:
        del mode
        self._done = True

    @property
    def is_complete(self) -> bool:
        return self._done


class _IdleStreamResult:
    def __init__(self) -> None:
        self.final_output = json.dumps(
            {
                "task_id": "task_idle_timeout",
                "status": "SUCCESS",
                "summary": "ok",
                "evidence_refs": {},
                "failure": None,
            },
            ensure_ascii=False,
        )
        self._done = False

    async def stream_events(self):
        yield types.SimpleNamespace(type="run_item_stream_event", name="noop", item=None)
        await asyncio.sleep(1.2)

    def cancel(self, mode: str = "immediate") -> None:
        del mode
        self._done = True

    @property
    def is_complete(self) -> bool:
        return self._done


class _DummyMCPDefault:
    def __init__(self, params=None, client_session_timeout_seconds=None, errlog_path=None, message_handler=None, **kwargs) -> None:
        del client_session_timeout_seconds, kwargs
        self.params = params
        self.errlog_path = errlog_path
        self.message_handler = message_handler

    async def connect(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    async def list_tools(self):
        return []


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract(task_id: str, spec: str = "mock") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": spec, "artifacts": _output_schema_artifacts("worker")},
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


def _install_fake_agents_sdk(monkeypatch, runner_cb, mcp_cls=_DummyMCPDefault, strict_agent_ctor: bool = False) -> None:
    if strict_agent_ctor:
        class _Agent:
            def __init__(self, name: str, instructions: str, mcp_servers: list):
                self.name = name
                self.instructions = instructions
                self.mcp_servers = mcp_servers
    else:
        class _Agent:
            def __init__(self, name: str, instructions: str, mcp_servers: list, **kwargs):
                self.name = name
                self.instructions = instructions
                self.mcp_servers = mcp_servers
                self.kwargs = kwargs

    class _Runner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            return runner_cb(agent, prompt, **kwargs)

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = _Agent
    agents_mod.Runner = _Runner
    agents_mod.RunConfig = _DummyRunConfig
    agents_mod.ModelSettings = _DummyModelSettings
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = mcp_cls

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)


def _prepare_runner(tmp_path: Path, monkeypatch, task_id: str) -> tuple[AgentsRunner, Path, dict, str]:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run(task_id)
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    runner = AgentsRunner(store)
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    contract = _base_contract(task_id)
    return runner, schema_path, contract, run_id


@pytest.mark.parametrize(
    ("task_id", "final_output", "summary_keyword"),
    [
        ("task_missing_output", None, "missing output"),
        ("task_not_json", "not-json", "output not json"),
        ("task_not_object", "[]", "output not object"),
    ],
)
def test_agents_runner_output_failure_matrix(tmp_path: Path, monkeypatch, task_id: str, final_output, summary_keyword: str) -> None:
    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(final_output))
    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, task_id)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert summary_keyword in result["summary"]


def test_agents_runner_output_schema_validation_failure(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "task_id": "task_schema_invalid",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)))

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_schema_invalid")

    original_validate = agents_runner.ContractValidator.validate_report

    def _raise_validate(self, report, schema_name: str):
        if schema_name == "agent_task_result.v1.json":
            raise RuntimeError("forced schema invalid")
        return original_validate(self, report, schema_name)

    monkeypatch.setattr(agents_runner.ContractValidator, "validate_report", _raise_validate)

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "output invalid" in result["summary"]


def test_agents_runner_probe_error_and_agent_fallback(tmp_path: Path, monkeypatch) -> None:
    class _MCPListToolsError(_DummyMCPDefault):
        async def list_tools(self):
            raise RuntimeError("list tools failed")

    payload = {
        "task_id": "task_probe_error",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(
        monkeypatch,
        lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)),
        mcp_cls=_MCPListToolsError,
        strict_agent_ctor=True,
    )

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_probe_error")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert result["summary"] == "agents sdk execution failed"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_READY_PROBE_FAILED" in events_text
    assert "MCP_READY_PROBE_OK" not in events_text


def test_agents_runner_context_manager_cleanup_timeout(tmp_path: Path, monkeypatch) -> None:
    class _MCPContextManager:
        def __init__(self, params=None, client_session_timeout_seconds=None, errlog_path=None, message_handler=None, **kwargs) -> None:
            del client_session_timeout_seconds, errlog_path, message_handler, kwargs
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            await asyncio.sleep(0.03)
            return False

        async def list_tools(self):
            return []

    payload = {
        "task_id": "task_cleanup_timeout",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(
        monkeypatch,
        lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)),
        mcp_cls=_MCPContextManager,
    )
    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "worker")
    monkeypatch.setenv("CORTEXPILOT_MCP_CONNECT_TIMEOUT_SEC", "0")
    monkeypatch.setenv("CORTEXPILOT_MCP_CLEANUP_TIMEOUT_SEC", "0.001")

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_cleanup_timeout")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_SERVER_CLOSED" in events_text
    assert "--profile" in events_text


def test_agents_runner_connect_without_timeout_branch(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "task_id": "task_connect_no_timeout",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(
        monkeypatch,
        lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)),
        mcp_cls=_DummyMCPDefault,
    )
    monkeypatch.setenv("CORTEXPILOT_MCP_CONNECT_TIMEOUT_SEC", "0")

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_connect_no_timeout")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"


def test_agents_runner_context_manager_direct_exit_without_timeout_branch(tmp_path: Path, monkeypatch) -> None:
    class _MCPContextManagerNoTimeout:
        def __init__(self, params=None, client_session_timeout_seconds=None, errlog_path=None, message_handler=None, **kwargs) -> None:
            del client_session_timeout_seconds, errlog_path, message_handler, kwargs
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def list_tools(self):
            return []

    payload = {
        "task_id": "task_context_no_timeout",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }

    _install_fake_agents_sdk(
        monkeypatch,
        lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)),
        mcp_cls=_MCPContextManagerNoTimeout,
    )
    monkeypatch.setenv("CORTEXPILOT_MCP_CONNECT_TIMEOUT_SEC", "0")
    monkeypatch.setenv("CORTEXPILOT_MCP_CLEANUP_TIMEOUT_SEC", "0")

    runner, schema_path, contract, _ = _prepare_runner(tmp_path, monkeypatch, "task_context_no_timeout")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"


def test_agents_runner_stream_idle_timeout_branch(tmp_path: Path, monkeypatch) -> None:
    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _IdleStreamResult())
    # Use a realistic-but-stable idle timeout for loaded CI workers.
    monkeypatch.setenv("CORTEXPILOT_STREAM_IDLE_TIMEOUT_SEC", "0.3")
    monkeypatch.setenv("CORTEXPILOT_CODEX_TIMEBOX_SEC", "")

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_idle_timeout")
    contract["timeout_retry"]["timeout_sec"] = 5
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "execution failed" in result["summary"]
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_STREAM_IDLE_TIMEOUT" in events_text


def test_agents_runner_tool_timeout_branch(tmp_path: Path, monkeypatch) -> None:
    class _ToolCalledEvent:
        def __init__(self) -> None:
            self.type = "run_item_stream_event"
            self.name = "tool_called"
            self.item = types.SimpleNamespace(raw_item={"name": "fs.read", "call_id": "c-timeout"})

    class _ToolTimeoutResult:
        def __init__(self) -> None:
            self.final_output = json.dumps(
                {
                    "task_id": "task_tool_timeout",
                    "status": "SUCCESS",
                    "summary": "ok",
                    "evidence_refs": {},
                    "failure": None,
                },
                ensure_ascii=False,
            )
            self._cancelled = False

        async def stream_events(self):
            yield _ToolCalledEvent()
            while not self._cancelled:
                await asyncio.sleep(0.5)

        def cancel(self, mode: str = "immediate") -> None:
            del mode
            self._cancelled = True

        @property
        def is_complete(self) -> bool:
            return self._cancelled

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _ToolTimeoutResult())
    monkeypatch.setenv("CORTEXPILOT_MCP_TOOL_TIMEOUT_SEC", "0.2")

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_tool_timeout")
    contract["timeout_retry"]["timeout_sec"] = 3

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_TOOL_CALL_TIMEOUT" in events_text


def test_agents_runner_broken_pipe_branch(tmp_path: Path, monkeypatch) -> None:
    class _BrokenPipeMCP(_DummyMCPDefault):
        async def connect(self) -> None:
            if self.errlog_path is not None:
                self.errlog_path.parent.mkdir(parents=True, exist_ok=True)
                self.errlog_path.write_text("broken pipe\n", encoding="utf-8")

    class _BlockingResult:
        def __init__(self) -> None:
            self.final_output = json.dumps(
                {
                    "task_id": "task_broken_pipe",
                    "status": "SUCCESS",
                    "summary": "ok",
                    "evidence_refs": {},
                    "failure": None,
                },
                ensure_ascii=False,
            )
            self._cancelled = False

        async def stream_events(self):
            yield types.SimpleNamespace(type="run_item_stream_event", name="heartbeat", item=None)
            while not self._cancelled:
                await asyncio.sleep(0.5)
                yield types.SimpleNamespace(type="run_item_stream_event", name="heartbeat", item=None)

        def cancel(self, mode: str = "immediate") -> None:
            del mode
            self._cancelled = True

        @property
        def is_complete(self) -> bool:
            return self._cancelled

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: _BlockingResult(), mcp_cls=_BrokenPipeMCP)
    monkeypatch.setenv("CORTEXPILOT_MCP_BROKEN_PIPE_FAIL", "1")

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_broken_pipe")
    contract["timeout_retry"]["timeout_sec"] = 1

    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert ("MCP_SERVER_BROKEN_PIPE" in events_text) or ("MCP_STREAM_TIMEOUT" in events_text)


def test_agents_runner_cleanup_timeout_branch(tmp_path: Path, monkeypatch) -> None:
    class _SlowCleanupMCP(_DummyMCPDefault):
        async def cleanup(self) -> None:
            await asyncio.sleep(0.03)

    payload = {
        "task_id": "task_cleanup_timeout_real",
        "status": "SUCCESS",
        "summary": "ok",
        "evidence_refs": {},
        "failure": None,
    }
    _install_fake_agents_sdk(
        monkeypatch,
        lambda *_args, **_kwargs: _DummyStreamResult(json.dumps(payload, ensure_ascii=False)),
        mcp_cls=_SlowCleanupMCP,
    )
    monkeypatch.setenv("CORTEXPILOT_MCP_CLEANUP_TIMEOUT_SEC", "0.001")

    runner, schema_path, contract, run_id = _prepare_runner(tmp_path, monkeypatch, "task_cleanup_timeout_real")
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_SERVER_CLEANUP_TIMEOUT" in events_text
