from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

try:
    from temporalio import activity, workflow  # type: ignore
except Exception:  # noqa: BLE001
    activity = None
    workflow = None

from openvibecoding_orch.scheduler.scheduler import Orchestrator


@contextmanager
def _isolated_temporal_env() -> Any:
    snapshot_temporal_activity = os.environ.get("OPENVIBECODING_TEMPORAL_ACTIVITY")
    snapshot_temporal_workflow = os.environ.get("OPENVIBECODING_TEMPORAL_WORKFLOW")
    snapshot_temporal_workflow_id = os.environ.get("OPENVIBECODING_TEMPORAL_WORKFLOW_ID")
    try:
        yield
    finally:
        if snapshot_temporal_activity is None:
            os.environ.pop("OPENVIBECODING_TEMPORAL_ACTIVITY", None)
        else:
            os.environ["OPENVIBECODING_TEMPORAL_ACTIVITY"] = snapshot_temporal_activity
        if snapshot_temporal_workflow is None:
            os.environ.pop("OPENVIBECODING_TEMPORAL_WORKFLOW", None)
        else:
            os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW"] = snapshot_temporal_workflow
        if snapshot_temporal_workflow_id is None:
            os.environ.pop("OPENVIBECODING_TEMPORAL_WORKFLOW_ID", None)
        else:
            os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW_ID"] = snapshot_temporal_workflow_id


@dataclass
class RunRequest:
    repo_root: str
    contract_path: str
    mock_mode: bool
    workflow_id: str


if activity and workflow:

    @activity.defn
    async def run_contract_activity(request: RunRequest) -> dict[str, Any]:
        with _isolated_temporal_env():
            os.environ["OPENVIBECODING_TEMPORAL_ACTIVITY"] = "1"
            os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW"] = "0"
            os.environ["OPENVIBECODING_TEMPORAL_WORKFLOW_ID"] = request.workflow_id
            orch = Orchestrator(Path(request.repo_root))
            run_id = orch.execute_task(Path(request.contract_path), mock_mode=request.mock_mode)
            return {"run_id": run_id}


    @workflow.defn
    class OpenVibeCodingRunWorkflow:
        @workflow.run
        async def run(self, request: RunRequest) -> dict[str, Any]:
            timeout_sec = int(os.getenv("OPENVIBECODING_TEMPORAL_ACTIVITY_TIMEOUT", "3600"))
            result = await workflow.execute_activity(
                run_contract_activity,
                request,
                start_to_close_timeout=timedelta(seconds=max(timeout_sec, 60)),
            )
            return result

else:

    async def run_contract_activity(request: RunRequest) -> dict[str, Any]:  # type: ignore[no-redef]
        raise RuntimeError("temporalio not installed")

    class OpenVibeCodingRunWorkflow:  # type: ignore[no-redef]
        pass
