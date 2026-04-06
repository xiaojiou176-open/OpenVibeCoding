import hashlib
import json
import subprocess
from pathlib import Path

from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.run_store import RunStore


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
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)


def _contract(task_id: str, artifacts: list[dict], owner_role: str = "WORKER") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": owner_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock update", "artifacts": artifacts},
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


def test_context_policy_summary_only_blocks_raw(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(Path("schemas")))

    artifacts = [
        *_output_schema_artifacts("worker"),
        {"name": "search_results.json", "uri": "file://raw", "sha256": "0" * 64},
    ]
    chain = {
        "chain_id": "chain_ctx_01",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "tl-1", "codex_thread_id": ""},
        "steps": [
            {
                "name": "step_raw",
                "kind": "contract",
                "payload": _contract("task_ctx_raw", artifacts, owner_role="PM"),
                "context_policy": {"mode": "summary-only"},
            }
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    runner = ChainRunner(repo, RunStore(), orch.execute_task)
    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"

    run_dir = runtime_root / "runs" / report["run_id"]
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_CONTEXT_POLICY_VIOLATION" in events


def test_context_policy_isolated_blocks_artifacts(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(Path("schemas")))

    artifacts = [{"name": "summary.json", "uri": "file://summary", "sha256": "1" * 64}]
    chain = {
        "chain_id": "chain_ctx_02",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "tl-1", "codex_thread_id": ""},
        "steps": [
            {
                "name": "step_isolated",
                "kind": "contract",
                "payload": _contract("task_ctx_isolated", artifacts),
                "context_policy": {"mode": "isolated"},
            }
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    runner = ChainRunner(repo, RunStore(), orch.execute_task)
    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"

    run_dir = runtime_root / "runs" / report["run_id"]
    events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_CONTEXT_POLICY_VIOLATION" in events
