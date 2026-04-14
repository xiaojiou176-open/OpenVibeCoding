from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from openvibecoding_orch.api import deps as api_deps
from openvibecoding_orch.api import main_run_views_helpers
from openvibecoding_orch.api.security_validators import validate_run_id
from openvibecoding_orch.config import load_config
from openvibecoding_orch.locks.locker import release_lock
from openvibecoding_orch.services.orchestration_service import OrchestrationService


router = APIRouter(prefix="/api", tags=["runs"])
_service = OrchestrationService()
_DEFAULT_MUTATION_ROLES = {"OWNER", "ARCHITECT", "OPS", "TECH_LEAD"}
_logger = logging.getLogger(__name__)


class ReleaseLocksPayload(BaseModel):
    paths: list[str]


class QueueRunPayload(BaseModel):
    priority: int = 0
    scheduled_at: str | None = None
    deadline_at: str | None = None

    @field_validator("scheduled_at", "deadline_at")
    @classmethod
    def _validate_aware_iso_ts(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("queue timestamps must be valid ISO-8601 strings") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("queue timestamps must include an explicit timezone offset or Z suffix")
        return text


class QueueCancelPayload(BaseModel):
    reason: str | None = None


class QueueRunNextPayload(BaseModel):
    mock: bool = False


class RoleConfigRuntimeBindingPayload(BaseModel):
    runner: str | None = None
    provider: str | None = None
    model: str | None = None


class RoleConfigPayload(BaseModel):
    system_prompt_ref: str | None = None
    skills_bundle_ref: str | None = None
    mcp_bundle_ref: str | None = None
    runtime_binding: RoleConfigRuntimeBindingPayload


def _route_deps_not_configured_http_error(exc: api_deps.RouteDepsNotConfiguredError, *, operation: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "ROUTE_DEPS_NOT_CONFIGURED",
            "error": "route dependencies not configured",
            "group": exc.group_name,
            "operation": operation,
        },
    )


def _masked_internal_error(*, code: str, operation: str, exc: Exception) -> HTTPException:
    _logger.exception("routes_runs.%s failed", operation)
    return HTTPException(status_code=500, detail={"code": code})


def _validated_run_id(run_id: str) -> str:
    return validate_run_id(run_id)


def _mutation_roles() -> set[str]:
    raw = os.getenv("OPENVIBECODING_APPROVAL_ALLOWED_ROLES", "").strip()
    if not raw:
        return set(_DEFAULT_MUTATION_ROLES)
    parsed = {item.strip().upper() for item in raw.split(",") if item.strip()}
    return parsed or set(_DEFAULT_MUTATION_ROLES)


def _request_role(request: Request | None) -> str:
    if request is None:
        return ""
    return request.headers.get("x-openvibecoding-role", "").strip().upper()


def _role_header_is_trusted(request: Request | None) -> bool:
    if request is None:
        return True
    if not load_config().api_auth_required:
        return True
    return bool(getattr(request.state, "openvibecoding_api_auth_verified", False))


def _enforce_mutation_rbac(request: Request | None) -> None:
    role = _request_role(request)
    if not role:
        raise HTTPException(status_code=403, detail={"code": "ROLE_REQUIRED"})
    if not _role_header_is_trusted(request):
        raise HTTPException(status_code=403, detail={"code": "ROLE_HEADER_UNTRUSTED"})
    if role not in _mutation_roles():
        raise HTTPException(status_code=403, detail={"code": "ROLE_FORBIDDEN"})


@router.get("/runs")
def list_runs(
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> list[dict]:
    try:
        return runs_deps.list_runs()
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="list_runs") from exc


@router.get("/queue")
def list_queue(
    workflow_id: str | None = None,
    status: str | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> list[dict[str, Any]]:
    return runs_deps.list_queue(workflow_id=workflow_id, status=status)


@router.post("/queue/from-run/{run_id}")
def enqueue_run_queue(
    run_id: str,
    payload: QueueRunPayload,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.enqueue_run_queue(_validated_run_id(run_id), payload.model_dump())


@router.post("/queue/from-run/{run_id}/preview")
def preview_enqueue_run_queue(
    run_id: str,
    payload: QueueRunPayload,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.preview_enqueue_run_queue(_validated_run_id(run_id), payload.model_dump())


@router.post("/queue/run-next")
def run_next_queue(
    payload: QueueRunNextPayload,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.run_next_queue(payload.model_dump())


@router.post("/queue/{queue_id}/cancel")
def cancel_queue_item(
    queue_id: str,
    payload: QueueCancelPayload,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.cancel_queue_item(
        queue_id,
        {
            "reason": payload.reason,
            "cancelled_by": _request_role(request),
        },
    )


@router.get("/workflows")
def list_workflows(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict]:
    return runs_deps.list_workflows()


@router.get("/workflows/{workflow_id}")
def get_workflow(
    workflow_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_workflow(workflow_id)


@router.post("/workflows/{workflow_id}/copilot-brief")
def get_workflow_operator_copilot_brief(
    workflow_id: str,
    payload: dict[str, Any] | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_workflow_operator_copilot_brief(workflow_id, payload or {})


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_run(_validated_run_id(run_id))


@router.get("/runs/{run_id}/events")
def get_events(
    run_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
    since: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=5000),
    tail: bool = False,
) -> list[dict[str, Any]]:
    return runs_deps.get_events(_validated_run_id(run_id), since=since, limit=limit, tail=tail)


@router.get("/runs/{run_id}/events/stream")
async def stream_events(
    run_id: str,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
    since: str | None = None,
    limit: int = Query(default=200, ge=1, le=5000),
    tail: bool = True,
    follow: bool = True,
) -> StreamingResponse:
    return await runs_deps.stream_events(
        _validated_run_id(run_id),
        request,
        since=since,
        limit=limit,
        tail=tail,
        follow=follow,
    )


@router.get("/runs/{run_id}/diff")
def get_diff(
    run_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_diff(_validated_run_id(run_id))


@router.get("/runs/{run_id}/reports")
def get_reports(
    run_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> list[dict[str, Any]]:
    return runs_deps.get_reports(_validated_run_id(run_id))


@router.get("/runs/{run_id}/artifacts")
def get_artifacts(
    run_id: str,
    name: str | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_artifacts(_validated_run_id(run_id), name=name)


@router.get("/runs/{run_id}/search")
def get_search(
    run_id: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_search(_validated_run_id(run_id))


@router.post("/runs/{run_id}/copilot-brief")
def get_operator_copilot_brief(
    run_id: str,
    payload: dict[str, Any] | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_operator_copilot_brief(_validated_run_id(run_id), payload or {})


@router.post("/runs/{run_id}/evidence/promote")
def promote_evidence(
    run_id: str,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.promote_evidence(_validated_run_id(run_id))


@router.post("/runs/{run_id}/rollback")
def rollback_run(
    run_id: str,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.rollback_run(_validated_run_id(run_id))


@router.post("/runs/{run_id}/reject")
def reject_run(
    run_id: str,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.reject_run(_validated_run_id(run_id))


@router.get("/contracts")
def list_contracts(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_contracts()


@router.get("/events")
def list_events(
    limit: int = Query(default=200, ge=1, le=5000),
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> list[dict[str, Any]]:
    return runs_deps.list_events(limit=limit)


@router.get("/diff-gate")
def list_diff_gate(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_diff_gate()


@router.get("/reviews")
def list_reviews(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_reviews()


@router.get("/tests")
def list_tests(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_tests()


@router.get("/agents")
def list_agents(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> dict[str, Any]:
    return runs_deps.list_agents()


@router.get("/agents/status")
def list_agents_status(
    run_id: str | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.list_agents_status(run_id=run_id)


@router.get("/agents/roles/{role}/config")
def get_role_config(
    role: str,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.get_role_config(role)


@router.post("/agents/roles/{role}/config/preview")
def preview_role_config(
    role: str,
    payload: RoleConfigPayload,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    return runs_deps.preview_role_config(role, payload.model_dump())


@router.post("/agents/roles/{role}/config/apply")
def apply_role_config(
    role: str,
    payload: RoleConfigPayload,
    request: Request,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return runs_deps.apply_role_config(role, payload.model_dump())


@router.get("/policies")
def list_policies(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> dict[str, Any]:
    return runs_deps.list_policies()


@router.get("/locks")
def list_locks(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_locks()


@router.post("/locks/release")
def release_locks_route(
    payload: ReleaseLocksPayload,
    request: Request,
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    return main_run_views_helpers.release_locks(paths=payload.paths, release_lock_fn=release_lock)


@router.get("/worktrees")
def list_worktrees(runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps)) -> list[dict[str, Any]]:
    return runs_deps.list_worktrees()


def replay_run(
    run_id: str,
    payload: dict | None = None,
    request: Request | None = None,
    runs_deps: api_deps.RunsRouteDeps | None = None,
) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    if payload is not None and not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"code": "PAYLOAD_INVALID"})
    resolved_deps = runs_deps or api_deps.resolve_runs_route_deps(request)
    if resolved_deps is not None:
        try:
            return resolved_deps.replay_run(run_id, payload)
        except api_deps.RouteDepsNotConfiguredError as exc:
            raise _route_deps_not_configured_http_error(exc, operation="replay_run") from exc
    baseline_run_id = payload.get("baseline_run_id") if payload else None
    return _service.replay_run(run_id, baseline_run_id=baseline_run_id)


def verify_run(
    run_id: str,
    strict: bool = True,
    request: Request | None = None,
    runs_deps: api_deps.RunsRouteDeps | None = None,
) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    resolved_deps = runs_deps or api_deps.resolve_runs_route_deps(request)
    if resolved_deps is not None:
        try:
            return resolved_deps.verify_run(run_id, strict=strict)
        except api_deps.RouteDepsNotConfiguredError as exc:
            raise _route_deps_not_configured_http_error(exc, operation="verify_run") from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _masked_internal_error(code="VERIFY_RUN_FAILED", operation="verify_run", exc=exc)
    try:
        return _service.replay_verify(run_id, strict=strict)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _masked_internal_error(code="VERIFY_RUN_FAILED", operation="verify_run", exc=exc)


def reexec_run(
    run_id: str,
    strict: bool = True,
    request: Request | None = None,
    runs_deps: api_deps.RunsRouteDeps | None = None,
) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    resolved_deps = runs_deps or api_deps.resolve_runs_route_deps(request)
    if resolved_deps is not None:
        try:
            return resolved_deps.reexec_run(run_id, strict=strict)
        except api_deps.RouteDepsNotConfiguredError as exc:
            raise _route_deps_not_configured_http_error(exc, operation="reexec_run") from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise _masked_internal_error(code="REEXEC_RUN_FAILED", operation="reexec_run", exc=exc)
    try:
        return _service.replay_reexec(run_id, strict=strict)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _masked_internal_error(code="REEXEC_RUN_FAILED", operation="reexec_run", exc=exc)


@router.post("/runs/{run_id}/replay")
def replay_run_route(
    run_id: str,
    request: Request,
    payload: dict | None = None,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    run_id = _validated_run_id(run_id)
    if payload is not None and not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"code": "PAYLOAD_INVALID"})
    try:
        return runs_deps.replay_run(run_id, payload)
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="replay_run_route") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _logger.exception("routes_runs.replay_run_route failed")
        raise HTTPException(status_code=500, detail={"code": "REPLAY_RUN_FAILED"})


@router.post("/runs/{run_id}/verify")
def verify_run_route(
    run_id: str,
    request: Request,
    strict: bool = True,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    run_id = _validated_run_id(run_id)
    try:
        return runs_deps.verify_run(run_id, strict=strict)
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="verify_run_route") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _logger.exception("routes_runs.verify_run_route failed")
        raise HTTPException(status_code=500, detail={"code": "VERIFY_RUN_FAILED"})


@router.post("/runs/{run_id}/reexec")
def reexec_run_route(
    run_id: str,
    request: Request,
    strict: bool = True,
    runs_deps: api_deps.RunsRouteDeps = Depends(api_deps.get_runs_route_deps),
) -> dict[str, Any]:
    _enforce_mutation_rbac(request)
    run_id = _validated_run_id(run_id)
    try:
        return runs_deps.reexec_run(run_id, strict=strict)
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="reexec_run_route") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _logger.exception("routes_runs.reexec_run_route failed")
        raise HTTPException(status_code=500, detail={"code": "REEXEC_RUN_FAILED"})


@router.get("/runs/{run_id}/_health")
def run_health_probe(run_id: str) -> dict[str, Any]:
    validated = _validated_run_id(run_id)
    return {"ok": True, "run_id": validated}
