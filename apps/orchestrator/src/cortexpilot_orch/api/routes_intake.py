from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request


router = APIRouter(prefix="/api", tags=["intake"])

_ListIntakesHandler = Callable[[], list[dict]]
_GetIntakeHandler = Callable[[str], dict]
_CreateIntakeHandler = Callable[[dict], dict]
_AnswerIntakeHandler = Callable[[str, dict], dict]
_RunIntakeHandler = Callable[[str, dict | None], dict]
_IntakeHandler = Callable[..., Any]


def _route_deps_not_configured_http_error(*, operation: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "ROUTE_DEPS_NOT_CONFIGURED",
            "error": "route dependencies not configured",
            "group": "intake",
            "operation": operation,
        },
    )


def _resolve_handler(request: Request, key: str) -> _IntakeHandler | None:
    handlers = getattr(request.app.state, "routes_intake_handlers", None)
    if not isinstance(handlers, dict):
        return None
    handler = handlers.get(key)
    return handler if callable(handler) else None


def _require_handler(request: Request, key: str, *, operation: str) -> _IntakeHandler:
    handler = _resolve_handler(request, key)
    if handler is None:
        raise _route_deps_not_configured_http_error(operation=operation)
    return handler


@router.get("/intakes")
def list_intakes(request: Request) -> list[dict]:
    return _require_handler(request, "list_intakes", operation="list_intakes")()


@router.get("/task-packs")
def list_task_packs(request: Request) -> list[dict]:
    return _require_handler(request, "list_task_packs", operation="list_task_packs")()


@router.get("/intake/{intake_id}")
def get_intake(intake_id: str, request: Request) -> dict:
    return _require_handler(request, "get_intake", operation="get_intake")(intake_id)


@router.post("/intake")
def create_intake(payload: dict, request: Request) -> dict:
    return _require_handler(request, "create_intake", operation="create_intake")(payload)


@router.post("/intake/preview")
def preview_intake(payload: dict, request: Request) -> dict:
    return _require_handler(request, "preview_intake", operation="preview_intake")(payload)


@router.post("/intake/preview/copilot-brief")
def preview_intake_copilot_brief(payload: dict, request: Request) -> dict:
    return _require_handler(request, "preview_intake_copilot_brief", operation="preview_intake_copilot_brief")(payload)


@router.post("/intake/{intake_id}/answers")
def answer_intake(intake_id: str, payload: dict, request: Request) -> dict:
    return _require_handler(request, "answer_intake", operation="answer_intake")(intake_id, payload)


@router.post("/intake/{intake_id}/run")
def run_intake(intake_id: str, request: Request, payload: dict | None = None) -> dict:
    return _require_handler(request, "run_intake", operation="run_intake")(intake_id, payload)


@router.post("/pm/intake")
def pm_create_intake(payload: dict, request: Request) -> dict:
    return _require_handler(request, "create_intake", operation="pm_create_intake")(payload)


@router.get("/pm/task-packs")
def pm_list_task_packs(request: Request) -> list[dict]:
    return _require_handler(request, "list_task_packs", operation="pm_list_task_packs")()


@router.post("/pm/intake/preview")
def pm_preview_intake(payload: dict, request: Request) -> dict:
    return _require_handler(request, "preview_intake", operation="pm_preview_intake")(payload)


@router.post("/pm/intake/preview/copilot-brief")
def pm_preview_intake_copilot_brief(payload: dict, request: Request) -> dict:
    return _require_handler(request, "preview_intake_copilot_brief", operation="pm_preview_intake_copilot_brief")(payload)


@router.post("/pm/intake/{intake_id}/answer")
def pm_answer_intake(intake_id: str, payload: dict, request: Request) -> dict:
    return _require_handler(request, "answer_intake", operation="pm_answer_intake")(intake_id, payload)


@router.post("/pm/intake/{intake_id}/run")
def pm_run_intake(intake_id: str, request: Request, payload: dict | None = None) -> dict:
    return _require_handler(request, "run_intake", operation="pm_run_intake")(intake_id, payload)
