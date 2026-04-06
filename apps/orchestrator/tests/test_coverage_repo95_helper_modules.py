from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortexpilot_orch.runners import agents_events
from cortexpilot_orch.store import run_store_archive_helpers as archive_helpers
from cortexpilot_orch.store import run_store_tool_call_helpers as tool_call_helpers


def test_normalize_tool_call_normalizes_invalid_fields() -> None:
    normalized = tool_call_helpers.normalize_tool_call(
        "run-1",
        {
            "tool": " ",
            "status": "",
            "args": "not-a-dict",
            "config": ["bad-config"],
            "artifacts": ["bad-artifacts"],
            "duration_ms": "10",
            "error": RuntimeError("boom"),
            "thread_id": 123,
            "session_id": 456,
            "task_id": 789,
            "output_sha256": 321,
        },
    )

    assert normalized["run_id"] == "run-1"
    assert normalized["tool"] == "unknown"
    assert normalized["status"] == "unknown"
    assert normalized["args"] == {}
    assert "config" not in normalized
    assert "artifacts" not in normalized
    assert "duration_ms" not in normalized
    assert normalized["error"] == "boom"
    assert normalized["thread_id"] == "123"
    assert normalized["session_id"] == "456"
    assert normalized["task_id"] == "789"
    assert normalized["output_sha256"] == "321"
    assert isinstance(normalized.get("ts"), str)


def test_tool_call_fallback_defaults_tool_name() -> None:
    fallback = tool_call_helpers.tool_call_fallback("run-2", "", "invalid payload")
    assert fallback["run_id"] == "run-2"
    assert fallback["tool"] == "unknown"
    assert fallback["status"] == "error"
    assert fallback["args"] == {}
    assert "schema_validation_failed: invalid payload" in fallback["error"]
    assert isinstance(fallback.get("ts"), str)


def test_agents_events_result_snapshot_covers_error_paths() -> None:
    class ModelDumpError:
        def model_dump(self) -> dict[str, object]:
            raise RuntimeError("model_dump failed")

    class ToDictError:
        def to_dict(self) -> dict[str, object]:
            raise RuntimeError("to_dict failed")

    class SlotsOnly:
        __slots__ = ()

    assert agents_events.result_snapshot(ModelDumpError()) == {}
    assert agents_events.result_snapshot(ToDictError()) == {}
    assert agents_events.result_snapshot(SlotsOnly()) == {}


def test_transcript_recorder_fallback_text_and_empty_flush_behavior() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.transcripts: list[tuple[str, str, str]] = []

        def write_codex_transcript(self, run_id: str, task_id: str, payload: str) -> None:
            self.transcripts.append((run_id, task_id, payload))

    captured_events: list[dict[str, object]] = []

    def _capture_append(store: object, run_id: str, payload: dict[str, object]) -> None:
        del store, run_id
        captured_events.append(dict(payload))

    fake_store = FakeStore()
    recorder = agents_events.TranscriptRecorder(fake_store, "run-3", "task-3")
    recorder.flush()
    assert fake_store.transcripts == []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(agents_events, "append_agents_transcript", _capture_append)
    try:
        recorder.record({"kind": "summary", "meta": {"x": 1}})
        recorder.flush()
    finally:
        monkeypatch.undo()

    assert len(captured_events) == 1
    assert "ts" in captured_events[0]
    assert len(fake_store.transcripts) == 1
    assert fake_store.transcripts[0][0] == "run-3"
    assert fake_store.transcripts[0][1] == "task-3"
    assert "summary:" in fake_store.transcripts[0][2]


def test_update_events_summary_handles_invalid_existing_json(tmp_path: Path) -> None:
    summary_path = tmp_path / "reports" / "events_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{not-json", encoding="utf-8")

    archive_helpers.update_events_summary(
        "run-4",
        {"event": "TASK_DONE", "level": "warn", "ts": "2026-03-09T00:00:00+00:00"},
        summary_path,
    )

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-4"
    assert payload["total_events"] == 1
    assert payload["event_counts"]["TASK_DONE"] == 1
    assert payload["level_counts"]["WARN"] == 1


def test_rebuild_events_summary_skips_blank_invalid_and_non_dict_lines(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            [
                "",
                "{bad-json",
                "[]",
                json.dumps({"event": "STEP_OK", "level": "warn", "ts": "2026-03-09T00:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "reports" / "events_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    archive_helpers.rebuild_events_summary("run-5", events_path, summary_path)
    rebuilt = json.loads(summary_path.read_text(encoding="utf-8"))

    assert rebuilt["run_id"] == "run-5"
    assert rebuilt["total_events"] == 1
    assert rebuilt["event_counts"]["STEP_OK"] == 1
    assert rebuilt["warn_events"] == 1
    assert rebuilt["rebuilt"] is True
    assert rebuilt["first_ts"] == "2026-03-09T00:00:00+00:00"
    assert rebuilt["last_ts"] == "2026-03-09T00:00:00+00:00"


def test_rebuild_events_summary_handles_missing_events_file(tmp_path: Path) -> None:
    events_path = tmp_path / "missing-events.jsonl"
    summary_path = tmp_path / "reports" / "events_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    archive_helpers.rebuild_events_summary("run-6", events_path, summary_path)
    rebuilt = json.loads(summary_path.read_text(encoding="utf-8"))
    assert rebuilt["run_id"] == "run-6"
    assert rebuilt["total_events"] == 0
    assert rebuilt["event_counts"] == {}
    assert rebuilt["level_counts"] == {}


def test_read_hashchain_tail_handles_read_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chain_path = tmp_path / "events.hashchain.jsonl"
    chain_path.write_text("{}", encoding="utf-8")

    def _raise_read_text(*_args: object, **_kwargs: object) -> str:
        raise OSError("disk error")

    monkeypatch.setattr(Path, "read_text", _raise_read_text)
    assert archive_helpers.read_hashchain_tail(chain_path) is None


def test_append_hashchain_entry_resets_invalid_tail_index(tmp_path: Path) -> None:
    chain_path = tmp_path / "events.hashchain.jsonl"
    chain_path.write_text(
        "\n".join(
            [
                "   ",
                "{bad-json",
                json.dumps({"index": "bad-index", "hash": 12345}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    archive_helpers.append_hashchain_entry(chain_path, '{"event":"HELLO"}')
    lines = [line for line in chain_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    entry = json.loads(lines[-1])
    assert entry["index"] == 1
    assert entry["prev_hash"] == "12345"
    assert isinstance(entry["hash"], str) and entry["hash"]

