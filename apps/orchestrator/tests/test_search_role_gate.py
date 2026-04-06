import hashlib
import json
import os
import subprocess
from pathlib import Path

from cortexpilot_orch.scheduler.scheduler import Orchestrator


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
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
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
                    {
                        "agent_id": "agent-1",
                        "role": "SEARCHER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "allow",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _contract(task_id: str, owner_role: str, assigned_role: str, artifacts: list[dict]) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": owner_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": assigned_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "mock search", "artifacts": artifacts},
        "required_outputs": [{"name": "mock_output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["mock_output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "allow",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_search_gate_blocks_pm_owner(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("CORTEXPILOT_SEARCH_MODE", "mock")
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "agents")
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)

    search_path = repo / "search_requests.json"
    body = json.dumps({"queries": ["cortexpilot"]}, ensure_ascii=False, indent=2)
    search_path.write_text(body, encoding="utf-8")
    artifact = {
        "name": "search_requests.json",
        "uri": str(search_path),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }

    contract = _contract(
        "task_search_pm",
        "PM",
        "SEARCHER",
        [*_output_schema_artifacts("searcher"), artifact],
    )
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runtime_root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "search forbidden for PM owner"


def test_search_gate_blocks_non_searcher(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("CORTEXPILOT_SEARCH_MODE", "mock")
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "agents")
    monkeypatch.delenv("CORTEXPILOT_ALLOW_CODEX_EXEC", raising=False)

    search_path = repo / "search_requests.json"
    body = json.dumps({"queries": ["cortexpilot"]}, ensure_ascii=False, indent=2)
    search_path.write_text(body, encoding="utf-8")
    artifact = {
        "name": "search_requests.json",
        "uri": str(search_path),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }

    contract = _contract("task_search_role", "TECH_LEAD", "WORKER", artifact)
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runtime_root / "runs" / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "search requires SEARCHER/RESEARCHER role"
