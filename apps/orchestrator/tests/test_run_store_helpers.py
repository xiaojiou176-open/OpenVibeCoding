import json
import threading
from pathlib import Path

import pytest

from cortexpilot_orch.store import run_store


def test_run_store_helper_functions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(tmp_path))
    run_id = "run_helper"

    run_dir = run_store.create_run_dir(run_id)
    assert run_dir.exists()

    manifest = run_store.write_manifest(run_id, {"run_id": run_id})
    assert manifest.exists()

    contract = run_store.write_contract(run_id, {"task_id": "task-0001"})
    assert contract.exists()

    run_store.append_event(
        run_id,
        {
            "ts": "2024-01-01T00:00:00Z",
            "level": "INFO",
            "event_type": "TEST",
            "run_id": run_id,
            "task_id": "task-0001",
            "attempt": 0,
            "payload": {},
            "event": "TEST",
        },
    )

    diff_path = run_store.write_diff(run_id, "diff --git a/a b/a\n")
    assert diff_path.exists()

    names_path = run_store.write_diff_names(run_id, ["a.txt"])
    assert names_path.exists()

    report_path = run_store.write_report(run_id, "test_report", {"task_id": "task-0001"})
    assert report_path.exists()

    task_contract = run_store.write_task_contract(run_id, "task-0001", {"task_id": "task-0001"})
    assert task_contract.exists()

    task_result = run_store.write_task_result(run_id, "task-0001", {"task_id": "task-0001"})
    assert task_result.exists()

    codex_event = run_store.append_codex_event(run_id, "task-0001", "{\"event\": \"X\"}")
    assert codex_event.exists()

    transcript = run_store.write_codex_transcript(run_id, "task-0001", "hello")
    assert transcript.exists()

    thread_id = run_store.write_codex_thread_id(run_id, "task-0001", "thread")
    assert thread_id.exists()

    session_map = run_store.write_codex_session_map(run_id, {"alias": "agent", "session_id": "s", "thread_id": "t"})
    assert session_map.exists()

    review_report = run_store.write_review_report(
        run_id,
        "task-0001",
        {
            "run_id": run_id,
            "task_id": "task-0001",
            "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
            "reviewed_at": "2024-01-01T00:00:00Z",
            "verdict": "PASS",
            "summary": "ok",
            "scope_check": {"passed": True, "violations": []},
            "evidence": [],
            "produced_diff": False,
        },
    )
    assert review_report.exists()

    ci_report = run_store.write_ci_report(run_id, "task-0001", {"ok": True})
    assert ci_report.exists()

    baseline = run_store.write_git_baseline(run_id, "HEAD")
    assert baseline.exists()

    worktree = run_store.write_worktree_ref(run_id, tmp_path / "worktree")
    assert worktree.exists()

    git_patch = run_store.write_git_patch(run_id, "task-0001", "diff --git a/a b/a\n")
    assert git_patch.exists()

    run_store.write_tests_logs(run_id, "pytest -q", "stdout", "stderr")
    run_store.write_trace_id(run_id, "trace")
    run_store.write_meta(run_id, {"ok": True})

    artifact = run_store.write_artifact(run_id, "note.txt", "hello")
    assert artifact.exists()


def test_write_artifact_blocks_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(tmp_path))
    run_id = "run_safe"
    run_store.create_run_dir(run_id)

    with pytest.raises(ValueError):
        run_store.write_artifact(run_id, "../escape.txt", "nope")

    with pytest.raises(ValueError):
        run_store.write_artifact(run_id, "/tmp/absolute.txt", "nope")


def test_write_task_paths_block_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(tmp_path))
    run_id = "run_task_paths"
    run_store.create_run_dir(run_id)

    with pytest.raises(ValueError):
        run_store.write_task_result(run_id, "../evil", {"task_id": "bad"})

    with pytest.raises(ValueError):
        run_store.write_task_contract(run_id, "a/b", {"task_id": "bad"})

    with pytest.raises(ValueError):
        run_store.write_review_report(
            run_id,
            "..",
            {
                "run_id": run_id,
                "task_id": "bad",
                "reviewer": {"role": "REVIEWER", "agent_id": "reviewer-1"},
                "reviewed_at": "2024-01-01T00:00:00Z",
                "verdict": "PASS",
                "summary": "ok",
                "scope_check": {"passed": True, "violations": []},
                "evidence": [],
                "produced_diff": False,
            },
        )

    with pytest.raises(ValueError):
        run_store.write_ci_report(run_id, "bad/ci", {"ok": True})

    with pytest.raises(ValueError):
        run_store.write_git_patch(run_id, "bad/patch", "diff --git a/a b/a\n")

    with pytest.raises(ValueError):
        run_store.write_report(run_id, "../report", {"ok": True})


def test_append_event_thread_safe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(tmp_path))
    store = run_store.RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_threads")
    per_thread = 25
    workers = 4
    seen: set[str] = set()

    def _worker(worker_id: int) -> None:
        for idx in range(per_thread):
            seq = f"{worker_id}-{idx}"
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "TOOL_USED",
                    "context": {"seq": seq},
                },
            )

    threads = [threading.Thread(target=_worker, args=(wid,)) for wid in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    events_path = tmp_path / run_id / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == per_thread * workers
    for raw in lines:
        payload = json.loads(raw)
        seq = payload.get("context", {}).get("seq")
        assert seq not in seen
        seen.add(seq)
    assert len(seen) == per_thread * workers
