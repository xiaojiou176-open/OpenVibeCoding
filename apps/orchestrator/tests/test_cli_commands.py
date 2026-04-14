import json
from pathlib import Path

import subprocess

from typer.testing import CliRunner

from openvibecoding_orch import cli
from openvibecoding_orch.cli import app
import hashlib


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
    schema_name = "agent_task_result.v1.json"
    if role.lower() in {"reviewer"}:
        schema_name = "review_report.v1.json"
    if role.lower() in {"test", "test_runner"}:
        schema_name = "test_report.v1.json"
    schema_path = schema_root / schema_name
    sha = hashlib.sha256(schema_path.read_bytes()).hexdigest()
    return [
        {
            "name": f"output_schema.{role.lower()}",
            "uri": f"schemas/{schema_name}",
            "sha256": sha,
        }
    ]


def _contract(task_id: str, output_name: str = "README.md") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "write output", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": output_name, "type": "file", "acceptance": "ok"}],
        "allowed_paths": [output_name],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
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


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def create_tiny_repo(base_dir: Path) -> Path:
    repo = base_dir
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
                    {"exec": "git", "argv_prefixes": [["git"]]},
                    {"exec": "echo", "argv_prefixes": [["echo"]]},
                    {"exec": "python", "argv_prefixes": [["python"], ["python", "-m"]]},
                    {"exec": "python3", "argv_prefixes": [["python3"], ["python3", "-m"]]},
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
                    },
                    {
                        "agent_id": "agent-1",
                        "role": "PM",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md", "policies/command_allowlist.json", "policies/agent_registry.json"], repo)
    _git(["git", "commit", "-m", "init"], repo)
    return repo


def test_cli_init_and_doctor(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))

    runner = CliRunner()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert (runtime_root / "runs").exists()
    assert (runtime_root / "locks").exists()

    repo = create_tiny_repo(tmp_path / "repo_doctor")
    monkeypatch.chdir(repo)
    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exit_code == 0
    assert "git_head" in doctor.output
    assert "ok" in doctor.output


def test_cli_run_and_run_chain(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_root = repo_root / "schemas"
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    contracts_root = tmp_path / "contracts"

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_SCHEMA_ROOT", str(schema_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))

    repo = create_tiny_repo(tmp_path / "repo_run")
    monkeypatch.chdir(repo)

    contract = _contract("cli_task_01")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["run", str(contract_path), "--mock", "--tail-format", "pretty", "--tail-level", "INFO"])
    assert result.exit_code == 0
    assert "run_id=" in result.output

    force_called = {"ok": False}

    def _fake_release(paths):
        force_called["ok"] = True

    monkeypatch.setattr(cli, "release_lock", _fake_release)
    result_force = runner.invoke(app, ["run", str(contract_path), "--mock", "--force-unlock"])
    assert result_force.exit_code == 0
    assert force_called["ok"] is True

    run_id = result.output.strip().split("run_id=")[-1]
    manifest_path = runs_root / run_id / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("status") == "SUCCESS"

    chain = {
        "chain_id": "chain_cli_01",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "step-1",
                "kind": "contract",
                "payload": _contract("chain_step_1", "file_a.txt"),
                "context_policy": {"mode": "inherit"},
            },
            {
                "name": "step-2",
                "kind": "contract",
                "payload": _contract("chain_step_2", "file_b.txt"),
                "depends_on": ["step-1"],
                "context_policy": {"mode": "inherit"},
            },
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")
    chain_result = runner.invoke(app, ["run-chain", str(chain_path), "--mock", "--tail-format", "jsonl", "--tail-level", "WARN"])
    assert chain_result.exit_code == 0
    assert "\"status\": \"SUCCESS\"" in chain_result.output


def test_cli_queue_and_session_alias(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_root = repo_root / "schemas"
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    contracts_root = tmp_path / "contracts"
    alias_path = tmp_path / "alias_map.json"

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_SCHEMA_ROOT", str(schema_root))
    monkeypatch.setenv("OPENVIBECODING_CONTRACT_ROOT", str(contracts_root))
    monkeypatch.setenv("OPENVIBECODING_SESSION_ALIAS_PATH", str(alias_path))

    repo = create_tiny_repo(tmp_path / "repo_queue")
    monkeypatch.chdir(repo)

    contract = _contract("queue_task_01", "queue.txt")
    contract_path = tmp_path / "queue_contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    runner = CliRunner()
    enqueue = runner.invoke(app, ["enqueue", str(contract_path)])
    assert enqueue.exit_code == 0
    assert "QUEUE_ENQUEUE" in enqueue.output

    run_next = runner.invoke(app, ["run-next", "--mock"])
    assert run_next.exit_code == 0
    assert "run_id=" in run_next.output

    alias_set = runner.invoke(
        app,
        ["session-alias", "set", "agent-1", "session-1", "--thread-id", "thread-1", "--note", "test"],
    )
    assert alias_set.exit_code == 0
    assert "agent-1" in alias_set.output

    alias_get = runner.invoke(app, ["session-alias", "get", "agent-1"])
    assert alias_get.exit_code == 0
    assert "thread-1" in alias_get.output

    alias_list = runner.invoke(app, ["session-alias", "list"])
    assert alias_list.exit_code == 0
    assert "agent-1" in alias_list.output

    alias_delete = runner.invoke(app, ["session-alias", "delete", "agent-1"])
    assert alias_delete.exit_code == 0
    assert "alias deleted" in alias_delete.output

    alias_missing = runner.invoke(app, ["session-alias", "get", "agent-1"])
    assert alias_missing.exit_code != 0
    assert "alias not found" in alias_missing.output

    delete_missing = runner.invoke(app, ["session-alias", "delete", "agent-1"])
    assert delete_missing.exit_code != 0
    assert "alias not found" in delete_missing.output


def test_cli_run_next_empty_queue(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    runner = CliRunner()
    result = runner.invoke(app, ["run-next", "--mock"])
    assert result.exit_code == 0
    assert "queue empty" in result.output


def test_cli_compile_plan_and_replay_guard(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    schema_root = repo_root / "schemas"
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_SCHEMA_ROOT", str(schema_root))

    repo = create_tiny_repo(tmp_path / "repo_compile")
    monkeypatch.chdir(repo)

    plan = {
        "plan_id": "plan_cli",
        "task_id": "plan_cli",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "spec": "spec",
        "allowed_paths": ["out.txt"],
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["compile-plan", str(plan_path)])
    assert result.exit_code == 0
    output_path = repo / "contracts" / "tasks" / "plan_cli.json"
    assert output_path.exists()
    compiled = json.loads(output_path.read_text(encoding="utf-8"))
    assert compiled.get("task_id") == "plan_cli"
    assert compiled.get("assigned_agent", {}).get("agent_id") == "agent-1"

    replay_guard = runner.invoke(app, ["replay", "run-1", "--verify", "--reexec"])
    assert replay_guard.exit_code != 0

    replay_verify = runner.invoke(app, ["replay", "run-missing", "--verify"])
    assert replay_verify.exit_code == 0
    assert "\"status\"" in replay_verify.output

    replay_reexec = runner.invoke(app, ["replay", "run-missing", "--reexec"])
    assert replay_reexec.exit_code == 0
    assert "\"status\"" in replay_reexec.output

    replay_plain = runner.invoke(app, ["replay", "run-missing"])
    assert replay_plain.exit_code == 0
    assert "\"status\"" in replay_plain.output

    invalid_plan_path = tmp_path / "plan_invalid.json"
    invalid_plan_path.write_text("[]", encoding="utf-8")
    invalid_plan = runner.invoke(app, ["compile-plan", str(invalid_plan_path)])
    assert invalid_plan.exit_code != 0

    out_path = tmp_path / "out" / "contract.json"
    explicit = runner.invoke(app, ["compile-plan", str(plan_path), "--output-path", str(out_path)])
    assert explicit.exit_code == 0
    assert out_path.exists()


def test_read_manifest_status_unknown(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    status = cli._read_manifest_status("missing")
    assert status == "UNKNOWN"


def test_cleanup_runtime_cli(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    logs_root = tmp_path / "logs"

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_LOGS_ROOT", str(logs_root))
    monkeypatch.setenv("OPENVIBECODING_RETENTION_RUN_DAYS", "0")
    monkeypatch.setenv("OPENVIBECODING_RETENTION_MAX_RUNS", "1")
    monkeypatch.setenv("OPENVIBECODING_RETENTION_LOG_DAYS", "0")
    monkeypatch.setenv("OPENVIBECODING_RETENTION_WORKTREE_DAYS", "0")

    (runs_root / "run_1").mkdir(parents=True, exist_ok=True)
    (runs_root / "run_2").mkdir(parents=True, exist_ok=True)
    (worktree_root / "run_1").mkdir(parents=True, exist_ok=True)
    (logs_root / "runtime").mkdir(parents=True, exist_ok=True)
    (logs_root / "runtime" / "app.log").write_text("log", encoding="utf-8")

    runner = CliRunner()
    dry = runner.invoke(app, ["cleanup", "runtime", "--dry-run"])
    assert dry.exit_code == 0
    assert "candidates_total" in dry.output

    apply = runner.invoke(app, ["cleanup", "runtime", "--apply"])
    assert apply.exit_code == 0
    assert "removed_total" in apply.output

    run_id = "run_bad"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text("{", encoding="utf-8")
    status = cli._read_manifest_status(run_id)
    assert status == "UNKNOWN"


def test_cli_doctor_missing_head(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(runtime_root / "worktrees"))

    class DummyErr(Exception):
        pass

    def _raise(*args, **kwargs):
        raise DummyErr("no head")

    monkeypatch.setattr(cli.subprocess, "run", _raise)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "git_head" in result.output
    assert "missing" in result.output
