from __future__ import annotations

import os


def validate_mcp_concurrency(mode: str | None) -> dict:
    raw = (mode or "single").strip().lower()
    single_modes = {"single", "single-client", "stdio", "one"}
    multi_modes = {"multi", "multi-client"}
    proxy_modes = {"proxy", "multi-proxy", "proxy-client"}
    if raw in single_modes:
        return {
            "ok": True,
            "mode": "single",
            "reason": "stdio transport is single-client; defaulting to single",
        }
    if raw in proxy_modes:
        enabled = os.getenv("OPENVIBECODING_MCP_PROXY_ENABLED", "").strip().lower() in {"1", "true", "yes"}
        return {
            "ok": enabled,
            "mode": "proxy",
            "reason": "proxy enabled" if enabled else "proxy disabled; set OPENVIBECODING_MCP_PROXY_ENABLED=1",
        }
    if raw in multi_modes:
        enabled = os.getenv("OPENVIBECODING_MCP_ALLOW_MULTI", "").strip().lower() in {"1", "true", "yes"}
        return {
            "ok": enabled,
            "mode": "multi",
            "reason": "multi-client enabled" if enabled else "multi-client mcp-server not verified; use single",
        }
    return {"ok": False, "mode": raw, "reason": "invalid concurrency mode"}
