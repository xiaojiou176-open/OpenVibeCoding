from __future__ import annotations

import os
from typing import Any


def _extract_first(payload: Any, keys: tuple[str, ...], depth: int = 0, max_depth: int = 6) -> Any | None:
    if depth > max_depth:
        return None
    if isinstance(payload, dict):
        for key in keys:
            if key in payload:
                return payload.get(key)
        for value in payload.values():
            found = _extract_first(value, keys, depth + 1, max_depth)
            if found is not None:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _extract_first(item, keys, depth + 1, max_depth)
            if found is not None:
                return found
    return None


def summarize_mcp_stream_item(event: Any) -> dict[str, Any]:
    name = getattr(event, "name", None)
    item = getattr(event, "item", None)
    item_type = getattr(item, "type", None) or (item.__class__.__name__ if item else None)
    raw_item = getattr(item, "raw_item", None) if item is not None else None
    tool_name = _extract_first(raw_item, ("name", "tool_name", "function_name", "tool"))
    call_id = _extract_first(raw_item, ("call_id", "tool_call_id", "id"))
    return {
        "name": name,
        "item_type": item_type,
        "tool_name": tool_name,
        "call_id": call_id,
    }


def summarize_mcp_tool_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"status": "unknown"}
    if "Ok" in result:
        ok = result.get("Ok")
        content_len = 0
        if isinstance(ok, dict):
            content = ok.get("content")
            if isinstance(content, list):
                content_len = len(content)
            elif isinstance(content, str):
                content_len = len(content)
        return {"status": "ok", "content_len": content_len}
    if "Err" in result:
        err = result.get("Err")
        return {"status": "error", "error": str(err)[:200]}
    return {"status": "unknown"}


def resolve_stream_log_every() -> int:
    raw = os.getenv("OPENVIBECODING_STREAM_LOG_EVERY", "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0
