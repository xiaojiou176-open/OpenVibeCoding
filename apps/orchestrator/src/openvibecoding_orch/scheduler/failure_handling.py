from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openvibecoding_orch.store.run_store import RunStore


def mark_failure(store: RunStore, run_id: str, reason: str, context: dict[str, Any] | None = None) -> None:
    manifest = store.read_manifest(run_id)
    manifest["status"] = "FAILURE"
    manifest["failure_reason"] = reason
    manifest["end_ts"] = datetime.now(timezone.utc).isoformat()
    store.write_manifest(run_id, manifest)
    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "TASK_FAILED",
            "run_id": run_id,
            "meta": {"reason": reason, **(context or {})},
        },
    )
