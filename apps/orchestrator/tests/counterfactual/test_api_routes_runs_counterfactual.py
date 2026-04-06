from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from cortexpilot_orch.api import deps as api_deps
from cortexpilot_orch.api import main as api_main
from cortexpilot_orch.api import routes_runs


def test_main_binds_routes_runs_handlers() -> None:
    handlers = getattr(api_main.app.state, "routes_runs_handlers", {})
    required = {
        "list_runs",
        "get_run",
        "get_events",
        "stream_events",
        "promote_evidence",
        "replay_run",
        "verify_run",
        "reexec_run",
        "reject_run",
        "list_agents_status",
    }
    missing = [key for key in sorted(required) if not callable(handlers.get(key))]
    assert missing == []


def test_routes_runs_fail_fast_when_unbound() -> None:
    app = FastAPI()
    app.include_router(routes_runs.router)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/runs",
        "headers": [],
        "query_string": b"",
        "app": app,
    }
    request = Request(scope)

    api_deps.configure_runs_route_deps_provider(None)
    try:
        with pytest.raises(HTTPException) as excinfo:
            api_deps.get_runs_route_deps(request)
    finally:
        api_deps.configure_runs_route_deps_provider(lambda: api_main._runs_route_deps)

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "ROUTE_DEPS_NOT_CONFIGURED"
    assert excinfo.value.detail["group"] == "runs"
    assert excinfo.value.detail["operation"] == "depends:get_runs_route_deps"


def test_main_replay_route_keeps_baseline_window_resolution(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _DummyOrchestrationService:
        def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, object]:
            captured["run_id"] = run_id
            captured["baseline_run_id"] = baseline_run_id
            return {
                "ok": True,
                "run_id": run_id,
                "baseline_run_id": baseline_run_id,
            }

    monkeypatch.setattr(api_main, "_orchestration_service", _DummyOrchestrationService())
    monkeypatch.setattr(api_main, "_select_baseline_by_window", lambda run_id, window: f"baseline-{run_id}")

    client = TestClient(api_main.app)
    response = client.post(
        "/api/runs/run_current/replay",
        json={"baseline_window": {"kind": "latest_success", "hours": 24}},
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_run_id"] == "baseline-run_current"
    assert captured == {"run_id": "run_current", "baseline_run_id": "baseline-run_current"}


def test_routes_runs_replay_fail_closed_on_partial_mapping() -> None:
    app = FastAPI()
    app.state.routes_runs_handlers = {"list_runs": lambda: []}
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/runs/run-counterfactual/replay",
            "headers": [],
            "app": app,
        }
    )

    previous_provider = getattr(api_deps, "_runs_route_deps_provider", None)
    api_deps.configure_runs_route_deps_provider(None)
    try:
        with pytest.raises(HTTPException) as excinfo:
            routes_runs.replay_run("run-counterfactual", payload={"baseline_run_id": "base-1"}, request=request)
    finally:
        api_deps.configure_runs_route_deps_provider(previous_provider)

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "replay_run",
    }
