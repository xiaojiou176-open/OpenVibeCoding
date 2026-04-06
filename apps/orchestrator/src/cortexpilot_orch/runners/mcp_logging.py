from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from cortexpilot_orch.store.run_store import RunStore

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "key",
    "password",
    "credential",
    "auth",
    "private",
    "cert",
)
_SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._\-]{12,}\b", re.IGNORECASE),
    re.compile(r"([?&](?:access_token|token|key|secret|password|credential|auth|cert)=)[^&\s]+", re.IGNORECASE),
]


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sensitive_key(key: str) -> bool:
    token = str(key or "").strip().lower()
    return any(part in token for part in _SENSITIVE_KEY_PARTS)


def _redact_text(value: str) -> str:
    text = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def sanitize_agents_payload(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                sanitized[key_text] = _REDACTED
                continue
            sanitized[key_text] = sanitize_agents_payload(item, parent_key=key_text)
        return sanitized
    if isinstance(value, list):
        return [sanitize_agents_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_agents_payload(item, parent_key=parent_key) for item in value)
    if isinstance(value, str):
        if _is_sensitive_key(parent_key):
            return _REDACTED
        return _redact_text(value)
    return value


def sanitize_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_agents_payload(payload)
    if isinstance(sanitized, dict):
        return sanitized
    return {}


def _sanitize_agents_raw_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_tool_payload(payload)
    raw_prompt = payload.get("prompt")
    if isinstance(raw_prompt, str):
        sanitized["prompt"] = _REDACTED
        sanitized["prompt_meta"] = {
            "sha256": hashlib.sha256(raw_prompt.encode("utf-8")).hexdigest(),
            "chars": len(raw_prompt),
            "lines": raw_prompt.count("\n") + (1 if raw_prompt else 0),
        }
    elif "prompt" in sanitized:
        sanitized["prompt"] = _REDACTED
    return sanitized


def append_agents_transcript(store: RunStore, run_id: str, payload: dict[str, Any]) -> None:
    store.append_artifact_jsonl(run_id, "agents_transcript.jsonl", payload)


def append_agents_raw_event(
    store: RunStore,
    run_id: str,
    payload: dict[str, Any],
    task_id: str | None = None,
) -> None:
    payload.setdefault("ts", _now_ts())
    payload.setdefault("source", "agents_sdk")
    sanitized_payload = _sanitize_agents_raw_event_payload(payload)
    store.append_artifact_jsonl(run_id, "agents_raw_events.jsonl", sanitized_payload)
    if task_id:
        store.append_codex_event(run_id, task_id, json.dumps(sanitized_payload, ensure_ascii=False))
