from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


_DEFAULT_ALLOWLIST = {"allow": [], "deny": []}


def _load_mcp_allowlist(repo_root: Path | None) -> tuple[dict, str]:
    if repo_root is None:
        return dict(_DEFAULT_ALLOWLIST), ""
    path = repo_root / "policies" / "mcp_allowlist.json"
    if not path.exists():
        return dict(_DEFAULT_ALLOWLIST), ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return dict(_DEFAULT_ALLOWLIST), f"mcp allowlist parse error: {exc}"
    if not isinstance(payload, dict):
        return dict(_DEFAULT_ALLOWLIST), "mcp allowlist must be an object"
    if "allow" in payload and not isinstance(payload.get("allow"), list):
        return dict(_DEFAULT_ALLOWLIST), "mcp allowlist.allow must be an array"
    if "deny" in payload and not isinstance(payload.get("deny"), list):
        return dict(_DEFAULT_ALLOWLIST), "mcp allowlist.deny must be an array"
    allow = payload.get("allow") if isinstance(payload.get("allow"), list) else []
    deny = payload.get("deny") if isinstance(payload.get("deny"), list) else []
    return {"allow": allow, "deny": deny}, ""


def validate_mcp_tools(
    allowed: Iterable[str] | None,
    required: Iterable[str] | None,
    repo_root: Path | None = None,
) -> dict:
    allowed_set = {item.strip() for item in (allowed or []) if str(item).strip()}
    required_set = {item.strip() for item in (required or []) if str(item).strip()}
    allowlist, load_error = _load_mcp_allowlist(repo_root)
    global_allow = {str(item).strip() for item in allowlist.get("allow", []) if str(item).strip()}
    global_deny = {str(item).strip() for item in allowlist.get("deny", []) if str(item).strip()}
    if global_allow:
        allowed_set = allowed_set & global_allow
    if global_deny:
        allowed_set = {item for item in allowed_set if item not in global_deny}

    missing = sorted(required_set - allowed_set)
    result = {
        "ok": len(missing) == 0,
        "allowed": sorted(allowed_set),
        "required": sorted(required_set),
        "missing": missing,
        "global_allow": sorted(global_allow),
        "global_deny": sorted(global_deny),
    }
    if load_error:
        result["warning"] = "mcp allowlist invalid; fallback to default allowlist"
        result["error"] = load_error
    return result
