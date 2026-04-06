#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCH_SRC = ROOT / "apps" / "orchestrator" / "src"
if str(ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(ORCH_SRC))

from cortexpilot_orch.runners.provider_resolution import (  # noqa: E402
    resolve_preferred_api_key,
    resolve_provider_credentials,
    resolve_provider_inventory_id,
    resolve_runtime_base_url_from_env,
    resolve_runtime_model_from_env,
    resolve_runtime_provider,
    resolve_runtime_provider_from_env,
)

try:
    import tomllib
except Exception:  # noqa: BLE001
    tomllib = None


DEFAULT_OUTPUT = ROOT / ".runtime-cache" / "test_output" / "governance" / "upstream" / "provider-runtime-path.report.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_TOKEN_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(x-goog-api-key[:=]\s*)[A-Za-z0-9._\-]+"),
)


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern in _TOKEN_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    return sanitized


def _sanitize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = urllib.parse.urlsplit(raw)
    hostname = parts.hostname or ""
    if not hostname:
        return _sanitize_text(raw)
    netloc = hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _build_public_report(report: dict[str, object]) -> dict[str, object]:
    return {
        "generated_at": report.get("generated_at", ""),
        "upstream_id": report.get("upstream_id", ""),
        "provider": report.get("provider", ""),
        "status": int(report.get("status", 0) or 0),
        "success": bool(report.get("success", False)),
    }


def _emit_report(output_path: Path, *, status: int, success: bool) -> None:
    public_report = {"status": int(status), "success": bool(success)}
    output_path.write_text(json.dumps(public_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"provider_probe_report success={str(success).lower()} status={status}")


def _resolve_codex_config() -> dict[str, str]:
    config_path = Path(os.environ.get("CORTEXPILOT_CODEX_CONFIG_PATH", Path.home() / ".codex" / "config.toml")).expanduser()
    if tomllib is None or not config_path.exists():
        return {"provider": "", "base_url": "", "model": "", "api_key": "", "key_source": "none"}
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"provider": "", "base_url": "", "model": "", "api_key": "", "key_source": "none"}

    provider_name = str(payload.get("model_provider") or "").strip()
    providers = payload.get("model_providers")
    provider_cfg = providers.get(provider_name) if isinstance(providers, dict) else {}
    provider_cfg = provider_cfg if isinstance(provider_cfg, dict) else {}
    api_key = str(provider_cfg.get("experimental_bearer_token") or provider_cfg.get("api_key") or "").strip()
    key_source = "inline" if api_key else "none"
    if api_key.startswith("${") and api_key.endswith("}") and len(api_key) > 3:
        env_name = api_key[2:-1].strip()
        api_key = str(os.environ.get(env_name, "")).strip()
        key_source = f"env:{env_name}" if api_key else "none"
    return {
        "provider": provider_name,
        "base_url": str(provider_cfg.get("base_url") or "").strip(),
        "model": str(payload.get("model") or provider_cfg.get("model") or "").strip(),
        "api_key": api_key,
        "key_source": key_source,
    }


def _request(url: str, *, headers: dict[str, str], data: bytes | None = None, timeout_sec: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read(1024 * 64).decode("utf-8", errors="ignore")
        return int(getattr(resp, "status", 200)), body


def _probe_provider(upstream_id: str, *, api_key: str, base_url: str, model: str) -> int:
    if upstream_id == "provider:gemini":
        status, _ = _request(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
        )
        return status
    if upstream_id == "provider:anthropic":
        status, _ = _request(
            "https://api.anthropic.com/v1/messages",
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            data=json.dumps(
                {
                    "model": model or "claude-3-5-sonnet-latest",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "ping"}],
                }
            ).encode("utf-8"),
        )
        return status
    if upstream_id == "provider:openai":
        status, _ = _request(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        return status
    effective_base_url = base_url.rstrip("/")
    if not effective_base_url:
        raise RuntimeError(f"missing base_url for upstream {upstream_id}")
    status, _ = _request(
        f"{effective_base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    return status


def _parse_args() -> object:
    parser = ArgumentParser(description="Probe a specific upstream provider contract path.")
    parser.add_argument("--upstream-id", default="")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_path = Path(str(getattr(args, "output")))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    provider = resolve_runtime_provider_from_env()
    base_url = resolve_runtime_base_url_from_env()
    model = resolve_runtime_model_from_env(provider)
    credentials = resolve_provider_credentials()
    api_key = resolve_preferred_api_key(credentials, provider)
    key_source = "env"

    if not base_url or not api_key:
        codex_cfg = _resolve_codex_config()
        if codex_cfg["provider"]:
            provider = resolve_runtime_provider(codex_cfg["provider"])
        if not base_url:
            base_url = codex_cfg["base_url"]
        if not model:
            model = codex_cfg["model"]
        if not api_key:
            api_key = codex_cfg["api_key"]
            key_source = codex_cfg["key_source"]

    requested_upstream_id = str(getattr(args, "upstream_id", "") or "").strip()
    upstream_id = requested_upstream_id or resolve_provider_inventory_id(provider)
    provider = resolve_runtime_provider(upstream_id.split(":", 1)[1].strip())

    report = {
        "generated_at": _utc_now(),
        "upstream_id": upstream_id,
        "provider": provider,
        "base_url": _sanitize_url(base_url),
        "model": model,
        "key_source": key_source,
        "success": False,
        "status": 0,
        "error": "",
    }

    try:
        if not api_key:
            raise RuntimeError("missing runtime provider api key")
        status = _probe_provider(upstream_id, api_key=api_key, base_url=base_url, model=model)
        if upstream_id.startswith("provider-gateway:") and status in {401, 403}:
            codex_cfg = _resolve_codex_config()
            fallback_key = codex_cfg.get("api_key", "").strip()
            if fallback_key and fallback_key != api_key:
                fallback_base_url = codex_cfg.get("base_url", "").strip() or base_url
                fallback_model = codex_cfg.get("model", "").strip() or model
                status = _probe_provider(upstream_id, api_key=fallback_key, base_url=fallback_base_url, model=fallback_model)
                if status < 400:
                    api_key = fallback_key
                    base_url = fallback_base_url
                    model = fallback_model
                    key_source = codex_cfg["key_source"]
        report["status"] = status
        report["success"] = status < 400
        if not report["success"]:
            raise RuntimeError(f"provider probe http status {status}")
    except Exception as exc:  # noqa: BLE001
        report["error"] = _sanitize_text(f"{type(exc).__name__}: {exc}")
        _emit_report(output_path, status=int(report.get("status", 0) or 0), success=False)
        return 1

    _emit_report(output_path, status=int(report.get("status", 0) or 0), success=bool(report.get("success", False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
