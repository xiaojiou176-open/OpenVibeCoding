from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from cortexpilot_orch.api import routes_pm


def _build_app(
    *,
    capture: dict[str, Any],
) -> FastAPI:
    app = FastAPI()
    app.include_router(routes_pm.router)

    def _list_handler(
        request: Request,
        status: str | None,
        status_filters: list[str],
        owner_pm: str | None,
        project_key: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        capture["list"] = {
            "request_path": request.url.path,
            "status": status,
            "status_filters": status_filters,
            "owner_pm": owner_pm,
            "project_key": project_key,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        }
        return [{"ok": True}]

    def _events_handler(
        pm_session_id: str,
        request: Request,
        since: str | None,
        limit: int | None,
        tail: bool,
        event_types: list[str],
        run_ids: list[str],
    ) -> list[dict[str, Any]]:
        capture["events"] = {
            "pm_session_id": pm_session_id,
            "request_path": request.url.path,
            "since": since,
            "limit": limit,
            "tail": tail,
            "event_types": event_types,
            "run_ids": run_ids,
        }
        return [{"ok": True}]

    app.state.routes_pm_handlers = {
        "list_pm_sessions": _list_handler,
        "get_pm_session": lambda _pm_session_id: {"ok": True},
        "get_pm_session_events": _events_handler,
        "get_pm_session_graph": lambda _pm_session_id, _window, _group_by_role: {"ok": True},
        "get_pm_session_metrics": lambda _pm_session_id: {"ok": True},
        "post_pm_session_message": lambda _pm_session_id, _payload: {"ok": True},
        "get_command_tower_overview": lambda: {"ok": True},
        "get_command_tower_alerts": lambda: {"ok": True},
    }
    return app


def test_routes_pm_list_sessions_forwards_status_array_filters() -> None:
    capture: dict[str, Any] = {}
    client = TestClient(_build_app(capture=capture))

    response = client.get(
        "/api/pm/sessions",
        params=[
            ("status", "active"),
            ("status[]", "failed"),
            ("status[]", "archived"),
            ("owner_pm", "pm-a"),
            ("project_key", "cortexpilot"),
            ("sort", "failed_desc"),
            ("limit", "25"),
            ("offset", "3"),
        ],
    )
    assert response.status_code == 200
    assert capture["list"]["status"] == "active"
    assert capture["list"]["status_filters"] == ["failed", "archived"]
    assert capture["list"]["owner_pm"] == "pm-a"
    assert capture["list"]["project_key"] == "cortexpilot"
    assert capture["list"]["sort"] == "failed_desc"
    assert capture["list"]["limit"] == 25
    assert capture["list"]["offset"] == 3


def test_routes_pm_get_events_forwards_types_and_run_ids_filters() -> None:
    capture: dict[str, Any] = {}
    client = TestClient(_build_app(capture=capture))

    response = client.get(
        "/api/pm/sessions/session-1/events",
        params=[
            ("since", "2026-01-01T00:00:00Z"),
            ("limit", "50"),
            ("tail", "true"),
            ("types", "CHAIN_HANDOFF"),
            ("types[]", "HUMAN_APPROVAL_REQUIRED"),
            ("types[]", "  "),
            ("run_ids", "run_1"),
            ("run_ids[]", "run_2"),
            ("run_ids[]", ""),
        ],
    )
    assert response.status_code == 200
    assert capture["events"]["pm_session_id"] == "session-1"
    assert capture["events"]["since"] == "2026-01-01T00:00:00Z"
    assert capture["events"]["limit"] == 50
    assert capture["events"]["tail"] is True
    assert capture["events"]["event_types"] == ["CHAIN_HANDOFF", "HUMAN_APPROVAL_REQUIRED"]
    assert capture["events"]["run_ids"] == ["run_1", "run_2"]
