import json
import subprocess
import hashlib
from pathlib import Path

from openvibecoding_orch.scheduler.scheduler import Orchestrator


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def create_repo(base_dir: Path) -> Path:
    repo = base_dir
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    codex_home = repo / "codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    tools_dir = repo / "tooling"
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "registry.json").write_text(
        json.dumps({"installed": ["codex", "search"], "integrated": ["codex", "search"]}),
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
                ],
                "deny_substrings": ["rm -rf", "sudo", "ssh ", "scp ", "sftp ", "curl ", "wget "],
            }
        ),
        encoding="utf-8",
    )
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
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(["git", "add", "README.md"], repo)
    _git(["git", "commit", "-m", "init"], repo)
    return repo


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


def _base_contract(task_id: str, output_name: str = "README.md") -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": output_name, "type": "file", "acceptance": "ok"}],
        "allowed_paths": [output_name],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_scheduler_network_gate_blocks(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_network")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    search_path = repo / "search_requests.json"
    search_path.write_text(json.dumps(["q1"]), encoding="utf-8")
    digest = _sha256_text(search_path.read_text(encoding="utf-8"))

    contract = _base_contract("task_network")
    contract["owner_agent"]["role"] = "SEARCHER"
    contract["assigned_agent"]["role"] = "SEARCHER"
    contract["inputs"]["artifacts"] = [
        {"name": "search_requests.json", "uri": str(search_path), "sha256": digest}
    ]
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "network gate violation"
    assert (runs_root / run_id / "reports" / "evidence_bundle.json").exists()


def test_scheduler_search_owner_forbidden(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_search_forbidden")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    search_path = repo / "search_requests.json"
    search_path.write_text(json.dumps(["q1"]), encoding="utf-8")
    digest = _sha256_text(search_path.read_text(encoding="utf-8"))

    contract = _base_contract("task_search_forbidden")
    contract["owner_agent"]["role"] = "PM"
    contract["assigned_agent"]["role"] = "WORKER"
    contract["inputs"]["artifacts"] = [
        {"name": "search_requests.json", "uri": str(search_path), "sha256": digest}
    ]
    contract_path = repo / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "search forbidden for PM owner"


def test_scheduler_tool_gate_and_mcp_gate_failures(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_tool_gate")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = _base_contract("task_mcp_fail")
    contract["tool_permissions"]["mcp_tools"] = []
    contract_path = repo / "contract_mcp.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("failure_reason") == "codex mcp tool not allowed"

    contract = _base_contract("task_tool_fail")
    contract["forbidden_actions"] = ["codex"]
    contract_path = repo / "contract_tool.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("failure_reason") == "tool gate violation"


def test_scheduler_mcp_concurrency_required(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_mcp_concurrency")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_MCP_CONCURRENCY_MODE", "multi")
    monkeypatch.setenv("OPENVIBECODING_MCP_CONCURRENCY_REQUIRED", "1")

    contract = _base_contract("task_mcp_concurrency")
    contract_path = repo / "contract_mcp_concurrency.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("failure_reason") == "mcp concurrency validation failed"


def test_scheduler_diff_gate_violation(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_diff_gate")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = _base_contract("task_diff_fail", output_name="output.txt")
    contract["allowed_paths"] = ["allowed.txt"]
    contract_path = repo / "contract_diff.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("failure_reason") == "diff gate violation"


def test_scheduler_mcp_only_blocks_codex_runner(tmp_path: Path, monkeypatch) -> None:
    repo = create_repo(tmp_path / "repo_mcp_only")
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.chdir(repo)
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_RUNNER", "codex")
    monkeypatch.setenv("OPENVIBECODING_MCP_ONLY", "1")
    monkeypatch.delenv("OPENVIBECODING_ALLOW_CODEX_EXEC", raising=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("codex runner should not be called")

    monkeypatch.setattr("openvibecoding_orch.runners.codex_runner.CodexRunner.run_contract", _boom)

    contract = _base_contract("task_mcp_only")
    contract_path = repo / "contract_mcp_only.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=False)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "mcp-only enforced: non-agents runner blocked"
