import hashlib
import json
import subprocess
from pathlib import Path

from cortexpilot_orch.scheduler import scheduler as sched
from cortexpilot_orch.scheduler.scheduler import Orchestrator


SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _create_repo(base_dir: Path) -> Path:
    repo = base_dir
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    codex_home = repo / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)

    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
                    {"exec": "git", "argv_prefixes": [["git"]]},
                    {"exec": "echo", "argv_prefixes": [["echo"]]},
                ],
                "deny_substrings": ["rm -rf", "sudo", "ssh ", "scp ", "sftp ", "curl ", "wget "],
            }
        ),
        encoding="utf-8",
    )
    (policies / "agent_registry.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "agents": [
                    {
                        "agent_id": "agent-1",
                        "role": "WORKER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)
    return repo


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


def _base_contract(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "README.md", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_execute_task_baseline_commit_missing_branch(tmp_path: Path, monkeypatch) -> None:
    repo = _create_repo(tmp_path / "repo_baseline_missing")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(SCHEMA_ROOT))

    contract = _base_contract("task_baseline_missing")
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.setattr(sched, "_baseline_commit", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing")))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    runs_root_actual = Path(orch._store._runs_root)
    events_text = (runs_root_actual / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "BASELINE_COMMIT_MISSING" in events_text


def test_execute_task_agent_registry_load_error_branch(tmp_path: Path, monkeypatch) -> None:
    repo = _create_repo(tmp_path / "repo_registry_error")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(SCHEMA_ROOT))

    contract = _base_contract("task_registry_error")
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.setattr(sched.artifact_pipeline, "load_agent_registry", lambda *_args, **_kwargs: (None, "registry-load-error"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    runs_root_actual = Path(orch._store._runs_root)
    manifest = json.loads((runs_root_actual / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "registry-load-error"


def test_execute_task_assigned_agent_validation_error_branch(tmp_path: Path, monkeypatch) -> None:
    repo = _create_repo(tmp_path / "repo_agent_invalid")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(SCHEMA_ROOT))

    contract = _base_contract("task_agent_invalid")
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.setattr(sched.artifact_pipeline, "load_agent_registry", lambda *_args, **_kwargs: ({"agents": []}, None))
    monkeypatch.setattr(sched.artifact_pipeline, "validate_assigned_agent", lambda *_args, **_kwargs: (False, "agent-invalid"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    runs_root_actual = Path(orch._store._runs_root)
    manifest = json.loads((runs_root_actual / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "agent-invalid"


def test_execute_task_codex_home_resolve_error_branch(tmp_path: Path, monkeypatch) -> None:
    repo = _create_repo(tmp_path / "repo_codex_home_error")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(SCHEMA_ROOT))

    contract = _base_contract("task_codex_home_error")
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    monkeypatch.setattr(sched.artifact_pipeline, "load_agent_registry", lambda *_args, **_kwargs: ({"agents": []}, None))
    monkeypatch.setattr(sched.artifact_pipeline, "validate_assigned_agent", lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(sched.policy_pipeline, "find_registry_entry", lambda *_args, **_kwargs: {"agent_id": "agent-1"})
    monkeypatch.setattr(sched.policy_pipeline, "resolve_codex_home", lambda *_args, **_kwargs: (None, "codex-home-missing"))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=False)

    runs_root_actual = Path(orch._store._runs_root)
    manifest = json.loads((runs_root_actual / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "codex-home-missing"
