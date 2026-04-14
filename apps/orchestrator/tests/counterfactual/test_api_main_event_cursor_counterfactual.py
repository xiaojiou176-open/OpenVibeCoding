from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from openvibecoding_orch.api import event_cursor
from openvibecoding_orch.api import main as api_main


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_events(run_dir: Path, lines: list[str]) -> None:
    (run_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_main_event_cursor_wrappers_delegate_to_event_cursor_module(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_dt = datetime(2024, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(event_cursor, "parse_iso_ts", lambda value: expected_dt)
    monkeypatch.setattr(event_cursor, "event_cursor_value", lambda event: "cursor-from-module")
    monkeypatch.setattr(event_cursor, "is_event_after_cursor", lambda event, since: True)
    monkeypatch.setattr(event_cursor, "filter_events", lambda events, since=None, limit=None, tail=False: [{"event": "delegated"}])

    assert api_main._parse_iso_ts("2024-01-01T00:00:00Z") is expected_dt
    assert api_main._event_cursor_value({"ts": "ignored"}) == "cursor-from-module"
    assert api_main._is_event_after_cursor({"ts": "ignored"}, "2024-01-01T00:00:00Z") is True
    assert api_main._filter_events([{"event": "x"}], since="2024-01-01T00:00:00Z") == [{"event": "delegated"}]


def test_run_events_endpoint_fails_loud_when_event_filter_module_breaks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("OPENVIBECODING_RUNS_ROOT", str(runs_root))

    run_id = "run_counterfactual"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_events(
        run_dir,
        [
            json.dumps({"event": "STEP_1", "ts": "2024-01-01T00:00:00Z"}),
            json.dumps({"event": "STEP_2", "ts": "2024-01-01T00:00:01Z"}),
        ],
    )

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-event-filter-broken")

    monkeypatch.setattr(event_cursor, "filter_events", _boom)

    client = TestClient(api_main.app)
    response = client.get(f"/api/runs/{run_id}/events")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
