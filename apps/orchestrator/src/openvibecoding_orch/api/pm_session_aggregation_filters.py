from __future__ import annotations

from typing import Any, Callable

from fastapi import Request


_EventCursorFn = Callable[[dict[str, Any]], str]
_FilterEventsFn = Callable[..., list[dict[str, Any]]]


def normalize_status_filters(
    request: Request,
    status: str | None,
    status_filters: list[str] | None = None,
) -> set[str]:
    values: list[str] = []
    if isinstance(status, str) and status.strip():
        values.append(status.strip())
    if isinstance(status_filters, list):
        values.extend(status_filters)
    values.extend(request.query_params.getlist("status[]"))
    values.extend(request.query_params.getlist("status"))
    normalized = {item.strip().lower() for item in values if isinstance(item, str) and item.strip()}
    return {item for item in normalized if item}


def normalize_event_types(request: Request, event_types: list[str] | None = None) -> set[str]:
    raw_types = list(request.query_params.getlist("types[]"))
    raw_types.extend(request.query_params.getlist("types"))
    if isinstance(event_types, list):
        raw_types.extend(event_types)
    return {item.strip().upper() for item in raw_types if isinstance(item, str) and item.strip()}


def normalize_run_ids(request: Request, run_ids: list[str] | None = None) -> set[str]:
    raw_run_ids = list(request.query_params.getlist("run_ids[]"))
    raw_run_ids.extend(request.query_params.getlist("run_ids"))
    if isinstance(run_ids, list):
        raw_run_ids.extend(run_ids)
    return {item.strip() for item in raw_run_ids if isinstance(item, str) and item.strip()}


def collect_pm_session_events(
    context: dict[str, Any],
    *,
    event_cursor_fn: _EventCursorFn,
    filter_events_fn: _FilterEventsFn,
    event_types: set[str] | None = None,
    run_ids: set[str] | None = None,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []

    if not run_ids:
        for event in context.get("intake_events", []):
            if not isinstance(event, dict):
                continue
            payload = dict(event)
            payload["_run_id"] = ""
            payload["_source"] = "session"
            merged.append(payload)

    for run_id in context.get("run_ids", []):
        if run_ids and run_id not in run_ids:
            continue
        run_events = context.get("events_by_run", {}).get(run_id, [])
        for event in run_events:
            if not isinstance(event, dict):
                continue
            payload = dict(event)
            payload["_run_id"] = run_id
            payload["_source"] = "run"
            merged.append(payload)

    merged.sort(key=event_cursor_fn)

    if event_types:
        merged = [
            item
            for item in merged
            if str(item.get("event") or item.get("event_type") or "").strip().upper() in event_types
        ]

    payload = filter_events_fn(merged, since=since, limit=limit, tail=tail)
    return payload if isinstance(payload, list) else []
