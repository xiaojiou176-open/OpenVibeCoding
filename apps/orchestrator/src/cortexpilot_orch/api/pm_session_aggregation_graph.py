from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException


_CollectEventsFn = Callable[[dict[str, Any]], list[dict[str, Any]]]
_EventCursorFn = Callable[[dict[str, Any]], str]
_ParseTsOrNoneFn = Callable[[Any], datetime | None]
_ErrorDetailFn = Callable[[str], dict[str, str]]


def _parse_window(
    window: str,
    *,
    windows: dict[str, timedelta],
    error_detail_fn: _ErrorDetailFn,
) -> timedelta:
    normalized = window.strip().lower()
    if normalized not in windows:
        raise HTTPException(status_code=400, detail=error_detail_fn("PM_SESSION_WINDOW_INVALID"))
    return windows[normalized]


def _extract_graph_roles(event: dict[str, Any]) -> tuple[str, str]:
    context = event.get("context") if isinstance(event.get("context"), dict) else {}
    from_role = ""
    to_role = ""

    for candidate in [context.get("from_role"), context.get("from"), context.get("role")]:
        if isinstance(candidate, str) and candidate.strip():
            from_role = candidate.strip()
            break

    for candidate in [context.get("to_role"), context.get("to"), context.get("next_role")]:
        if isinstance(candidate, str) and candidate.strip():
            to_role = candidate.strip()
            break

    return from_role, to_role


def build_pm_session_graph(
    context: dict[str, Any],
    window: str,
    *,
    windows: dict[str, timedelta],
    collect_events_fn: _CollectEventsFn,
    event_cursor_fn: _EventCursorFn,
    parse_ts_or_none_fn: _ParseTsOrNoneFn,
    error_detail_fn: _ErrorDetailFn,
    group_by_role: bool = False,
) -> dict[str, Any]:
    delta = _parse_window(window, windows=windows, error_detail_fn=error_detail_fn)
    now = datetime.now(timezone.utc)
    cutoff = now - delta

    nodes: set[str] = set()
    edges: list[dict[str, Any]] = []

    events = collect_events_fn(context)
    for index, event in enumerate(events):
        event_name = str(event.get("event") or event.get("event_type") or "").strip().upper()
        if event_name != "CHAIN_HANDOFF":
            continue
        ts = event_cursor_fn(event)
        dt = parse_ts_or_none_fn(ts)
        if dt is not None and dt < cutoff:
            continue

        from_role, to_role = _extract_graph_roles(event)
        if not from_role and not to_role:
            continue
        if from_role:
            nodes.add(from_role)
        if to_role:
            nodes.add(to_role)

        run_id = str(event.get("_run_id") or event.get("run_id") or "")
        edges.append(
            {
                "from_role": from_role,
                "to_role": to_role,
                "run_id": run_id,
                "ts": ts,
                "event_ref": f"{run_id}:{index}",
            }
        )

    if group_by_role:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for edge in edges:
            key = (str(edge.get("from_role") or ""), str(edge.get("to_role") or ""))
            slot = grouped.get(key)
            if slot is None:
                grouped[key] = {
                    "from_role": key[0],
                    "to_role": key[1],
                    "run_id": "*",
                    "ts": edge.get("ts", ""),
                    "event_ref": edge.get("event_ref", ""),
                    "count": 1,
                }
                continue
            slot["count"] = int(slot.get("count") or 0) + 1
            previous_ts = parse_ts_or_none_fn(slot.get("ts"))
            candidate_ts = parse_ts_or_none_fn(edge.get("ts"))
            if candidate_ts and (previous_ts is None or candidate_ts >= previous_ts):
                slot["ts"] = edge.get("ts", "")
                slot["event_ref"] = edge.get("event_ref", "")
        edges = list(grouped.values())

    return {
        "pm_session_id": context.get("pm_session_id", ""),
        "window": window,
        "group_by_role": group_by_role,
        "nodes": sorted(nodes),
        "edges": edges,
        "stats": {"node_count": len(nodes), "edge_count": len(edges)},
    }
