from __future__ import annotations

import os
from typing import Iterable


def _is_approved(approved_override: bool = False) -> bool:
    if approved_override:
        return True
    raw = os.getenv("OPENVIBECODING_NETWORK_APPROVED", "").strip().lower()
    return raw in {"1", "true", "yes"}


def validate_network_policy(policy: str | None, requires_network: bool, approved_override: bool = False) -> dict:
    normalized = (policy or "deny").strip().lower()
    if normalized not in {"deny", "on-request", "allow"}:
        return {
            "ok": False,
            "policy": normalized,
            "requires_network": requires_network,
            "reason": "invalid network policy",
        }

    if not requires_network:
        return {"ok": True, "policy": normalized, "requires_network": False, "reason": ""}

    if normalized == "deny":
        return {
            "ok": False,
            "policy": normalized,
            "requires_network": True,
            "reason": "network access denied by policy",
        }

    if normalized == "on-request" and not _is_approved(approved_override):
        return {
            "ok": False,
            "policy": normalized,
            "requires_network": True,
            "reason": "network access requires approval",
        }

    return {"ok": True, "policy": normalized, "requires_network": True, "reason": ""}


def requires_network_items(items: Iterable[object]) -> bool:
    for item in items:
        if item:
            return True
    return False
