import hashlib
import json
from pathlib import Path

import pytest

from openvibecoding_orch.replay.replayer import (
    ReplayRunner,
    _collect_evidence_hashes,
    _git,
    _git_allow_nonzero,
    _hash_events,
    _is_allowed,
    _load_acceptance_commands,
    _load_baseline_hashes,
    _load_events,
)
from openvibecoding_orch.store.run_store import RunStore


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
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {"filesystem": "workspace-write", "shell": "on-request", "network": "deny", "mcp_tools": ["codex"]},
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_hash_events_handles_blank_and_invalid(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                "",
                "not-json",
                json.dumps({"event": "REPLAY_START", "ts": "2024-01-01T00:00:00Z"}),
                json.dumps({"event": "CUSTOM", "ts": "2024-01-01T00:00:01Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    digest = _hash_events(events_path)
    assert digest


def test_git_helpers_raise_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(RuntimeError):
        _git(["git", "rev-parse", "HEAD"], cwd=repo)
    with pytest.raises(RuntimeError):
        _git_allow_nonzero(["git", "diff", "--no-index", "/dev/null", "missing"], cwd=repo, allowed=(0,))


def test_load_baseline_hashes_invalid_manifest_falls_back(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write(run_dir / "manifest.json", "{bad-json")
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    hashes = _load_baseline_hashes(run_dir)
    assert "events.jsonl" in hashes


def test_acceptance_commands_ignore_non_list() -> None:
    contract = {"acceptance_tests": "nope"}
    assert _load_acceptance_commands(contract) == set()


def test_is_allowed_skips_empty_entries() -> None:
    assert _is_allowed("src/app.py", ["", "src/"]) is True
    assert _is_allowed("src/app.py", [""]) is False


def test_collect_evidence_hashes_covers_nested_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "reports").mkdir(parents=True)
    (run_dir / "tasks").mkdir()
    (run_dir / "results" / "task").mkdir(parents=True)
    (run_dir / "reviews").mkdir()
    (run_dir / "ci" / "task").mkdir(parents=True)
    (run_dir / "git").mkdir()
    (run_dir / "tests").mkdir()
    (run_dir / "trace").mkdir()
    _write(run_dir / "reports" / "custom.json", {"ok": True})
    _write(run_dir / "tasks" / "task.json", {"task_id": "task"})
    _write(run_dir / "results" / "task" / "result.json", {"task_id": "task"})
    _write(run_dir / "results" / "task" / "patch.diff", "diff --git a/a b/a\n")
    _write(run_dir / "reviews" / "review.json", {"task_id": "task"})
    _write(run_dir / "ci" / "task" / "report.json", {"ok": True})
    _write(run_dir / "git" / "baseline_commit.txt", "HEAD")
    _write(run_dir / "tests" / "stdout.log", "ok")
    _write(run_dir / "trace" / "trace_id.txt", "trace")
    hashes = _collect_evidence_hashes(run_dir)
    assert "reports/custom.json" in hashes
    assert "results/task/patch.diff" in hashes


def test_replay_report_checks_unknown_and_invalid_schema(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    baseline_id = store.create_run("baseline")
    run_id = store.create_run("current")
    baseline_dir = tmp_path / baseline_id
    run_dir = tmp_path / run_id

    _write(baseline_dir / "manifest.json", {"run_id": baseline_id, "task_id": "task"})
    _write(baseline_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")

    _write(run_dir / "manifest.json", {"run_id": run_id, "task_id": "task"})
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(run_dir / "reports" / "custom.json", {"ok": True})
    _write(run_dir / "reports" / "test_report.json", {"task_id": "task"})

    runner = ReplayRunner(store)
    report = runner.replay(run_id, baseline_run_id=baseline_id)
    assert report["report_checks"]["custom.json"]["ok"] is True
    assert report["report_checks"]["test_report.json"]["ok"] is False


def test_verify_manifest_invalid_and_event_ts_invalid(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify_invalid")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", _base_contract("verify_invalid"))
    _write(
        run_dir / "events.jsonl",
        json.dumps({"event": "TEST_RESULT", "ts": "bad-ts"}) + "\n",
    )
    _write(run_dir / "manifest.json", "{bad-json")
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, "verify_invalid"))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "verify_invalid", ["echo", "ok"]))

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=False)
    codes = {item["code"] for item in report["errors"]}
    assert "event_ts_invalid" in codes
    assert "manifest_invalid" in codes


def test_verify_patch_missing_and_command_list(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify_patch_missing")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", _base_contract("verify_patch_missing"))
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(run_dir / "manifest.json", {"evidence_hashes": {"patch.diff": "abc"}})
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, "verify_patch_missing"))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "verify_patch_missing", ["echo", "ok"]))

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=False)
    codes = {item["code"] for item in report["errors"]}
    assert "patch_missing" in codes


def test_verify_strict_evidence_missing(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("verify_missing")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", _base_contract("verify_missing"))
    _write(run_dir / "events.jsonl", json.dumps({"event": "TEST_RESULT", "ts": "2024-01-01T00:00:00Z"}) + "\n")
    _write(
        run_dir / "manifest.json",
        {
            "evidence_hashes": {
                "contract.json": "x",
                "events.jsonl": "y",
                "patch.diff": "z",
                "diff_name_only.txt": "w",
                "reports/review_report.json": "r",
                "reports/test_report.json": "t",
            }
        },
    )
    _write(run_dir / "reports" / "review_report.json", _review_report(run_id, "verify_missing"))
    _write(run_dir / "reports" / "test_report.json", _test_report(run_id, "verify_missing", ["echo", "ok"]))

    runner = ReplayRunner(store)
    report = runner.verify(run_id, strict=True)
    codes = {item["code"] for item in report["errors"]}
    assert "evidence_missing" in codes


def test_reexecute_invalid_inputs(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("reexec_invalid")
    run_dir = tmp_path / run_id

    _write(run_dir / "contract.json", _base_contract("reexec_invalid"))
    _write(run_dir / "manifest.json", "{bad-json")
    _write(run_dir / "reports" / "task_result.json", "{bad-json")
    _write(run_dir / "reports" / "test_report.json", "{bad-json")

    runner = ReplayRunner(store)
    report = runner.reexecute(run_id, strict=True)
    assert any(str(item).startswith("manifest invalid") for item in report["errors"])
    assert "task_result invalid" in report["errors"]
    assert "test_report invalid" in report["errors"]
