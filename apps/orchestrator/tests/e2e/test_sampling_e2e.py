from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from .e2e_helpers import build_env, create_tiny_repo, run_contract


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


@pytest.mark.e2e
def test_sampling_requests_flow(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    base_env["OPENVIBECODING_SAMPLING_APPROVED"] = "true"

    repo = create_tiny_repo(tmp_path / "tiny_repo_sampling")
    sampling_path = repo / "sampling_requests.json"
    sampling_payload = {"requests": [{"input": "hello sampling", "model": "mock"}]}
    sampling_path.write_text(json.dumps(sampling_payload), encoding="utf-8")
    sampling_sha = hashlib.sha256(sampling_path.read_bytes()).hexdigest()

    contract = {
        "task_id": "e2e_sampling_01",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {
            "spec": "sampling request should be executed",
            "artifacts": [
                *_output_schema_artifacts("worker"),
                {"name": "sampling_requests.json", "uri": str(sampling_path), "sha256": sampling_sha}
            ],
        },
        "required_outputs": [
            {"name": "sampling_results.json", "type": "json", "acceptance": "sampling ok"}
        ],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "workspace-write",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex", "sampling"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }

    run_id = run_contract(repo, base_env, contract, tmp_path)

    events_path = runs_root / run_id / "events.jsonl"
    assert events_path.exists()
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(ev.get("event") == "MCP_SAMPLING_REQUEST" for ev in events)

    artifact_path = runs_root / run_id / "artifacts" / "sampling_results.json"
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload.get("latest") or payload.get("count") is not None
