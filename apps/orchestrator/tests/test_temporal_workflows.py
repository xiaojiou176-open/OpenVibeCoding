import asyncio

import pytest

from cortexpilot_orch.temporal import workflows


def test_temporal_workflows_fallback_activity_raises() -> None:
    request = workflows.RunRequest(
        repo_root="/tmp/repo",
        contract_path="/tmp/repo/contract.json",
        mock_mode=True,
        workflow_id="wf-1",
    )

    if hasattr(workflows.CortexPilotRunWorkflow, "run"):
        pytest.skip("temporalio installed path covered elsewhere")

    with pytest.raises(RuntimeError, match="temporalio not installed"):
        asyncio.run(workflows.run_contract_activity(request))

    assert workflows.CortexPilotRunWorkflow is not None


def test_temporal_workflows_activity_and_workflow_paths(monkeypatch, tmp_path):
    if not (workflows.activity and workflows.workflow):
        pytest.skip("temporal workflow decorators unavailable")

    class _FakeOrchestrator:
        def __init__(self, repo_root):  # noqa: ANN001
            self.repo_root = repo_root

        def execute_task(self, contract_path, mock_mode: bool = False):  # noqa: ANN001
            return "run-from-activity"

    monkeypatch.setattr(workflows, "Orchestrator", _FakeOrchestrator)

    request = workflows.RunRequest(
        repo_root=str(tmp_path),
        contract_path=str(tmp_path / "contract.json"),
        mock_mode=True,
        workflow_id="wf-activity",
    )

    activity_result = asyncio.run(workflows.run_contract_activity(request))
    assert activity_result == {"run_id": "run-from-activity"}

    async def _fake_execute_activity(fn, req, start_to_close_timeout):  # noqa: ANN001
        return await fn(req)

    monkeypatch.setattr(workflows.workflow, "execute_activity", _fake_execute_activity)

    wf = workflows.CortexPilotRunWorkflow()
    workflow_result = asyncio.run(wf.run(request))
    assert workflow_result == {"run_id": "run-from-activity"}


def test_temporal_workflows_reload_activity_and_workflow_paths(monkeypatch, tmp_path) -> None:
    import importlib
    import os
    import sys
    import types

    from cortexpilot_orch.temporal import workflows as workflows_module

    class _FakeActivity:
        @staticmethod
        def defn(fn):  # noqa: ANN001
            return fn

    class _FakeWorkflow:
        captured: dict[str, int] = {}

        @staticmethod
        def defn(cls):  # noqa: ANN001
            return cls

        @staticmethod
        def run(fn):  # noqa: ANN001
            return fn

        @staticmethod
        async def execute_activity(fn, request, start_to_close_timeout):  # noqa: ANN001
            _FakeWorkflow.captured["timeout_sec"] = int(start_to_close_timeout.total_seconds())
            return await fn(request)

    fake_temporal = types.ModuleType("temporalio")
    fake_temporal.activity = _FakeActivity
    fake_temporal.workflow = _FakeWorkflow
    monkeypatch.setitem(sys.modules, "temporalio", fake_temporal)

    reloaded = importlib.reload(workflows_module)

    class _FakeOrchestrator:
        def __init__(self, repo_root):  # noqa: ANN001
            self.repo_root = repo_root

        def execute_task(self, contract_path, mock_mode):  # noqa: ANN001
            return "run_from_activity"

    monkeypatch.setattr(reloaded, "Orchestrator", _FakeOrchestrator)

    request = reloaded.RunRequest(
        repo_root=str(tmp_path / "repo"),
        contract_path=str(tmp_path / "repo" / "contract.json"),
        mock_mode=True,
        workflow_id="wf-activity",
    )

    monkeypatch.delenv("CORTEXPILOT_TEMPORAL_ACTIVITY", raising=False)
    monkeypatch.delenv("CORTEXPILOT_TEMPORAL_WORKFLOW", raising=False)
    monkeypatch.delenv("CORTEXPILOT_TEMPORAL_WORKFLOW_ID", raising=False)

    result = asyncio.run(reloaded.run_contract_activity(request))
    assert result["run_id"] == "run_from_activity"
    # Activity execution must not leak temporal flags to outer process env.
    assert "CORTEXPILOT_TEMPORAL_ACTIVITY" not in os.environ
    assert "CORTEXPILOT_TEMPORAL_WORKFLOW" not in os.environ
    assert "CORTEXPILOT_TEMPORAL_WORKFLOW_ID" not in os.environ

    monkeypatch.setenv("CORTEXPILOT_TEMPORAL_ACTIVITY_TIMEOUT", "10")
    workflow_result = asyncio.run(reloaded.CortexPilotRunWorkflow().run(request))
    assert workflow_result["run_id"] == "run_from_activity"
    assert _FakeWorkflow.captured["timeout_sec"] == 60
