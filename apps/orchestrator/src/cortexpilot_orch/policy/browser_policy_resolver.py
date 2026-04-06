from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tooling.browser.repo_chrome_singleton import (
    DEFAULT_PROFILE_DISPLAY_NAME,
    default_repo_browser_root,
    default_repo_chrome_user_data_dir,
)


_ALLOWED_TASK_OVERRIDE_FIELDS = {"stealth_mode", "human_behavior"}
_ALLOWED_PROFILE_MODES = {"ephemeral", "allow_profile", "cookie_file"}
_ALLOWED_STEALTH_MODES = {"none", "lite", "plugin"}
_ALLOWED_BEHAVIOR_LEVELS = {"low", "medium", "high"}
_PRIVILEGED_BREAK_GLASS_ROLES = {"ARCHITECT", "OPS", "OWNER", "TECH_LEAD"}


def _non_empty_text(*values: str, default: str = "") -> str:
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return default


def _raw_to_bool(raw: str, default: bool = False) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _ci_or_container_env() -> bool:
    return (
        os.getenv("CI", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("GITHUB_ACTIONS", "").strip().lower() in {"1", "true", "yes", "on"}
        or os.getenv("CORTEXPILOT_CI_CONTAINER", "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _normalize_profile_mode(raw: Any, default: str = "ephemeral") -> str:
    value = str(raw or default).strip().lower()
    if value in _ALLOWED_PROFILE_MODES:
        return value
    if value in {"profile"}:
        return "allow_profile"
    if value in {"cookie"}:
        return "cookie_file"
    return "ephemeral"


def _normalize_stealth_mode(raw: Any, default: str = "none") -> str:
    value = str(raw or default).strip().lower()
    return value if value in _ALLOWED_STEALTH_MODES else "none"


def _normalize_behavior_level(raw: Any, default: str = "low") -> str:
    value = str(raw or default).strip().lower()
    return value if value in _ALLOWED_BEHAVIOR_LEVELS else "low"


def _normalize_full_policy(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    profile_ref = payload.get("profile_ref") if isinstance(payload.get("profile_ref"), dict) else {}
    cookie_ref = payload.get("cookie_ref") if isinstance(payload.get("cookie_ref"), dict) else {}
    human = payload.get("human_behavior") if isinstance(payload.get("human_behavior"), dict) else {}

    profile_dir = str(profile_ref.get("profile_dir", "")).strip() if isinstance(profile_ref.get("profile_dir"), str) else ""
    profile_name = str(profile_ref.get("profile_name", "")).strip() if isinstance(profile_ref.get("profile_name"), str) else ""
    cookie_path = str(cookie_ref.get("cookie_path", "")).strip() if isinstance(cookie_ref.get("cookie_path"), str) else ""

    return {
        "profile_mode": _normalize_profile_mode(payload.get("profile_mode"), "ephemeral"),
        "profile_ref": {
            "profile_dir": profile_dir,
            "profile_name": profile_name,
        },
        "cookie_ref": {
            "cookie_path": cookie_path,
        },
        "stealth_mode": _normalize_stealth_mode(payload.get("stealth_mode"), "none"),
        "human_behavior": {
            "enabled": bool(human.get("enabled", False)),
            "level": _normalize_behavior_level(human.get("level"), "low"),
        },
    }


def _normalize_task_override(raw: Any) -> tuple[dict[str, Any], list[str]]:
    payload = raw if isinstance(raw, dict) else {}
    override: dict[str, Any] = {}
    rejected: list[str] = []

    for key, value in payload.items():
        if key not in _ALLOWED_TASK_OVERRIDE_FIELDS:
            rejected.append(str(key))
            continue
        if key == "stealth_mode":
            override["stealth_mode"] = _normalize_stealth_mode(value, "none")
            continue
        if key == "human_behavior":
            if isinstance(value, dict):
                override["human_behavior"] = {
                    "enabled": bool(value.get("enabled", False)),
                    "level": _normalize_behavior_level(value.get("level"), "low"),
                }
            else:
                override["human_behavior"] = {"enabled": False, "level": "low"}
    return override, rejected


def _env_default_policy() -> dict[str, Any]:
    default_profile_mode = _default_profile_mode()
    profile_mode = _normalize_profile_mode(
        _non_empty_text(
            os.getenv("CORTEXPILOT_BROWSER_PROFILE_MODE", ""),
            default=default_profile_mode,
        ),
        default_profile_mode,
    )
    profile_dir = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_PROFILE_DIR", ""),
        default="",
    )
    profile_name = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_PROFILE_NAME", ""),
        default=_default_profile_name(profile_mode),
    )
    cookie_path = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_COOKIE_PATH", ""),
        default="",
    )
    stealth_mode = _normalize_stealth_mode(
        _non_empty_text(
            os.getenv("CORTEXPILOT_BROWSER_STEALTH_MODE", ""),
            default="none",
        ),
        "none",
    )
    behavior_enabled = _raw_to_bool(os.getenv("CORTEXPILOT_BROWSER_HUMAN_BEHAVIOR", ""), default=False)
    behavior_level = _normalize_behavior_level(
        _non_empty_text(os.getenv("CORTEXPILOT_BROWSER_HUMAN_BEHAVIOR_LEVEL", ""), default="low"),
        "low",
    )
    plugin_optional = _raw_to_bool(os.getenv("CORTEXPILOT_BROWSER_PLUGIN_OPTIONAL", ""), default=True)
    return {
        "profile_mode": profile_mode,
        "profile_ref": {"profile_dir": profile_dir, "profile_name": profile_name or "Default"},
        "cookie_ref": {"cookie_path": cookie_path},
        "stealth_mode": stealth_mode,
        "human_behavior": {"enabled": behavior_enabled, "level": behavior_level},
        "plugin_optional": plugin_optional,
    }


def _default_chrome_profile_dir() -> Path | None:
    return default_repo_chrome_user_data_dir().resolve()


def _local_profile_defaults_enabled() -> bool:
    if _ci_or_container_env():
        return False
    if _non_empty_text(
        os.getenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", ""),
        os.getenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", ""),
        default="",
    ):
        return False
    return True


def _default_profile_mode() -> str:
    return "allow_profile" if _local_profile_defaults_enabled() else "ephemeral"


def _default_profile_name(profile_mode: str) -> str:
    if profile_mode == "allow_profile" and _local_profile_defaults_enabled():
        return DEFAULT_PROFILE_DISPLAY_NAME
    return "Default"


def _forced_ephemeral_reason() -> str:
    if _ci_or_container_env():
        return "ci_or_container"
    if _non_empty_text(
        os.getenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT", ""),
        os.getenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT", ""),
        default="",
    ):
        return "clean_room"
    return ""


def _explicit_profile_env_overrides() -> tuple[dict[str, Any], dict[str, str]]:
    overrides: dict[str, Any] = {}
    sources: dict[str, str] = {}

    profile_mode = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_PROFILE_MODE", ""),
        os.getenv("CORTEXPILOT_WEB_PROFILE_MODE", ""),
        default="",
    )
    if profile_mode:
        overrides["profile_mode"] = _normalize_profile_mode(profile_mode, "ephemeral")
        sources["profile_mode"] = "env"

    profile_dir = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_PROFILE_DIR", ""),
        os.getenv("CORTEXPILOT_WEB_PROFILE_DIR", ""),
        default="",
    )
    if profile_dir:
        overrides["profile_ref.profile_dir"] = profile_dir
        sources["profile_ref.profile_dir"] = "env"

    profile_name = _non_empty_text(
        os.getenv("CORTEXPILOT_BROWSER_PROFILE_NAME", ""),
        os.getenv("CORTEXPILOT_WEB_PROFILE_NAME", ""),
        default="",
    )
    if profile_name:
        overrides["profile_ref.profile_name"] = profile_name
        sources["profile_ref.profile_name"] = "env"

    return overrides, sources


def _apply_default_profile_dir(policy: dict[str, Any], policy_source: dict[str, str]) -> None:
    if str(policy.get("profile_mode", "")).strip().lower() != "allow_profile":
        return
    profile_ref = policy.get("profile_ref") if isinstance(policy.get("profile_ref"), dict) else {}
    if _non_empty_text(str(profile_ref.get("profile_dir", "")), default=""):
        return
    default_profile_dir = _default_chrome_profile_dir()
    if default_profile_dir is None:
        return
    profile_ref["profile_dir"] = str(default_profile_dir)
    policy["profile_ref"] = profile_ref
    policy_source["profile_ref.profile_dir"] = "default"


def _apply_default_profile_name(policy: dict[str, Any], policy_source: dict[str, str]) -> None:
    if str(policy.get("profile_mode", "")).strip().lower() != "allow_profile":
        return
    profile_ref = policy.get("profile_ref") if isinstance(policy.get("profile_ref"), dict) else {}
    if _non_empty_text(str(profile_ref.get("profile_name", "")), default=""):
        return
    profile_ref["profile_name"] = _default_profile_name("allow_profile")
    policy["profile_ref"] = profile_ref
    policy_source["profile_ref.profile_name"] = "default"


def _profile_allowlist_roots() -> list[Path]:
    configured = _non_empty_text(os.getenv("CORTEXPILOT_BROWSER_PROFILE_ALLOWLIST", ""), default="")
    if configured:
        items = [item.strip() for item in configured.split(",") if item.strip()]
    else:
        items = [str(default_repo_browser_root())]
    roots: list[Path] = []
    seen: set[str] = set()
    for item in items:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(path)
    return roots


def _is_profile_dir_allowed(path_value: str) -> bool:
    if not path_value:
        return False
    target = Path(path_value).expanduser()
    target = target.resolve() if target.is_absolute() else (Path.cwd() / target).resolve()
    for root in _profile_allowlist_roots():
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def resolve_browser_policy(
    *,
    contract_policy: dict[str, Any] | None,
    task_policy: dict[str, Any] | None,
    requested_by: dict[str, Any] | None = None,
    source: str,
    task_id: str,
) -> dict[str, Any]:
    role = str((requested_by or {}).get("role", "")).strip().upper()
    break_glass = _raw_to_bool(os.getenv("CORTEXPILOT_BROWSER_BREAK_GLASS", ""), default=False)
    break_glass_allowed = break_glass and role in _PRIVILEGED_BREAK_GLASS_ROLES

    requested = _env_default_policy()
    policy_source = {
        "profile_mode": "env",
        "profile_ref.profile_dir": "env",
        "profile_ref.profile_name": "env",
        "cookie_ref.cookie_path": "env",
        "stealth_mode": "env",
        "human_behavior.enabled": "env",
        "human_behavior.level": "env",
        "plugin_optional": "env",
    }

    if isinstance(contract_policy, dict):
        contract = _normalize_full_policy(contract_policy)
        requested["profile_mode"] = contract["profile_mode"]
        requested["profile_ref"] = dict(contract["profile_ref"])
        requested["cookie_ref"] = dict(contract["cookie_ref"])
        requested["stealth_mode"] = contract["stealth_mode"]
        requested["human_behavior"] = dict(contract["human_behavior"])
        for key in (
            "profile_mode",
            "profile_ref.profile_dir",
            "profile_ref.profile_name",
            "cookie_ref.cookie_path",
            "stealth_mode",
            "human_behavior.enabled",
            "human_behavior.level",
        ):
            policy_source[key] = "contract"

    env_overrides, env_sources = _explicit_profile_env_overrides()
    if "profile_mode" in env_overrides:
        requested["profile_mode"] = env_overrides["profile_mode"]
        policy_source["profile_mode"] = env_sources["profile_mode"]
    if "profile_ref.profile_dir" in env_overrides:
        requested.setdefault("profile_ref", {})
        requested["profile_ref"]["profile_dir"] = env_overrides["profile_ref.profile_dir"]
        policy_source["profile_ref.profile_dir"] = env_sources["profile_ref.profile_dir"]
    if "profile_ref.profile_name" in env_overrides:
        requested.setdefault("profile_ref", {})
        requested["profile_ref"]["profile_name"] = env_overrides["profile_ref.profile_name"]
        policy_source["profile_ref.profile_name"] = env_sources["profile_ref.profile_name"]

    _apply_default_profile_dir(requested, policy_source)
    _apply_default_profile_name(requested, policy_source)

    task_override, rejected_fields = _normalize_task_override(task_policy)
    if "stealth_mode" in task_override:
        requested["stealth_mode"] = task_override["stealth_mode"]
        policy_source["stealth_mode"] = "task"
    if "human_behavior" in task_override:
        requested["human_behavior"] = dict(task_override["human_behavior"])
        policy_source["human_behavior.enabled"] = "task"
        policy_source["human_behavior.level"] = "task"

    effective = {
        "profile_mode": requested["profile_mode"],
        "profile_ref": dict(requested["profile_ref"]),
        "cookie_ref": dict(requested["cookie_ref"]),
        "stealth_mode": requested["stealth_mode"],
        "human_behavior": dict(requested["human_behavior"]),
        "plugin_optional": bool(requested.get("plugin_optional", True)),
    }

    events: list[dict[str, Any]] = []
    fallback_chain: list[str] = []

    for field in rejected_fields:
        events.append(
            {
                "event": "BROWSER_POLICY_FIELD_REJECTED",
                "level": "WARN",
                "meta": {
                    "source": source,
                    "task_id": task_id,
                    "field": field,
                    "reason": "task_override_not_allowed",
                },
            }
        )

    if effective["profile_mode"] == "allow_profile":
        profile_dir = str(effective.get("profile_ref", {}).get("profile_dir", "")).strip()
        forced_ephemeral_reason = _forced_ephemeral_reason()
        if forced_ephemeral_reason:
            effective["profile_mode"] = "ephemeral"
            effective["profile_ref"] = {"profile_dir": "", "profile_name": ""}
            effective["cookie_ref"] = {"cookie_path": ""}
            fallback_chain.append("allow_profile->ephemeral")
            events.append(
                {
                    "event": "BROWSER_POLICY_GUARD_BLOCK",
                    "level": "WARN",
                    "meta": {
                        "source": source,
                        "task_id": task_id,
                        "rule": "force_ephemeral_environment",
                        "action": "downgrade_to_ephemeral",
                        "reason": forced_ephemeral_reason,
                    },
                }
            )
        elif not _is_profile_dir_allowed(profile_dir):
            if break_glass_allowed:
                events.append(
                    {
                        "event": "BROWSER_BREAK_GLASS_ENABLED",
                        "level": "WARN",
                        "meta": {"source": source, "task_id": task_id, "role": role},
                    }
                )
                events.append(
                    {
                        "event": "BROWSER_POLICY_OVERRIDE_APPROVED",
                        "level": "WARN",
                        "meta": {
                            "source": source,
                            "task_id": task_id,
                            "rule": "profile_allowlist",
                            "role": role,
                        },
                    }
                )
            else:
                effective["profile_mode"] = "ephemeral"
                effective["profile_ref"] = {"profile_dir": "", "profile_name": ""}
                fallback_chain.append("allow_profile->ephemeral")
                events.append(
                    {
                        "event": "BROWSER_POLICY_GUARD_BLOCK",
                        "level": "WARN",
                        "meta": {
                            "source": source,
                            "task_id": task_id,
                            "rule": "profile_allowlist",
                            "action": "downgrade_to_ephemeral",
                            "reason": "profile_dir_not_allowlisted",
                        },
                    }
                )

    if effective["profile_mode"] == "cookie_file":
        forced_ephemeral_reason = _forced_ephemeral_reason()
        if forced_ephemeral_reason:
            effective["profile_mode"] = "ephemeral"
            effective["cookie_ref"] = {"cookie_path": ""}
            fallback_chain.append("cookie_file->ephemeral")
            events.append(
                {
                    "event": "BROWSER_POLICY_GUARD_BLOCK",
                    "level": "WARN",
                    "meta": {
                        "source": source,
                        "task_id": task_id,
                        "rule": "force_ephemeral_environment",
                        "action": "downgrade_to_ephemeral",
                        "reason": forced_ephemeral_reason,
                    },
                }
            )

    behavior_level = str(effective.get("human_behavior", {}).get("level", "low"))
    if (
        effective["profile_mode"] == "allow_profile"
        and effective["stealth_mode"] == "plugin"
        and behavior_level == "high"
    ):
        if break_glass_allowed:
            events.append(
                {
                    "event": "BROWSER_POLICY_OVERRIDE_APPROVED",
                    "level": "WARN",
                    "meta": {
                        "source": source,
                        "task_id": task_id,
                        "rule": "high_risk_combo",
                        "role": role,
                    },
                }
            )
        else:
            effective["stealth_mode"] = "lite"
            fallback_chain.append("plugin->lite")
            events.append(
                {
                    "event": "BROWSER_POLICY_GUARD_BLOCK",
                    "level": "WARN",
                    "meta": {
                        "source": source,
                        "task_id": task_id,
                        "rule": "high_risk_combo",
                        "action": "downgrade_stealth",
                        "reason": "allow_profile+plugin+high",
                    },
                }
            )

    events.append(
        {
            "event": "BROWSER_POLICY_RESOLVED",
            "level": "INFO",
            "meta": {
                "source": source,
                "task_id": task_id,
                "requested_policy": requested,
                "effective_policy": effective,
                "policy_source": policy_source,
                "fallback_chain": fallback_chain,
            },
        }
    )

    return {
        "requested_policy": requested,
        "effective_policy": effective,
        "policy_source": policy_source,
        "fallback_chain": fallback_chain,
        "events": events,
        "break_glass": break_glass_allowed,
    }
