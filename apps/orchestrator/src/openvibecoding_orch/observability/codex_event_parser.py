from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

PARSER_VERSION = "1"


def _extract_string(payload: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for container in ("payload", "msg", "context", "data", "item"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return None


def _extract_event_type(payload: dict[str, Any]) -> str:
    for key in ("type", "event", "kind", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for container in ("payload", "msg", "context", "data", "item"):
        nested = payload.get(container)
        if isinstance(nested, dict):
            for key in ("type", "event", "kind", "name"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return ""


@dataclass(frozen=True)
class CodexEventParseResult:
    raw_line: str
    is_json: bool
    payload: dict[str, Any]
    event_type: str
    session_id: str | None
    thread_id: str | None
    item_id: str | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    codex_version: str | None = None
    parser_version: str = PARSER_VERSION

    def to_codex_jsonl(self) -> str:
        if self.is_json:
            return self.raw_line
        return json.dumps({"raw": self.raw_line, "parse_error": "non_json"}, ensure_ascii=False)

    def to_event_context(self) -> dict[str, Any]:
        context: dict[str, Any] = {
            "event_type": self.event_type,
            "session_id": self.session_id or "",
            "thread_id": self.thread_id or "",
            "item_id": self.item_id or "",
            "parser_version": self.parser_version,
            "codex_version": self.codex_version or "",
            "warnings": self.warnings,
            "errors": self.errors,
        }
        if self.is_json:
            context["payload"] = self.payload
        else:
            context["raw"] = self.raw_line
        return context


def parse_codex_event_line(line: str, codex_version: str | None = None) -> CodexEventParseResult:
    raw_line = line.rstrip("\n")
    warnings: list[str] = []
    errors: list[str] = []

    if not raw_line.strip():
        errors.append("empty_line")
        return CodexEventParseResult(
            raw_line=raw_line,
            is_json=False,
            payload={"raw": raw_line},
            event_type="empty",
            session_id=None,
            thread_id=None,
            item_id=None,
            warnings=warnings,
            errors=errors,
            codex_version=codex_version,
        )

    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError:
        errors.append("non_json")
        return CodexEventParseResult(
            raw_line=raw_line,
            is_json=False,
            payload={"raw": raw_line},
            event_type="unknown",
            session_id=None,
            thread_id=None,
            item_id=None,
            warnings=warnings,
            errors=errors,
            codex_version=codex_version,
        )

    if not isinstance(payload, dict):
        warnings.append("payload_not_object")
        payload = {"value": payload}

    event_type = _extract_event_type(payload)
    if not event_type:
        warnings.append("missing_event_type")
        event_type = "unknown"

    session_id = _extract_string(payload, ("session_id", "sessionId"))
    thread_id = _extract_string(payload, ("thread_id", "threadId"))
    item_id = _extract_string(payload, ("item_id", "itemId", "id"))

    return CodexEventParseResult(
        raw_line=raw_line,
        is_json=True,
        payload=payload,
        event_type=event_type,
        session_id=session_id,
        thread_id=thread_id,
        item_id=item_id,
        warnings=warnings,
        errors=errors,
        codex_version=codex_version,
    )
