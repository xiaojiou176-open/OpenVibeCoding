from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from cortexpilot_orch.scheduler import scheduler_bridge_runtime as bridge_runtime
from cortexpilot_orch.store.run_store import RunStore


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def append_event(self, run_id: str, payload: dict[str, object]) -> None:
        self.events.append((run_id, payload))


def test_run_optional_tool_requests_search_browser_tamper_sampling_paths() -> None:
    store = _DummyStore()
    run_id = "run-1"
    agent = {"role": "PM"}

    def _never(*_args, **_kwargs):
        raise AssertionError("should not be called")

    failed_search = bridge_runtime.run_optional_tool_requests(
        run_id=run_id,
        store=store,
        tool_runner=object(),
        assigned_agent=agent,
        contract_browser_policy={"mode": "safe"},
        search_request={"queries": ["q"], "parallel": 2, "verify": True, "providers": ["chatgpt_web"]},
        browser_request={"tasks": [{"url": "https://example.com", "script": ""}]},
        tamper_request={"tasks": [{"script": "x"}]},
        sampling_request={"requests": [{"tool": "x"}]},
        run_search_pipeline_fn=lambda *_a, **_k: {"ok": False, "reason": "search down"},
        run_browser_tasks_fn=_never,
        run_tampermonkey_tasks_fn=_never,
        run_sampling_requests_fn=_never,
    )
    assert failed_search == "search pipeline failed"
    assert [event["event"] for _, event in store.events[:3]] == [
        "SEARCH_PARALLEL_POLICY",
        "SEARCH_VERIFY_POLICY",
        "SEARCH_PIPELINE_RESULT",
    ]

    failed_browser = bridge_runtime.run_optional_tool_requests(
        run_id=run_id,
        store=store,
        tool_runner=object(),
        assigned_agent=agent,
        contract_browser_policy={"mode": "safe"},
        search_request=None,
        browser_request={"tasks": [{"url": "https://example.com", "script": ""}]},
        tamper_request=None,
        sampling_request=None,
        run_search_pipeline_fn=_never,
        run_browser_tasks_fn=lambda *_a, **_k: {"ok": False, "reason": "browser down"},
        run_tampermonkey_tasks_fn=_never,
        run_sampling_requests_fn=_never,
    )
    assert failed_browser == "browser tasks failed"

    failed_tamper = bridge_runtime.run_optional_tool_requests(
        run_id=run_id,
        store=store,
        tool_runner=object(),
        assigned_agent=agent,
        contract_browser_policy={"mode": "safe"},
        search_request=None,
        browser_request=None,
        tamper_request={"tasks": [{"script": "x"}]},
        sampling_request=None,
        run_search_pipeline_fn=_never,
        run_browser_tasks_fn=_never,
        run_tampermonkey_tasks_fn=lambda *_a, **_k: {"ok": False, "reason": "tamper down"},
        run_sampling_requests_fn=_never,
    )
    assert failed_tamper == "tampermonkey tasks failed"

    failed_sampling = bridge_runtime.run_optional_tool_requests(
        run_id=run_id,
        store=store,
        tool_runner=object(),
        assigned_agent=agent,
        contract_browser_policy={"mode": "safe"},
        search_request=None,
        browser_request=None,
        tamper_request=None,
        sampling_request={"requests": [{"tool": "x"}]},
        run_search_pipeline_fn=_never,
        run_browser_tasks_fn=_never,
        run_tampermonkey_tasks_fn=_never,
        run_sampling_requests_fn=lambda *_a, **_k: {"ok": False, "reason": "sampling down"},
    )
    assert failed_sampling == "sampling requests failed"
    assert store.events[-1][1]["level"] == "ERROR"

    ok = bridge_runtime.run_optional_tool_requests(
        run_id=run_id,
        store=store,
        tool_runner=object(),
        assigned_agent=agent,
        contract_browser_policy={"mode": "safe"},
        search_request={"queries": ["q"], "parallel": 1, "verify": False, "providers": ["chatgpt_web"]},
        browser_request={"tasks": [{"url": "https://example.com", "script": ""}]},
        tamper_request={"tasks": [{"script": "x"}]},
        sampling_request={"requests": [{"tool": "x"}]},
        run_search_pipeline_fn=lambda *_a, **_k: {"ok": True},
        run_browser_tasks_fn=lambda *_a, **_k: {"ok": True},
        run_tampermonkey_tasks_fn=lambda *_a, **_k: {"ok": True},
        run_sampling_requests_fn=lambda *_a, **_k: {"ok": True},
    )
    assert ok == ""


def test_adapter_runner_build_variants_and_none_paths(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    contract = {"task_id": "t1"}
    assert bridge_runtime._build_runner_via_execution_adapter(contract, store, "agents") is None

    monkeypatch.setattr(bridge_runtime, "import_module", lambda _name: (_ for _ in ()).throw(ModuleNotFoundError("x")))
    assert bridge_runtime._build_runner_via_execution_adapter(contract, store, "codex") is None

    calls: list[str] = []

    class _Runner:
        def run_contract(self, *_a, **_k):
            return {"status": "SUCCESS"}

    class _FakeAdapterModule:
        @staticmethod
        def build_execution_adapter(*args, **kwargs):
            calls.append("build_execution_adapter")
            raise TypeError("try next")

        @staticmethod
        def create_runner(*args, **kwargs):
            del kwargs
            calls.append("create_runner")
            if len(args) == 3:
                return _Runner()
            raise TypeError("need positional")

    monkeypatch.setattr(bridge_runtime, "import_module", lambda _name: _FakeAdapterModule)
    runner = bridge_runtime._build_runner_via_execution_adapter(contract, store, "codex")
    assert isinstance(runner, _Runner)
    assert "build_execution_adapter" in calls
    assert "create_runner" in calls


def test_select_runner_error_paths_and_fallback(monkeypatch, tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")

    with pytest.raises(ValueError, match="unsupported runtime_options.runner"):
        bridge_runtime.select_runner({"runtime_options": {"runner": "bad-runner"}}, store)

    monkeypatch.setattr(bridge_runtime, "_build_runner_via_execution_adapter", lambda *_a, **_k: object())
    with pytest.raises(TypeError, match="must implement run_contract"):
        bridge_runtime.select_runner({"runtime_options": {"runner": "codex"}}, store)

    monkeypatch.setattr(bridge_runtime, "_build_runner_via_execution_adapter", lambda *_a, **_k: None)
    monkeypatch.setenv("CORTEXPILOT_RUNNER", "unknown-runner")
    with pytest.raises(ValueError, match="unsupported runner"):
        bridge_runtime.select_runner({}, store)


def test_apply_rollback_and_scoped_revert_delegate(monkeypatch, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    rollback = {"strategy": "noop"}
    paths = ["a.py"]
    monkeypatch.setattr(bridge_runtime.rollback_pipeline, "apply_rollback", lambda wt, rb: {"wt": str(wt), "rb": rb})
    monkeypatch.setattr(bridge_runtime.rollback_pipeline, "scoped_revert", lambda wt, ps: {"wt": str(wt), "ps": ps})
    assert bridge_runtime.apply_rollback(worktree, rollback)["rb"] == rollback
    assert bridge_runtime.scoped_revert(worktree, paths)["ps"] == paths


def test_execute_replay_action_error_branch_writes_event_when_manifest_exists(tmp_path: Path) -> None:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run("task-replay")
    run_dir = store._runs_root / run_id
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    runner = types.SimpleNamespace()

    failed = bridge_runtime.execute_replay_action(
        runner=runner,
        action="unsupported",
        run_id=run_id,
        store=store,
        event="REPLAY_FAIL",
    )
    assert failed["status"] == "fail"
    events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(item.get("event") == "REPLAY_FAIL" for item in events)

    missing_run = bridge_runtime.execute_replay_action(
        runner=runner,
        action="unsupported",
        run_id="run-missing",
        store=store,
        event="REPLAY_FAIL",
    )
    assert missing_run["status"] == "fail"
