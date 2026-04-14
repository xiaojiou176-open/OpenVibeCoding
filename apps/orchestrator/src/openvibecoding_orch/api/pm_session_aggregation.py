from __future__ import annotations

import copy
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from fastapi import HTTPException, Request

from openvibecoding_orch.api.pm_session_aggregation_alerts import (
    build_command_tower_alerts,
    command_tower_ratios,
    compute_failure_trend_30m,
)
from openvibecoding_orch.api.pm_session_aggregation_context import (
    resolve_pm_session_context as resolve_pm_session_context_payload,
)
from openvibecoding_orch.api.pm_session_aggregation_filters import (
    collect_pm_session_events,
    normalize_event_types,
    normalize_run_ids,
    normalize_status_filters,
)
from openvibecoding_orch.api.pm_session_aggregation_graph import build_pm_session_graph
from openvibecoding_orch.api.pm_session_aggregation_views import (
    build_command_tower_overview as build_command_tower_overview_payload,
    list_pm_sessions_view,
)
from openvibecoding_orch.services.session_index_service import SessionIndexService


_logger = logging.getLogger(__name__)
_RunsRootFn = Callable[[], Path]
_RuntimeRootFn = Callable[[], Path]
_ReadJsonFn = Callable[[Path, object], object]
_LoadContractFn = Callable[[str], dict[str, Any]]
_ReadEventsFn = Callable[[str], list[dict[str, Any]]]
_LastEventTsFn = Callable[[str], str]
_FilterEventsFn = Callable[..., list[dict[str, Any]]]
_EventCursorFn = Callable[[dict[str, Any]], str]
_ParseIsoFn = Callable[[str], datetime]
_ErrorDetailFn = Callable[[str], dict[str, str]]

_runs_root_fn: _RunsRootFn | None = None
_runtime_root_fn: _RuntimeRootFn | None = None
_read_json_fn: _ReadJsonFn | None = None
_load_contract_fn: _LoadContractFn | None = None
_read_events_fn: _ReadEventsFn | None = None
_last_event_ts_fn: _LastEventTsFn | None = None
_filter_events_fn: _FilterEventsFn | None = None
_event_cursor_fn: _EventCursorFn | None = None
_parse_iso_fn: _ParseIsoFn | None = None
_error_detail_fn: _ErrorDetailFn | None = None

_PM_SESSION_STATUS_VALUES = {"active", "paused", "done", "failed", "archived"}
_PM_SESSION_RUNNING_STATUSES = {"RUNNING", "PENDING", "QUEUED", "IN_PROGRESS"}
_PM_SESSION_SUCCESS_STATUSES = {"SUCCESS", "DONE", "PASSED"}
_PM_SESSION_FAILED_STATUSES = {"FAILURE", "FAILED", "ERROR", "CANCELLED", "REJECTED"}
_PM_SESSION_WINDOWS = {
    "30m": timedelta(minutes=30),
    "2h": timedelta(hours=2),
    "24h": timedelta(hours=24),
}
_PM_SESSION_SORT_VALUES = {"updated_desc", "created_desc", "failed_desc", "blocked_desc"}
_COMMAND_TOWER_SLO_TARGETS = {
    "sessions_api_p95_ms": 450,
    "sessions_api_p99_ms": 900,
    "overview_api_p95_ms": 350,
    "event_ingest_lag_ms": 5000,
}
_OVERVIEW_CACHE_TTL_DEFAULT_SEC = 2.0
_OVERVIEW_CACHE_TTL_ENV = "OPENVIBECODING_COMMAND_TOWER_OVERVIEW_TTL_SEC"
_overview_cache_lock = Lock()
_overview_cache_entry: dict[str, Any] | None = None
_session_summaries_cache_lock = Lock()
_session_summaries_cache_entry: dict[str, Any] | None = None


def configure(
    *,
    runs_root_fn: _RunsRootFn,
    runtime_root_fn: _RuntimeRootFn,
    read_json_fn: _ReadJsonFn,
    load_contract_fn: _LoadContractFn,
    read_events_fn: _ReadEventsFn,
    last_event_ts_fn: _LastEventTsFn,
    filter_events_fn: _FilterEventsFn,
    event_cursor_fn: _EventCursorFn,
    parse_iso_fn: _ParseIsoFn,
    error_detail_fn: _ErrorDetailFn,
) -> None:
    global _runs_root_fn
    global _runtime_root_fn
    global _read_json_fn
    global _load_contract_fn
    global _read_events_fn
    global _last_event_ts_fn
    global _filter_events_fn
    global _event_cursor_fn
    global _parse_iso_fn
    global _error_detail_fn

    _runs_root_fn = runs_root_fn
    _runtime_root_fn = runtime_root_fn
    _read_json_fn = read_json_fn
    _load_contract_fn = load_contract_fn
    _read_events_fn = read_events_fn
    _last_event_ts_fn = last_event_ts_fn
    _filter_events_fn = filter_events_fn
    _event_cursor_fn = event_cursor_fn
    _parse_iso_fn = parse_iso_fn
    _error_detail_fn = error_detail_fn


def _require_callable(name: str, fn: Callable[..., Any] | None) -> Callable[..., Any]:
    if callable(fn):
        return fn
    raise RuntimeError(f"pm session aggregation not configured: {name}")


def _runs_root() -> Path:
    fn = _require_callable("runs_root_fn", _runs_root_fn)
    return fn()


def _runtime_root() -> Path:
    fn = _require_callable("runtime_root_fn", _runtime_root_fn)
    return fn()


def _read_json(path: Path, default: object) -> object:
    fn = _require_callable("read_json_fn", _read_json_fn)
    return fn(path, default)


def _load_contract(run_id: str) -> dict[str, Any]:
    fn = _require_callable("load_contract_fn", _load_contract_fn)
    payload = fn(run_id)
    return payload if isinstance(payload, dict) else {}


def _read_events(run_id: str) -> list[dict[str, Any]]:
    fn = _require_callable("read_events_fn", _read_events_fn)
    payload = fn(run_id)
    return payload if isinstance(payload, list) else []


def _last_event_ts(run_id: str) -> str:
    fn = _require_callable("last_event_ts_fn", _last_event_ts_fn)
    value = fn(run_id)
    return value if isinstance(value, str) else ""


def _filter_events(
    events: list[dict[str, Any]],
    *,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
) -> list[dict[str, Any]]:
    fn = _require_callable("filter_events_fn", _filter_events_fn)
    payload = fn(events, since=since, limit=limit, tail=tail)
    return payload if isinstance(payload, list) else []


def _event_cursor_value(event: dict[str, Any]) -> str:
    fn = _require_callable("event_cursor_fn", _event_cursor_fn)
    value = fn(event)
    return value if isinstance(value, str) else ""


def _parse_iso_ts(value: str) -> datetime:
    fn = _require_callable("parse_iso_fn", _parse_iso_fn)
    return fn(value)


def _error_detail(code: str) -> dict[str, str]:
    fn = _require_callable("error_detail_fn", _error_detail_fn)
    payload = fn(code)
    return payload if isinstance(payload, dict) else {"code": code}


def _session_index_service() -> SessionIndexService:
    return SessionIndexService(_runtime_root())


def _overview_cache_ttl_sec() -> float:
    raw = os.getenv(_OVERVIEW_CACHE_TTL_ENV, "").strip()
    if raw:
        try:
            parsed = float(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return _OVERVIEW_CACHE_TTL_DEFAULT_SEC


def _overview_scope_key() -> str:
    return str(_runtime_root())


def _summary_sort_ts(value: Any) -> float:
    parsed = _parse_ts_or_none(value)
    return float(parsed.timestamp()) if parsed else 0.0


def _build_overview_snapshot() -> dict[str, Any]:
    return build_command_tower_overview_payload(
        list_pm_session_ids_fn=_list_pm_session_ids,
        resolve_pm_session_context_fn=lambda session_id: _resolve_pm_session_context(
            session_id,
            strict=False,
            include_runs=False,
        ),
        parse_ts_or_none_fn=_parse_ts_or_none,
        compute_failure_trend_30m_fn=compute_failure_trend_30m,
        command_tower_ratios_fn=command_tower_ratios,
        failed_statuses=_PM_SESSION_FAILED_STATUSES,
        slo_targets=_COMMAND_TOWER_SLO_TARGETS,
    )


def _get_overview_snapshot() -> tuple[dict[str, Any], bool]:
    scope_key = _overview_scope_key()
    now = datetime.now(timezone.utc)

    global _overview_cache_entry
    with _overview_cache_lock:
        entry = _overview_cache_entry
        if (
            isinstance(entry, dict)
            and entry.get("scope_key") == scope_key
            and isinstance(entry.get("expires_at"), datetime)
            and entry["expires_at"] > now
            and isinstance(entry.get("payload"), dict)
        ):
            return copy.deepcopy(entry["payload"]), True

    payload = _build_overview_snapshot()
    ttl_sec = _overview_cache_ttl_sec()
    with _overview_cache_lock:
        _overview_cache_entry = {
            "scope_key": scope_key,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_sec),
            "payload": copy.deepcopy(payload),
        }
    return payload, False


def _overview_generated_from(cache_hit: bool) -> str:
    return "cache_snapshot" if cache_hit else "recomputed"


def _build_pm_session_summaries_snapshot() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for session_id in _list_pm_session_ids():
        context = _resolve_pm_session_context(
            session_id,
            strict=False,
            include_run_events=False,
            include_runs=False,
        )
        summary = context.get("summary") if isinstance(context, dict) else None
        if isinstance(summary, dict):
            enriched_summary = dict(summary)
            enriched_summary["_sort_updated_ts"] = _summary_sort_ts(
                enriched_summary.get("updated_at") or enriched_summary.get("created_at") or ""
            )
            enriched_summary["_sort_created_ts"] = _summary_sort_ts(enriched_summary.get("created_at") or "")
            sessions.append(enriched_summary)
    return sessions


def _get_pm_session_summaries_snapshot() -> tuple[list[dict[str, Any]], bool]:
    scope_key = _overview_scope_key()
    now = datetime.now(timezone.utc)

    global _session_summaries_cache_entry
    with _session_summaries_cache_lock:
        entry = _session_summaries_cache_entry
        if (
            isinstance(entry, dict)
            and entry.get("scope_key") == scope_key
            and isinstance(entry.get("expires_at"), datetime)
            and entry["expires_at"] > now
            and isinstance(entry.get("payload"), list)
        ):
            return list(entry["payload"]), True

    payload = _build_pm_session_summaries_snapshot()
    ttl_sec = _overview_cache_ttl_sec()
    with _session_summaries_cache_lock:
        _session_summaries_cache_entry = {
            "scope_key": scope_key,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_sec),
            "payload": list(payload),
        }
    return payload, False


def _list_pm_session_ids() -> list[str]:
    return _session_index_service().list_session_ids()


def _read_pm_session_files(pm_session_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    return _session_index_service().read_session_files(pm_session_id)


def _read_run_manifest(run_id: str) -> dict[str, Any]:
    payload = _read_json(_runs_root() / run_id / "manifest.json", {})
    return payload if isinstance(payload, dict) else {}


def _parse_ts_or_none(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_iso_ts(value)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("pm_session_aggregation: _parse_ts_or_none failed: %s", exc)
        return None


def _resolve_pm_session_context(
    pm_session_id: str,
    *,
    strict: bool = True,
    include_run_events: bool = True,
    include_runs: bool = True,
) -> dict[str, Any]:
    return resolve_pm_session_context_payload(
        pm_session_id,
        strict=strict,
        read_pm_session_files_fn=_read_pm_session_files,
        session_index_service_fn=_session_index_service,
        read_run_manifest_fn=_read_run_manifest,
        load_contract_fn=_load_contract,
        read_events_fn=_read_events,
        last_event_ts_fn=_last_event_ts,
        parse_iso_ts_fn=_parse_iso_ts,
        event_cursor_fn=_event_cursor_value,
        error_detail_fn=_error_detail,
        running_statuses=_PM_SESSION_RUNNING_STATUSES,
        success_statuses=_PM_SESSION_SUCCESS_STATUSES,
        failed_statuses=_PM_SESSION_FAILED_STATUSES,
        include_run_events=include_run_events,
        include_runs=include_runs,
    )


def list_pm_sessions(
    request: Request,
    status: str | None = None,
    status_filters: list[str] | None = None,
    owner_pm: str | None = None,
    project_key: str | None = None,
    sort: str = "updated_desc",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    session_summaries, _ = _get_pm_session_summaries_snapshot()
    return list_pm_sessions_view(
        request,
        status=status,
        status_filters=status_filters,
        owner_pm=owner_pm,
        project_key=project_key,
        sort=sort,
        limit=limit,
        offset=offset,
        status_values=_PM_SESSION_STATUS_VALUES,
        sort_values=_PM_SESSION_SORT_VALUES,
        normalize_status_filters_fn=normalize_status_filters,
        error_detail_fn=_error_detail,
        list_pm_session_ids_fn=_list_pm_session_ids,
        resolve_pm_session_context_fn=lambda session_id: _resolve_pm_session_context(
            session_id,
            strict=False,
            include_run_events=False,
            include_runs=False,
        ),
        parse_ts_or_none_fn=_parse_ts_or_none,
        session_summaries=session_summaries,
    )


def get_pm_session(pm_session_id: str) -> dict[str, Any]:
    context = _resolve_pm_session_context(pm_session_id)
    blockers = [
        {
            "run_id": item.get("run_id", ""),
            "task_id": item.get("task_id", ""),
            "status": item.get("status", ""),
            "current_role": item.get("current_role", ""),
            "current_step": item.get("current_step", ""),
        }
        for item in context["runs"]
        if bool(item.get("blocked"))
    ]
    return {
        "session": context["summary"],
        "run_ids": context["run_ids"],
        "runs": context["runs"],
        "bindings": context.get("bindings", []),
        "blockers": blockers,
    }


def get_pm_session_events(
    pm_session_id: str,
    request: Request,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
    event_types: list[str] | None = None,
    run_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    context = _resolve_pm_session_context(pm_session_id)
    normalized_event_types = normalize_event_types(request, event_types)
    normalized_run_ids = normalize_run_ids(request, run_ids)
    known_run_ids = set(context.get("run_ids", []))
    if normalized_run_ids and not normalized_run_ids.issubset(known_run_ids):
        raise HTTPException(status_code=400, detail=_error_detail("PM_SESSION_CURSOR_INVALID"))

    return collect_pm_session_events(
        context,
        event_cursor_fn=_event_cursor_value,
        filter_events_fn=_filter_events,
        event_types=normalized_event_types,
        run_ids=normalized_run_ids,
        since=since,
        limit=limit,
        tail=tail,
    )


def get_pm_session_conversation_graph(
    pm_session_id: str,
    window: str = "30m",
    group_by_role: bool = False,
) -> dict[str, Any]:
    context = _resolve_pm_session_context(pm_session_id)
    normalized_window = (window or "30m").strip().lower()
    return build_pm_session_graph(
        context,
        normalized_window,
        windows=_PM_SESSION_WINDOWS,
        collect_events_fn=lambda payload: collect_pm_session_events(
            payload,
            event_cursor_fn=_event_cursor_value,
            filter_events_fn=_filter_events,
        ),
        event_cursor_fn=_event_cursor_value,
        parse_ts_or_none_fn=_parse_ts_or_none,
        error_detail_fn=_error_detail,
        group_by_role=group_by_role,
    )


def get_pm_session_metrics(pm_session_id: str) -> dict[str, Any]:
    context = _resolve_pm_session_context(pm_session_id)
    return context["metrics"]


def get_command_tower_overview() -> dict[str, Any]:
    overview, cache_hit = _get_overview_snapshot()
    payload = copy.deepcopy(overview)
    payload["meta"] = {
        "cache_hit": cache_hit,
        "generated_from": _overview_generated_from(cache_hit),
    }
    return payload


def get_command_tower_alerts() -> dict[str, Any]:
    overview, overview_cache_hit = _get_overview_snapshot()
    alerts = build_command_tower_alerts(overview)
    status = "healthy"
    if any(item.get("severity") == "critical" for item in alerts):
        status = "critical"
    elif any(item.get("severity") == "warning" for item in alerts):
        status = "degraded"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "slo_targets": _COMMAND_TOWER_SLO_TARGETS,
        "alerts": alerts,
        "meta": {
            "overview_cache_hit": overview_cache_hit,
        },
    }
