import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

from openvibecoding_orch.runners.agents_runner import AgentsRunner
from openvibecoding_orch.store.run_store import RunStore

from .test_agents_runner_helpers_extra import _base_contract, agents_runner


def test_agents_patch_initialized_runtime_behaviors() -> None:
    patched_ok, _ = agents_runner._patch_mcp_initialized_notification()
    assert patched_ok is True

    import mcp.client.session as mcp_session
    from mcp.shared.version import SUPPORTED_PROTOCOL_VERSIONS

    patched_initialize = mcp_session.ClientSession.initialize

    class DummyHandlers:
        @staticmethod
        def build_capability():
            return None

    notifications: list[object] = []

    async def _send_request_supported(_request, _result_type):
        return types.SimpleNamespace(
            protocolVersion=SUPPORTED_PROTOCOL_VERSIONS[0],
            capabilities={"tools": True},
            serverInfo=types.SimpleNamespace(name="other-server"),
        )

    async def _send_notification(payload):
        notifications.append(payload)

    fake_supported = types.SimpleNamespace(
        _sampling_capabilities=None,
        _sampling_callback=lambda *_a, **_k: None,
        _elicitation_callback=lambda *_a, **_k: None,
        _list_roots_callback=lambda *_a, **_k: None,
        _task_handlers=DummyHandlers(),
        _client_info={"name": "openvibecoding", "version": "0.1.0"},
        send_request=_send_request_supported,
        send_notification=_send_notification,
        _server_capabilities=None,
    )

    result = asyncio.run(patched_initialize(fake_supported))
    assert result.protocolVersion == SUPPORTED_PROTOCOL_VERSIONS[0]
    assert fake_supported._server_capabilities == {"tools": True}
    assert len(notifications) == 1

    async def _send_request_unsupported(_request, _result_type):
        return types.SimpleNamespace(
            protocolVersion="1900-01-01",
            capabilities={},
            serverInfo=types.SimpleNamespace(name="other-server"),
        )

    fake_unsupported = types.SimpleNamespace(
        _sampling_capabilities=None,
        _sampling_callback=lambda *_a, **_k: None,
        _elicitation_callback=lambda *_a, **_k: None,
        _list_roots_callback=lambda *_a, **_k: None,
        _task_handlers=DummyHandlers(),
        _client_info={"name": "openvibecoding", "version": "0.1.0"},
        send_request=_send_request_unsupported,
        send_notification=_send_notification,
        _server_capabilities=None,
    )

    with pytest.raises(RuntimeError, match="Unsupported protocol version"):
        asyncio.run(patched_initialize(fake_unsupported))


def test_agents_runner_hard_timebox_timeout(tmp_path: Path, monkeypatch) -> None:
    class TimeoutAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list, **kwargs) -> None:
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers
            self.kwargs = kwargs

    class TimeoutModelSettings:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class TimeoutRunConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class TimeoutStreamResult:
        def __init__(self) -> None:
            self.final_output = None
            self._cancelled = False

        async def stream_events(self):
            while not self._cancelled:
                await asyncio.sleep(0.05)
                yield types.SimpleNamespace(type="run_item_stream_event", name="noop", item=None)

        def cancel(self, mode: str = "immediate") -> None:
            del mode
            self._cancelled = True

        @property
        def is_complete(self) -> bool:
            return self._cancelled

    class TimeoutRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            del agent, prompt, kwargs
            return TimeoutStreamResult()

    class TimeoutMCPServerStdio:
        def __init__(self, params=None, **kwargs) -> None:
            self.params = params
            self.kwargs = kwargs

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

        async def list_tools(self):
            return []

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = TimeoutAgent
    agents_mod.ModelSettings = TimeoutModelSettings
    agents_mod.RunConfig = TimeoutRunConfig
    agents_mod.Runner = TimeoutRunner
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = TimeoutMCPServerStdio

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_timebox_timeout")
    monkeypatch.setenv("OPENVIBECODING_RUN_ID", run_id)
    monkeypatch.setenv("OPENVIBECODING_CODEX_TIMEBOX_SEC", "0.2")
    monkeypatch.setenv("OPENVIBECODING_STREAM_LOG_EVERY", "1")

    runner = AgentsRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task_timebox_timeout")
    contract["timeout_retry"] = {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0}

    result = runner.run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "agents sdk execution failed" in result["summary"]

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_STREAM_TIMEBOX_APPLIED" in events_text
    assert ("MCP_STREAM_HARD_TIMEOUT" in events_text) or ("MCP_STREAM_TIMEOUT" in events_text)
