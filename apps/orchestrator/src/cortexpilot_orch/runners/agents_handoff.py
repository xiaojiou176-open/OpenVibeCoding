from __future__ import annotations

import json
import os
from typing import Any

_HANDOFF_ROLE_ORDER = [
    "PM",
    "TECH_LEAD",
    "SEARCHER",
    "RESEARCHER",
    "UI_UX",
    "FRONTEND",
    "BACKEND",
    "AI",
    "SECURITY",
    "INFRA",
    "OPS",
    "WORKER",
    "REVIEWER",
    "TEST",
    "TEST_RUNNER",
]
_PRIMARY_HANDOFF_ORDER = ["PM", "TECH_LEAD", "WORKER", "REVIEWER", "TEST_RUNNER"]


def _agent_role(agent: dict[str, Any]) -> str:
    if not isinstance(agent, dict):
        return ""
    role = agent.get("role")
    return str(role).strip().upper() if role else ""


def _validate_handoff_chain(contract: dict[str, Any]) -> tuple[bool, str]:
    chain = contract.get("handoff_chain") if isinstance(contract, dict) else {}
    if not isinstance(chain, dict):
        return True, ""
    enabled = bool(chain.get("enabled", False))
    raw_roles = chain.get("roles") if isinstance(chain.get("roles"), list) else []
    roles = [str(item).strip().upper() for item in raw_roles if str(item).strip()]
    if enabled and not roles:
        return False, "handoff_chain.enabled requires roles"
    if roles:
        last_idx = -1
        for role in roles:
            if role not in _HANDOFF_ROLE_ORDER:
                return False, f"handoff_chain role invalid: {role}"
            idx = _HANDOFF_ROLE_ORDER.index(role)
            if idx <= last_idx:
                return False, "handoff_chain roles out of order"
            last_idx = idx
        primary_present = {role for role in roles if role in _PRIMARY_HANDOFF_ORDER}
        for idx, role in enumerate(_PRIMARY_HANDOFF_ORDER):
            if role in primary_present:
                missing = [r for r in _PRIMARY_HANDOFF_ORDER[:idx] if r not in primary_present]
                if missing:
                    return False, f"handoff_chain missing required roles before {role}: {missing}"
        owner_role = _agent_role(contract.get("owner_agent", {}))
        assigned_role = _agent_role(contract.get("assigned_agent", {}))
        if owner_role and roles[0] != owner_role:
            return False, "handoff_chain must start with owner role"
        if assigned_role and roles[-1] != assigned_role:
            return False, "handoff_chain must end with assigned role"
    return True, ""


def _handoff_chain_roles(contract: dict[str, Any]) -> list[str]:
    chain = contract.get("handoff_chain") if isinstance(contract.get("handoff_chain"), dict) else {}
    enabled = bool(chain.get("enabled", False))
    raw_roles = chain.get("roles") if isinstance(chain.get("roles"), list) else []
    roles = [str(item).strip().upper() for item in raw_roles if str(item).strip()]
    owner_role = _agent_role(contract.get("owner_agent", {}))
    assigned_role = _agent_role(contract.get("assigned_agent", {}))
    if not enabled and not roles:
        return []
    if owner_role and (not roles or roles[0] != owner_role):
        roles = [owner_role] + [item for item in roles if item != owner_role]
    if assigned_role and (not roles or roles[-1] != assigned_role):
        roles = [item for item in roles if item != assigned_role] + [assigned_role]
    return roles


def _handoff_prompt(task_id: str, instruction: str) -> str:
    return (
        "Generate a structured handoff summary for the next agent. "
        "Return JSON only.\n\n"
        f"task_id={task_id}\n"
        f"original_instruction={instruction}"
    )


def _parse_handoff_payload(
    payload_text: str,
    *,
    instruction_sha256: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        return None, {"error": f"handoff output not json: {exc}"}
    if not isinstance(payload, dict):
        return None, {"error": "handoff output not object"}
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None, {"error": "handoff missing summary"}
    risks = payload.get("risks")
    if not isinstance(risks, list):
        return None, {"error": "handoff missing risks"}
    if instruction_sha256:
        payload["instruction_sha256"] = instruction_sha256
    return payload, payload


def _handoff_required(contract: dict[str, Any]) -> bool:
    force = os.getenv("CORTEXPILOT_AGENTS_FORCE_HANDOFF", "").strip().lower() in {"1", "true", "yes"}
    owner = _agent_role(contract.get("owner_agent", {}))
    assigned = _agent_role(contract.get("assigned_agent", {}))
    if force:
        return True
    return bool(owner and assigned and owner != assigned)
