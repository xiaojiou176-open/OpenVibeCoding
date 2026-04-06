from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen

from cortexpilot_orch.runners.provider_resolution import ProviderCredentials, resolve_preferred_api_key


def equilibrium_health_url(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, "/api/health", "", ""))


def equilibrium_healthcheck(base_url: str, timeout_sec: float = 1.5) -> bool:
    health_url = equilibrium_health_url(base_url)
    if not health_url:
        return False
    try:
        with urlopen(health_url, timeout=timeout_sec) as response:  # nosec: B310 local health probe only
            return 200 <= int(getattr(response, "status", 0) or 0) < 300
    except Exception:  # noqa: BLE001
        return False


def enable_lock_auto_cleanup_for_coverage() -> dict[str, Any]:
    lock_auto_cleanup_raw = os.getenv("CORTEXPILOT_LOCK_AUTO_CLEANUP", "").strip().lower()
    if lock_auto_cleanup_raw in {"1", "true", "yes"}:
        cleanup_source = "env"
    else:
        os.environ["CORTEXPILOT_LOCK_AUTO_CLEANUP"] = "1"
        cleanup_source = "coverage_execute_default"

    ttl_raw = os.getenv("CORTEXPILOT_LOCK_TTL_SEC", "").strip()
    if ttl_raw:
        ttl_source = "env"
        ttl_display: int | str = ttl_raw
        try:
            ttl_display = int(ttl_raw)
        except ValueError:
            ttl_display = ttl_raw
    else:
        os.environ["CORTEXPILOT_LOCK_TTL_SEC"] = "120"
        ttl_source = "coverage_execute_default"
        ttl_display = 120

    return {
        "enabled": True,
        "source": cleanup_source,
        "ttl_sec": ttl_display,
        "ttl_source": ttl_source,
    }


def enable_chain_subprocess_timeout_for_coverage() -> dict[str, Any]:
    chain_mode_raw = os.getenv("CORTEXPILOT_CHAIN_EXEC_MODE", "").strip().lower()
    if chain_mode_raw:
        chain_mode = chain_mode_raw
        chain_mode_source = "env"
    else:
        os.environ["CORTEXPILOT_CHAIN_EXEC_MODE"] = "subprocess"
        chain_mode = "subprocess"
        chain_mode_source = "coverage_execute_default"

    timeout_raw = os.getenv("CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC", "").strip()
    if timeout_raw:
        timeout_source = "env"
        timeout_display: int | str = timeout_raw
        try:
            timeout_display = int(float(timeout_raw))
        except ValueError:
            timeout_display = timeout_raw
    else:
        os.environ["CORTEXPILOT_CHAIN_SUBPROCESS_TIMEOUT_SEC"] = "300"
        timeout_source = "coverage_execute_default"
        timeout_display = 300

    return {
        "mode": chain_mode,
        "mode_source": chain_mode_source,
        "timeout_sec": timeout_display,
        "timeout_source": timeout_source,
    }


def ensure_coverage_python_env(repo_root: Path) -> dict[str, Any]:
    raw = os.getenv("CORTEXPILOT_PYTHON", "").strip()
    if raw:
        return {"python": raw, "source": "env"}

    candidate = repo_root / ".venv" / "bin" / "python"
    if candidate.exists() and os.access(candidate, os.X_OK):
        value = str(candidate)
        os.environ["CORTEXPILOT_PYTHON"] = value
        return {"python": value, "source": "coverage_execute_default"}

    return {"python": "", "source": "unresolved"}


def prepare_coverage_execute_env(
    mock_mode: bool,
    *,
    load_config_fn: Callable[[], Any],
    repo_root: Path,
    equilibrium_healthcheck_fn: Callable[[str], bool],
    equilibrium_health_url_fn: Callable[[str], str],
) -> dict[str, Any]:
    if mock_mode:
        return {
            "mode": "mock",
            "runner": os.getenv("CORTEXPILOT_RUNNER", "agents") or "agents",
            "lock_auto_cleanup": {"enabled": False, "source": "mock_skip"},
        }

    lock_auto_cleanup = enable_lock_auto_cleanup_for_coverage()
    chain_subprocess = enable_chain_subprocess_timeout_for_coverage()
    python_env = ensure_coverage_python_env(repo_root)

    runner_cfg = load_config_fn().runner
    runner_env_raw = os.getenv("CORTEXPILOT_RUNNER", "").strip().lower()
    runner_name = runner_env_raw or "agents"
    base_url = (runner_cfg.agents_base_url or "").strip()
    api_key = resolve_preferred_api_key(
        ProviderCredentials(
            openai_api_key=(runner_cfg.openai_api_key or "").strip(),
            gemini_api_key=(runner_cfg.gemini_api_key or "").strip(),
            equilibrium_api_key=(runner_cfg.equilibrium_api_key or "").strip(),
        )
    )

    if runner_name != "agents":
        return {
            "mode": "runner_already_selected",
            "runner": runner_name,
            "lock_auto_cleanup": lock_auto_cleanup,
            "chain_subprocess": chain_subprocess,
            "python_env": python_env,
        }
    if api_key:
        return {
            "mode": "llm_key_present",
            "runner": "agents",
            "lock_auto_cleanup": lock_auto_cleanup,
            "chain_subprocess": chain_subprocess,
            "python_env": python_env,
        }
    if base_url:
        return {
            "mode": "agents_base_url_present",
            "runner": "agents",
            "base_url": base_url,
            "lock_auto_cleanup": lock_auto_cleanup,
            "chain_subprocess": chain_subprocess,
            "python_env": python_env,
        }

    fallback_base_url = "http://127.0.0.1:1456/v1"
    if fallback_base_url and equilibrium_healthcheck_fn(fallback_base_url):
        os.environ["CORTEXPILOT_PROVIDER_BASE_URL"] = fallback_base_url
        os.environ.setdefault("CORTEXPILOT_EQUILIBRIUM_API_KEY", "local-equilibrium")
        return {
            "mode": "equilibrium_fallback",
            "runner": "agents",
            "base_url": fallback_base_url,
            "health_url": equilibrium_health_url_fn(fallback_base_url),
            "lock_auto_cleanup": lock_auto_cleanup,
            "chain_subprocess": chain_subprocess,
            "python_env": python_env,
        }

    if not runner_env_raw:
        os.environ["CORTEXPILOT_RUNNER"] = "codex"
        codex_allow_exists = bool(os.getenv("CORTEXPILOT_ALLOW_CODEX_EXEC", "").strip())
        os.environ.setdefault("CORTEXPILOT_ALLOW_CODEX_EXEC", "1")
        return {
            "mode": "codex_runner_fallback",
            "runner": "codex",
            "reason": "missing_llm_key_and_equilibrium_unavailable",
            "lock_auto_cleanup": lock_auto_cleanup,
            "chain_subprocess": chain_subprocess,
            "codex_exec": {
                "enabled": True,
                "source": "env" if codex_allow_exists else "coverage_execute_default",
            },
            "python_env": python_env,
        }

    return {
        "mode": "missing_credentials",
        "runner": "agents",
        "reason": "missing_llm_key_and_no_agents_base_url",
        "lock_auto_cleanup": lock_auto_cleanup,
        "chain_subprocess": chain_subprocess,
        "python_env": python_env,
    }
