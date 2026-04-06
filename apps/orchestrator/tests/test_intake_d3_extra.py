import json
import os
import sys
import types
from pathlib import Path

import pytest

from cortexpilot_orch.planning import intake
from cortexpilot_orch.runners.provider_resolution import ProviderCredentials


class _CfgBase:
    agents_base_url = "http://127.0.0.1:1456/v1"
    gemini_api_key = "gemini-key"
    openai_api_key = ""
    anthropic_api_key = ""
    equilibrium_api_key = ""
    agents_api = "responses"
    agents_model = "gpt-test"


def _install_agents_module(monkeypatch, *, runner_result, set_api, set_client) -> None:
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

    class DummyRunner:
        @staticmethod
        def run_streamed(*_args, **_kwargs):
            return runner_result

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = set_api
    agents_mod.set_default_openai_client = set_client
    monkeypatch.setitem(sys.modules, "agents", agents_mod)


def test_intake_preferred_api_key_alias_and_fallback_branches(monkeypatch) -> None:
    local_bridge_creds = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="",
        equilibrium_api_key="eq-key",
    )
    assert (
        intake._resolve_preferred_api_key_for_provider(
            local_bridge_creds,
            "google-genai",
            base_url="http://127.0.0.1:1456/v1",
        )
        == "eq-key"
    )
    assert intake._resolve_preferred_api_key_for_provider(local_bridge_creds, "codex-equilibrium") == "eq-key"

    creds_with_openai = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="openai-key",
        anthropic_api_key="",
        equilibrium_api_key="",
    )

    monkeypatch.setattr(
        intake,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(intake.ProviderResolutionError("E", "no provider")),
    )
    assert intake._resolve_preferred_api_key_for_provider(creds_with_openai, "custom-provider") == "openai-key"

    def _typeerror_then_plain(*args, **_kwargs):
        if len(args) == 2:
            raise TypeError("bad args")
        return "plain-fallback"

    monkeypatch.setattr(intake, "resolve_preferred_api_key", _typeerror_then_plain)
    assert intake._resolve_preferred_api_key_for_provider(creds_with_openai, "custom-provider") == "plain-fallback"

    creds_with_anthropic = ProviderCredentials(
        gemini_api_key="",
        openai_api_key="",
        anthropic_api_key="anthropic-key",
        equilibrium_api_key="",
    )
    monkeypatch.setattr(
        intake,
        "resolve_preferred_api_key",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert intake._resolve_preferred_api_key_for_provider(creds_with_anthropic, "custom-provider") == "anthropic-key"


def test_intake_execute_chain_uses_repo_root_and_orchestrator(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    scheduler_mod = types.ModuleType("cortexpilot_orch.scheduler.scheduler")

    class FakeOrchestrator:
        def __init__(self, root: Path) -> None:
            captured["root"] = root

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict[str, object]:
            captured["chain_path"] = chain_path
            captured["mock_mode"] = mock_mode
            return {"run_id": "run-exec"}

    scheduler_mod.Orchestrator = FakeOrchestrator
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.scheduler.scheduler", scheduler_mod)

    chain_path = tmp_path / "task_chain.json"
    chain_path.write_text("{}", encoding="utf-8")

    result = intake._execute_chain(chain_path, mock_mode=True)
    assert result == {"run_id": "run-exec"}
    assert captured["chain_path"] == chain_path
    assert captured["mock_mode"] is True
    assert captured["root"] == intake._repo_root()


def test_intake_run_agent_provider_resolution_error(monkeypatch) -> None:
    class _Result:
        final_output = json.dumps({"questions": ["ok"]})

    _install_agents_module(
        monkeypatch,
        runner_result=_Result(),
        set_api=lambda *_args, **_kwargs: None,
        set_client=lambda *_args, **_kwargs: None,
    )

    monkeypatch.setattr(intake, "get_runner_config", lambda: _CfgBase())
    monkeypatch.setattr(
        intake,
        "resolve_runtime_provider_from_env",
        lambda: (_ for _ in ()).throw(intake.ProviderResolutionError("PROVIDER_UNSUPPORTED", "bad provider")),
    )

    with pytest.raises(RuntimeError, match="bad provider"):
        intake._run_agent("prompt", "inst")


def test_intake_run_agent_set_default_and_stream_branches(monkeypatch) -> None:
    class _ResultWithStream:
        final_output = json.dumps({"questions": ["Q1"]})

        async def stream_events(self):
            yield {"type": "delta"}

    _install_agents_module(
        monkeypatch,
        runner_result=_ResultWithStream(),
        set_api=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("api mode error")),
        set_client=object(),
    )

    monkeypatch.setattr(intake, "get_runner_config", lambda: _CfgBase())
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(intake, "build_llm_compat_client", lambda **_kwargs: object())

    out = intake._run_agent("prompt", "inst")
    assert out == {"questions": ["Q1"]}



def test_intake_run_agent_set_default_client_exception_and_no_stream(monkeypatch) -> None:
    class _ResultNoStream:
        def __init__(self) -> None:
            self.final_output = json.dumps({"questions": ["Q2"]})

    def _raise_client(*_args, **_kwargs):
        raise RuntimeError("client hook failed")

    _install_agents_module(
        monkeypatch,
        runner_result=_ResultNoStream(),
        set_api=lambda *_args, **_kwargs: None,
        set_client=_raise_client,
    )

    monkeypatch.setattr(intake, "get_runner_config", lambda: _CfgBase())
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setattr(intake, "build_llm_compat_client", lambda **_kwargs: object())

    out = intake._run_agent("prompt", "inst")
    assert out == {"questions": ["Q2"]}


def test_intake_service_answer_payload_and_contract_edge_branches(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    monkeypatch.setattr(service._validator, "validate_report", lambda *_args, **_kwargs: None)

    # intake_exists=True but intake payload missing in store.
    monkeypatch.setattr(service._store, "intake_exists", lambda _intake_id: True)
    monkeypatch.setattr(service._store, "read_intake", lambda _intake_id: {})
    missing_payload = service.answer("broken-intake", {"answers": ["x"]})
    assert missing_payload["status"] == "FAILED"

    # Use a real intake for non-dict payload path and keep pre-set runner env unchanged.
    store = intake.IntakeService()._store
    intake_id = store.create(
        {
            "objective": "edge branches",
            "allowed_paths": ["apps/orchestrator/src"],
            "mcp_tool_set": ["01-filesystem"],
            "browser_policy_preset": "safe",
            "browser_policy": {"profile_mode": "ephemeral"},
            "policy_notes": "",
        }
    )

    service2 = intake.IntakeService()
    monkeypatch.setattr(service2._validator, "validate_report", lambda *_args, **_kwargs: None)

    plan = {
        "plan_id": "plan-a",
        "task_id": "task-a",
    }
    plan_bundle = {
        "bundle_id": "bundle-a",
        "created_at": "2026-03-01T00:00:00Z",
        "objective": "edge branches",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "plans": [plan],
    }

    monkeypatch.setattr(intake, "generate_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(intake, "generate_plan_bundle", lambda *_args, **_kwargs: (plan_bundle, ""))
    monkeypatch.setattr(intake, "build_task_chain_from_bundle", lambda *_args, **_kwargs: {"chain_id": "chain-1", "steps": []})
    monkeypatch.setattr(intake, "_execute_chain", lambda *_args, **_kwargs: {"run_id": "run-edge"})

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    ready = service2.answer(intake_id, ["not-a-dict-payload"])
    assert ready["status"] == "READY"
    assert ready["chain_run_id"] == "run-edge"
    assert os.getenv("CORTEXPILOT_RUNNER") == "codex"

    service2._store.write_response(
        intake_id,
        {
            "intake_id": intake_id,
            "status": "READY",
            "questions": [],
            "plan": {"plan_id": "p", "task_id": "t"},
        },
    )
    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-no-pm",
            "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
            "inputs": {"artifacts": []},
        },
    )
    contract = service2.build_contract(intake_id)
    assert isinstance(contract, dict)
    assert "handoff_chain" not in contract
