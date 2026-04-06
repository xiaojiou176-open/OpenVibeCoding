from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.runners import agents_mcp_execution_helpers as helpers
from cortexpilot_orch.runners.provider_resolution import ProviderResolutionError


class _Store:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.artifacts: list[tuple[str, str, dict[str, Any]]] = []
        self.codex_events: list[tuple[str, str, str]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append((run_id, payload))

    def append_tool_call(self, run_id: str, payload: dict[str, Any]) -> None:
        self.tool_calls.append((run_id, payload))

    def append_artifact_jsonl(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        self.artifacts.append((run_id, name, payload))

    def append_codex_event(self, run_id: str, task_id: str, payload: str) -> None:
        self.codex_events.append((run_id, task_id, payload))


class _Agent:
    def __init__(self, **kwargs: Any) -> None:
        self.name = str(kwargs.get("name", "CortexPilotWorker"))


class _Result:
    def __init__(self, final_output: Any = "ok") -> None:
        self.final_output = final_output


class _Credentials:
    def __init__(
        self,
        *,
        gemini: str = "",
        openai: str = "",
        anthropic: str = "",
        equilibrium: str = "",
    ) -> None:
        self.gemini_api_key = gemini
        self.openai_api_key = openai
        self.anthropic_api_key = anthropic
        self.equilibrium_api_key = equilibrium


async def _noop_message_handler(_message: Any) -> None:
    return None


async def _default_run_streamed(_agent: Any, _prompt: str) -> _Result:
    return _Result("done")


def _base_kwargs(
    *,
    store: _Store,
    tmp_path: Path,
    server_cls: Any,
    probe_mcp_ready: Any,
    runtime_provider: str | None = None,
    mcp_stderr_path: Any = None,
    stdio_client: Any = None,
    resolve_profile: Any = None,
    connect_timeout: Any = None,
    cleanup_timeout: Any = None,
    run_streamed: Any = None,
    finalize_archive: Any = None,
) -> dict[str, Any]:
    return {
        "store": store,
        "run_id": "run-1",
        "task_id": "task-1",
        "instruction": "do it",
        "output_schema_name": "schema.json",
        "output_schema_binding": object,
        "tool_name": "codex",
        "tool_payload": {"x": 1},
        "tool_config": {"sandbox": "workspace-write", "cwd": "/tmp"},
        "fixed_output": False,
        "mcp_tool_set": ["01-filesystem"],
        "worker_codex_home": tmp_path,
        "mcp_stderr_path": mcp_stderr_path,
        "mcp_message_handler": _noop_message_handler,
        "finalize_archive": finalize_archive or (lambda: None),
        "agent_cls": _Agent,
        "mcp_server_stdio_cls": server_cls,
        "stdio_client": stdio_client,
        "run_streamed": run_streamed or _default_run_streamed,
        "agent_instructions": lambda *_args: "inst",
        "user_prompt": lambda *_args: "prompt",
        "resolve_profile": resolve_profile or (lambda: None),
        "patch_initialized_notification": lambda: (True, "patched-init"),
        "patch_codex_event_notifications": lambda: (True, "patched-event"),
        "resolve_mcp_timeout_seconds": lambda: 10.0,
        "resolve_mcp_connect_timeout_sec": connect_timeout or (lambda: None),
        "resolve_mcp_cleanup_timeout_sec": cleanup_timeout or (lambda: None),
        "resolve_codex_base_url": lambda: "http://127.0.0.1:1456/v1",
        "probe_mcp_ready": probe_mcp_ready,
        "runtime_provider": runtime_provider,
    }


def test_normalize_provider_name_and_preferred_api_key_resolution(monkeypatch) -> None:
    assert helpers._normalize_provider_name("google-genai") == "gemini"

    monkeypatch.setattr(
        helpers,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ProviderResolutionError("UNSUPPORTED", "bad provider")),
    )
    assert (
        helpers._resolve_preferred_api_key_for_provider(
            _Credentials(gemini="gem-key"),
            "google-genai",
        )
        == "gem-key"
    )

    arity_calls: list[int] = []

    def _resolver(*args: Any) -> str:
        arity_calls.append(len(args))
        if len(args) == 2:
            raise TypeError("provider arg unsupported")
        return "fallback-key"

    monkeypatch.setattr(helpers, "resolve_preferred_api_key", _resolver)
    assert helpers._resolve_preferred_api_key_for_provider(_Credentials(), "openai") == "fallback-key"
    assert arity_calls == [2, 1]

    monkeypatch.setattr(
        helpers,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected")),
    )
    assert helpers._resolve_preferred_api_key_for_provider(_Credentials(openai="openai-key"), "mystery") == "openai-key"
    assert helpers._resolve_preferred_api_key_for_provider(_Credentials(), "mystery") == ""


@pytest.mark.parametrize(
    ("provider", "expected_key_name"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ],
)
def test_run_worker_execution_sets_provider_specific_env_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    expected_key_name: str,
) -> None:
    captured_env: dict[str, str] = {}

    class _Server:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            env = params.get("env")
            if isinstance(env, dict):
                captured_env.update({str(k): str(v) for k, v in env.items()})
            self.params = params

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    async def _probe(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        return {"probe": "ok"}

    monkeypatch.setattr(helpers, "resolve_runtime_provider", lambda value: value)
    monkeypatch.setattr(
        helpers,
        "resolve_provider_credentials",
        lambda _env=None: _Credentials(openai="openai-key", anthropic="anthropic-key"),
    )

    kwargs = _base_kwargs(
        store=_Store(),
        tmp_path=tmp_path,
        server_cls=_Server,
        probe_mcp_ready=_probe,
        runtime_provider=provider,
    )
    result = asyncio.run(helpers.run_worker_execution(**kwargs))
    assert isinstance(result, _Result)
    assert captured_env["CORTEXPILOT_PROVIDER"] == provider
    assert captured_env[expected_key_name] in {"openai-key", "anthropic-key"}



def test_run_worker_execution_provider_resolution_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Server:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            self.params = params

    async def _probe(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        return {"probe": "ok"}

    monkeypatch.setattr(
        helpers,
        "resolve_runtime_provider",
        lambda _value: (_ for _ in ()).throw(ProviderResolutionError("UNSUPPORTED", "bad provider")),
    )

    kwargs = _base_kwargs(
        store=_Store(),
        tmp_path=tmp_path,
        server_cls=_Server,
        probe_mcp_ready=_probe,
        runtime_provider="legacy",
    )
    with pytest.raises(RuntimeError, match="bad provider"):
        asyncio.run(helpers.run_worker_execution(**kwargs))



def test_run_worker_execution_probe_fail_and_probe_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Server:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            self.params = params

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    monkeypatch.setattr(helpers, "resolve_runtime_provider_from_env", lambda _env=None: "gemini")
    monkeypatch.setattr(helpers, "resolve_provider_credentials", lambda _env=None: _Credentials(gemini="g"))

    async def _probe_fail(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        raise RuntimeError("probe boom")

    store_fail = _Store()
    kwargs_fail = _base_kwargs(
        store=store_fail,
        tmp_path=tmp_path,
        server_cls=_Server,
        probe_mcp_ready=_probe_fail,
        connect_timeout=lambda: None,
    )
    with pytest.raises(RuntimeError, match="mcp ready probe failed"):
        asyncio.run(helpers.run_worker_execution(**kwargs_fail))
    assert any(event[1]["event"] == "MCP_READY_PROBE_FAILED" for event in store_fail.events)

    async def _probe_blocked(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        return {"probe": "blocked"}

    store_blocked = _Store()
    kwargs_blocked = _base_kwargs(
        store=store_blocked,
        tmp_path=tmp_path,
        server_cls=_Server,
        probe_mcp_ready=_probe_blocked,
        connect_timeout=lambda: None,
    )
    with pytest.raises(RuntimeError, match="did not reach ready state"):
        asyncio.run(helpers.run_worker_execution(**kwargs_blocked))
    assert any(event[1]["event"] == "MCP_READY_PROBE_BLOCKED" for event in store_blocked.events)



def test_run_worker_execution_aenter_path_and_cleanup_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _AenterServer:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            self.params = params

        async def __aenter__(self) -> "_AenterServer":
            return self

        async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> bool:
            await asyncio.sleep(0.01)
            return False

    async def _probe(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        return {"probe": "ok"}

    monkeypatch.setattr(helpers, "resolve_runtime_provider_from_env", lambda _env=None: "gemini")
    monkeypatch.setattr(helpers, "resolve_provider_credentials", lambda _env=None: _Credentials(gemini="g"))

    store = _Store()
    kwargs = _base_kwargs(
        store=store,
        tmp_path=tmp_path,
        server_cls=_AenterServer,
        probe_mcp_ready=_probe,
        resolve_profile=lambda: "ops-profile",
        connect_timeout=lambda: None,
        cleanup_timeout=lambda: 0,
    )

    result = asyncio.run(helpers.run_worker_execution(**kwargs))
    assert isinstance(result, _Result)
    assert any(event[1]["event"] == "MCP_SERVER_CLEANUP_TIMEOUT" for event in store.events)
    start_event = next(event for _, event in store.events if event.get("event") == "MCP_SERVER_START")
    assert start_event["meta"]["args"] == ["--profile", "ops-profile", "mcp-server"]



def test_run_worker_execution_create_streams_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _FakeHandle:
        def close(self) -> None:
            raise RuntimeError("close failed")

    class _FakeParent:
        def mkdir(self, parents: bool = False, exist_ok: bool = False) -> None:
            return None

    class _FakeErrPath:
        parent = _FakeParent()

        def open(self, _mode: str, encoding: str = "utf-8") -> _FakeHandle:
            assert encoding == "utf-8"
            return _FakeHandle()

    stdio_calls: list[dict[str, Any]] = []

    def _stdio_client(params: dict[str, Any], errlog: Any) -> dict[str, Any]:
        stdio_calls.append({"params": params, "errlog": errlog})
        return {"ok": True}

    class _ServerWithCreate:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            self.params = params

        def create_streams(self) -> dict[str, Any]:
            return {"super": True}

        async def connect(self) -> None:
            self.create_streams()

        async def cleanup(self) -> None:
            return None

    async def _probe(_server: Any, _tool_set: list[str]) -> dict[str, Any]:
        return {"probe": "ok"}

    monkeypatch.setattr(helpers, "resolve_runtime_provider_from_env", lambda _env=None: "gemini")
    monkeypatch.setattr(helpers, "resolve_provider_credentials", lambda _env=None: _Credentials(gemini="g"))

    finalized: list[str] = []
    kwargs = _base_kwargs(
        store=_Store(),
        tmp_path=tmp_path,
        server_cls=_ServerWithCreate,
        probe_mcp_ready=_probe,
        mcp_stderr_path=_FakeErrPath(),
        stdio_client=_stdio_client,
        finalize_archive=lambda: finalized.append("done"),
        connect_timeout=lambda: None,
        cleanup_timeout=lambda: None,
    )
    result = asyncio.run(helpers.run_worker_execution(**kwargs))
    assert isinstance(result, _Result)
    assert stdio_calls and stdio_calls[0]["errlog"].__class__.__name__ == "_FakeHandle"
    assert finalized == ["done"]

    class _ServerNoCreate:
        def __init__(self, params: dict[str, Any], **_kwargs: Any) -> None:
            self.params = params

        async def connect(self) -> None:
            self.create_streams()

        async def cleanup(self) -> None:
            return None

    kwargs_fail = _base_kwargs(
        store=_Store(),
        tmp_path=tmp_path,
        server_cls=_ServerNoCreate,
        probe_mcp_ready=_probe,
        mcp_stderr_path=None,
        stdio_client=None,
        connect_timeout=lambda: None,
        cleanup_timeout=lambda: None,
    )
    with pytest.raises(RuntimeError, match="MCP create_streams unavailable"):
        asyncio.run(helpers.run_worker_execution(**kwargs_fail))
