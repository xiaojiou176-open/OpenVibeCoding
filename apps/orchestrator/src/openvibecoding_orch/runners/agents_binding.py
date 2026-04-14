from __future__ import annotations

import re
from typing import Any

from openvibecoding_orch.store.session_map import SessionAliasStore

_THREAD_ID_RE = re.compile(
    r"^(?:urn:uuid:)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FLEX_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _resolve_assigned_agent(contract: dict[str, Any]) -> dict[str, Any]:
    assigned = contract.get("assigned_agent", {})
    return assigned if isinstance(assigned, dict) else {}


def _is_valid_thread_id(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    return bool(_THREAD_ID_RE.match(candidate) or _FLEX_THREAD_ID_RE.match(candidate))


def _extract_evidence_refs(payload: dict[str, Any]) -> dict[str, Any]:
    refs = payload.get("evidence_refs")
    return refs if isinstance(refs, dict) else {}


def _extract_binding_from_result(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    refs = _extract_evidence_refs(payload)
    thread_id = refs.get("thread_id") or refs.get("codex_thread_id")
    session_id = refs.get("session_id") or refs.get("codex_session_id")
    thread_id = thread_id if isinstance(thread_id, str) and _is_valid_thread_id(thread_id) else None
    session_id = session_id if isinstance(session_id, str) and session_id.strip() else None
    return thread_id, session_id


def _resolve_session_binding(contract: dict[str, Any]) -> tuple[str | None, str | None]:
    assigned = _resolve_assigned_agent(contract)
    thread_id = assigned.get("codex_thread_id") if isinstance(assigned.get("codex_thread_id"), str) else ""
    thread_id = thread_id.strip() if thread_id else ""
    session_id = ""
    alias = assigned.get("agent_id") if isinstance(assigned.get("agent_id"), str) else ""
    if not thread_id and alias:
        record = SessionAliasStore().resolve(alias)
        if record is not None:
            thread_id = record.thread_id.strip()
            session_id = record.session_id.strip()
    if not _is_valid_thread_id(thread_id):
        thread_id = ""
    return thread_id or None, session_id or None
