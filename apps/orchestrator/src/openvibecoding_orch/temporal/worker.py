from __future__ import annotations

import asyncio
import os


def _config() -> tuple[str, str, str]:
    address = os.getenv("OPENVIBECODING_TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.getenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "default")
    task_queue = os.getenv("OPENVIBECODING_TEMPORAL_TASK_QUEUE", "openvibecoding-orch")
    return address, namespace, task_queue


def run_worker() -> None:
    async def _run() -> None:
        from temporalio.client import Client  # type: ignore
        from temporalio.worker import Worker  # type: ignore
        from openvibecoding_orch.temporal.workflows import OpenVibeCodingRunWorkflow, run_contract_activity

        address, namespace, task_queue = _config()
        client = await Client.connect(address, namespace=namespace)
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[OpenVibeCodingRunWorkflow],
            activities=[run_contract_activity],
        )
        await worker.run()

    asyncio.run(_run())
