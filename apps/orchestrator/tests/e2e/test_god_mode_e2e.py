import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from .e2e_helpers import build_env, create_tiny_repo, start_api, wait_for_http
import hashlib


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


def _wait_for_run_id(runs_root: Path, existing: set[str], timeout_s: int = 10) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if runs_root.exists():
            for item in runs_root.iterdir():
                if item.is_dir() and item.name.startswith("run_") and item.name not in existing:
                    return item.name
        time.sleep(0.1)
    raise RuntimeError("run_id not detected")


def _approve(api_port: int, run_id: str) -> None:
    url = f"http://127.0.0.1:{api_port}/api/god-mode/approve"
    payload = json.dumps({"run_id": run_id}).encode("utf-8")
    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "x-openvibecoding-role": "TECH_LEAD"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
        time.sleep(0.2)
    raise RuntimeError("approval failed: pending approval event not ready in time")


@pytest.mark.e2e
def test_god_mode_approval_flow(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    runs_root.mkdir(parents=True, exist_ok=True)

    base_env = build_env(repo_root, runtime_root, runs_root, worktree_root)
    base_env["OPENVIBECODING_GOD_MODE_ON_REQUEST"] = "1"
    base_env["OPENVIBECODING_GOD_MODE_REQUIRED"] = "1"
    base_env["OPENVIBECODING_GOD_MODE_TIMEOUT_SEC"] = "12"
    api_proc, api_port = start_api(repo_root, base_env, tmp_path / "api.log")

    try:
        wait_for_http(f"http://127.0.0.1:{api_port}/api/runs", 20, api_proc)
        repo = create_tiny_repo(tmp_path / "tiny_repo_god_mode")
        contract = {
            "task_id": "e2e_god_mode_01",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
            "inputs": {"spec": "mock change gated by god mode", "artifacts": _output_schema_artifacts("worker")},
            "required_outputs": [{"name": "README.md", "type": "file", "acceptance": "ok"}],
            "allowed_paths": ["README.md"],
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
        contract_path = tmp_path / "contract.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        existing = {item.name for item in runs_root.iterdir() if item.is_dir()}
        uv_bin = shutil.which("uv") or "uv"
        requirements_path = repo_root / "apps" / "orchestrator" / "requirements.txt"
        run_cmd = [
            uv_bin,
            "run",
            "--no-project",
            "--with-requirements",
            str(requirements_path),
            "python",
            "-m",
            "openvibecoding_orch.cli",
            "run",
            str(contract_path),
            "--mock",
        ]
        proc = subprocess.Popen(
            run_cmd,
            cwd=repo,
            env=base_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        run_id = _wait_for_run_id(runs_root, existing, timeout_s=10)
        _approve(api_port, run_id)

        stdout, stderr = proc.communicate(timeout=30)
        assert proc.returncode == 0, stderr or stdout

        manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("status") == "SUCCESS"

        events_text = (runs_root / run_id / "events.jsonl").read_text(encoding="utf-8")
        assert "HUMAN_APPROVAL_REQUIRED" in events_text
        assert "HUMAN_APPROVAL_COMPLETED" in events_text
    finally:
        api_proc.stop()
