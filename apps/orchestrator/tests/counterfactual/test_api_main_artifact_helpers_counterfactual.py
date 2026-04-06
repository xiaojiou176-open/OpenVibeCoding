from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cortexpilot_orch.api import artifact_helpers
from cortexpilot_orch.api import main as api_main


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_main_artifact_wrappers_delegate_to_helper_module(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_path = Path("/tmp/delegated-artifact-path")
    expected_payload = {"delegated": True}
    expected_report = {"report": "delegated"}

    monkeypatch.setattr(artifact_helpers, "safe_artifact_target", lambda *args, **kwargs: expected_path)
    monkeypatch.setattr(artifact_helpers, "read_artifact_file", lambda *args, **kwargs: expected_payload)
    monkeypatch.setattr(artifact_helpers, "read_report_file", lambda *args, **kwargs: expected_report)

    assert api_main._safe_artifact_target("run-x", "a.json") == expected_path
    assert api_main._read_artifact_file("run-x", "a.json") == expected_payload
    assert api_main._read_report_file("run-x", "report.json") == expected_report


def test_run_search_endpoint_fails_loud_when_artifact_helper_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_id = "run_artifact_counterfactual"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-artifact-helper-broken")

    monkeypatch.setattr(artifact_helpers, "read_artifact_file", _boom)

    client = TestClient(api_main.app)
    response = client.get(f"/api/runs/{run_id}/search")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
