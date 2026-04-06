import json
import subprocess
from pathlib import Path

import pytest
from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.run_store import RunStore


SCHEMA_ROOT = Path(__file__).resolve().parents[3] / "schemas"


@pytest.fixture(autouse=True)
def _disable_strict_nontrivial(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "0")


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    registry_source = Path(__file__).resolve().parents[3] / "policies" / "agent_registry.json"
    if registry_source.exists():
        (policies / "agent_registry.json").write_text(
            registry_source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
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
    tools_dir = repo / "tooling"
    tools_dir.mkdir(parents=True, exist_ok=True)
    registry_source = Path(__file__).resolve().parents[3] / "tooling" / "registry.json"
    if registry_source.exists():
        (tools_dir / "registry.json").write_text(
            registry_source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _plan(plan_id: str, allowed_paths: list[str]) -> dict:
    return {
        "plan_id": plan_id,
        "plan_type": "BACKEND",
        "task_type": "IMPLEMENT",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        "spec": f"audit {plan_id}",
        "allowed_paths": allowed_paths,
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "never",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
    }


def test_chain_runner_normalizes_fanin_summary(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(
        [
            "git",
            "add",
            "README.md",
            "policies/command_allowlist.json",
            "policies/agent_registry.json",
            "tooling/registry.json",
        ],
        repo,
    )
    _git(["git", "commit", "-m", "init"], repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(SCHEMA_ROOT))

    chain = {
        "chain_id": "chain_fanin",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "tl-1", "codex_thread_id": ""},
        "strategy": {"continue_on_fail": False},
        "steps": [
            {
                "name": "worker_0",
                "kind": "plan",
                "payload": _plan("plan-one", ["docs/one"]),
                "exclusive_paths": ["docs/one"],
                "parallel_group": "audit",
            },
            {
                "name": "fan_in",
                "kind": "plan",
                "payload": _plan("plan-fanin", ["__fan_in__/"]),
                "exclusive_paths": ["__fan_in__/"],
                "depends_on": ["worker_0"],
            },
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    runner = ChainRunner(repo, RunStore(), orch.execute_task)
    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "SUCCESS"
    fan_in_step = next(step for step in report["steps"] if step["name"] == "fan_in")
    fan_in_run_id = fan_in_step["run_id"]
    runs_root_actual = Path(runner._store._runs_root)
    report_path = runs_root_actual / fan_in_run_id / "reports" / "task_result.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", "")
    parsed = json.loads(summary)
    assert parsed.get("format") == "cortexpilot.fanin.summary.v1"
    assert parsed.get("dependency_run_ids")
