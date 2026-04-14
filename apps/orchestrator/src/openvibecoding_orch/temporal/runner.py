from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

from openvibecoding_orch.temporal.manager import temporal_required


def _enabled() -> bool:
    return os.getenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "").strip().lower() in {"1", "true", "yes"}


def _config() -> tuple[str, str, str]:
    address = os.getenv("OPENVIBECODING_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.getenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "default")
    task_queue = os.getenv("OPENVIBECODING_TEMPORAL_TASK_QUEUE", "openvibecoding-orch")
    return address, namespace, task_queue


def _workflow_id(task_id: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    base = task_id or "openvibecoding"
    return f"openvibecoding-{base}-{suffix}"


def run_workflow(repo_root: Path, contract_path: Path, mock_mode: bool) -> dict[str, Any]:
    if not _enabled():
        raise RuntimeError("temporal workflow disabled")

    try:
        from temporalio.client import Client  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"temporalio not installed: {exc}") from exc

    from openvibecoding_orch.temporal.workflows import OpenVibeCodingRunWorkflow, RunRequest

    async def _run() -> dict[str, Any]:
        address, namespace, task_queue = _config()
        client = await Client.connect(address, namespace=namespace)
        workflow_id = _workflow_id(contract_path.stem)
        request = RunRequest(
            repo_root=str(repo_root),
            contract_path=str(contract_path),
            mock_mode=mock_mode,
            workflow_id=workflow_id,
        )
        try:
            handle = await client.start_workflow(
                OpenVibeCodingRunWorkflow.run,  # type: ignore[arg-type]
                request,
                id=workflow_id,
                task_queue=task_queue,
            )
        except TypeError:
            # Compatibility for client stubs or older signatures using `_id`.
            handle = await client.start_workflow(
                OpenVibeCodingRunWorkflow.run,  # type: ignore[arg-type]
                request,
                _id=workflow_id,
                task_queue=task_queue,
            )
        result = await handle.result()
        if not isinstance(result, dict) or not result.get("run_id"):
            raise RuntimeError("temporal workflow missing run_id")
        return {
            "ok": True,
            "workflow_id": workflow_id,
            "run_id": result["run_id"],
            "task_queue": task_queue,
            "namespace": namespace,
        }

    return asyncio.run(_run())


def temporal_required_or_raise(error: str) -> dict[str, Any]:
    if temporal_required():
        raise RuntimeError(error)
    return {"ok": False, "error": error}
