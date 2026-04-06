import json
import os
import sys
import threading
import types
from pathlib import Path

import pytest

from cortexpilot_orch.api import main_pm_intake_helpers
from cortexpilot_orch.planning import intake
from cortexpilot_orch.store.intake_store import IntakeStore


def test_intake_normalizers_and_defaults() -> None:
    assert intake._normalize_answers(" yes ") == ["yes"]
    assert intake._normalize_answers(["a", " ", 2]) == ["a", "2"]
    assert intake._normalize_answers({"bad": True}) == []

    assert intake._normalize_constraints(" 并行度=3 ") == ["并行度=3"]
    assert intake._normalize_constraints(["x", "", " y "]) == ["x", "y"]
    assert intake._extract_parallelism(["foo", "并行度=4"]) == 4
    assert intake._extract_parallelism(["并行度=0"]) is None

    qs = intake._default_questions("x" * 120)
    assert len(qs) == 4
    assert qs[0] == "Which specific directories or files need to change?"
    assert "Should the scope stay strictly limited to:" in qs[-1]


def test_build_plan_fallback_clone_and_paths() -> None:
    payload = {
        "objective": "harden runtime",
        "allowed_paths": ["apps/orchestrator/src"],
        "constraints": ["no network"],
        "owner_agent": {"role": "PM", "agent_id": "agent-9"},
        "mcp_tool_set": ["01-filesystem"],
    }
    plan = intake._build_plan_fallback(payload, ["ship it"])
    assert plan["plan_type"] == "BACKEND"
    assert plan["owner_agent"]["role"] == "PM"
    assert "Answers:" in plan["spec"]
    assert plan["acceptance_tests"] == [
        {"name": "repo_hygiene", "cmd": "bash scripts/check_repo_hygiene.sh", "must_pass": True}
    ]

    clone = intake._clone_plan({"plan_id": "plan-alpha", "labels": ["keep"]}, "SECURITY")
    assert clone["plan_id"].endswith("security")
    assert "SECURITY" in clone["labels"]

    assert intake._paths_overlap("docs/", "docs/api/")
    assert not intake._paths_overlap("apps/", "docs/")

    with pytest.raises(ValueError, match="mcp_tool_set"):
        intake._build_plan_fallback({"objective": "x"}, [])


def test_bundle_normalization_and_rebalance() -> None:
    owner = {"role": "TECH_LEAD", "agent_id": "agent-1"}
    tests = [{"name": "echo", "cmd": "echo ok", "must_pass": True}]

    normalized = intake._normalize_bundle_plan(
        {
            "plan_id": "short",
            "task_id": "bad",
            "plan_type": "UNKNOWN",
            "spec": {"rich": True},
            "allowed_paths": ["apps/"],
            "assigned_agent": {"role": "REVIEWER", "agent_id": "someone"},
            "owner_agent": {"role": "PM", "agent_id": "pm"},
        },
        owner,
        tests,
        "BACKEND",
    )
    assert normalized["plan_type"] == "BACKEND"
    assert normalized["assigned_agent"]["role"] == "REVIEWER"
    assert normalized["owner_agent"]["role"] == "PM"
    assert isinstance(normalized["spec"], str)

    with pytest.raises(ValueError, match="allowed_paths"):
        intake._normalize_bundle_plan({}, owner, tests, None)

    plans = [
        {"plan_id": "a", "allowed_paths": ["apps/"]},
        {"plan_id": "b", "allowed_paths": ["docs/"]},
    ]
    intake._validate_plan_bundle_paths(plans)

    with pytest.raises(ValueError, match="overlap"):
        intake._validate_plan_bundle_paths(
            [
                {"plan_id": "a", "allowed_paths": ["apps/"]},
                {"plan_id": "b", "allowed_paths": ["apps/core/"]},
            ]
        )

    rebalanced = intake._rebalance_bundle_paths(
        [{"allowed_paths": ["x"]}, {"allowed_paths": ["y"]}, {"allowed_paths": ["z"]}],
        ["apps/", "docs/", "tooling/", "schemas/"],
        desired_parallelism=2,
    )
    assert len(rebalanced) == 2
    assert rebalanced[0]["allowed_paths"]


def test_agents_config_helpers_and_strip_model_input_ids(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STORE", "true")
    assert intake._resolve_agents_store() is True
    monkeypatch.setenv("CORTEXPILOT_AGENTS_STORE", "no")
    assert intake._resolve_agents_store() is False

    assert intake._is_local_base_url("http://127.0.0.1:1456/v1")
    assert not intake._is_local_base_url("https://api.openai.com/v1")

    class DummyModelInputData:
        def __init__(self, input, instructions=None) -> None:  # noqa: A002
            self.input = input
            self.instructions = instructions

    run_mod = types.ModuleType("agents.run")
    run_mod.ModelInputData = DummyModelInputData
    monkeypatch.setitem(sys.modules, "agents.run", run_mod)

    payload = types.SimpleNamespace(
        model_data=types.SimpleNamespace(
            input=[{"id": "x", "response_id": "y", "foo": 1}, "bar"],
            instructions="inst",
        )
    )
    sanitized = intake._strip_model_input_ids(payload)
    assert sanitized.instructions == "inst"
    assert sanitized.input[0] == {"foo": 1}


def test_generate_questions_and_plan_fallback(monkeypatch) -> None:
    payload = {
        "objective": "improve docs",
        "allowed_paths": ["docs/"],
        "mcp_tool_set": ["01-filesystem"],
    }

    monkeypatch.setattr(intake, "_agents_available", lambda: False)
    assert intake.generate_questions(payload)
    plan = intake.generate_plan(payload, ["focus on quickstart"])
    assert plan["task_type"] == "IMPLEMENT"

    monkeypatch.setattr(intake, "_agents_available", lambda: True)
    monkeypatch.setattr(intake, "_run_agent", lambda *_args, **_kwargs: {"questions": ["Q1", "Q2"]})
    assert intake.generate_questions(payload) == ["Q1", "Q2"]

    monkeypatch.setattr(intake, "_run_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    plan2 = intake.generate_plan(payload, [])
    assert plan2["plan_type"] == "BACKEND"


def test_intake_run_agent_with_fake_sdk(monkeypatch) -> None:
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
        def __init__(self, output: str) -> None:
            self.final_output = output

        async def stream_events(self):
            if self.final_output == "__stream__":
                yield None
            return

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, run_config):
            del agent, prompt, run_config
            return DummyResult(json.dumps({"questions": ["Q1"]}))

    records: dict[str, object] = {}

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda mode: records.setdefault("api_mode", mode)
    agents_mod.set_default_openai_client = lambda client: records.setdefault("client", client)

    class DummyAsyncOpenAI:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = DummyAsyncOpenAI

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "openai", openai_mod)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORTEXPILOT_AGENTS_API", "responses")
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_MODEL", "gpt-test")

    result = intake._run_agent("prompt", "instructions")
    assert result == {"questions": ["Q1"]}

    class BadRunner:
        @staticmethod
        def run_streamed(agent, prompt, run_config):
            del agent, prompt, run_config
            return DummyResult("not-json")

    agents_mod.Runner = BadRunner
    with pytest.raises(RuntimeError, match="planner output not json"):
        intake._run_agent("prompt", "instructions")


def test_intake_run_agent_accepts_gemini_api_key_as_equivalent_credential(monkeypatch) -> None:
    class _Cfg:
        agents_base_url = "https://api.openai.com/v1"
        openai_api_key = ""
        equilibrium_api_key = ""
        agents_api = ""
        agents_model = "gpt-test"

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

    captured: dict[str, object] = {}
    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("legacy openai client injection should not be used")
    )

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setattr(
        intake,
        "build_llm_compat_client",
        lambda api_key, base_url=None, **_kwargs: captured.update(
            {"api_key": api_key, "base_url": base_url}
        ),
    )
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-only-key")

    result = intake._run_agent("prompt", "instructions")

    assert result == {"questions": ["Q1"]}
    assert captured["api_key"] == "gemini-only-key"
    assert captured["base_url"] == _Cfg.agents_base_url


def test_intake_run_agent_switchyard_runtime_forces_chat_mode_and_placeholder_key(monkeypatch) -> None:
    class _Cfg:
        agents_base_url = "http://127.0.0.1:4010/v1/runtime/invoke"
        gemini_api_key = ""
        openai_api_key = ""
        anthropic_api_key = ""
        equilibrium_api_key = ""
        agents_api = "responses"
        agents_model = "chatgpt/gpt-4o"

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

    records: dict[str, object] = {}

    def _build_client(**kwargs):
        records["client_kwargs"] = kwargs
        return object()

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda mode: records.setdefault("api_mode", mode)
    agents_mod.set_default_openai_client = lambda client: records.setdefault("client", client)
    monkeypatch.setitem(sys.modules, "agents", agents_mod)

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setattr(intake, "resolve_runtime_provider_from_env", lambda: "openai")
    monkeypatch.setattr(
        intake,
        "resolve_provider_credentials",
        lambda: types.SimpleNamespace(
            gemini_api_key="",
            openai_api_key="",
            anthropic_api_key="",
            equilibrium_api_key="",
        ),
    )
    monkeypatch.setattr(intake, "merge_provider_credentials", lambda primary, fallback: primary)
    monkeypatch.setattr(intake, "build_llm_compat_client", _build_client)

    result = intake._run_agent("prompt", "instructions")

    assert result == {"questions": ["Q1"]}
    assert records["api_mode"] == "chat_completions"
    assert records["client_kwargs"] == {
        "api_key": "switchyard-local",
        "base_url": _Cfg.agents_base_url,
        "provider": "openai",
    }


def test_intake_service_answer_and_build_contract(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    schema_root = repo_root / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)

    source_schema_root = Path(__file__).resolve().parents[3] / "schemas"
    for name in [
        "pm_intake_request.v1.json",
        "pm_intake_response.v1.json",
        "plan.schema.json",
        "plan_bundle.v1.json",
        "task_chain.v1.json",
        "handoff.v1.json",
    ]:
        (schema_root / name).write_text((source_schema_root / name).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))

    service = intake.IntakeService()

    missing = service.answer("missing-id", {"answers": ["x"]})
    assert missing["status"] == "FAILED"
    assert not (runtime_root / "intakes" / "missing-id").exists()
    assert service.build_contract("missing-id") is None
    assert not (runtime_root / "intakes" / "missing-id").exists()

    payload = {
        "objective": "wire intake",
        "allowed_paths": ["apps/orchestrator/src"],
        "mcp_tool_set": ["01-filesystem"],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "never",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "search_queries": ["cortexpilot orchestrator"],
    }
    created = service.create(payload)
    assert created["status"] == "NEEDS_INPUT"
    intake_id = created["intake_id"]

    answered = service.answer(intake_id, {"answers": ["none"], "auto_run_chain": False})
    assert answered["status"] == "READY"
    assert "plan" in answered
    events_path = service._store._intake_dir(intake_id) / "events.jsonl"
    event_rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    answer_events = [item for item in event_rows if item.get("event") == "INTAKE_ANSWER"]
    assert len(answer_events) == 1
    assert (answer_events[0].get("context") or {}).get("answers") == ["none"]

    contract = service.build_contract(intake_id)
    assert isinstance(contract, dict)
    artifacts = contract.get("inputs", {}).get("artifacts", [])
    assert any(item.get("name") == "search_requests.json" for item in artifacts)
    assert contract["tool_permissions"]["mcp_tools"] == ["codex", "search"]

    # PM owner should force handoff chain in compiled contract.
    response_path = service._store._intake_dir(intake_id) / "response.json"
    response = json.loads(response_path.read_text(encoding="utf-8"))
    response["plan"]["owner_agent"] = {"role": "PM", "agent_id": "agent-1"}
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    contract_pm = service.build_contract(intake_id)
    assert contract_pm.get("handoff_chain", {}).get("enabled") is True


def test_intake_service_auto_run_chain_restores_runner_env(monkeypatch, tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    repo_root = tmp_path / "repo"
    schema_root = repo_root / "schemas"
    schema_root.mkdir(parents=True, exist_ok=True)

    source_schema_root = Path(__file__).resolve().parents[3] / "schemas"
    for name in [
        "pm_intake_request.v1.json",
        "pm_intake_response.v1.json",
        "plan.schema.json",
        "plan_bundle.v1.json",
        "task_chain.v1.json",
    ]:
        (schema_root / name).write_text((source_schema_root / name).read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_REPO_ROOT", str(repo_root))
    monkeypatch.delenv("CORTEXPILOT_RUNNER", raising=False)

    observed_runner: dict[str, str] = {}

    def _fake_execute_chain(_chain_path: Path, _mock_mode: bool) -> dict[str, object]:
        observed_runner["value"] = os.getenv("CORTEXPILOT_RUNNER", "")
        return {"run_id": "run-auto-chain"}

    monkeypatch.setattr(intake, "_execute_chain", _fake_execute_chain)

    service = intake.IntakeService()
    created = service.create(
        {
            "objective": "auto run chain env isolation",
            "allowed_paths": ["apps/orchestrator/src"],
            "mcp_tool_set": ["01-filesystem"],
        }
    )
    intake_id = created["intake_id"]

    answered = service.answer(intake_id, {"answers": ["ready"]})
    assert answered["status"] == "READY"
    assert answered["chain_run_id"] == "run-auto-chain"
    assert observed_runner["value"] == "agents"
    assert os.getenv("CORTEXPILOT_RUNNER", "") == ""


def test_intake_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = IntakeStore(root=tmp_path / "intakes")
    store.create({"objective": "safe"})
    outside_response = tmp_path / "response.json"
    outside_intake = tmp_path / "intake.json"
    outside_events = tmp_path / "events.jsonl"

    assert store.read_intake("..") == {}
    assert store.read_response("..") == {}
    with pytest.raises(ValueError, match="invalid intake_id"):
        store.append_event("..", {"event": "NOPE"})
    with pytest.raises(ValueError, match="invalid intake_id"):
        store.write_response("..", {"bad": True})

    assert not outside_response.exists()
    assert not outside_intake.exists()
    assert not outside_events.exists()


def test_run_intake_strict_acceptance_isolation_across_concurrent_requests(monkeypatch, tmp_path: Path) -> None:
    contracts_root = tmp_path / "contracts"
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", raising=False)

    class FakeIntakeService:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": f"task-{intake_id}"}

    strict_entered = threading.Event()
    release_strict = threading.Event()
    observed_runtime_options: dict[str, dict[str, object]] = {}

    class FakeOrchestrationService:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            payload = json.loads(Path(contract_path).read_text(encoding="utf-8"))
            task_id = str(payload.get("task_id", ""))
            if task_id == "task-strict":
                strict_entered.set()
                release_strict.wait(timeout=2.0)
            runtime_options = payload.get("runtime_options")
            observed_runtime_options[task_id] = runtime_options if isinstance(runtime_options, dict) else {}
            return f"run-{task_id}"

    errors: list[Exception] = []

    def _run_strict() -> None:
        try:
            main_pm_intake_helpers.run_intake(
                "strict",
                {"strict_acceptance": True},
                intake_service_cls=FakeIntakeService,
                orchestration_service=FakeOrchestrationService(),
                error_detail_fn=lambda code: {"code": code},
                current_request_id_fn=lambda: "req-strict",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    def _run_non_strict() -> None:
        try:
            main_pm_intake_helpers.run_intake(
                "non-strict",
                {"strict_acceptance": False},
                intake_service_cls=FakeIntakeService,
                orchestration_service=FakeOrchestrationService(),
                error_detail_fn=lambda code: {"code": code},
                current_request_id_fn=lambda: "req-non-strict",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread_strict = threading.Thread(target=_run_strict)
    thread_non_strict = threading.Thread(target=_run_non_strict)

    thread_strict.start()
    assert strict_entered.wait(timeout=2.0), "strict request did not start execute_task in time"
    thread_non_strict.start()
    thread_non_strict.join(timeout=2.0)
    assert not thread_non_strict.is_alive()
    release_strict.set()
    thread_strict.join(timeout=2.0)

    assert not errors
    assert observed_runtime_options["task-strict"]["strict_acceptance"] is True
    assert observed_runtime_options["task-non-strict"]["strict_acceptance"] is False
    assert os.getenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "") == ""


def test_run_intake_contract_path_uniqueness_under_high_concurrency(monkeypatch, tmp_path: Path) -> None:
    contracts_root = tmp_path / "contracts"
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_ROOT", str(contracts_root))
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.delenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", raising=False)

    class FakeIntakeService:
        def build_contract(self, intake_id: str) -> dict[str, object]:
            return {"task_id": "task_stress_same_id", "intake_id": intake_id}

    lock = threading.Lock()
    contract_paths: list[str] = []
    errors: list[Exception] = []
    run_count = 100

    class FakeOrchestrationService:
        @staticmethod
        def execute_task(contract_path: Path, mock_mode: bool = False) -> str:
            del mock_mode
            with lock:
                contract_paths.append(str(contract_path))
            return f"run-{contract_path.stem}"

    def _worker(index: int) -> None:
        try:
            result = main_pm_intake_helpers.run_intake(
                f"stress-{index}",
                {"mock": True},
                intake_service_cls=FakeIntakeService,
                orchestration_service=FakeOrchestrationService(),
                error_detail_fn=lambda code: {"code": code},
                current_request_id_fn=lambda: f"req-{index}",
            )
            path = result["contract_path"]
            assert Path(path).exists()
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(run_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5.0)

    assert not errors
    assert len(contract_paths) == run_count
    assert len(set(contract_paths)) == run_count
