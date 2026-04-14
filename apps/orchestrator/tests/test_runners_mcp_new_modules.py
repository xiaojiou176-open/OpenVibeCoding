from __future__ import annotations

import json
from typing import Any

from openvibecoding_orch.runners import mcp_logging, mcp_server_lifecycle, mcp_streaming


class _DummyStore:
    def __init__(self) -> None:
        self.artifacts: list[tuple[str, str, dict[str, Any]]] = []
        self.codex: list[tuple[str, str, str]] = []

    def append_artifact_jsonl(self, run_id: str, name: str, payload: dict[str, Any]) -> None:
        self.artifacts.append((run_id, name, payload))

    def append_codex_event(self, run_id: str, task_id: str, payload: str) -> None:
        self.codex.append((run_id, task_id, payload))


class _Item:
    def __init__(self, raw_item: dict[str, Any]) -> None:
        self.type = "tool_call"
        self.raw_item = raw_item


class _Event:
    def __init__(self, raw_item: dict[str, Any]) -> None:
        self.name = "evt"
        self.item = _Item(raw_item)


def test_mcp_server_lifecycle_env_resolution(monkeypatch) -> None:
    monkeypatch.delenv("OPENVIBECODING_MCP_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MCP_TOOL_TIMEOUT_SEC", raising=False)

    assert mcp_server_lifecycle.resolve_mcp_timeout_seconds() == 600.0
    assert mcp_server_lifecycle.resolve_mcp_connect_timeout_sec() == 20.0
    assert mcp_server_lifecycle.resolve_mcp_cleanup_timeout_sec() == 5.0
    assert mcp_server_lifecycle.resolve_mcp_tool_timeout_sec() is None

    monkeypatch.setenv("OPENVIBECODING_MCP_TIMEOUT_SEC", "bad")
    monkeypatch.setenv("OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC", "bad")
    monkeypatch.setenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", "bad")
    monkeypatch.setenv("OPENVIBECODING_MCP_TOOL_TIMEOUT_SEC", "bad")
    assert mcp_server_lifecycle.resolve_mcp_timeout_seconds() == 600.0
    assert mcp_server_lifecycle.resolve_mcp_connect_timeout_sec() == 20.0
    assert mcp_server_lifecycle.resolve_mcp_cleanup_timeout_sec() == 5.0
    assert mcp_server_lifecycle.resolve_mcp_tool_timeout_sec() is None

    monkeypatch.setenv("OPENVIBECODING_MCP_TIMEOUT_SEC", "0")
    monkeypatch.setenv("OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC", "0")
    monkeypatch.setenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", "0")
    monkeypatch.setenv("OPENVIBECODING_MCP_TOOL_TIMEOUT_SEC", "3")
    assert mcp_server_lifecycle.resolve_mcp_timeout_seconds() is None
    assert mcp_server_lifecycle.resolve_mcp_connect_timeout_sec() is None
    assert mcp_server_lifecycle.resolve_mcp_cleanup_timeout_sec() is None
    assert mcp_server_lifecycle.resolve_mcp_tool_timeout_sec() == 3.0

    monkeypatch.delenv("OPENVIBECODING_MCP_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MCP_CONNECT_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("OPENVIBECODING_MCP_CLEANUP_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("OPENVIBECODING_MCP_SERVER_TIMEOUT_SEC", "777")
    monkeypatch.setenv("OPENVIBECODING_MCP_SERVER_CONNECT_TIMEOUT_SEC", "44")
    monkeypatch.setenv("OPENVIBECODING_MCP_SERVER_CLEANUP_TIMEOUT_SEC", "9")
    assert mcp_server_lifecycle.resolve_mcp_timeout_seconds() == 600.0
    assert mcp_server_lifecycle.resolve_mcp_connect_timeout_sec() == 20.0
    assert mcp_server_lifecycle.resolve_mcp_cleanup_timeout_sec() == 5.0


def test_mcp_streaming_summaries_and_log_every(monkeypatch) -> None:
    event = _Event({"name": "shell", "call_id": "c1", "nested": {"a": 1}})
    summary = mcp_streaming.summarize_mcp_stream_item(event)
    assert summary["name"] == "evt"
    assert summary["item_type"] == "tool_call"
    assert summary["tool_name"] == "shell"
    assert summary["call_id"] == "c1"

    ok_result = mcp_streaming.summarize_mcp_tool_result({"Ok": {"content": [1, 2]}})
    err_result = mcp_streaming.summarize_mcp_tool_result({"Err": "failed"})
    unknown_result = mcp_streaming.summarize_mcp_tool_result("bad")

    assert ok_result == {"status": "ok", "content_len": 2}
    assert err_result["status"] == "error"
    assert unknown_result == {"status": "unknown"}

    monkeypatch.setenv("OPENVIBECODING_STREAM_LOG_EVERY", "")
    assert mcp_streaming.resolve_stream_log_every() == 0
    monkeypatch.setenv("OPENVIBECODING_STREAM_LOG_EVERY", "bad")
    assert mcp_streaming.resolve_stream_log_every() == 0
    monkeypatch.setenv("OPENVIBECODING_STREAM_LOG_EVERY", "4")
    assert mcp_streaming.resolve_stream_log_every() == 4


def test_mcp_streaming_private_extract_first_paths() -> None:
    payload = {"x": [{"deep": {"tool_name": "search", "tool_call_id": "c-1"}}]}
    assert mcp_streaming._extract_first(payload, ("tool_name",)) == "search"
    assert mcp_streaming._extract_first(payload, ("tool_call_id",)) == "c-1"
    assert mcp_streaming._extract_first("plain", ("x",)) is None
    assert mcp_streaming._extract_first({"a": {"b": {"c": 1}}}, ("c",), depth=7, max_depth=6) is None

    as_string = mcp_streaming.summarize_mcp_tool_result({"Ok": {"content": "abc"}})
    unknown_dict = mcp_streaming.summarize_mcp_tool_result({"something": 1})
    assert as_string == {"status": "ok", "content_len": 3}
    assert unknown_dict == {"status": "unknown"}


def test_mcp_logging_appenders() -> None:
    store = _DummyStore()
    mcp_logging.append_agents_transcript(store, "run-1", {"x": 1})
    assert store.artifacts[0][1] == "agents_transcript.jsonl"

    payload: dict[str, Any] = {}
    mcp_logging.append_agents_raw_event(store, "run-1", payload, task_id="task-1")
    assert store.artifacts[-1][1] == "agents_raw_events.jsonl"
    assert "ts" in payload
    assert payload["source"] == "agents_sdk"
    assert len(store.codex) == 1

    mcp_logging.append_agents_raw_event(store, "run-1", {"source": "custom"}, task_id=None)
    assert len(store.codex) == 1


def test_mcp_logging_redacts_prompt_and_sensitive_payload() -> None:
    store = _DummyStore()
    synthetic_prompt = "run with " + "sk-" + "1234567890123456" + " and token=abc123"
    payload = {
        "kind": "execution_start",
        "prompt": synthetic_prompt,
        "codex_payload": {
            "api_key": "plain-secret",
            "message": "Bearer abcdefghijklmnop",
            "nested": {"credential": "nested-secret"},
        },
    }
    mcp_logging.append_agents_raw_event(store, "run-2", payload, task_id="task-2")

    stored_payload = store.artifacts[-1][2]
    assert stored_payload["prompt"] == "[REDACTED]"
    assert stored_payload["prompt_meta"]["chars"] == len(payload["prompt"])
    assert stored_payload["codex_payload"]["api_key"] == "[REDACTED]"
    assert stored_payload["codex_payload"]["nested"]["credential"] == "[REDACTED]"
    assert stored_payload["codex_payload"]["message"] == "[REDACTED]"

    codex_event_payload = json.loads(store.codex[-1][2])
    assert codex_event_payload["prompt"] == "[REDACTED]"
