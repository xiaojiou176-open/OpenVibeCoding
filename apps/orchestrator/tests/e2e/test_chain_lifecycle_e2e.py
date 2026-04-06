from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from .e2e_helpers import build_env, create_tiny_repo, run_chain


def _output_schema_artifacts(role: str) -> list[dict[str, Any]]:
    schema_root = Path(__file__).resolve().parents[4] / "schemas"
    role_key = role.strip().upper()
    if role_key == "REVIEWER":
        schema_name = "review_report.v1.json"
    elif role_key in {"TEST", "TEST_RUNNER"}:
        schema_name = "test_report.v1.json"
    else:
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


def _contract(
    task_id: str,
    owner_role: str,
    assigned_role: str,
    output_name: str,
    extra_allowed_paths: list[str] | None = None,
) -> dict[str, Any]:
    allowed_paths = [output_name]
    if extra_allowed_paths:
        for item in extra_allowed_paths:
            path = str(item).strip()
            if path and path not in allowed_paths:
                allowed_paths.append(path)

    role_key = assigned_role.strip().upper()
    filesystem = "workspace-write"
    task_type = "IMPLEMENT"
    if role_key == "REVIEWER":
        filesystem = "read-only"
        task_type = "REVIEW"
    elif role_key in {"TEST", "TEST_RUNNER"}:
        filesystem = "read-only"
        task_type = "TEST"

    return {
        "task_id": task_id,
        "task_type": task_type,
        "owner_agent": {"role": owner_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {
            "role": assigned_role,
            "agent_id": "agent-1",
            "codex_thread_id": "",
        },
        "inputs": {
            "spec": f"execute {task_id}",
            "artifacts": _output_schema_artifacts(assigned_role),
        },
        "required_outputs": [{"name": output_name, "type": "file", "acceptance": "ok"}],
        "allowed_paths": allowed_paths,
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": filesystem,
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


def _chain_payload(chain_id: str, reviewer_quorum: int) -> dict[str, Any]:
    return {
        "chain_id": chain_id,
        "owner_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
        "strategy": {
            "continue_on_fail": False,
            "lifecycle": {
                "enforce": True,
                "required_path": [
                    "PM",
                    "TECH_LEAD",
                    "WORKER",
                    "REVIEWER",
                    "TEST_RUNNER",
                    "TECH_LEAD",
                    "PM",
                ],
                "min_workers": 2,
                "min_reviewers": 2,
                "reviewer_quorum": reviewer_quorum,
                "require_test_stage": True,
                "require_return_to_pm": True,
            },
        },
        "steps": [
            {
                "name": "pm_to_tl",
                "kind": "handoff",
                "payload": {
                    "task_id": "pm_to_tl_01",
                    "owner_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
                    "assigned_agent": {
                        "role": "TECH_LEAD",
                        "agent_id": "agent-1",
                        "codex_thread_id": "",
                    },
                },
            },
            {
                "name": "worker_core",
                "kind": "contract",
                "payload": _contract("worker_core_01", "TECH_LEAD", "WORKER", ".runtime-cache/test_output/worker_markers/worker_core.txt"),
                "depends_on": ["pm_to_tl"],
                "parallel_group": "workers",
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/worker_core.txt"],
            },
            {
                "name": "worker_frontend",
                "kind": "contract",
                "payload": _contract("worker_frontend_01", "TECH_LEAD", "FRONTEND", ".runtime-cache/test_output/worker_markers/worker_frontend.txt"),
                "depends_on": ["pm_to_tl"],
                "parallel_group": "workers",
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/worker_frontend.txt"],
            },
            {
                "name": "review_a",
                "kind": "contract",
                "payload": _contract(
                    "review_a_01",
                    "TECH_LEAD",
                    "REVIEWER",
                    ".runtime-cache/test_output/worker_markers/review_a.txt",
                    extra_allowed_paths=[".runtime-cache/test_output/worker_markers/worker_core.txt", ".runtime-cache/test_output/worker_markers/worker_frontend.txt"],
                ),
                "depends_on": ["worker_core", "worker_frontend"],
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/review_a.txt"],
            },
            {
                "name": "review_b",
                "kind": "contract",
                "payload": _contract(
                    "review_b_01",
                    "TECH_LEAD",
                    "REVIEWER",
                    ".runtime-cache/test_output/worker_markers/review_b.txt",
                    extra_allowed_paths=[".runtime-cache/test_output/worker_markers/worker_core.txt", ".runtime-cache/test_output/worker_markers/worker_frontend.txt"],
                ),
                "depends_on": ["worker_core", "worker_frontend"],
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/review_b.txt"],
            },
            {
                "name": "testing",
                "kind": "contract",
                "payload": _contract(
                    "testing_01",
                    "TECH_LEAD",
                    "TEST_RUNNER",
                    ".runtime-cache/test_output/worker_markers/testing.txt",
                    extra_allowed_paths=[
                        ".runtime-cache/test_output/worker_markers/worker_core.txt",
                        ".runtime-cache/test_output/worker_markers/worker_frontend.txt",
                        ".runtime-cache/test_output/worker_markers/review_a.txt",
                        ".runtime-cache/test_output/worker_markers/review_b.txt",
                    ],
                ),
                "depends_on": ["review_a", "review_b"],
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/testing.txt"],
            },
            {
                "name": "tl_to_pm",
                "kind": "handoff",
                "payload": {
                    "task_id": "tl_to_pm_01",
                    "owner_agent": {
                        "role": "TECH_LEAD",
                        "agent_id": "agent-1",
                        "codex_thread_id": "",
                    },
                    "assigned_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
                },
                "depends_on": ["testing"],
            },
        ],
    }


def _read_events(path: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


@pytest.mark.e2e
def test_run_chain_lifecycle_full_e2e_success(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    repo = create_tiny_repo(tmp_path / "tiny_repo_chain_success")

    report = run_chain(repo, env, _chain_payload("chain_e2e_full_success", reviewer_quorum=2), tmp_path)

    assert report["status"] == "SUCCESS"
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is True
    assert lifecycle["workers"]["observed"] >= 2
    assert lifecycle["reviewers"]["observed"] == 2
    assert lifecycle["reviewers"]["pass"] == 2
    assert lifecycle["reviewers"]["quorum_met"] is True
    assert lifecycle["tests"]["ok"] is True
    assert lifecycle["return_to_pm"]["ok"] is True

    run_id = report["run_id"]
    run_dir = runs_root / run_id
    assert (run_dir / "reports" / "chain_report.json").exists()

    events = _read_events(run_dir / "events.jsonl")
    event_names = [str(item.get("event") or "") for item in events]
    assert "CHAIN_HANDOFF_STEP_MARKED" in event_names
    assert "CHAIN_LIFECYCLE_EVALUATED" in event_names
    assert "CHAIN_COMPLETED" in event_names


@pytest.mark.e2e
def test_run_chain_lifecycle_full_e2e_quorum_fail(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    repo = create_tiny_repo(tmp_path / "tiny_repo_chain_fail")

    report = run_chain(repo, env, _chain_payload("chain_e2e_full_fail", reviewer_quorum=3), tmp_path)

    assert report["status"] == "FAILURE"
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is False
    assert lifecycle["reviewers"]["observed"] == 2
    assert lifecycle["reviewers"]["pass"] == 2
    assert lifecycle["reviewers"]["quorum"] == 3
    assert lifecycle["reviewers"]["quorum_met"] is False

    run_id = report["run_id"]
    run_dir = runs_root / run_id
    events = _read_events(run_dir / "events.jsonl")

    lifecycle_event = next((item for item in events if item.get("event") == "CHAIN_LIFECYCLE_EVALUATED"), None)
    assert lifecycle_event is not None
    meta = lifecycle_event.get("meta", {})
    assert isinstance(meta, dict)
    violations = meta.get("violations", [])
    assert isinstance(violations, list)
    assert any("reviewer quorum not met" in str(item) for item in violations)

    completed_event = next((item for item in events if item.get("event") == "CHAIN_COMPLETED"), None)
    assert completed_event is not None
    completed_meta = completed_event.get("meta", {})
    assert isinstance(completed_meta, dict)
    assert completed_meta.get("status") == "FAILURE"


@pytest.mark.e2e
def test_run_chain_lifecycle_official_example_contract(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    repo = create_tiny_repo(tmp_path / "tiny_repo_chain_example")

    chain_path = repo_root / "contracts" / "examples" / "task_chain.lifecycle.full.json"
    chain_payload = json.loads(chain_path.read_text(encoding="utf-8"))
    report = run_chain(repo, env, chain_payload, tmp_path)

    assert report["status"] == "SUCCESS"
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is True
    assert lifecycle["reviewers"]["quorum_met"] is True
    assert lifecycle["tests"]["ok"] is True
    assert lifecycle["return_to_pm"]["ok"] is True

    run_id = report["run_id"]
    run_dir = runs_root / run_id
    events = _read_events(run_dir / "events.jsonl")
    event_names = [str(item.get("event") or "") for item in events]
    assert "CHAIN_HANDOFF_STEP_MARKED" in event_names
    assert "CHAIN_LIFECYCLE_EVALUATED" in event_names
    assert "CHAIN_COMPLETED" in event_names


@pytest.mark.e2e
def test_run_chain_lifecycle_e2e_missing_testing_and_pm_return(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    repo = create_tiny_repo(tmp_path / "tiny_repo_chain_missing_stages")

    payload = _chain_payload("chain_e2e_missing_stages", reviewer_quorum=2)
    payload["steps"] = [
        step
        for step in payload["steps"]
        if str(step.get("name", "")) not in {"testing", "tl_to_pm"}
    ]
    report = run_chain(repo, env, payload, tmp_path)

    assert report["status"] == "FAILURE"
    lifecycle = report["lifecycle"]
    assert lifecycle["tests"]["ok"] is False
    assert lifecycle["return_to_pm"]["ok"] is False

    run_id = report["run_id"]
    run_dir = runs_root / run_id
    events = _read_events(run_dir / "events.jsonl")
    lifecycle_event = next((item for item in events if item.get("event") == "CHAIN_LIFECYCLE_EVALUATED"), None)
    assert lifecycle_event is not None
    meta = lifecycle_event.get("meta", {})
    assert isinstance(meta, dict)
    violations = meta.get("violations", [])
    assert isinstance(violations, list)
    assert any("test stage missing PASS result" in str(item) for item in violations)
    assert any("final lifecycle role is not PM" in str(item) for item in violations)
