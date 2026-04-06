from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import cortexpilot_orch.queue.store as queue_store_module
from cortexpilot_orch.queue.store import QueueStore


def test_claim_next_is_atomic_for_single_pending_item(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.jsonl"
    store = QueueStore(queue_path=queue_path)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps({"task_id": "task-1"}), encoding="utf-8")
    store.enqueue(contract_path, "task-1", owner="owner-1")

    claims: list[dict[str, object] | None] = [None, None]

    def _worker(index: int) -> None:
        claims[index] = store.claim_next(run_id=f"run-{index}")

    t1 = threading.Thread(target=_worker, args=(0,))
    t2 = threading.Thread(target=_worker, args=(1,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    successful = [item for item in claims if item is not None]
    assert len(successful) == 1
    assert successful[0]["status"] == "CLAIMED"
    assert successful[0]["task_id"] == "task-1"


def test_queue_store_fails_closed_when_fcntl_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    queue_path = tmp_path / "queue.jsonl"
    store = QueueStore(queue_path=queue_path)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps({"task_id": "task-1"}), encoding="utf-8")
    monkeypatch.setattr(queue_store_module, "fcntl", None)

    with pytest.raises(RuntimeError, match="fail-closed file locking"):
        store.enqueue(contract_path, "task-1", owner="owner-1")
