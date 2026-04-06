from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from cortexpilot_orch.api import deps as api_deps
from cortexpilot_orch.api import routes_admin
from cortexpilot_orch.store import run_store as run_store_module


@pytest.fixture(autouse=True)
def _reset_admin_provider() -> None:
    previous_provider = getattr(api_deps, "_admin_route_deps_provider", None)
    api_deps.configure_admin_route_deps_provider(None)
    yield
    api_deps.configure_admin_route_deps_provider(previous_provider)


def _approval_headers() -> dict[str, str]:
    return {"x-cortexpilot-role": "TECH_LEAD"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"run_id": ""},
        {"run_id": None},
        {"run_id": 0},
        {"run_id": False},
    ],
)
def test_route_admin_approve_missing_run_id(payload: dict) -> None:
    app = FastAPI()
    app.include_router(routes_admin.router)

    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
    }

    client = TestClient(app)
    response = client.post("/api/god-mode/approve", json=payload, headers=_approval_headers())

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "RUN_ID_REQUIRED"


def test_route_admin_approve_rejects_non_dict_payload_with_400() -> None:
    app = FastAPI()
    app.include_router(routes_admin.router)

    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
    }

    client = TestClient(app)
    response = client.post("/api/god-mode/approve", json=["invalid"], headers=_approval_headers())

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PAYLOAD_INVALID"


def test_route_admin_approve_store_failure_returns_500() -> None:
    app = FastAPI()
    app.include_router(routes_admin.router)

    def fail_mutation(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("store unavailable")

    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
        "approve_god_mode_mutation": fail_mutation,
    }

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/god-mode/approve", json={"run_id": "run-123"}, headers=_approval_headers())

    assert response.status_code == 500
    assert "Internal Server Error" in response.text


def test_approve_god_mode_missing_run_id_skips_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_append_event(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("append_event should not be called")

    monkeypatch.setattr(routes_admin.run_store, "append_event", fail_append_event)

    with pytest.raises(HTTPException) as exc_info:
        routes_admin.approve_god_mode({})
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "RUN_ID_REQUIRED"


def test_approve_god_mode_empty_run_id_skips_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_append_event(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("append_event should not be called")

    monkeypatch.setattr(routes_admin.run_store, "append_event", fail_append_event)

    with pytest.raises(HTTPException) as exc_info:
        routes_admin.approve_god_mode({"run_id": ""})
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "RUN_ID_REQUIRED"


def test_approve_god_mode_rejects_non_dict_payload() -> None:
    with pytest.raises(HTTPException) as exc_info:
        routes_admin.approve_god_mode(["run-123"])
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "PAYLOAD_INVALID"


def test_approve_god_mode_store_exception_bubbles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_append_event(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(
        routes_admin,
        "_has_pending_approval",
        lambda _run_id, _request=None, admin_deps=None: True,
    )
    monkeypatch.setattr(routes_admin.run_store, "append_event", fail_append_event)

    with pytest.raises(RuntimeError, match="store unavailable"):
        routes_admin.approve_god_mode({"run_id": "run-123"})


def test_route_admin_approve_fail_closed_when_mutation_handler_unconfigured(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic_token = "sk-" + "live-raw-secret"
    app = FastAPI()
    app.include_router(routes_admin.router)
    app.state.routes_admin_handlers = {
        "get_run_events": lambda _run_id: [{"event": "HUMAN_APPROVAL_REQUIRED"}],
    }

    monkeypatch.setattr(routes_admin, "_orchestration_service", object())
    monkeypatch.setattr(
        run_store_module,
        "_default_store",
        run_store_module.RunStore(runs_root=tmp_path / "runs"),
    )

    client = TestClient(app)
    response = client.post(
        "/api/god-mode/approve",
        json={
            "run_id": "run-fallback",
            "approved_by": "ops",
            "token": synthetic_token,
            "nested": {"api_key": "nested-secret-value"},
        },
        headers=_approval_headers(),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin",
        "operation": "approve_god_mode:mutation",
    }

    events_path = tmp_path / "runs" / "run-fallback" / "events.jsonl"
    assert not events_path.exists()


def test_approve_god_mode_uses_provider_when_request_absent() -> None:
    synthetic_token = "sk-" + "live-raw-secret"
    seen: dict[str, Any] = {}

    class _ProviderDeps:
        def list_pending_approvals(self) -> list[dict[str, str]]:
            return []

        def get_run_events(self, _run_id: str) -> list[dict[str, str]]:
            return [{"event": "HUMAN_APPROVAL_REQUIRED"}]

        def approve_god_mode_mutation(self, run_id: str, payload: dict[str, Any]) -> dict[str, str]:
            seen["payload"] = payload
            return {"source": "provider", "run_id": run_id, "approved_by": payload.get("approved_by", "")}

    api_deps.configure_admin_route_deps_provider(lambda: _ProviderDeps())
    try:
        approved = routes_admin.approve_god_mode(
            {
                "run_id": "run-provider",
                "approved_by": "ops",
                "token": synthetic_token,
                "nested": {"api_key": "nested-secret-value"},
            }
        )
    finally:
        api_deps.configure_admin_route_deps_provider(None)

    assert approved == {"source": "provider", "run_id": "run-provider", "approved_by": "ops"}
    assert isinstance(seen.get("payload"), dict)
    assert seen["payload"]["token"] == "[REDACTED]"
    assert seen["payload"]["nested"]["api_key"] == "[REDACTED]"


def test_resolve_admin_route_deps_prefers_provider_over_partial_state_mapping() -> None:
    class _ProviderDeps:
        def list_pending_approvals(self) -> list[dict[str, str]]:
            return [{"source": "provider"}]

    provider = _ProviderDeps()
    api_deps.configure_admin_route_deps_provider(lambda: provider)
    app = FastAPI()
    app.state.routes_admin_handlers = {"list_pending_approvals": None}
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/god-mode/pending",
            "headers": [],
            "app": app,
        }
    )
    try:
        resolved = api_deps.resolve_admin_route_deps(request)
    finally:
        api_deps.configure_admin_route_deps_provider(None)

    assert resolved is provider
    assert resolved.list_pending_approvals() == [{"source": "provider"}]


def test_approve_god_mode_fail_closed_when_pending_check_handler_unconfigured(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.state.routes_admin_handlers = {"list_pending_approvals": lambda: []}
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/god-mode/approve",
            "headers": [(b"x-cortexpilot-role", b"TECH_LEAD")],
            "app": app,
        }
    )

    run_id = "run-partial-admin-mapping"
    runs_root = tmp_path / "runs"
    events_dir = runs_root / run_id
    events_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        routes_admin,
        "_read_events_from_store",
        lambda candidate: [{"event": "HUMAN_APPROVAL_REQUIRED"}] if candidate == run_id else [],
    )

    monkeypatch.setattr(routes_admin, "_orchestration_service", object())
    monkeypatch.setattr(
        run_store_module,
        "_default_store",
        run_store_module.RunStore(runs_root=runs_root),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes_admin.approve_god_mode({"run_id": run_id, "approved_by": "ops"}, request=request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "code": "ROUTE_DEPS_NOT_CONFIGURED",
        "error": "route dependencies not configured",
        "group": "admin",
        "operation": "approve_god_mode:pending_check",
    }
    assert not (events_dir / "events.jsonl").exists()


def test_approve_god_mode_does_not_swallow_provider_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ProviderDeps:
        def list_pending_approvals(self) -> list[dict[str, str]]:
            return []

        def get_run_events(self, _run_id: str) -> list[dict[str, str]]:
            return [{"event": "HUMAN_APPROVAL_REQUIRED"}]

        def approve_god_mode_mutation(self, run_id: str, payload: dict[str, str]) -> dict[str, str]:
            raise RuntimeError("admin routes not configured")

    monkeypatch.setattr(
        routes_admin,
        "approve_god_mode_mutation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected fallback")),
    )
    api_deps.configure_admin_route_deps_provider(lambda: _ProviderDeps())
    try:
        with pytest.raises(RuntimeError, match="admin routes not configured"):
            routes_admin.approve_god_mode({"run_id": "run-provider", "approved_by": "ops"})
    finally:
        api_deps.configure_admin_route_deps_provider(None)


def test_has_pending_approval_uses_latest_required_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes_admin,
        "_read_events_from_store",
        lambda _run_id: [
            {"event": "HUMAN_APPROVAL_REQUIRED"},
            {"event": "HUMAN_APPROVAL_COMPLETED"},
            {"event": "HUMAN_APPROVAL_REQUIRED"},
        ],
    )
    assert routes_admin._has_pending_approval("run-latest-required") is True


def test_collect_pending_approvals_handles_required_completed_required_sequence(tmp_path) -> None:
    runs_root = tmp_path / "runs"
    (runs_root / "run-1").mkdir(parents=True, exist_ok=True)
    pending = routes_admin.collect_pending_approvals(
        runs_root=runs_root,
        read_events_fn=lambda _run_id: [
            {"event": "HUMAN_APPROVAL_REQUIRED", "context": {"reason": ["first"]}},
            {"event": "HUMAN_APPROVAL_COMPLETED"},
            {"event": "HUMAN_APPROVAL_REQUIRED", "context": {"reason": ["second"], "actions": ["approve"]}},
        ],
    )
    assert len(pending) == 1
    assert pending[0]["run_id"] == "run-1"
    assert pending[0]["reason"] == ["second"]
