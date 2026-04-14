from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from openvibecoding_orch.scheduler.scheduler import Orchestrator
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


def _git(cmd: list[str], cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], cwd=repo)
    _git(["git", "config", "user.email", "test@example.com"], cwd=repo)
    _git(["git", "config", "user.name", "tester"], cwd=repo)


def test_scheduler_creates_run(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_SCHEMA_ROOT", str(Path("schemas")))

    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], cwd=repo)
    _git(["git", "commit", "-m", "init"], cwd=repo)

    contract = {
        "task_id": "task_scheduler",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock change", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo hello", "must_pass": True}],
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
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    cwd = Path.cwd()
    try:
        os.chdir(repo)
        orch = Orchestrator(repo)
        run_id = orch.execute_task(contract_path, mock_mode=True)
    finally:
        os.chdir(cwd)

    runs_root_actual = Path(orch._store._runs_root)
    run_dir = runs_root_actual / run_id
    events_path = run_dir / "events.jsonl"
    assert events_path.exists()
    events_text = events_path.read_text(encoding="utf-8")
    assert "STATE_TRANSITION" in events_text