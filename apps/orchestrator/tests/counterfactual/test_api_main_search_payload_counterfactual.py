from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.api import search_payload_helpers


def _write_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_contract(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "contract.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_artifact(run_dir: Path, name: str, payload: object) -> None:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def test_main_search_payload_wrappers_delegate_to_helper_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_queries = ["delegated-query"]
    expected_payload = {"run_id": "run-delegated", "raw": {"delegated": True}}

    monkeypatch.setattr(search_payload_helpers, "extract_search_queries", lambda contract: expected_queries)
    monkeypatch.setattr(search_payload_helpers, "build_search_payload", lambda *args, **kwargs: expected_payload)

    assert api_main._extract_search_queries({"inputs": {"artifacts": []}}) == expected_queries

    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))
    run_id = "run-delegated"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    assert api_main.get_search(run_id) == expected_payload


def test_run_search_endpoint_fails_loud_when_search_payload_builder_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_id = "run-search-builder-counterfactual"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-search-payload-builder-broken")

    monkeypatch.setattr(search_payload_helpers, "build_search_payload", _boom)

    client = TestClient(api_main.app)
    response = client.get(f"/api/runs/{run_id}/search")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"


def test_promote_evidence_fails_loud_when_search_query_extractor_breaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runs_root))

    run_id = "run-search-query-counterfactual"
    run_dir = runs_root / run_id
    _write_manifest(run_dir, {"run_id": run_id, "task_id": "task", "status": "RUNNING"})
    _write_contract(
        run_dir,
        {
            "assigned_agent": {"role": "SEARCHER", "agent_id": "agent-1"},
            "inputs": {"artifacts": []},
        },
    )
    _write_artifact(run_dir, "search_results.json", {"results": [{"title": "x"}]})

    def _boom(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("counterfactual-search-query-extractor-broken")

    monkeypatch.setattr(search_payload_helpers, "extract_search_queries", _boom)

    client = TestClient(api_main.app)
    response = client.post(
        f"/api/runs/{run_id}/evidence/promote",
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"
