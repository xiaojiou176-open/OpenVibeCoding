from __future__ import annotations

import re
from typing import Any

from cortexpilot_orch.store.run_store import RunStore
from cortexpilot_orch.store.session_map import SessionAliasStore

_THREAD_ID_RE = re.compile(
    r"^(?:urn:uuid:)?[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FLEX_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def is_valid_thread_id(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    return bool(_THREAD_ID_RE.match(candidate) or _FLEX_THREAD_ID_RE.match(candidate))


def is_codex_reply_thread_id(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return False
    return bool(_THREAD_ID_RE.match(candidate))


def extract_thread_id(snapshot: dict[str, Any], extract_first: Any) -> str | None:
    thread_id = extract_first(snapshot, ("threadId", "thread_id", "threadID"), 0, 6)
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()
    return None


def bind_agent_session(
    store: RunStore,
    run_id: str,
    task_id: str,
    alias: str,
    thread_id: str | None,
    session_id: str | None,
) -> None:
    if thread_id:
        store.write_codex_thread_id(run_id, task_id, thread_id)
    if alias and (thread_id or session_id):
        mapping = {
            "alias": alias,
            "session_id": session_id or "",
            "thread_id": thread_id or "",
            "note": "agents_runner",
        }
        store.write_codex_session_map(run_id, mapping)
        if session_id:
            SessionAliasStore().set_alias(
                alias,
                session_id,
                thread_id=thread_id or "",
                note="agents_runner",
            )
        store.append_event(
            run_id,
            {
                "level": "INFO",
                "event": "AGENT_SESSION_BOUND",
                "run_id": run_id,
                "meta": mapping,
            },
        )

