from __future__ import annotations

import os


def resolve_mcp_timeout_seconds() -> float | None:
    raw = os.getenv("CORTEXPILOT_MCP_TIMEOUT_SEC", "").strip()
    if not raw:
        return 600.0
    try:
        value = float(raw)
    except ValueError:
        return 600.0
    return value if value > 0 else None


def resolve_mcp_connect_timeout_sec() -> float | None:
    raw = os.getenv("CORTEXPILOT_MCP_CONNECT_TIMEOUT_SEC", "").strip()
    if not raw:
        return 20.0
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return value if value > 0 else None


def resolve_mcp_cleanup_timeout_sec() -> float | None:
    raw = os.getenv("CORTEXPILOT_MCP_CLEANUP_TIMEOUT_SEC", "").strip()
    if not raw:
        return 5.0
    try:
        value = float(raw)
    except ValueError:
        return 5.0
    return value if value > 0 else None


def resolve_mcp_tool_timeout_sec() -> float | None:
    raw = os.getenv("CORTEXPILOT_MCP_TOOL_TIMEOUT_SEC", "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None
