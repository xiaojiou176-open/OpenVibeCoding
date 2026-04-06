from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO

from cortexpilot_orch.services.control_plane_read_service import ControlPlaneReadService

try:
    from mcp.shared.version import LATEST_PROTOCOL_VERSION
except Exception:  # noqa: BLE001
    LATEST_PROTOCOL_VERSION = "2025-11-25"


JSONRPC_VERSION = "2.0"
SERVER_INFO = {
    "name": "cortexpilot-readonly",
    "title": "CortexPilot Read-only MCP",
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


def _as_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_arg(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise ValueError(f"`{key}` is required")
    return value


def _optional_text_arg(arguments: dict[str, Any], key: str) -> str | None:
    value = str(arguments.get(key) or "").strip()
    return value or None


def _json_summary(name: str, payload: dict[str, Any]) -> str:
    keys = ", ".join(sorted(payload.keys()))
    return f"{name} returned structured data ({keys or 'no keys'})."


@dataclass(frozen=True)
class ReadonlyToolSpec:
    name: str
    title: str
    description: str
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
            "annotations": {"readOnlyHint": True},
        }


def _tool_result(name: str, payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _json_summary(name, payload)}],
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


def build_readonly_tools(read_service: ControlPlaneReadService) -> list[ReadonlyToolSpec]:
    return [
        ReadonlyToolSpec(
            name="list_runs",
            title="List runs",
            description="Return the current CortexPilot run ledger as a structured read-only list.",
            input_schema=_schema_object(),
            output_schema=_schema_object(properties={"runs": {"type": "array", "items": {"type": "object"}}}, required=["runs"]),
            handler=lambda _arguments: {"runs": read_service.list_runs()},
        ),
        ReadonlyToolSpec(
            name="get_run",
            title="Get run",
            description="Return one run snapshot, including manifest-derived status and contract-aligned metadata.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "run": {"type": "object"},
                },
                required=["run_id", "run"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "run": read_service.get_run(_text_arg(arguments, "run_id")),
            },
        ),
        ReadonlyToolSpec(
            name="get_run_events",
            title="Get run events",
            description="Return the structured event timeline for one run.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "events": {"type": "array", "items": {"type": "object"}},
                },
                required=["run_id", "events"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "events": read_service.get_run_events(_text_arg(arguments, "run_id")),
            },
        ),
        ReadonlyToolSpec(
            name="get_run_reports",
            title="Get run reports",
            description="Return the report bundle attached to one run, including compare/proof/incident packs when present.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "reports": {"type": "array", "items": {"type": "object"}},
                },
                required=["run_id", "reports"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "reports": read_service.get_run_reports(_text_arg(arguments, "run_id")),
            },
        ),
        ReadonlyToolSpec(
            name="list_workflows",
            title="List workflows",
            description="Return the current Workflow Case list as a structured read-only surface.",
            input_schema=_schema_object(),
            output_schema=_schema_object(
                properties={"workflows": {"type": "array", "items": {"type": "object"}}},
                required=["workflows"],
            ),
            handler=lambda _arguments: {"workflows": read_service.list_workflows()},
        ),
        ReadonlyToolSpec(
            name="get_workflow",
            title="Get workflow",
            description="Return one Workflow Case with linked runs and workflow-scoped events.",
            input_schema=_schema_object(
                properties={"workflow_id": {"type": "string", "minLength": 1}},
                required=["workflow_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "workflow_id": {"type": "string"},
                    "workflow_detail": {"type": "object"},
                },
                required=["workflow_id", "workflow_detail"],
            ),
            handler=lambda arguments: {
                "workflow_id": _text_arg(arguments, "workflow_id"),
                "workflow_detail": read_service.get_workflow(_text_arg(arguments, "workflow_id")),
            },
        ),
        ReadonlyToolSpec(
            name="list_queue",
            title="List queue",
            description="Return queue items, optionally filtered by workflow or queue status.",
            input_schema=_schema_object(
                properties={
                    "workflow_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            ),
            output_schema=_schema_object(
                properties={
                    "workflow_id": {"type": ["string", "null"]},
                    "status": {"type": ["string", "null"]},
                    "queue": {"type": "array", "items": {"type": "object"}},
                },
                required=["workflow_id", "status", "queue"],
            ),
            handler=lambda arguments: {
                "workflow_id": _optional_text_arg(arguments, "workflow_id"),
                "status": _optional_text_arg(arguments, "status"),
                "queue": read_service.list_queue(
                    workflow_id=_optional_text_arg(arguments, "workflow_id"),
                    status=_optional_text_arg(arguments, "status"),
                ),
            },
        ),
        ReadonlyToolSpec(
            name="get_pending_approvals",
            title="Get pending approvals",
            description="Return pending approval items, optionally filtered to one run.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string"}},
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": ["string", "null"]},
                    "approvals": {"type": "array", "items": {"type": "object"}},
                },
                required=["run_id", "approvals"],
            ),
            handler=lambda arguments: {
                "run_id": _optional_text_arg(arguments, "run_id"),
                "approvals": read_service.get_pending_approvals(
                    run_id=_optional_text_arg(arguments, "run_id"),
                ),
            },
        ),
        ReadonlyToolSpec(
            name="get_diff_gate_state",
            title="Get diff gate state",
            description="Return diff gate rows, optionally filtered to one run.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string"}},
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": ["string", "null"]},
                    "diff_gates": {"type": "array", "items": {"type": "object"}},
                },
                required=["run_id", "diff_gates"],
            ),
            handler=lambda arguments: {
                "run_id": _optional_text_arg(arguments, "run_id"),
                "diff_gates": read_service.get_diff_gate_state(
                    run_id=_optional_text_arg(arguments, "run_id"),
                ),
            },
        ),
        ReadonlyToolSpec(
            name="get_compare_summary",
            title="Get compare summary",
            description="Return the structured compare summary for one run when a run compare report exists.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "compare_summary": {"type": "object"},
                },
                required=["run_id", "compare_summary"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "compare_summary": read_service.get_compare_summary(_text_arg(arguments, "run_id")),
            },
        ),
        ReadonlyToolSpec(
            name="get_proof_summary",
            title="Get proof summary",
            description="Return the proof pack for one run when proof artifacts are present.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "proof_pack": {"type": "object"},
                },
                required=["run_id", "proof_pack"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "proof_pack": read_service.get_proof_summary(_text_arg(arguments, "run_id")),
            },
        ),
        ReadonlyToolSpec(
            name="get_incident_summary",
            title="Get incident summary",
            description="Return the incident pack for one run when incident context exists.",
            input_schema=_schema_object(
                properties={"run_id": {"type": "string", "minLength": 1}},
                required=["run_id"],
            ),
            output_schema=_schema_object(
                properties={
                    "run_id": {"type": "string"},
                    "incident_pack": {"type": "object"},
                },
                required=["run_id", "incident_pack"],
            ),
            handler=lambda arguments: {
                "run_id": _text_arg(arguments, "run_id"),
                "incident_pack": read_service.get_incident_summary(_text_arg(arguments, "run_id")),
            },
        ),
    ]


class CortexPilotReadonlyMcpServer:
    def __init__(self, read_service: ControlPlaneReadService | None = None) -> None:
        self._read_service = read_service or ControlPlaneReadService.from_api_main()
        self._tools = build_readonly_tools(self._read_service)
        self._tool_map = {tool.name: tool for tool in self._tools}

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": SERVER_INFO,
        }

    def _handle_tool_call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(arguments.get("name") or "").strip()
        if not tool_name:
            raise ValueError("`name` is required")
        tool = self._tool_map.get(tool_name)
        if tool is None:
            raise KeyError(f"unknown tool `{tool_name}`")
        tool_arguments = _as_record(arguments.get("arguments"))
        return tool.handler(tool_arguments)

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
            try:
                result = self._handle_tool_call(params)
            except KeyError as exc:
                return _error_response(request_id, -32601, str(exc))
            except ValueError as exc:
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "result": _tool_result(
                        str(params.get("name") or "unknown"),
                        {"error": str(exc)},
                        is_error=True,
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "result": _tool_result(
                        str(params.get("name") or "unknown"),
                        {"error": str(exc)},
                        is_error=True,
                    ),
                }
            return {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": _tool_result(str(params.get("name") or ""), result),
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


def serve_readonly_mcp() -> None:
    CortexPilotReadonlyMcpServer().serve_forever()
