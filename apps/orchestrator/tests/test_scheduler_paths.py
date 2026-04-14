import json
import hashlib
import subprocess
from pathlib import Path

from openvibecoding_orch.scheduler import scheduler as sched
from openvibecoding_orch.scheduler.scheduler import Orchestrator


def _git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["git", "init"], repo)
    _git(["git", "config", "user.email", "test@example.com"], repo)
    _git(["git", "config", "user.name", "tester"], repo)
    policies = repo / "policies"
    policies.mkdir(parents=True, exist_ok=True)
    (policies / "command_allowlist.json").write_text(
        json.dumps(
            {
                "version": "v1",
                "allow": [
                    {"exec": "codex", "argv_prefixes": [["codex", "exec"]]},
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
                    {
                        "agent_id": "agent-1",
                        "role": "REVIEWER",
                        "codex_home": "codex_home",
                        "defaults": {
                            "sandbox": "workspace-write",
                            "approval_policy": "on-request",
                            "network": "deny",
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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _base_contract(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "output.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["output.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _write_json(path: Path, payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(raw, encoding="utf-8")
    return raw


def _artifact_ref(name: str, path: str, sha: str) -> dict:
    return {"name": name, "path": path, "sha256": sha}


def _test_report(status: str, exit_code: int) -> dict:
    return {
        "runner": {"role": "TEST_RUNNER", "agent_id": "tests"},
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:00:01Z",
        "status": status,
        "commands": [
            {
                "name": "pytest -q",
                "cmd_argv": ["pytest", "-q"],
                "must_pass": True,
                "timeout_sec": 600,
                "exit_code": exit_code,
                "duration_sec": 0.1,
                "stdout": _artifact_ref("stdout", "tests/stdout.log", "a" * 64),
                "stderr": _artifact_ref("stderr", "tests/stderr.log", "b" * 64),
            }
        ],
        "artifacts": [],
    }


def test_scheduler_lock_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = _base_contract("task_lock")
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    monkeypatch.setattr(sched, "acquire_lock_with_cleanup", lambda paths, auto_cleanup: (False, [], []))

    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "lock acquisition failed"


def test_scheduler_tool_request_invalid(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    search_path = repo / "search_requests.json"
    raw = _write_json(search_path, {"queries": []})

    contract = _base_contract("task_tool_invalid")
    contract["inputs"]["artifacts"] = [
        {"name": "search_requests.json", "uri": str(search_path), "sha256": _sha256_text(raw)}
    ]
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert "tool requests invalid" in manifest.get("failure_reason", "")


def test_scheduler_fix_loop_triggered_then_passes(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = _base_contract("task_fix_loop")
    contract["timeout_retry"]["max_retries"] = 1
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    results = [
        {
            "ok": False,
            "reports": [
                _test_report("FAIL", 1)
            ],
            "reason": "fail",
        },
        {
            "ok": True,
            "reports": [
                _test_report("PASS", 0)
            ],
            "reason": "ok",
        },
    ]

    def _fake_tests(*args, **kwargs):
        return results.pop(0)

    monkeypatch.setattr(sched, "run_acceptance_tests", _fake_tests)
    monkeypatch.setattr(sched, "validate_diff", lambda *args, **kwargs: {"ok": True, "changed_files": []})
    monkeypatch.setattr(sched, "_collect_diff_text", lambda *args, **kwargs: "diff")

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)

    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "SUCCESS"

    events_text = (runs_root / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "FIX_LOOP_TRIGGERED" in events_text
    assert "TEST_RESULT" in events_text


def test_scheduler_reviewer_gate_failure(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))

    contract = _base_contract("task_review_gate")
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.setattr(sched, "run_acceptance_tests", lambda *args, **kwargs: {"ok": True, "reports": []})
    monkeypatch.setattr(sched, "validate_diff", lambda *args, **kwargs: {"ok": True, "changed_files": []})
    monkeypatch.setattr(sched, "_collect_diff_text", lambda *args, **kwargs: "diff")
    monkeypatch.setattr(sched, "validate_reviewer_isolation", lambda *args, **kwargs: {"ok": False})

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "reviewer isolation violation"


def test_scheduler_reviewer_fallback_and_review_failed(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.setenv("OPENVIBECODING_REVIEWER_MODE", "codex")

    contract = _base_contract("task_review_fail")
    contract_path = repo / "contract.json"
    _write_json(contract_path, contract)

    monkeypatch.setattr(sched, "run_acceptance_tests", lambda *args, **kwargs: {"ok": True, "reports": []})
    monkeypatch.setattr(sched, "validate_diff", lambda *args, **kwargs: {"ok": True, "changed_files": []})
    monkeypatch.setattr(sched, "_collect_diff_text", lambda *args, **kwargs: "diff")

    import openvibecoding_orch.reviewer.reviewer as reviewer_mod

    class BoomReviewer:
        def review_task(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(reviewer_mod, "CodexReviewer", lambda: BoomReviewer())

    def _fail_review(*args, **kwargs):
        return {
            "task_id": "task_review_fail",
            "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
            "reviewed_at": "2024-01-01T00:00:00Z",
            "verdict": "FAIL",
            "summary": "review failed",
            "scope_check": {"passed": False, "violations": ["fail"]},
            "evidence": [],
            "produced_diff": False,
        }

    monkeypatch.setattr(reviewer_mod.Reviewer, "review_task", _fail_review)

    monkeypatch.chdir(repo)
    orch = Orchestrator(repo)
    run_id = orch.execute_task(contract_path, mock_mode=True)
    manifest = json.loads((runs_root / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("status") == "FAILURE"
    assert manifest.get("failure_reason") == "review failed"
