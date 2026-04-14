import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from openvibecoding_orch.runners.agents_runner import AgentsRunner
from openvibecoding_orch.store.run_store import RunStore


class DummyRunConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyModelSettings:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class DummyStreamResult:
    def __init__(self, text: str | None, events: list[object] | None = None) -> None:
        self.final_output = text
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


class DummyTool:
    def __init__(self, name: str) -> None:
        self.name = name


class DummyMCPDefault:
    def __init__(
        self,
        params=None,
        client_session_timeout_seconds=None,
        errlog_path=None,
        message_handler=None,
        **kwargs,
    ) -> None:
        del client_session_timeout_seconds, errlog_path, kwargs
        self.params = params
        self._message_handler = message_handler

    async def connect(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    async def list_tools(self):
        return [DummyTool("fs.read")]


class StreamItem:
    def __init__(self, raw_item: dict) -> None:
        self.raw_item = raw_item
        self.type = "function_call"


class StreamEvent:
    def __init__(self, name: str, raw_item: dict) -> None:
        self.type = "run_item_stream_event"
        self.name = name
        self.item = StreamItem(raw_item)


class DumpMessage:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


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


def _install_fake_agents_sdk(monkeypatch, runner_cb, mcp_cls=DummyMCPDefault, run_cb=None) -> None:
    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list, **kwargs):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers
            self.kwargs = kwargs

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            return runner_cb(agent, prompt, **kwargs)

        @staticmethod
        def run(agent, prompt, **kwargs):
            if callable(run_cb):
                return run_cb(agent, prompt, **kwargs)
            raise RuntimeError("run() not implemented in fake sdk")

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.Runner = DummyRunner
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = mcp_cls

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)


def test_stream_timeout_fallback_to_runner_run(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_stream_timeout_fallback")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_AGENTS_STREAM_TIMEOUT_FALLBACK", "true")

    class TimeoutStreamResult:
        final_output = None

        async def stream_events(self):
            yield type("E", (), {"type": "agent_updated_stream_event"})()
            raise RuntimeError("Request timed out.")

    def _runner_cb(_agent, _prompt, **_kwargs):
        return TimeoutStreamResult()

    def _run_cb(_agent, _prompt, **_kwargs):
        payload = {
            "task_id": "task_stream_timeout_fallback",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {"thread_id": "thread-fallback"},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload))

    _install_fake_agents_sdk(monkeypatch, _runner_cb, run_cb=_run_cb)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_stream_timeout_fallback")
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENTS_STREAM_TIMEOUT_FALLBACK" in events_text


def test_stream_timeout_retry_then_success_without_fallback(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_stream_timeout_retry_success")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_AGENTS_STREAM_TIMEOUT_FALLBACK", "false")
    monkeypatch.setenv("OPENVIBECODING_AGENTS_STREAM_TIMEOUT_RETRIES", "2")
    monkeypatch.setenv("OPENVIBECODING_AGENTS_STREAM_RETRY_BACKOFF_SEC", "0.001")

    call_counter = {"count": 0}

    class TimeoutStreamResult:
        final_output = None

        async def stream_events(self):
            yield type("E", (), {"type": "agent_updated_stream_event"})()
            raise RuntimeError("Request timed out.")

    def _runner_cb(_agent, _prompt, **_kwargs):
        call_counter["count"] += 1
        if call_counter["count"] < 3:
            return TimeoutStreamResult()
        payload = {
            "task_id": "task_stream_timeout_retry_success",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {"thread_id": "thread-retry-ok"},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload))

    _install_fake_agents_sdk(monkeypatch, _runner_cb)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_stream_timeout_retry_success")
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    assert call_counter["count"] == 3
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENTS_STREAM_TIMEOUT_RETRY" in events_text


def test_handoff_chain_max_handoffs_guard(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_chain_guard")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: DummyStreamResult("{}"))

    contract = _base_contract("task_chain_guard")
    contract["owner_agent"]["role"] = "PM"
    contract["assigned_agent"]["role"] = "WORKER"
    contract["handoff_chain"] = {
        "enabled": True,
        "roles": ["PM", "TECH_LEAD", "WORKER"],
        "max_handoffs": 1,
    }

    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "max_handoffs" in result["summary"]


def test_handoff_chain_invalid_payload_fails(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_chain_invalid_payload")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def _runner_cb(agent, _prompt, **_kwargs):
        if agent.name.startswith("OpenVibeCodingHandoff_"):
            return DummyStreamResult(json.dumps({"summary": "missing instruction"}))
        return DummyStreamResult(json.dumps({"task_id": "x", "status": "SUCCESS", "summary": "ok", "evidence_refs": {}, "failure": None}))

    _install_fake_agents_sdk(monkeypatch, _runner_cb)

    contract = _base_contract("task_chain_invalid_payload")
    contract["owner_agent"]["role"] = "PM"
    contract["assigned_agent"]["role"] = "WORKER"
    contract["handoff_chain"] = {
        "enabled": True,
        "roles": ["PM", "TECH_LEAD", "WORKER"],
        "max_handoffs": 3,
    }

    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "handoff failed" in result["summary"]


def test_fixed_output_invalid_when_tool_set_disabled(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_fixed_invalid")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    _install_fake_agents_sdk(monkeypatch, lambda *_args, **_kwargs: DummyStreamResult("{}"))

    contract = _base_contract("task_fixed_invalid", spec="RETURN EXACTLY THIS JSON BUT PAYLOAD IS MISSING")
    contract["mcp_tool_set"] = ["none"]

    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "fixed output json missing" in result["summary"]


def test_stream_and_message_handler_success_path(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_stream_success")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_STREAM_LOG_EVERY", "1")
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_URL", "http://127.0.0.1:1456/v1")

    class DummyMCPWithMessages(DummyMCPDefault):
        async def connect(self) -> None:
            if self._message_handler is not None:
                await self._message_handler(
                    DumpMessage(
                        {
                            "method": "codex/event",
                            "params": {
                                "msg": {
                                    "type": "mcp_tool_call_begin",
                                    "invocation": {
                                        "tool": "read",
                                        "server": "fs",
                                        "arguments": {"path": "README.md"},
                                    },
                                    "call_id": "call-1",
                                }
                            },
                        }
                    )
                )
                await self._message_handler(
                    DumpMessage(
                        {
                            "method": "codex/event",
                            "params": {
                                "msg": {
                                    "type": "mcp_tool_call_end",
                                    "invocation": {
                                        "tool": "read",
                                        "server": "fs",
                                        "arguments": {"path": "README.md"},
                                    },
                                    "call_id": "call-1",
                                    "result": {"Ok": {"content": ["ok"]}},
                                }
                            },
                        }
                    )
                )

    stream_events = [
        StreamEvent("tool_called", {"name": "codex", "call_id": "c-1"}),
        StreamEvent("tool_output", {"name": "codex", "call_id": "c-1", "result": {"Ok": {"content": ["x"]}}}),
    ]

    def _runner_cb(_agent, _prompt, **_kwargs):
        payload = {
            "task_id": "task_stream_success",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {"thread_id": "thread-stream", "session_id": "session-stream"},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload), events=stream_events)

    _install_fake_agents_sdk(monkeypatch, _runner_cb, mcp_cls=DummyMCPWithMessages)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_stream_success")
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    assert result["evidence_refs"]["thread_id"] == "thread-stream"

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_TOOL_CALL_STARTED" in events_text
    assert "MCP_STREAM_ITEM" in events_text
    assert "MCP_EVENT_ROUTED" in events_text

    mcp_stdout = tmp_path / run_id / "codex" / "task_stream_success" / "mcp_stdout.jsonl"
    assert mcp_stdout.exists()
    assert "codex/event" in mcp_stdout.read_text(encoding="utf-8")


def test_mcp_connect_timeout_returns_failure(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_connect_timeout")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC", "0.001")

    class SlowConnectMCP(DummyMCPDefault):
        async def connect(self) -> None:
            import asyncio

            await asyncio.sleep(0.02)

    def _runner_cb(_agent, _prompt, **_kwargs):
        payload = {
            "task_id": "task_connect_timeout",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload))

    _install_fake_agents_sdk(monkeypatch, _runner_cb, mcp_cls=SlowConnectMCP)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_connect_timeout")
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "FAILED"
    assert "agents sdk execution failed" in result["summary"]
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_SERVER_CONNECT_TIMEOUT" in events_text


def test_handoff_chain_success_and_context_exit_path(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_handoff_success")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", "0.01")

    class DummyMCPContextOnly:
        def __init__(
            self,
            params=None,
            client_session_timeout_seconds=None,
            errlog_path=None,
            message_handler=None,
            **kwargs,
        ) -> None:
            del client_session_timeout_seconds, errlog_path, message_handler, kwargs
            self.params = params

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return None

        async def connect(self) -> None:
            return None

        async def list_tools(self):
            return [DummyTool("fs.read")]

    def _runner_cb(agent, _prompt, **_kwargs):
        if agent.name.startswith("OpenVibeCodingHandoff_"):
            handoff_payload = {
                "summary": "handoff ok",
                "risks": [],
            }
            return DummyStreamResult(json.dumps(handoff_payload))
        payload = {
            "task_id": "task_handoff_success",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {"thread_id": "thread-handoff", "session_id": "session-handoff"},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload))

    _install_fake_agents_sdk(monkeypatch, _runner_cb, mcp_cls=DummyMCPContextOnly)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_handoff_success")
    contract["owner_agent"]["role"] = "PM"
    contract["assigned_agent"]["role"] = "WORKER"
    contract["handoff_chain"] = {
        "enabled": True,
        "roles": ["PM", "TECH_LEAD", "WORKER"],
        "max_handoffs": 3,
    }
    contract["timeout_retry"]["timeout_sec"] = 0
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner.ContractValidator.validate_contract",
        lambda self, payload: payload,
    )

    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    assert result["evidence_refs"]["thread_id"] == "thread-handoff"

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_HANDOFF" in events_text
    assert "MCP_SERVER_CLOSED" in events_text


def test_cleanup_without_timeout_uses_direct_cleanup(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_cleanup_direct")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", "0")

    def _runner_cb(_agent, _prompt, **_kwargs):
        payload = {
            "task_id": "task_cleanup_direct",
            "status": "SUCCESS",
            "summary": "ok",
            "evidence_refs": {},
            "failure": None,
        }
        return DummyStreamResult(json.dumps(payload))

    _install_fake_agents_sdk(monkeypatch, _runner_cb, mcp_cls=DummyMCPDefault)

    worker_home = tmp_path / "worker-home"
    worker_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner._materialize_worker_codex_home",
        lambda *_args, **_kwargs: worker_home,
    )

    contract = _base_contract("task_cleanup_direct")
    contract["timeout_retry"]["timeout_sec"] = 0
    monkeypatch.setattr(
        "openvibecoding_orch.runners.agents_runner.ContractValidator.validate_contract",
        lambda self, payload: payload,
    )

    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "task_result.v1.json"
    runner = AgentsRunner(store)
    result = runner.run_contract(contract, tmp_path / "worktree", schema_path, mock_mode=False)

    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_SERVER_CLOSED" in events_text
