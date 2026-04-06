from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.api import run_state_helpers


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_main_run_state_wrappers_delegate_to_helper_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_state_helpers, "derive_stage", lambda events, manifest: "DELEGATED_STAGE")
    monkeypatch.setattr(run_state_helpers, "last_event_ts", lambda run_id, runs_root: "DELEGATED_TS")

    assert api_main._derive_stage([{"event": "STEP_STARTED"}], {"status": "RUNNING"}) == "DELEGATED_STAGE"
    assert api_main._last_event_ts("run-delegated") == "DELEGATED_TS"


def test_runs_endpoint_fails_loud_when_last_event_ts_helper_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_dir = runs_root / "run_last_event_fail"
    _write_manifest(run_dir, {"run_id": "run_last_event_fail", "task_id": "task", "status": "RUNNING"})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-last-event-ts-helper-broken")

    monkeypatch.setattr(run_state_helpers, "last_event_ts", _boom)

    client = TestClient(api_main.app)
    response = client.get("/api/runs")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"


def test_agents_status_endpoint_fails_loud_when_derive_stage_helper_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_dir = runs_root / "run_stage_fail"
    _write_manifest(run_dir, {"run_id": "run_stage_fail", "task_id": "task", "status": "RUNNING"})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-derive-stage-helper-broken")

    monkeypatch.setattr(run_state_helpers, "derive_stage", _boom)

    client = TestClient(api_main.app)
    response = client.get("/api/agents/status")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
