from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from openvibecoding_orch.runners import agents_events, agents_payload, mcp_server_lifecycle, mcp_streaming
from openvibecoding_orch.runners.agents_stream_watch_helpers import (
    StreamWatchState,
    cancel_watch_tasks,
    start_watch_tasks,
)
from openvibecoding_orch.store.run_store import RunStore


async def consume_stream_events(
    *,
    result: Any,
    store: RunStore,
    run_id: str,
    task_id: str,
    contract: dict[str, Any],
    mcp_stderr_path: Path | None,
    tool_context: dict[str, Any] | None = None,
    activity_bridge: dict[str, Any] | None = None,
) -> None:
    tool_context = tool_context or {}
    if isinstance(activity_bridge, dict):
        activity_bridge["touch"] = None
    timeout_raw = None
    if isinstance(contract.get("timeout_retry"), dict):
        timeout_raw = contract.get("timeout_retry", {}).get("timeout_sec")
    timeout_sec: float | None = None
    if timeout_raw is not None:
        try:
            timeout_sec = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_sec = None
    if timeout_sec is not None and timeout_sec <= 0:
        timeout_sec = None

    activity_state = {"last": None, "source": ""}

    def _touch_activity(source: str) -> None:
        activity_state["last"] = time.monotonic()
        activity_state["source"] = source

    if isinstance(activity_bridge, dict):
        activity_bridge["touch"] = _touch_activity

    event_count = 0
    stream_started_at = time.monotonic()
    tool_timeout_sec = mcp_server_lifecycle.resolve_mcp_tool_timeout_sec()
    watch_state = StreamWatchState()

    tool_timeout_event: asyncio.Event | None = asyncio.Event() if tool_timeout_sec is not None else None
    idle_timeout_raw = os.getenv("OPENVIBECODING_STREAM_IDLE_TIMEOUT_SEC", "").strip()
    idle_timeout_sec: float | None = None
    if idle_timeout_raw:
        try:
            idle_timeout_sec = float(idle_timeout_raw)
        except (TypeError, ValueError):
            idle_timeout_sec = None
    if idle_timeout_sec is not None and idle_timeout_sec <= 0:
        idle_timeout_sec = None
    stream_idle_event: asyncio.Event | None = asyncio.Event() if idle_timeout_sec is not None else None
    hard_timebox_raw = os.getenv("OPENVIBECODING_CODEX_TIMEBOX_SEC", "").strip()
    hard_timebox_sec: float | None = None
    if hard_timebox_raw:
        try:
            hard_timebox_sec = float(hard_timebox_raw)
        except (TypeError, ValueError):
            hard_timebox_sec = None
    if hard_timebox_sec is not None and hard_timebox_sec <= 0:
        hard_timebox_sec = None
    broken_pipe_enabled = os.getenv("OPENVIBECODING_MCP_BROKEN_PIPE_FAIL", "1").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    broken_pipe_event: asyncio.Event | None = (
        asyncio.Event() if broken_pipe_enabled and mcp_stderr_path is not None else None
    )

    async def _consume_stream() -> None:
        nonlocal event_count
        agents_events.append_agents_raw_event(
            store,
            run_id,
            {"kind": "stream_start", "timeout_sec": timeout_sec},
            task_id,
        )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "MCP_STREAM_START",
                "run_id": run_id,
                "meta": {"task_id": task_id, "timeout_sec": timeout_sec},
            },
        )
        log_every = mcp_streaming.resolve_stream_log_every()
        async for event in result.stream_events():
            event_count += 1
            _touch_activity("stream:event")
            if event_count == 1 or event_count % 50 == 0:
                event_type = getattr(event, "type", None) or event.__class__.__name__
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {
                        "kind": "stream_event",
                        "count": event_count,
                        "event_type": event_type,
                    },
                    task_id,
                )
            if log_every and event_count % log_every == 0:
                event_type = getattr(event, "type", None) or event.__class__.__name__
                store.append_event(
                    run_id,
                    {
                        "level": "INFO",
                        "event": "MCP_STREAM_TICK",
                        "run_id": run_id,
                        "meta": {
                            "task_id": task_id,
                            "count": event_count,
                            "event_type": event_type,
                        },
                    },
                )
            event_type = getattr(event, "type", None) or event.__class__.__name__
            if event_type == "run_item_stream_event":
                name = getattr(event, "name", None)
                if name in {
                    "tool_called",
                    "tool_output",
                    "mcp_approval_requested",
                    "mcp_approval_response",
                    "mcp_list_tools",
                }:
                    summary = mcp_streaming.summarize_mcp_stream_item(event)
                    raw_item = None
                    item = getattr(event, "item", None)
                    if item is not None:
                        raw_item = getattr(item, "raw_item", None)
                    if name in {"tool_called", "tool_output"} and raw_item is not None:
                        agents_events.append_agents_raw_event(
                            store,
                            run_id,
                            {
                                "kind": f"mcp_{name}_raw",
                                "count": event_count,
                                "tool_name": summary.get("tool_name"),
                                "call_id": summary.get("call_id"),
                                "raw_item": agents_payload._safe_json_value(raw_item),
                            },
                            task_id,
                        )
                    if name == "tool_called":
                        watch_state.tool_active = True
                        watch_state.tool_started_at = time.monotonic()
                        watch_state.tool_meta = summary
                        _touch_activity("stream:tool_called")
                        store.append_event(
                            run_id,
                            {
                                "level": "INFO",
                                "event": "MCP_TOOL_CALL_STARTED",
                                "run_id": run_id,
                                "meta": {
                                    "task_id": task_id,
                                    "timeout_sec": tool_timeout_sec,
                                    **summary,
                                },
                            },
                        )
                    elif name == "tool_output":
                        watch_state.tool_active = False
                        watch_state.tool_started_at = None
                        _touch_activity("stream:tool_output")
                        store.append_event(
                            run_id,
                            {
                                "level": "INFO",
                                "event": "MCP_TOOL_CALL_OUTPUT",
                                "run_id": run_id,
                                "meta": {"task_id": task_id, **summary},
                            },
                        )
                    agents_events.append_agents_raw_event(
                        store,
                        run_id,
                        {
                            "kind": "mcp_stream_item",
                            "count": event_count,
                            "event_type": event_type,
                            **summary,
                        },
                        task_id,
                    )
                    store.append_event(
                        run_id,
                        {
                            "level": "INFO",
                            "event": "MCP_STREAM_ITEM",
                            "run_id": run_id,
                            "meta": {
                                "task_id": task_id,
                                "event": event_type,
                                **summary,
                            },
                        },
                    )
            if watch_state.tool_timeout_triggered:
                break

    async def _drive_stream() -> None:
        consume_task = asyncio.create_task(_consume_stream())
        watch_state.consume_task_ref = consume_task
        timeout_task: asyncio.Task[None] | None = None
        idle_task: asyncio.Task[None] | None = None
        broken_pipe_task: asyncio.Task[None] | None = None
        tasks: set[asyncio.Task[object]] = {consume_task}
        if tool_timeout_event is not None:
            timeout_task = asyncio.create_task(tool_timeout_event.wait())
            tasks.add(timeout_task)
        if stream_idle_event is not None:
            idle_task = asyncio.create_task(stream_idle_event.wait())
            tasks.add(idle_task)
        if broken_pipe_event is not None:
            broken_pipe_task = asyncio.create_task(broken_pipe_event.wait())
            tasks.add(broken_pipe_task)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if timeout_task is not None and timeout_task in done and not consume_task.done():
            consume_task.cancel()
            try:
                await asyncio.wait_for(consume_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            timeout_context = {
                "task_id": task_id,
                "timeout_sec": tool_timeout_sec,
                "tool": tool_context.get("tool", "") or watch_state.tool_meta.get("tool_name", ""),
                "call_id": watch_state.tool_meta.get("call_id", ""),
            }
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "stream_aborted", **timeout_context},
                task_id,
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_STREAM_ABORTED",
                    "run_id": run_id,
                    "meta": timeout_context,
                },
            )
            raise RuntimeError("mcp tool call timeout")
        if broken_pipe_task is not None and broken_pipe_task in done and not consume_task.done():
            consume_task.cancel()
            try:
                await asyncio.wait_for(consume_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            broken_pipe_context = {
                "task_id": task_id,
                "stderr_path": str(mcp_stderr_path) if mcp_stderr_path is not None else "",
                "reason": "broken_pipe",
            }
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "stream_aborted", **broken_pipe_context},
                task_id,
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_STREAM_ABORTED",
                    "run_id": run_id,
                    "meta": broken_pipe_context,
                },
            )
            result.cancel(mode="immediate")
            raise RuntimeError("mcp server broken pipe")
        if idle_task is not None and idle_task in done and not consume_task.done():
            consume_task.cancel()
            try:
                await asyncio.wait_for(consume_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            idle_context = {
                "task_id": task_id,
                "idle_timeout_sec": idle_timeout_sec,
                "last_activity_source": activity_state.get("source", ""),
            }
            agents_events.append_agents_raw_event(
                store,
                run_id,
                {"kind": "stream_idle_timeout", **idle_context},
                task_id,
            )
            store.append_event(
                run_id,
                {
                    "level": "ERROR",
                    "event": "MCP_STREAM_IDLE_TIMEOUT",
                    "run_id": run_id,
                    "meta": idle_context,
                },
            )
            raise RuntimeError("stream idle timeout")
        try:
            await consume_task
        except asyncio.CancelledError:
            if watch_state.tool_timeout_triggered:
                timeout_context = {
                    "task_id": task_id,
                    "timeout_sec": tool_timeout_sec,
                    "tool": tool_context.get("tool", "") or watch_state.tool_meta.get("tool_name", ""),
                    "call_id": watch_state.tool_meta.get("call_id", ""),
                }
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "stream_aborted", **timeout_context},
                    task_id,
                )
                store.append_event(
                    run_id,
                    {
                        "level": "ERROR",
                        "event": "MCP_STREAM_ABORTED",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                raise RuntimeError("mcp tool call timeout")
            raise
        if timeout_task is not None and not timeout_task.done():
            timeout_task.cancel()

    effective_timeout = timeout_sec
    if hard_timebox_sec is not None:
        if effective_timeout is None:
            effective_timeout = hard_timebox_sec
        else:
            effective_timeout = min(effective_timeout, hard_timebox_sec)
    if effective_timeout is not None:
        try:
            watchdog_task, idle_watch_task, broken_pipe_watch_task = start_watch_tasks(
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
                idle_timeout_sec=idle_timeout_sec,
                stream_idle_event=stream_idle_event,
                broken_pipe_event=broken_pipe_event,
                mcp_stderr_path=mcp_stderr_path,
                enable_tool_watch=tool_timeout_sec is not None or hard_timebox_sec is not None,
            )
            store.append_event(
                run_id,
                {
                    "level": "INFO",
                    "event": "MCP_STREAM_TIMEBOX_APPLIED",
                    "run_id": run_id,
                    "meta": {
                        "task_id": task_id,
                        "timeout_sec": effective_timeout,
                        "contract_timeout_sec": timeout_sec,
                        "hard_timebox_sec": hard_timebox_sec,
                    },
                },
            )
            drive_task = asyncio.create_task(_drive_stream())
            done, _ = await asyncio.wait({drive_task}, timeout=effective_timeout, return_when=asyncio.FIRST_COMPLETED)
            if drive_task not in done:
                timeout_context = {
                    "task_id": task_id,
                    "count": event_count,
                    "timeout_sec": effective_timeout,
                }
                agents_events.append_agents_raw_event(
                    store,
                    run_id,
                    {"kind": "stream_timeout", **timeout_context},
                    task_id,
                )
                store.append_event(
                    run_id,
                    {
                        "level": "WARN",
                        "event": "MCP_STREAM_TIMEOUT",
                        "run_id": run_id,
                        "meta": timeout_context,
                    },
                )
                result.cancel(mode="immediate")
                drive_task.cancel()
                raise asyncio.TimeoutError()
            await drive_task
        except asyncio.TimeoutError as exc:
            raise exc
        finally:
            cancel_watch_tasks(watchdog_task, idle_watch_task, broken_pipe_watch_task)
    else:
        watchdog_task, idle_watch_task, broken_pipe_watch_task = start_watch_tasks(
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
            idle_timeout_sec=idle_timeout_sec,
            stream_idle_event=stream_idle_event,
            broken_pipe_event=broken_pipe_event,
            mcp_stderr_path=mcp_stderr_path,
            enable_tool_watch=tool_timeout_sec is not None,
        )
        try:
            await _drive_stream()
        finally:
            cancel_watch_tasks(watchdog_task, idle_watch_task, broken_pipe_watch_task)
    if watch_state.tool_timeout_triggered:
        raise RuntimeError("mcp tool call timeout")
    agents_events.append_agents_raw_event(
        store,
        run_id,
        {"kind": "stream_end", "count": event_count},
        task_id,
    )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "MCP_STREAM_END",
            "run_id": run_id,
            "meta": {"task_id": task_id, "count": event_count},
        },
    )
