from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cortexpilot_orch.runners import agents_events
from cortexpilot_orch.store.run_store import RunStore


@dataclass
class StreamWatchState:
    tool_active: bool = False
    tool_started_at: float | None = None
    tool_meta: dict[str, Any] = field(default_factory=dict)
    tool_timeout_triggered: bool = False
    consume_task_ref: asyncio.Task[None] | None = None


async def watch_tool_timeout(
    *,
    result: Any,
    store: RunStore,
    run_id: str,
    task_id: str,
    tool_timeout_sec: float | None,
    hard_timebox_sec: float | None,
    stream_started_at: float,
    activity_state: dict[str, Any],
    watch_state: StreamWatchState,
    tool_timeout_event: asyncio.Event | None,
) -> None:
    if tool_timeout_sec is None and hard_timebox_sec is None:
        return
    hard_timeout_sec: float | None = hard_timebox_sec
    while True:
        await asyncio.sleep(0.2)
        if watch_state.tool_timeout_triggered:
            return
        if hard_timeout_sec is not None:
            stream_elapsed = time.monotonic() - stream_started_at
            if stream_elapsed >= hard_timeout_sec:
                timeout_context = {
                    "task_id": task_id,
                    "elapsed_sec": round(stream_elapsed, 3),
                    "timeout_sec": hard_timeout_sec,
                    "last_activity_source": activity_state.get("source", ""),
                    "scope": "stream",
                    **watch_state.tool_meta,
                }
                watch_state.tool_timeout_triggered = True
                if tool_timeout_event is not None:
                    tool_timeout_event.set()
                if watch_state.consume_task_ref is not None and not watch_state.consume_task_ref.done():
                    watch_state.consume_task_ref.cancel()
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "mcp_stream_hard_timeout", **timeout_context},
                    task_id,
                )
                store.append_event(
                    run_id,
                    {
                        "level": "ERROR",
                        "event": "MCP_STREAM_HARD_TIMEOUT",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                result.cancel(mode="immediate")
                store.append_event(
                    run_id,
                    {
                        "level": "WARN",
                        "event": "MCP_STREAM_CANCELLED",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "mcp_stream_cancelled", **timeout_context},
                    task_id,
                )
                return
        if not watch_state.tool_active or watch_state.tool_started_at is None:
            if result.is_complete:
                return
            continue
        if tool_timeout_sec is not None:
            last_activity = activity_state.get("last") or watch_state.tool_started_at
            elapsed = time.monotonic() - last_activity
            if elapsed >= tool_timeout_sec:
                timeout_context = {
                    "task_id": task_id,
                    "elapsed_sec": round(elapsed, 3),
                    "timeout_sec": tool_timeout_sec,
                    "last_activity_source": activity_state.get("source", ""),
                    **watch_state.tool_meta,
                }
                watch_state.tool_timeout_triggered = True
                if tool_timeout_event is not None:
                    tool_timeout_event.set()
                if watch_state.consume_task_ref is not None and not watch_state.consume_task_ref.done():
                    watch_state.consume_task_ref.cancel()
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "mcp_tool_timeout", **timeout_context},
                    task_id,
                )
                store.append_event(
                    run_id,
                    {
                        "level": "ERROR",
                        "event": "MCP_TOOL_CALL_TIMEOUT",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                result.cancel(mode="immediate")
                store.append_event(
                    run_id,
                    {
                        "level": "WARN",
                        "event": "MCP_TOOL_CALL_CANCELLED",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "mcp_tool_cancelled", **timeout_context},
                    task_id,
                )
                return
        if result.is_complete:
            return


async def watch_stream_idle(
    *,
    idle_timeout_sec: float | None,
    activity_state: dict[str, Any],
    stream_idle_event: asyncio.Event | None,
) -> None:
    if idle_timeout_sec is None:
        return
    while True:
        await asyncio.sleep(0.5)
        last = activity_state.get("last")
        if last is None:
            continue
        elapsed = time.monotonic() - last
        if elapsed >= idle_timeout_sec:
            if stream_idle_event is not None:
                stream_idle_event.set()
            return


async def watch_mcp_stderr(
    *,
    broken_pipe_event: asyncio.Event | None,
    mcp_stderr_path: Path | None,
    store: RunStore,
    run_id: str,
    task_id: str,
) -> None:
    if broken_pipe_event is None or mcp_stderr_path is None:
        return
    last_pos = 0
    while True:
        await asyncio.sleep(0.5)
        try:
            if not mcp_stderr_path.exists():
                continue
            with mcp_stderr_path.open("r", encoding="utf-8", errors="ignore") as handle:
                handle.seek(last_pos)
                chunk = handle.read()
                last_pos = handle.tell()
        except Exception:  # noqa: BLE001
            continue
        if not chunk:
            continue
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", chunk)
        if "broken pipe" in cleaned.lower():
            context = {
                "task_id": task_id,
                "stderr_path": str(mcp_stderr_path),
                "reason": "broken_pipe",
            }
            broken_pipe_event.set()
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "mcp_broken_pipe", **context},
                task_id,
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_SERVER_BROKEN_PIPE",
                    "run_id": run_id,
                    "meta": context,
                },
            )
            return


def start_watch_tasks(
    *,
    result: Any,
    store: RunStore,
    run_id: str,
    task_id: str,
    tool_timeout_sec: float | None,
    hard_timebox_sec: float | None,
    stream_started_at: float,
    activity_state: dict[str, Any],
    watch_state: StreamWatchState,
    tool_timeout_event: asyncio.Event | None,
    idle_timeout_sec: float | None,
    stream_idle_event: asyncio.Event | None,
    broken_pipe_event: asyncio.Event | None,
    mcp_stderr_path: Path | None,
    enable_tool_watch: bool,
) -> tuple[asyncio.Task[None] | None, asyncio.Task[None] | None, asyncio.Task[None] | None]:
    watchdog_task = (
        asyncio.create_task(
            watch_tool_timeout(
                result=result,
                store=store,
                run_id=run_id,
                task_id=task_id,
                tool_timeout_sec=tool_timeout_sec,
                hard_timebox_sec=hard_timebox_sec,
                stream_started_at=stream_started_at,
                activity_state=activity_state,
                watch_state=watch_state,
                tool_timeout_event=tool_timeout_event,
            )
        )
        if enable_tool_watch
        else None
    )
    idle_watch_task = (
        asyncio.create_task(
            watch_stream_idle(
                idle_timeout_sec=idle_timeout_sec,
                activity_state=activity_state,
                stream_idle_event=stream_idle_event,
            )
        )
        if idle_timeout_sec is not None
        else None
    )
    broken_pipe_watch_task = (
        asyncio.create_task(
            watch_mcp_stderr(
                broken_pipe_event=broken_pipe_event,
                mcp_stderr_path=mcp_stderr_path,
                store=store,
                run_id=run_id,
                task_id=task_id,
            )
        )
        if broken_pipe_event is not None
        else None
    )
    return watchdog_task, idle_watch_task, broken_pipe_watch_task


def cancel_watch_tasks(*tasks: asyncio.Task[None] | None) -> None:
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
