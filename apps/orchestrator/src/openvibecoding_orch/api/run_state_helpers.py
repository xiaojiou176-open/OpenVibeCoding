from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any


_logger = logging.getLogger(__name__)


def derive_stage(events: list[dict[str, Any]], manifest: dict[str, Any]) -> str:
    status = str(manifest.get("status") or "").upper()
    if status == "FAILURE":
        return "FAILED"
    if status == "SUCCESS":
        return "DONE"
    has_required = any(ev.get("event") == "HUMAN_APPROVAL_REQUIRED" for ev in events)
    has_completed = any(ev.get("event") == "HUMAN_APPROVAL_COMPLETED" for ev in events)
    if has_required and not has_completed:
        return "WAITING_APPROVAL"
    if any(ev.get("event") in {"TEST_RESULT"} for ev in events):
        return "TESTING"
    if any(ev.get("event") in {"REVIEW_RESULT", "REVIEWER_GATE_RESULT"} for ev in events):
        return "REVIEW"
    if any(ev.get("event") in {"DIFF_GATE_RESULT", "DIFF_GATE_FAIL"} for ev in events):
        return "DIFF_GATE"
    if any(ev.get("event") in {"STEP_STARTED", "CODEX_CMD", "MCP_CALL"} for ev in events):
        return "EXECUTING"
    return "PENDING"


def last_event_ts(run_id: str, *, runs_root: Path) -> str:
    events_path = runs_root / run_id / "events.jsonl"
    if not events_path.exists():
        return ""
    last_line = ""
    try:
        with events_path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            offset = max(0, size - 8192)
            handle.seek(offset)
            chunk = handle.read().decode("utf-8", errors="ignore")
            lines = [line for line in chunk.splitlines() if line.strip()]
            if lines:
                last_line = lines[-1]
    except Exception as exc:  # noqa: BLE001
        _logger.debug("run_state_helpers: last_event_ts read failed for %s: %s", run_id, exc)
        return ""
    if not last_line:
        return ""
    try:
        payload = json.loads(last_line)
    except json.JSONDecodeError:
        return ""
    return str(payload.get("ts") or payload.get("_ts") or "")
