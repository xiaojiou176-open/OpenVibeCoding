from __future__ import annotations

import heapq
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException, Request


_ListPmSessionIdsFn = Callable[[], list[str]]
_ResolvePmSessionContextFn = Callable[[str], dict[str, Any]]
_ParseTsOrNoneFn = Callable[[Any], datetime | None]
_ErrorDetailFn = Callable[[str], dict[str, str]]
_NormalizeStatusFiltersFn = Callable[[Request, str | None, list[str] | None], set[str]]
_ComputeFailureTrend30mFn = Callable[..., int]
_CommandTowerRatiosFn = Callable[[int, int, int], tuple[float, float]]


def _pm_session_sort_value(
    item: dict[str, Any],
    sort: str,
    *,
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
) -> tuple[float, float]:
    normalized = sort.strip().lower()
    updated_ts_raw = item.get("_sort_updated_ts")
    created_ts_raw = item.get("_sort_created_ts")
    if isinstance(updated_ts_raw, (int, float)):
        updated_ts_value = float(updated_ts_raw)
    else:
        updated_ts = parse_ts_or_none_fn(item.get("updated_at") or item.get("created_at") or "")
        updated_ts_value = float(updated_ts.timestamp()) if updated_ts else 0.0

    if isinstance(created_ts_raw, (int, float)):
        created_ts_value = float(created_ts_raw)
    else:
        created_ts = parse_ts_or_none_fn(item.get("created_at") or "")
        created_ts_value = float(created_ts.timestamp()) if created_ts else 0.0

    if normalized == "created_desc":
        return (created_ts_value, updated_ts_value)
    if normalized == "failed_desc":
        return (float(item.get("failed_runs") or 0), updated_ts_value)
    if normalized == "blocked_desc":
        return (float(item.get("blocked_runs") or 0), updated_ts_value)
    return (updated_ts_value, created_ts_value)


def _public_summary_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"_sort_updated_ts", "_sort_created_ts"}
    }


def _collect_pm_session_summaries(
    *,
    list_pm_session_ids_fn: _ListPmSessionIdsFn,
    resolve_pm_session_context_fn: _ResolvePmSessionContextFn,
) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for session_id in list_pm_session_ids_fn():
        context = resolve_pm_session_context_fn(session_id)
        summary = context.get("summary") if isinstance(context, dict) else None
        if isinstance(summary, dict):
            sessions.append(summary)

    return sessions


def _select_ranked_page(
    sessions: list[dict[str, Any]],
    *,
    sort: str,
    offset: int,
    limit: int,
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
) -> list[dict[str, Any]]:
    if not sessions:
        return []

    ranked_key = lambda item: _pm_session_sort_value(item, sort, parse_ts_or_none_fn=parse_ts_or_none_fn)
    k = offset + limit
    if k <= 0:
        return []

    if k >= len(sessions):
        ranked = sorted(sessions, key=ranked_key, reverse=True)
    else:
        ranked = heapq.nlargest(k, sessions, key=ranked_key)
    return [_public_summary_payload(item) for item in ranked[offset: offset + limit]]


def list_pm_sessions_view(
    request: Request,
    *,
    status: str | None,
    status_filters: list[str] | None,
    owner_pm: str | None,
    project_key: str | None,
    sort: str,
    limit: int,
    offset: int,
    status_values: set[str],
    sort_values: set[str],
    normalize_status_filters_fn: _NormalizeStatusFiltersFn,
    error_detail_fn: _ErrorDetailFn,
    list_pm_session_ids_fn: _ListPmSessionIdsFn,
    resolve_pm_session_context_fn: _ResolvePmSessionContextFn,
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
    session_summaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    normalized_status_filters = normalize_status_filters_fn(request, status, status_filters)
    invalid_status = [item for item in normalized_status_filters if item not in status_values]
    if invalid_status:
        raise HTTPException(status_code=400, detail=error_detail_fn("PM_SESSION_STATUS_INVALID"))

    normalized_sort = (sort or "updated_desc").strip().lower()
    if normalized_sort not in sort_values:
        raise HTTPException(status_code=400, detail=error_detail_fn("PM_SESSION_SORT_INVALID"))

    if session_summaries is None:
        sessions = _collect_pm_session_summaries(
            list_pm_session_ids_fn=list_pm_session_ids_fn,
            resolve_pm_session_context_fn=resolve_pm_session_context_fn,
        )
    else:
        sessions = [item for item in session_summaries if isinstance(item, dict)]
    if normalized_status_filters:
        sessions = [
            item
            for item in sessions
            if str(item.get("status") or "").strip().lower() in normalized_status_filters
        ]

    normalized_owner = (owner_pm or "").strip()
    if normalized_owner:
        sessions = [item for item in sessions if str(item.get("owner_pm") or "").strip() == normalized_owner]

    normalized_project_key = (project_key or "").strip()
    if normalized_project_key:
        sessions = [item for item in sessions if str(item.get("project_key") or "").strip() == normalized_project_key]

    return _select_ranked_page(
        sessions,
        sort=normalized_sort,
        offset=offset,
        limit=limit,
        parse_ts_or_none_fn=parse_ts_or_none_fn,
    )


def build_command_tower_overview(
    *,
    list_pm_session_ids_fn: _ListPmSessionIdsFn,
    resolve_pm_session_context_fn: _ResolvePmSessionContextFn,
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
    compute_failure_trend_30m_fn: _ComputeFailureTrend30mFn,
    command_tower_ratios_fn: _CommandTowerRatiosFn,
    failed_statuses: set[str],
    slo_targets: dict[str, int],
) -> dict[str, Any]:
    session_ids = list_pm_session_ids_fn()
    contexts = [resolve_pm_session_context_fn(item) for item in session_ids]
    summaries = [item["summary"] for item in contexts if isinstance(item.get("summary"), dict)]

    total_sessions = len(summaries)
    active_sessions = sum(1 for item in summaries if str(item.get("status") or "") == "active")
    failed_sessions = sum(1 for item in summaries if str(item.get("status") or "") == "failed")
    blocked_sessions = sum(1 for item in summaries if int(item.get("blocked_runs") or 0) > 0)
    failure_trend_30m = compute_failure_trend_30m_fn(
        contexts,
        failed_statuses=failed_statuses,
        parse_ts_or_none_fn=parse_ts_or_none_fn,
    )
    failed_ratio, blocked_ratio = command_tower_ratios_fn(total_sessions, failed_sessions, blocked_sessions)

    top_blockers = heapq.nlargest(
        5,
        summaries,
        key=lambda item: (
            int(item.get("blocked_runs") or 0),
            int(item.get("running_runs") or 0),
            parse_ts_or_none_fn(item.get("updated_at") or item.get("created_at") or "")
            or datetime.fromtimestamp(0, tz=timezone.utc),
        ),
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "failed_sessions": failed_sessions,
        "blocked_sessions": blocked_sessions,
        "failed_ratio": failed_ratio,
        "blocked_ratio": blocked_ratio,
        "failure_trend_30m": failure_trend_30m,
        "slo_targets": slo_targets,
        "top_blockers": top_blockers,
    }
