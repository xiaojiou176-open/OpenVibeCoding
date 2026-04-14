from __future__ import annotations

from openvibecoding_orch.mcp_queue_pilot_server import OpenVibeCodingQueuePilotMcpServer


def test_mcp_queue_pilot_server_lists_tools_and_requires_confirm_for_apply(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _preview(run_id: str, payload: dict[str, object]) -> dict[str, object]:
        captured["preview"] = {"run_id": run_id, "payload": payload}
        return {
            "run_id": run_id,
            "validation": "fail-closed",
            "can_apply": True,
            "preview_item": {"queue_id": "preview-1", "status": "PENDING"},
        }

    def _apply(run_id: str, payload: dict[str, object]) -> dict[str, object]:
        captured["apply"] = {"run_id": run_id, "payload": payload}
        return {"queue_id": "queue-1", "task_id": "task-1", "status": "PENDING"}

    server = OpenVibeCodingQueuePilotMcpServer(
        preview_enqueue_fn=_preview,
        enqueue_fn=_apply,
    )

    tools_response = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert tools_response is not None
    tool_names = [item["name"] for item in tools_response["result"]["tools"]]
    assert "preview_enqueue_from_run" in tool_names
    assert "enqueue_from_run" in tool_names

    preview_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "preview_enqueue_from_run",
                "arguments": {"run_id": "run-1", "priority": 5},
            },
        }
    )
    assert preview_response is not None
    assert preview_response["result"]["structuredContent"]["preview_item"]["status"] == "PENDING"
    assert preview_response["result"]["structuredContent"]["can_apply"] is False
    assert preview_response["result"]["structuredContent"]["mutation_gate"] == "default-off"
    assert preview_response["result"]["structuredContent"]["required_apply_inputs"] == [
        "confirm",
        "actor_role",
        "requested_by",
        "approval_reason",
    ]
    assert captured["preview"] == {"run_id": "run-1", "payload": {"priority": 5}}

    blocked_apply = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "enqueue_from_run",
                "arguments": {
                    "run_id": "run-1",
                    "priority": 5,
                    "actor_role": "OWNER",
                    "requested_by": "omega-worker",
                    "approval_reason": "queue-only pilot",
                    "confirm": False,
                },
            },
        }
    )
    assert blocked_apply is not None
    assert blocked_apply["result"]["isError"] is True

    monkeypatch.setenv("OPENVIBECODING_MCP_QUEUE_PILOT_ENABLE_APPLY", "1")

    apply_response = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "enqueue_from_run",
                "arguments": {
                    "run_id": "run-1",
                    "priority": 5,
                    "actor_role": "OWNER",
                    "requested_by": "omega-worker",
                    "approval_reason": "queue-only pilot",
                    "confirm": True,
                },
            },
        }
    )
    assert apply_response is not None
    assert apply_response["result"]["structuredContent"]["queue_id"] == "queue-1"
    assert captured["apply"] == {
        "run_id": "run-1",
        "payload": {
            "priority": 5,
            "requested_by": "omega-worker",
            "actor_role": "OWNER",
            "approval_reason": "queue-only pilot",
            "approval_mode": "manual-owner-default-off",
            "pilot_source": "mcp_queue_pilot_server",
        },
    }

    rejected_role = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "enqueue_from_run",
                "arguments": {
                    "run_id": "run-1",
                    "priority": 5,
                    "actor_role": "WORKER",
                    "requested_by": "omega-worker",
                    "approval_reason": "queue-only pilot",
                    "confirm": True,
                },
            },
        }
    )
    assert rejected_role is not None
    assert rejected_role["result"]["isError"] is True
