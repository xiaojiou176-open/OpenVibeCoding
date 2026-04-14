from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from openvibecoding_orch.api import main as api_main
from openvibecoding_orch.api import pm_session_aggregation


def _build_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/pm/sessions",
        "headers": [],
        "query_string": b"",
        "app": api_main.app,
    }
    return Request(scope)


def test_main_pm_session_wrappers_delegate_to_aggregation(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_list_pm_sessions(
        request: Request,
        *,
        status: str | None = None,
        owner_pm: str | None = None,
        project_key: str | None = None,
        sort: str = "updated_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        captured["request_path"] = request.url.path
        captured["status"] = status
        captured["owner_pm"] = owner_pm
        captured["project_key"] = project_key
        captured["sort"] = sort
        captured["limit"] = limit
        captured["offset"] = offset
        return [{"pm_session_id": "delegated"}]

    monkeypatch.setattr(pm_session_aggregation, "list_pm_sessions", _fake_list_pm_sessions)

    payload = api_main.list_pm_sessions(
        _build_request(),
        status="active",
        owner_pm="pm-alpha",
        project_key="openvibecoding",
        sort="blocked_desc",
        limit=7,
        offset=2,
    )

    assert payload == [{"pm_session_id": "delegated"}]
    assert captured == {
        "request_path": "/api/pm/sessions",
        "status": "active",
        "owner_pm": "pm-alpha",
        "project_key": "openvibecoding",
        "sort": "blocked_desc",
        "limit": 7,
        "offset": 2,
    }


def test_post_pm_session_message_checks_aggregation_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pm_session_aggregation,
        "get_pm_session",
        lambda pm_session_id: (_ for _ in ()).throw(
            HTTPException(status_code=404, detail={"code": "PM_SESSION_NOT_FOUND"})
        ),
    )

    client = TestClient(api_main.app)
    response = client.post("/api/pm/sessions/session-missing/messages", json={"message": "hi"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PM_SESSION_NOT_FOUND"


def test_pm_session_aggregation_fails_fast_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pm_session_aggregation, "_runtime_root_fn", None)
    with pytest.raises(RuntimeError, match="pm session aggregation not configured: runtime_root_fn"):
        pm_session_aggregation.get_command_tower_overview()


def test_command_tower_overview_endpoint_has_no_silent_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> dict[str, object]:
        raise RuntimeError("counterfactual-overview-error")

    monkeypatch.setattr(pm_session_aggregation, "get_command_tower_overview", _boom)

    client = TestClient(api_main.app)
    response = client.get("/api/command-tower/overview")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "INTERNAL_SERVER_ERROR"


def test_pm_sessions_invalid_sort_returns_sort_specific_error() -> None:
    client = TestClient(api_main.app)
    response = client.get("/api/pm/sessions", params={"sort": "invalid_sort"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "PM_SESSION_SORT_INVALID"


def test_main_pm_session_wrappers_forward_status_filters_when_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_list_pm_sessions(
        request: Request,
        *,
        status: str | None = None,
        status_filters: list[str] | None = None,
        owner_pm: str | None = None,
        project_key: str | None = None,
        sort: str = "updated_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, object]]:
        captured["request_path"] = request.url.path
        captured["status"] = status
        captured["status_filters"] = status_filters
        captured["owner_pm"] = owner_pm
        captured["project_key"] = project_key
        captured["sort"] = sort
        captured["limit"] = limit
        captured["offset"] = offset
        return [{"pm_session_id": "delegated-status-filters"}]

    monkeypatch.setattr(pm_session_aggregation, "list_pm_sessions", _fake_list_pm_sessions)

    payload = api_main.list_pm_sessions(
        _build_request(),
        status="active",
        status_filters=["failed", "archived"],
        owner_pm="pm-alpha",
        project_key="openvibecoding",
        sort="blocked_desc",
        limit=7,
        offset=2,
    )

    assert payload == [{"pm_session_id": "delegated-status-filters"}]
    assert captured["status_filters"] == ["failed", "archived"]
