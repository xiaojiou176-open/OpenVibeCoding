from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable


def _load_registry(repo_root: Path) -> dict:
    override = os.getenv("CORTEXPILOT_TOOL_REGISTRY", "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = (repo_root / path).resolve()
    else:
        path = repo_root / "tooling" / "registry.json"
    if not path.exists():
        if repo_root != _REPO_ROOT:
            fallback = _REPO_ROOT / "tooling" / "registry.json"
            if fallback.exists():
                path = fallback
            else:
                return {"installed": [], "integrated": []}
        else:
            return {"installed": [], "integrated": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"installed": [], "integrated": []}


def validate_integrated_tools(repo_root: Path, required_tools: Iterable[str]) -> dict:
    registry = _load_registry(repo_root)
    integrated = set(str(item).strip() for item in registry.get("integrated", []) if str(item).strip())
    required = set(str(item).strip() for item in required_tools if str(item).strip())
    missing = sorted(required - integrated)
    return {
        "ok": len(missing) == 0,
        "integrated": sorted(integrated),
        "required": sorted(required),
        "missing": missing,
    }
_REPO_ROOT = Path(__file__).resolve().parents[5]
