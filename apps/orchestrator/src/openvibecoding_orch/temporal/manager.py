from __future__ import annotations

import asyncio
import os
from typing import Any


def _enabled() -> bool:
    if os.getenv("OPENVIBECODING_TEMPORAL_ACTIVITY", "").strip() in {"1", "true", "yes"}:
        return False
    return os.getenv("OPENVIBECODING_TEMPORAL_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _required() -> bool:
    return os.getenv("OPENVIBECODING_TEMPORAL_REQUIRED", "").strip().lower() in {"1", "true", "yes"}


def _config() -> tuple[str, str]:
    address = os.getenv("OPENVIBECODING_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.getenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "default")
    return address, namespace


def notify_run_started(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not _enabled():
        return {"ok": True, "skipped": True, "run_id": run_id}
    address, namespace = _config()
    try:
        from temporalio.client import Client  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"temporalio not installed: {exc}", "run_id": run_id}
    try:
        client = asyncio.run(Client.connect(address, namespace=namespace))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "run_id": run_id}
    return {
        "ok": True,
        "run_id": run_id,
        "address": address,
        "namespace": namespace,
        "client": str(client),
    }


def notify_run_completed(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not _enabled():
        return {"ok": True, "skipped": True, "run_id": run_id}
    address, namespace = _config()
    try:
        from temporalio.client import Client  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"temporalio not installed: {exc}", "run_id": run_id}
    try:
        client = asyncio.run(Client.connect(address, namespace=namespace))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "run_id": run_id}
    return {
        "ok": True,
        "run_id": run_id,
        "address": address,
        "namespace": namespace,
        "client": str(client),
    }


def temporal_required() -> bool:
    return _required()
