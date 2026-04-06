from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from cortexpilot_orch.runners import agents_events, agents_payload, mcp_streaming
from cortexpilot_orch.store.run_store import RunStore


class MCPMessageArchive:
    def __init__(
        self,
        *,
        store: RunStore,
        run_id: str,
        task_id: str,
        stdout_path: Path,
        touch_activity: Callable[[str], None],
    ) -> None:
        self._store = store
        self._run_id = run_id
        self._task_id = task_id
        self.stdout_path = stdout_path
        self.touch_activity = touch_activity
        try:
            self._sample_every = max(
                1,
                int(os.getenv("CORTEXPILOT_MCP_EVENT_ROUTED_SAMPLE_EVERY", "20")),
            )
        except ValueError:
            self._sample_every = 20
        self.routed_total = 0
        self.routed_sampled = 0

    def append_stdout(self, payload: dict[str, Any]) -> None:
        try:
            line = json.dumps(payload, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            line = json.dumps({"raw": str(payload)}, ensure_ascii=False)
        with self.stdout_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    async def handle_message(self, message: Any) -> None:
        payload: dict[str, Any] = {
            "ts": agents_events.now_ts(),
            "type": message.__class__.__name__,
        }
        if hasattr(message, "model_dump"):
            try:
                payload["payload"] = agents_payload._safe_json_value(message.model_dump())
            except Exception:  # noqa: BLE001
                payload["payload"] = str(message)
        else:
            payload["payload"] = agents_payload._safe_json_value(str(message))
        self.append_stdout(payload)
        method = None
        if isinstance(payload.get("payload"), dict):
            method = payload.get("payload", {}).get("method")
        if method == "codex/event":
            self.routed_total += 1
            if self.routed_total == 1 or self.routed_total % self._sample_every == 0:
                self.routed_sampled += 1
                self._store.append_event(
                    self._run_id,
                    {
                        "level": "INFO",
                        "event": "MCP_EVENT_ROUTED",
                        "run_id": self._run_id,
                        "meta": {
                            "task_id": self._task_id,
                            "routed_total": self.routed_total,
                            "sample_every": self._sample_every,
                            "sampled": True,
                        },
                    },
                )
        msg = (
            payload.get("payload", {}).get("params", {}).get("msg", {})
            if isinstance(payload.get("payload"), dict)
            else {}
        )
        msg_type = msg.get("type") if isinstance(msg, dict) else None
        if msg_type:
            self.touch_activity(f"mcp:{msg_type}")
        if msg_type == "mcp_tool_call_begin":
            invocation = msg.get("invocation", {}) if isinstance(msg, dict) else {}
            tool_name = invocation.get("tool", "") if isinstance(invocation, dict) else ""
            server_name = invocation.get("server", "") if isinstance(invocation, dict) else ""
            args = invocation.get("arguments", {}) if isinstance(invocation, dict) else {}
            call_id = msg.get("call_id", "")
            self._store.append_tool_call(
                self._run_id,
                {
                    "tool": f"{server_name}.{tool_name}".strip(".") or tool_name or "unknown",
                    "args": args if isinstance(args, dict) else {},
                    "status": "started",
                    "task_id": self._task_id,
                },
            )
            self._store.append_event(
                self._run_id,
                {
                    "level": "INFO",
                    "event": "MCP_TOOL_CALL_STARTED",
                    "run_id": self._run_id,
                    "meta": {
                        "task_id": self._task_id,
                        "scope": "nested",
                        "server": server_name,
                        "tool": tool_name,
                        "call_id": call_id,
                    },
                },
            )
        elif msg_type == "mcp_tool_call_end":
            invocation = msg.get("invocation", {}) if isinstance(msg, dict) else {}
            tool_name = invocation.get("tool", "") if isinstance(invocation, dict) else ""
            server_name = invocation.get("server", "") if isinstance(invocation, dict) else ""
            args = invocation.get("arguments", {}) if isinstance(invocation, dict) else {}
            call_id = msg.get("call_id", "")
            result = msg.get("result")
            result_summary = mcp_streaming.summarize_mcp_tool_result(result)
            status = result_summary.get("status", "unknown")
            self._store.append_tool_call(
                self._run_id,
                {
                    "tool": f"{server_name}.{tool_name}".strip(".") or tool_name or "unknown",
                    "args": args if isinstance(args, dict) else {},
                    "status": status,
                    "task_id": self._task_id,
                },
            )
            self._store.append_event(
                self._run_id,
                {
                    "level": "INFO",
                    "event": "MCP_TOOL_CALL_RESULT",
                    "run_id": self._run_id,
                    "meta": {
                        "task_id": self._task_id,
                        "scope": "nested",
                        "server": server_name,
                        "tool": tool_name,
                        "call_id": call_id,
                        "result": result_summary,
                    },
                },
            )

    def finalize(self) -> None:
        if self.routed_total <= 0:
            return
        self._store.append_event(
            self._run_id,
            {
                "level": "INFO",
                "event": "MCP_EVENT_ROUTED",
                "run_id": self._run_id,
                "meta": {
                    "task_id": self._task_id,
                    "routed_total": self.routed_total,
                    "sampled_total": self.routed_sampled,
                    "suppressed_total": max(0, self.routed_total - self.routed_sampled),
                    "sample_every": self._sample_every,
                    "summary": True,
                },
            },
        )


def bind_mcp_log_paths(
    *,
    store: RunStore,
    run_id: str,
    task_id: str,
) -> tuple[Path, Path]:
    mcp_task_dir = store._codex_task_dir(run_id, task_id)
    mcp_stdout_path = mcp_task_dir / "mcp_stdout.jsonl"
    mcp_stderr_path = mcp_task_dir / "mcp_stderr.log"
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "MCP_STDOUT_LOG_BOUND",
            "run_id": run_id,
            "meta": {"task_id": task_id, "path": str(mcp_stdout_path)},
        },
    )
    store.append_event(
        run_id,
        {
            "level": "INFO",
            "event": "MCP_STDERR_LOG_BOUND",
            "run_id": run_id,
            "meta": {"task_id": task_id, "path": str(mcp_stderr_path)},
        },
    )
    return mcp_stdout_path, mcp_stderr_path
