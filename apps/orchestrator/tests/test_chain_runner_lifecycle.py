import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.store.run_store import RunStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _disable_strict_nontrivial(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "0")


def _output_schema_artifacts(role: str) -> list[dict]:
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


def _contract(task_id: str, owner_role: str, assigned_role: str, output_name: str) -> dict:
    return {
        "task_id": task_id,
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
        "allowed_paths": [output_name],
        "forbidden_actions": [],
        "acceptance_tests": [{"name": "noop", "cmd": "echo ok", "must_pass": True}],
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


def _execute_stub(store: RunStore, reviewer_verdicts: dict[str, str]):
    def _inner(contract_path: Path, mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        assigned = contract.get("assigned_agent") if isinstance(contract.get("assigned_agent"), dict) else {}
        assigned_role = str(assigned.get("role") or "WORKER").upper()

        run_id = store.create_run(task_id)
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "SUCCESS"})

        task_result = {
            "run_id": run_id,
            "task_id": task_id,
            "status": "SUCCESS",
            "summary": f"{task_id} done",
            "started_at": _now(),
            "finished_at": _now(),
        }
        store.write_report(run_id, "task_result", task_result)
        store.write_task_result(run_id, task_id, task_result)

        if assigned_role == "REVIEWER":
            verdict = reviewer_verdicts.get(task_id, "PASS").upper()
            review_report = {
                "run_id": run_id,
                "task_id": task_id,
                "attempt": 0,
                "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
                "reviewed_at": _now(),
                "verdict": verdict,
                "summary": "review ok" if verdict == "PASS" else "review failed",
                "scope_check": {"passed": verdict == "PASS", "violations": [] if verdict == "PASS" else ["violation"]},
                "evidence": [],
                "produced_diff": False,
            }
            store.write_report(run_id, "review_report", review_report)

        if assigned_role in {"TEST", "TEST_RUNNER"}:
            test_report = {
                "run_id": run_id,
                "task_id": task_id,
                "attempt": 0,
                "runner": {"role": "TEST_RUNNER", "agent_id": "test-runner-1"},
                "started_at": _now(),
                "finished_at": _now(),
                "status": "PASS",
                "commands": [],
                "artifacts": [],
            }
            store.write_report(run_id, "test_report", test_report)

        return run_id

    return _inner


def _chain_payload(chain_id: str) -> dict:
    return {
        "chain_id": chain_id,
        "owner_agent": {"role": "PM", "agent_id": "pm-1", "codex_thread_id": ""},
        "strategy": {
            "continue_on_fail": False,
            "lifecycle": {
                "enforce": True,
                "min_workers": 2,
                "min_reviewers": 2,
                "reviewer_quorum": 2,
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
                    "assigned_agent": {"role": "TECH_LEAD", "agent_id": "agent-1", "codex_thread_id": ""},
                },
            },
            {
                "name": "worker_a",
                "kind": "contract",
                "payload": _contract("worker_a", "TECH_LEAD", "WORKER", ".runtime-cache/test_output/worker_markers/worker_a.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/worker_a.txt"],
                "depends_on": ["pm_to_tl"],
                "parallel_group": "workers",
            },
            {
                "name": "worker_b",
                "kind": "contract",
                "payload": _contract("worker_b", "TECH_LEAD", "FRONTEND", ".runtime-cache/test_output/worker_markers/worker_b.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/worker_b.txt"],
                "depends_on": ["pm_to_tl"],
                "parallel_group": "workers",
            },
            {
                "name": "review_a",
                "kind": "contract",
                "payload": _contract("review_a", "TECH_LEAD", "REVIEWER", ".runtime-cache/test_output/worker_markers/review_a.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/review_a.txt"],
                "depends_on": ["worker_a", "worker_b"],
                "parallel_group": "reviewers",
            },
            {
                "name": "review_b",
                "kind": "contract",
                "payload": _contract("review_b", "TECH_LEAD", "REVIEWER", ".runtime-cache/test_output/worker_markers/review_b.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/review_b.txt"],
                "depends_on": ["worker_a", "worker_b"],
                "parallel_group": "reviewers",
            },
            {
                "name": "testing",
                "kind": "contract",
                "payload": _contract("testing01", "TECH_LEAD", "TEST_RUNNER", ".runtime-cache/test_output/worker_markers/testing.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/testing.txt"],
                "depends_on": ["review_a", "review_b"],
            },
            {
                "name": "tl_to_pm",
                "kind": "handoff",
                "payload": {
                    "task_id": "tl_to_pm_01",
                    "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1", "codex_thread_id": ""},
                    "assigned_agent": {"role": "PM", "agent_id": "agent-1", "codex_thread_id": ""},
                },
                "depends_on": ["testing"],
            },
        ],
    }


def test_chain_runner_lifecycle_enforced_success(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store, {"review_a": "PASS", "review_b": "PASS"}))

    chain_path = tmp_path / "chain_lifecycle_success.json"
    chain_path.write_text(json.dumps(_chain_payload("chain_lifecycle_success"), ensure_ascii=False, indent=2), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "SUCCESS"
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is True
    assert lifecycle["workers"]["observed"] >= 2
    assert lifecycle["reviewers"]["observed"] == 2
    assert lifecycle["reviewers"]["pass"] == 2
    assert lifecycle["reviewers"]["quorum_met"] is True
    assert lifecycle["tests"]["ok"] is True
    assert lifecycle["return_to_pm"]["ok"] is True



def test_chain_runner_lifecycle_enforced_fails_on_reviewer_quorum(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store, {"review_a": "PASS", "review_b": "FAIL"}))

    chain_path = tmp_path / "chain_lifecycle_fail.json"
    chain_path.write_text(json.dumps(_chain_payload("chain_lifecycle_fail01"), ensure_ascii=False, indent=2), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "FAILURE"
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is False
    assert lifecycle["reviewers"]["observed"] == 2
    assert lifecycle["reviewers"]["pass"] == 1
    assert lifecycle["reviewers"]["fail"] == 1
    assert lifecycle["reviewers"]["quorum_met"] is False

    run_id = str(report["run_id"])
    run_dir = tmp_path / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"

    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle_index = next(i for i, item in enumerate(events) if item.get("event") == "CHAIN_LIFECYCLE_EVALUATED")
    completed_index = next(i for i, item in enumerate(events) if item.get("event") == "CHAIN_COMPLETED")
    assert lifecycle_index < completed_index

    lifecycle_meta = events[lifecycle_index].get("meta", {})
    completed_meta = events[completed_index].get("meta", {})
    assert isinstance(lifecycle_meta, dict)
    assert isinstance(completed_meta, dict)
    assert lifecycle_meta.get("failure_reason")
    assert completed_meta.get("failure_reason")
    assert lifecycle_meta.get("failure_reason") == completed_meta.get("failure_reason")
    assert lifecycle_meta.get("failure_reason") == manifest.get("failure_reason")


def test_chain_runner_lifecycle_mock_mode_ignores_subprocess_exec_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_CHAIN_EXEC_MODE", "subprocess")
    monkeypatch.setenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", "1")

    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store, {"review_a": "PASS", "review_b": "PASS"}))

    chain_path = tmp_path / "chain_lifecycle_mock_inline.json"
    chain_path.write_text(
        json.dumps(_chain_payload("chain_lifecycle_mock_inline"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "SUCCESS"

    events = [
        json.loads(line)
        for line in (tmp_path / str(report["run_id"]) / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert not any(item.get("event") == "CHAIN_SUBPROCESS_LAUNCHED" for item in events)


def test_chain_runner_persists_final_manifest_before_completed_event(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store, {"review_a": "PASS", "review_b": "FAIL"}))

    operations: list[tuple[str, str, str]] = []
    original_write_manifest = store.write_manifest
    original_append_event = store.append_event

    def _record_write_manifest(run_id: str, payload: dict) -> None:
        operations.append(("manifest", run_id, str(payload.get("status", ""))))
        original_write_manifest(run_id, payload)

    def _record_append_event(run_id: str, payload: dict) -> None:
        operations.append(("event", run_id, str(payload.get("event", ""))))
        original_append_event(run_id, payload)

    monkeypatch.setattr(store, "write_manifest", _record_write_manifest)
    monkeypatch.setattr(store, "append_event", _record_append_event)

    chain_path = tmp_path / "chain_lifecycle_order.json"
    chain_path.write_text(
        json.dumps(_chain_payload("chain_lifecycle_order01"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = runner.run_chain(chain_path, mock_mode=True)
    run_id = str(report["run_id"])

    final_manifest_idx = max(
        i
        for i, (kind, rid, value) in enumerate(operations)
        if kind == "manifest" and rid == run_id and value == "FAILURE"
    )
    completed_idx = min(
        i
        for i, (kind, rid, value) in enumerate(operations)
        if kind == "event" and rid == run_id and value == "CHAIN_COMPLETED"
    )
    assert final_manifest_idx < completed_idx
