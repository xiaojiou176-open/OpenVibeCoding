from __future__ import annotations

from dataclasses import replace
import io
import sys
from types import ModuleType

from cortexpilot_orch import mcp_queue_pilot_server as queue_pilot_module


def test_mcp_queue_pilot_helpers_and_protocol_edges(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_APPROVAL_ALLOWED_ROLES", " owner , ops ")

    assert queue_pilot_module._mutation_roles() == {"OWNER", "OPS"}
    assert queue_pilot_module._required_role_arg({"actor_role": "owner"}) == "OWNER"
    assert queue_pilot_module._queue_payload(
        {"priority": 3, "scheduled_at": " 2026-04-12T09:00:00Z ", "deadline_at": " "}
    ) == {
        "priority": 3,
        "scheduled_at": "2026-04-12T09:00:00Z",
    }
    assert queue_pilot_module._error_response(7, -32601, "boom") == {
        "jsonrpc": "2.0",
        "id": 7,
        "error": {"code": -32601, "message": "boom"},
    }


def test_mcp_queue_pilot_server_covers_default_constructor_unknown_methods_and_stream(monkeypatch) -> None:
    captured: list[tuple[str, dict[str, object]]] = []

    def _preview(run_id: str, payload: dict[str, object]) -> dict[str, object]:
        captured.append((run_id, payload))
        return {
            "run_id": run_id,
            "validation": "ok",
            "can_apply": True,
            "preview_item": {"queue_id": "preview-1"},
        }

    def _apply(run_id: str, payload: dict[str, object]) -> dict[str, object]:
        return {"queue_id": f"{run_id}-queue", "task_id": "task-1", "status": "PENDING"}

    api_main = ModuleType("cortexpilot_orch.api.main")
    api_main.preview_enqueue_run_queue = _preview
    api_main.enqueue_run_queue = _apply
    monkeypatch.setitem(sys.modules, "cortexpilot_orch.api.main", api_main)

    server = queue_pilot_module.CortexPilotQueuePilotMcpServer()

    assert server.handle_message({"jsonrpc": "2.0", "method": "initialized"}) is None
    assert server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "ping"}) == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {},
    }
    init_response = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize"})
    assert init_response is not None
    assert init_response["result"]["serverInfo"]["name"] == "cortexpilot-queue-pilot"

    alias_list = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tooling/list"})
    assert alias_list is not None
    assert {tool["name"] for tool in alias_list["result"]["tools"]} == {
        "preview_enqueue_from_run",
        "enqueue_from_run",
    }

    unknown_tool = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "missing_tool", "arguments": {}},
        }
    )
    assert unknown_tool == {
        "jsonrpc": "2.0",
        "id": 4,
        "error": {"code": -32601, "message": "unknown tool `missing_tool`"},
    }

    missing_run_id = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "preview_enqueue_from_run", "arguments": {}},
        }
    )
    assert missing_run_id is not None
    assert missing_run_id["result"]["isError"] is True
    assert "`run_id` is required" in missing_run_id["result"]["structuredContent"]["error"]

    broken_tool = replace(
        server._tool_map["preview_enqueue_from_run"],
        handler=lambda arguments: (_ for _ in ()).throw(RuntimeError("preview exploded")),
    )
    server._tool_map["preview_enqueue_from_run"] = broken_tool
    runtime_error = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "preview_enqueue_from_run", "arguments": {"run_id": "run-9"}},
        }
    )
    assert runtime_error is not None
    assert runtime_error["result"]["isError"] is True
    assert runtime_error["result"]["structuredContent"]["error"] == "preview exploded"

    assert server.handle_message({"jsonrpc": "2.0", "method": "unsupported"}) is None
    unsupported = server.handle_message({"jsonrpc": "2.0", "id": 7, "method": "unsupported"})
    assert unsupported == {
        "jsonrpc": "2.0",
        "id": 7,
        "error": {"code": -32601, "message": "method `unsupported` is not supported"},
    }

    source = io.StringIO('\nnot-json\n[]\n{"jsonrpc":"2.0","id":8,"method":"ping"}\n')
    target = io.StringIO()
    server.serve_forever(instream=source, outstream=target)
    assert target.getvalue().strip() == '{"jsonrpc": "2.0", "id": 8, "result": {}}'

    called = {"serve_forever": False}

    class _FakeServer:
        def serve_forever(self) -> None:
            called["serve_forever"] = True

    monkeypatch.setattr(queue_pilot_module, "CortexPilotQueuePilotMcpServer", _FakeServer)
    queue_pilot_module.serve_queue_pilot_mcp()
    assert called["serve_forever"] is True
