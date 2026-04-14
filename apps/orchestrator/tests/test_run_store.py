import hashlib
import hmac
import json
import os
import threading
from pathlib import Path

import pytest

from openvibecoding_orch.store import run_store
from openvibecoding_orch.store.run_store import RunStore
from openvibecoding_orch.store.run_store_primitives import write_atomic


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_run_store_creation(tmp_path: Path):
    os.environ["OPENVIBECODING_RUNS_ROOT"] = str(tmp_path)
    store = RunStore()
    run_id = store.create_run("task_1")
    run_dir = tmp_path / run_id
    assert run_dir.exists()
    assert (run_dir / "artifacts").exists()
    assert (run_dir / "reports").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "events.hashchain.jsonl").exists()
    assert _read_lines(run_dir / "events.jsonl") == []


def test_run_store_append_events(tmp_path: Path):
    os.environ["OPENVIBECODING_RUNS_ROOT"] = str(tmp_path)
    store = RunStore()
    run_id = store.create_run("task_2")
    store.append_event(
        run_id,
        {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {"n": 1}},
    )
    store.append_event(
        run_id,
        {"level": "INFO", "event": "TEST_RESULT", "run_id": run_id, "context": {"n": 2}},
    )
    store.append_event(
        run_id,
        {"level": "INFO", "event": "REVIEW_RESULT", "run_id": run_id, "context": {"n": 3}},
    )
    events_path = tmp_path / run_id / "events.jsonl"
    hashchain_path = tmp_path / run_id / "events.hashchain.jsonl"
    lines = _read_lines(events_path)
    assert len(lines) == 3
    for line in lines:
        payload = json.loads(line)
        assert "ts" in payload
    chain_lines = _read_lines(hashchain_path)
    assert len(chain_lines) == len(lines)
    prev_hash = ""
    for index, (event_line, chain_line) in enumerate(zip(lines, chain_lines), start=1):
        entry = json.loads(chain_line)
        event_sha256 = _sha256_text(event_line)
        chain_material = f"{index}:{prev_hash}:{event_sha256}".encode("utf-8")
        expected_hash = _sha256_bytes(chain_material)
        assert entry["index"] == index
        assert entry["event_sha256"] == event_sha256
        assert entry["prev_hash"] == prev_hash
        assert entry["hash"] == expected_hash
        prev_hash = entry["hash"]


def test_run_store_append_only(tmp_path: Path):
    os.environ["OPENVIBECODING_RUNS_ROOT"] = str(tmp_path)
    store = RunStore()
    run_id = store.create_run("task_3")
    store.append_event(
        run_id,
        {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {}},
    )
    store = RunStore()
    store.append_event(
        run_id,
        {"level": "INFO", "event": "TASK_RESULT_RECORDED", "run_id": run_id, "context": {}},
    )
    events_path = tmp_path / run_id / "events.jsonl"
    lines = _read_lines(events_path)
    assert [json.loads(line)["event"] for line in lines] == [
        "STEP_STARTED",
        "TASK_RESULT_RECORDED",
    ]


def test_run_store_contract_signature(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    store = RunStore()
    run_id = store.create_run("task_sig")
    contract_path = store.write_contract(run_id, {"task_id": "task_sig"})

    monkeypatch.delenv("OPENVIBECODING_CONTRACT_HMAC_KEY", raising=False)
    assert store.write_contract_signature(run_id, contract_path) is None

    monkeypatch.setenv("OPENVIBECODING_CONTRACT_HMAC_KEY", "secret")
    sig_path = store.write_contract_signature(run_id, contract_path)
    assert sig_path is not None
    assert sig_path.exists()
    expected = hmac.new(b"secret", contract_path.read_bytes(), hashlib.sha256).hexdigest()
    assert sig_path.read_text(encoding="utf-8").strip() == expected


def test_append_event_rolls_back_when_hashchain_append_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    store = RunStore()
    run_id = store.create_run("task_hashchain_fail")
    events_path = tmp_path / run_id / "events.jsonl"

    def _raise_hashchain(*_args, **_kwargs):
        raise RuntimeError("hashchain broken")

    monkeypatch.setattr(store, "_append_hashchain_entry", _raise_hashchain)

    with pytest.raises(RuntimeError, match="hashchain broken"):
        store.append_event(
            run_id,
            {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {"n": 1}},
        )

    assert _read_lines(events_path) == []


def test_append_event_keeps_primary_evidence_when_summary_update_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    store = RunStore()
    run_id = store.create_run("task_summary_fail")
    events_path = tmp_path / run_id / "events.jsonl"
    hashchain_path = tmp_path / run_id / "events.hashchain.jsonl"

    def _raise_summary(*_args, **_kwargs):
        raise RuntimeError("summary write failed")

    monkeypatch.setattr(store, "_update_events_summary", _raise_summary)

    store.append_event(
        run_id,
        {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {"n": 1}},
    )

    assert len(_read_lines(events_path)) == 1
    assert len(_read_lines(hashchain_path)) == 1
    marker_path = tmp_path / run_id / "reports" / "events_summary.rebuild_required.json"
    assert marker_path.exists()
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["run_id"] == run_id
    assert marker["event_type"] == "STEP_STARTED"


def test_rebuild_events_summary_clears_rebuild_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    store = RunStore()
    run_id = store.create_run("task_summary_rebuild")
    marker_path = tmp_path / run_id / "reports" / "events_summary.rebuild_required.json"
    summary_path = tmp_path / run_id / "reports" / "events_summary.json"

    def _raise_summary(*_args, **_kwargs):
        raise RuntimeError("summary write failed")

    monkeypatch.setattr(store, "_update_events_summary", _raise_summary)
    store.append_event(
        run_id,
        {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {"n": 1}},
    )
    assert marker_path.exists()

    rebuilt_path = store.rebuild_events_summary(run_id)
    assert rebuilt_path == summary_path
    assert summary_path.exists()
    assert not marker_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == run_id
    assert payload["total_events"] == 1
    assert payload["event_counts"]["STEP_STARTED"] == 1


def test_module_helper_rebuild_events_summary_for_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    run_id = run_store.create_run_dir("task_summary_helper").name
    run_store.append_event(run_id, {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {}})
    rebuilt_path = run_store.rebuild_events_summary_for_run(run_id)
    assert rebuilt_path.exists()


def test_append_event_hashchain_failure_does_not_truncate_concurrent_append_from_other_store(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    failing_store = RunStore(runs_root=tmp_path)
    peer_store = RunStore(runs_root=tmp_path)
    run_id = failing_store.create_run("task_hashchain_concurrency")
    entered_hashchain = threading.Event()
    allow_failure = threading.Event()
    thread_error: list[Exception] = []

    def _blocked_hashchain(*_args, **_kwargs):
        entered_hashchain.set()
        if not allow_failure.wait(timeout=2):
            raise RuntimeError("timeout waiting failure gate")
        raise RuntimeError("hashchain broken")

    monkeypatch.setattr(failing_store, "_append_hashchain_entry", _blocked_hashchain)

    def _failing_worker() -> None:
        try:
            failing_store.append_event(
                run_id,
                {"level": "INFO", "event": "STEP_STARTED", "run_id": run_id, "context": {"source": "failing"}},
            )
        except Exception as exc:  # noqa: BLE001
            thread_error.append(exc)

    worker = threading.Thread(target=_failing_worker)
    worker.start()
    assert entered_hashchain.wait(timeout=2)

    peer_error: list[Exception] = []

    def _peer_worker() -> None:
        try:
            peer_store.append_event(
                run_id,
                {"level": "INFO", "event": "STEP_COMPLETED", "run_id": run_id, "context": {"source": "peer"}},
            )
        except Exception as exc:  # noqa: BLE001
            peer_error.append(exc)

    peer_thread = threading.Thread(target=_peer_worker)
    peer_thread.start()
    allow_failure.set()
    worker.join(timeout=2)
    peer_thread.join(timeout=2)

    assert thread_error
    assert not peer_error
    events_path = tmp_path / run_id / "events.jsonl"
    payloads = [json.loads(line) for line in _read_lines(events_path)]
    events = [item.get("event") for item in payloads]
    assert "STEP_COMPLETED" in events
    assert "STEP_STARTED" not in events


def test_write_codex_session_map_preserves_task_entries_across_concurrent_writers(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(tmp_path))
    first_store = RunStore(runs_root=tmp_path)
    second_store = RunStore(runs_root=tmp_path)
    run_id = first_store.create_run("task_session_map_race")

    def _writer(store: RunStore, task_id: str, thread_id: str) -> None:
        store.write_codex_session_map(
            run_id,
            {
                "run_id": run_id,
                "task_id": task_id,
                "codex_thread_id": thread_id,
            },
        )

    thread_a = threading.Thread(target=_writer, args=(first_store, "task-A", "thread-A"))
    thread_b = threading.Thread(target=_writer, args=(second_store, "task-B", "thread-B"))
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=2)
    thread_b.join(timeout=2)

    session_map_path = tmp_path / run_id / "codex" / "session_map.json"
    payload = json.loads(session_map_path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    assert isinstance(tasks, dict)
    assert tasks["task-A"]["codex_thread_id"] == "thread-A"
    assert tasks["task-B"]["codex_thread_id"] == "thread-B"


def test_write_atomic_fsyncs_parent_directory(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "nested" / "payload.json"
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def _tracked_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr("openvibecoding_orch.store.run_store_primitives.os.fsync", _tracked_fsync)
    write_atomic(target, b'{"ok":true}')
    assert target.read_text(encoding="utf-8") == '{"ok":true}'
    assert len(fsync_calls) >= 2
