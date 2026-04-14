from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


PROVIDER_UNSUPPORTED_ERROR = "PROVIDER_UNSUPPORTED"
_PROVIDER_ALIASES = {
    "gemini": "gemini",
    "google": "gemini",
    "google-genai": "gemini",
    "google_genai": "gemini",
    "openai": "openai",
    "openai-compatible": "openai",
    "openai_compatible": "openai",
    "oai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "anthropic-claude": "anthropic",
    "anthropic_claude": "anthropic",
}
_PROVIDER_BASE_URL_ENV_KEYS = ("OPENVIBECODING_PROVIDER_BASE_URL",)
_REPO_ROOT = Path(__file__).resolve().parents[5]
_SWITCHYARD_RUNTIME_INVOKE_PATH = "/v1/runtime/invoke"


class ProviderResolutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"[{code}] {message}")


def _is_switchyard_runtime_base_url(base_url: str | None) -> bool:
    candidate = str(base_url or "").strip()
    if not candidate:
        return False
    try:
        parsed = urlparse(candidate)
    except Exception:
        return False
    path = parsed.path.rstrip("/") or "/"
    return path == _SWITCHYARD_RUNTIME_INVOKE_PATH


def resolve_compat_api_mode(default_api: str | None, *, base_url: str | None = None) -> str:
    if _is_switchyard_runtime_base_url(base_url):
        return "chat_completions"
    normalized = str(default_api or "").strip()
    return normalized or "responses"


@lru_cache(maxsize=1)
def _provider_gateway_ids() -> set[str]:
    inventory_path = _REPO_ROOT / "configs" / "upstream_inventory.json"
    if not inventory_path.exists():
        return set()
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    upstreams = payload.get("upstreams")
    if not isinstance(upstreams, list):
        return set()
    gateways: set[str] = set()
    for entry in upstreams:
        if not isinstance(entry, dict):
            continue
        upstream_id = str(entry.get("id") or "").strip().lower()
        if upstream_id.startswith("provider-gateway:"):
            gateways.add(upstream_id.split(":", 1)[1].strip())
    return gateways


def resolve_runtime_provider(raw_provider: str | None) -> str:
    candidate = str(raw_provider or "").strip().lower()
    if not candidate:
        return "gemini"
    normalized = _PROVIDER_ALIASES.get(candidate)
    if normalized:
        return normalized
    if candidate in _provider_gateway_ids():
        return candidate
    raise ProviderResolutionError(
        PROVIDER_UNSUPPORTED_ERROR,
        f"provider `{candidate}` is not allowlisted; register provider-gateway:{candidate} first",
    )


def resolve_runtime_base_url_from_env(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    for key in _PROVIDER_BASE_URL_ENV_KEYS:
        value = str(source.get(key, "")).strip()
        if value:
            return value
    return ""
