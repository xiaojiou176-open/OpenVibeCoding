from __future__ import annotations

import json
from typing import Any


def _safe_json_value(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:  # noqa: BLE001
        return str(value)


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


def _extract_structured_content(snapshot: dict[str, Any]) -> Any | None:
    return _extract_first(snapshot, ("structuredContent", "structured_content", "structured_content"), 0, 6)


def _is_tool_call_dict(payload: dict[str, Any]) -> bool:
    payload_type = payload.get("type")
    if isinstance(payload_type, str) and payload_type.lower() in {
        "tool_call",
        "tool_call_item",
        "function_call",
    }:
        return True
    if any(key in payload for key in ("call_id", "tool_call_id")):
        return True
    has_tool_name = any(key in payload for key in ("tool_name", "tool", "name"))
    has_arguments = any(key in payload for key in ("arguments", "args", "input", "command", "cmd"))
    return has_tool_name and has_arguments


def _contains_shell_request(payload: Any, in_tool_call: bool = False) -> bool:
    if isinstance(payload, dict):
        is_tool_call = in_tool_call or _is_tool_call_dict(payload)
        for key, value in payload.items():
            if is_tool_call and key in {"tool", "tool_name", "name", "type"} and isinstance(value, str):
                lowered = value.lower()
                if lowered in {"shell", "bash", "command_execution", "terminal", "command"}:
                    return True
            if is_tool_call and key in {"command", "cmd"} and isinstance(value, str) and value.strip():
                return True
        for key, value in payload.items():
            if key in {"final_output", "output", "output_text", "text", "content"} and not is_tool_call:
                continue
            if _contains_shell_request(value, is_tool_call):
                return True
        return False
    if isinstance(payload, list):
        return any(_contains_shell_request(item, in_tool_call) for item in payload)
    return False
