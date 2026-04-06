from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from cortexpilot_orch.config import get_runner_config
from cortexpilot_orch.runners import common as runner_common
from cortexpilot_orch.transport.codex_profile_pool import pick_profile


def path_allowed(path: str, allowed_paths: list[Any]) -> bool:
    if not isinstance(path, str) or not path.strip():
        return False
    candidate = Path(path).as_posix().lstrip("./")
    for raw in allowed_paths:
        if not isinstance(raw, str) or not raw.strip():
            continue
        allowed = Path(raw).as_posix().lstrip("./")
        if allowed.endswith("/"):
            if candidate.startswith(allowed.rstrip("/") + "/"):
                return True
        elif candidate == allowed:
            return True
    return False


def mock_output_path(contract: dict[str, Any]) -> str:
    inputs = contract.get("inputs") if isinstance(contract, dict) else {}
    spec = ""
    if isinstance(inputs, dict):
        spec = str(inputs.get("spec", "")).lower()
    preferred = runner_common.extract_required_output(contract)
    if "outside allowed" in spec or "out of bounds" in spec or "out-of-bounds" in spec:
        return "README.md"
    allowed_paths = contract.get("allowed_paths") if isinstance(contract, dict) else []
    allowed_paths = allowed_paths if isinstance(allowed_paths, list) else []
    if preferred:
        if preferred != "patch.diff":
            return preferred
        if path_allowed(preferred, allowed_paths):
            return preferred
    for raw in allowed_paths:
        if not isinstance(raw, str) or not raw.strip():
            continue
        candidate = raw.strip()
        if candidate.endswith("/"):
            return f"{candidate.rstrip('/')}/mock_output.txt"
        name = Path(candidate).name
        if "." in name:
            return candidate
        return f"{candidate.rstrip('/')}/mock_output.txt"
    return preferred or "mock_output.txt"


def resolve_profile() -> str | None:
    profile = os.getenv("CORTEXPILOT_CODEX_PROFILE", "").strip()
    if profile:
        return profile
    return pick_profile()


def resolve_agents_model() -> str | None:
    runner_cfg = get_runner_config()
    return (runner_cfg.agents_model or runner_cfg.codex_model or "gemini-2.5-flash").strip()


def resolve_agents_store() -> bool:
    return bool(get_runner_config().agents_store)


def resolve_agents_base_url() -> str:
    return get_runner_config().agents_base_url


def resolve_equilibrium_base_url() -> str:
    explicit = (get_runner_config().agents_base_url or "").strip()
    if explicit:
        return explicit
    return "http://127.0.0.1:1456/v1"


def equilibrium_health_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/api/health", "", ""))


def equilibrium_healthcheck(base_url: str, timeout_sec: float = 1.0) -> bool:
    health_url = equilibrium_health_url(base_url)
    if not health_url:
        return False
    try:
        with urlopen(health_url, timeout=timeout_sec) as response:  # nosec: B310 local health probe only
            return 200 <= int(getattr(response, "status", 0) or 0) < 300
    except Exception:  # noqa: BLE001
        return False


def is_local_base_url(base_url: str) -> bool:
    base = base_url.strip().lower()
    return base.startswith("http://127.0.0.1") or base.startswith("http://localhost") or base.startswith(
        "http://0.0.0.0"
    )
