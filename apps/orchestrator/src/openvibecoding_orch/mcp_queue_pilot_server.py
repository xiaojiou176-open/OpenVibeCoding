from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO

try:
    from mcp.shared.version import LATEST_PROTOCOL_VERSION
except Exception:  # noqa: BLE001
    LATEST_PROTOCOL_VERSION = "2025-11-25"


JSONRPC_VERSION = "2.0"
_DEFAULT_MUTATION_ROLES = {"OWNER", "ARCHITECT", "OPS", "TECH_LEAD"}
_APPLY_ENABLE_ENV = "OPENVIBECODING_MCP_QUEUE_PILOT_ENABLE_APPLY"
SERVER_INFO = {
    "name": "openvibecoding-queue-pilot",
    "title": "OpenVibeCoding Queue Pilot MCP",
    "version": "0.1.0",
}


def _schema_object(*, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_arg(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise ValueError(f"`{key}` is required")
    return value


def _optional_text_arg(arguments: dict[str, Any], key: str) -> str | None:
    value = str(arguments.get(key) or "").strip()
    return value or None


def _mutation_roles() -> set[str]:
    raw = os.getenv("OPENVIBECODING_APPROVAL_ALLOWED_ROLES", "").strip()
    if not raw:
        return set(_DEFAULT_MUTATION_ROLES)
    parsed = {item.strip().upper() for item in raw.split(",") if item.strip()}
    return parsed or set(_DEFAULT_MUTATION_ROLES)


def _required_role_arg(arguments: dict[str, Any]) -> str:
    role = _text_arg(arguments, "actor_role").upper()
    if role not in _mutation_roles():
        raise ValueError(f"`actor_role` must be one of: {', '.join(sorted(_mutation_roles()))}")
    return role


def _apply_mutation_enabled() -> bool:
    raw = str(os.getenv(_APPLY_ENABLE_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _tool_result(name: str, payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    keys = ", ".join(sorted(payload.keys()))
    return {
        "content": [{"type": "text", "text": f"{name} returned structured data ({keys or 'no keys'})."}],
        "structuredContent": payload,
        "isError": is_error,
    }


def _error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _queue_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    priority = arguments.get("priority")
    if priority is not None:
        payload["priority"] = priority
    scheduled_at = _optional_text_arg(arguments, "scheduled_at")
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at
    deadline_at = _optional_text_arg(arguments, "deadline_at")
    if deadline_at is not None:
        payload["deadline_at"] = deadline_at
    return payload


@dataclass(frozen=True)
class QueuePilotToolSpec:
    name: str
    title: str
    description: str
    read_only: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "annotations": {"readOnlyHint": self.read_only},
        }


class OpenVibeCodingQueuePilotMcpServer:
    def __init__(
        self,
        *,
        preview_enqueue_fn: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        enqueue_fn: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        if preview_enqueue_fn is None or enqueue_fn is None:
            from openvibecoding_orch.api import main as api_main

            preview_enqueue_fn = preview_enqueue_fn or api_main.preview_enqueue_run_queue
            enqueue_fn = enqueue_fn or api_main.enqueue_run_queue
        self._preview_enqueue_fn = preview_enqueue_fn
        self._enqueue_fn = enqueue_fn
        self._tools = [
            QueuePilotToolSpec(
                name="preview_enqueue_from_run",
                title="Preview enqueue from run",
                description="Preview the queue-first write pilot by deriving one queue item from an existing run without mutating queue state.",
                read_only=True,
                input_schema=_schema_object(
                    properties={
                        "run_id": {"type": "string", "minLength": 1},
                        "priority": {"type": "integer"},
                        "scheduled_at": {"type": "string"},
                        "deadline_at": {"type": "string"},
                    },
                    required=["run_id"],
                ),
                output_schema=_schema_object(
                    properties={
                        "run_id": {"type": "string"},
                        "validation": {"type": "string"},
                        "can_apply": {"type": "boolean"},
                        "preview_item": {"type": "object"},
                        "required_apply_inputs": {"type": "array", "items": {"type": "string"}},
                        "allowed_roles": {"type": "array", "items": {"type": "string"}},
                        "mutation_gate": {"type": "string"},
                        "next_step": {"type": "string"},
                    },
                    required=["run_id", "validation", "can_apply", "preview_item"],
                ),
                handler=self._preview_tool_handler,
            ),
            QueuePilotToolSpec(
                name="enqueue_from_run",
                title="Enqueue from run",
                description="Apply the narrow queue-first pilot by appending one queue item derived from an existing run. Requires explicit confirm=true plus trusted operator metadata.",
                read_only=False,
                input_schema=_schema_object(
                    properties={
                        "run_id": {"type": "string", "minLength": 1},
                        "priority": {"type": "integer"},
                        "scheduled_at": {"type": "string"},
                        "deadline_at": {"type": "string"},
                        "actor_role": {"type": "string", "minLength": 1},
                        "requested_by": {"type": "string", "minLength": 1},
                        "approval_reason": {"type": "string", "minLength": 1},
                        "confirm": {"type": "boolean"},
                    },
                    required=["run_id", "actor_role", "requested_by", "approval_reason", "confirm"],
                ),
                output_schema=_schema_object(
                    properties={
                        "queue_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    required=["queue_id", "task_id", "status"],
                ),
                handler=self._enqueue_tool_handler,
            ),
        ]
        self._tool_map = {tool.name: tool for tool in self._tools}

    def _preview_tool_handler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._preview_enqueue_fn(
            _text_arg(arguments, "run_id"),
            _queue_payload(arguments),
        )
        result.setdefault("required_apply_inputs", ["confirm", "actor_role", "requested_by", "approval_reason"])
        result.setdefault("allowed_roles", sorted(_mutation_roles()))
        if not _apply_mutation_enabled():
            result["can_apply"] = False
            result.setdefault("mutation_gate", "default-off")
            result.setdefault(
                "next_step",
                f"Set {_APPLY_ENABLE_ENV}=1 in a trusted operator environment before calling `enqueue_from_run`.",
            )
        return result

    def _enqueue_tool_handler(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not _apply_mutation_enabled():
            raise ValueError(
                f"`enqueue_from_run` is default-off until {_APPLY_ENABLE_ENV}=1 is set in the trusted operator environment"
            )
        if not bool(arguments.get("confirm")):
            raise ValueError("`confirm=true` is required for enqueue_from_run mutations")
        actor_role = _required_role_arg(arguments)
        requested_by = _text_arg(arguments, "requested_by")
        approval_reason = _text_arg(arguments, "approval_reason")
        payload = _queue_payload(arguments)
        payload.update(
            {
                "requested_by": requested_by,
                "actor_role": actor_role,
                "approval_reason": approval_reason,
                "approval_mode": "manual-owner-default-off",
                "pilot_source": "mcp_queue_pilot_server",
            }
        )
        return self._enqueue_fn(_text_arg(arguments, "run_id"), payload)

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": SERVER_INFO,
        }

    def handle_message(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        method = str(payload.get("method") or "").strip()
        request_id = payload.get("id")
        params = _as_record(payload.get("params"))

        if method in {"initialized", "notifications/initialized"}:
            return None

        if method == "ping":
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": {}}

        if method == "initialize":
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": self._initialize_result(),
            }

        if method in {"tools/list", "tooling/list"}:
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": {"tools": [tool.describe() for tool in self._tools]},
            }

        if method == "tools/call":
            tool_name = str(params.get("name") or "").strip()
            tool = self._tool_map.get(tool_name)
            if tool is None:
                return _error_response(request_id, -32601, f"unknown tool `{tool_name}`")
            try:
                result = tool.handler(_as_record(params.get("arguments")))
            except ValueError as exc:
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "result": _tool_result(tool_name, {"error": str(exc)}, is_error=True),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "result": _tool_result(tool_name, {"error": str(exc)}, is_error=True),
                }
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": _tool_result(tool_name, result),
            }

        if request_id is None:
            return None
        return _error_response(request_id, -32601, f"method `{method}` is not supported")

    def serve_forever(self, *, instream: TextIO | None = None, outstream: TextIO | None = None) -> None:
        source = instream or sys.stdin
        target = outstream or sys.stdout
        for raw_line in source:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            response = self.handle_message(payload)
            if response is None:
                continue
            target.write(json.dumps(response, ensure_ascii=False) + "\n")
            target.flush()


def serve_queue_pilot_mcp() -> None:
    OpenVibeCodingQueuePilotMcpServer().serve_forever()
