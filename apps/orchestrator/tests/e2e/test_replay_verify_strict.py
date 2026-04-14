import json
from pathlib import Path

import pytest
from openvibecoding_orch.contract.validator import ContractValidator
from openvibecoding_orch.replay.replayer import ReplayRunner, _collect_evidence_hashes
from openvibecoding_orch.store.run_store import RunStore
import hashlib

pytestmark = pytest.mark.e2e


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_manifest(run_dir: Path, run_id: str) -> None:
    manifest = {"run_id": run_id, "evidence_hashes": _collect_evidence_hashes(run_dir)}
    _write_json(run_dir / "manifest.json", manifest)


def _artifact_ref(name: str, path: str, sha: str) -> dict:
    return {"name": name, "path": path, "sha256": sha}


def _test_report(run_id: str, task_id: str, cmd_argv: list[str]) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": 0,
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


def _review_report(run_id: str, task_id: str) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": 0,
        "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
        "reviewed_at": "2024-01-01T00:00:00Z",
        "verdict": "PASS",
        "summary": "ok",
        "scope_check": {"passed": True, "violations": []},
        "evidence": [],
        "produced_diff": False,
    }


def _task_result(run_id: str, task_id: str) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "attempt": 0,
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


def _build_base_bundle(tmp_path: Path) -> tuple[RunStore, str, Path]:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_strict")
    run_dir = tmp_path / run_id

    contract = {
        "task_id": "task_strict",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "strict verify bundle", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "README.md", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["README.md"],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "echo", "cmd": "echo ok", "must_pass": True}],
        "tool_permissions": {
            "filesystem": "read-only",
            "shell": "on-request",
            "network": "deny",
            "mcp_tools": ["codex"],
        },
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
        "rollback": {"strategy": "git_reset_hard", "baseline_ref": "HEAD"},
        "evidence_links": [],
        "log_refs": {"run_id": run_id, "paths": {}},
    }
    _write_json(run_dir / "contract.json", contract)

    task_result = _task_result(run_id, "task_strict")
    review_report = _review_report(run_id, "task_strict")
    test_report = _test_report(run_id, "task_strict", ["echo", "ok"])

    _write_json(run_dir / "reports" / "task_result.json", task_result)
    _write_json(run_dir / "reports" / "review_report.json", review_report)
    _write_json(run_dir / "reports" / "test_report.json", test_report)

    (run_dir / "patch.diff").write_text("", encoding="utf-8")
    (run_dir / "diff_name_only.txt").write_text("README.md\n", encoding="utf-8")

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "STEP_STARTED",
            "run_id": run_id,
            "context": {"task_id": "task_strict", "attempt": 0},
        },
    )

    _write_manifest(run_dir, run_id)
    return store, run_id, run_dir


def _assert_error(report: dict, code: str) -> None:
    assert report["status"] == "fail"
    assert any(item.get("code") == code for item in report.get("errors", []))


def test_strict_task_id_mismatch(tmp_path: Path) -> None:
    store, run_id, run_dir = _build_base_bundle(tmp_path)
    review_path = run_dir / "reports" / "review_report.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["task_id"] = "task_wrong"
    _write_json(review_path, review)
    _write_manifest(run_dir, run_id)

    runner = ReplayRunner(store, ContractValidator())
    report = runner.verify(run_id, strict=True)
    _assert_error(report, "task_id_mismatch")


def test_strict_manifest_hash_missing(tmp_path: Path) -> None:
    store, run_id, run_dir = _build_base_bundle(tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = manifest.get("evidence_hashes", {})
    evidence.pop("reports/test_report.json", None)
    manifest["evidence_hashes"] = evidence
    _write_json(manifest_path, manifest)

    runner = ReplayRunner(store, ContractValidator())
    report = runner.verify(run_id, strict=True)
    _assert_error(report, "manifest_hash_missing")


def test_strict_test_command_outside_acceptance(tmp_path: Path) -> None:
    store, run_id, run_dir = _build_base_bundle(tmp_path)
    test_path = run_dir / "reports" / "test_report.json"
    test_report = json.loads(test_path.read_text(encoding="utf-8"))
    test_report["commands"][0]["cmd_argv"] = ["echo", "nope"]
    test_report["commands"][0]["name"] = "echo nope"
    _write_json(test_path, test_report)
    _write_manifest(run_dir, run_id)

    runner = ReplayRunner(store, ContractValidator())
    report = runner.verify(run_id, strict=True)
    _assert_error(report, "test_command_outside_acceptance")


def test_strict_review_produced_diff(tmp_path: Path) -> None:
    store, run_id, run_dir = _build_base_bundle(tmp_path)
    review_path = run_dir / "reports" / "review_report.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["produced_diff"] = True
    _write_json(review_path, review)
    _write_manifest(run_dir, run_id)

    runner = ReplayRunner(store, ContractValidator())
    report = runner.verify(run_id, strict=True)
    assert report["status"] == "fail"
