from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from openvibecoding_orch.api import artifact_helpers
from openvibecoding_orch.api import event_cursor
from openvibecoding_orch.api import main_run_views_helpers
from openvibecoding_orch.api import pm_session_aggregation_graph
from openvibecoding_orch.api import run_state_helpers
from openvibecoding_orch.api import security_validators


def _err(code: str) -> dict[str, str]:
    return {"code": code}


def test_artifact_helpers_fail_closed_and_read_formats(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run-artifact"
    artifacts = runs_root / run_id / "artifacts"
    reports = runs_root / run_id / "reports"
    artifacts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    with pytest.raises(HTTPException) as exc_name:
        artifact_helpers.safe_artifact_target(run_id, "   ", runs_root=runs_root, error_detail_fn=_err)
    assert exc_name.value.detail == {"code": "ARTIFACT_NAME_REQUIRED"}

    with pytest.raises(HTTPException) as exc_abs:
        artifact_helpers.safe_artifact_target(run_id, "/tmp/a.json", runs_root=runs_root, error_detail_fn=_err)
    assert exc_abs.value.detail == {"code": "ARTIFACT_PATH_INVALID"}

    with pytest.raises(HTTPException) as exc_escape:
        artifact_helpers.safe_artifact_target(run_id, "../escape", runs_root=runs_root, error_detail_fn=_err)
    assert exc_escape.value.detail == {"code": "ARTIFACT_PATH_ESCAPE"}

    resolved = artifact_helpers.safe_artifact_target(run_id, "nested/out.json", runs_root=runs_root, error_detail_fn=_err)
    assert resolved == (artifacts / "nested/out.json").resolve()

    (artifacts / "ok.json").write_text('{"ok": true}', encoding="utf-8")
    (artifacts / "rows.jsonl").write_text('{"a":1}\n\nnot-json\n{"b":2}\n', encoding="utf-8")
    (artifacts / "note.txt").write_text("hello", encoding="utf-8")
    (artifacts / "bad.txt").write_bytes(b"\xff\xfe")
    (reports / "report.json").write_text('{"score": 1}', encoding="utf-8")
    (reports / "plain.json").write_text("{broken", encoding="utf-8")

    assert artifact_helpers.read_artifact_file(run_id, "ok.json", runs_root=runs_root, error_detail_fn=_err) == {"ok": True}
    assert artifact_helpers.read_artifact_file(run_id, "rows.jsonl", runs_root=runs_root, error_detail_fn=_err) == [
        {"a": 1},
        {"raw": "not-json"},
        {"b": 2},
    ]
    assert artifact_helpers.read_artifact_file(run_id, "note.txt", runs_root=runs_root, error_detail_fn=_err) == "hello"
    assert artifact_helpers.read_artifact_file(run_id, "../escape", runs_root=runs_root, error_detail_fn=_err) is None
    assert artifact_helpers.read_artifact_file(run_id, "missing.txt", runs_root=runs_root, error_detail_fn=_err) is None
    assert artifact_helpers.read_artifact_file(run_id, "bad.txt", runs_root=runs_root, error_detail_fn=_err) is None

    assert artifact_helpers.read_report_file(run_id, "report.json", runs_root=runs_root) == {"score": 1}
    assert artifact_helpers.read_report_file(run_id, "plain.json", runs_root=runs_root) == "{broken"
    assert artifact_helpers.read_report_file(run_id, "missing.json", runs_root=runs_root) is None


def test_event_cursor_parse_filter_and_string_fallback() -> None:
    assert event_cursor.parse_iso_ts("2026-01-01T00:00:00Z").tzinfo is not None
    assert event_cursor.parse_iso_ts("2026-01-01T00:00:00").tzinfo == timezone.utc

    assert event_cursor.event_cursor_value({"ts": "  2026-01-02T00:00:00Z  "}) == "2026-01-02T00:00:00Z"
    assert event_cursor.event_cursor_value({"_ts": "  2026-01-03T00:00:00Z  "}) == "2026-01-03T00:00:00Z"
    assert event_cursor.event_cursor_value({"ts": "  "}) == ""

    assert (
        event_cursor.is_event_after_cursor(
            {"ts": "2026-01-02T00:00:00Z"},
            "2026-01-01T00:00:00Z",
        )
        is True
    )
    assert event_cursor.is_event_after_cursor({"ts": "not-iso-z"}, "not-iso-a") is True

    items = [
        {"ts": "2026-01-01T00:00:00Z", "id": "a"},
        {"_ts": "2026-01-02T00:00:00Z", "id": "b"},
        {"ts": "2026-01-03T00:00:00Z", "id": "c"},
    ]
    assert [it["id"] for it in event_cursor.filter_events(items, since="2026-01-01T12:00:00Z")] == ["b", "c"]
    assert [it["id"] for it in event_cursor.filter_events(items, limit=2)] == ["a", "b"]
    assert [it["id"] for it in event_cursor.filter_events(items, limit=2, tail=True)] == ["b", "c"]
    assert event_cursor.filter_events(items, limit=0) == items


def test_main_run_views_helpers_list_agents_status_skips_missing_manifest(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_ok = runs_root / "run-ok"
    run_skip = runs_root / "run-skip"
    run_ok.mkdir(parents=True, exist_ok=True)
    run_skip.mkdir(parents=True, exist_ok=True)
    (run_ok / "manifest.json").write_text('{"task_id":"t-1"}', encoding="utf-8")

    payload = main_run_views_helpers.list_agents_status(
        run_id=None,
        runs_root=runs_root,
        load_worktrees_fn=lambda: [],
        load_locks_fn=lambda: [],
        load_contract_fn=lambda _run_id: {},
        read_events_fn=lambda _run_id: [],
        derive_stage_fn=lambda _events, _manifest: "PENDING",
    )
    assert payload == {
        "agents": [
            {
                "run_id": "run-ok",
                "task_id": "t-1",
                "agent_id": "",
                "role": "",
                "stage": "PENDING",
                "worktree": "",
                "allowed_paths": [],
                "locked_paths": [],
                "current_files": [],
            }
        ]
    }


@pytest.mark.parametrize(
    ("events", "manifest", "expected"),
    [
        ([], {"status": "FAILURE"}, "FAILED"),
        ([], {"status": "SUCCESS"}, "DONE"),
        ([{"event": "HUMAN_APPROVAL_REQUIRED"}], {"status": "RUNNING"}, "WAITING_APPROVAL"),
        ([{"event": "HUMAN_APPROVAL_REQUIRED"}, {"event": "HUMAN_APPROVAL_COMPLETED"}], {"status": "RUNNING"}, "PENDING"),
        ([{"event": "TEST_RESULT"}], {"status": "RUNNING"}, "TESTING"),
        ([{"event": "REVIEWER_GATE_RESULT"}], {"status": "RUNNING"}, "REVIEW"),
        ([{"event": "DIFF_GATE_FAIL"}], {"status": "RUNNING"}, "DIFF_GATE"),
        ([{"event": "MCP_CALL"}], {"status": "RUNNING"}, "EXECUTING"),
        ([], {"status": "RUNNING"}, "PENDING"),
    ],
)
def test_run_state_helpers_derive_stage_matrix(
    events: list[dict[str, str]],
    manifest: dict[str, str],
    expected: str,
) -> None:
    assert run_state_helpers.derive_stage(events, manifest) == expected


def test_run_state_helpers_last_event_ts_handles_edge_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_root = tmp_path / "runs"

    run_ok = runs_root / "run-ok"
    run_ok.mkdir(parents=True, exist_ok=True)
    (run_ok / "events.jsonl").write_text(
        '{"event":"a","ts":"2026-03-01T00:00:00Z"}\n{"event":"b","_ts":"2026-03-02T00:00:00Z"}\n',
        encoding="utf-8",
    )
    assert run_state_helpers.last_event_ts("run-ok", runs_root=runs_root) == "2026-03-02T00:00:00Z"

    run_bad = runs_root / "run-bad"
    run_bad.mkdir(parents=True, exist_ok=True)
    (run_bad / "events.jsonl").write_text('{"event":"a","ts":"2026-03-01T00:00:00Z"}\nnot-json\n', encoding="utf-8")
    assert run_state_helpers.last_event_ts("run-bad", runs_root=runs_root) == ""
    assert run_state_helpers.last_event_ts("run-missing", runs_root=runs_root) == ""

    run_boom = runs_root / "run-boom"
    run_boom.mkdir(parents=True, exist_ok=True)
    events_path = run_boom / "events.jsonl"
    events_path.write_text('{"event":"x","ts":"2026-03-03T00:00:00Z"}\n', encoding="utf-8")
    original_open = Path.open

    def _open_boom(self: Path, *args: object, **kwargs: object):
        if self == events_path:
            raise OSError("boom")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _open_boom)
    assert run_state_helpers.last_event_ts("run-boom", runs_root=runs_root) == ""


def test_validate_run_id_matrix() -> None:
    with pytest.raises(HTTPException) as exc_non_str:
        security_validators.validate_run_id(123)  # type: ignore[arg-type]
    assert exc_non_str.value.detail == {"code": "RUN_ID_INVALID"}

    with pytest.raises(HTTPException) as exc_empty:
        security_validators.validate_run_id("   ")
    assert exc_empty.value.detail == {"code": "RUN_ID_REQUIRED"}

    with pytest.raises(HTTPException) as exc_bad:
        security_validators.validate_run_id("bad/value", error_code="CUSTOM_INVALID")
    assert exc_bad.value.detail == {"code": "CUSTOM_INVALID"}

    with pytest.raises(HTTPException) as exc_dotdot:
        security_validators.validate_run_id("abc..def")
    assert exc_dotdot.value.detail == {"code": "RUN_ID_INVALID"}

    assert security_validators.validate_run_id("  run-ok_1.2-3  ") == "run-ok_1.2-3"


def test_pm_session_aggregation_graph_window_and_role_extract() -> None:
    one_hour = timedelta(hours=1)
    assert (
        pm_session_aggregation_graph._parse_window(
            " 1H ",
            windows={"1h": one_hour},
            error_detail_fn=_err,
        )
        == one_hour
    )
    with pytest.raises(HTTPException) as exc_window:
        pm_session_aggregation_graph._parse_window("2h", windows={"1h": one_hour}, error_detail_fn=_err)
    assert exc_window.value.detail == {"code": "PM_SESSION_WINDOW_INVALID"}

    assert pm_session_aggregation_graph._extract_graph_roles({"context": {"from_role": " PM ", "to_role": "TL"}}) == ("PM", "TL")
    assert pm_session_aggregation_graph._extract_graph_roles({"context": {"from": "WORKER", "to": "REVIEWER"}}) == (
        "WORKER",
        "REVIEWER",
    )
    assert pm_session_aggregation_graph._extract_graph_roles({"context": {"role": "TL", "next_role": "WORKER"}}) == (
        "TL",
        "WORKER",
    )
    assert pm_session_aggregation_graph._extract_graph_roles({"context": "not-a-dict"}) == ("", "")


def test_build_pm_session_graph_group_and_cutoff_paths() -> None:
    def _collect_events(_context: dict[str, object]) -> list[dict[str, object]]:
        return [
            {"event": "OTHER", "cursor": "3000-01-01T00:00:00Z"},
            {
                "event_type": "CHAIN_HANDOFF",
                "context": {"from_role": "PM", "to_role": "TL"},
                "_run_id": "run-old",
                "cursor": "1970-01-01T00:00:00Z",
            },
            {
                "event": "CHAIN_HANDOFF",
                "context": {"from_role": "PM", "to_role": "TL"},
                "_run_id": "run-a",
                "cursor": "3000-01-01T00:00:00Z",
            },
            {
                "event": "CHAIN_HANDOFF",
                "context": {"from": "PM", "to": "TL"},
                "_run_id": "run-b",
                "cursor": "3000-01-02T00:00:00Z",
            },
            {
                "event": "CHAIN_HANDOFF",
                "context": {"from_role": "PM", "to_role": "TL"},
                "_run_id": "run-c",
                "cursor": "bad-ts",
            },
            {"event": "CHAIN_HANDOFF", "context": {}, "_run_id": "run-empty", "cursor": "3000-01-01T00:00:00Z"},
            {
                "event": "CHAIN_HANDOFF",
                "context": {"role": "TL", "next_role": "WORKER"},
                "run_id": "run-d",
                "cursor": "",
            },
        ]

    def _parse_ts_or_none(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    base_context = {"pm_session_id": "pm-1"}
    graph = pm_session_aggregation_graph.build_pm_session_graph(
        base_context,
        "24h",
        windows={"24h": timedelta(hours=24)},
        collect_events_fn=_collect_events,
        event_cursor_fn=lambda event: str(event.get("cursor") or ""),
        parse_ts_or_none_fn=_parse_ts_or_none,
        error_detail_fn=_err,
    )
    assert graph["nodes"] == ["PM", "TL", "WORKER"]
    assert graph["stats"] == {"node_count": 3, "edge_count": 4}
    assert {edge["run_id"] for edge in graph["edges"]} == {"run-a", "run-b", "run-c", "run-d"}

    grouped = pm_session_aggregation_graph.build_pm_session_graph(
        base_context,
        "24h",
        windows={"24h": timedelta(hours=24)},
        collect_events_fn=_collect_events,
        event_cursor_fn=lambda event: str(event.get("cursor") or ""),
        parse_ts_or_none_fn=_parse_ts_or_none,
        error_detail_fn=_err,
        group_by_role=True,
    )
    grouped_edges = {(edge["from_role"], edge["to_role"]): edge for edge in grouped["edges"]}
    assert grouped["stats"] == {"node_count": 3, "edge_count": 2}
    assert grouped_edges[("PM", "TL")]["count"] == 3
    assert grouped_edges[("PM", "TL")]["run_id"] == "*"
    assert grouped_edges[("PM", "TL")]["ts"] == "3000-01-02T00:00:00Z"
    assert grouped_edges[("TL", "WORKER")]["count"] == 1
