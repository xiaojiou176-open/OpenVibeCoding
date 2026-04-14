from __future__ import annotations

from typing import Any


def _extract_handoff_payload(task_result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(task_result, dict):
        return {}
    for key in ("handoff_payload", "next_payload"):
        value = task_result.get(key)
        if isinstance(value, dict) and value:
            return value
    refs = task_result.get("evidence_refs")
    if isinstance(refs, dict):
        for key in ("handoff_payload", "next_payload"):
            value = refs.get(key)
            if isinstance(value, dict) and value:
                return value
    return {}


def _extract_contracts(task_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(task_result, dict):
        return []
    contracts = task_result.get("contracts")
    if isinstance(contracts, list) and contracts:
        return [item for item in contracts if isinstance(item, dict)]
    refs = task_result.get("evidence_refs")
    if isinstance(refs, dict):
        contracts = refs.get("contracts")
        if isinstance(contracts, list) and contracts:
            return [item for item in contracts if isinstance(item, dict)]
    return []


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _is_subsequence(required: list[str], observed: list[str]) -> bool:
    if not required:
        return True
    cursor = 0
    for role in observed:
        if role == required[cursor]:
            cursor += 1
            if cursor == len(required):
                return True
    return False
