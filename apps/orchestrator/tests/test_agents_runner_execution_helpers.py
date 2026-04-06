from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from cortexpilot_orch.runners import agents_runner_execution_helpers as execution_helpers
from cortexpilot_orch.runners.provider_resolution import ProviderCredentials, ProviderResolutionError


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.tool_calls: list[tuple[str, dict[str, Any]]] = []
        self.raw_events: list[tuple[str, dict[str, Any], str]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append((run_id, payload))

    def append_tool_call(self, run_id: str, payload: dict[str, Any]) -> None:
        self.tool_calls.append((run_id, payload))


class _DummyValidator:
    def validate_report(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _install_fake_agents_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyAgent:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class DummyModelSettings:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class DummyRunConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class DummyRunner:
        @staticmethod
        def run_streamed(*_args: Any, **_kwargs: Any) -> object:
            class _Result:
                async def stream_events(self):
                    return
                    yield

            return _Result()

        @staticmethod
        def run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            return {"status": "fallback"}

    agents_mod = types.ModuleType("agents")
    agents_mod.__path__ = []  # type: ignore[attr-defined]
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda _api: None
    agents_mod.set_default_openai_client = lambda _client: None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = object
    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)


def _build_module(tmp_path: Path) -> types.SimpleNamespace:
    module = types.SimpleNamespace()
    module.get_runner_config = lambda: types.SimpleNamespace(
        agents_base_url="https://api.provider.local/v1",
        gemini_api_key="gemini-key",
        openai_api_key="openai-key",
        anthropic_api_key="anthropic-key",
        equilibrium_api_key="equilibrium-key",
    )
    module._resolve_agents_base_url = lambda: "https://fallback.local/v1"
    module._resolve_assigned_agent = lambda contract: contract.get("assigned_agent", {})
    module._agent_role = (
        lambda agent: str(agent.get("role", "WORKER")).upper() if isinstance(agent, dict) else "WORKER"
    )
    module._handoff_chain_roles = lambda _contract: []
    module._resolve_output_schema_path = lambda *_args, **_kwargs: tmp_path / "output_schema.json"
    module._build_output_schema_binding = lambda *_args, **_kwargs: object()
    module.agents_handoff_runtime = types.SimpleNamespace(
        execute_handoff_flow=lambda **kwargs: (kwargs["instruction"], {"handoff_ref": "ok"}, None)
    )
    module._handoff_instructions = lambda *_args, **_kwargs: "handoff"
    module._sha256_text = lambda _text: "sha256"
    module._is_fixed_json_template = lambda _instruction: False
    module._decorate_instruction = lambda _role, instruction, *_args, **_kwargs: instruction
    module._resolve_session_binding = lambda _contract: ("", "")
    module._build_codex_payload = lambda _contract, instruction, _worktree_path: {"instruction": instruction}
    module._fixed_output_cwd = lambda _store: str(tmp_path)
    module._resolve_tool_dispatch = lambda _payload, **_kwargs: ("codex", {"argv": []}, {"mode": "safe"}, "")
    module._is_codex_reply_thread_id = lambda _thread_id: False
    module._normalize_mcp_tool_set = lambda raw: list(raw or [])
    module._tool_set_disabled = lambda _tool_set: False
    module._extract_fixed_json_payload = lambda _instruction: {"task_id": "task-1", "status": "SUCCESS"}
    module._build_evidence_refs = lambda _a, _b: {"source": "test"}
    module._coerce_task_result = (
        lambda payload, _contract, evidence_refs, status: {"status": status, "payload": payload, "refs": evidence_refs}
    )
    module._materialize_worker_codex_home = lambda *_args, **_kwargs: tmp_path / "worker-codex-home"
    module._append_agents_raw_event = (
        lambda store, run_id, payload, task_id: store.raw_events.append((run_id, payload, task_id))
    )
    module._build_tool_call = lambda **kwargs: kwargs
    module._resolve_agents_model = lambda: "gemini-model"
    module._resolve_agents_store = lambda: True
    module._strip_model_input_ids = lambda payload: payload
    module._agent_instructions = lambda *_args, **_kwargs: "agent instructions"
    module._user_prompt = lambda *_args, **_kwargs: "user prompt"
    module._resolve_profile = lambda: None
    module._patch_mcp_initialized_notification = lambda: (True, "patched")
    module._patch_mcp_codex_event_notifications = lambda: (True, "patched")
    module._resolve_mcp_timeout_seconds = lambda: 600.0
    module._resolve_mcp_connect_timeout_sec = lambda: 20.0
    module._resolve_mcp_cleanup_timeout_sec = lambda: 5.0
    module._resolve_codex_base_url = lambda: "http://127.0.0.1:1456/v1"
    module._probe_mcp_ready = lambda *_args, **_kwargs: {"probe": "ok"}

    class _Archive:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def handle_message(self, _message: Any) -> None:
            return None

        def finalize(self) -> None:
            return None

    async def _run_worker_execution(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}

    module.agents_mcp_runtime = types.SimpleNamespace(
        bind_mcp_log_paths=lambda **_kwargs: (tmp_path / "stdout.log", tmp_path / "stderr.log"),
        MCPMessageArchive=_Archive,
        run_worker_execution=_run_worker_execution,
    )
    return module


def _invoke_execute(
    *,
    module: Any,
    store: _DummyStore,
    contract: dict[str, Any],
    tmp_path: Path,
    instruction: str = "do it",
    validator: _DummyValidator | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
    transcripts: list[dict[str, Any]] = []
    flush_counter = {"count": 0}

    def _record(payload: dict[str, Any]) -> None:
        transcripts.append(payload)

    def _flush() -> None:
        flush_counter["count"] += 1

    def _failure(reason: str, evidence: dict[str, Any] | None) -> dict[str, Any]:
        return {"status": "FAILED", "reason": reason, "evidence": evidence}

    result = execution_helpers.execute_agents_contract(
        module=module,
        store=store,
        contract=contract,
        worktree_path=tmp_path,
        schema_path=tmp_path / "task_result.v1.json",
        run_id="run-1",
        task_id="task-1",
        instruction=instruction,
        shell_policy="on-request",
        validator=validator or _DummyValidator(),
        record_transcript=_record,
        flush_transcript=_flush,
        failure_result=_failure,
    )
    return result, transcripts, flush_counter


def test_missing_api_key_message_and_provider_key_resolution_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        execution_helpers._missing_llm_api_key_message("openai")
        == "missing LLM API key (OPENAI_API_KEY)"
    )
    assert (
        execution_helpers._missing_llm_api_key_message("unknown")
        == "missing LLM API key (GEMINI_API_KEY)"
    )

    local_gemini = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        equilibrium_api_key="equilibrium-local-key",
    )
    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(
            local_gemini,
            "gemini",
            base_url="http://127.0.0.1:1456/v1",
        )
        == "equilibrium-local-key"
    )

    monkeypatch.setattr(
        execution_helpers,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProviderResolutionError("PROVIDER_UNSUPPORTED", "unsupported")
        ),
    )
    fallback_creds = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="openai-fallback",
        anthropic_api_key="",
        equilibrium_api_key="",
    )
    assert (
        execution_helpers._resolve_preferred_api_key_for_provider(fallback_creds, "mystery-provider")
        == "openai-fallback"
    )


def test_execute_agents_contract_agents_sdk_missing_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _DummyStore()
    contract = {"task_id": "task-1"}
    real_import_module = importlib.import_module

    def _fake_import_module(name: str, package: str | None = None):
        if name == "agents":
            raise ImportError("missing agents sdk")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", _fake_import_module)
    result, transcripts, flush_counter = _invoke_execute(
        module=types.SimpleNamespace(),
        store=store,
        contract=contract,
        tmp_path=tmp_path,
    )

    assert result["status"] == "FAILED"
    assert result["reason"] == "agents sdk not available"
    assert transcripts[0]["kind"] == "agents_sdk_missing"
    assert flush_counter["count"] == 1


def test_execute_agents_contract_provider_resolution_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    store = _DummyStore()
    module = _build_module(tmp_path)
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}}

    monkeypatch.setattr(
        execution_helpers,
        "resolve_runtime_provider_from_contract",
        lambda _contract: (_ for _ in ()).throw(
            ProviderResolutionError("PROVIDER_UNSUPPORTED", "provider invalid")
        ),
    )
    result, transcripts, flush_counter = _invoke_execute(
        module=module, store=store, contract=contract, tmp_path=tmp_path
    )

    assert result["status"] == "FAILED"
    assert result["reason"] == "[PROVIDER_UNSUPPORTED] provider invalid"
    assert result["evidence"] == {"error_code": "PROVIDER_UNSUPPORTED"}
    assert transcripts[0]["kind"] == "provider_resolution_failed"
    assert flush_counter["count"] == 1


def test_execute_agents_contract_missing_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_agents_sdk(monkeypatch)
    store = _DummyStore()
    module = _build_module(tmp_path)
    module.get_runner_config = lambda: types.SimpleNamespace(
        agents_base_url="https://api.provider.local/v1",
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        equilibrium_api_key="",
    )
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}}
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "openai")

    result, transcripts, flush_counter = _invoke_execute(
        module=module, store=store, contract=contract, tmp_path=tmp_path
    )

    assert result["status"] == "FAILED"
    assert result["reason"] == "missing LLM API key (OPENAI_API_KEY)"
    assert transcripts[0]["kind"] == "missing_api_key"
    assert flush_counter["count"] == 1


def test_execute_agents_contract_llm_client_setup_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    store = _DummyStore()
    module = _build_module(tmp_path)
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}}
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(
        execution_helpers,
        "build_llm_compat_client",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("client boom")),
    )

    result, transcripts, flush_counter = _invoke_execute(
        module=module, store=store, contract=contract, tmp_path=tmp_path
    )

    assert result["status"] == "FAILED"
    assert result["reason"] == "agents sdk client setup failed"
    assert result["evidence"] == {"error": "client boom"}
    assert transcripts[0]["kind"] == "llm_compat_client_setup_failed"
    assert flush_counter["count"] == 1


def test_execute_agents_contract_switchyard_runtime_forces_chat_mode_and_placeholder_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    records: dict[str, object] = {}
    agents_mod = sys.modules["agents"]
    agents_mod.set_default_openai_api = lambda mode: records.setdefault("api_mode", mode)
    agents_mod.set_default_openai_client = lambda client: records.setdefault("client", client)

    store = _DummyStore()
    module = _build_module(tmp_path)
    module.get_runner_config = lambda: types.SimpleNamespace(
        agents_base_url="http://127.0.0.1:4010/v1/runtime/invoke",
        agents_api="responses",
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        equilibrium_api_key="",
    )
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}}
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "openai")

    def _build_client(**kwargs):
        records["client_kwargs"] = kwargs
        return object()

    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", _build_client)

    result, transcripts, flush_counter = _invoke_execute(
        module=module,
        store=store,
        contract=contract,
        tmp_path=tmp_path,
    )

    assert result["status"] == "FAILED"
    assert (
        result["reason"]
        == "Switchyard runtime-first adapter is not supported for agents_runner MCP tool execution yet."
    )
    assert result["evidence"] == {"base_url": "http://127.0.0.1:4010/v1/runtime/invoke"}
    assert records == {}
    assert transcripts[0]["kind"] == "switchyard_runtime_unsupported"
    assert flush_counter["count"] == 1


def test_execute_agents_contract_schema_binding_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())

    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]}

    store_path_fail = _DummyStore()
    module_path_fail = _build_module(tmp_path)
    module_path_fail._resolve_output_schema_path = (
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("schema path failed"))
    )
    result_path, _transcripts_path, _flush_path = _invoke_execute(
        module=module_path_fail,
        store=store_path_fail,
        contract=contract,
        tmp_path=tmp_path,
    )
    assert result_path["reason"] == "output schema binding failed"
    assert result_path["evidence"] == {"error": "schema path failed"}
    assert store_path_fail.events[-1][1]["event"] == "OUTPUT_SCHEMA_BIND_FAILED"

    store_bind_fail = _DummyStore()
    module_bind_fail = _build_module(tmp_path)
    module_bind_fail._build_output_schema_binding = (
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bind failed"))
    )
    result_bind, _transcripts_bind, _flush_bind = _invoke_execute(
        module=module_bind_fail,
        store=store_bind_fail,
        contract=contract,
        tmp_path=tmp_path,
    )
    assert result_bind["reason"] == "output schema binding failed"
    assert result_bind["evidence"] == {"error": "bind failed"}
    assert store_bind_fail.events[-1][1]["event"] == "OUTPUT_SCHEMA_BIND_FAILED"


def test_execute_agents_contract_fixed_output_and_mcp_policy_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]}

    # fixed output + disabled tool set + missing fixed payload
    store_fixed = _DummyStore()
    module_fixed = _build_module(tmp_path)
    module_fixed._is_fixed_json_template = lambda _instruction: True
    module_fixed._tool_set_disabled = lambda _tool_set: True
    module_fixed._extract_fixed_json_payload = lambda _instruction: {}
    fixed_result, _transcripts_fixed, _flush_fixed = _invoke_execute(
        module=module_fixed,
        store=store_fixed,
        contract=contract,
        tmp_path=tmp_path,
        instruction='{"fixed":true}',
    )
    assert fixed_result["reason"] == "fixed output json missing"
    assert store_fixed.events[-1][1]["event"] == "AGENT_FIXED_OUTPUT_INVALID"

    # non-fixed + empty mcp tool set
    store_toolset = _DummyStore()
    module_toolset = _build_module(tmp_path)
    module_toolset._normalize_mcp_tool_set = lambda _raw: []
    module_toolset._tool_set_disabled = lambda _tool_set: False
    toolset_result, _transcripts_toolset, _flush_toolset = _invoke_execute(
        module=module_toolset,
        store=store_toolset,
        contract=contract,
        tmp_path=tmp_path,
    )
    assert toolset_result["reason"] == "mcp_tool_set missing or empty"
    assert store_toolset.events[-1][1]["event"] == "MCP_READY_PROBE_FAILED"


def test_execute_agents_contract_materialize_and_execution_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]}

    # codex home materialize failure
    store_materialize = _DummyStore()
    module_materialize = _build_module(tmp_path)
    module_materialize._materialize_worker_codex_home = (
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("materialize failed"))
    )
    materialize_result, _transcripts_materialize, _flush_materialize = _invoke_execute(
        module=module_materialize,
        store=store_materialize,
        contract=contract,
        tmp_path=tmp_path,
    )
    assert materialize_result["reason"] == "codex home materialize failed: materialize failed"
    assert store_materialize.events[-1][1]["event"] == "MCP_READY_PROBE_FAILED"

    # runtime execution failure
    store_execute = _DummyStore()
    module_execute = _build_module(tmp_path)

    async def _raise_worker_execution(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("worker execution failed")

    module_execute.agents_mcp_runtime.run_worker_execution = _raise_worker_execution
    execute_result, transcripts_execute, flush_execute = _invoke_execute(
        module=module_execute,
        store=store_execute,
        contract=contract,
        tmp_path=tmp_path,
    )
    assert execute_result["reason"] == "agents sdk execution failed"
    assert execute_result["evidence"] == {"error": "worker execution failed"}
    assert transcripts_execute[-1]["kind"] == "execution_error"
    assert flush_execute["count"] == 1
    assert len(store_execute.tool_calls) == 1
    assert len(store_execute.raw_events) == 1


def _install_stream_test_sdk(monkeypatch: pytest.MonkeyPatch, runner_cls: Any) -> None:
    class DummyAgent:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class DummyModelSettings:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class DummyRunConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    agents_mod = types.ModuleType("agents")
    agents_mod.__path__ = []  # type: ignore[attr-defined]
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = runner_cls
    agents_mod.set_default_openai_client = lambda _client: None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = object
    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)


def test_execute_agents_contract_stream_timeout_retry_mode_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Result:
        async def stream_events(self):
            return
            yield

    class _Runner:
        @staticmethod
        def run_streamed(*_args: Any, **_kwargs: Any) -> _Result:
            return _Result()

        @staticmethod
        def run(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            return {"status": "unused"}

    _install_stream_test_sdk(monkeypatch, _Runner)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STREAM_TIMEOUT_RETRIES", "1")
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STREAM_TIMEOUT_RETRY_BACKOFF_SEC", "0.01")
    monkeypatch.delenv("CORTEXPILOT_AGENTS_STREAM_TIMEOUT_FALLBACK", raising=False)

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(execution_helpers.asyncio, "sleep", _no_sleep)

    store = _DummyStore()
    module = _build_module(tmp_path)
    consume_calls = {"count": 0}

    async def _consume_stream_events(**_kwargs: Any) -> None:
        consume_calls["count"] += 1
        if consume_calls["count"] == 1:
            raise RuntimeError("stream timeout")
        return None

    module.agents_stream_runtime = types.SimpleNamespace(consume_stream_events=_consume_stream_events)

    def _handoff_flow(**kwargs: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
        asyncio.run(kwargs["run_streamed"](object(), "handoff prompt"))
        return kwargs["instruction"], {}, {"status": "FAILED", "reason": "handoff-stop"}

    module.agents_handoff_runtime = types.SimpleNamespace(execute_handoff_flow=_handoff_flow)

    result, _transcripts, _flush = _invoke_execute(
        module=module,
        store=store,
        contract={"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]},
        tmp_path=tmp_path,
    )

    assert result["reason"] == "handoff-stop"
    assert consume_calls["count"] == 2
    retry_events = [payload for _, payload in store.events if payload.get("event") == "AGENTS_STREAM_TIMEOUT_RETRY"]
    assert retry_events
    assert retry_events[0]["meta"]["mode"] == "stream"


def test_execute_agents_contract_stream_timeout_fallback_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Result:
        async def stream_events(self):
            return
            yield

    run_calls = {"count": 0}

    class _Runner:
        @staticmethod
        def run_streamed(*_args: Any, **_kwargs: Any) -> _Result:
            return _Result()

        @staticmethod
        async def run(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            run_calls["count"] += 1
            if run_calls["count"] == 1:
                raise RuntimeError("fallback timeout")
            return {"status": "fallback-ok"}

    _install_stream_test_sdk(monkeypatch, _Runner)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STREAM_TIMEOUT_RETRIES", "1")
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STREAM_RETRY_BACKOFF_SEC", "0.01")
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STREAM_TIMEOUT_FALLBACK", "1")

    async def _no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(execution_helpers.asyncio, "sleep", _no_sleep)

    store = _DummyStore()
    module = _build_module(tmp_path)
    captured: dict[str, Any] = {}

    async def _consume_stream_events(**_kwargs: Any) -> None:
        raise RuntimeError("stream timed out")

    module.agents_stream_runtime = types.SimpleNamespace(consume_stream_events=_consume_stream_events)

    def _handoff_flow(**kwargs: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
        captured["fallback_result"] = asyncio.run(kwargs["run_streamed"](object(), "handoff prompt"))
        return kwargs["instruction"], {}, {"status": "FAILED", "reason": "handoff-stop"}

    module.agents_handoff_runtime = types.SimpleNamespace(execute_handoff_flow=_handoff_flow)

    result, _transcripts, _flush = _invoke_execute(
        module=module,
        store=store,
        contract={"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]},
        tmp_path=tmp_path,
    )

    assert result["reason"] == "handoff-stop"
    assert captured["fallback_result"] == {"status": "fallback-ok"}
    assert run_calls["count"] == 2
    fallback_events = [payload for _, payload in store.events if payload.get("event") == "AGENTS_STREAM_TIMEOUT_FALLBACK"]
    retry_events = [payload for _, payload in store.events if payload.get("event") == "AGENTS_STREAM_TIMEOUT_RETRY"]
    assert fallback_events
    assert retry_events
    assert retry_events[0]["meta"]["mode"] == "fallback"


def test_execute_agents_contract_stream_result_without_stream_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Runner:
        @staticmethod
        def run_streamed(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            return {"immediate": "ok"}

        @staticmethod
        def run(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            return {"status": "unused"}

    _install_stream_test_sdk(monkeypatch, _Runner)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())

    store = _DummyStore()
    module = _build_module(tmp_path)
    captured: dict[str, Any] = {}

    def _handoff_flow(**kwargs: Any) -> tuple[str, dict[str, Any], dict[str, Any]]:
        captured["stream_result"] = asyncio.run(kwargs["run_streamed"](object(), "handoff prompt"))
        return kwargs["instruction"], {}, {"status": "FAILED", "reason": "handoff-stop"}

    module.agents_handoff_runtime = types.SimpleNamespace(execute_handoff_flow=_handoff_flow)

    result, _transcripts, _flush = _invoke_execute(
        module=module,
        store=store,
        contract={"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]},
        tmp_path=tmp_path,
    )

    assert result["reason"] == "handoff-stop"
    assert captured["stream_result"] == {"immediate": "ok"}


def test_execute_agents_contract_fixed_output_schema_invalid_and_success_bypass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    contract = {"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]}

    module_invalid = _build_module(tmp_path)
    module_invalid._is_fixed_json_template = lambda _instruction: True
    module_invalid._tool_set_disabled = lambda _tool_set: True
    module_invalid._extract_fixed_json_payload = lambda _instruction: {"task_id": "task-1", "status": "SUCCESS"}

    class _FailValidator(_DummyValidator):
        def validate_report(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("schema invalid")

    result_invalid, _transcripts_invalid, _flush_invalid = _invoke_execute(
        module=module_invalid,
        store=_DummyStore(),
        contract=contract,
        tmp_path=tmp_path,
        instruction='{"fixed":true}',
        validator=_FailValidator(),
    )
    assert result_invalid["reason"] == "fixed output schema invalid"
    assert result_invalid["evidence"] == {"error": "schema invalid"}

    module_success = _build_module(tmp_path)
    module_success._is_fixed_json_template = lambda _instruction: True
    module_success._tool_set_disabled = lambda _tool_set: True
    module_success._extract_fixed_json_payload = lambda _instruction: {"task_id": "task-1", "status": "SUCCESS"}
    module_success.agents_handoff_runtime = types.SimpleNamespace(
        execute_handoff_flow=lambda **kwargs: (kwargs["instruction"], {"handoff_ref": "present"}, None)
    )
    result_success, _transcripts_success, _flush_success = _invoke_execute(
        module=module_success,
        store=_DummyStore(),
        contract=contract,
        tmp_path=tmp_path,
        instruction='{"fixed":true}',
    )
    assert result_success["status"] == "SUCCESS"
    assert result_success["refs"]["handoff_ref"] == "present"


def test_execute_agents_contract_session_events_finalize_and_mcp_message_handler(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(execution_helpers, "resolve_runtime_provider_from_contract", lambda _contract: "gemini")
    monkeypatch.setattr(execution_helpers, "build_llm_compat_client", lambda **_kwargs: object())
    monkeypatch.setattr(
        execution_helpers,
        "finalize_agents_run_result",
        lambda **kwargs: {"status": "SUCCESS", "result": kwargs["result"]},
    )

    messages: list[Any] = []

    class _Archive:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def handle_message(self, message: Any) -> None:
            messages.append(message)

        def finalize(self) -> None:
            return None

    async def _run_worker_execution(**kwargs: Any) -> dict[str, Any]:
        await kwargs["mcp_message_handler"]({"kind": "mcp"})
        return {"status": "ok"}

    store = _DummyStore()
    module = _build_module(tmp_path)
    module._resolve_session_binding = lambda _contract: ("thread-123", "session-123")
    module._resolve_tool_dispatch = (
        lambda _payload, **_kwargs: ("codex", {"argv": []}, {"mode": "safe"}, "legacy-thread")
    )
    module.agents_mcp_runtime = types.SimpleNamespace(
        bind_mcp_log_paths=lambda **_kwargs: (tmp_path / "stdout.log", tmp_path / "stderr.log"),
        MCPMessageArchive=_Archive,
        run_worker_execution=_run_worker_execution,
    )

    result, _transcripts, _flush = _invoke_execute(
        module=module,
        store=store,
        contract={"task_id": "task-1", "assigned_agent": {"role": "WORKER"}, "mcp_tool_set": ["01-filesystem"]},
        tmp_path=tmp_path,
    )

    assert result["status"] == "SUCCESS"
    assert messages == [{"kind": "mcp"}]
    events = [payload.get("event") for _, payload in store.events]
    assert "AGENT_SESSION_THREAD_ID_UNSUPPORTED" in events
    assert "AGENT_SESSION_RESOLVED" in events
