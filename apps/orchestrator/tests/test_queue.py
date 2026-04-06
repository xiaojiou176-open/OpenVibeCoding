import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from cortexpilot_orch.contract.validator import ContractValidator
from cortexpilot_orch.queue import QueueStore


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


def _valid_contract() -> dict:
    return {
        "task_id": "task_queue_01",
        "owner_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "assigned_agent": {"role": "WORKER", "agent_id": "agent-1", "codex_thread_id": ""},
        "inputs": {"spec": "queue test", "artifacts": _output_schema_artifacts("worker")},
        "required_outputs": [{"name": "out.txt", "type": "file", "acceptance": "ok"}],
        "allowed_paths": ["out.txt"],
        "forbidden_actions": ["rm -rf"],
        "acceptance_tests": [{"name": "noop", "cmd": "echo hello", "must_pass": True}],
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
        "log_refs": {"run_id": "", "paths": {}},
    }


def test_queue_enqueue_and_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    contract = _valid_contract()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    validator = ContractValidator()
    validator.validate_contract_file(contract_path)

    store = QueueStore()
    store.enqueue(contract_path, contract["task_id"], owner="agent-1")

    pending = store.next_pending()
    assert pending is not None
    assert pending.get("task_id") == contract["task_id"]

    store.mark_claimed(contract["task_id"], run_id="run-1")
    assert store.next_pending() is None

    store.mark_done(contract["task_id"], run_id="run-1", status="SUCCESS")
    items = store.list_items()
    assert items[-1].get("status") == "SUCCESS"


def test_queue_store_respects_priority_and_schedule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")
    future_ts = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    breached_ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    store.enqueue(contract_path, "task-low", owner="agent-1", metadata={"priority": 1})
    store.enqueue(contract_path, "task-high", owner="agent-1", metadata={"priority": 9})
    store.enqueue(contract_path, "task-future", owner="agent-1", metadata={"priority": 20, "scheduled_at": future_ts})
    store.enqueue(contract_path, "task-breached", owner="agent-1", metadata={"priority": 3, "deadline_at": breached_ts})

    next_item = store.next_pending()
    assert next_item is not None
    assert next_item["task_id"] == "task-high"

    items = {item["task_id"]: item for item in store.list_items()}
    assert items["task-future"]["eligible"] is False
    assert items["task-future"]["sla_state"] == "scheduled"
    assert items["task-breached"]["sla_state"] == "breached"


def test_queue_store_treats_naive_schedule_values_as_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    store.enqueue(
        contract_path,
        "task-naive",
        owner="agent-1",
        metadata={"scheduled_at": "2026-03-30T12:00", "deadline_at": "2026-03-30T13:00"},
    )

    item = store.list_items()[0]
    assert item["eligible"] is True
    assert item["sla_state"] == "on_track"


def test_queue_store_ignores_invalid_lines_and_merges_latest_task_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    queue_path = runtime_root / "queue.jsonl"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        "\n".join(
            [
                "",
                "{",
                json.dumps({"event": "QUEUE_ENQUEUE"}),
                json.dumps({"task_id": "task-1", "status": "PENDING", "priority": 1}),
                json.dumps({"task_id": "task-1", "priority": 9}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    store = QueueStore(queue_path=queue_path)
    items = store.list_items()
    assert len(items) == 1
    assert items[0]["task_id"] == "task-1"
    assert items[0]["priority"] == 9


def test_queue_store_branch_matrix_for_claimed_completed_failed_and_at_risk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")
    at_risk_ts = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()

    store.enqueue(contract_path, "task-claimed", owner="agent-1")
    store.enqueue(contract_path, "task-success", owner="agent-1")
    store.enqueue(contract_path, "task-failure", owner="agent-1")
    store.enqueue(contract_path, "task-at-risk", owner="agent-1", metadata={"deadline_at": at_risk_ts})

    store.mark_claimed("task-claimed", run_id="run-claimed")
    store.mark_done("task-success", run_id="run-success", status="SUCCESS")
    store.mark_done("task-failure", run_id="run-failure", status="FAILURE")

    items = {item["task_id"]: item for item in store.list_items()}
    assert items["task-claimed"]["queue_state"] == "claimed"
    assert items["task-claimed"]["sla_state"] == "in_progress"
    assert items["task-success"]["queue_state"] == "closed"
    assert items["task-success"]["sla_state"] == "completed"
    assert items["task-failure"]["queue_state"] == "closed"
    assert items["task-failure"]["sla_state"] == "ended"
    assert items["task-at-risk"]["sla_state"] == "at_risk"


def test_queue_store_fails_closed_without_fcntl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setattr("cortexpilot_orch.queue.store.fcntl", None)

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    with pytest.raises(RuntimeError):
        store.enqueue(contract_path, "task-lockless", owner="agent-1")


def test_queue_store_without_storage_returns_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    queue_path = runtime_root / "missing" / "queue.jsonl"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore(queue_path=queue_path, ensure_storage=False)

    assert store.next_pending() is None
    assert store.list_items() == []


def test_queue_store_claim_next_reuses_queue_id_and_returns_none_when_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    store.enqueue(contract_path, "task-claim", owner="agent-1", metadata={"queue_id": "queue-claim", "priority": 3})

    claimed = store.claim_next(run_id="run-claim")
    assert claimed is not None
    assert claimed["task_id"] == "task-claim"
    assert claimed["queue_id"] == "queue-claim"
    assert claimed["status"] == "CLAIMED"
    assert store.claim_next(run_id="run-claim-2") is None


def test_queue_store_markers_keep_explicit_queue_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    store.enqueue(contract_path, "task-markers", owner="agent-1")

    claimed = store.mark_claimed("task-markers", run_id="run-markers", queue_id="queue-markers")
    done = store.mark_done("task-markers", run_id="run-markers", status="SUCCESS", queue_id="queue-markers")

    assert claimed["queue_id"] == "queue-markers"
    assert done["queue_id"] == "queue-markers"
    items = {item["task_id"]: item for item in store.list_items()}
    assert items["task-markers"]["queue_id"] == "queue-markers"


def test_queue_store_preview_enqueue_coerces_invalid_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    preview_without_dict = store.preview_enqueue(contract_path, "task-preview-raw", owner="agent-1", metadata="ignored")
    assert preview_without_dict["priority"] == 0
    assert preview_without_dict["eligible"] is True
    assert preview_without_dict["sla_state"] == "on_track"

    preview_with_invalid_values = store.preview_enqueue(
        contract_path,
        "task-preview-invalid",
        owner="agent-1",
        metadata={
            "priority": "not-a-number",
            "scheduled_at": "not-a-date",
            "deadline_at": "still-not-a-date",
        },
    )
    assert preview_with_invalid_values["priority"] == 0
    assert preview_with_invalid_values["eligible"] is True
    assert preview_with_invalid_values["sla_state"] == "on_track"


def test_queue_store_cancel_branch_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    with pytest.raises(ValueError, match="queue_id is required"):
        store.cancel("")

    store.enqueue(contract_path, "task-first", owner="agent-1", metadata={"queue_id": "queue-first"})
    store.enqueue(contract_path, "task-second", owner="agent-1", metadata={"queue_id": "queue-second"})
    store.enqueue(contract_path, "task-claimed", owner="agent-1", metadata={"queue_id": "queue-claimed"})
    store.mark_claimed("task-claimed", run_id="run-claimed", queue_id="queue-claimed")

    cancelled = store.cancel("queue-second")
    assert cancelled["queue_id"] == "queue-second"
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["queue_state"] == "closed"
    assert cancelled["cancelled_at"]
    assert "reason" not in cancelled
    assert "cancelled_by" not in cancelled

    with pytest.raises(KeyError, match="queue item `queue-missing` not found"):
        store.cancel("queue-missing")

    with pytest.raises(ValueError, match="queue item `queue-claimed` is not pending"):
        store.cancel("queue-claimed")


def test_queue_store_preview_and_cancel_surface_preserves_reason_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))

    store = QueueStore()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_valid_contract()), encoding="utf-8")

    preview = store.preview_enqueue(
        contract_path,
        "task-preview",
        owner="agent-1",
        metadata={"priority": 500, "scheduled_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()},
    )
    assert preview["priority"] == 100
    assert preview["queue_state"] == "waiting"
    assert preview["waiting_reason"] == "scheduled_for_future"

    enqueued = store.enqueue(
        contract_path,
        "task-cancel",
        owner="agent-1",
        metadata={"queue_id": "queue-cancel", "priority": -500},
    )
    assert enqueued["priority"] == -100

    cancelled = store.cancel("queue-cancel", reason="operator_request", cancelled_by="pm-1")
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["queue_state"] == "closed"
    assert cancelled["sla_state"] == "ended"
    assert cancelled["cancelled_at"]
    assert cancelled["reason"] == "operator_request"
    assert cancelled["cancelled_by"] == "pm-1"

    items = {item["task_id"]: item for item in store.list_items()}
    assert items["task-cancel"]["cancelled_at"]
    assert items["task-cancel"]["reason"] == "operator_request"
    assert items["task-cancel"]["cancelled_by"] == "pm-1"
