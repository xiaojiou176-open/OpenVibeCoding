from __future__ import annotations

import os


def _to_bool(raw: str, default: bool) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def browser_human_behavior_enabled(default: bool = False) -> bool:
    raw = os.getenv("OPENVIBECODING_BROWSER_HUMAN_BEHAVIOR", "")
    return _to_bool(raw, default)


def browser_human_behavior_level(default: str = "") -> str:
    raw = os.getenv("OPENVIBECODING_BROWSER_HUMAN_BEHAVIOR_LEVEL")
    if raw is None:
        return default
    stripped = raw.strip()
    return stripped or default


def browser_plugin_optional(default: bool = True) -> bool:
    raw = os.getenv("OPENVIBECODING_BROWSER_PLUGIN_OPTIONAL", "")
    return _to_bool(raw, default)


def env_bool(name: str, default: bool = False) -> bool:
    if name == "OPENVIBECODING_BROWSER_HUMAN_BEHAVIOR":
        return browser_human_behavior_enabled(default=default)
    if name == "OPENVIBECODING_BROWSER_PLUGIN_OPTIONAL":
        return browser_plugin_optional(default=default)
    return default


def env_text(name: str, default: str = "") -> str:
    if name == "OPENVIBECODING_BROWSER_HUMAN_BEHAVIOR_LEVEL":
        return browser_human_behavior_level(default=default)
    return default
