from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter(prefix="/api", tags=["pm"])

_ListPmSessionsHandler = Callable[
    [Request, str | None, list[str], str | None, str | None, str, int, int],
    list[dict[str, Any]],
]
_GetPmSessionHandler = Callable[[str], dict[str, Any]]
_GetPmSessionEventsHandler = Callable[
    [str, Request, str | None, int | None, bool, list[str], list[str]],
    list[dict[str, Any]],
]
_GetPmSessionGraphHandler = Callable[[str, str, bool], dict[str, Any]]
_GetPmSessionMetricsHandler = Callable[[str], dict[str, Any]]
_PostPmSessionMessageHandler = Callable[[str, dict[str, Any]], dict[str, Any]]
_GetCommandTowerOverviewHandler = Callable[[], dict[str, Any]]
_GetCommandTowerAlertsHandler = Callable[[], dict[str, Any]]
_PmHandler = Callable[..., Any]


def _route_deps_not_configured_http_error(*, operation: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "ROUTE_DEPS_NOT_CONFIGURED",
            "error": "route dependencies not configured",
            "group": "pm",
            "operation": operation,
        },
    )


def _resolve_handler(request: Request, key: str) -> _PmHandler | None:
    handlers = getattr(request.app.state, "routes_pm_handlers", None)
    if not isinstance(handlers, dict):
        return None
    handler = handlers.get(key)
    return handler if callable(handler) else None


def _require_handler(request: Request, key: str, *, operation: str) -> _PmHandler:
    handler = _resolve_handler(request, key)
    if handler is None:
        raise _route_deps_not_configured_http_error(operation=operation)
    return handler


@router.get("/pm/sessions")
def list_pm_sessions(
    request: Request,
    status: str | None = None,
    _status_array: list[str] = Query(default_factory=list, alias="status[]"),
    owner_pm: str | None = None,
    project_key: str | None = None,
    sort: str = "updated_desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _require_handler(request, "list_pm_sessions", operation="list_pm_sessions")(
        request, status, _status_array, owner_pm, project_key, sort, limit, offset
    )


@router.get("/pm/sessions/{pm_session_id}")
def get_pm_session(pm_session_id: str, request: Request) -> dict[str, Any]:
    return _require_handler(request, "get_pm_session", operation="get_pm_session")(pm_session_id)


@router.get("/pm/sessions/{pm_session_id}/events")
def get_pm_session_events(
    pm_session_id: str,
    request: Request,
    since: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=5000),
    tail: bool = False,
    _types: str | None = Query(default=None, alias="types"),
    _types_array: list[str] = Query(default_factory=list, alias="types[]"),
    _run_ids: str | None = Query(default=None, alias="run_ids"),
    _run_ids_array: list[str] = Query(default_factory=list, alias="run_ids[]"),
) -> list[dict[str, Any]]:
    event_types = [value for value in [_types, *_types_array] if isinstance(value, str) and value.strip()]
    run_ids = [value for value in [_run_ids, *_run_ids_array] if isinstance(value, str) and value.strip()]
    return _require_handler(request, "get_pm_session_events", operation="get_pm_session_events")(
        pm_session_id, request, since, limit, tail, event_types, run_ids
    )


@router.get("/pm/sessions/{pm_session_id}/conversation-graph")
def get_pm_session_conversation_graph(
    pm_session_id: str,
    request: Request,
    window: str = "30m",
    group_by_role: bool = False,
) -> dict[str, Any]:
    return _require_handler(request, "get_pm_session_graph", operation="get_pm_session_conversation_graph")(
        pm_session_id, window, group_by_role
    )


@router.get("/pm/sessions/{pm_session_id}/metrics")
def get_pm_session_metrics(pm_session_id: str, request: Request) -> dict[str, Any]:
    return _require_handler(request, "get_pm_session_metrics", operation="get_pm_session_metrics")(pm_session_id)


@router.post("/pm/sessions/{pm_session_id}/messages")
def post_pm_session_message(pm_session_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    return _require_handler(request, "post_pm_session_message", operation="post_pm_session_message")(
        pm_session_id, payload
    )


@router.get("/command-tower/overview")
def get_command_tower_overview(request: Request) -> dict[str, Any]:
    return _require_handler(request, "get_command_tower_overview", operation="get_command_tower_overview")()


@router.get("/command-tower/alerts")
def get_command_tower_alerts(request: Request) -> dict[str, Any]:
    return _require_handler(request, "get_command_tower_alerts", operation="get_command_tower_alerts")()
