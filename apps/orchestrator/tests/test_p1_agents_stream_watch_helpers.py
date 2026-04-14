from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from openvibecoding_orch.runners import agents_stream_watch_helpers as watch_helpers


class _FakeResult:
    def __init__(self, *, is_complete: bool = False) -> None:
        self.is_complete = is_complete
        self.cancel_modes: list[str] = []

    def cancel(self, mode: str = "") -> None:
        self.cancel_modes.append(mode)


class _FakeStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.events.append({"run_id": run_id, "payload": dict(payload)})


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_watch_tool_timeout_returns_immediately_without_timeouts() -> None:
    result = _FakeResult()
    store = _FakeStore()
    watch_state = watch_helpers.StreamWatchState()
    _run(
        watch_helpers.watch_tool_timeout(
            result=result,
            store=store,  # type: ignore[arg-type]
            run_id="run_1",
            task_id="task_1",
            tool_timeout_sec=None,
            hard_timebox_sec=None,
            stream_started_at=0.0,
            activity_state={},
            watch_state=watch_state,
            tool_timeout_event=None,
        )
    )
    assert result.cancel_modes == []
    assert store.events == []
    assert watch_state.tool_timeout_triggered is False


def test_watch_tool_timeout_handles_hard_stream_timeout(monkeypatch) -> None:
    async def _exercise() -> None:
        result = _FakeResult()
        store = _FakeStore()
        raw_events: list[dict[str, Any]] = []
        watch_state = watch_helpers.StreamWatchState(tool_meta={"tool_name": "read_file"})
        watch_state.consume_task_ref = asyncio.create_task(asyncio.sleep(3600))
        timeout_event = asyncio.Event()

        async def _fast_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(watch_helpers.asyncio, "sleep", _fast_sleep)
        monkeypatch.setattr(watch_helpers.time, "monotonic", lambda: 10.0)
        monkeypatch.setattr(
            watch_helpers.agents_events,
            "append_agents_raw_event",
            lambda _store, _run_id, payload, _task_id: raw_events.append(dict(payload)),
        )

        await watch_helpers.watch_tool_timeout(
            result=result,
            store=store,  # type: ignore[arg-type]
            run_id="run_1",
            task_id="task_1",
            tool_timeout_sec=None,
            hard_timebox_sec=5.0,
            stream_started_at=0.0,
            activity_state={"source": "stream_loop"},
            watch_state=watch_state,
            tool_timeout_event=timeout_event,
        )
        await asyncio.sleep(0)

        assert watch_state.tool_timeout_triggered is True
        assert timeout_event.is_set()
        assert result.cancel_modes == ["immediate"]
        assert watch_state.consume_task_ref is not None
        task_ref = watch_state.consume_task_ref
        cancel_count = getattr(task_ref, "cancelling", None)
        if callable(cancel_count):
          assert task_ref.cancelled() or cancel_count() > 0 or getattr(task_ref, "_must_cancel", False)
        else:
          assert task_ref.cancelled() or getattr(task_ref, "_must_cancel", False)
        event_names = [item["payload"]["event"] for item in store.events]
        assert event_names == ["MCP_STREAM_HARD_TIMEOUT", "MCP_STREAM_CANCELLED"]
        assert [item["kind"] for item in raw_events] == [
            "mcp_stream_hard_timeout",
            "mcp_stream_cancelled",
        ]

    _run(_exercise())


def test_watch_tool_timeout_handles_active_tool_timeout(monkeypatch) -> None:
    async def _exercise() -> None:
        result = _FakeResult()
        store = _FakeStore()
        raw_events: list[dict[str, Any]] = []
        watch_state = watch_helpers.StreamWatchState(
            tool_active=True,
            tool_started_at=1.0,
            tool_meta={"tool_name": "write_file"},
        )
        timeout_event = asyncio.Event()

        async def _fast_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(watch_helpers.asyncio, "sleep", _fast_sleep)
        monkeypatch.setattr(watch_helpers.time, "monotonic", lambda: 8.0)
        monkeypatch.setattr(
            watch_helpers.agents_events,
            "append_agents_raw_event",
            lambda _store, _run_id, payload, _task_id: raw_events.append(dict(payload)),
        )

        await watch_helpers.watch_tool_timeout(
            result=result,
            store=store,  # type: ignore[arg-type]
            run_id="run_2",
            task_id="task_2",
            tool_timeout_sec=2.0,
            hard_timebox_sec=None,
            stream_started_at=0.0,
            activity_state={"last": 2.0, "source": "tool_call"},
            watch_state=watch_state,
            tool_timeout_event=timeout_event,
        )

        assert watch_state.tool_timeout_triggered is True
        assert timeout_event.is_set()
        assert result.cancel_modes == ["immediate"]
        event_names = [item["payload"]["event"] for item in store.events]
        assert event_names == ["MCP_TOOL_CALL_TIMEOUT", "MCP_TOOL_CALL_CANCELLED"]
        assert [item["kind"] for item in raw_events] == [
            "mcp_tool_timeout",
            "mcp_tool_cancelled",
        ]

    _run(_exercise())


def test_watch_tool_timeout_returns_when_result_completes_without_active_tool(monkeypatch) -> None:
    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(watch_helpers.asyncio, "sleep", _fast_sleep)
    result = _FakeResult(is_complete=True)
    watch_state = watch_helpers.StreamWatchState(tool_active=False, tool_started_at=None)
    store = _FakeStore()
    _run(
        watch_helpers.watch_tool_timeout(
            result=result,
            store=store,  # type: ignore[arg-type]
            run_id="run_3",
            task_id="task_3",
            tool_timeout_sec=5.0,
            hard_timebox_sec=None,
            stream_started_at=0.0,
            activity_state={},
            watch_state=watch_state,
            tool_timeout_event=None,
        )
    )
    assert store.events == []
    assert result.cancel_modes == []


def test_watch_stream_idle_sets_event_after_idle_window(monkeypatch) -> None:
    async def _exercise() -> None:
        activity_state: dict[str, Any] = {"last": None}
        idle_event = asyncio.Event()
        calls = {"count": 0}

        async def _controlled_sleep(_seconds: float) -> None:
            calls["count"] += 1
            if calls["count"] >= 2:
                activity_state["last"] = 1.0

        monkeypatch.setattr(watch_helpers.asyncio, "sleep", _controlled_sleep)
        monkeypatch.setattr(watch_helpers.time, "monotonic", lambda: 5.0)

        await watch_helpers.watch_stream_idle(
            idle_timeout_sec=2.0,
            activity_state=activity_state,
            stream_idle_event=idle_event,
        )
        assert idle_event.is_set()

    _run(_exercise())


def test_watch_stream_idle_noop_when_timeout_disabled() -> None:
    _run(
        watch_helpers.watch_stream_idle(
            idle_timeout_sec=None,
            activity_state={},
            stream_idle_event=asyncio.Event(),
        )
    )


def test_watch_mcp_stderr_detects_broken_pipe_and_emits_events(monkeypatch, tmp_path: Path) -> None:
    async def _exercise() -> None:
        stderr_path = tmp_path / "mcp.stderr"
        stderr_path.write_text("\x1b[31mBROKEN PIPE\x1b[0m\n", encoding="utf-8")
        broken_pipe_event = asyncio.Event()
        store = _FakeStore()
        raw_events: list[dict[str, Any]] = []

        async def _fast_sleep(_seconds: float) -> None:
            return None

        monkeypatch.setattr(watch_helpers.asyncio, "sleep", _fast_sleep)
        monkeypatch.setattr(
            watch_helpers.agents_events,
            "append_agents_raw_event",
            lambda _store, _run_id, payload, _task_id: raw_events.append(dict(payload)),
        )

        await watch_helpers.watch_mcp_stderr(
            broken_pipe_event=broken_pipe_event,
            mcp_stderr_path=stderr_path,
            store=store,  # type: ignore[arg-type]
            run_id="run_bp",
            task_id="task_bp",
        )

        assert broken_pipe_event.is_set()
        assert [item["kind"] for item in raw_events] == ["mcp_broken_pipe"]
        assert [item["payload"]["event"] for item in store.events] == ["MCP_SERVER_BROKEN_PIPE"]

    _run(_exercise())


def test_watch_mcp_stderr_noop_when_inputs_missing(tmp_path: Path) -> None:
    store = _FakeStore()
    _run(
        watch_helpers.watch_mcp_stderr(
            broken_pipe_event=None,
            mcp_stderr_path=tmp_path / "stderr.log",
            store=store,  # type: ignore[arg-type]
            run_id="run_noop",
            task_id="task_noop",
        )
    )
    _run(
        watch_helpers.watch_mcp_stderr(
            broken_pipe_event=asyncio.Event(),
            mcp_stderr_path=None,
            store=store,  # type: ignore[arg-type]
            run_id="run_noop",
            task_id="task_noop",
        )
    )
    assert store.events == []


def test_start_watch_tasks_and_cancel_watch_tasks(monkeypatch, tmp_path: Path) -> None:
    async def _exercise() -> None:
        async def _blocking_watch(**_kwargs) -> None:
            await asyncio.Event().wait()

        monkeypatch.setattr(watch_helpers, "watch_tool_timeout", _blocking_watch)
        monkeypatch.setattr(watch_helpers, "watch_stream_idle", _blocking_watch)
        monkeypatch.setattr(watch_helpers, "watch_mcp_stderr", _blocking_watch)

        watch_state = watch_helpers.StreamWatchState()
        watchdog, idle_watch, broken_pipe_watch = watch_helpers.start_watch_tasks(
            result=_FakeResult(),
            store=_FakeStore(),  # type: ignore[arg-type]
            run_id="run_tasks",
            task_id="task_tasks",
            tool_timeout_sec=1.0,
            hard_timebox_sec=2.0,
            stream_started_at=0.0,
            activity_state={},
            watch_state=watch_state,
            tool_timeout_event=asyncio.Event(),
            idle_timeout_sec=1.0,
            stream_idle_event=asyncio.Event(),
            broken_pipe_event=asyncio.Event(),
            mcp_stderr_path=tmp_path / "stderr.log",
            enable_tool_watch=True,
        )
        assert watchdog is not None
        assert idle_watch is not None
        assert broken_pipe_watch is not None

        watch_helpers.cancel_watch_tasks(watchdog, idle_watch, broken_pipe_watch)
        await asyncio.sleep(0)
        assert watchdog.cancelled()
        assert idle_watch.cancelled()
        assert broken_pipe_watch.cancelled()

        disabled = watch_helpers.start_watch_tasks(
            result=_FakeResult(),
            store=_FakeStore(),  # type: ignore[arg-type]
            run_id="run_tasks",
            task_id="task_tasks",
            tool_timeout_sec=1.0,
            hard_timebox_sec=2.0,
            stream_started_at=0.0,
            activity_state={},
            watch_state=watch_state,
            tool_timeout_event=None,
            idle_timeout_sec=None,
            stream_idle_event=None,
            broken_pipe_event=None,
            mcp_stderr_path=None,
            enable_tool_watch=False,
        )
        assert disabled == (None, None, None)

    _run(_exercise())
