from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from openvibecoding_orch.api import deps as api_deps
from openvibecoding_orch.api.security_validators import validate_run_id
from openvibecoding_orch.config import load_config
from openvibecoding_orch.services.orchestration_service import OrchestrationService, sanitize_approval_payload
from openvibecoding_orch.store import run_store


router = APIRouter(prefix="/api", tags=["admin"])
_orchestration_service = OrchestrationService()
_RUM_JSONL_PATH: Path | None = None
_DEFAULT_APPROVAL_ROLES = {"OWNER", "ARCHITECT", "OPS", "TECH_LEAD"}
try:
    _RUM_MAX_PAYLOAD_BYTES = max(1, int(os.getenv("OPENVIBECODING_RUM_MAX_PAYLOAD_BYTES", "32768")))
except ValueError:
    _RUM_MAX_PAYLOAD_BYTES = 32768


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


def _approval_roles() -> set[str]:
    raw = os.getenv("OPENVIBECODING_APPROVAL_ALLOWED_ROLES", "").strip()
    if not raw:
        return set(_DEFAULT_APPROVAL_ROLES)
    parsed = {item.strip().upper() for item in raw.split(",") if item.strip()}
    return parsed or set(_DEFAULT_APPROVAL_ROLES)


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


def _enforce_approval_rbac(request: Request | None) -> None:
    if request is None:
        raise HTTPException(status_code=403, detail={"code": "ROLE_REQUIRED"})
    role = _request_role(request)
    if not role:
        raise HTTPException(status_code=403, detail={"code": "ROLE_REQUIRED"})
    if not _role_header_is_trusted(request):
        raise HTTPException(status_code=403, detail={"code": "ROLE_HEADER_UNTRUSTED"})
    if role not in _approval_roles():
        raise HTTPException(status_code=403, detail={"code": "ROLE_FORBIDDEN"})


def _read_events_from_store(run_id: str) -> list[dict[str, Any]]:
    events_path = load_config().runs_root / run_id / "events.jsonl"
    if not events_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for raw in events_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _has_pending_approval(
    run_id: str,
    request: Request | None = None,
    admin_deps: api_deps.AdminRouteDeps | None = None,
) -> bool:
    resolved_deps = admin_deps or api_deps.resolve_admin_route_deps(request)
    if resolved_deps is not None:
        events = resolved_deps.get_run_events(run_id)
    else:
        events = _read_events_from_store(run_id)
    if not events:
        return False
    return _is_pending_after_latest_required(events)


def _is_pending_after_latest_required(events: list[dict[str, Any]]) -> bool:
    last_required_index: int | None = None
    for index, event in enumerate(events):
        if isinstance(event, dict) and event.get("event") == "HUMAN_APPROVAL_REQUIRED":
            last_required_index = index
    if last_required_index is None:
        return False
    for event in events[last_required_index + 1 :]:
        if isinstance(event, dict) and event.get("event") == "HUMAN_APPROVAL_COMPLETED":
            return False
    return True


def collect_pending_approvals(
    *,
    runs_root: Path,
    read_events_fn: Callable[[str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for run_dir in runs_root.glob("*"):
        run_id = run_dir.name
        events = read_events_fn(run_id)
        required_events = [ev for ev in events if isinstance(ev, dict) and ev.get("event") == "HUMAN_APPROVAL_REQUIRED"]
        if not required_events or not _is_pending_after_latest_required(events):
            continue
        latest = required_events[-1]
        context = latest.get("context") if isinstance(latest.get("context"), dict) else latest.get("meta") if isinstance(latest.get("meta"), dict) else {}
        manifest_path = run_dir / "manifest.json"
        contract_path = run_dir / "contract.json"
        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        except json.JSONDecodeError:
            manifest_payload = {}
        try:
            contract_payload = json.loads(contract_path.read_text(encoding="utf-8")) if contract_path.exists() else {}
        except json.JSONDecodeError:
            contract_payload = {}
        task_id = str((manifest_payload or {}).get("task_id") or (contract_payload or {}).get("task_id") or "").strip()
        failure_reason = str((manifest_payload or {}).get("failure_reason") or "").strip()
        reasons = [str(item).strip() for item in context.get("reason", []) if str(item).strip()] if isinstance(context.get("reason"), list) else []
        actions = [str(item).strip() for item in context.get("actions", []) if str(item).strip()] if isinstance(context.get("actions"), list) else []
        verify_steps = [str(item).strip() for item in context.get("verify_steps", []) if str(item).strip()] if isinstance(context.get("verify_steps"), list) else []
        resume_step = str(context.get("resume_step") or "").strip()
        summary_parts = [f"Run {run_id} is waiting for human approval."]
        if failure_reason:
            summary_parts.append(f"Failure reason: {failure_reason}.")
        if resume_step:
            summary_parts.append(f"Resume at: {resume_step}.")
        approval_pack = {
            "report_type": "approval_pack",
            "run_id": run_id,
            "status": "pending",
            "summary": " ".join(summary_parts).strip(),
            "task_id": task_id,
            "failure_reason": failure_reason,
            "reasons": reasons,
            "actions": actions,
            "verify_steps": verify_steps,
            "resume_step": resume_step,
        }
        pending.append(
            {
                "run_id": run_id,
                "status": "pending",
                "task_id": task_id,
                "failure_reason": failure_reason,
                "reason": reasons,
                "actions": actions,
                "verify_steps": verify_steps,
                "resume_step": resume_step,
                "approval_pack": approval_pack,
            }
        )
    return pending


def list_pending_approvals(
    request: Request | None = None,
    admin_deps: api_deps.AdminRouteDeps | None = None,
) -> list[dict[str, Any]]:
    resolved_deps = admin_deps or api_deps.resolve_admin_route_deps(request)
    if resolved_deps is None:
        return []
    try:
        return resolved_deps.list_pending_approvals()
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="list_pending_approvals") from exc


def approve_god_mode_mutation(
    run_id: str,
    payload: dict[str, Any],
    *,
    orchestration_service: Any = None,
    append_run_event_fn: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    sanitized_payload = sanitize_approval_payload(payload)
    service = orchestration_service if orchestration_service is not None else _orchestration_service
    approve_fn = getattr(service, "approve_god_mode", None)
    if callable(approve_fn):
        return approve_fn(run_id, sanitized_payload)
    event_payload = {
        "level": "INFO",
        "event": "HUMAN_APPROVAL_COMPLETED",
        "run_id": run_id,
        "context": {"payload": sanitized_payload},
    }
    if append_run_event_fn is not None:
        append_run_event_fn(run_id, event_payload)
    else:
        run_store.append_event(run_id, event_payload)
    return {"ok": True, "run_id": run_id}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rum_jsonl_path() -> Path:
    if _RUM_JSONL_PATH is not None:
        return _RUM_JSONL_PATH
    return load_config().logs_root / "runtime" / "rum_web_vitals.jsonl"


def _json_payload_size_bytes(payload: Any) -> int:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = json.dumps({"raw_payload": str(payload)}, ensure_ascii=False, separators=(",", ":"))
    return len(serialized.encode("utf-8"))


def _rum_correlation_kind(body: dict[str, Any]) -> str:
    if str(body.get("run_id") or "").strip():
        return "run"
    if str(body.get("session_id") or "").strip():
        return "session"
    if str(body.get("request_id") or "").strip():
        return "request"
    if str(body.get("trace_id") or "").strip():
        return "trace"
    if str(body.get("test_id") or "").strip():
        return "test"
    return "none"


def _append_rum_record(payload: Any) -> tuple[bool, str]:
    try:
        payload_size_bytes = _json_payload_size_bytes(payload)
        if payload_size_bytes > _RUM_MAX_PAYLOAD_BYTES:
            return False, "PAYLOAD_TOO_LARGE"
        body: dict[str, Any]
        if isinstance(payload, dict):
            body = payload
        else:
            body = {"raw_payload": payload}
        sanitized_body = sanitize_approval_payload(body)
        event = {
            "ts": _now_iso(),
            "level": "INFO",
            "domain": "ui",
            "surface": "dashboard",
            "service": "openvibecoding-dashboard",
            "component": "api.routes_admin",
            "event": "RUM_WEB_VITAL_RECEIVED",
            "lane": "runtime",
            "run_id": str(sanitized_body.get("run_id") or ""),
            "request_id": str(sanitized_body.get("request_id") or ""),
            "trace_id": str(sanitized_body.get("trace_id") or ""),
            "session_id": str(sanitized_body.get("session_id") or ""),
            "test_id": str(sanitized_body.get("test_id") or ""),
            "source_kind": "app_log",
            "artifact_kind": "rum_web_vitals",
            "correlation_kind": _rum_correlation_kind(sanitized_body),
            "meta": {
                "source": "dashboard_web_vitals",
                "payload_size_bytes": payload_size_bytes,
                "payload": sanitized_body,
            },
            "redaction_version": "redaction.v1",
            "schema_version": "log_event.v2",
        }
        rum_path = _rum_jsonl_path()
        rum_path.parent.mkdir(parents=True, exist_ok=True)
        with rum_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return True, ""
    except Exception:  # pragma: no cover - defensive fallback
        return False, "WRITE_FAILED"


@router.get("/god-mode/pending")
def list_pending_approvals_route(
    request: Request,
    admin_deps: api_deps.AdminRouteDeps = Depends(api_deps.get_admin_route_deps),
) -> list[dict[str, Any]]:
    _enforce_approval_rbac(request)
    return list_pending_approvals(request, admin_deps=admin_deps)


@router.get("/god-mode/ping")
def god_mode_ping() -> dict[str, Any]:
    return {"ok": True, "mode": "god"}


def approve_god_mode(
    payload: Any,
    request: Request | None = None,
    admin_deps: api_deps.AdminRouteDeps | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"code": "PAYLOAD_INVALID"})
    run_id = validate_run_id(str(payload.get("run_id") or ""))
    # Keep API routes fail-closed via request-bound RBAC, while preserving
    # direct function-call semantics used by unit tests/providers.
    if request is not None:
        _enforce_approval_rbac(request)
    sanitized_payload = sanitize_approval_payload(payload)
    try:
        has_pending_approval = _has_pending_approval(run_id, request, admin_deps=admin_deps)
    except api_deps.RouteDepsNotConfiguredError as exc:
        raise _route_deps_not_configured_http_error(exc, operation="approve_god_mode:pending_check") from exc
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if exc.status_code == 503 and detail.get("code") == "ROUTE_DEPS_NOT_CONFIGURED":
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ROUTE_DEPS_NOT_CONFIGURED",
                    "error": "route dependencies not configured",
                    "group": detail.get("group", "admin"),
                    "operation": "approve_god_mode:pending_check",
                },
            ) from exc
        raise
    if not has_pending_approval:
        raise HTTPException(status_code=409, detail={"code": "APPROVAL_NOT_PENDING"})
    resolved_deps = admin_deps or api_deps.resolve_admin_route_deps(request)
    if resolved_deps is not None:
        try:
            return resolved_deps.approve_god_mode_mutation(run_id, sanitized_payload)
        except api_deps.RouteDepsNotConfiguredError as exc:
            raise _route_deps_not_configured_http_error(exc, operation="approve_god_mode:mutation") from exc
    return approve_god_mode_mutation(run_id, sanitized_payload)


@router.post("/god-mode/approve")
def approve_god_mode_route(
    request: Request,
    payload: Any = Body(...),
    admin_deps: api_deps.AdminRouteDeps = Depends(api_deps.get_admin_route_deps),
) -> dict[str, Any]:
    return approve_god_mode(payload, request, admin_deps=admin_deps)


@router.post("/rum/web-vitals")
def ingest_rum_web_vitals(payload: Any = Body(default=None)) -> dict[str, Any]:
    ingested, reason = _append_rum_record(payload)
    result: dict[str, Any] = {
        "ok": ingested,
        "ingested": ingested,
        "artifact_kind": "rum_web_vitals",
    }
    if not ingested and reason:
        result["reason"] = reason
    return result
