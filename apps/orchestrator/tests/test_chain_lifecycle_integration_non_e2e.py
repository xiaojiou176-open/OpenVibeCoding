from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tests.e2e.e2e_helpers import build_env, create_tiny_repo, run_chain


def _output_schema_artifacts(role: str) -> list[dict[str, Any]]:
    schema_root = Path(__file__).resolve().parents[3] / "schemas"
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
    role_key = assigned_role.strip().upper()
    filesystem = "workspace-write"
    task_type = "IMPLEMENT"
    if role_key == "REVIEWER":
        filesystem = "read-only"
        task_type = "REVIEW"
    elif role_key in {"TEST", "TEST_RUNNER"}:
        filesystem = "read-only"
        task_type = "TEST"

    allowed_paths = [output_name]
    if extra_allowed_paths:
        for item in extra_allowed_paths:
            path = str(item).strip()
            if path and path not in allowed_paths:
                allowed_paths.append(path)

    return {
        "task_id": task_id,
        "task_type": task_type,
        "owner_agent": {"role": owner_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": assigned_role, "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": f"execute {task_id}", "artifacts": _output_schema_artifacts(assigned_role)},
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


def _chain_payload(chain_id: str, reviewer_quorum: int, include_testing: bool = True, include_return_pm: bool = True) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [
        {
            "name": "pm_to_tl",
            "kind": "handoff",
            "payload": {
                "task_id": "pm_to_tl_01",
                "owner_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
                "assigned_agent": {"role": "TECH_LEAD", "agent_id": "agent-1", "codex_thread_id": ""},
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
    ]

    if include_testing:
        steps.append(
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
            }
        )
    if include_return_pm:
        steps.append(
            {
                "name": "tl_to_pm",
                "kind": "handoff",
                "payload": {
                    "task_id": "tl_to_pm_01",
                    "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1", "codex_thread_id": ""},
                    "assigned_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
                },
                "depends_on": ["testing"] if include_testing else ["review_a", "review_b"],
            }
        )

    return {
        "chain_id": chain_id,
        "owner_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
        "strategy": {
            "continue_on_fail": False,
            "lifecycle": {
                "enforce": True,
                "required_path": ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER", "TECH_LEAD", "PM"],
                "min_workers": 2,
                "min_reviewers": 2,
                "reviewer_quorum": reviewer_quorum,
                "require_test_stage": True,
                "require_return_to_pm": True,
            },
        },
        "steps": steps,
    }


def _build_env_with_chain_role_mcp(
    repo_root: Path,
    runtime_root: Path,
    runs_root: Path,
    worktree_root: Path,
    tmp_path: Path,
) -> dict[str, str]:
    env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    registry_path = repo_root / "policies" / "agent_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for agent in registry.get("agents", []):
        if not isinstance(agent, dict):
            continue
        role = str(agent.get("role", "")).strip().upper()
        if role not in {"REVIEWER", "TEST_RUNNER", "TEST"}:
            continue
        capabilities = agent.get("capabilities")
        if not isinstance(capabilities, dict):
            capabilities = {}
            agent["capabilities"] = capabilities
        tools = capabilities.get("mcp_tools")
        if not isinstance(tools, list):
            tools = []
        if "codex" not in tools:
            tools.append("codex")
        capabilities["mcp_tools"] = tools
    test_registry = tmp_path / "agent_registry.chain_non_e2e.json"
    test_registry.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    env["OPENVIBECODING_AGENT_REGISTRY"] = str(test_registry)
    return env


def test_chain_lifecycle_non_e2e_success(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = _build_env_with_chain_role_mcp(repo_root, runtime_root, runs_root, worktree_root, tmp_path)
    repo = create_tiny_repo(tmp_path / "tiny_repo_success")

    report = run_chain(repo, env, _chain_payload("chain_non_e2e_success", reviewer_quorum=2), tmp_path)
    assert report["status"] == "SUCCESS"
    assert report["lifecycle"]["is_complete"] is True


def test_chain_lifecycle_non_e2e_quorum_failure(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = _build_env_with_chain_role_mcp(repo_root, runtime_root, runs_root, worktree_root, tmp_path)
    repo = create_tiny_repo(tmp_path / "tiny_repo_quorum_fail")

    report = run_chain(repo, env, _chain_payload("chain_non_e2e_quorum_fail", reviewer_quorum=3), tmp_path)
    assert report["status"] == "FAILURE"
    assert report["lifecycle"]["reviewers"]["quorum_met"] is False


def test_chain_lifecycle_non_e2e_missing_stages(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    env = _build_env_with_chain_role_mcp(repo_root, runtime_root, runs_root, worktree_root, tmp_path)
    repo = create_tiny_repo(tmp_path / "tiny_repo_missing_stage")

    report = run_chain(
        repo,
        env,
        _chain_payload(
            "chain_non_e2e_missing_stage",
            reviewer_quorum=2,
            include_testing=False,
            include_return_pm=False,
        ),
        tmp_path,
    )
    assert report["status"] == "FAILURE"
    assert report["lifecycle"]["tests"]["ok"] is False
    assert report["lifecycle"]["return_to_pm"]["ok"] is False
