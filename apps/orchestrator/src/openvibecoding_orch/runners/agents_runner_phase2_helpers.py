from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


def codex_allowed(contract: dict[str, Any]) -> bool:
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return False
    tools = tool_permissions.get("mcp_tools", [])
    if not isinstance(tools, list):
        return False
    return "codex" in {str(item).strip() for item in tools if str(item).strip()}


def resolve_assigned_agent(contract: dict[str, Any]) -> dict[str, Any]:
    assigned = contract.get("assigned_agent", {})
    return assigned if isinstance(assigned, dict) else {}


def agent_role(agent: dict[str, Any]) -> str:
    if not isinstance(agent, dict):
        return ""
    role = agent.get("role")
    return str(role).strip().upper() if role else ""


def shell_policy(contract: dict[str, Any]) -> str:
    tool_permissions = contract.get("tool_permissions")
    if not isinstance(tool_permissions, dict):
        return "deny"
    raw = tool_permissions.get("shell")
    return str(raw).strip().lower() if isinstance(raw, str) and raw.strip() else "deny"


def build_output_schema_binding(
    schema_path: Path,
    *,
    agent_output_schema_base: type[Any],
    model_behavior_error: type[Exception],
    draft_validator_cls: type[Any],
) -> Any:
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = draft_validator_cls(payload)

    class _JsonSchemaOutput(agent_output_schema_base):
        def __init__(self, name: str, schema: dict[str, Any]) -> None:
            self._name = name
            self._schema = schema

        def is_plain_text(self) -> bool:
            return False

        def name(self) -> str:
            return self._name

        def json_schema(self) -> dict[str, Any]:
            return self._schema

        def is_strict_json_schema(self) -> bool:
            return False

        def validate_json(self, json_str: str) -> Any:
            try:
                payload_obj = json.loads(json_str)
            except json.JSONDecodeError as exc:
                raise model_behavior_error(f"Output not JSON: {exc}") from exc
            try:
                validator.validate(payload_obj)
            except Exception as exc:  # noqa: BLE001
                raise model_behavior_error(f"Output schema validation failed: {exc}") from exc
            return payload_obj

    return _JsonSchemaOutput(schema_path.name, payload)


def resolve_tool_dispatch(
    codex_payload: dict[str, Any],
    *,
    instruction: str,
    thread_id: str | None,
    is_codex_reply_thread_id: Callable[[str | None], bool],
) -> tuple[str, dict[str, Any], dict[str, str], str | None]:
    tool_name = "codex"
    tool_payload = dict(codex_payload)
    tool_config = {
        "cwd": codex_payload.get("cwd", ""),
        "sandbox": codex_payload.get("sandbox", ""),
        "approval-policy": codex_payload.get("approval-policy", ""),
        "model": codex_payload.get("model", ""),
    }
    unsupported_thread_id: str | None = None
    if thread_id and is_codex_reply_thread_id(thread_id):
        tool_name = "codex-reply"
        tool_payload = {"prompt": codex_payload.get("prompt", instruction), "threadId": thread_id}
    elif thread_id:
        unsupported_thread_id = thread_id
    return tool_name, tool_payload, tool_config, unsupported_thread_id


def extract_structured_thread_id(structured: Any) -> str | None:
    if not isinstance(structured, dict):
        return None
    raw_thread = structured.get("threadId") or structured.get("thread_id") or structured.get("threadID")
    if isinstance(raw_thread, str) and raw_thread.strip():
        return raw_thread.strip()
    return None


def build_tool_result_event(
    *,
    run_id: str,
    tool_name: str,
    snapshot_thread_id: str | None,
    structured: Any,
    safe_json_value: Callable[[Any], Any],
) -> dict[str, Any]:
    return {
        "level": "INFO",
        "event": "MCP_TOOL_RESULT",
        "run_id": run_id,
        "meta": {
            "tool": tool_name,
            "thread_id": snapshot_thread_id or "",
            "structured_content": safe_json_value(structured) if structured is not None else None,
        },
    }


def build_tool_call(
    *,
    tool_name: str,
    tool_payload: dict[str, Any],
    tool_config: dict[str, Any],
    status: str,
    duration_ms: int,
    task_id: str,
    error: str | None = None,
    thread_id: str | None = None,
    session_id: str | None = None,
    output_sha256: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tool": tool_name,
        "args": tool_payload,
        "config": tool_config,
        "status": status,
        "duration_ms": duration_ms,
        "task_id": task_id,
    }
    if error is not None:
        payload["error"] = error
    if thread_id is not None:
        payload["thread_id"] = thread_id
    if session_id is not None:
        payload["session_id"] = session_id
    if output_sha256 is not None:
        payload["output_sha256"] = output_sha256
    return payload


def normalize_final_output(
    final_output: Any,
) -> tuple[Any | None, dict[str, Any] | None, list[dict[str, str]]]:
    transcript_items: list[dict[str, str]] = []
    if final_output is None:
        transcript_items.append({"kind": "final_output_missing", "text": "agents sdk missing output"})
        return (
            None,
            {
                "summary": "agents sdk missing output",
                "emit_tool_call": True,
                "tool_error": "agents sdk missing output",
            },
            transcript_items,
        )

    payload: Any
    if isinstance(final_output, str):
        stripped = final_output.strip()
        if not stripped:
            transcript_items.append({"kind": "final_output_missing", "text": "agents sdk missing output"})
            return (
                None,
                {
                    "summary": "agents sdk missing output",
                    "emit_tool_call": False,
                    "tool_error": "",
                },
                transcript_items,
            )
        transcript_items.append({"kind": "final_output", "text": stripped})
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            transcript_items.append({"kind": "output_not_json", "text": str(exc)})
            return (
                None,
                {
                    "summary": "agents sdk output not json",
                    "emit_tool_call": True,
                    "tool_error": f"output_not_json: {exc}",
                    "evidence": {"error": str(exc)},
                },
                transcript_items,
            )
    else:
        payload = final_output
        transcript_items.append({"kind": "final_output_structured", "text": json.dumps(payload, ensure_ascii=False)})

    if isinstance(payload, dict) and "text" in payload and isinstance(payload.get("text"), str):
        text_value = payload.get("text", "").strip()
        if text_value.startswith("{") and text_value.endswith("}"):
            try:
                nested = json.loads(text_value)
            except json.JSONDecodeError:
                nested = None
            if isinstance(nested, dict):
                payload = nested

    if not isinstance(payload, dict):
        transcript_items.append({"kind": "output_not_object", "text": str(type(payload))})
        return (
            None,
            {
                "summary": "agents sdk output not object",
                "emit_tool_call": True,
                "tool_error": "agents sdk output not object",
                "evidence": {"error": str(type(payload))},
            },
            transcript_items,
        )
    return payload, None, transcript_items


def final_output_sha_source(final_output: Any) -> str:
    if isinstance(final_output, str):
        return final_output.strip()
    return json.dumps(final_output, ensure_ascii=False)
