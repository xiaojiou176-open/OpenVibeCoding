import hashlib
import hmac
import json
from pathlib import Path

import subprocess

from cortexpilot_orch.replay.replayer import (
    ReplayRunner,
    _collect_evidence_hashes,
    _collect_diff_text,
    _expected_reports,
    _extract_diff_names_from_patch,
    _hash_events,
    _is_allowed,
    _load_acceptance_commands,
    _load_baseline_hashes,
    _load_changed_files,
    _load_events,
)
from cortexpilot_orch.store.run_store import RunStore


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


def _review_report(run_id: str, task_id: str, verdict: str = "PASS", produced_diff: bool = False) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": verdict,
        "summary": "ok" if verdict == "PASS" else "failed",
        "scope_check": {"passed": verdict == "PASS", "violations": [] if verdict == "PASS" else ["fail"]},
        "evidence": [],
        "produced_diff": produced_diff,
    }


def _task_result(run_id: str, task_id: str) -> dict:
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
            "head_ref": "HEAD",
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


def _base_contract(task_id: str) -> dict:
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
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def _write_verify_bundle(store: RunStore, run_id: str, run_dir: Path, task_id: str) -> None:
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "TEST_RESULT",
            "run_id": run_id,
            "context": {"task_id": task_id, "attempt": 0},
        },
    )
    _write(run_dir / "patch.diff", "diff --git a/out.txt b/out.txt\n")
    _write(run_dir / "diff_name_only.txt", "out.txt\n")
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, task_id))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, task_id, ["echo", "ok"]))
    _write(run_dir / "reports" / "task_result.json", _task_result(run_id, task_id))
    manifest = {"run_id": run_id, "task_id": task_id, "evidence_hashes": _collect_evidence_hashes(run_dir)}
    _write(run_dir / "manifest.json", manifest)


def test_extract_diff_names_from_patch_handles_multiple_files() -> None:
    patch = "\n".join(
        [
            "diff --git a/a.txt b/a.txt",
            "diff --git a/dir/b.txt b/dir/b.txt",
        ]
    )
    names = _extract_diff_names_from_patch(patch)
    assert names == ["a.txt", "dir/b.txt"]


def test_load_acceptance_commands_supports_dict_and_list() -> None:
    contract = {"acceptance_tests": [{"cmd": "echo ok"}, "pytest -q"]}
    commands = _load_acceptance_commands(contract)
    assert commands == {("echo", "ok"), ("pytest", "-q")}


def test_replay_runner_replay_detects_missing_reports_and_hash_mismatch(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    baseline_id = store.create_run("baseline")
    run_id = store.create_run("current")

    baseline_dir = tmp_path / baseline_id
    _write(baseline_dir / "manifest.json", {"run_id": baseline_id, "task_id": "task"})
    _write(baseline_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(baseline_dir / "patch.diff", "diff --git a/a b/a\n")
    _write(baseline_dir / "reports" / "test_report.json", _test_report(baseline_id, "task", ["echo", "ok"]))

    run_dir = tmp_path / run_id
    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "task"})
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(run_dir / "patch.diff", "diff --git a/a b/a\ncorrupt\n")

    runner = ReplayRunner(store)
    report = runner.replay(run_id, baseline_run_id=baseline_id)
    assert report["status"] == "fail"
    assert "test_report.json" in report["missing_reports"]
    assert report["evidence_hashes"]["mismatched"]


def test_replay_verify_strict_collects_errors(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "verify_task",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }
    _write(run_dir / "contract.json", contract)
    _write(
        run_dir / "events.jsonl",
        "\n".join(
            [
                "not-json",
                json.dumps({"event": "SCHEMA_DRIFT_DETECTED", "ts": "2024-01-02T00:00:00Z"}),
                json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}),
            ]
        )
        + "\n",
    )
    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "task", "evidence_hashes": {}})
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, "task"))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "task", ["unexpected"]))

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "event_not_json" in codes
    assert "event_order_invalid" in codes
    assert "manifest_hashes_missing" in codes
    assert "diff_name_only_missing" in codes


def test_replayer_collect_diff_and_hash_events(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True, text=True)
    (repo / "new.txt").write_text("new", encoding="utf-8")

    diff_text = _collect_diff_text(repo, "HEAD")
    assert "new.txt" in diff_text

    events_path = repo / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"event": "REPLAY_START", "ts": "2024-01-01T00:00:00Z"}),
                json.dumps({"event": "CUSTOM", "ts": "2024-01-01T00:00:01Z"}),
                json.dumps({"event": "REPLAY_DONE", "ts": "2024-01-01T00:00:02Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    digest = _hash_events(events_path)
    assert digest


def test_replay_verify_contract_signature_invalid_strict(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_CONTRACT_HMAC_KEY", "secret")
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("sig_invalid")
    run_dir = tmp_path / run_id

    contract = _base_contract("sig_invalid")
    _write(run_dir / "contract.json", contract)
    contract_path = run_dir / "contract.json"
    bad_sig = hmac.new(b"wrong", contract_path.read_bytes(), hashlib.sha256).hexdigest()
    _write(run_dir / "contract.sig", bad_sig)
    _write_verify_bundle(store, run_id, run_dir, "sig_invalid")

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "contract_signature_invalid" in codes


def test_replay_verify_hashchain_invalid_strict(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("hashchain_invalid")
    run_dir = tmp_path / run_id

    contract = _base_contract("hashchain_invalid")
    _write(run_dir / "contract.json", contract)
    _write_verify_bundle(store, run_id, run_dir, "hashchain_invalid")

    (run_dir / "events.hashchain.jsonl").write_text("invalid\n", encoding="utf-8")

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "events_hashchain_invalid" in codes


def test_replay_verify_hashchain_missing_strict(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("hashchain_missing")
    run_dir = tmp_path / run_id

    contract = _base_contract("hashchain_missing")
    _write(run_dir / "contract.json", contract)
    _write_verify_bundle(store, run_id, run_dir, "hashchain_missing")
    (run_dir / "events.hashchain.jsonl").unlink(missing_ok=True)

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "events_hashchain_missing" in codes


def test_replay_verify_strict_binds_run_id_to_verify_target(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify_target_bind")
    run_dir = tmp_path / run_id

    contract = _base_contract("verify_target_bind")
    _write(run_dir / "contract.json", contract)
    _write_verify_bundle(store, run_id, run_dir, "verify_target_bind")

    wrong_id = "run-not-target"
    review_path = run_dir / "reports" / "review_report.json"
    test_path = run_dir / "reports" / "test_report.json"
    task_result_path = run_dir / "reports" / "task_result.json"
    review_payload = json.loads(review_path.read_text(encoding="utf-8"))
    test_payload = json.loads(test_path.read_text(encoding="utf-8"))
    task_payload = json.loads(task_result_path.read_text(encoding="utf-8"))
    review_payload["run_id"] = wrong_id
    test_payload["run_id"] = wrong_id
    task_payload["run_id"] = wrong_id
    _write(review_path, review_payload)
    _write(test_path, test_payload)
    _write(task_result_path, task_payload)

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "run_id_target_mismatch" in codes


def test_replay_verify_flags_review_and_diff_gate(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify_review")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "verify_review",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "spec", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "mcp_tool_set": ["01-filesystem"],
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }
    _write(run_dir / "contract.json", contract)
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "verify_review", "evidence_hashes": {"patch.diff": "bad"}})
    _write(run_dir / "patch.diff", "diff --git a/out.txt b/out.txt\n")
    _write(run_dir / "diff_name_only.txt", "outside.txt\n")
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, "verify_review", produced_diff=True))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "verify_review", ["not-allowed"]))

    runner = ReplayRunner(store)
    original_validate = runner._validator.validate_report_file
    def _fake_validate(path: Path, schema_name: str):
        if schema_name == "review_report.v1.json":
            return json.loads(path.read_text(encoding="utf-8"))
        return original_validate(path, schema_name)
    runner._validator.validate_report_file = _fake_validate  # type: ignore[assignment]
    report = runner.verify(run_id, strict=False)
    codes = {item["code"] for item in report["errors"]}
    assert "review_produced_diff" in codes
    assert "diff_gate_violation" in codes


def test_replayer_helper_functions(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_helper"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write(run_dir / "events.jsonl", "\n".join([json.dumps({"event": "TEST_RESULT"}), "raw"]) + "\n")
    _write(run_dir / "manifest.json", {"evidence_hashes": {"events.jsonl": "abc"}})
    _write(run_dir / "diff_name_only.txt", "src/app.py\n")

    events = _load_events(run_dir / "events.jsonl")
    assert events[0]["event"] == "TEST_RESULT"
    assert "raw" in events[1]

    baseline = _load_baseline_hashes(run_dir)
    assert baseline.get("events.jsonl") == "abc"

    changed = _load_changed_files(run_dir)
    assert changed == ["src/app.py"]

    expected = _expected_reports([{"event": "TEST_RESULT"}, {"event": "TASK_RESULT_RECORDED"}])
    assert "test_report.json" in expected
    assert "task_result.json" in expected

    assert _is_allowed("src/app.py", ["src/"]) is True
    assert _is_allowed("docs/readme.md", ["src/"]) is False
