import json
from pathlib import Path

import pytest

from cortexpilot_orch.store.run_store import RunStore


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_event_schema_enforced(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_event")

    with pytest.raises(ValueError):
        store.append_event(run_id, {"event": "NO_LEVEL", "run_id": run_id, "context": {}})


def test_schema_drift_detection(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_drift")

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "UNKNOWN_NEW_EVENT",
            "run_id": run_id,
            "context": {},
        },
    )

    events_path = tmp_path / run_id / "events.jsonl"
    events = _read_events(events_path)
    event_types = [item.get("event_type") for item in events]
    assert "UNKNOWN_NEW_EVENT" in event_types
    assert "SCHEMA_DRIFT_DETECTED" in event_types


def test_known_event_does_not_trigger_drift(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_tamper")

    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "TAMPERMONKEY_FAILURE",
            "run_id": run_id,
            "context": {"error": "boom"},
        },
    )

    events_path = tmp_path / run_id / "events.jsonl"
    events = _read_events(events_path)
    event_types = [item.get("event_type") for item in events]
    assert "TAMPERMONKEY_FAILURE" in event_types
    assert "SCHEMA_DRIFT_DETECTED" not in event_types


def test_search_purified_event_known(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_search")

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "SEARCH_PURIFIED",
            "run_id": run_id,
            "context": {},
        },
    )

    events_path = tmp_path / run_id / "events.jsonl"
    events = _read_events(events_path)
    event_types = [item.get("event_type") for item in events]
    assert "SEARCH_PURIFIED" in event_types
    assert "SCHEMA_DRIFT_DETECTED" not in event_types


@pytest.mark.parametrize(
    "event_name",
    [
        "CHAIN_HANDOFF_STEP_MARKED",
        "CHAIN_LIFECYCLE_EVALUATED",
        "AGENT_SESSION_THREAD_ID_UNSUPPORTED",
        "MCP_BASE_HOME_FALLBACK",
        "DEPENDENCY_PATCH_SKIPPED",
    ],
)
def test_new_known_events_do_not_trigger_drift(tmp_path: Path, event_name: str) -> None:
    store = RunStore(runs_root=tmp_path)
    run_id = store.create_run("task_known_event")

    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": event_name,
            "run_id": run_id,
            "context": {},
        },
    )

    events_path = tmp_path / run_id / "events.jsonl"
    events = _read_events(events_path)
    event_types = [item.get("event_type") for item in events]
    assert event_name in event_types
    assert "SCHEMA_DRIFT_DETECTED" not in event_types
