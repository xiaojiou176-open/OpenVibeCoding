from __future__ import annotations

from typing import Any

_BROWSER_POLICY_PRESETS = {
    "safe": {
        "profile_mode": "ephemeral",
        "stealth_mode": "none",
        "human_behavior": {"enabled": False, "level": "low"},
    },
    "balanced": {
        "profile_mode": "ephemeral",
        "stealth_mode": "lite",
        "human_behavior": {"enabled": True, "level": "low"},
    },
    "aggressive": {
        "profile_mode": "allow_profile",
        "stealth_mode": "plugin",
        "human_behavior": {"enabled": True, "level": "medium"},
    },
}
_ALLOWED_CUSTOM_ROLES = {"ARCHITECT", "OPS", "OWNER", "TECH_LEAD"}


def _ensure_agent(agent: dict | None, fallback: dict[str, str]) -> dict[str, str]:
    if isinstance(agent, dict) and agent.get("role") and agent.get("agent_id"):
        return {"role": str(agent["role"]), "agent_id": str(agent["agent_id"])}
    return dict(fallback)


def _normalize_answers(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalize_constraints(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalize_browser_policy(raw: Any) -> dict[str, Any]:
    payload = raw if isinstance(raw, dict) else {}
    human = payload.get("human_behavior") if isinstance(payload.get("human_behavior"), dict) else {}
    profile_ref = payload.get("profile_ref") if isinstance(payload.get("profile_ref"), dict) else {}
    cookie_ref = payload.get("cookie_ref") if isinstance(payload.get("cookie_ref"), dict) else {}

    profile_mode = str(payload.get("profile_mode", "ephemeral")).strip().lower()
    if profile_mode not in {"ephemeral", "allow_profile", "cookie_file"}:
        profile_mode = "ephemeral"

    stealth_mode = str(payload.get("stealth_mode", "none")).strip().lower()
    if stealth_mode not in {"none", "lite", "plugin"}:
        stealth_mode = "none"

    level = str(human.get("level", "low")).strip().lower()
    if level not in {"low", "medium", "high"}:
        level = "low"

    return {
        "profile_mode": profile_mode,
        "profile_ref": {
            "profile_dir": str(profile_ref.get("profile_dir", "")).strip(),
            "profile_name": str(profile_ref.get("profile_name", "")).strip(),
        },
        "cookie_ref": {
            "cookie_path": str(cookie_ref.get("cookie_path", "")).strip(),
        },
        "stealth_mode": stealth_mode,
        "human_behavior": {
            "enabled": bool(human.get("enabled", False)),
            "level": level,
        },
    }


def _compact_browser_policy(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_browser_policy(raw)
    compact: dict[str, Any] = {
        "profile_mode": normalized.get("profile_mode"),
        "stealth_mode": normalized.get("stealth_mode"),
        "human_behavior": normalized.get("human_behavior"),
    }

    profile_ref = normalized.get("profile_ref") if isinstance(normalized.get("profile_ref"), dict) else {}
    profile_dir = str(profile_ref.get("profile_dir", "")).strip()
    profile_name = str(profile_ref.get("profile_name", "")).strip()
    if profile_dir or profile_name:
        compact_profile_ref: dict[str, Any] = {}
        if profile_dir:
            compact_profile_ref["profile_dir"] = profile_dir
        if profile_name:
            compact_profile_ref["profile_name"] = profile_name
        compact["profile_ref"] = compact_profile_ref

    cookie_ref = normalized.get("cookie_ref") if isinstance(normalized.get("cookie_ref"), dict) else {}
    cookie_path = str(cookie_ref.get("cookie_path", "")).strip()
    if cookie_path:
        compact["cookie_ref"] = {"cookie_path": cookie_path}

    return compact


def _resolve_intake_browser_policy(payload: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    preset_raw = str(payload.get("browser_policy_preset", "safe")).strip().lower() or "safe"
    preset = preset_raw if preset_raw in {"safe", "balanced", "aggressive", "custom"} else "safe"

    owner = payload.get("owner_agent") if isinstance(payload.get("owner_agent"), dict) else {}
    owner_role = str(owner.get("role", "")).strip().upper()
    requester_role = str(payload.get("requester_role", "")).strip().upper()
    role = requester_role or owner_role or "PM"

    if preset == "custom":
        if role not in _ALLOWED_CUSTOM_ROLES:
            raise ValueError("custom browser policy requires privileged requester role")
        if not isinstance(payload.get("browser_policy"), dict):
            raise ValueError("custom browser policy requires browser_policy payload")
        normalized = _normalize_browser_policy(payload.get("browser_policy"))
        return preset, normalized, "custom policy accepted"

    preset_policy = _BROWSER_POLICY_PRESETS.get(preset, _BROWSER_POLICY_PRESETS["safe"])
    normalized = _normalize_browser_policy(preset_policy)
    return preset, normalized, f"preset applied: {preset}"


def _default_questions(objective: str) -> list[str]:
    return [
        "Which specific directories or files need to change?",
        "What are the acceptance criteria (for example, which tests must pass)?",
        "Is network access or any external dependency allowed?",
        f"Should the scope stay strictly limited to: {objective[:80]}?",
    ]
