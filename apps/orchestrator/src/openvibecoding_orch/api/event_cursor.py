from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any


_logger = logging.getLogger(__name__)


def parse_iso_ts(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def event_cursor_value(event: dict[str, Any]) -> str:
    ts = event.get("ts")
    if isinstance(ts, str) and ts.strip():
        return ts.strip()
    fallback = event.get("_ts")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return ""


def is_event_after_cursor(event: dict[str, Any], since: str) -> bool:
    cursor = event_cursor_value(event)
    if not cursor:
        return False
    try:
        return parse_iso_ts(cursor) > parse_iso_ts(since)
    except Exception as exc:  # noqa: BLE001
        _logger.debug("event_cursor: iso parse fallback to string compare: %s", exc)
        return cursor > since


def filter_events(
    events: list[dict[str, Any]],
    *,
    since: str | None = None,
    limit: int | None = None,
    tail: bool = False,
) -> list[dict[str, Any]]:
    filtered = events
    if isinstance(since, str) and since.strip():
        cursor = since.strip()
        filtered = [item for item in events if is_event_after_cursor(item, cursor)]

    if isinstance(limit, int) and limit > 0:
        if tail:
            return filtered[-limit:]
        return filtered[:limit]
    return filtered
