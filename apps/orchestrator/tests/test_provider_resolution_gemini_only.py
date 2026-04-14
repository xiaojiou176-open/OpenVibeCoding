from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

from openvibecoding_orch.planning import intake
from openvibecoding_orch.runners import agents_mcp_execution_helpers, agents_mcp_runtime
from openvibecoding_orch.runners import provider_resolution as provider_resolution_module
from openvibecoding_orch import config as config_module
from openvibecoding_orch.runners.provider_resolution import (
    build_llm_compat_client,
    ProviderResolutionError,
    resolve_runtime_provider_from_contract,
)
from openvibecoding_orch.scheduler import scheduler_bridge_runtime
from openvibecoding_orch.store.run_store import RunStore


class _Cfg:
    agents_base_url = "https://api.provider.local/v1"
    agents_api = ""
    agents_model = "model-from-runner"
    gemini_api_key = ""
    openai_api_key = ""
    equilibrium_api_key = ""


class _Creds:
    def __init__(
        self, gemini: str = "", openai: str = "", equilibrium: str = "", anthropic: str = ""
    ) -> None:
        self.gemini_api_key = gemini
        self.openai_api_key = openai
        self.equilibrium_api_key = equilibrium
        self.anthropic_api_key = anthropic


def _install_fake_agents_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers

    class DummyModelSettings:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyRunConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyResult:
        final_output = json.dumps({"questions": ["Q1"]})

        async def stream_events(self):
            return
            yield

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, run_config):
            del agent, prompt, run_config
            return DummyResult()

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner

    monkeypatch.setitem(sys.modules, "agents", agents_mod)


@pytest.mark.parametrize(
    ("provider", "expected_key"),
    [
        ("gemini", "gemini-key"),
        ("openai", "openai-key"),
        ("equilibrium", "gemini-key"),
    ],
)
def test_intake_run_agent_accepts_three_provider_inputs(
    monkeypatch: pytest.MonkeyPatch, provider: str, expected_key: str
) -> None:
    _install_fake_agents_sdk(monkeypatch)
    captured: dict[str, str] = {}

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: provider)
    monkeypatch.setattr(
        intake,
        "resolve_provider_credentials",
        lambda: _Creds(gemini="gemini-key", openai="openai-key", equilibrium="equilibrium-key"),
    )
    monkeypatch.setattr(intake, "merge_provider_credentials", lambda primary, fallback: fallback)
    monkeypatch.setattr(
        intake,
        "build_llm_compat_client",
        lambda api_key, base_url=None, **_kwargs: captured.update(
            {
                "api_key": str(api_key),
                "base_url": str(base_url or ""),
            }
        ),
    )

    payload = intake._run_agent("prompt", "instructions")
    assert payload == {"questions": ["Q1"]}
    assert captured["api_key"] == expected_key
    assert captured["base_url"] == _Cfg.agents_base_url


def test_intake_run_agent_rejects_invalid_provider_with_fail_closed_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_agents_sdk(monkeypatch)

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setattr(
        intake,
        "resolve_runtime_provider_from_env",
        lambda: (_ for _ in ()).throw(
            ProviderResolutionError("PROVIDER_UNSUPPORTED", "unsupported provider 'legacy'")
        ),
    )

    with pytest.raises(RuntimeError, match=r"\[PROVIDER_UNSUPPORTED\]"):
        intake._run_agent("prompt", "instructions")


def test_intake_run_agent_missing_key_message_matches_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_agents_sdk(monkeypatch)

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: "openai")
    monkeypatch.setattr(intake, "resolve_provider_credentials", lambda: _Creds())
    monkeypatch.setattr(intake, "merge_provider_credentials", lambda primary, fallback: fallback)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        intake._run_agent("prompt", "instructions")


def test_mcp_runtime_materialize_injects_provider_model_key_and_base_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs_root = tmp_path / "runs"
    role_home = tmp_path / "role-home"
    base_home = tmp_path / "base-home"
    role_home.mkdir(parents=True, exist_ok=True)
    base_home.mkdir(parents=True, exist_ok=True)
    (role_home / "config.toml").write_text(
        'model_provider = "gemini"\nmodel = "legacy-model"\n',
        encoding="utf-8",
    )
    (base_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "gemini"',
                'model = "legacy-model"',
                "",
                "[model_providers.openai]",
                'base_url = "https://old.local/v1"',
                'experimental_bearer_token = "old"',
                "",
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_HOME", str(base_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_MODEL", "openai-model")
    monkeypatch.setattr(agents_mcp_runtime, "resolve_runtime_provider_from_env", lambda env=None: "openai")
    monkeypatch.setattr(agents_mcp_runtime, "resolve_provider_credentials", lambda env=None: _Creds(openai="okey"))

    store = RunStore(runs_root=runs_root)
    out = agents_mcp_runtime.materialize_worker_codex_home(
        store=store,
        run_id="run-1",
        task_id="task-1",
        tool_set=["01-filesystem"],
        role="WORKER",
        worktree_path=tmp_path,
        skip_role_prompt=True,
        resolve_codex_base_url=lambda: "https://provider.local/v1",
    )
    text = (out / "config.toml").read_text(encoding="utf-8")
    assert 'model_provider = "openai"' in text
    assert 'model = "openai-model"' in text
    assert 'base_url = "https://provider.local/v1"' in text
    assert 'env_key = "OPENAI_API_KEY"' not in text
    assert 'experimental_bearer_token = "okey"' not in text
    assert 'api_key = "okey"' not in text


def test_mcp_execution_env_injects_provider_specific_key_and_base_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured_env: dict[str, str] = {}

    class DummyServer:
        def __init__(self, params: dict[str, object], **kwargs) -> None:
            del kwargs
            env = params.get("env")
            if isinstance(env, dict):
                for key, value in env.items():
                    captured_env[str(key)] = str(value)
            self.params = params

        async def connect(self) -> None:
            return

        async def cleanup(self) -> None:
            return

    class DummyAgent:
        def __init__(self, **kwargs) -> None:
            self.name = "OpenVibeCodingWorker"
            self.kwargs = kwargs

    class DummyResult:
        final_output = "ok"

    async def _run_streamed(agent: object, prompt: str) -> DummyResult:
        del agent, prompt
        return DummyResult()

    async def _probe(server: object, tool_set: list[str]) -> dict[str, object]:
        del server, tool_set
        return {"probe": "ok", "tools_count": 1, "servers": ["filesystem"]}

    store = RunStore(runs_root=tmp_path / "runs")
    monkeypatch.setattr(
        agents_mcp_execution_helpers,
        "resolve_runtime_provider_from_env",
        lambda env=None: "equilibrium",
    )
    monkeypatch.setattr(
        agents_mcp_execution_helpers,
        "resolve_provider_credentials",
        lambda env=None: _Creds(equilibrium="equ-key"),
    )

    async def _execute() -> None:
        await agents_mcp_execution_helpers.run_worker_execution(
            store=store,
            run_id="run-1",
            task_id="task-1",
            instruction="do it",
            output_schema_name="schema.json",
            output_schema_binding=object,
            tool_name="exec",
            tool_payload={},
            tool_config={},
            fixed_output=False,
            mcp_tool_set=["01-filesystem"],
            worker_codex_home=tmp_path,
            mcp_stderr_path=None,
            mcp_message_handler=lambda _msg: None,  # type: ignore[arg-type]
            finalize_archive=lambda: None,
            agent_cls=DummyAgent,
            mcp_server_stdio_cls=DummyServer,
            stdio_client=None,
            run_streamed=_run_streamed,
            agent_instructions=lambda *_args: "inst",
            user_prompt=lambda *_args: "prompt",
            resolve_profile=lambda: None,
            patch_initialized_notification=lambda: (True, "patched"),
            patch_codex_event_notifications=lambda: (True, "patched"),
            resolve_mcp_timeout_seconds=lambda: 10.0,
            resolve_mcp_connect_timeout_sec=lambda: 5.0,
            resolve_mcp_cleanup_timeout_sec=lambda: 5.0,
            resolve_codex_base_url=lambda: "http://127.0.0.1:1456/v1",
            probe_mcp_ready=_probe,
        )

    asyncio.run(_execute())

    assert captured_env["OPENVIBECODING_PROVIDER"] == "equilibrium"
    assert captured_env["OPENVIBECODING_PROVIDER_BASE_URL"] == "http://127.0.0.1:1456/v1"
    assert captured_env["OPENVIBECODING_EQUILIBRIUM_API_KEY"] == "equ-key"


def test_mcp_execution_tool_call_persistence_redacts_sensitive_args(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class DummyStore:
        def __init__(self) -> None:
            self.tool_calls: list[dict[str, object]] = []
            self.events: list[dict[str, object]] = []
            self.artifacts: list[dict[str, object]] = []
            self.codex_events: list[dict[str, object]] = []

        def append_event(self, _run_id: str, payload: dict[str, object]) -> None:
            self.events.append(payload)

        def append_tool_call(self, _run_id: str, payload: dict[str, object]) -> None:
            self.tool_calls.append(payload)

        def append_artifact_jsonl(self, _run_id: str, _name: str, payload: dict[str, object]) -> None:
            self.artifacts.append(payload)

        def append_codex_event(self, _run_id: str, _task_id: str, payload: str) -> None:
            self.codex_events.append(json.loads(payload))

    class DummyServer:
        def __init__(self, params: dict[str, object], **kwargs) -> None:
            del kwargs
            self.params = params

        async def connect(self) -> None:
            return

        async def cleanup(self) -> None:
            return

    class DummyAgent:
        def __init__(self, **kwargs) -> None:
            self.name = "OpenVibeCodingWorker"
            self.kwargs = kwargs

    class DummyResult:
        final_output = "ok"

    async def _run_streamed(agent: object, prompt: str) -> DummyResult:
        del agent, prompt
        return DummyResult()

    async def _probe(server: object, tool_set: list[str]) -> dict[str, object]:
        del server, tool_set
        return {"probe": "ok", "tools_count": 1, "servers": ["filesystem"]}

    monkeypatch.setattr(
        agents_mcp_execution_helpers,
        "resolve_runtime_provider_from_env",
        lambda env=None: "gemini",
    )
    monkeypatch.setattr(
        agents_mcp_execution_helpers,
        "resolve_provider_credentials",
        lambda env=None: _Creds(gemini="gem-key"),
    )
    store = DummyStore()

    async def _execute() -> None:
        await agents_mcp_execution_helpers.run_worker_execution(
            store=store,  # type: ignore[arg-type]
            run_id="run-redact",
            task_id="task-redact",
            instruction="do it",
            output_schema_name="schema.json",
            output_schema_binding=object,
            tool_name="exec",
            tool_payload={
                "api_key": "top-secret",
                "message": "Bearer abcdefghijklmnop",
                "nested": {"token": "child-secret"},
            },
            tool_config={"token": "config-secret", "model": "gemini-3.0-flash"},
            fixed_output=False,
            mcp_tool_set=["01-filesystem"],
            worker_codex_home=tmp_path,
            mcp_stderr_path=None,
            mcp_message_handler=lambda _msg: None,  # type: ignore[arg-type]
            finalize_archive=lambda: None,
            agent_cls=DummyAgent,
            mcp_server_stdio_cls=DummyServer,
            stdio_client=None,
            run_streamed=_run_streamed,
            agent_instructions=lambda *_args: "inst",
            user_prompt=lambda *_args: "prompt token=abc123",
            resolve_profile=lambda: None,
            patch_initialized_notification=lambda: (True, "patched"),
            patch_codex_event_notifications=lambda: (True, "patched"),
            resolve_mcp_timeout_seconds=lambda: 10.0,
            resolve_mcp_connect_timeout_sec=lambda: 5.0,
            resolve_mcp_cleanup_timeout_sec=lambda: 5.0,
            resolve_codex_base_url=lambda: "http://127.0.0.1:1456/v1",
            probe_mcp_ready=_probe,
        )

    asyncio.run(_execute())

    assert store.tool_calls
    tool_call = store.tool_calls[0]
    args = tool_call.get("args")
    assert isinstance(args, dict)
    assert args["api_key"] == "[REDACTED]"
    assert args["nested"]["token"] == "[REDACTED]"
    assert args["message"] == "[REDACTED]"

    config = tool_call.get("config")
    assert isinstance(config, dict)
    assert config["token"] == "[REDACTED]"

    assert store.codex_events
    execution_start_events = [item for item in store.codex_events if item.get("kind") == "execution_start"]
    assert execution_start_events
    assert execution_start_events[0]["prompt"] == "[REDACTED]"


def test_select_runner_prefers_contract_provider_override_over_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, str] = {}

    class DummyAdapterRunner:
        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            del contract, worktree_path, schema_path, mock_mode
            return {"status": "SUCCESS"}

    def _build_execution_adapter(*, run_store, runner_name=None, provider=None):
        del run_store
        captured["runner_name"] = str(runner_name or "")
        captured["provider"] = str(provider or "")
        return DummyAdapterRunner()

    fake_module = types.SimpleNamespace(build_execution_adapter=_build_execution_adapter)
    monkeypatch.setattr(scheduler_bridge_runtime, "import_module", lambda _name: fake_module)
    monkeypatch.setenv("OPENVIBECODING_RUNNER", "agents")
    monkeypatch.setenv("OPENVIBECODING_PROVIDER", "gemini")

    store = RunStore(runs_root=tmp_path / "runs")
    runner = scheduler_bridge_runtime.select_runner(
        {
            "task_id": "task-provider-override",
            "runtime_options": {"runner": "claude", "provider": "anthropic"},
        },
        store,
    )

    assert isinstance(runner, DummyAdapterRunner)
    assert captured["runner_name"] == "claude"
    assert captured["provider"] == ""


def test_select_runner_keeps_runner_resolution_when_provider_override_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, str] = {}

    class DummyAdapterRunner:
        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            del contract, worktree_path, schema_path, mock_mode
            return {"status": "SUCCESS"}

    def _build_execution_adapter(*, run_store, runner_name=None, provider=None):
        del run_store
        captured["runner_name"] = str(runner_name or "")
        captured["provider"] = str(provider or "")
        return DummyAdapterRunner()

    fake_module = types.SimpleNamespace(build_execution_adapter=_build_execution_adapter)
    monkeypatch.setattr(scheduler_bridge_runtime, "import_module", lambda _name: fake_module)
    monkeypatch.setenv("OPENVIBECODING_RUNNER", "agents")
    monkeypatch.setenv("OPENVIBECODING_PROVIDER", "openai")

    store = RunStore(runs_root=tmp_path / "runs")
    runner = scheduler_bridge_runtime.select_runner(
        {"task_id": "task-provider-fallback", "runtime_options": {"runner": "claude"}},
        store,
    )

    assert isinstance(runner, DummyAdapterRunner)
    assert captured["runner_name"] == "claude"
    assert captured["provider"] == ""


def test_contract_provider_override_takes_precedence_over_env_provider() -> None:
    resolved = resolve_runtime_provider_from_contract(
        {"runtime_options": {"provider": "openai"}},
        env={"OPENVIBECODING_PROVIDER": "gemini"},
    )
    assert resolved == "openai"


def test_contract_provider_invalid_value_is_blocked() -> None:
    with pytest.raises(ProviderResolutionError) as exc_info:
        resolve_runtime_provider_from_contract(
            {"runtime_options": {"provider": "legacy"}},
            env={"OPENVIBECODING_PROVIDER": "gemini"},
        )
    assert exc_info.value.code == "PROVIDER_UNSUPPORTED"
    assert "register provider-gateway:legacy first" in str(exc_info.value)


def test_build_llm_compat_client_litellm_switch_falls_back_to_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _LiteLLMModule:
        acompletion = object()

    class _AsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _OpenAIModule:
        AsyncOpenAI = _AsyncOpenAI

    def _import_module(name: str):
        if name == "litellm":
            return _LiteLLMModule()
        if name == "openai":
            return _OpenAIModule()
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setenv("OPENVIBECODING_PROVIDER_USE_LITELLM", "1")
    monkeypatch.setattr(provider_resolution_module.importlib, "import_module", _import_module)

    client = build_llm_compat_client(api_key="k", base_url="https://llm.example/v1")
    assert isinstance(client, _AsyncOpenAI)
    assert client.kwargs["api_key"] == "k"
    assert client.kwargs["base_url"] == "https://llm.example/v1"


def test_build_llm_compat_client_uses_openai_path_when_switch_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_PROVIDER_USE_LITELLM", raising=False)

    class _AsyncOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _OpenAIModule:
        AsyncOpenAI = _AsyncOpenAI

    def _import_module(name: str):
        if name == "openai":
            return _OpenAIModule()
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(provider_resolution_module.importlib, "import_module", _import_module)

    client = build_llm_compat_client(api_key="openai-key", base_url="https://api.example/v1")
    assert isinstance(client, _AsyncOpenAI)
    assert client.kwargs["api_key"] == "openai-key"
    assert client.kwargs["base_url"] == "https://api.example/v1"


def test_resolve_compat_api_mode_forces_chat_completions_for_switchyard_runtime() -> None:
    assert (
        provider_resolution_module.resolve_compat_api_mode(
            "responses",
            base_url="http://127.0.0.1:4010/v1/runtime/invoke",
        )
        == "chat_completions"
    )


def test_resolve_compat_api_key_uses_placeholder_for_switchyard_runtime_without_keys() -> None:
    credentials = _Creds()
    assert (
        provider_resolution_module.resolve_compat_api_key(
            credentials,
            "openai",
            base_url="http://127.0.0.1:4010/v1/runtime/invoke",
        )
        == "switchyard-local"
    )


def test_build_llm_compat_client_returns_switchyard_runtime_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeMessage:
        def __init__(self, payload: dict[str, object]) -> None:
            self.role = str(payload.get("role") or "")
            self.content = str(payload.get("content") or "")
            self._payload = payload

        def model_dump(self) -> dict[str, object]:
            return dict(self._payload)

    class _FakeChatCompletion:
        def __init__(self, payload: dict[str, object]) -> None:
            self.id = str(payload.get("id") or "")
            self.created = int(payload.get("created") or 0)
            self.model = str(payload.get("model") or "")
            choice_payload = payload["choices"][0]  # type: ignore[index]
            message = _FakeMessage(choice_payload["message"])  # type: ignore[index]
            self.choices = [
                types.SimpleNamespace(
                    index=int(choice_payload.get("index", 0)),
                    finish_reason=str(choice_payload.get("finish_reason") or ""),
                    message=message,
                    logprobs=None,
                )
            ]
            self.usage = types.SimpleNamespace(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                prompt_tokens_details=None,
                completion_tokens_details=None,
            )

        @classmethod
        def model_validate(cls, payload: dict[str, object]):
            return cls(payload)

    class _FakeChatModule:
        ChatCompletion = _FakeChatCompletion

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                "outputText": "SWITCHYARD_OK",
                "providerMessageId": "switchyard-msg-1",
            }

    class _FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, object]):
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    real_import_module = provider_resolution_module.importlib.import_module

    def _import_module(name: str):
        if name == "openai.types.chat":
            return _FakeChatModule()
        return real_import_module(name)

    monkeypatch.setattr(provider_resolution_module.importlib, "import_module", _import_module)
    monkeypatch.setattr(provider_resolution_module.httpx, "AsyncClient", _FakeAsyncClient)

    client = build_llm_compat_client(
        api_key="switchyard-local",
        base_url="http://127.0.0.1:4010/v1/runtime/invoke",
        provider="openai",
    )
    completion = asyncio.run(
        client.chat.completions.create(
            model="chatgpt/gpt-4o",
            messages=[
                {"role": "system", "content": "Return the exact sentinel."},
                {"role": "user", "content": "Return SWITCHYARD_OK"},
            ],
        )
    )

    assert captured["url"] == "http://127.0.0.1:4010/v1/runtime/invoke"
    assert captured["json"] == {
        "provider": "chatgpt",
        "model": "gpt-4o",
        "input": "System instructions:\nReturn the exact sentinel.\n\nUser request:\nReturn SWITCHYARD_OK",
        "lane": "web",
        "stream": False,
    }
    assert completion.id == "switchyard-msg-1"
    assert completion.choices[0].message.content == "SWITCHYARD_OK"


def test_invoke_switchyard_runtime_retries_transient_5xx_and_generates_unique_fallback_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            types.SimpleNamespace(
                status_code=503,
                json=lambda: {"error": {"message": "temporary outage"}},
            ),
            types.SimpleNamespace(
                status_code=200,
                json=lambda: {"outputText": "SWITCHYARD_OK"},
            ),
        ]
    )
    captured_calls: list[dict[str, object]] = []

    class _FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, object]):
            captured_calls.append({"url": url, "json": json, "timeout": self.timeout})
            return next(responses)

    monkeypatch.setattr(provider_resolution_module.httpx, "AsyncClient", _FakeAsyncClient)

    output_text, response_id = asyncio.run(
        provider_resolution_module._invoke_switchyard_runtime(
            base_url="http://127.0.0.1:4010/v1/runtime/invoke",
            provider="chatgpt",
            model="gpt-4o",
            lane="web",
            input_text="Return SWITCHYARD_OK",
            system_text=None,
            timeout=30.0,
            max_retries=1,
        )
    )

    assert len(captured_calls) == 2
    assert output_text == "SWITCHYARD_OK"
    assert response_id.startswith("switchyard-")


def test_resolve_provider_credentials_reads_equilibrium_key_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENVIBECODING_EQUILIBRIUM_API_KEY", "eq-only")
    credentials = provider_resolution_module.resolve_provider_credentials()
    assert credentials.equilibrium_api_key == "eq-only"


def test_load_config_propagates_equilibrium_key_into_runner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENVIBECODING_EQUILIBRIUM_API_KEY", "eq-only")
    cfg = config_module.load_config()
    assert cfg.runner.equilibrium_api_key == "eq-only"


def test_resolve_runtime_base_url_uses_canonical_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_url = "https://api.provider.local/v1"
    monkeypatch.setenv("OPENVIBECODING_PROVIDER_BASE_URL", base_url)
    resolved = provider_resolution_module.resolve_runtime_base_url_from_env()
    assert resolved == base_url


def test_agents_mcp_runtime_key_resolution_fallback_and_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        agents_mcp_runtime,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProviderResolutionError("PROVIDER_UNSUPPORTED", "unsupported")
        ),
    )
    creds = _Creds(gemini="gemini-key", openai="openai-key", equilibrium="equilibrium-key")

    assert agents_mcp_runtime._normalize_provider_name("google-genai") == "gemini"
    assert (
        agents_mcp_runtime._resolve_preferred_api_key_for_provider(creds, "google-genai")
        == "gemini-key"
    )
    assert (
        agents_mcp_runtime._resolve_preferred_api_key_for_provider(creds, "openai")
        == "openai-key"
    )


def test_agents_mcp_runtime_key_resolution_typeerror_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    call_arity: list[int] = []

    def _resolver(*args):
        call_arity.append(len(args))
        if len(args) == 2:
            raise TypeError("provider arg unsupported")
        return "fallback-key"

    monkeypatch.setattr(agents_mcp_runtime, "resolve_preferred_api_key", _resolver)

    assert (
        agents_mcp_runtime._resolve_preferred_api_key_for_provider(_Creds(), "anthropic")
        == "fallback-key"
    )
    assert call_arity == [2, 1]


def test_agents_mcp_runtime_resolve_mcp_server_names_aliases_and_missing() -> None:
    resolved, missing = agents_mcp_runtime.resolve_mcp_server_names(
        ["codex", "search", "browser", "unknown"],
        {
            "devtools-04-filesystem",
            "ctx-short-02-ripgrep",
            "browser-01-playwright",
        },
    )
    assert resolved == ["devtools-04-filesystem", "ctx-short-02-ripgrep", "browser-01-playwright"]
    assert missing == ["unknown"]


def test_agents_mcp_runtime_patch_functions_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name.startswith("mcp"):
            raise ImportError("forced mcp import error")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    ok_codex, detail_codex = agents_mcp_runtime.patch_mcp_codex_event_notifications()
    ok_init, detail_init = agents_mcp_runtime.patch_mcp_initialized_notification()
    assert ok_codex is False and "mcp import failed" in detail_codex
    assert ok_init is False and "mcp import failed" in detail_init


def test_agents_mcp_runtime_probe_ready_and_strip_model_input_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Tool:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Server:
        async def list_tools(self):
            return [_Tool("fs.read"), _Tool("browser/open"), _Tool("plain")]

    skipped = asyncio.run(agents_mcp_runtime.probe_mcp_ready(object(), ["01-filesystem"]))
    assert skipped["probe"] == "skipped"

    payload = asyncio.run(agents_mcp_runtime.probe_mcp_ready(_Server(), ["01-filesystem"]))
    assert payload["probe"] == "ok"
    assert payload["tools_count"] == 3
    assert payload["servers"] == ["browser", "fs", "plain"]

    agents_pkg = types.ModuleType("agents")
    agents_pkg.__path__ = []  # type: ignore[attr-defined]
    run_mod = types.ModuleType("agents.run")

    class _ModelInputData:
        def __init__(self, input, instructions=None) -> None:  # noqa: A002
            self.input = input
            self.instructions = instructions

    run_mod.ModelInputData = _ModelInputData
    agents_pkg.run = run_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents", agents_pkg)
    monkeypatch.setitem(sys.modules, "agents.run", run_mod)

    rich_payload = types.SimpleNamespace(
        model_data=types.SimpleNamespace(
            input=[{"id": "x", "response_id": "y", "keep": 1}, "raw"],
            instructions="keep",
        )
    )
    sanitized = agents_mcp_runtime.strip_model_input_ids(rich_payload)
    assert isinstance(sanitized, _ModelInputData)
    assert sanitized.input[0] == {"keep": 1}
    assert sanitized.input[1] == "raw"
    assert sanitized.instructions == "keep"


def test_agents_mcp_runtime_strip_model_input_ids_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "agents.run":
            raise ImportError("missing agents.run")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match="ModelInputData missing"):
        agents_mcp_runtime.strip_model_input_ids(types.SimpleNamespace(model_data=None))


def test_agents_mcp_runtime_helper_branches_runtime_root_and_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original = 'model_provider = "old"\n[model_providers.old]\napi_key = "k"\n'
    assert agents_mcp_runtime._override_top_level_toml_key(original, "model", "") == original
    replaced = agents_mcp_runtime._override_top_level_toml_key(original, "model_provider", "new-provider")
    assert 'model_provider = "new-provider"' in replaced
    assert replaced.count('model_provider = "new-provider"') == 1

    section = agents_mcp_runtime._extract_model_provider_section(
        "\n".join(
            [
                "[model_providers.openai]",
                'base_url = "https://api.example.com/v1"',
                "",
                "[other]",
                "enabled = true",
            ]
        ),
        "openai",
    )
    assert "[model_providers.openai]" in section
    assert "base_url" in section
    assert agents_mcp_runtime._extract_model_provider_section("plain = true", "openai") == ""
    assert agents_mcp_runtime._extract_model_provider_section("plain = true", "") == ""

    store = RunStore(runs_root=tmp_path / "runs")
    override_root = tmp_path / "runtime-root"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(override_root))
    assert agents_mcp_runtime.runtime_root_from_store(store) == override_root
    assert agents_mcp_runtime.fixed_output_cwd(store) == str(override_root.resolve())


def test_agents_mcp_runtime_resolve_mcp_server_names_numeric_aliases_and_vcs() -> None:
    resolved, missing = agents_mcp_runtime.resolve_mcp_server_names(
        ["", "01-filesystem", "vcs-01-filesystem", "playwright", "unknown"],
        {"filesystem", "browser-02-playwright"},
    )
    assert resolved == ["filesystem", "browser-02-playwright"]
    assert missing == ["unknown"]


def test_agents_mcp_runtime_materialize_missing_tool_set_and_provider_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runs_root = tmp_path / "runs"
    role_home = tmp_path / "role-home"
    base_home = tmp_path / "base-home"
    role_home.mkdir(parents=True, exist_ok=True)
    base_home.mkdir(parents=True, exist_ok=True)
    (role_home / "config.toml").write_text('model_provider = "gemini"\n', encoding="utf-8")
    (base_home / "config.toml").write_text('model_provider = "gemini"\n', encoding="utf-8")

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.setenv("OPENVIBECODING_CODEX_BASE_HOME", str(base_home))
    store = RunStore(runs_root=runs_root)

    with pytest.raises(RuntimeError, match="mcp_tool_set missing in base config"):
        agents_mcp_runtime.materialize_worker_codex_home(
            store=store,
            run_id="run-missing",
            task_id="task-missing",
            tool_set=["01-filesystem"],
            role="WORKER",
            worktree_path=tmp_path,
            skip_role_prompt=True,
        )

    (base_home / "config.toml").write_text(
        "\n".join(
            [
                'model_provider = "gemini"',
                "",
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agents_mcp_runtime,
        "resolve_runtime_provider",
        lambda _provider: (_ for _ in ()).throw(
            ProviderResolutionError("PROVIDER_UNSUPPORTED", "unsupported provider")
        ),
    )
    with pytest.raises(RuntimeError, match=r"\[PROVIDER_UNSUPPORTED\]"):
        agents_mcp_runtime.materialize_worker_codex_home(
            store=store,
            run_id="run-provider-error",
            task_id="task-provider-error",
            tool_set=["01-filesystem"],
            role="WORKER",
            worktree_path=tmp_path,
            skip_role_prompt=True,
            runtime_provider="legacy",
        )


def test_agents_mcp_runtime_probe_ready_empty_and_strip_with_none_input(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Tool:
        def __init__(self, name: object) -> None:
            self.name = name

    class _Server:
        async def list_tools(self):
            return [_Tool(""), _Tool(None), _Tool("   ")]

    payload = asyncio.run(agents_mcp_runtime.probe_mcp_ready(_Server(), ["01-filesystem"]))
    assert payload["probe"] == "empty"
    assert payload["tools_count"] == 0

    agents_pkg = types.ModuleType("agents")
    agents_pkg.__path__ = []  # type: ignore[attr-defined]
    run_mod = types.ModuleType("agents.run")

    class _ModelInputData:
        def __init__(self, input, instructions=None) -> None:  # noqa: A002
            self.input = input
            self.instructions = instructions

    run_mod.ModelInputData = _ModelInputData
    agents_pkg.run = run_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agents", agents_pkg)
    monkeypatch.setitem(sys.modules, "agents.run", run_mod)

    sanitized = agents_mcp_runtime.strip_model_input_ids(types.SimpleNamespace(model_data=None))
    assert isinstance(sanitized, _ModelInputData)
    assert sanitized.input == []
    assert sanitized.instructions is None


def test_agents_mcp_runtime_patch_codex_event_supported_and_patch_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_pkg = types.ModuleType("mcp")
    mcp_pkg.__path__ = []  # type: ignore[attr-defined]
    mcp_types_supported = types.ModuleType("mcp.types")

    class _Notification:
        def __class_getitem__(cls, _item):
            return cls

    class _ServerNotification:
        @staticmethod
        def model_validate(_payload):
            return True

    mcp_types_supported.Notification = _Notification
    mcp_types_supported.ServerNotification = _ServerNotification
    mcp_types_supported.ServerNotificationType = object
    monkeypatch.setitem(sys.modules, "mcp", mcp_pkg)
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types_supported)

    ok_supported, detail_supported = agents_mcp_runtime.patch_mcp_codex_event_notifications()
    assert ok_supported is True
    assert detail_supported == "already supported"

    mcp_types_fail = types.ModuleType("mcp.types")
    mcp_types_fail.Notification = _Notification
    mcp_types_fail.ServerNotificationType = "broken"

    class _ServerNotificationFail:
        @staticmethod
        def model_validate(_payload):
            raise RuntimeError("unsupported")

    mcp_types_fail.ServerNotification = _ServerNotificationFail
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types_fail)

    ok_failed, detail_failed = agents_mcp_runtime.patch_mcp_codex_event_notifications()
    assert ok_failed is False
    assert "patch failed" in detail_failed


def test_agents_mcp_runtime_patch_initialized_notification_runtime_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_pkg = types.ModuleType("mcp")
    mcp_pkg.__path__ = []  # type: ignore[attr-defined]
    mcp_client_pkg = types.ModuleType("mcp.client")
    mcp_client_pkg.__path__ = []  # type: ignore[attr-defined]
    mcp_shared_pkg = types.ModuleType("mcp.shared")
    mcp_shared_pkg.__path__ = []  # type: ignore[attr-defined]

    mcp_session = types.ModuleType("mcp.client.session")
    mcp_types = types.ModuleType("mcp.types")
    mcp_version = types.ModuleType("mcp.shared.version")
    mcp_version.SUPPORTED_PROTOCOL_VERSIONS = ["2026-03-08"]

    class _SimpleType:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class _ClientSession:
        async def initialize(self):  # pragma: no cover - replaced by patch
            return None

    mcp_session.ClientSession = _ClientSession
    mcp_session._default_sampling_callback = lambda *_args, **_kwargs: None
    mcp_session._default_elicitation_callback = lambda *_args, **_kwargs: None
    mcp_session._default_list_roots_callback = lambda *_args, **_kwargs: None
    mcp_types.LATEST_PROTOCOL_VERSION = "2026-03-08"
    mcp_types.InitializeResult = _SimpleType
    mcp_types.ClientRequest = _SimpleType
    mcp_types.InitializeRequest = _SimpleType
    mcp_types.InitializeRequestParams = _SimpleType
    mcp_types.ClientCapabilities = _SimpleType
    mcp_types.SamplingCapability = _SimpleType
    mcp_types.ElicitationCapability = _SimpleType
    mcp_types.FormElicitationCapability = _SimpleType
    mcp_types.UrlElicitationCapability = _SimpleType
    mcp_types.RootsCapability = _SimpleType
    mcp_types.ClientNotification = _SimpleType
    mcp_types.InitializedNotification = _SimpleType

    monkeypatch.setitem(sys.modules, "mcp", mcp_pkg)
    monkeypatch.setitem(sys.modules, "mcp.client", mcp_client_pkg)
    monkeypatch.setitem(sys.modules, "mcp.client.session", mcp_session)
    monkeypatch.setitem(sys.modules, "mcp.types", mcp_types)
    monkeypatch.setitem(sys.modules, "mcp.shared", mcp_shared_pkg)
    monkeypatch.setitem(sys.modules, "mcp.shared.version", mcp_version)

    ok_patch, detail_patch = agents_mcp_runtime.patch_mcp_initialized_notification()
    assert ok_patch is True
    assert detail_patch == "patched"

    patched_initialize = mcp_session.ClientSession.initialize
    notifications: list[object] = []

    class _Handlers:
        @staticmethod
        def build_capability():
            return {"tasks": True}

    async def _send_request_non_codex(_request: object, _result_type: object):
        return types.SimpleNamespace(
            protocolVersion="2026-03-08",
            capabilities={"ok": True},
            serverInfo=types.SimpleNamespace(name="other-server"),
        )

    async def _send_notification(payload: object):
        notifications.append(payload)

    fake_non_codex = types.SimpleNamespace(
        _sampling_capabilities=None,
        _sampling_callback=lambda *_args, **_kwargs: None,
        _elicitation_callback=lambda *_args, **_kwargs: None,
        _list_roots_callback=lambda *_args, **_kwargs: None,
        _task_handlers=_Handlers(),
        _client_info={"name": "openvibecoding", "version": "0.1"},
        send_request=_send_request_non_codex,
        send_notification=_send_notification,
        _server_capabilities=None,
    )

    asyncio.run(patched_initialize(fake_non_codex))
    assert len(notifications) == 1
    assert fake_non_codex._server_capabilities == {"ok": True}

    async def _send_request_codex(_request: object, _result_type: object):
        return types.SimpleNamespace(
            protocolVersion="2026-03-08",
            capabilities={"ok": True},
            serverInfo=types.SimpleNamespace(name="codex-server"),
        )

    fake_codex = types.SimpleNamespace(
        _sampling_capabilities=None,
        _sampling_callback=lambda *_args, **_kwargs: None,
        _elicitation_callback=lambda *_args, **_kwargs: None,
        _list_roots_callback=lambda *_args, **_kwargs: None,
        _task_handlers=_Handlers(),
        _client_info={"name": "openvibecoding", "version": "0.1"},
        send_request=_send_request_codex,
        send_notification=_send_notification,
        _server_capabilities=None,
    )
    asyncio.run(patched_initialize(fake_codex))
    assert len(notifications) == 1

    async def _send_request_unsupported(_request: object, _result_type: object):
        return types.SimpleNamespace(
            protocolVersion="1900-01-01",
            capabilities={},
            serverInfo=types.SimpleNamespace(name="other-server"),
        )

    fake_unsupported = types.SimpleNamespace(
        _sampling_capabilities=None,
        _sampling_callback=lambda *_args, **_kwargs: None,
        _elicitation_callback=lambda *_args, **_kwargs: None,
        _list_roots_callback=lambda *_args, **_kwargs: None,
        _task_handlers=_Handlers(),
        _client_info={"name": "openvibecoding", "version": "0.1"},
        send_request=_send_request_unsupported,
        send_notification=_send_notification,
        _server_capabilities=None,
    )
    with pytest.raises(RuntimeError, match="Unsupported protocol version"):
        asyncio.run(patched_initialize(fake_unsupported))

    ok_repeat, detail_repeat = agents_mcp_runtime.patch_mcp_initialized_notification()
    assert ok_repeat is True
    assert detail_repeat == "already patched"
