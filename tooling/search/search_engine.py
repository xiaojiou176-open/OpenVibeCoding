from __future__ import annotations

import fnmatch
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

from tooling.browser.human_behavior import apply_human_behavior
from tooling.browser.policy import (
    browser_human_behavior_enabled,
    browser_human_behavior_level,
    browser_plugin_optional,
)
from tooling.browser.session_manager import BrowserSessionHandle, BrowserSessionManager
from tooling.browser.stealth_provider import StealthProvider


def _close_browser_session_strict(session: BrowserSessionHandle) -> None:
    session.close()


def _mock_results(query: str) -> list[dict[str, str]]:
    return [
        {"title": f"{query} - official", "href": "https://ai.google.dev/"},
        {"title": f"{query} - docs", "href": "https://ai.google.dev/gemini-api/docs"},
        {"title": f"{query} - github", "href": "https://github.com"},
    ]


def _duckduckgo_results(query: str) -> list[dict[str, str]]:
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        hits = ddgs.text(query, max_results=3)
        return [{"title": item.get("title", ""), "href": item.get("href", "")} for item in hits]


def _browser_search(query: str, browser_policy: dict[str, Any] | None = None) -> tuple[list[dict[str, str]], str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return [], f"playwright_unavailable: {exc}"

    url = f"https://duckduckgo.com/?q={quote_plus(query)}"
    session: BrowserSessionHandle | None = None

    try:
        with sync_playwright() as p:
            try:
                session_manager = _web_session_manager(browser_policy)
                stealth_provider = _web_stealth_provider(browser_policy)
                session = session_manager.open_page(p, extra_launch_args=stealth_provider.launch_args())
                page = session.page
                stealth_provider.apply(page=page, context=session.context)

                page.goto(url)
                behavior = _web_human_behavior(browser_policy)
                apply_human_behavior(page, enabled=behavior["enabled"], level=behavior["level"])
                page.wait_for_timeout(1000)
                results = page.evaluate(
                    """() => Array.from(document.querySelectorAll('a[data-testid=\"result-title-a\"]'))
                        .slice(0, 3)
                        .map(a => ({ title: a.textContent || '', href: a.href || '' }))"""
                )
                session_to_close = session
                session = None
                _close_browser_session_strict(session_to_close)
            finally:
                if session is not None:
                    _close_browser_session_strict(session)
                    session = None
    except Exception as exc:  # noqa: BLE001
        return [], f"browser_ddg_failed: {exc}"

    if not isinstance(results, list):
        return [], "browser_parse_failed"
    normalized: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        href = item.get("href", "")
        normalized.append({"title": str(title), "href": str(href)})
    if not normalized:
        return [], "browser_parse_failed"
    return normalized, None


def _web_allowlist() -> list[str]:
    raw = os.getenv("CORTEXPILOT_WEB_ALLOWLIST", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "https://gemini.google.com/",
        "https://*.google.com/",
        "https://chatgpt.com/",
        "https://*.openai.com/",
        "https://grok.com/",
    ]


def _url_allowed(url: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    cleaned = url.strip()
    if not cleaned:
        return False
    parsed = urlparse(cleaned)
    url_scheme = parsed.scheme.lower()
    url_host = parsed.netloc.lower()
    url_path = parsed.path or "/"
    url_lower = cleaned.lower()

    for pattern in allowlist:
        raw = pattern.strip()
        if not raw:
            continue
        pat = raw.lower()

        if "://" in pat:
            pat_parsed = urlparse(pat)
            pat_scheme = pat_parsed.scheme.lower()
            if pat_scheme and url_scheme and pat_scheme != url_scheme:
                continue
            pat_host = pat_parsed.netloc.lower()
            pat_path = pat_parsed.path or ""

            if pat_host:
                if any(token in pat_host for token in ("*", "?", "[")):
                    if not fnmatch.fnmatchcase(url_host, pat_host):
                        continue
                elif url_host != pat_host:
                    continue

            if pat_path:
                if any(token in pat_path for token in ("*", "?", "[")):
                    if fnmatch.fnmatchcase(url_lower, pat):
                        return True
                    continue
                if not url_path.startswith(pat_path):
                    continue
            return True

        if any(token in pat for token in ("*", "?", "[")):
            if fnmatch.fnmatchcase(url_host, pat) or fnmatch.fnmatchcase(url_lower, pat):
                return True
            continue

        if url_host == pat:
            return True
        if url_lower.startswith(pat):
            return True
    return False


def _runtime_root() -> Path:
    return Path(os.getenv("CORTEXPILOT_RUNTIME_ROOT", ".runtime-cache/cortexpilot")).resolve()


def _web_headless() -> bool:
    raw = os.getenv("CORTEXPILOT_WEB_HEADLESS", "").strip().lower()
    if raw in {"0", "false", "no"}:
        return False
    if raw in {"1", "true", "yes"}:
        return True
    return False


def _web_profile_mode(browser_policy: dict[str, Any] | None = None) -> str:
    if isinstance(browser_policy, dict):
        value = browser_policy.get("profile_mode")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    raw = os.getenv("CORTEXPILOT_BROWSER_PROFILE_MODE", "").strip().lower()
    if raw:
        return raw
    legacy = os.getenv("CORTEXPILOT_WEB_PROFILE_MODE", "").strip().lower()
    if legacy:
        return legacy
    return "ephemeral"


def _web_stealth_mode(browser_policy: dict[str, Any] | None = None) -> str:
    if isinstance(browser_policy, dict):
        value = browser_policy.get("stealth_mode")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    raw = os.getenv("CORTEXPILOT_BROWSER_STEALTH_MODE", "").strip().lower()
    if raw:
        return raw
    return os.getenv("CORTEXPILOT_WEB_STEALTH_MODE", "none").strip().lower() or "none"


def _web_human_behavior(browser_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(browser_policy, dict):
        payload = browser_policy.get("human_behavior")
        if isinstance(payload, dict):
            return {
                "enabled": bool(payload.get("enabled", False)),
                "level": str(payload.get("level", "low")).strip() or "low",
            }
    return {
        "enabled": browser_human_behavior_enabled(default=False),
        "level": browser_human_behavior_level(default="low"),
    }


def _web_session_manager(browser_policy: dict[str, Any] | None = None) -> BrowserSessionManager:
    if isinstance(browser_policy, dict) and browser_policy:
        return BrowserSessionManager.from_policy(
            headless=_web_headless(),
            policy=browser_policy,
            default_profile_mode=_web_profile_mode(browser_policy),
        )
    return BrowserSessionManager.from_env(
        headless=_web_headless(),
        default_profile_mode=_web_profile_mode(browser_policy),
    )


def _web_stealth_provider(browser_policy: dict[str, Any] | None = None) -> StealthProvider:
    if isinstance(browser_policy, dict) and browser_policy:
        return StealthProvider.from_policy(browser_policy)
    return StealthProvider(
        mode=_web_stealth_mode(browser_policy),
        plugin_optional=browser_plugin_optional(default=True),
    )


def _web_artifact_dir(provider: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    suffix = uuid.uuid4().hex[:8]
    path = _runtime_root() / "web-search" / provider / f"{stamp}_{suffix}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_web_error_artifacts(artifacts_dir: Path, error: str, page: Any | None) -> dict[str, str | None]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    error_path = artifacts_dir / "error.txt"
    error_path.write_text(error, encoding="utf-8")
    screenshot_path = artifacts_dir / "screenshot.png"
    html_path = artifacts_dir / "page.html"
    if page is not None:
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except TypeError:
            try:
                page.screenshot(path=str(screenshot_path), _full_page=True)
            except TypeError:
                try:
                    page.screenshot(str(screenshot_path), True)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return {
        "error": str(error_path),
        "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
        "html": str(html_path) if html_path.exists() else None,
    }


def _pick_chat_input_locator(page: Any) -> Any | None:
    selectors = (
        "textarea",
        "input[type='text']",
        "[role='textbox'][contenteditable='true']",
        "[contenteditable='true'][role='textbox']",
        "[aria-label='Enter a prompt for Gemini'][contenteditable='true']",
        ".ql-editor[contenteditable='true']",
    )
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            return locator.first
    return None


def _chat_provider_search(
    query: str,
    provider: str,
    url: str,
    browser_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    allowlist = _web_allowlist()
    artifacts_dir = _web_artifact_dir(provider)
    policy_events: list[dict[str, Any]] = []

    if not _url_allowed(url, allowlist):
        error = f"url not allowlisted: {url}"
        return {
            "ok": False,
            "results": [],
            "meta": {
                "artifacts": _write_web_error_artifacts(artifacts_dir, error, None),
                "context": {},
                "policy_events": policy_events,
            },
            "error": error,
        }

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        error = f"playwright_unavailable: {exc}"
        return {
            "ok": False,
            "results": [],
            "meta": {
                "artifacts": _write_web_error_artifacts(artifacts_dir, error, None),
                "context": {},
                "policy_events": policy_events,
            },
            "error": error,
        }

    response_text = ""
    page = None
    session: BrowserSessionHandle | None = None
    context_meta: dict[str, Any] = {}
    stealth_meta: dict[str, Any] = {}
    behavior_meta: dict[str, Any] = {}

    with sync_playwright() as p:
        try:
            try:
                session_manager = _web_session_manager(browser_policy)
                stealth_provider = _web_stealth_provider(browser_policy)

                session = session_manager.open_page(p, extra_launch_args=stealth_provider.launch_args())
                context_meta = session.metadata
                policy_events.append(session_manager.profile_event(context_meta))

                page = session.page
                stealth_meta = stealth_provider.apply(page=page, context=session.context)
                policy_events.extend(stealth_meta.get("events", []))

                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                behavior = _web_human_behavior(browser_policy)
                behavior_meta = apply_human_behavior(page, enabled=behavior["enabled"], level=behavior["level"])

                locator = _pick_chat_input_locator(page)
                if locator is None:
                    raise RuntimeError("input box not found")
                locator.click()
                locator.fill(query)
                locator.press("Enter")
                page.wait_for_timeout(3000)

                candidates = page.locator("[data-message-author-role='assistant']")
                if candidates.count() == 0:
                    candidates = page.locator("article")
                if candidates.count() == 0:
                    candidates = page.locator("main")
                if candidates.count() > 0:
                    response_text = candidates.last.inner_text().strip()

                screenshot_path = artifacts_dir / "screenshot.png"
                html_path = artifacts_dir / "page.html"
                page.screenshot(path=str(screenshot_path), full_page=True)
                html_path.write_text(page.content(), encoding="utf-8")

                session_to_close = session
                session = None
                _close_browser_session_strict(session_to_close)

                results = [{"title": f"{provider} response", "href": url, "snippet": response_text[:2000]}]
                meta = {
                    "artifacts": {
                        "screenshot": str(screenshot_path),
                        "html": str(html_path),
                    },
                    "context": context_meta,
                    "stealth": stealth_meta,
                    "human_behavior": behavior_meta,
                    "policy_events": policy_events,
                }
                return {"ok": True, "results": results, "meta": meta}
            finally:
                if session is not None:
                    _close_browser_session_strict(session)
                    session = None
        except Exception as exc:  # noqa: BLE001
            artifacts = _write_web_error_artifacts(artifacts_dir, str(exc), page)
            return {
                "ok": False,
                "results": [],
                "meta": {
                    "artifacts": artifacts,
                    "context": context_meta,
                    "stealth": stealth_meta,
                    "human_behavior": behavior_meta,
                    "policy_events": policy_events,
                },
                "error": str(exc),
            }


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    mapping = {
        "ddg": "duckduckgo",
        "duck": "duckduckgo",
        "browser": "browser_ddg",
        "gemini": "gemini_web",
        "chatgpt": "chatgpt_web",
        "grok": "grok_web",
    }
    return mapping.get(normalized, normalized)


def _extract_domains(results: list[dict[str, str]]) -> list[str]:
    domains: list[str] = []
    for item in results:
        href = item.get("href", "")
        if not href:
            continue
        try:
            host = urlparse(href).netloc
        except Exception:  # noqa: BLE001
            host = ""
        if host:
            domains.append(host)
    return domains


def search_verify(query: str, provider: str | None = None, browser_policy: dict[str, Any] | None = None) -> dict[str, Any]:
    start = time.monotonic()
    raw_provider = provider or os.getenv("CORTEXPILOT_SEARCH_PROVIDER", "duckduckgo")
    provider_name = _normalize_provider(str(raw_provider))
    forced_mock = os.getenv("CORTEXPILOT_SEARCH_MODE", "").strip().lower() == "mock"
    fallback_policy = os.getenv("CORTEXPILOT_WEB_SEARCH_FALLBACK_POLICY", "strict").strip().lower()

    results: list[dict[str, str]]
    mode = "mock"
    resolved_provider = provider_name
    warning = ""
    browser_warning = ""

    if provider_name in {"gemini_web", "chatgpt_web", "grok_web"} and not forced_mock:
        if provider_name == "gemini_web":
            web_payload = _chat_provider_search(query, provider_name, "https://gemini.google.com/", browser_policy=browser_policy)
        elif provider_name == "chatgpt_web":
            web_payload = _chat_provider_search(query, provider_name, "https://chatgpt.com/", browser_policy=browser_policy)
        else:
            web_payload = _chat_provider_search(query, provider_name, "https://grok.com/", browser_policy=browser_policy)
        if web_payload.get("ok") is True:
            results = web_payload.get("results", [])
            meta = web_payload.get("meta", {})
            mode = "web"
            payload: dict[str, Any] = {
                "query": query,
                "provider": provider_name,
                "resolved_provider": provider_name,
                "mode": mode,
                "results": results,
                "meta": meta,
                "verification": {"consistent": True, "count": len(results)},
                "duration_ms": int((time.monotonic() - start) * 1000),
                "ok": True,
            }
            return payload
        error = web_payload.get("error", "web provider failed")
        if fallback_policy == "strict":
            return {
                "query": query,
                "provider": provider_name,
                "resolved_provider": provider_name,
                "mode": "web",
                "results": [],
                "meta": web_payload.get("meta", {}),
                "verification": {"consistent": False, "count": 0},
                "duration_ms": int((time.monotonic() - start) * 1000),
                "ok": False,
                "error": error,
            }
        fallback = os.getenv("CORTEXPILOT_WEB_SEARCH_FALLBACK", "duckduckgo").strip().lower()
        resolved_provider = _normalize_provider(fallback or "mock")
        warning = f"provider_fallback: {provider_name} -> {resolved_provider} ({error})"

    if forced_mock or resolved_provider == "mock":
        results = _mock_results(query)
        mode = "mock"
    elif resolved_provider == "duckduckgo":
        try:
            results = _duckduckgo_results(query)
            mode = "duckduckgo"
        except Exception as exc:  # noqa: BLE001
            results = _mock_results(query)
            mode = "mock"
            warning = f"duckduckgo_failed: {exc}"
    elif resolved_provider == "browser_ddg":
        results, browser_warning = _browser_search(query, browser_policy=browser_policy)
        mode = "browser"
        if browser_warning:
            warning = browser_warning
    else:
        results = _mock_results(query)
        mode = "mock"
        if not warning:
            warning = f"unknown_provider: {provider_name}"

    domains = _extract_domains(results)
    consistency = len(set(domains)) == len(domains)

    browser_fail_closed = resolved_provider == "browser_ddg" and bool(browser_warning)

    payload: dict[str, Any] = {
        "query": query,
        "provider": provider_name,
        "resolved_provider": resolved_provider,
        "mode": mode,
        "results": results,
        "verification": {
            "consistent": consistency,
            "count": len(results),
        },
        "duration_ms": int((time.monotonic() - start) * 1000),
        "ok": not browser_fail_closed,
    }
    if warning:
        payload["warning"] = warning
    if browser_fail_closed:
        payload["error"] = warning
    return payload
