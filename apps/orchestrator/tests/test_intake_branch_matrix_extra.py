import builtins
import json
import sys
import types
from pathlib import Path

import pytest

from cortexpilot_orch.planning import intake


def test_extract_parallelism_positive_after_regex_fix() -> None:
    assert intake._extract_parallelism(["并行度=4"]) == 4
    assert intake._extract_parallelism(["并行度 = 2", "其他约束"]) == 2
    assert intake._extract_parallelism(["并行度=0"]) is None


def test_generate_plan_bundle_fallback_on_non_object_plan(monkeypatch) -> None:
    payload = {
        "objective": "bundle matrix",
        "allowed_paths": ["apps/", "docs/"],
        "constraints": ["并行度=2"],
        "mcp_tool_set": ["01-filesystem"],
    }

    monkeypatch.setattr(intake, "_agents_available", lambda: True)
    monkeypatch.setattr(
        intake,
        "_run_agent",
        lambda *_args, **_kwargs: {
            "bundle_id": "bundle-x",
            "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
            "plans": ["bad-plan"],
        },
    )

    bundle, note = intake.generate_plan_bundle(payload, ["a1"])
    assert note.startswith("plan_bundle_fallback:")
    assert isinstance(bundle.get("plans"), list)
    assert len(bundle["plans"]) == 2
    assert bundle["plans"][0]["allowed_paths"] == ["apps/"]
    assert bundle["plans"][1]["allowed_paths"] == ["docs/"]
    assert bundle["plans"][0]["owner_agent"]["role"] == "TECH_LEAD"
    assert bundle["plans"][1]["owner_agent"]["role"] == "TECH_LEAD"
    assert bundle["plans"][0]["assigned_agent"]["role"] == "WORKER"
    assert bundle["plans"][1]["assigned_agent"]["role"] == "WORKER"


def test_generate_plan_bundle_rebalance_overlap_paths(monkeypatch) -> None:
    payload = {
        "objective": "split plans",
        "allowed_paths": ["apps/", "docs/", "scripts/"],
        "constraints": ["并行度=2"],
        "mcp_tool_set": ["01-filesystem"],
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
    }

    def _bundle(*_args, **_kwargs):
        return {
            "bundle_id": "bundle-1",
            "created_at": "2026-02-08T00:00:00Z",
            "objective": "split plans",
            "owner_agent": {"role": "PM", "agent_id": "pm-1"},
            "plans": [
                {
                    "plan_id": "plan-a",
                    "plan_type": "BACKEND",
                    "task_type": "IMPLEMENT",
                    "spec": "x",
                    "allowed_paths": ["apps/"],
                    "mcp_tool_set": ["01-filesystem"],
                },
                {
                    "plan_id": "plan-b",
                    "plan_type": "FRONTEND",
                    "task_type": "IMPLEMENT",
                    "spec": "y",
                    "allowed_paths": ["apps/core/"],
                    "mcp_tool_set": ["01-filesystem"],
                },
                {
                    "plan_id": "plan-c",
                    "plan_type": "OPS",
                    "task_type": "IMPLEMENT",
                    "spec": "z",
                    "allowed_paths": ["ops/"],
                    "mcp_tool_set": ["01-filesystem"],
                },
            ],
        }

    monkeypatch.setattr(intake, "_agents_available", lambda: True)
    monkeypatch.setattr(intake, "_run_agent", _bundle)

    bundle, note = intake.generate_plan_bundle(payload, ["answer"])

    assert note == ""
    assert len(bundle["plans"]) == 2
    assert bundle["plans"][0]["allowed_paths"]
    assert bundle["plans"][1]["allowed_paths"]
    assert bundle["owner_agent"]["role"] == "PM"
    assert bundle["owner_agent"]["agent_id"] == "agent-1"


def test_build_task_chain_invalid_plan_entries() -> None:
    with pytest.raises(ValueError, match="missing plans"):
        intake.build_task_chain_from_bundle({"bundle_id": "x", "plans": []}, {"role": "PM", "agent_id": "agent-1"})

    with pytest.raises(ValueError, match="plan invalid"):
        intake.build_task_chain_from_bundle(
            {"bundle_id": "x", "plans": ["bad"]},
            {"role": "PM", "agent_id": "agent-1"},
        )


def test_intake_service_answer_chain_failure_and_bundle_note(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    monkeypatch.setattr(service._validator, "validate_report", lambda *_args, **_kwargs: None)

    intake_payload = {
        "objective": "service branch",
        "allowed_paths": ["apps/"],
        "mcp_tool_set": ["01-filesystem"],
    }
    intake_id = service._store.create(intake_payload)

    plan = {
        "plan_id": "plan-12345678",
        "task_id": "task-12345678",
        "plan_type": "BACKEND",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "task_type": "IMPLEMENT",
        "spec": "ok",
        "artifacts": [],
        "required_outputs": [{"name": "patch.diff", "type": "patch", "acceptance": "ok"}],
        "allowed_paths": ["apps/"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "never", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
    }
    plan_bundle = {
        "bundle_id": "bundle-1234",
        "created_at": "2026-02-08T00:00:00Z",
        "objective": "service branch",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "plans": [plan],
    }

    monkeypatch.setattr(intake, "generate_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(intake, "generate_plan_bundle", lambda *_args, **_kwargs: (plan_bundle, "bundle fallback note"))
    monkeypatch.setattr(intake, "build_task_chain_from_bundle", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("chain failed")))

    response = service.answer(
        intake_id,
        {"answers": ["yes"], "auto_run_chain": False, "mock_chain": True},
    )

    assert response["status"] == "READY"
    assert "task_chain" not in response
    assert "bundle fallback note" in response.get("notes", "")


def test_intake_service_build_contract_artifacts_non_list(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()

    intake_payload = {
        "objective": "build contract",
        "allowed_paths": ["docs/"],
        "mcp_tool_set": ["01-filesystem"],
        "search_queries": ["query-a", "query-b"],
    }
    intake_id = service._store.create(intake_payload)

    response = {
        "intake_id": intake_id,
        "status": "READY",
        "questions": [],
        "plan": {"plan_id": "p", "task_id": "t"},
    }
    service._store.write_response(intake_id, response)

    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-x",
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "inputs": {"artifacts": "not-a-list"},
        },
    )

    contract = service.build_contract(intake_id)

    assert isinstance(contract, dict)
    assert contract.get("handoff_chain", {}).get("enabled") is True
    artifacts = contract.get("inputs", {}).get("artifacts", [])
    assert isinstance(artifacts, list)
    assert any(item.get("name") == "search_requests.json" for item in artifacts)

    search_path = service._store._intake_dir(intake_id) / "search_requests.json"
    payload = json.loads(search_path.read_text(encoding="utf-8"))
    assert payload["queries"] == ["query-a", "query-b"]


def test_intake_service_build_contract_compacts_empty_browser_policy_fields(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()

    intake_payload = {
        "objective": "compact browser policy",
        "allowed_paths": ["docs/"],
        "mcp_tool_set": ["01-filesystem"],
        "browser_policy": {
            "profile_mode": "ephemeral",
            "profile_ref": {"profile_dir": "", "profile_name": ""},
            "cookie_ref": {"cookie_path": ""},
            "stealth_mode": "none",
            "human_behavior": {"enabled": False, "level": "low"},
        },
    }
    intake_id = service._store.create(intake_payload)

    response = {
        "intake_id": intake_id,
        "status": "READY",
        "questions": [],
        "plan": {"plan_id": "p", "task_id": "t"},
    }
    service._store.write_response(intake_id, response)

    monkeypatch.setattr(
        intake,
        "compile_plan",
        lambda _plan: {
            "task_id": "task-policy",
            "owner_agent": {"role": "PM", "agent_id": "agent-1"},
            "inputs": {"artifacts": []},
        },
    )

    contract = service.build_contract(intake_id)

    assert isinstance(contract, dict)
    browser_policy = contract.get("browser_policy", {})
    assert browser_policy.get("profile_mode") == "ephemeral"
    assert "profile_ref" not in browser_policy
    assert "cookie_ref" not in browser_policy


def test_intake_agents_available_and_strip_model_input_missing(monkeypatch) -> None:
    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "agents":
            raise ImportError("forced")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    assert intake._agents_available() is False

    monkeypatch.setitem(sys.modules, "agents.run", types.ModuleType("agents.run"))
    with pytest.raises(RuntimeError, match="ModelInputData missing"):
        intake._strip_model_input_ids(types.SimpleNamespace(model_data=None))


def test_intake_run_agent_local_key_fallback_and_output_errors(monkeypatch) -> None:
    class _Cfg:
        agents_base_url = "http://127.0.0.1:1456/v1"
        openai_api_key = ""
        equilibrium_api_key = "eq-key"
        agents_api = "responses"
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

    class _Result:
        def __init__(self, output: str) -> None:
            self.final_output = output

        async def stream_events(self):
            if self.final_output == "__stream__":
                yield None
            return

    class _RunnerOK:
        @staticmethod
        def run_streamed(*_args, **_kwargs):
            return _Result(json.dumps({"questions": ["q1"]}))

    class _RunnerMissing:
        @staticmethod
        def run_streamed(*_args, **_kwargs):
            return _Result("")

    class _RunnerList:
        @staticmethod
        def run_streamed(*_args, **_kwargs):
            return _Result("[]")

    records: dict[str, object] = {}

    def _build_agents_module(runner_cls):
        mod = types.ModuleType("agents")
        mod.Agent = DummyAgent
        mod.ModelSettings = DummyModelSettings
        mod.RunConfig = DummyRunConfig
        mod.Runner = runner_cls
        mod.set_default_openai_api = lambda mode: records.setdefault("api_mode", mode)
        mod.set_default_openai_client = lambda client: records.setdefault("client", client)
        return mod

    class DummyAsyncOpenAI:
        def __init__(self, api_key: str, base_url: str | None = None) -> None:
            self.api_key = api_key
            self.base_url = base_url

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncOpenAI = DummyAsyncOpenAI

    monkeypatch.setattr(intake, "get_runner_config", lambda: _Cfg())
    monkeypatch.setitem(sys.modules, "openai", openai_mod)

    monkeypatch.setitem(sys.modules, "agents", _build_agents_module(_RunnerOK))
    out = intake._run_agent("prompt", "inst")
    assert out == {"questions": ["q1"]}
    assert isinstance(records.get("client"), DummyAsyncOpenAI)

    monkeypatch.setitem(sys.modules, "agents", _build_agents_module(_RunnerMissing))
    with pytest.raises(RuntimeError, match="planner output missing"):
        intake._run_agent("prompt", "inst")

    monkeypatch.setitem(sys.modules, "agents", _build_agents_module(_RunnerList))
    with pytest.raises(RuntimeError, match="planner output not object"):
        intake._run_agent("prompt", "inst")


def test_intake_service_answer_failure_and_chain_run_failed(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))

    service = intake.IntakeService()
    monkeypatch.setattr(service._validator, "validate_report", lambda *_args, **_kwargs: None)

    intake_payload = {
        "objective": "service failure branches",
        "allowed_paths": ["apps/"],
        "mcp_tool_set": ["01-filesystem"],
    }
    intake_id = service._store.create(intake_payload)

    good_plan = {
        "plan_id": "plan-12345678",
        "task_id": "task-12345678",
        "plan_type": "BACKEND",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "task_type": "IMPLEMENT",
        "spec": "ok",
        "artifacts": [],
        "required_outputs": [{"name": "patch.diff", "type": "patch", "acceptance": "ok"}],
        "allowed_paths": ["apps/"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "never", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
    }
    good_bundle = {
        "bundle_id": "bundle-1234",
        "created_at": "2026-02-08T00:00:00Z",
        "objective": "service failure branches",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "plans": [good_plan],
    }

    # 1) validator failure path -> FAILED response branch
    monkeypatch.setattr(intake, "generate_plan", lambda *_args, **_kwargs: good_plan)
    monkeypatch.setattr(intake, "generate_plan_bundle", lambda *_args, **_kwargs: (good_bundle, ""))
    monkeypatch.setattr(service._validator, "validate_report", lambda payload, schema: (_ for _ in ()).throw(RuntimeError("bad schema")) if schema == "plan.schema.json" else None)

    failed = service.answer(intake_id, {"answers": ["x"]})
    assert failed["status"] == "FAILED"
    assert "bad schema" in failed["notes"]

    # 2) chain_run_failed branch when auto_run_chain enabled
    monkeypatch.setattr(service._validator, "validate_report", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(intake, "build_task_chain_from_bundle", lambda *_args, **_kwargs: {"chain_id": "c1", "steps": []})
    monkeypatch.setattr(intake, "_execute_chain", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom run")))

    ready = service.answer(intake_id, {"answers": ["x"], "auto_run_chain": True})
    assert ready["status"] == "READY"
    assert "chain_run_failed" in ready.get("notes", "")


def test_intake_lastmile_helper_branches(tmp_path: Path, monkeypatch) -> None:
    payload = {
        "objective": "lastmile",
        "allowed_paths": ["apps/"],
        "mcp_tool_set": ["01-filesystem"],
        "audit_only": True,
    }
    plan = intake._build_plan_fallback(payload, ["ok"])
    assert plan.get("audit_only") is True

    class DummyModelInputData:
        def __init__(self, input, instructions=None) -> None:  # noqa: A002
            self.input = input
            self.instructions = instructions

    run_mod = types.ModuleType("agents.run")
    run_mod.ModelInputData = DummyModelInputData
    monkeypatch.setitem(sys.modules, "agents.run", run_mod)

    sanitized = intake._strip_model_input_ids(types.SimpleNamespace(model_data=None))
    assert sanitized.input == []
    assert sanitized.instructions is None

    monkeypatch.setattr(intake, "_agents_available", lambda: False)
    bundle, note = intake.generate_plan_bundle(payload, [])
    assert note.startswith("plan_bundle_fallback")
    assert isinstance(bundle.get("plans"), list)

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))
    service = intake.IntakeService()
    intake_id = service._store.create(payload)
    service._store.write_response(intake_id, {"intake_id": intake_id, "status": "READY", "questions": []})
    assert service.build_contract(intake_id) is None
