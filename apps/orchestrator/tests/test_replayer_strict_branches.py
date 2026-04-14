import hashlib
import json
import subprocess
from pathlib import Path

from openvibecoding_orch.replay.replayer import ReplayRunner
from openvibecoding_orch.store.run_store import RunStore


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


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _artifact_ref(name: str, path: str, sha: str) -> dict:
    return {"name": name, "path": path, "sha256": sha}


def _test_report(run_id: str, task_id: str, cmd_argv: list[str]) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "runner": {"role": "TEST_RUNNER", "agent_id": "tests"},
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:00:01Z",
        "status": "PASS",
        "commands": [
            {
                "name": " ".join(cmd_argv),
                "cmd_argv": cmd_argv,
                "must_pass": True,
                "timeout_sec": 600,
                "exit_code": 0,
                "duration_sec": 0.1,
                "stdout": _artifact_ref("stdout", "tests/stdout.log", "a" * 64),
                "stderr": _artifact_ref("stderr", "tests/stderr.log", "b" * 64),
            }
        ],
        "artifacts": [],
    }


def _review_report(run_id: str, task_id: str, verdict: str = "PASS") -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": verdict,
        "summary": "ok" if verdict == "PASS" else "failed",
        "scope_check": {"passed": verdict == "PASS", "violations": [] if verdict == "PASS" else ["fail"]},
        "evidence": [],
        "produced_diff": False,
    }


def _task_result(run_id: str, task_id: str, head_ref: str) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "producer": {"role": "WORKER", "agent_id": "agent-1"},
        "status": "SUCCESS",
        "started_at": "2024-01-01T00:00:00Z",
        "finished_at": "2024-01-01T00:00:01Z",
        "summary": "ok",
        "artifacts": [],
        "git": {
            "baseline_ref": "HEAD",
            "head_ref": head_ref,
            "changed_files": _artifact_ref("diff_name_only", "diff_name_only.txt", "c" * 64),
            "patch": _artifact_ref("patch", "patch.diff", "d" * 64),
        },
        "gates": {
            "diff_gate": {"passed": True, "violations": []},
            "policy_gate": {"passed": True, "violations": []},
            "review_gate": {"passed": True, "violations": []},
            "tests_gate": {"passed": True, "violations": []},
        },
        "next_steps": {"suggested_action": "none", "notes": "n/a"},
        "failure": None,
    }


def _init_repo(repo: Path) -> str:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    return sha


def _base_contract(task_id: str, baseline: str) -> dict:
    return {
        "task_id": task_id,
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": baseline},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_replay_verify_missing_files(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = "manual_missing"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=False)

    codes = {item["code"] for item in report["errors"]}
    assert "contract_missing" in codes
    assert "events_missing" in codes
    assert "manifest_missing" in codes
    assert "review_missing" in codes
    assert "test_missing" in codes


def test_replay_verify_contract_invalid_and_patch_mismatch(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("invalid")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", {"task_id": "bad"})
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "bad"}) + "\n")
    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "invalid", "evidence_hashes": {"patch.diff": "deadbeef"}})
    _write(run_dir / "patch.diff", "diff --git a/a b/a\n")
    _write(run_dir / "reports" / "review_report.json", {"bad": True})
    _write(run_dir / "reports" / "test_report.json", {"bad": True})

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=False)
    codes = {item["code"] for item in report["errors"]}
    assert "contract_invalid" in codes
    assert "event_ts_invalid" in codes
    assert "patch_hash_mismatch" in codes
    assert "review_invalid" in codes
    assert "test_invalid" in codes


def test_reexecute_soft_and_hard_diffs(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    baseline = _init_repo(repo)

    runtime_root = tmp_path / "runtime"
    runs_root = runtime_root / "runs"
    worktree_root = runtime_root / "worktrees"
    monkeypatch.setenv("OPENVIBECODING_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("OPENVIBECODING_WORKTREE_ROOT", str(worktree_root))
    monkeypatch.chdir(repo)

    store = RunStore(runs_root=runs_root)
    run_id = store.create_run("reexec")
    run_dir = runs_root / run_id

    contract = _base_contract("reexec-0001", baseline)
    _write(run_dir / "contract.json", contract)
    _write(
        run_dir / "manifest.json",
        {"run_id": run_id, "task_id": "reexec-0001", "repo": {"root": str(repo), "baseline_ref": baseline, "final_ref": baseline}},
    )

    patch_text = "diff --git a/README.md b/README.md\n"
    _write(run_dir / "patch.diff", patch_text)
    _write(run_dir / "diff_name_only.txt", "README.md\n")
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "reexec-0001", ["echo", "ok"]))

    def _fake_tests(*args, **kwargs):
        return {"ok": False, "reports": [], "reason": "fail"}

    monkeypatch.setattr("openvibecoding_orch.replay.replayer.run_acceptance_tests", _fake_tests)
    monkeypatch.setattr("openvibecoding_orch.replay.replayer.worktree_manager.create_worktree", lambda *args, **kwargs: repo)
    monkeypatch.setattr("openvibecoding_orch.replay.replayer.worktree_manager.remove_worktree", lambda *args, **kwargs: None)

    runner = ReplayRunner(store)
    report = runner.reexecute(run_id, strict=True)
    assert report["status"] == "fail"
    assert report["hard_diffs"]
    assert report["soft_diffs"]


def test_reexecute_missing_baseline_and_head(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("reexec_missing")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", {"task_id": "reexec_missing"})
    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "reexec_missing"})

    runner = ReplayRunner(store)
    report = runner.reexecute(run_id, strict=True)
    assert report["status"] == "fail"
    assert any("baseline_ref missing" in err for err in report["errors"])
    assert any("head_ref missing" in err for err in report["errors"])


def test_replay_verify_strict_mismatches(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("strict")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "task-0001",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["src/"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": ""},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }
    _write(run_dir / "contract.json", contract)

    events = [
        {
            "ts": "2024-01-02T00:00:00Z",
            "level": "INFO",
            "event_type": "SCHEMA_DRIFT_DETECTED",
            "run_id": run_id,
            "task_id": "task-0001",
            "attempt": 0,
            "payload": {},
            "event": "TEST_RESULT",
        },
        {
            "ts": "2024-01-01T00:00:00Z",
            "level": "INFO",
            "event_type": "TEST_RESULT",
            "run_id": run_id,
            "task_id": "task-0001",
            "attempt": 0,
            "payload": {},
            "event": "TEST_RESULT",
        },
    ]
    _write(run_dir / "events.jsonl", "\n".join([json.dumps(item) for item in events]) + "\n")

    _write(run_dir / "patch.diff", "diff --git a/README.md b/README.md\n")
    _write(run_dir / "diff_name_only.txt", "README.md\n")

    review_report = _review_report("run-other", "task-0002")
    review_report["attempt"] = 1
    _write(run_dir / "reports" / "review_report.json", review_report)

    test_report = _test_report("run-other2", "task-0003", ["pytest", "-q"])
    test_report["attempt"] = 2
    _write(run_dir / "reports" / "test_report.json", test_report)

    task_result = _task_result("run-other", "task-0004", " ")
    task_result["attempt"] = 3
    _write(run_dir / "reports" / "task_result.json", task_result)

    _write(
        run_dir / "manifest.json",
        {
            "run_id": run_id,
            "task_id": "task-0001",
            "evidence_hashes": {"events.jsonl": "deadbeef", "patch.diff": "deadbeef"},
        },
    )

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "event_order_invalid" in codes
    assert "patch_hash_mismatch" in codes
    assert "test_command_outside_acceptance" in codes
    assert "task_id_mismatch" in codes
    assert "run_id_mismatch" in codes
    assert "attempt_mismatch" in codes
    assert "baseline_missing" in codes
    assert "head_missing" in codes
    assert "manifest_hash_missing" in codes
