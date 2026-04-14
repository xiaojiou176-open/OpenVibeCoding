from __future__ import annotations

import json
import os
import time
from typing import Any

from openvibecoding_orch.store.run_store import RunStore


def requires_human_approval(
    *,
    requires_network: bool,
    filesystem_policy: str,
    network_policy: str,
    shell_policy: str,
) -> bool:
    env_flag = os.getenv("OPENVIBECODING_GOD_MODE_REQUIRED", "").strip().lower()
    if env_flag in {"1", "true", "yes"}:
        return True

    on_request_flag = os.getenv("OPENVIBECODING_GOD_MODE_ON_REQUEST", "").strip().lower()
    if on_request_flag not in {"1", "true", "yes"}:
        return filesystem_policy == "danger-full-access"

    if requires_network and network_policy == "on-request":
        return True
    if filesystem_policy == "danger-full-access":
        return True
    return shell_policy == "on-request"


def force_unlock_requested() -> bool:
    raw = os.getenv("OPENVIBECODING_FORCE_UNLOCK", "").strip().lower()
    return raw in {"1", "true", "yes"}


def auto_lock_cleanup_requested() -> bool:
    raw = os.getenv("OPENVIBECODING_LOCK_AUTO_CLEANUP", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    ttl_raw = os.getenv("OPENVIBECODING_LOCK_TTL_SEC", "").strip()
    if ttl_raw != "":
        return True
    default_raw = os.getenv("OPENVIBECODING_LOCK_TTL_SEC_DEFAULT", "").strip()
    return default_raw != ""


def god_mode_timeout_sec() -> int:
    timeout_raw = os.getenv("OPENVIBECODING_GOD_MODE_TIMEOUT_SEC", "0").strip()
    try:
        return int(timeout_raw)
    except ValueError:
        return 0


def await_human_approval(
    run_id: str,
    store: RunStore,
    reason: list[str] | None = None,
    actions: list[str] | None = None,
    verify_steps: list[str] | None = None,
    resume_step: str | None = None,
) -> bool:
    timeout_sec = god_mode_timeout_sec()
    context = {
        "timeout_sec": timeout_sec,
        "reason": reason or [],
        "actions": actions or [],
        "verify_steps": verify_steps or [],
        "resume_step": resume_step or "",
    }
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "HUMAN_APPROVAL_REQUIRED",
            "run_id": run_id,
            "meta": context,
        },
    )

    if timeout_sec <= 0:
        return False

    start = time.monotonic()
    events_path = store.events_path(run_id)
    offset = 0
    while time.monotonic() - start <= timeout_sec:
        if not events_path.exists():
            time.sleep(1)
            continue
        with events_path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                offset = handle.tell()
                try:
                    payload: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = payload.get("event_type") or payload.get("event")
                if event_type == "HUMAN_APPROVAL_COMPLETED":
                    return True
        time.sleep(1)

    store.append_event(
        run_id,
        {
            "level": "ERROR",
            "event": "HUMAN_APPROVAL_TIMEOUT",
            "run_id": run_id,
            "meta": {"timeout_sec": timeout_sec},
        },
    )
    return False
