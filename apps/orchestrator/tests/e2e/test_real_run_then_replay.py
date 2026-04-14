import json
import os
import subprocess
from pathlib import Path

import pytest
from openvibecoding_orch.scheduler.scheduler import Orchestrator
import hashlib

pytestmark = pytest.mark.e2e


def _output_schema_artifacts(role: str = "worker") -> list[dict]:
    schema_root = Path(__file__).resolve().parents[4] / "schemas"
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
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_real_run_then_replay(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "test"], repo)

    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = {
        "task_id": "task_real_run",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock update", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
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

    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    report = orch.replay_verify(run_id, strict=True)
    assert report["status"] == "pass"
    assert not report["errors"]
