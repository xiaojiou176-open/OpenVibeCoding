import json
from pathlib import Path

import pytest
from openvibecoding_orch.chain.runner import ChainRunner
from openvibecoding_orch.store.run_store import RunStore
import hashlib


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


@pytest.fixture(autouse=True)
def _disable_strict_nontrivial(monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_ACCEPTANCE_STRICT_NONTRIVIAL", "0")


def _contract(task_id: str, output_name: str = "out.txt") -> dict:
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


def _execute_stub(store: RunStore):
    def _inner(contract_path: Path, mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = contract.get("task_id", "task")
        run_id = store.create_run(task_id)
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "SUCCESS"})
        return run_id
    return _inner


def test_chain_runner_exclusive_paths_conflict(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    chain = {
        "chain_id": "chain_conflict",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {"name": "s1", "kind": "contract", "payload": _contract("task1"), "exclusive_paths": ["src/"]},
            {"name": "s2", "kind": "contract", "payload": _contract("task2"), "exclusive_paths": ["src/"]},
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")
    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"
    assert report["steps"] == []


def test_chain_runner_keyboard_interrupt_finalizes_manifest_and_report(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)

    def _execute_interrupt(_contract_path: Path, _mock_mode: bool) -> str:
        raise KeyboardInterrupt

    runner = ChainRunner(tmp_path, store, _execute_interrupt)
    chain = {
        "chain_id": "chain_interrupt",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "interrupt_step",
                "kind": "contract",
                "payload": _contract("task_interrupt"),
                "exclusive_paths": ["interrupt/"],
            }
        ],
    }
    chain_path = tmp_path / "chain_interrupt.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"
    run_id = report["run_id"]

    manifest = json.loads((tmp_path / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"
    assert manifest["end_ts"]

    assert (tmp_path / run_id / "reports" / "chain_report.json").exists()
    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_INTERRUPTED" in events_text
    assert "CHAIN_COMPLETED" in events_text
    assert isinstance(report["steps"], list)


def test_chain_runner_continue_on_fail_with_policy_violation(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    chain = {
        "chain_id": "chain_partial",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "strategy": {"continue_on_fail": True},
        "steps": [
            {
                "name": "bad",
                "kind": "contract",
                "payload": _contract("task_bad"),
                "context_policy": {"mode": "summary-only"},
                "exclusive_paths": ["bad/"],
            },
            {"name": "good", "kind": "contract", "payload": _contract("task_okay"), "exclusive_paths": ["good/"]},
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")
    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "PARTIAL"
    assert len(report["steps"]) == 2
    assert any(step.get("status") == "FAILURE" for step in report["steps"])

    run_id = str(report["run_id"])
    run_dir = tmp_path / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PARTIAL"
    assert manifest.get("failure_reason")

    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    lifecycle_meta = next(item for item in events if item.get("event") == "CHAIN_LIFECYCLE_EVALUATED").get("meta", {})
    completed_meta = next(item for item in events if item.get("event") == "CHAIN_COMPLETED").get("meta", {})
    assert lifecycle_meta.get("failure_reason")
    assert completed_meta.get("failure_reason")
    assert lifecycle_meta.get("failure_reason") == completed_meta.get("failure_reason")
    assert lifecycle_meta.get("failure_reason") == manifest.get("failure_reason")


def test_chain_runner_context_policy_violation(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    chain = {
        "chain_id": "chain_policy",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "policy",
                "kind": "contract",
                "payload": _contract("task_policy"),
                "context_policy": {"mode": "summary-only"},
                "exclusive_paths": ["policy/"],
            }
        ],
    }
    chain_path = tmp_path / "chain.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")
    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"


def test_chain_runner_non_terminal_subrun_forces_failure_and_report(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)

    def _execute_non_terminal(contract_path: Path, _mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        run_id = store.create_run(task_id)
        store.write_manifest(
            run_id,
            {
                "run_id": run_id,
                "task_id": task_id,
                "status": "RUNNING",
                "failure_reason": "",
            },
        )
        return run_id

    runner = ChainRunner(tmp_path, store, _execute_non_terminal)
    chain = {
        "chain_id": "chain_non_terminal",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "stalled_step",
                "kind": "contract",
                "payload": _contract("task_stalled"),
                "exclusive_paths": ["stalled/"],
            }
        ],
    }
    chain_path = tmp_path / "chain_non_terminal.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "FAILURE"
    assert len(report["steps"]) == 1
    step = report["steps"][0]
    assert step["status"] == "FAILURE"
    assert "did not reach terminal status" in step["failure_reason"]
    assert "status=RUNNING" in step["failure_reason"]

    run_id = str(report["run_id"])
    assert (tmp_path / run_id / "reports" / "chain_report.json").exists()

    manifest = json.loads((tmp_path / run_id / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILURE"

    events_text = (tmp_path / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "CHAIN_STEP_NON_TERMINAL" in events_text
    assert "CHAIN_COMPLETED" in events_text


def test_chain_runner_stops_later_parallel_group_after_earlier_group_failure(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)

    def _execute_fail_first_group(contract_path: Path, _mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        run_id = store.create_run(task_id)
        status = "FAILURE" if task_id == "task_fail_first_group" else "SUCCESS"
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": status})
        return run_id

    runner = ChainRunner(tmp_path, store, _execute_fail_first_group)
    chain = {
        "chain_id": "chain_parallel_group_failure_short_circuit",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "strategy": {"continue_on_fail": False},
        "steps": [
            {
                "name": "fail_first_group",
                "kind": "contract",
                "payload": _contract("task_fail_first_group"),
                "exclusive_paths": ["fail_first_group/"],
                "parallel_group": "group_a",
            },
            {
                "name": "later_group_should_not_run",
                "kind": "contract",
                "payload": _contract("task_should_not_run"),
                "exclusive_paths": ["later_group_should_not_run/"],
                "parallel_group": "group_z",
            },
        ],
    }
    chain_path = tmp_path / "chain_parallel_group_failure_short_circuit.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "FAILURE"
    step_names = {str(step.get("name")) for step in report["steps"]}
    assert "fail_first_group" in step_names
    assert "later_group_should_not_run" not in step_names


def test_chain_runner_subprocess_missing_run_id_does_not_claim_timeout(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    monkeypatch.setattr(runner, "_chain_exec_mode", lambda: "subprocess")
    monkeypatch.setattr(runner, "_execute_task_subprocess", lambda _chain_run_id, _contract_ref, _mock_mode: "")

    chain = {
        "chain_id": "chain_subprocess_missing_run_id",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "strategy": {"continue_on_fail": False},
        "steps": [
            {
                "name": "s1",
                "kind": "contract",
                "payload": _contract("task_subproc_s1"),
                "exclusive_paths": ["s1/"],
                "parallel_group": "group_x",
            },
            {
                "name": "s2",
                "kind": "contract",
                "payload": _contract("task_subproc_s2"),
                "exclusive_paths": ["s2/"],
                "parallel_group": "group_x",
            },
        ],
    }
    chain_path = tmp_path / "chain_subprocess_missing_run_id.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=False)
    assert report["status"] == "FAILURE"
    assert report["steps"]
    assert all("timeout" not in str(item.get("failure_reason", "")).lower() for item in report["steps"])


def test_chain_runner_continue_on_fail_does_not_allow_blocked_status(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    executed: list[str] = []

    def _execute_blocked(contract_path: Path, _mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        executed.append(task_id)
        run_id = store.create_run(task_id)
        status = "BLOCKED" if task_id == "task_blocked" else "SUCCESS"
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": status})
        return run_id

    runner = ChainRunner(tmp_path, store, _execute_blocked)
    chain = {
        "chain_id": "chain_continue_on_fail_blocked",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "strategy": {"continue_on_fail": True},
        "steps": [
            {
                "name": "blocked_step",
                "kind": "contract",
                "payload": _contract("task_blocked"),
                "exclusive_paths": ["blocked_step/"],
                "parallel_group": "group_a",
            },
            {
                "name": "must_not_run",
                "kind": "contract",
                "payload": _contract("task_must_not_run"),
                "exclusive_paths": ["must_not_run/"],
                "parallel_group": "group_b",
            },
        ],
    }
    chain_path = tmp_path / "chain_continue_on_fail_blocked.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"
    assert executed == ["task_blocked"]


def test_chain_runner_continue_on_fail_unknown_status_not_promoted_to_partial(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)

    def _execute_unknown(contract_path: Path, _mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        run_id = store.create_run(task_id)
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "UNKNOWN"})
        return run_id

    runner = ChainRunner(tmp_path, store, _execute_unknown)
    chain = {
        "chain_id": "chain_continue_on_fail_unknown",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "strategy": {"continue_on_fail": True},
        "steps": [
            {
                "name": "unknown_step",
                "kind": "contract",
                "payload": _contract("task_unknown"),
                "exclusive_paths": ["unknown_step/"],
                "parallel_group": "group_a",
            }
        ],
    }
    chain_path = tmp_path / "chain_continue_on_fail_unknown.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"
    assert report["steps"][0]["status"] == "FAILURE"
