from __future__ import annotations

import re
from typing import Any

from openvibecoding_orch.store.run_store import RunStore

_SENSITIVE_KEYWORDS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "credential",
    "auth",
    "private_key",
)
_TOKEN_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return any(token in normalized for token in _SENSITIVE_KEYWORDS)


def _redact_string(value: str) -> str:
    redacted = value
    for pattern in _TOKEN_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def sanitize_mcp_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = sanitize_mcp_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_mcp_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [sanitize_mcp_payload(item) for item in payload]
    if isinstance(payload, str):
        return _redact_string(payload)
    return payload


def record_mcp_call(run_id: str, tool_name: str, payload: dict) -> None:
    sanitized_payload = sanitize_mcp_payload(payload)
    store = RunStore()
    store.append_tool_call(run_id, {
        "tool": tool_name,
        "args": sanitized_payload,
        "status": "requested",
    })
    store.append_event(run_id, {
        "level": "INFO",
        "event": "MCP_CALL",
        "run_id": run_id,
        "task_id": "",
        "context": {"tool": tool_name, "payload": sanitized_payload},
    })
