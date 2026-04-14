from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from openvibecoding_orch.runners import agents_runner_phase2_helpers as helpers


class _ModelBehaviorError(RuntimeError):
    pass


class _OutputSchemaBase:
    pass


class _DraftValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = schema

    def validate(self, payload: dict[str, Any]) -> None:
        if payload.get("ok") is not True:
            raise ValueError("ok must be true")


def test_basic_permission_and_role_helpers() -> None:
    assert helpers.codex_allowed({}) is False
    assert helpers.codex_allowed({"tool_permissions": {"mcp_tools": "codex"}}) is False
    assert helpers.codex_allowed({"tool_permissions": {"mcp_tools": [" codex ", ""]}}) is True

    assert helpers.resolve_assigned_agent({"assigned_agent": []}) == {}
    assert helpers.resolve_assigned_agent({"assigned_agent": {"role": "worker"}}) == {"role": "worker"}

    assert helpers.agent_role([]) == ""
    assert helpers.agent_role({"role": " reviewer "}) == "REVIEWER"

    assert helpers.shell_policy({}) == "deny"
    assert helpers.shell_policy({"tool_permissions": {"shell": "  "}}) == "deny"
    assert helpers.shell_policy({"tool_permissions": {"shell": " On-Request "}}) == "on-request"


def test_build_output_schema_binding_validate_json_paths(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps({"type": "object"}), encoding="utf-8")

    binding = helpers.build_output_schema_binding(
        schema_path,
        agent_output_schema_base=_OutputSchemaBase,
        model_behavior_error=_ModelBehaviorError,
        draft_validator_cls=_DraftValidator,
    )

    assert binding.is_plain_text() is False
    assert binding.name() == "schema.json"
    assert binding.json_schema() == {"type": "object"}
    assert binding.is_strict_json_schema() is False
    assert binding.validate_json('{"ok": true}') == {"ok": True}

    with pytest.raises(_ModelBehaviorError, match="Output not JSON"):
        binding.validate_json("not-json")

    with pytest.raises(_ModelBehaviorError, match="Output schema validation failed"):
        binding.validate_json('{"ok": false}')


def test_dispatch_and_thread_id_helpers() -> None:
    payload = {
        "cwd": "/tmp",
        "sandbox": "workspace-write",
        "approval-policy": "never",
        "model": "gpt",
        "prompt": "payload-prompt",
    }

    tool_name, tool_payload, tool_config, unsupported = helpers.resolve_tool_dispatch(
        payload,
        instruction="fallback-instruction",
        thread_id="thread-1",
        is_codex_reply_thread_id=lambda tid: tid == "thread-1",
    )
    assert tool_name == "codex-reply"
    assert tool_payload == {"prompt": "payload-prompt", "threadId": "thread-1"}
    assert unsupported is None
    assert tool_config["cwd"] == "/tmp"

    tool_name, tool_payload, _tool_config, unsupported = helpers.resolve_tool_dispatch(
        payload,
        instruction="fallback-instruction",
        thread_id="unsupported-thread",
        is_codex_reply_thread_id=lambda _tid: False,
    )
    assert tool_name == "codex"
    assert tool_payload == payload
    assert unsupported == "unsupported-thread"

    assert helpers.extract_structured_thread_id(None) is None
    assert helpers.extract_structured_thread_id({"threadId": "tid-1"}) == "tid-1"
    assert helpers.extract_structured_thread_id({"thread_id": "tid-2"}) == "tid-2"
    assert helpers.extract_structured_thread_id({"threadID": "tid-3"}) == "tid-3"
    assert helpers.extract_structured_thread_id({"threadId": "   "}) is None


def test_build_tool_event_and_tool_call_helpers() -> None:
    seen: list[Any] = []

    event = helpers.build_tool_result_event(
        run_id="run-1",
        tool_name="codex",
        snapshot_thread_id=None,
        structured={"k": "v"},
        safe_json_value=lambda value: seen.append(value) or {"safe": True},
    )
    assert event["meta"]["thread_id"] == ""
    assert event["meta"]["structured_content"] == {"safe": True}
    assert seen == [{"k": "v"}]

    event_none = helpers.build_tool_result_event(
        run_id="run-1",
        tool_name="codex",
        snapshot_thread_id="t1",
        structured=None,
        safe_json_value=lambda value: value,
    )
    assert event_none["meta"]["thread_id"] == "t1"
    assert event_none["meta"]["structured_content"] is None

    minimal = helpers.build_tool_call(
        tool_name="codex",
        tool_payload={"x": 1},
        tool_config={"sandbox": "workspace-write"},
        status="ok",
        duration_ms=5,
        task_id="task-1",
    )
    assert set(minimal.keys()) == {"tool", "args", "config", "status", "duration_ms", "task_id"}

    with_optional = helpers.build_tool_call(
        tool_name="codex",
        tool_payload={"x": 1},
        tool_config={"sandbox": "workspace-write"},
        status="error",
        duration_ms=8,
        task_id="task-1",
        error="boom",
        thread_id="thread-1",
        session_id="session-1",
        output_sha256="sha",
    )
    assert with_optional["error"] == "boom"
    assert with_optional["thread_id"] == "thread-1"
    assert with_optional["session_id"] == "session-1"
    assert with_optional["output_sha256"] == "sha"


def test_normalize_final_output_error_and_success_paths() -> None:
    payload, failure, transcript = helpers.normalize_final_output(None)
    assert payload is None
    assert failure == {
        "summary": "agents sdk missing output",
        "emit_tool_call": True,
        "tool_error": "agents sdk missing output",
    }
    assert transcript[0]["kind"] == "final_output_missing"

    payload, failure, transcript = helpers.normalize_final_output("   ")
    assert payload is None
    assert failure == {
        "summary": "agents sdk missing output",
        "emit_tool_call": False,
        "tool_error": "",
    }
    assert transcript[0]["kind"] == "final_output_missing"

    payload, failure, transcript = helpers.normalize_final_output("not-json")
    assert payload is None
    assert failure is not None
    assert failure["summary"] == "agents sdk output not json"
    assert "output_not_json" in failure["tool_error"]
    assert transcript[-1]["kind"] == "output_not_json"

    payload, failure, transcript = helpers.normalize_final_output("[1,2,3]")
    assert payload is None
    assert failure is not None
    assert failure["summary"] == "agents sdk output not object"
    assert transcript[-1]["kind"] == "output_not_object"

    payload, failure, transcript = helpers.normalize_final_output('{"text":"{bad}"}')
    assert payload == {"text": "{bad}"}
    assert failure is None
    assert transcript[0]["kind"] == "final_output"

    nested_input = json.dumps({"text": json.dumps({"nested": 1})})
    payload, failure, transcript = helpers.normalize_final_output(nested_input)
    assert payload == {"nested": 1}
    assert failure is None
    assert transcript[0]["kind"] == "final_output"

    payload, failure, transcript = helpers.normalize_final_output({"ok": True})
    assert payload == {"ok": True}
    assert failure is None
    assert transcript[0]["kind"] == "final_output_structured"


def test_final_output_sha_source() -> None:
    assert helpers.final_output_sha_source("  keep  ") == "keep"
    assert helpers.final_output_sha_source({"ok": True}) == '{"ok": true}'
