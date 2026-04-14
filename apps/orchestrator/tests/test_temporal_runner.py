import os
import pytest
from pathlib import Path

from openvibecoding_orch.temporal.runner import run_workflow


def test_temporal_runner_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_WORKFLOW", raising=False)
    with pytest.raises(RuntimeError, match="temporal workflow disabled"):
        run_workflow(tmp_path, tmp_path / "contract.json", False)


def test_temporal_runner_missing_dependency(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "1")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "127.0.0.1:1")
    with pytest.raises(RuntimeError, match="temporalio not installed|Connection refused|Server connection error"):
        run_workflow(tmp_path, tmp_path / "contract.json", False)


def test_temporal_runner_helpers_and_required(monkeypatch) -> None:
    from openvibecoding_orch.temporal import runner as temporal_runner

    monkeypatch.delenv("OPENVIBECODING_TEMPORAL_WORKFLOW", raising=False)
    assert temporal_runner._enabled() is False

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "1")
    assert temporal_runner._enabled() is True

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "host:7233")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "ns")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_TASK_QUEUE", "q")
    assert temporal_runner._config() == ("host:7233", "ns", "q")

    workflow_id = temporal_runner._workflow_id("task")
    assert workflow_id.startswith("openvibecoding-task-")

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_REQUIRED", "1")
    with pytest.raises(RuntimeError, match="boom"):
        temporal_runner.temporal_required_or_raise("boom")

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_REQUIRED", "0")
    assert temporal_runner.temporal_required_or_raise("nope") == {"ok": False, "error": "nope"}


def test_temporal_runner_success_and_missing_run_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "1")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_ADDRESS", "127.0.0.1:7233")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_NAMESPACE", "default")
    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_TASK_QUEUE", "openvibecoding-orch")

    import sys
    import types

    class _FakeHandle:
        async def result(self):
            return {"run_id": "run-123"}

    class _FakeClient:
        @staticmethod
        async def connect(address: str, namespace: str):
            class _Connected:
                async def start_workflow(self, _run_fn, request, _id: str, task_queue: str):  # noqa: ANN001
                    return _FakeHandle()

            return _Connected()

    temporal_pkg = types.ModuleType("temporalio")
    temporal_client_mod = types.ModuleType("temporalio.client")
    temporal_client_mod.Client = _FakeClient
    monkeypatch.setitem(sys.modules, "temporalio", temporal_pkg)
    monkeypatch.setitem(sys.modules, "temporalio.client", temporal_client_mod)

    class _FakeRunRequest:
        def __init__(self, repo_root: str, contract_path: str, mock_mode: bool, workflow_id: str) -> None:
            self.repo_root = repo_root
            self.contract_path = contract_path
            self.mock_mode = mock_mode
            self.workflow_id = workflow_id

    class _FakeWorkflow:
        async def run(self, request):  # noqa: ANN001
            return {"run_id": "run-123"}

    workflow_mod = types.ModuleType("openvibecoding_orch.temporal.workflows")
    workflow_mod.RunRequest = _FakeRunRequest
    workflow_mod.OpenVibeCodingRunWorkflow = _FakeWorkflow
    monkeypatch.setitem(sys.modules, "openvibecoding_orch.temporal.workflows", workflow_mod)

    repo_root = tmp_path / "repo"
    contract_path = tmp_path / "contract.json"
    repo_root.mkdir(parents=True, exist_ok=True)
    contract_path.write_text("{}", encoding="utf-8")

    result = run_workflow(repo_root, contract_path, mock_mode=False)
    assert result["ok"] is True
    assert result["run_id"] == "run-123"

    class _MissingHandle:
        async def result(self):
            return {}

    class _ClientMissing:
        @staticmethod
        async def connect(address: str, namespace: str):
            class _Connected:
                async def start_workflow(self, _run_fn, request, _id: str, task_queue: str):  # noqa: ANN001
                    return _MissingHandle()

            return _Connected()

    temporal_client_mod.Client = _ClientMissing
    monkeypatch.setitem(sys.modules, "temporalio.client", temporal_client_mod)

    with pytest.raises(RuntimeError, match="missing run_id"):
        run_workflow(repo_root, contract_path, mock_mode=True)


def test_temporal_runner_forced_import_error(tmp_path: Path, monkeypatch) -> None:
    import builtins

    monkeypatch.setenv("OPENVIBECODING_TEMPORAL_WORKFLOW", "1")

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: ANN001
        if name == "temporalio.client":
            raise ImportError("forced temporal client missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    with pytest.raises(RuntimeError, match="temporalio not installed"):
        run_workflow(tmp_path, tmp_path / "contract.json", False)
