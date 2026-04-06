import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from cortexpilot_orch.api import deps as api_deps
from cortexpilot_orch.api import routes_runs


@pytest.fixture(autouse=True)
def _reset_runs_provider() -> None:
    previous_provider = getattr(api_deps, "_runs_route_deps_provider", None)
    api_deps.configure_runs_route_deps_provider(None)
    yield
    api_deps.configure_runs_route_deps_provider(previous_provider)


class _DummyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, object]:
        self.calls.append(("replay_run", run_id, baseline_run_id))
        return {"ok": True, "run_id": run_id, "baseline_run_id": baseline_run_id}

    def replay_verify(self, run_id: str, strict: bool = True) -> dict[str, object]:
        self.calls.append(("replay_verify", run_id, strict))
        return {"ok": True, "run_id": run_id, "strict": strict}

    def replay_reexec(self, run_id: str, strict: bool = True) -> dict[str, object]:
        self.calls.append(("replay_reexec", run_id, strict))
        return {"ok": True, "run_id": run_id, "strict": strict}


class _FailingService:
    def __init__(self, exc: Exception) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.exc = exc

    def replay_run(self, run_id: str, baseline_run_id: str | None = None) -> dict[str, object]:
        self.calls.append(("replay_run", run_id, baseline_run_id))
        raise self.exc

    def replay_verify(self, run_id: str, strict: bool = True) -> dict[str, object]:
        self.calls.append(("replay_verify", run_id, strict))
        raise self.exc

    def replay_reexec(self, run_id: str, strict: bool = True) -> dict[str, object]:
        self.calls.append(("replay_reexec", run_id, strict))
        raise self.exc


def test_replay_run_payload_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    first = routes_runs.replay_run("run-1", payload=None)
    assert first["baseline_run_id"] is None
    assert service.calls[0] == ("replay_run", "run-1", None)

    second = routes_runs.replay_run("run-2", payload={"baseline_run_id": "base-1"})
    assert second["baseline_run_id"] == "base-1"
    assert service.calls[1] == ("replay_run", "run-2", "base-1")


@pytest.mark.parametrize("run_id", ["", "   ", "\n\t"])
def test_run_health_probe_rejects_blank_run_id(run_id: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        routes_runs.run_health_probe(run_id)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == {"code": "RUN_ID_REQUIRED"}


def test_run_health_probe_allows_non_blank() -> None:
    assert routes_runs.run_health_probe(" run-123 ") == {"ok": True, "run_id": "run-123"}


def test_replay_run_payload_missing_baseline_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    result = routes_runs.replay_run("run-3", payload={"other": "value"})
    assert result["baseline_run_id"] is None
    assert service.calls[0] == ("replay_run", "run-3", None)


def test_replay_run_rejects_non_dict_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    with pytest.raises(HTTPException) as excinfo:
        routes_runs.replay_run("run-3", payload=["bad-payload"])  # type: ignore[arg-type]

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == {"code": "PAYLOAD_INVALID"}
    assert service.calls == []


def test_verify_and_reexec_forward_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    verify = routes_runs.verify_run("run-v")
    reexec = routes_runs.reexec_run("run-r")

    assert verify["strict"] is True
    assert reexec["strict"] is True
    assert service.calls[0] == ("replay_verify", "run-v", True)
    assert service.calls[1] == ("replay_reexec", "run-r", True)


def test_verify_and_reexec_override_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    verify = routes_runs.verify_run("run-v", strict=True)
    reexec = routes_runs.reexec_run("run-r", strict=False)

    assert verify["strict"] is True
    assert reexec["strict"] is False
    assert service.calls[0] == ("replay_verify", "run-v", True)
    assert service.calls[1] == ("replay_reexec", "run-r", False)


def test_replay_run_propagates_service_http_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = HTTPException(status_code=409, detail={"code": "RUN_CONFLICT"})
    service = _FailingService(exc)
    monkeypatch.setattr(routes_runs, "_service", service)

    with pytest.raises(HTTPException) as excinfo:
        routes_runs.replay_run("run-err", payload={"baseline_run_id": "base-err"})

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail == {"code": "RUN_CONFLICT"}
    assert service.calls == [("replay_run", "run-err", "base-err")]


def test_verify_run_propagates_service_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = RuntimeError("verify boom")
    service = _FailingService(exc)
    monkeypatch.setattr(routes_runs, "_service", service)

    with pytest.raises(HTTPException) as excinfo:
        routes_runs.verify_run("run-bad")

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == {"code": "VERIFY_RUN_FAILED"}
    assert service.calls == [("replay_verify", "run-bad", True)]


def test_reexec_run_propagates_service_http_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = HTTPException(status_code=500, detail={"code": "REEXEC_FAILED"})
    service = _FailingService(exc)
    monkeypatch.setattr(routes_runs, "_service", service)

    with pytest.raises(HTTPException) as excinfo:
        routes_runs.reexec_run("run-bad", strict=False)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == {"code": "REEXEC_FAILED"}
    assert service.calls == [("replay_reexec", "run-bad", False)]


def test_reexec_run_masks_service_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    exc = RuntimeError("reexec boom")
    service = _FailingService(exc)
    monkeypatch.setattr(routes_runs, "_service", service)

    with pytest.raises(HTTPException) as excinfo:
        routes_runs.reexec_run("run-bad", strict=False)

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == {"code": "REEXEC_RUN_FAILED"}
    assert service.calls == [("replay_reexec", "run-bad", False)]


def test_replay_verify_reexec_use_provider_when_request_absent() -> None:
    class _ProviderDeps:
        def replay_run(self, run_id: str, payload: dict | None = None) -> dict[str, object]:
            return {"source": "provider", "op": "replay", "run_id": run_id, "payload": payload}

        def verify_run(self, run_id: str, strict: bool = True) -> dict[str, object]:
            return {"source": "provider", "op": "verify", "run_id": run_id, "strict": strict}

        def reexec_run(self, run_id: str, strict: bool = True) -> dict[str, object]:
            return {"source": "provider", "op": "reexec", "run_id": run_id, "strict": strict}

    provider = _ProviderDeps()
    api_deps.configure_runs_route_deps_provider(lambda: provider)
    try:
        replay = routes_runs.replay_run("run-provider", payload={"baseline_run_id": "b"})
        verify = routes_runs.verify_run("run-provider", strict=False)
        reexec = routes_runs.reexec_run("run-provider", strict=True)
    finally:
        api_deps.configure_runs_route_deps_provider(None)

    assert replay == {
        "source": "provider",
        "op": "replay",
        "run_id": "run-provider",
        "payload": {"baseline_run_id": "b"},
    }
    assert verify == {"source": "provider", "op": "verify", "run_id": "run-provider", "strict": False}
    assert reexec == {"source": "provider", "op": "reexec", "run_id": "run-provider", "strict": True}


def test_resolve_runs_route_deps_prefers_provider_over_partial_state_mapping() -> None:
    class _ProviderDeps:
        def list_runs(self) -> list[dict[str, str]]:
            return [{"source": "provider"}]

    provider = _ProviderDeps()
    api_deps.configure_runs_route_deps_provider(lambda: provider)
    app = FastAPI()
    app.state.routes_runs_handlers = {"list_runs": None}
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/runs",
            "headers": [],
            "app": app,
        }
    )
    try:
        resolved = api_deps.resolve_runs_route_deps(request)
    finally:
        api_deps.configure_runs_route_deps_provider(None)

    assert resolved is provider
    assert resolved.list_runs() == [{"source": "provider"}]


def test_replay_verify_reexec_fail_closed_on_unconfigured_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)

    app = FastAPI()
    app.state.routes_runs_handlers = {"list_runs": lambda: []}
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/runs/run-partial/replay",
            "headers": [],
            "app": app,
        }
    )

    with pytest.raises(HTTPException) as replay_exc:
        routes_runs.replay_run("run-partial", payload={"baseline_run_id": "base-1"}, request=request)
    with pytest.raises(HTTPException) as verify_exc:
        routes_runs.verify_run("run-partial", strict=False, request=request)
    with pytest.raises(HTTPException) as reexec_exc:
        routes_runs.reexec_run("run-partial", strict=True, request=request)

    assert replay_exc.value.status_code == 503
    assert replay_exc.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "replay_run",
    }
    assert verify_exc.value.status_code == 503
    assert verify_exc.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "verify_run",
    }
    assert reexec_exc.value.status_code == 503
    assert reexec_exc.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "runs",
        "operation": "reexec_run",
    }
    assert service.calls == []


def test_replay_run_does_not_swallow_provider_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ProviderDeps:
        def replay_run(self, run_id: str, payload: dict | None = None) -> dict[str, object]:
            raise RuntimeError("runs routes not configured")

    service = _DummyService()
    monkeypatch.setattr(routes_runs, "_service", service)
    api_deps.configure_runs_route_deps_provider(lambda: _ProviderDeps())
    try:
        with pytest.raises(RuntimeError, match="runs routes not configured"):
            routes_runs.replay_run("run-provider", payload={"baseline_run_id": "base-1"})
    finally:
        api_deps.configure_runs_route_deps_provider(None)

    assert service.calls == []


def test_list_events_route_enforces_limit_query_bounds() -> None:
    app = FastAPI()
    app.include_router(routes_runs.router)

    class _RunsDeps:
        def __init__(self) -> None:
            self.last_limit: int | None = None

        def list_events(self, limit: int = 200) -> list[dict[str, int]]:
            self.last_limit = limit
            return [{"limit": limit}]

    deps = _RunsDeps()
    app.dependency_overrides[api_deps.get_runs_route_deps] = lambda: deps
    client = TestClient(app)

    ok_response = client.get("/api/events", params={"limit": 1})
    assert ok_response.status_code == 200
    assert ok_response.json() == [{"limit": 1}]
    assert deps.last_limit == 1

    low_response = client.get("/api/events", params={"limit": 0})
    assert low_response.status_code == 422

    high_response = client.get("/api/events", params={"limit": 5001})
    assert high_response.status_code == 422
