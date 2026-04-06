from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from cortexpilot_orch.runners import mcp_logging
from cortexpilot_orch.store.run_store import RunStore


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_agents_transcript(store: RunStore, run_id: str, payload: dict[str, Any]) -> None:
    mcp_logging.append_agents_transcript(store, run_id, payload)


def append_agents_raw_event(
    store: RunStore,
    run_id: str,
    payload: dict[str, Any],
    task_id: str | None = None,
) -> None:
    mcp_logging.append_agents_raw_event(store, run_id, payload, task_id)


def sanitize_tool_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return mcp_logging.sanitize_tool_payload(payload)


def result_snapshot(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump()
        except Exception:  # noqa: BLE001
            return {}
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict()
        except Exception:  # noqa: BLE001
            return {}
    if hasattr(result, "__dict__"):
        return dict(result.__dict__)
    return {}


class TranscriptRecorder:
    def __init__(self, store: RunStore, run_id: str, task_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._task_id = task_id
        self._lines: list[str] = []

    def record(self, entry: dict[str, Any]) -> None:
        payload = dict(entry)
        payload.setdefault("ts", now_ts())
        append_agents_transcript(self._store, self._run_id, payload)
        text = payload.get("text") or payload.get("instruction") or payload.get("summary")
        if not isinstance(text, str) or not text.strip():
            text = json.dumps(payload, ensure_ascii=False)
        self._lines.append(f"[{payload['ts']}] {payload.get('kind', 'entry')}: {text}")

    def flush(self) -> None:
        if not self._lines:
            return
        self._store.write_codex_transcript(self._run_id, self._task_id, "\n".join(self._lines))
