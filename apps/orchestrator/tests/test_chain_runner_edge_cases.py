import json
from pathlib import Path

import pytest

from cortexpilot_orch.chain import helpers as chain_helpers
from cortexpilot_orch.chain import runner as chain_runner
from cortexpilot_orch.chain.runner import ChainRunner
from cortexpilot_orch.store.run_store import RunStore
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
    monkeypatch.setenv("CORTEXPILOT_ACCEPTANCE_STRICT_NONTRIVIAL", "0")


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
        "mcp_tool_set": ["01-filesystem"],
        "timeout_retry": {"timeout_sec": 1, "max_retries": 0, "retry_backoff_sec": 0},
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


def test_chain_helpers_load_manifest_and_step_task_id(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    assert chain_runner._load_manifest(runs_root, "missing") == {}

    payload = {"plan_id": "plan-01"}
    assert chain_helpers._step_task_id("plan", payload) == "plan-01"
    payload = {"plan_id": "plan-01", "task_id": "task-01"}
    assert chain_helpers._step_task_id("plan", payload) == "task-01"

    handoff = {"task_id": "handoff_01"}
    assert chain_helpers._step_task_id("handoff", handoff) == "handoff_01"


def test_chain_runner_rejects_invalid_payload_and_kind(tmp_path: Path, monkeypatch) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    monkeypatch.setattr(runner._validator, "validate_report", lambda payload, schema: payload)

    chain_payload = {
        "chain_id": "chain_payload",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {"name": "aaa-payload", "kind": "contract", "payload": "oops", "exclusive_paths": ["a/"]},
        ],
    }
    payload_path = tmp_path / "chain_payload.json"
    payload_path.write_text(json.dumps(chain_payload), encoding="utf-8")

    with pytest.raises(AttributeError):
        runner.run_chain(payload_path, mock_mode=True)

    chain_kind = {
        "chain_id": "chain_kind",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {"name": "zzz-kind", "kind": "weird", "payload": _contract("task2"), "exclusive_paths": ["b/"]},
        ],
    }
    kind_path = tmp_path / "chain_kind.json"
    kind_path.write_text(json.dumps(chain_kind), encoding="utf-8")

    report_kind = runner.run_chain(kind_path, mock_mode=True)
    assert report_kind["status"] == "FAILURE"
    assert "unsupported step kind" in report_kind["steps"][0]["failure_reason"]


def test_chain_runner_accepts_handoff_steps_without_execution(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))

    chain_handoff = {
        "chain_id": "chain_handoff",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "pm_to_tl",
                "kind": "handoff",
                "payload": {
                    "task_id": "pm_to_tl_01",
                    "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                    "assigned_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
                },
            },
            {
                "name": "tl_to_pm",
                "kind": "handoff",
                "payload": {
                    "task_id": "tl_to_pm_01",
                    "owner_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
                    "assigned_agent": {"role": "PM", "agent_id": "agent-1"},
                },
                "depends_on": ["pm_to_tl"],
            },
        ],
    }
    handoff_path = tmp_path / "chain_handoff.json"
    handoff_path.write_text(json.dumps(chain_handoff), encoding="utf-8")

    report = runner.run_chain(handoff_path, mock_mode=True)
    assert report["status"] == "SUCCESS"
    assert [step["kind"] for step in report["steps"]] == ["handoff", "handoff"]
    lifecycle = report["lifecycle"]
    assert lifecycle["is_complete"] is False
    assert lifecycle["workers"]["observed"] == 0


def test_chain_runner_detects_duplicate_and_cycle(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))

    chain_dup = {
        "chain_id": "chain_dup",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {"name": "dup", "kind": "contract", "payload": _contract("task1"), "exclusive_paths": ["a/"]},
            {"name": "dup", "kind": "contract", "payload": _contract("task2"), "exclusive_paths": ["b/"]},
        ],
    }
    dup_path = tmp_path / "chain_dup.json"
    dup_path.write_text(json.dumps(chain_dup), encoding="utf-8")
    try:
        report_dup = runner.run_chain(dup_path, mock_mode=True)
    except ValueError as exc:
        assert "duplicate step name" in str(exc)
    else:
        assert report_dup["status"] == "FAILURE"
        assert report_dup.get("steps") == []

    chain_cycle = {
        "chain_id": "chain_cycle",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "a",
                "kind": "contract",
                "payload": _contract("task_a"),
                "depends_on": ["b"],
                "exclusive_paths": ["a/"],
            },
            {
                "name": "b",
                "kind": "contract",
                "payload": _contract("task_b"),
                "depends_on": ["a"],
                "exclusive_paths": ["b/"],
            },
        ],
    }
    cycle_path = tmp_path / "chain_cycle.json"
    cycle_path.write_text(json.dumps(chain_cycle), encoding="utf-8")
    try:
        report_cycle = runner.run_chain(cycle_path, mock_mode=True)
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        assert report_cycle["status"] == "FAILURE"
        assert report_cycle.get("steps") == []

def _execute_stub_with_contracts(store: RunStore, include_contracts: bool):
    def _inner(contract_path: Path, mock_mode: bool) -> str:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        task_id = str(contract.get("task_id") or "task")
        run_id = store.create_run(task_id)
        store.write_manifest(run_id, {"run_id": run_id, "task_id": task_id, "status": "SUCCESS"})

        task_result = {
            "run_id": run_id,
            "task_id": task_id,
            "status": "SUCCESS",
            "summary": f"{task_id} done",
            "evidence_refs": {},
        }
        if include_contracts and task_id == "producer":
            task_result["contracts"] = [_contract("generated_contract", ".runtime-cache/test_output/worker_markers/generated.txt")]

        store.write_report(run_id, "task_result", task_result)
        store.write_task_result(run_id, task_id, task_result)
        return run_id

    return _inner


def test_chain_runner_contract_from_resolution_success(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub_with_contracts(store, include_contracts=True))

    chain_payload = {
        "chain_id": "chain_contract_from_success",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "producer",
                "kind": "contract",
                "payload": _contract("producer", ".runtime-cache/test_output/worker_markers/producer.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/producer.txt"],
            },
            {
                "name": "consumer",
                "kind": "contract",
                "payload": {
                    "contract_from": "producer",
                    "contract_index": 0,
                    "contract_overrides": {
                        "task_id": "consumer",
                        "required_outputs": [{"name": ".runtime-cache/test_output/worker_markers/consumer.txt", "type": "file", "acceptance": "ok"}],
                        "allowed_paths": [".runtime-cache/test_output/worker_markers/consumer.txt"],
                    },
                },
                "depends_on": ["producer"],
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/consumer.txt"],
            },
        ],
    }

    chain_path = tmp_path / "chain_contract_from_success.json"
    chain_path.write_text(json.dumps(chain_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "SUCCESS"
    consumer = next(item for item in report["steps"] if item["name"] == "consumer")
    assert consumer["status"] == "SUCCESS"
    assert consumer["task_id"] == "consumer"


def test_chain_runner_contract_from_resolution_failed(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub_with_contracts(store, include_contracts=False))

    chain_payload = {
        "chain_id": "chain_contract_from_failed",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "producer",
                "kind": "contract",
                "payload": _contract("producer", ".runtime-cache/test_output/worker_markers/producer.txt"),
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/producer.txt"],
            },
            {
                "name": "consumer",
                "kind": "contract",
                "payload": {
                    "contract_from": "producer",
                    "contract_index": 0,
                },
                "depends_on": ["producer"],
                "exclusive_paths": [".runtime-cache/test_output/worker_markers/consumer.txt"],
            },
        ],
    }

    chain_path = tmp_path / "chain_contract_from_failed.json"
    chain_path.write_text(json.dumps(chain_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)
    assert report["status"] == "FAILURE"
    consumer = next(item for item in report["steps"] if item["name"] == "consumer")
    assert consumer["status"] == "FAILURE"
    assert "contract_from resolution failed" in consumer["failure_reason"]


def test_chain_runner_initial_manifest_status_is_upper_running(
    tmp_path: Path, monkeypatch
) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    monkeypatch.setattr(runner._validator, "validate_report", lambda payload, _schema: payload)

    written_statuses: list[str] = []
    original_write_manifest = store.write_manifest

    def _recording_write_manifest(run_id: str, payload: dict) -> None:
        status = payload.get("status")
        if isinstance(status, str):
            written_statuses.append(status)
        original_write_manifest(run_id, payload)

    monkeypatch.setattr(store, "write_manifest", _recording_write_manifest)

    chain = {
        "chain_id": "chain_manifest_status_case",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "pm_to_tl",
                "kind": "handoff",
                "payload": {
                    "task_id": "pm_to_tl_01",
                    "owner_agent": {"role": "PM", "agent_id": "agent-1"},
                    "assigned_agent": {"role": "TECH_LEAD", "agent_id": "agent-1"},
                },
            }
        ],
    }
    chain_path = tmp_path / "chain_manifest_status_case.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "SUCCESS"
    assert written_statuses
    assert written_statuses[0] == "RUNNING"


def test_chain_runner_preserves_ready_batch_boundary_across_groups(
    tmp_path: Path, monkeypatch
) -> None:
    store = RunStore(runs_root=tmp_path)
    runner = ChainRunner(tmp_path, store, _execute_stub(store))
    monkeypatch.setattr(runner._validator, "validate_report", lambda payload, _schema: payload)

    execution_order: list[str] = []

    def _fake_execute_chain_step(*, step_name: str, name_map: dict[str, int], **_kwargs) -> dict:
        execution_order.append(step_name)
        idx = name_map[step_name]
        return {
            "index": idx,
            "name": step_name,
            "kind": "contract",
            "task_id": f"task_{step_name}",
            "run_id": f"run_{step_name}",
            "status": "SUCCESS",
            "failure_reason": "",
            "owner_agent": {"role": "WORKER", "agent_id": "agent-1"},
            "assigned_agent": {"role": "WORKER", "agent_id": "agent-1"},
        }

    monkeypatch.setattr(chain_runner, "_execute_chain_step", _fake_execute_chain_step)

    chain = {
        "chain_id": "chain_group_batch_boundary",
        "owner_agent": {"role": "PM", "agent_id": "pm"},
        "steps": [
            {
                "name": "a",
                "kind": "contract",
                "payload": _contract("task_a"),
                "parallel_group": "aa",
                "exclusive_paths": ["a/"],
            },
            {
                "name": "b",
                "kind": "contract",
                "payload": _contract("task_b"),
                "parallel_group": "zz",
                "exclusive_paths": ["b/"],
            },
            {
                "name": "c",
                "kind": "contract",
                "payload": _contract("task_c"),
                "parallel_group": "mid",
                "depends_on": ["b"],
                "exclusive_paths": ["c/"],
            },
        ],
    }
    chain_path = tmp_path / "chain_batch_boundary.json"
    chain_path.write_text(json.dumps(chain), encoding="utf-8")

    report = runner.run_chain(chain_path, mock_mode=True)

    assert report["status"] == "SUCCESS"
    assert execution_order == ["a", "b", "c"]
