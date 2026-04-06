import json
import os
import subprocess
from pathlib import Path

import pytest
from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.scheduler.scheduler import Orchestrator
from cortexpilot_orch.store.run_store import RunStore
import hashlib


@pytest.fixture(autouse=True)
def _disable_strict_nontrivial(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "0")


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


def _contract(task_id: str, output_name: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": f"generate {output_name}", "artifacts": _output_schema_artifacts("worker")},
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


def test_chain_runner_executes_steps(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("CORTEXPILOT_SCHEMA_ROOT", str(Path("schemas")))

    chain = {
        "chain_id": "chain_example_01",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "tl-1", "codex_thread_id": ""},
        "strategy": {"continue_on_fail": False},
        "steps": [
            {
                "name": "step_1",
                "kind": "contract",
                "payload": _contract("task_chain_1", "step1.txt"),
                "exclusive_paths": ["step1.txt"],
                "parallel_group": "group_a",
            },
            {
                "name": "step_2",
                "kind": "contract",
                "payload": _contract("task_chain_2", "step2.txt"),
                "exclusive_paths": ["step2.txt"],
                "parallel_group": "group_a",
                "depends_on": ["step_1"],
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
    assert len(report["steps"]) == 2
    assert report["steps"][0]["owner_agent"]["role"] == "WORKER"
    assert report["steps"][0]["assigned_agent"]["role"] == "WORKER"
    assert report["timeouts"]["count"] == 0
    assert report["timeouts"]["timed_out_steps"] == []

    run_id = report["run_id"]
    run_dir = runs_root / run_id
    assert (run_dir / "reports" / "chain_report.json").exists()
    events_text = (run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_STARTED" in events_text
    assert "CHAIN_HANDOFF" in events_text
    assert "CHAIN_STEP_RESULT" in events_text


def _execute_stub_with_failure(store: RunStore, failed_task_ids: set[str]):
    def _inner(contract_path: Path, mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id", "task"))
        run_id = store.create_run(task_id)
        status = "FAILURE" if task_id in failed_task_ids else "SUCCESS"
        failure_reason = "forced failure" if status == "FAILURE" else ""
        store.write_manifest(
            run_id,
            {
                "run_id": run_id,
                "task_id": task_id,
                "status": status,
                "failure_reason": failure_reason,
            },
        )
        return run_id

    return _inner


def test_chain_runner_executes_all_ready_parallel_groups_before_failure(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    runner = ChainRunner(tmp_path, store, _execute_stub_with_failure(store, {"task_group_b"}))
    monkeypatch.setattr(runner._validator, "validate_report", lambda payload, schema: payload)

    chain = {
        "chain_id": "chain_parallel_groups_fail",
        "owner_agent": {"role": "TECH_LEAD", "agent_id": "tl-1", "codex_thread_id": ""},
        "strategy": {"continue_on_fail": False},
        "steps": [
            {
                "name": "group_a_step",
                "kind": "contract",
                "payload": _contract("task_group_a", "group_a.txt"),
                "parallel_group": "group_a",
                "exclusive_paths": ["group_a.txt"],
            },
            {
                "name": "group_b_step",
                "kind": "contract",
                "payload": _contract("task_group_b", "group_b.txt"),
                "parallel_group": "group_b",
                "exclusive_paths": ["group_b.txt"],
            },
        ],
    }
    chain_path = tmp_path / "chain_parallel_groups_fail.json"
    chain_path.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "FAILURE"
    assert [item["name"] for item in report["steps"]] == ["group_a_step", "group_b_step"]
    assert [item["status"] for item in report["steps"]] == ["SUCCESS", "FAILURE"]
