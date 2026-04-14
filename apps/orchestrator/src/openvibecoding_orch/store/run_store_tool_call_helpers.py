from __future__ import annotations

from typing import Any

from .run_store_primitives import now_ts


def normalize_tool_call(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = dict(payload or {})
    entry.setdefault("ts", now_ts())
    entry.setdefault("run_id", run_id)
    tool = entry.get("tool")
    if not isinstance(tool, str) or not tool.strip():
        entry["tool"] = "unknown"
    status = entry.get("status")
    if not isinstance(status, str) or not status.strip():
        entry["status"] = "unknown"
    args = entry.get("args")
    if not isinstance(args, dict):
        entry["args"] = {}
    config = entry.get("config")
    if config is not None and not isinstance(config, dict):
        entry.pop("config", None)
    artifacts = entry.get("artifacts")
    if artifacts is not None and not isinstance(artifacts, dict):
        entry.pop("artifacts", None)
    duration = entry.get("duration_ms")
    if duration is not None and not isinstance(duration, int):
        entry.pop("duration_ms", None)
    error = entry.get("error")
    if error is not None and not isinstance(error, str):
        entry["error"] = str(error)
    for key in ("thread_id", "session_id", "task_id", "output_sha256"):
        if key in entry and not isinstance(entry.get(key), str):
            entry[key] = str(entry.get(key))
    return entry


def tool_call_fallback(run_id: str, tool: str, error: str) -> dict[str, Any]:
    return {
        "ts": now_ts(),
        "run_id": run_id,
        "tool": tool or "unknown",
        "status": "error",
        "args": {},
        "error": f"schema_validation_failed: {error}",
    }
