from __future__ import annotations

from contextvars import ContextVar
import hmac
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from cortexpilot_orch.api import (
    artifact_helpers,
    deps as api_deps,
    event_cursor,
    main_pm_intake_helpers,
    main_runs_handlers,
    main_run_views_helpers,
    main_state_store_helpers,
    run_state_helpers,
    routes_admin,
    routes_intake,
    routes_pm,
    routes_runs,
    search_payload_helpers,
)
from cortexpilot_orch.config import get_api_runtime_config, load_config
from cortexpilot_orch.contract.compiler import build_role_binding_summary
from cortexpilot_orch.contract.validator import resolve_agent_registry_path
from cortexpilot_orch.observability.logger import log_event
from cortexpilot_orch.services.orchestration_service import OrchestrationService
from cortexpilot_orch.queue import QueueStore
from cortexpilot_orch.services.rollback_service import RollbackService
from cortexpilot_orch.planning.intake import IntakeService
from cortexpilot_orch.store import run_store as run_store_fallback
from cortexpilot_orch.worktrees import manager as worktree_manager

app = FastAPI(title="CortexPilot Orchestrator API")
_api_runtime_config = get_api_runtime_config()


def _resolve_allow_origins(dashboard_port: str, configured_origins: tuple[str, ...]) -> set[str]:
    allow_origins = {
        "http://localhost:3100",
        "http://127.0.0.1:3100",
        f"http://localhost:{dashboard_port}",
        f"http://127.0.0.1:{dashboard_port}",
    }
    for origin in configured_origins:
        normalized = origin.strip().rstrip("/")
        if normalized:
            allow_origins.add(normalized)
    return allow_origins


_allow_origins = _resolve_allow_origins(
    _api_runtime_config.dashboard_port,
    _api_runtime_config.allowed_origins,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_request_id_ctx: ContextVar[str] = ContextVar("cortexpilot_request_id", default="")
_trace_id_ctx: ContextVar[str] = ContextVar("cortexpilot_trace_id", default="")
_run_id_ctx: ContextVar[str] = ContextVar("cortexpilot_run_id", default="")
_bearer = HTTPBearer(auto_error=True)
_rollback_service = RollbackService()
_orchestration_service = OrchestrationService()


def _resolve_canary_percent() -> float:
    return get_api_runtime_config().canary_percent


def _resolve_request_lane(request: Request, request_id: str) -> str:
    explicit = request.headers.get("x-cortexpilot-lane", "").strip().lower()
    if explicit in {"stable", "canary"}:
        return explicit

    percent = _resolve_canary_percent()
    if percent <= 0:
        return "stable"

    digest = hashlib.sha1(request_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return "canary" if bucket < percent else "stable"


def _append_run_event(run_id: str, payload: dict[str, Any]) -> None:
    append_event_fn = getattr(_orchestration_service, "append_event", None)
    if callable(append_event_fn):
        append_event_fn(run_id, payload)
        return
    run_store_fallback.append_event(run_id, payload)


def _write_manifest(run_id: str, manifest_data: dict[str, Any]) -> None:
    write_manifest_fn = getattr(_orchestration_service, "write_manifest", None)
    if callable(write_manifest_fn):
        write_manifest_fn(run_id, manifest_data)
        return
    run_store_fallback.write_manifest(run_id, manifest_data)


def _write_evidence_bundle(run_id: str, bundle: dict[str, Any]) -> None:
    write_bundle_fn = getattr(_orchestration_service, "write_evidence_bundle", None)
    if callable(write_bundle_fn):
        write_bundle_fn(run_id, bundle)
        return
    run_store_fallback.write_report(run_id, "evidence_bundle", bundle)


def _promote_evidence(run_id: str, bundle: dict[str, Any]) -> dict[str, Any]:
    promote_fn = getattr(_orchestration_service, "promote_evidence", None)
    if callable(promote_fn):
        return promote_fn(run_id, bundle, source="search_ui")
    _write_evidence_bundle(run_id, bundle)
    _append_run_event(
        run_id,
        {
            "level": "INFO",
            "event": "SEARCH_PROMOTED",
            "run_id": run_id,
            "context": {"source": "search_ui"},
        },
    )
    return {"ok": True, "bundle": bundle}


def _reject_run_mutation(run_id: str, reason: str = "diff gate rejected") -> dict[str, Any]:
    reject_fn = getattr(_orchestration_service, "reject_run", None)
    if callable(reject_fn):
        result = reject_fn(run_id, reason=reason)
        if result.get("error") == "RUN_NOT_FOUND":
            raise HTTPException(status_code=404, detail=_error_detail("RUN_NOT_FOUND"))
        if not result.get("ok"):
            failure_reason = str(result.get("reason") or result.get("error") or "reject failed").strip() or "reject failed"
            raise HTTPException(
                status_code=422,
                detail={**_error_detail("REJECT_FAILED"), "reason": failure_reason},
            )
        return result

    run_dir = _runs_root() / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=_error_detail("RUN_NOT_FOUND"))
    manifest = _read_json(manifest_path, {})
    if isinstance(manifest, dict):
        manifest["status"] = "FAILURE"
        manifest["failure_reason"] = reason
        manifest["end_ts"] = manifest.get("end_ts") or datetime.now(timezone.utc).isoformat()
        _write_manifest(run_id, manifest)
    _append_run_event(
        run_id,
        {
            "level": "WARN",
            "event": "DIFF_GATE_REJECTED",
            "run_id": run_id,
            "context": {"reason": reason},
        },
    )
    return {"ok": True, "reason": reason}


def _approve_god_mode_mutation(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return routes_admin.approve_god_mode_mutation(
        run_id,
        payload,
        orchestration_service=_orchestration_service,
        append_run_event_fn=_append_run_event,
    )


def _current_request_id() -> str:
    request_id = _request_id_ctx.get().strip()
    return request_id or "unknown"


def _current_trace_id() -> str:
    trace_id = _trace_id_ctx.get().strip()
    return trace_id or ""


def _error_detail(code: str) -> dict[str, str]:
    return {"code": code, "request_id": _current_request_id(), "trace_id": _current_trace_id()}


def _trace_id_from_traceparent(value: str) -> str:
    parts = value.strip().split("-")
    if len(parts) != 4:
        return ""
    version, trace_id, _span_id, flags = parts
    if len(version) != 2 or len(trace_id) != 32 or len(flags) != 2:
        return ""
    if not all(ch in "0123456789abcdefABCDEF" for ch in trace_id):
        return ""
    return trace_id.lower()


@app.exception_handler(RequestValidationError)
async def _request_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = _error_detail("REQUEST_VALIDATION_ERROR")
    detail["reason"] = "request validation failed"
    return JSONResponse(status_code=422, content={"detail": detail})


@app.middleware("http")
async def _request_guard(request: Request, call_next):
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
        or uuid.uuid4().hex
    )
    traceparent = request.headers.get("traceparent", "").strip()
    trace_id = (
        request.headers.get("x-trace-id", "").strip()
        or _trace_id_from_traceparent(traceparent)
        or uuid.uuid4().hex
    )
    inbound_run_id = request.headers.get("x-cortexpilot-run-id", "").strip()
    token = _request_id_ctx.set(request_id)
    trace_token = _trace_id_ctx.set(trace_id)
    run_token = _run_id_ctx.set(inbound_run_id)
    started_at = time.perf_counter()
    lane = _resolve_request_lane(request, request_id)
    request.state.cortexpilot_lane = lane
    try:
        path = request.url.path
        cfg = load_config()
        request.state.cortexpilot_api_auth_required = bool(cfg.api_auth_required)
        request.state.cortexpilot_api_auth_verified = False
        request.state.cortexpilot_api_auth_source = "none"
        is_health_path = path in {"/health", "/api/health"}
        if path.startswith("/api/") and request.method != "OPTIONS" and not is_health_path and cfg.api_auth_required:
            if not cfg.api_token:
                return JSONResponse(status_code=503, content={"detail": _error_detail("API_TOKEN_NOT_CONFIGURED")})

            provided_token = ""
            auth_source = "none"
            try:
                credentials = await _bearer(request)
                provided_token = credentials.credentials
                auth_source = "bearer"
            except HTTPException:
                provided_token = ""

            if not provided_token:
                cookie_token = request.cookies.get("cortexpilot_api_token", "").strip() or request.cookies.get(
                    "api_token", ""
                ).strip()
                if cookie_token:
                    provided_token = cookie_token
                    auth_source = "cookie"

            if not provided_token:
                return JSONResponse(status_code=401, content={"detail": _error_detail("AUTH_MISSING_BEARER")})
            if not hmac.compare_digest(provided_token, cfg.api_token):
                return JSONResponse(status_code=401, content={"detail": _error_detail("AUTH_INVALID_TOKEN")})
            request.state.cortexpilot_api_auth_verified = True
            request.state.cortexpilot_api_auth_source = auth_source
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        log_event(
            "INFO",
            "api",
            "HTTP_ACCESS",
            meta={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_lane": lane,
                "header_run_id": inbound_run_id,
            },
            request_id=request_id,
            trace_id=trace_id,
            run_id=inbound_run_id,
            domain="api",
            surface="backend",
            artifact_kind="http_access",
        )
        response.headers["x-request-id"] = request_id
        response.headers["x-trace-id"] = trace_id
        if traceparent:
            response.headers["traceparent"] = traceparent
        if inbound_run_id:
            response.headers["x-cortexpilot-run-id"] = inbound_run_id
        response.headers["x-cortexpilot-lane"] = lane
        return response
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        log_event(
            "ERROR",
            "api",
            "UNHANDLED_EXCEPTION",
            meta={
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "duration_ms": duration_ms,
                "error": str(exc),
                "request_lane": lane,
                "header_run_id": inbound_run_id,
            },
            request_id=request_id,
            trace_id=trace_id,
            run_id=inbound_run_id,
            domain="api",
            surface="backend",
            artifact_kind="http_failure",
        )
        return JSONResponse(status_code=500, content={"detail": _error_detail("INTERNAL_SERVER_ERROR")})
    finally:
        _request_id_ctx.reset(token)
        _trace_id_ctx.reset(trace_token)
        _run_id_ctx.reset(run_token)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


def _runs_root() -> Path:
    return load_config().runs_root


def _repo_root() -> Path:
    return load_config().repo_root.resolve()


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _load_agent_registry() -> dict:
    path = resolve_agent_registry_path(_repo_root())
    payload = _read_json(path, {"version": "v1", "agents": []})
    return payload if isinstance(payload, dict) else {"version": "v1", "agents": []}


def _load_command_allowlist() -> dict:
    path = _repo_root() / "policies" / "command_allowlist.json"
    payload = _read_json(path, {"version": "v1", "allow": [], "deny_substrings": []})
    return payload if isinstance(payload, dict) else {"version": "v1", "allow": [], "deny_substrings": []}


def _load_forbidden_actions() -> dict:
    path = _repo_root() / "policies" / "forbidden_actions.json"
    payload = _read_json(path, {"version": "v1", "forbidden_actions": []})
    return payload if isinstance(payload, dict) else {"version": "v1", "forbidden_actions": []}


def _load_tool_registry() -> dict:
    path = _repo_root() / "tooling" / "registry.json"
    payload = _read_json(path, {"installed": [], "integrated": []})
    return payload if isinstance(payload, dict) else {"installed": [], "integrated": []}


def _load_contract(run_id: str) -> dict:
    contract_path = _runs_root() / run_id / "contract.json"
    payload = _read_json(contract_path, {})
    return payload if isinstance(payload, dict) else {}


def _load_locks() -> list[dict]:
    return main_state_store_helpers.load_locks(
        runtime_root=load_config().runtime_root,
        load_contract_fn=_load_contract,
    )


def _load_worktrees() -> list[dict]:
    return main_state_store_helpers.load_worktrees(
        list_worktrees_lines_fn=worktree_manager.list_worktrees,
        worktree_root=load_config().worktree_root.resolve(),
    )


def _parse_iso_ts(value: str) -> datetime:
    return event_cursor.parse_iso_ts(value)


def _select_baseline_by_window(run_id: str, window: dict) -> str | None:
    return main_state_store_helpers.select_baseline_by_window(
        run_id=run_id,
        window=window,
        runs_root=_runs_root(),
        parse_iso_ts_fn=_parse_iso_ts,
    )


def _read_events(run_id: str) -> list[dict]:
    return main_state_store_helpers.read_events(run_id=run_id, runs_root=_runs_root())


def _read_events_incremental(
    run_id: str,
    *,
    offset: int = 0,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
) -> tuple[list[dict], int]:
    return main_state_store_helpers.read_events_incremental(
        run_id=run_id,
        runs_root=_runs_root(),
        offset=offset,
        since=since,
        limit=limit,
        tail=tail,
        filter_events_fn=_filter_events,
    )


def _event_cursor_value(event: dict[str, Any]) -> str:
    return event_cursor.event_cursor_value(event)


def _is_event_after_cursor(event: dict[str, Any], since: str) -> bool:
    return event_cursor.is_event_after_cursor(event, since)


def _filter_events(
    events: list[dict],
    *,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
) -> list[dict]:
    return event_cursor.filter_events(events, since=since, limit=limit, tail=tail)


def _read_artifact_file(run_id: str, name: str) -> object | None:
    return artifact_helpers.read_artifact_file(
        run_id,
        name,
        runs_root=_runs_root(),
        error_detail_fn=_error_detail,
    )


def _read_report_file(run_id: str, name: str) -> object | None:
    return artifact_helpers.read_report_file(run_id, name, runs_root=_runs_root())


def _safe_artifact_target(run_id: str, name: str) -> Path:
    return artifact_helpers.safe_artifact_target(
        run_id,
        name,
        runs_root=_runs_root(),
        error_detail_fn=_error_detail,
    )


def _extract_search_queries(contract: dict) -> list[str]:
    return search_payload_helpers.extract_search_queries(contract)


def _derive_stage(events: list[dict], manifest: dict) -> str:
    return run_state_helpers.derive_stage(events, manifest)

def _last_event_ts(run_id: str) -> str:
    return run_state_helpers.last_event_ts(run_id, runs_root=_runs_root())


def _read_manifest_status(run_id: str) -> str:
    manifest = _read_json(_runs_root() / run_id / "manifest.json", default={})
    if not isinstance(manifest, dict):
        return "UNKNOWN"
    return str(manifest.get("status") or "UNKNOWN")


def _collect_workflows() -> dict[str, dict]:
    return main_state_store_helpers.collect_workflows(
        runs_root=_runs_root(),
        runtime_root=load_config().runtime_root,
        read_events_fn=_read_events,
    )


def _rollback_run_handler(run_id: str) -> dict:
    result = _rollback_service.apply(run_id)
    if result.get("error_code") == "RUN_NOT_FOUND":
        raise HTTPException(status_code=404, detail=_error_detail("RUN_NOT_FOUND"))
    if not result.get("ok"):
        reason = str(result.get("reason") or result.get("error") or "rollback failed").strip() or "rollback failed"
        raise HTTPException(
            status_code=422,
            detail={**_error_detail("ROLLBACK_FAILED"), "reason": reason},
        )
    return result


def list_pending_approvals() -> list[dict]:
    return routes_admin.collect_pending_approvals(
        runs_root=_runs_root(),
        read_events_fn=_read_events,
    )


_runs_handler_map = main_runs_handlers.build_runs_handlers(
    runs_root_fn=_runs_root,
    load_contract_fn=_load_contract,
    parse_iso_ts_fn=_parse_iso_ts,
    select_baseline_by_window_fn=lambda run_id, window: _select_baseline_by_window(run_id, window),
    last_event_ts_fn=_last_event_ts,
    collect_workflows_fn=_collect_workflows,
    queue_store_cls=QueueStore,
    read_events_fn=_read_events,
    filter_events_fn=_filter_events,
    event_cursor_value_fn=_event_cursor_value,
    safe_artifact_target_fn=_safe_artifact_target,
    read_artifact_fn=_read_artifact_file,
    read_report_fn=_read_report_file,
    extract_search_queries_fn=_extract_search_queries,
    list_pending_approvals_fn=list_pending_approvals,
    promote_evidence_fn=_promote_evidence,
    orchestration_service_fn=lambda: _orchestration_service,
    load_config_fn=load_config,
    error_detail_fn=_error_detail,
    current_request_id_fn=_current_request_id,
    log_event_fn=log_event,
    json_loads_fn=lambda raw: json.loads(raw),
    json_decode_error_cls=json.JSONDecodeError,
    list_diff_gate_fn=lambda: main_run_views_helpers.list_diff_gate(
        runs_root=_runs_root(),
        read_events_fn=_read_events,
        read_json_fn=_read_json,
    ),
    rollback_run_fn=_rollback_run_handler,
    reject_run_fn=lambda run_id: _reject_run_mutation(run_id),
    list_reviews_fn=lambda: main_run_views_helpers.list_reports_by_name(
        runs_root=_runs_root(),
        report_name="review_report.json",
    ),
    list_tests_fn=lambda: main_run_views_helpers.list_reports_by_name(
        runs_root=_runs_root(),
        report_name="test_report.json",
    ),
    list_agents_fn=lambda: main_run_views_helpers.list_agents(
        load_agent_registry_fn=_load_agent_registry,
        load_locks_fn=_load_locks,
        build_role_binding_summary_fn=build_role_binding_summary,
    ),
    list_agents_status_fn=lambda run_id=None: main_run_views_helpers.list_agents_status(
        run_id=run_id,
        runs_root=_runs_root(),
        load_worktrees_fn=_load_worktrees,
        load_locks_fn=_load_locks,
        load_contract_fn=_load_contract,
        read_events_fn=_read_events,
        derive_stage_fn=_derive_stage,
    ),
    list_policies_fn=lambda: main_run_views_helpers.list_policies(
        load_agent_registry_fn=_load_agent_registry,
        load_command_allowlist_fn=_load_command_allowlist,
        load_forbidden_actions_fn=_load_forbidden_actions,
        load_tool_registry_fn=_load_tool_registry,
    ),
    list_locks_fn=lambda: main_run_views_helpers.list_locks(load_locks_fn=_load_locks),
    list_worktrees_fn=lambda: main_run_views_helpers.list_worktrees(load_worktrees_fn=_load_worktrees),
    read_manifest_status_fn=_read_manifest_status,
    read_events_incremental_fn=_read_events_incremental,
)

# Explicit symbol export for test shims and direct-call compatibility.
list_runs = _runs_handler_map["list_runs"]
list_queue = _runs_handler_map["list_queue"]
preview_enqueue_run_queue = _runs_handler_map["preview_enqueue_run_queue"]
enqueue_run_queue = _runs_handler_map["enqueue_run_queue"]
cancel_queue_item = _runs_handler_map["cancel_queue_item"]
run_next_queue = _runs_handler_map["run_next_queue"]
list_workflows = _runs_handler_map["list_workflows"]
get_workflow = _runs_handler_map["get_workflow"]
get_run = _runs_handler_map["get_run"]
get_events = _runs_handler_map["get_events"]
stream_events = _runs_handler_map["stream_events"]
get_diff = _runs_handler_map["get_diff"]
get_reports = _runs_handler_map["get_reports"]
get_artifacts = _runs_handler_map["get_artifacts"]
get_search = _runs_handler_map["get_search"]
get_operator_copilot_brief = _runs_handler_map["get_operator_copilot_brief"]
get_workflow_operator_copilot_brief = _runs_handler_map["get_workflow_operator_copilot_brief"]
promote_evidence = _runs_handler_map["promote_evidence"]
replay_run = _runs_handler_map["replay_run"]
verify_run = _runs_handler_map["verify_run"]
reexec_run = _runs_handler_map["reexec_run"]
list_contracts = _runs_handler_map["list_contracts"]
list_events = _runs_handler_map["list_events"]
list_diff_gate = _runs_handler_map["list_diff_gate"]
rollback_run = _runs_handler_map["rollback_run"]
reject_run = _runs_handler_map["reject_run"]
list_reviews = _runs_handler_map["list_reviews"]
list_tests = _runs_handler_map["list_tests"]
list_agents = _runs_handler_map["list_agents"]
list_agents_status = _runs_handler_map["list_agents_status"]
get_role_config = _runs_handler_map["get_role_config"]
preview_role_config = _runs_handler_map["preview_role_config"]
apply_role_config = _runs_handler_map["apply_role_config"]
list_policies = _runs_handler_map["list_policies"]
list_locks = _runs_handler_map["list_locks"]
list_worktrees = _runs_handler_map["list_worktrees"]

_runs_route_deps = api_deps.build_runs_route_deps_from_mapping(_runs_handler_map)
api_deps.configure_runs_route_deps_provider(lambda: _runs_route_deps)

_admin_handler_map = {
    "list_pending_approvals": lambda: list_pending_approvals(),
    "approve_god_mode_mutation": lambda run_id, payload: _approve_god_mode_mutation(run_id, payload),
    "get_run_events": lambda run_id: _read_events(run_id),
}
_admin_route_deps = api_deps.build_admin_route_deps_from_mapping(_admin_handler_map)
api_deps.configure_admin_route_deps_provider(lambda: _admin_route_deps)


list_intakes = main_pm_intake_helpers.list_intakes
list_pm_sessions = main_pm_intake_helpers.list_pm_sessions
get_pm_session = main_pm_intake_helpers.get_pm_session
get_pm_session_events = main_pm_intake_helpers.get_pm_session_events
get_pm_session_conversation_graph = main_pm_intake_helpers.get_pm_session_conversation_graph
get_pm_session_metrics = main_pm_intake_helpers.get_pm_session_metrics
get_command_tower_overview = main_pm_intake_helpers.get_command_tower_overview
get_command_tower_alerts = main_pm_intake_helpers.get_command_tower_alerts

def post_pm_session_message(pm_session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return main_pm_intake_helpers.post_pm_session_message(pm_session_id, payload, error_detail_fn=_error_detail, ensure_pm_session_fn=get_pm_session)


app.state.routes_runs_handlers = _runs_handler_map
app.include_router(routes_runs.router)

app.state.routes_admin_handlers = _admin_handler_map
app.include_router(routes_admin.router)


main_pm_intake_helpers.configure_pm_session_aggregation(
    runs_root_fn=_runs_root,
    runtime_root_fn=lambda: load_config().runtime_root,
    read_json_fn=_read_json,
    load_contract_fn=_load_contract,
    read_events_fn=_read_events,
    last_event_ts_fn=_last_event_ts,
    filter_events_fn=_filter_events,
    event_cursor_fn=_event_cursor_value,
    parse_iso_fn=_parse_iso_ts,
    error_detail_fn=_error_detail,
)

def get_intake(intake_id: str) -> dict:
    return main_pm_intake_helpers.get_intake(intake_id, error_detail_fn=_error_detail)


def list_task_packs() -> list[dict]:
    return IntakeService().list_task_packs()


def create_intake(payload: dict) -> dict:
    return main_pm_intake_helpers.create_intake(payload, intake_service_cls=IntakeService, error_detail_fn=_error_detail, current_request_id_fn=_current_request_id)


def preview_intake(payload: dict) -> dict:
    return main_pm_intake_helpers.preview_intake(
        payload,
        intake_service_cls=IntakeService,
        error_detail_fn=_error_detail,
        current_request_id_fn=_current_request_id,
    )


def preview_intake_copilot_brief(payload: dict) -> dict:
    return main_pm_intake_helpers.preview_intake_copilot_brief(
        payload,
        error_detail_fn=_error_detail,
        current_request_id_fn=_current_request_id,
    )


def answer_intake(intake_id: str, payload: dict) -> dict:
    return main_pm_intake_helpers.answer_intake(intake_id, payload, intake_service_cls=IntakeService, error_detail_fn=_error_detail, current_request_id_fn=_current_request_id)


def run_intake(intake_id: str, payload: dict | None = None) -> dict:
    return main_pm_intake_helpers.run_intake(intake_id, payload, intake_service_cls=IntakeService, orchestration_service=_orchestration_service, error_detail_fn=_error_detail, current_request_id_fn=_current_request_id)


main_pm_intake_helpers.configure_routes(
    app=app,
    list_pm_sessions_accessor=lambda: list_pm_sessions,
    get_pm_session_accessor=lambda: get_pm_session,
    get_pm_session_events_accessor=lambda: get_pm_session_events,
    get_pm_session_graph_accessor=lambda: get_pm_session_conversation_graph,
    get_pm_session_metrics_accessor=lambda: get_pm_session_metrics,
    post_pm_session_message_accessor=lambda: post_pm_session_message,
    get_command_tower_overview_accessor=lambda: get_command_tower_overview,
    get_command_tower_alerts_accessor=lambda: get_command_tower_alerts,
    list_intakes_accessor=lambda: list_intakes,
    list_task_packs_accessor=lambda: list_task_packs,
    get_intake_accessor=lambda: get_intake,
    create_intake_accessor=lambda: create_intake,
    preview_intake_accessor=lambda: preview_intake,
    preview_intake_copilot_brief_accessor=lambda: preview_intake_copilot_brief,
    answer_intake_accessor=lambda: answer_intake,
    run_intake_accessor=lambda: run_intake,
)
app.include_router(routes_pm.router)
app.include_router(routes_intake.router)


def approve_god_mode(payload: dict) -> dict:
    return routes_admin.approve_god_mode(payload)
