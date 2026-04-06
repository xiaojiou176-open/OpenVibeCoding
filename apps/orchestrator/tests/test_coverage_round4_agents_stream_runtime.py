from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from cortexpilot_orch.runners import agents_stream_runtime
from cortexpilot_orch.store.run_store import RunStore


class _Item:
    def __init__(self, raw_item: dict) -> None:
        self.raw_item = raw_item


class _RunItemEvent:
    def __init__(self, name: str, raw_item: dict | None = None) -> None:
        self.type = "run_item_stream_event"
        self.name = name
        self.item = _Item(raw_item or {})


class _QuickResult:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []
        self._complete = False

    async def stream_events(self):
        yield _RunItemEvent("mcp_list_tools", {"name": "tool"})
        self._complete = True

    def cancel(self, mode: str = "immediate") -> None:
        self.cancel_calls.append(mode)
        self._complete = True

    @property
    def is_complete(self) -> bool:
        return self._complete


class _PendingResult:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []
        self._complete = False

    async def stream_events(self):
        await asyncio.sleep(10)
        if False:  # pragma: no cover
            yield None

    def cancel(self, mode: str = "immediate") -> None:
        self.cancel_calls.append(mode)
        self._complete = True

    @property
    def is_complete(self) -> bool:
        return self._complete


class _CancelledResult:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []
        self._complete = False

    async def stream_events(self):
        raise asyncio.CancelledError()
        if False:  # pragma: no cover
            yield None

    def cancel(self, mode: str = "immediate") -> None:
        self.cancel_calls.append(mode)
        self._complete = True

    @property
    def is_complete(self) -> bool:
        return self._complete


def _start_watch_tasks_factory(
    *,
    trigger: str | None = None,
    mark_tool_timeout_triggered: bool = False,
):
    def _start_watch_tasks(**kwargs):
        if mark_tool_timeout_triggered:
            kwargs["watch_state"].tool_timeout_triggered = True
        if trigger == "tool" and kwargs.get("tool_timeout_event") is not None:
            kwargs["tool_timeout_event"].set()
        if trigger == "idle" and kwargs.get("stream_idle_event") is not None:
            kwargs["stream_idle_event"].set()
        if trigger == "broken_pipe" and kwargs.get("broken_pipe_event") is not None:
            kwargs["broken_pipe_event"].set()
        return None, None, None

    return _start_watch_tasks


def _store_and_run_id(tmp_path: Path, task_name: str) -> tuple[RunStore, str]:
    store = RunStore(runs_root=tmp_path / "runs")
    run_id = store.create_run(task_name)
    return store, run_id


def test_stream_runtime_invalid_timeout_inputs_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-invalid-timeout-values")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: None,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    monkeypatch.setenv("CORTEXPILOT_STREAM_IDLE_TIMEOUT_SEC", "oops")
    monkeypatch.setenv("CORTEXPILOT_CODEX_TIMEBOX_SEC", "oops")

    asyncio.run(
        agents_stream_runtime.consume_stream_events(
            result=_QuickResult(),
            store=store,
            run_id=run_id,
            task_id="task-invalid-timeout",
            contract={"timeout_retry": {"timeout_sec": "oops"}},
            mcp_stderr_path=None,
        )
    )


def test_stream_runtime_non_positive_idle_and_hard_timebox_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-non-positive-timeouts")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: 1.0,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    monkeypatch.setenv("CORTEXPILOT_STREAM_IDLE_TIMEOUT_SEC", "0")
    monkeypatch.setenv("CORTEXPILOT_CODEX_TIMEBOX_SEC", "-1")

    asyncio.run(
        agents_stream_runtime.consume_stream_events(
            result=_QuickResult(),
            store=store,
            run_id=run_id,
            task_id="task-non-positive-timeouts",
            contract={"timeout_retry": {"timeout_sec": 1}},
            mcp_stderr_path=None,
        )
    )


def test_stream_runtime_hard_timebox_only_applies_and_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-hard-timebox-only")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: None,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    monkeypatch.setenv("CORTEXPILOT_CODEX_TIMEBOX_SEC", "0.2")
    monkeypatch.delenv("CORTEXPILOT_STREAM_IDLE_TIMEOUT_SEC", raising=False)

    asyncio.run(
        agents_stream_runtime.consume_stream_events(
            result=_QuickResult(),
            store=store,
            run_id=run_id,
            task_id="task-hard-timebox-only",
            contract={"timeout_retry": {"timeout_sec": "bad"}},
            mcp_stderr_path=None,
        )
    )
    events_text = (tmp_path / "runs" / run_id / "events.jsonl").read_text(encoding="utf-8")
    assert "MCP_STREAM_TIMEBOX_APPLIED" in events_text


def test_stream_runtime_tool_timeout_event_aborts_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-tool-timeout-event")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: 1.0,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(trigger="tool"),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    result = _PendingResult()

    with pytest.raises(RuntimeError, match="mcp tool call timeout"):
        asyncio.run(
            agents_stream_runtime.consume_stream_events(
                result=result,
                store=store,
                run_id=run_id,
                task_id="task-tool-timeout-event",
                contract={},
                mcp_stderr_path=None,
                tool_context={"tool": "test-tool"},
            )
        )


def test_stream_runtime_broken_pipe_and_idle_timeout_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-broken-pipe-event")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: None,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(trigger="broken_pipe"),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    result_broken = _PendingResult()
    with pytest.raises(RuntimeError, match="broken pipe"):
        asyncio.run(
            agents_stream_runtime.consume_stream_events(
                result=result_broken,
                store=store,
                run_id=run_id,
                task_id="task-broken-pipe-event",
                contract={},
                mcp_stderr_path=tmp_path / "mcp.stderr.log",
            )
        )
    assert result_broken.cancel_calls == ["immediate"]

    store_idle, run_id_idle = _store_and_run_id(tmp_path, "stream-idle-timeout-event")
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(trigger="idle"),
    )
    monkeypatch.setenv("CORTEXPILOT_STREAM_IDLE_TIMEOUT_SEC", "0.1")
    with pytest.raises(RuntimeError, match="idle timeout"):
        asyncio.run(
            agents_stream_runtime.consume_stream_events(
                result=_PendingResult(),
                store=store_idle,
                run_id=run_id_idle,
                task_id="task-idle-timeout-event",
                contract={},
                mcp_stderr_path=None,
            )
        )


def test_stream_runtime_cancelled_and_post_watch_timeout_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store, run_id = _store_and_run_id(tmp_path, "stream-cancelled-path")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: 1.0,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(),
    )
    monkeypatch.setattr(agents_stream_runtime, "cancel_watch_tasks", lambda *args: None)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            agents_stream_runtime.consume_stream_events(
                result=_CancelledResult(),
                store=store,
                run_id=run_id,
                task_id="task-cancelled-path",
                contract={},
                mcp_stderr_path=None,
            )
        )

    store_timeout, run_id_timeout = _store_and_run_id(tmp_path, "stream-post-watch-timeout")
    monkeypatch.setattr(
        agents_stream_runtime.mcp_server_lifecycle,
        "resolve_mcp_tool_timeout_sec",
        lambda: None,
    )
    monkeypatch.setattr(
        agents_stream_runtime,
        "start_watch_tasks",
        _start_watch_tasks_factory(mark_tool_timeout_triggered=True),
    )
    with pytest.raises(RuntimeError, match="mcp tool call timeout"):
        asyncio.run(
            agents_stream_runtime.consume_stream_events(
                result=_QuickResult(),
                store=store_timeout,
                run_id=run_id_timeout,
                task_id="task-post-watch-timeout",
                contract={},
                mcp_stderr_path=None,
                activity_bridge={"touch": SimpleNamespace()},
            )
        )
