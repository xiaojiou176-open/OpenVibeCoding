from __future__ import annotations

import os
from typing import Iterable


_SAMPLING_TOOL_NAMES = {"sampling", "mcp.sampling"}


def _sampling_approved() -> bool:
    raw = os.getenv("CORTEXPILOT_SAMPLING_APPROVED", "").strip().lower()
    return raw in {"1", "true", "yes"}


def validate_sampling_policy(allowed_tools: Iterable[str] | None) -> dict:
    allowed_set = {item.strip() for item in (allowed_tools or []) if str(item).strip()}
    wants_sampling = any(tool in _SAMPLING_TOOL_NAMES for tool in allowed_set)

    if not wants_sampling:
        return {
            "ok": True,
            "requested": False,
            "approved": False,
            "allowed": sorted(allowed_set),
            "reason": "",
        }

    if not _sampling_approved():
        return {
            "ok": False,
            "requested": True,
            "approved": False,
            "allowed": sorted(allowed_set),
            "reason": "sampling requires explicit approval",
        }

    return {
        "ok": True,
        "requested": True,
        "approved": True,
        "allowed": sorted(allowed_set),
        "reason": "",
    }


def is_sampling_tool(tool_name: str) -> bool:
    return tool_name in _SAMPLING_TOOL_NAMES
