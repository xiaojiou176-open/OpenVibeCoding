import asyncio
import builtins
import json
import sys
import types
from pathlib import Path

import pytest

from cortexpilot_orch.runners import agents_runner
from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.store.run_store import RunStore


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    schema_path = schema_root / schema_name
    import hashlib

    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _base_contract(task_id: str, instruction: str = "mock") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": instruction, "artifacts": _output_schema_artifacts("worker")},
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


def test_agents_patch_import_failure(monkeypatch) -> None:
    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name.startswith("mcp"):
            raise ImportError("forced mcp import error")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    ok1, detail1 = agents_runner._patch_mcp_codex_event_notifications()
    ok2, detail2 = agents_runner._patch_mcp_initialized_notification()
    assert ok1 is False and "mcp import failed" in detail1
    assert ok2 is False and "mcp import failed" in detail2


def test_materialize_worker_codex_home_and_probe(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    store = RunStore(runs_root=runs_root)

    # Missing role/base config should fail loudly.
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-role"))
    monkeypatch.setenv("CORTEXPILOT_CODEX_BASE_HOME", str(tmp_path / "missing-base"))
    with pytest.raises(RuntimeError, match="role config missing"):
        agents_runner._materialize_worker_codex_home(
            store,
            "run-1",
            "task-1",
            ["01-filesystem"],
            "WORKER",
            tmp_path,
            skip_role_prompt=True,
        )

    role_home = tmp_path / "role-home"
    base_home = tmp_path / "base-home"
    role_home.mkdir(parents=True, exist_ok=True)
    base_home.mkdir(parents=True, exist_ok=True)

    (role_home / "config.toml").write_text('model_provider = "codex_equilibrium"\nmodel = "gpt-5.2-codex"\n', encoding="utf-8")
    (base_home / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "codex_equilibrium"',
                'model = "gpt-5.2-codex"',
                '',
                '[mcp_servers."01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                '',
            ]
        ),
        encoding="utf-8",
    )
    (role_home / "requirements.toml").write_text("[]", encoding="utf-8")

    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.setenv("CORTEXPILOT_CODEX_BASE_HOME", str(base_home))

    target = agents_runner._materialize_worker_codex_home(
        store,
        "run-1",
        "task-1",
        ["01-filesystem"],
        "WORKER",
        tmp_path,
        skip_role_prompt=True,
    )
    merged = (target / "config.toml").read_text(encoding="utf-8")
    assert "developer_instructions" in merged
    assert '[mcp_servers."01-filesystem"]' in merged or "[mcp_servers.01-filesystem]" in merged

    alias_target = agents_runner._materialize_worker_codex_home(
        store,
        "run-1",
        "task-alias",
        ["codex"],
        "WORKER",
        tmp_path,
        skip_role_prompt=True,
    )
    alias_merged = (alias_target / "config.toml").read_text(encoding="utf-8")
    assert '[mcp_servers."01-filesystem"]' in alias_merged or "[mcp_servers.01-filesystem]" in alias_merged

    (base_home / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "codex_equilibrium"',
                'model = "gpt-5.2-codex"',
                '',
                '[mcp_servers."devtools-04-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                '',
            ]
        ),
        encoding="utf-8",
    )
    devtools_alias_target = agents_runner._materialize_worker_codex_home(
        store,
        "run-1",
        "task-devtools-alias",
        ["codex"],
        "WORKER",
        tmp_path,
        skip_role_prompt=True,
    )
    devtools_alias_merged = (devtools_alias_target / "config.toml").read_text(encoding="utf-8")
    assert (
        '[mcp_servers."devtools-04-filesystem"]' in devtools_alias_merged
        or "[mcp_servers.devtools-04-filesystem]" in devtools_alias_merged
    )

    (base_home / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "codex_equilibrium"',
                'model = "gpt-5.2-codex"',
                '',
                '[mcp_servers."vcs-01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                '',
            ]
        ),
        encoding="utf-8",
    )
    vcs_target = agents_runner._materialize_worker_codex_home(
        store,
        "run-1",
        "task-vcs-fallback",
        ["01-filesystem"],
        "WORKER",
        tmp_path,
        skip_role_prompt=True,
    )
    vcs_merged = (vcs_target / "config.toml").read_text(encoding="utf-8")
    assert '[mcp_servers."vcs-01-filesystem"]' in vcs_merged or "[mcp_servers.vcs-01-filesystem]" in vcs_merged


def test_materialize_worker_codex_home_fallback_to_default_catalog(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    store = RunStore(runs_root=runs_root)

    role_home = tmp_path / "role-home"
    home_root = tmp_path / "home"
    default_catalog = home_root / ".codex"
    role_home.mkdir(parents=True, exist_ok=True)
    default_catalog.mkdir(parents=True, exist_ok=True)

    (role_home / "config.toml").write_text(
        'model_provider = "codex_equilibrium"\nmodel = "gpt-5.2-codex"\n',
        encoding="utf-8",
    )
    (default_catalog / "config.toml").write_text(
        '\n'.join(
            [
                'model_provider = "codex_equilibrium"',
                'model = "gpt-5.2-codex"',
                '',
                '[mcp_servers."vcs-01-filesystem"]',
                'command = ["python", "-m", "dummy"]',
                '',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(home_root))
    monkeypatch.setenv("CODEX_HOME", str(role_home))
    monkeypatch.delenv("CORTEXPILOT_CODEX_BASE_HOME", raising=False)

    target = agents_runner._materialize_worker_codex_home(
        store,
        "run-fallback",
        "task-fallback",
        ["01-filesystem"],
        "WORKER",
        tmp_path,
        skip_role_prompt=True,
    )

    merged = (target / "config.toml").read_text(encoding="utf-8")
    assert '[mcp_servers."vcs-01-filesystem"]' in merged or "[mcp_servers.vcs-01-filesystem]" in merged


async def _collect_probe_payload() -> dict:
    class Tool:
        def __init__(self, name: str) -> None:
            self.name = name

    class WithTools:
        async def list_tools(self):
            return [Tool("fs.read"), Tool("browser/open"), Tool("search")]

    return await agents_runner._probe_mcp_ready(WithTools(), ["01-filesystem"])


def test_probe_ready_and_snapshot_helpers() -> None:
    # no list_tools branch
    payload = agents_runner.asyncio.run(agents_runner._probe_mcp_ready(object(), ["01-filesystem"]))
    assert payload["probe"] == "skipped"

    with_tools = agents_runner.asyncio.run(_collect_probe_payload())
    assert with_tools["probe"] == "ok"
    assert with_tools["tools_count"] == 3

    class ModelDumpError:
        def model_dump(self):
            raise RuntimeError("boom")

        def to_dict(self):
            return {"ok": True}

    snap = agents_runner._result_snapshot(ModelDumpError())
    assert snap == {}

    class DictOnly:
        def __init__(self) -> None:
            self.value = 1

    assert agents_runner._result_snapshot(DictOnly())["value"] == 1


def test_resolve_codex_base_url_fallback_to_equilibrium(monkeypatch) -> None:
    monkeypatch.delenv("CORTEXPILOT_CODEX_BASE_URL", raising=False)
    monkeypatch.delenv("CORTEXPILOT_PROVIDER_BASE_URL", raising=False)
    monkeypatch.setattr(agents_runner, "_equilibrium_healthcheck", lambda *_args, **_kwargs: True)
    assert agents_runner._resolve_codex_base_url() == "http://127.0.0.1:1456/v1"


def test_resolve_codex_base_url_prefers_agents_base(monkeypatch) -> None:
    monkeypatch.delenv("CORTEXPILOT_CODEX_BASE_URL", raising=False)
    monkeypatch.setenv("CORTEXPILOT_PROVIDER_BASE_URL", "http://127.0.0.1:2456/v1")
    assert agents_runner._resolve_codex_base_url() == "http://127.0.0.1:2456/v1"


def test_agents_small_helpers(monkeypatch) -> None:
    assert agents_runner._is_valid_thread_id("urn:uuid:123e4567-e89b-12d3-a456-426614174000")
    assert agents_runner._is_valid_thread_id("thread-abc_1")
    assert not agents_runner._is_valid_thread_id("  ")

    assert agents_runner._is_codex_reply_thread_id("urn:uuid:123e4567-e89b-12d3-a456-426614174000")
    assert agents_runner._is_codex_reply_thread_id("123e4567-e89b-12d3-a456-426614174000")
    assert not agents_runner._is_codex_reply_thread_id("thread-abc_1")

    path = agents_runner._mock_output_path(
        {
            "inputs": {"spec": "outside allowed"},
            "allowed_paths": ["apps/"],
            "required_outputs": [{"name": "patch.diff"}],
        }
    )
    assert path == "README.md"

    assert not agents_runner._path_allowed("apps/a.txt", ["apps/"])
    assert agents_runner._path_allowed("apps/a.txt", ["apps/a.txt"])

    monkeypatch.setenv("CORTEXPILOT_CODEX_PROFILE", "")
    profile = agents_runner._resolve_profile()
    assert profile is None or isinstance(profile, str)

    assert agents_runner._agent_role({"role": "worker"}) == "WORKER"
    assert agents_runner._shell_policy({"tool_permissions": {"shell": "on-request"}}) == "on-request"
    assert agents_runner._handoff_required({"owner_agent": {"role": "PM"}, "assigned_agent": {"role": "WORKER"}})


def test_agents_strip_model_input_ids(monkeypatch) -> None:
    class DummyModelInputData:
        def __init__(self, input, instructions=None) -> None:  # noqa: A002
            self.input = input
            self.instructions = instructions

    run_mod = types.ModuleType("agents.run")
    run_mod.ModelInputData = DummyModelInputData
    monkeypatch.setitem(sys.modules, "agents.run", run_mod)

    payload = types.SimpleNamespace(
        model_data=types.SimpleNamespace(
            input=[{"id": "id-1", "response_id": "resp-1", "v": 1}, "raw"],
            instructions="keep",
        )
    )
    sanitized = agents_runner._strip_model_input_ids(payload)
    assert sanitized.input[0] == {"v": 1}
    assert sanitized.instructions == "keep"


def _install_fake_agents_sdk(monkeypatch) -> None:
    class DummyAgent:
        def __init__(self, name: str, instructions: str, mcp_servers: list, **kwargs):
            self.name = name
            self.instructions = instructions
            self.mcp_servers = mcp_servers
            self.kwargs = kwargs

    class DummyModelSettings:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyRunConfig:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class DummyRunner:
        @staticmethod
        def run_streamed(agent, prompt, **kwargs):
            del agent, prompt, kwargs
            class _Result:
                final_output = None
                async def stream_events(self):
                    if self.final_output == "__stream__":
                        yield None
                    return
                def cancel(self, mode="immediate"):
                    return None
                @property
                def is_complete(self):
                    return True
            return _Result()

    agents_mod = types.ModuleType("agents")
    agents_mod.Agent = DummyAgent
    agents_mod.ModelSettings = DummyModelSettings
    agents_mod.RunConfig = DummyRunConfig
    agents_mod.Runner = DummyRunner
    agents_mod.set_default_openai_api = lambda *_args, **_kwargs: None
    agents_mod.set_default_openai_client = None

    mcp_mod = types.ModuleType("agents.mcp")
    mcp_mod.MCPServerStdio = object

    monkeypatch.setitem(sys.modules, "agents", agents_mod)
    monkeypatch.setitem(sys.modules, "agents.mcp", mcp_mod)


def test_agents_runner_fixed_output_bypass(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_fixed")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(agents_runner.ContractValidator, "validate_contract", lambda self, contract: contract)

    runner = AgentsRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"
    fixed_json = json.dumps(
        {
            "task_id": "task_fixed",
            "status": "SUCCESS",
            "summary": "fixed",
            "evidence_refs": {},
            "failure": None,
        },
        ensure_ascii=False,
    )
    instruction = f"RETURN EXACTLY THIS JSON\n{fixed_json}\nOUTPUT JSON ONLY"
    contract = _base_contract("task_fixed", instruction=instruction)
    contract["mcp_tool_set"] = ["disabled"]

    result = runner.run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "SUCCESS"
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "AGENT_FIXED_OUTPUT_BYPASS" in events_text


def test_agents_runner_missing_mcp_tool_set(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_no_mcp")
    monkeypatch.setenv("CORTEXPILOT_RUN_ID", run_id)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _install_fake_agents_sdk(monkeypatch)
    monkeypatch.setattr(agents_runner.ContractValidator, "validate_contract", lambda self, contract: contract)

    runner = AgentsRunner(store)
    repo_root = Path(__file__).resolve().parents[3]
    schema_path = repo_root / "schemas" / "task_result.v1.json"

    contract = _base_contract("task_no_mcp")
    contract["mcp_tool_set"] = []

    result = runner.run_contract(contract, tmp_path, schema_path, mock_mode=False)
    assert result["status"] == "FAILED"
    assert "mcp_tool_set missing or empty" in result["summary"]


def test_agents_patch_success_paths() -> None:
    patched_codex, detail_codex = agents_runner._patch_mcp_codex_event_notifications()
    patched_init, detail_init = agents_runner._patch_mcp_initialized_notification()

    assert patched_codex is True
    assert patched_init is True
    assert detail_codex in {"patched", "already supported", "already patched"}
    assert detail_init in {"patched", "already patched"}

    # second call should be idempotent
    patched_codex_2, detail_codex_2 = agents_runner._patch_mcp_codex_event_notifications()
    patched_init_2, detail_init_2 = agents_runner._patch_mcp_initialized_notification()
    assert patched_codex_2 is True and detail_codex_2 == "already patched"
    assert patched_init_2 is True and detail_init_2 == "already patched"
