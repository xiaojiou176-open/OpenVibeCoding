from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cortexpilot_orch.api import deps as api_deps
from cortexpilot_orch.api import routes_admin, routes_intake, routes_pm, routes_runs
from cortexpilot_orch.replay import reexec_flow, verify_flow
from cortexpilot_orch.runners import agents_contract_flow, agents_stream_flow
from cortexpilot_orch.scheduler import execute_flow, failure_handling, manifest_lifecycle, runtime_bootstrap


class _DummyStore:
    def __init__(self) -> None:
        self.manifest = {"status": "RUNNING"}
        self.events: list[dict] = []

    def read_manifest(self, _run_id: str) -> dict:
        return dict(self.manifest)

    def write_manifest(self, _run_id: str, payload: dict) -> None:
        self.manifest = dict(payload)

    def append_event(self, _run_id: str, payload: dict) -> None:
        self.events.append(payload)


def test_manifest_lifecycle_helpers() -> None:
    store = _DummyStore()
    loaded = manifest_lifecycle.load_manifest(store, "run_1")
    assert loaded["status"] == "RUNNING"

    manifest_lifecycle.write_manifest(store, "run_1", {"status": "SUCCESS"})
    assert store.manifest["status"] == "SUCCESS"


def test_failure_handling_updates_manifest_and_event() -> None:
    store = _DummyStore()
    failure_handling.mark_failure(store, "run_1", "boom", {"step": "tests"})
    assert store.manifest["status"] == "FAILURE"
    assert store.manifest["failure_reason"] == "boom"
    assert any(item.get("event") == "TASK_FAILED" for item in store.events)


def test_runtime_bootstrap_creates_target_dirs(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("CORTEXPILOT_RUNS_ROOT", str(runtime_root / "runs"))
    monkeypatch.setenv("CORTEXPILOT_WORKTREE_ROOT", str(runtime_root / "worktrees"))
    monkeypatch.setenv("CORTEXPILOT_LOGS_ROOT", str(tmp_path / "logs"))
    monkeypatch.setenv("CORTEXPILOT_CACHE_ROOT", str(tmp_path / "cache"))

    targets = runtime_bootstrap.ensure_runtime_dirs()
    assert targets["runtime_root"].exists()
    assert targets["runs_root"].exists()
    assert targets["worktree_root"].exists()
    assert targets["logs_root"].exists()
    assert targets["cache_root"].exists()


def test_execute_flow_helpers() -> None:
    class _DummyOrch:
        def execute_task(self, contract_path: Path, mock_mode: bool = False) -> str:
            return f"task:{contract_path.name}:{mock_mode}"

        def execute_chain(self, chain_path: Path, mock_mode: bool = False) -> dict:
            return {"chain": chain_path.name, "mock": mock_mode}

    orch = _DummyOrch()
    assert execute_flow.execute_task_flow(orch, Path("a.json"), mock_mode=True).startswith("task:a.json")
    assert execute_flow.execute_chain_flow(orch, Path("chain.json"), mock_mode=False)["chain"] == "chain.json"


def test_replay_flow_wrappers() -> None:
    class _DummyReplayer:
        def verify(self, run_id: str, strict: bool = False) -> dict:
            return {"mode": "verify", "run_id": run_id, "strict": strict}

        def reexecute(self, run_id: str, strict: bool = True) -> dict:
            return {"mode": "reexec", "run_id": run_id, "strict": strict}

    replayer = _DummyReplayer()
    assert verify_flow.verify_run(replayer, "run_x", strict=True)["mode"] == "verify"
    assert reexec_flow.reexecute_run(replayer, "run_x", strict=False)["mode"] == "reexec"


def test_route_admin_ping_and_approve(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "_admin_route_deps_provider", None)
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
        "approve_god_mode_mutation": lambda run_id, payload: routes_admin.approve_god_mode_mutation(
            run_id,
            payload,
        ),
    }

    captured: list[dict] = []

    def _fake_append_event(run_id: str, payload: dict) -> None:
        captured.append({"run_id": run_id, "payload": payload})

    monkeypatch.setattr(routes_admin.run_store, "append_event", _fake_append_event)

    client = TestClient(app)
    assert client.get("/api/god-mode/ping").status_code == 200
    response = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_1"},
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )
    assert response.status_code == 200
    assert captured and captured[0]["run_id"] == "run_1"


def test_route_admin_approve_missing_mutation_handler_returns_structured_503(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "_admin_route_deps_provider", None)
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
    }

    client = TestClient(app)
    response = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_1"},
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin",
        "operation": "approve_god_mode:mutation",
    }


def test_route_admin_approve_rejects_untrusted_role_header_when_api_auth_required(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_API_AUTH_REQUIRED", "1")
    monkeypatch.setattr(api_deps, "_admin_route_deps_provider", None)
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {}

    client = TestClient(app)
    response = client.post(
        "/api/god-mode/approve",
        json={"run_id": "run_1"},
        headers={"x-cortexpilot-role": "TECH_LEAD"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ROLE_HEADER_UNTRUSTED"


def test_route_dep_missing_returns_structured_503(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "_admin_route_deps_provider", None)
    monkeypatch.setattr(api_deps, "_runs_route_deps_provider", None)

    admin_app = FastAPI()
    admin_app.include_router(routes_admin.router)
    admin_client = TestClient(admin_app)
    admin_response = admin_client.get("/api/god-mode/pending", headers={"x-cortexpilot-role": "TECH_LEAD"})
    assert admin_response.status_code == 503
    assert admin_response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin",
        "operation": "depends:get_admin_route_deps",
    }

    runs_app = FastAPI()
    runs_app.include_router(routes_runs.router)
    runs_client = TestClient(runs_app)
    runs_response = runs_client.get("/api/runs")
    assert runs_response.status_code == 503
    assert runs_response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "depends:get_runs_route_deps",
    }


def test_route_pm_missing_deps_returns_structured_503() -> None:
    app = FastAPI()
    app.include_router(routes_pm.router)

    client = TestClient(app)
    response = client.get("/api/pm/sessions")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "pm",
        "operation": "list_pm_sessions",
    }


def test_route_intake_missing_deps_returns_structured_503() -> None:
    app = FastAPI()
    app.include_router(routes_intake.router)

    client = TestClient(app)
    response = client.get("/api/intakes")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "intake",
        "operation": "list_intakes",
    }


def test_route_intake_run_missing_deps_returns_structured_503() -> None:
    app = FastAPI()
    app.include_router(routes_intake.router)

    client = TestClient(app)
    response = client.post("/api/intake/intake-1/run")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "intake",
        "operation": "run_intake",
    }


def test_route_pm_intake_run_missing_deps_returns_structured_503() -> None:
    app = FastAPI()
    app.include_router(routes_intake.router)

    client = TestClient(app)
    response = client.post("/api/pm/intake/intake-1/run")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "intake",
        "operation": "pm_run_intake",
    }


def test_route_runs_list_partial_mapping_returns_structured_503(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "_runs_route_deps_provider", None)
    app = FastAPI()
    app.include_router(routes_runs.router)
    app.state.routes_runs_handlers = {}

    client = TestClient(app)
    response = client.get("/api/runs")
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "list_runs",
    }


def test_route_admin_pending_partial_mapping_returns_structured_503(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "_admin_route_deps_provider", None)
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {}

    client = TestClient(app)
    response = client.get("/api/god-mode/pending", headers={"x-cortexpilot-role": "TECH_LEAD"})
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin",
        "operation": "list_pending_approvals",
    }


def test_route_runs_endpoints(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(routes_runs.router)

    monkeypatch.setattr(api_deps, "_runs_route_deps_provider", None)

    def _fake_replay_run(run_id: str, payload: dict | None = None) -> dict:
        baseline_run_id = payload.get("baseline_run_id") if isinstance(payload, dict) else None
        return {"run_id": run_id, "baseline_run_id": baseline_run_id}

    app.state.routes_runs_handlers = {
        "replay_run": _fake_replay_run,
        "verify_run": lambda run_id, strict=False: {"run_id": run_id, "strict": strict, "mode": "verify"},
        "reexec_run": lambda run_id, strict=True: {"run_id": run_id, "strict": strict, "mode": "reexec"},
    }

    client = TestClient(app)
    headers = {"x-cortexpilot-role": "TECH_LEAD"}
    assert client.get("/api/runs/run_1/_health").status_code == 200
    assert client.post("/api/runs/run_1/replay", json={"baseline_run_id": "run_0"}, headers=headers).status_code == 200
    assert client.post("/api/runs/run_1/verify", params={"strict": "true"}, headers=headers).status_code == 200
    assert client.post("/api/runs/run_1/reexec", params={"strict": "false"}, headers=headers).status_code == 200


def test_agents_flow_wrappers(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    class _FakeRunner:
        def __init__(self, run_store) -> None:
            self.run_store = run_store

        def run_contract(self, contract, worktree_path, schema_path, mock_mode=False):
            calls.append(
                {
                    "contract": contract,
                    "worktree_path": str(worktree_path),
                    "schema_path": str(schema_path),
                    "mock_mode": mock_mode,
                }
            )
            return {"ok": True}

    monkeypatch.setattr(agents_contract_flow, "AgentsRunner", _FakeRunner)
    monkeypatch.setattr(agents_stream_flow, "AgentsRunner", _FakeRunner)

    run_store = object()
    contract = {"task_id": "t1"}
    worktree = tmp_path / "wt"
    schema = tmp_path / "schema.json"

    assert agents_contract_flow.run_agents_contract(contract, worktree, schema, run_store, mock_mode=True)["ok"] is True
    assert agents_stream_flow.run_agents_stream(contract, worktree, schema, run_store)["ok"] is True
    assert len(calls) == 2
