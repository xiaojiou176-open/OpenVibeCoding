#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import tomllib

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_mainline_context() -> bool:
    if _is_truthy(os.environ.get("CI")):
        return True
    if str(os.environ.get("CORTEXPILOT_CI_PROFILE", "")).strip().lower() == "strict":
        return True
    if str(os.environ.get("GITHUB_REF_NAME", "")).strip() == "main":
        return True
    if str(os.environ.get("GITHUB_BASE_REF", "")).strip() == "main":
        return True
    return False


def _resolve_process_env_key_candidates(candidates: tuple[str, ...]) -> dict[str, str]:
    for key_name in candidates:
        val = str(os.environ.get(key_name, "")).strip()
        if val:
            return {"env_name": key_name, "value": val, "source": "process_env"}

    return {"env_name": "", "value": "", "source": "none"}


def _resolve_key_candidates(
    candidates: tuple[str, ...], *, allow_local_fallback: bool | None = None
) -> dict[str, str]:
    resolved = _resolve_process_env_key_candidates(candidates)
    if resolved.get("value"):
        return resolved

    if allow_local_fallback is None:
        allow_local_fallback = not _is_mainline_context()
    if not allow_local_fallback:
        return resolved

    for env_file in (Path(".env.local"), Path(".env")):
        dotenv = _parse_dotenv(env_file)
        for key_name in candidates:
            val = str(dotenv.get(key_name, "")).strip()
            if val:
                os.environ.setdefault(key_name, val)
                return {
                    "env_name": key_name,
                    "value": val,
                    "source": f"dotenv:{env_file.name}",
                }

    if shutil_which("zsh"):
        for key_name in candidates:
            try:
                raw = subprocess.check_output(
                    ["zsh", "-lc", f"printenv {key_name} 2>/dev/null || true"],
                    text=True,
                    timeout=5,
                ).strip()
            except Exception:
                raw = ""
            if raw:
                os.environ.setdefault(key_name, raw)
                return {"env_name": key_name, "value": raw, "source": "zsh_env"}

    return resolved


def _codex_config_path() -> Path:
    return Path(
        os.environ.get(
            "CORTEXPILOT_CODEX_CONFIG_PATH",
            str(Path.home() / ".codex" / "config.toml"),
        )
    )


def _load_codex_provider_block() -> tuple[str, dict[str, Any]]:
    config_path = _codex_config_path()
    if not config_path.exists():
        return "", {}
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return "", {}
    provider_name = str(data.get("model_provider") or "").strip().lower()
    providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
    provider_block = providers.get(provider_name) if isinstance(providers, dict) else {}
    if not isinstance(provider_block, dict):
        return provider_name, {}
    return provider_name, provider_block


def _resolve_token_hint(raw: str) -> tuple[str, str]:
    token = raw.strip()
    if not token:
        return "", ""
    if token.startswith("${") and token.endswith("}") and len(token) > 3:
        env_key = token[2:-1].strip()
        return env_key, str(os.environ.get(env_key, "")).strip()
    return "", token


def _resolve_key() -> dict[str, str]:
    return _resolve_key_candidates(("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"))


def _resolve_provider_probe_key() -> dict[str, str]:
    resolved = _resolve_key_candidates(
        ("GEMINI_API_KEY", "OPENAI_API_KEY"),
        allow_local_fallback=not _is_mainline_context(),
    )
    if resolved.get("value"):
        return resolved

    provider_name, provider_block = _load_codex_provider_block()
    if not provider_name or not provider_block:
        return resolved

    env_key = str(provider_block.get("env_key") or "").strip()
    if env_key:
        env_value = str(os.environ.get(env_key, "")).strip()
        if env_value:
            return {"env_name": env_key, "value": env_value, "source": "codex_config_env_key"}

    token_env_key, token_value = _resolve_token_hint(
        str(provider_block.get("experimental_bearer_token") or provider_block.get("api_key") or "")
    )
    if token_value:
        source = f"codex_config_env:{token_env_key}" if token_env_key else "codex_config_inline"
        env_name = token_env_key or "CODEX_CONFIG_BEARER_TOKEN"
        return {"env_name": env_name, "value": token_value, "source": source}

    return resolved


def _resolve_provider_probe_target() -> dict[str, str]:
    provider = str(os.environ.get("CORTEXPILOT_PROVIDER", "")).strip().lower()
    base_url = str(os.environ.get("CORTEXPILOT_PROVIDER_BASE_URL", "")).strip()
    source = "env" if provider or base_url else "none"
    provider_name, provider_block = _load_codex_provider_block()
    if not base_url and provider_block:
        if not provider and provider_name:
            provider = provider_name
            source = "codex_config"
        if not base_url:
            base_url = str(provider_block.get("base_url") or "").strip()
            if base_url:
                source = "codex_config"
    return {
        "provider": provider,
        "base_url": base_url,
        "source": source,
    }


def shutil_which(name: str) -> bool:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        target = Path(path) / name
        if target.exists() and os.access(target, os.X_OK):
            return True
    return False


def _ensure_playwright_browser() -> None:
    browsers_path = str(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")).strip()
    if not browsers_path:
        return
    browser_root = Path(browsers_path)
    if any(browser_root.glob("chromium-*/chrome-*/*")) or any(
        browser_root.glob("chromium_headless_shell-*/chrome-headless-shell-*/*")
    ):
        return
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
        capture_output=True,
        text=True,
    )


def _probe_provider_api(
    *,
    key_env_name: str,
    key_value: str,
    timeout_sec: int,
    provider_name: str = "",
    base_url: str = "",
) -> dict[str, Any]:
    if not key_value:
        return {"attempted": False, "success": False, "provider": "", "error": "missing_key"}

    if key_env_name == "GEMINI_API_KEY":
        provider = "gemini"
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        cmd = [
            "curl",
            "-sS",
            "--max-time",
            str(max(1, timeout_sec)),
            "-H",
            f"x-goog-api-key: {key_value}",
            url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            payload: Any
            try:
                payload = json.loads(proc.stdout)
            except Exception:
                payload = {}
            return {
                "attempted": True,
                "success": True,
                "provider": provider,
                "status": 200,
                "sample_keys": sorted(payload.keys())[:10] if isinstance(payload, dict) else [],
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "attempted": True,
                "success": False,
                "provider": provider,
                "error": f"provider_probe_error: {type(exc).__name__}: {exc}",
            }
    elif key_env_name == "OPENAI_API_KEY" or provider_name or base_url:
        provider = provider_name or "openai"
        normalized_base_url = base_url.strip().rstrip("/")
        url = f"{normalized_base_url}/models" if normalized_base_url else "https://api.openai.com/v1/models"
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Authorization": f"Bearer {key_value}"},
        )
    else:
        return {
            "attempted": False,
            "success": False,
            "provider": "anthropic",
            "error": "provider_api_probe_not_supported",
        }

    try:
        with urllib.request.urlopen(req, timeout=max(1, timeout_sec)) as resp:
            body = resp.read(1024 * 64)
            payload: Any
            try:
                payload = json.loads(body.decode("utf-8", errors="ignore"))
            except Exception:
                payload = {}
            return {
                "attempted": True,
                "success": int(getattr(resp, "status", 0)) < 400,
                "provider": provider,
                "status": int(getattr(resp, "status", 0)),
                "sample_keys": sorted(payload.keys())[:10] if isinstance(payload, dict) else [],
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "attempted": True,
            "success": False,
            "provider": provider,
            "error": f"provider_probe_error: {type(exc).__name__}: {exc}",
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real external web probe via Playwright (non-mock)."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_URL", "https://example.com"),
        help="External URL to probe.",
    )
    parser.add_argument(
        "--title-regex",
        default=os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_TITLE_REGEX", r"Example\s+Domain"),
        help="Expected page title regex.",
    )
    parser.add_argument(
        "--run-id",
        default=os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_RUN_ID", "").strip(),
        help="Optional run id.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_TIMEOUT_MS", "45000")),
        help="Page navigation timeout in milliseconds.",
    )
    parser.add_argument(
        "--provider-api-mode",
        choices=("off", "auto", "require"),
        default=os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_API_MODE", "auto"),
        help="Whether to probe real provider API with resolved key.",
    )
    parser.add_argument(
        "--provider-api-timeout-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_PROVIDER_TIMEOUT_SEC", "15")),
        help="Timeout for provider API probe.",
    )
    parser.add_argument(
        "--heartbeat-interval-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_HEARTBEAT_SEC", "10")),
        help="Heartbeat emission interval in seconds.",
    )
    parser.add_argument(
        "--hard-timeout-sec",
        type=int,
        default=int(os.environ.get("CORTEXPILOT_EXTERNAL_WEB_PROBE_HARD_TIMEOUT_SEC", "180")),
        help="Hard timeout for whole probe process (seconds).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run in headless mode (default true).",
    )
    return parser.parse_args()


def _mask_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _sanitize_report_string(value: str) -> str:
    sanitized = str(value or "")
    sanitized = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", sanitized)
    sanitized = re.sub(r"(?i)(x-goog-api-key[:=]\s*)[A-Za-z0-9._\-]+", r"\1[REDACTED]", sanitized)
    return sanitized


def _sanitize_report_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlsplit(raw)
    hostname = parsed.hostname or ""
    if not hostname:
        return _sanitize_report_string(raw)
    netloc = hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _is_sensitive_report_key(key_name: str) -> bool:
    lowered = str(key_name).lower()
    return any(token in lowered for token in ("token", "secret", "password", "api_key", "bearer"))


def _safe_report_field_name(key_name: str, *, redacted_index: int) -> str:
    raw_key = str(key_name)
    if _is_sensitive_report_key(raw_key):
        return f"redacted_field_{redacted_index}"
    return raw_key


def _summarize_report_field(key_name: str, value: Any) -> Any:
    lowered = str(key_name).lower()
    if _is_sensitive_report_key(lowered):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            "type": "object",
            "items": len(value),
        }
    if isinstance(value, list):
        return {
            "type": "list",
            "items": len(value),
        }
    if isinstance(value, str):
        if lowered.endswith("url") or lowered.endswith("base_url") or ("://" in value and "@" in value):
            return _sanitize_report_url(value)
        return "[STRING]"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def _summarize_report_artifacts(artifacts: dict[str, Any]) -> dict[str, Any]:
    summarized: dict[str, Any] = {}
    redacted_index = 0
    for key, value in artifacts.items():
        if _is_sensitive_report_key(str(key)):
            redacted_index += 1
        field_name = _safe_report_field_name(key, redacted_index=redacted_index)
        summarized[field_name] = _summarize_report_field(str(key), value)
    return summarized


_ALLOWED_PROBE_STAGES = {"starting", "web_probe", "provider_api_probe", "finished", "unknown"}
_ALLOWED_FAILURE_CATEGORIES = {
    "",
    "content_mismatch",
    "hard_timeout",
    "provider_auth_failure",
    "provider_timeout",
    "provider_probe_failure",
    "dns_failure",
    "tls_failure",
    "network_failure",
    "navigation_timeout",
    "timeout",
    "unknown_failure",
}


def _safe_probe_stage(stage: str) -> str:
    normalized = str(stage or "").strip().lower()
    return normalized if normalized in _ALLOWED_PROBE_STAGES else "unknown"


def _safe_failure_category(category: str) -> str:
    normalized = str(category or "").strip().lower()
    return normalized if normalized in _ALLOWED_FAILURE_CATEGORIES else "unknown_failure"


def _safe_report_epoch(timestamp: str) -> int | None:
    value = str(timestamp or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp())


def _write_status_json(
    path: Path,
    *,
    stage: str,
    started_at_epoch: int | None,
    updated_at_epoch: int | None,
) -> None:
    status_payload = {
        "stage": _safe_probe_stage(stage),
        "started_at_epoch": started_at_epoch,
        "updated_at_epoch": updated_at_epoch,
    }
    path.write_text(json.dumps(status_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_report_json(
    path: Path,
    *,
    started_at_epoch: int | None,
    finished_at_epoch: int | None,
    success: bool,
    failure_stage: str,
    failure_category: str,
    title_present: bool,
    artifacts: dict[str, Any],
) -> None:
    report_payload = {
        "started_at_epoch": started_at_epoch,
        "finished_at_epoch": finished_at_epoch,
        "success": success,
        "failure_stage": _safe_probe_stage(failure_stage),
        "failure_category": _safe_failure_category(failure_category),
        "title_present": title_present,
        "artifacts": _summarize_report_artifacts(artifacts),
    }
    path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fallback_probe_url(url: str, error: Exception | None) -> str | None:
    if not error:
        return None
    message = str(error)
    if "ERR_ADDRESS_INVALID" not in message:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return None
    fallback = parsed._replace(scheme="http")
    return urllib.parse.urlunparse(fallback)


def _classify_failure(stage: str, error: Exception | str) -> str:
    text = str(error)
    upper = text.upper()
    if "TITLE MISMATCH" in upper:
        return "content_mismatch"
    if "HARD TIMEOUT" in upper:
        return "hard_timeout"
    if "PROVIDER API PROBE REQUIRED BUT FAILED" in upper or "PROVIDER_PROBE_ERROR" in upper:
        if "401" in text or "403" in text or "MISSING_KEY" in upper:
            return "provider_auth_failure"
        if "TIMEOUT" in upper:
            return "provider_timeout"
        return "provider_probe_failure"
    if "ERR_NAME_NOT_RESOLVED" in upper or "NAME_NOT_RESOLVED" in upper:
        return "dns_failure"
    if "ERR_CERT" in upper or "SSL" in upper or "TLS" in upper or "CERTIFICATE" in upper:
        return "tls_failure"
    if "ERR_CONNECTION" in upper or "ECONNREFUSED" in upper or "NETWORK" in upper:
        return "network_failure"
    if "TIMEOUT" in upper:
        return "navigation_timeout" if stage == "web_probe" else "timeout"
    return "unknown_failure"


def main() -> int:
    args = _parse_args()
    run_id = args.run_id or f"external_web_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(".runtime-cache/test_output/external_web_probe") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    playwright_tmp_dir = Path(os.environ.get("RUNNER_TEMP", str(out_dir / "tmp"))) / "playwright-artifacts"
    playwright_tmp_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(playwright_tmp_dir)

    screenshot_path = out_dir / "page.png"
    report_path = out_dir / "report.json"
    heartbeat_path = out_dir / "heartbeat.json"

    key_info = _resolve_provider_probe_key() if args.provider_api_mode != "off" else _resolve_key()
    provider_probe_target = _resolve_provider_probe_target()

    started_at_iso = _utc_now()
    started_at_epoch = _safe_report_epoch(started_at_iso)
    heartbeat_stage = "starting"
    heartbeat_updated_at_epoch = _utc_now_epoch()
    summary_finished_at_epoch: int | None = None
    summary_success = False
    summary_failure_stage = ""
    summary_failure_category = ""
    summary_title_present = False
    summary_artifacts = {
        "screenshot": str(screenshot_path),
        "heartbeat": str(heartbeat_path),
        "report": str(report_path),
    }

    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at_iso,
        "url": args.url,
        "title_regex": args.title_regex,
        "timeout_ms": args.timeout_ms,
        "hard_timeout_sec": args.hard_timeout_sec,
        "heartbeat_interval_sec": max(1, int(args.heartbeat_interval_sec)),
        "success": False,
        "failure_stage": "",
        "failure_category": "",
        "title": "",
        "errors": [],
        "navigation_attempts": [],
        "key_resolution": {
            "env_name": key_info.get("env_name", ""),
            "source": key_info.get("source", "none"),
            "masked": _mask_key(str(key_info.get("value", ""))),
        },
        "provider_api_probe": {
            "mode": args.provider_api_mode,
            "attempted": False,
            "success": False,
            "provider": "",
            "base_url": provider_probe_target.get("base_url", ""),
            "target_source": provider_probe_target.get("source", "none"),
            "error": "",
        },
        "artifacts": summary_artifacts.copy(),
    }

    hb_lock = threading.Lock()
    hb_stop = threading.Event()

    def set_stage(stage: str) -> None:
        nonlocal heartbeat_stage, heartbeat_updated_at_epoch
        with hb_lock:
            heartbeat_stage = stage
            heartbeat_updated_at_epoch = _utc_now_epoch()
            _write_status_json(
                heartbeat_path,
                stage=heartbeat_stage,
                started_at_epoch=started_at_epoch,
                updated_at_epoch=heartbeat_updated_at_epoch,
            )

    def hb_loop() -> None:
        nonlocal heartbeat_updated_at_epoch
        interval = max(1, int(args.heartbeat_interval_sec))
        while not hb_stop.wait(timeout=interval):
            with hb_lock:
                heartbeat_updated_at_epoch = _utc_now_epoch()
                _write_status_json(
                    heartbeat_path,
                    stage=heartbeat_stage,
                    started_at_epoch=started_at_epoch,
                    updated_at_epoch=heartbeat_updated_at_epoch,
                )
                print(
                    f"💓 [external-web-probe] run_id={run_id} stage={heartbeat_stage} url={args.url}",
                    flush=True,
                )

    def _hard_timeout_handler(*_: Any) -> None:
        raise TimeoutError(f"hard timeout reached: {int(args.hard_timeout_sec)}s")

    signal.signal(signal.SIGALRM, _hard_timeout_handler)
    signal.alarm(max(1, int(args.hard_timeout_sec)))

    hb_thread = threading.Thread(target=hb_loop, name="external-web-probe-heartbeat", daemon=True)
    hb_thread.start()

    try:
        set_stage("web_probe")
        _ensure_playwright_browser()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=args.headless)
            title = ""
            last_nav_error: Exception | None = None
            active_url = args.url
            for attempt in range(1, 4):
                page = browser.new_page()
                try:
                    page.goto(active_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
                    page.wait_for_timeout(400)
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    title = page.title()
                    report["url"] = active_url
                    report["navigation_attempts"].append(
                        {"attempt": attempt, "url": active_url, "status": "success"}
                    )
                    break
                except PlaywrightTimeoutError as exc:
                    last_nav_error = exc
                    report["navigation_attempts"].append(
                        {
                            "attempt": attempt,
                            "url": active_url,
                            "status": "timeout",
                            "category": _classify_failure("web_probe", exc),
                            "error": str(exc),
                        }
                    )
                    report["errors"].append(
                        f"playwright_timeout_attempt_{attempt}: {exc}"
                    )
                    if attempt < 3:
                        time.sleep(2)
                except Exception as exc:  # noqa: BLE001
                    last_nav_error = exc
                    report["navigation_attempts"].append(
                        {
                            "attempt": attempt,
                            "url": active_url,
                            "status": "error",
                            "category": _classify_failure("web_probe", exc),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    report["errors"].append(
                        f"playwright_probe_attempt_{attempt}: {type(exc).__name__}: {exc}"
                    )
                    fallback_url = _fallback_probe_url(active_url, exc)
                    if fallback_url and fallback_url != active_url:
                        active_url = fallback_url
                    if attempt < 3:
                        time.sleep(2)
                finally:
                    page.close()
            if not title:
                raise RuntimeError(str(last_nav_error or "navigation failed"))
            report["title"] = title
            summary_title_present = bool(title)
            if not re.search(args.title_regex, title, flags=re.IGNORECASE):
                raise AssertionError(
                    f"title mismatch: got={title!r}, expected_regex={args.title_regex!r}"
                )
            browser.close()

        if args.provider_api_mode != "off":
            set_stage("provider_api_probe")
            provider_result = _probe_provider_api(
                key_env_name=str(key_info.get("env_name", "")),
                key_value=str(key_info.get("value", "")),
                timeout_sec=max(1, int(args.provider_api_timeout_sec)),
                provider_name=str(provider_probe_target.get("provider", "")),
                base_url=str(provider_probe_target.get("base_url", "")),
            )
            report["provider_api_probe"].update(provider_result)
            if args.provider_api_mode == "require" and not bool(provider_result.get("success")):
                raise RuntimeError(
                    f"provider api probe required but failed: {provider_result.get('error', 'unknown')}"
                )

        report["success"] = True
        summary_success = True
    except PlaywrightTimeoutError as exc:
        report["errors"].append(f"playwright_timeout: {exc}")
        report["failure_stage"] = "web_probe"
        report["failure_category"] = _classify_failure("web_probe", exc)
        summary_failure_stage = "web_probe"
        summary_failure_category = _classify_failure("web_probe", exc)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"probe_error: {exc}")
        current_stage = str(heartbeat_stage or "unknown")
        report["failure_stage"] = current_stage
        report["failure_category"] = _classify_failure(current_stage, exc)
        summary_failure_stage = current_stage
        summary_failure_category = _classify_failure(current_stage, exc)
    finally:
        signal.alarm(0)
        set_stage("finished")
        hb_stop.set()
        hb_thread.join(timeout=2)
        report["finished_at"] = _utc_now()
        summary_finished_at_epoch = _utc_now_epoch()
        if report["success"]:
            report["failure_stage"] = ""
            report["failure_category"] = ""
            summary_failure_stage = ""
            summary_failure_category = ""
        _write_report_json(
            report_path,
            started_at_epoch=started_at_epoch,
            finished_at_epoch=summary_finished_at_epoch,
            success=summary_success,
            failure_stage=summary_failure_stage,
            failure_category=summary_failure_category,
            title_present=summary_title_present,
            artifacts=summary_artifacts,
        )

    print(json.dumps({"report": str(report_path), "success": bool(report["success"])}, ensure_ascii=False))
    return 0 if bool(report["success"]) else 1


if __name__ == "__main__":
    sys.exit(main())
