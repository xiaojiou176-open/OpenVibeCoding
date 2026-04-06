import json
import subprocess
from pathlib import Path

from cortexpilot_orch.runners.agents_runner import AgentsRunner
from cortexpilot_orch.runners.app_server_runner import AppServerRunner
from cortexpilot_orch.runners import execution_adapter as execution_adapter_module
from cortexpilot_orch.scheduler import scheduler as sched
from cortexpilot_orch.scheduler import scheduler_bridge_runtime as bridge_runtime
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.run_store import RunStore


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _contract(task_id: str) -> dict:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    schema_path = schema_root / schema_name
    import hashlib

    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": [{"name": "output_schema.worker", "uri": f"schemas/{schema_name}", "sha256": sha}]},
        "required_outputs": [{"name": "output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_scheduler_runner_selection_and_search_signature(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "agents")
    assert isinstance(sched._select_runner({}, store), AgentsRunner)
    assert isinstance(
        sched._select_runner({"runtime_options": {"runner": "claude"}}, store),
        execution_adapter_module.ClaudeExecutionAdapter,
    )

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "app-server")
    assert isinstance(sched._select_runner({}, store), AppServerRunner)

    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")
    assert isinstance(sched._select_runner({}, store), execution_adapter_module.CodexExecutionAdapter)

    class DummyToolRunner:
        pass

    with pytest.raises(TypeError):
        sched._run_search_pipeline("run-1", DummyToolRunner(), "bad")


def test_scheduler_adapter_factory_resolves_build_execution_adapter_name(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    calls: list[dict[str, object]] = []

    class DummyRunner:
        def run_contract(self, *_args, **_kwargs):
            return {"status": "SUCCESS"}

    class FakeAdapterModule:
        @staticmethod
        def build_execution_adapter(**kwargs):
            assert kwargs.get("run_store") is store
            calls.append(dict(kwargs))
            return DummyRunner()

    def _fake_import_module(name: str):
        if name == "cortexpilot_orch.runners.execution_adapter":
            return FakeAdapterModule
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(bridge_runtime, "import_module", _fake_import_module)
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "codex")

    runner = sched._select_runner({}, store)
    assert isinstance(runner, DummyRunner)
    assert calls == [{"run_store": store, "runner_name": "codex"}]


def test_scheduler_runner_selection_ignores_provider_override(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "app-server")

    selected = sched._select_runner({"runtime_options": {"provider": "gemini"}}, store)
    assert isinstance(selected, AppServerRunner)


def test_scheduler_replay_error_paths(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_dir = runs_root / "run-replay"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps({"run_id": "run-replay", "task_id": "t", "status": "RUNNING"}), encoding="utf-8")

    class BoomReplayRunner:
        def __init__(self, *_args, **_kwargs):
            pass

        def replay(self, *_args, **_kwargs):
            raise RuntimeError("boom replay")

        def verify(self, *_args, **_kwargs):
            raise RuntimeError("boom verify")

        def reexecute(self, *_args, **_kwargs):
            raise RuntimeError("boom reexec")

    monkeypatch.setattr(sched, "ReplayRunner", BoomReplayRunner)

    orch = Orchestrator(repo)
    replay = orch.replay_run("run-replay")
    verify = orch.replay_verify("run-replay")
    reexec = orch.replay_reexec("run-replay")
    assert replay["status"] == "fail"
    assert verify["status"] == "fail"
    assert reexec["status"] == "fail"


import pytest


def test_scheduler_temporal_workflow_fast_paths(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))

    contract_path = repo / "contract.json"
    _write_json(contract_path, _contract("task-temporal"))

    monkeypatch.setenv("CORTEXPILOT_TEMPORAL_WORKFLOW", "1")
    monkeypatch.delenv("CORTEXPILOT_TEMPORAL_ACTIVITY", raising=False)

    monkeypatch.setattr(sched, "run_workflow", lambda *_args, **_kwargs: {"run_id": "wf-123"})
    orch = Orchestrator(repo)
    assert orch.execute_task(contract_path, mock_mode=True) == "wf-123"

    def _raise(*_args, **_kwargs):
        raise RuntimeError("temporal unavailable")

    monkeypatch.setattr(sched, "run_workflow", _raise)
    monkeypatch.setattr(sched, "temporal_required", lambda: True)
    failed_run_id = orch.execute_task(contract_path, mock_mode=True)
    runs_root_actual = Path(orch._store._runs_root)
    manifest = json.loads((runs_root_actual / failed_run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert "temporal workflow failed" in manifest["failure_reason"]


def test_scheduler_observability_branches(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo_obs"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime_obs"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.delenv("CORTEXPILOT_TEMPORAL_WORKFLOW", raising=False)

    contract_path = repo / "contract_obs.json"
    _write_json(contract_path, _contract("task-observability"))

    monkeypatch.setattr(sched, "ensure_tracing", lambda: (_ for _ in ()).throw(RuntimeError("tracing down")))
    monkeypatch.setattr(sched, "_write_contract_signature", lambda *_args, **_kwargs: (None, None))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    runs_root_actual = Path(orch._store._runs_root)
    manifest = json.loads((runs_root_actual / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert "observability required" in manifest["failure_reason"]

    monkeypatch.setattr(sched, "ensure_tracing", lambda: {"enabled": False, "backend": "off"})
    monkeypatch.setattr(sched, "check_schema_registry", lambda *_args, **_kwargs: {"status": "ok"})
    monkeypatch.setattr(sched, "validate_mcp_tools", lambda *_args, **_kwargs: {"ok": False, "reason": "blocked"})
    monkeypatch.setattr(sched, "_write_contract_signature", lambda *_args, **_kwargs: (None, None))

    run_id_2 = orch.execute_task(contract_path, mock_mode=True)
    events_text = (runs_root_actual / run_id_2 / "events.jsonl").read_text(encoding="utf-8")
    assert "OBSERVABILITY_DISABLED" in events_text
