from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from cortexpilot_orch.observability.tracer import trace_span
from tooling.browser.human_behavior import apply_human_behavior
from tooling.browser.policy import browser_human_behavior_enabled, browser_human_behavior_level
from tooling.browser.session_manager import BrowserSessionHandle, BrowserSessionManager
from tooling.browser.stealth_provider import StealthProvider
from tooling.search.search_engine import _url_allowed


def _safe_screenshot(page: Any, path: Path) -> None:
    try:
        page.screenshot(path=str(path), full_page=True)
        return
    except TypeError:
        pass
    try:
        page.screenshot(path=str(path), _full_page=True)
        return
    except TypeError:
        pass
    page.screenshot(str(path), True)


def _close_session_strict(session: BrowserSessionHandle) -> None:
    session.close()


class BrowserRunner:
    def __init__(
        self,
        artifacts_dir: Path,
        headless: bool | None = None,
        browser_policy: dict[str, Any] | None = None,
    ) -> None:
        self._artifacts_dir = artifacts_dir
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        if headless is None:
            env = os.getenv("CORTEXPILOT_HEADLESS", "true").lower()
            headless = env not in {"0", "false", "no"}
        self._headless = headless
        timeout_ms = os.getenv("CORTEXPILOT_PLAYWRIGHT_TIMEOUT_MS", "30000")
        try:
            self._timeout_ms = int(timeout_ms)
        except ValueError:
            self._timeout_ms = 30000

        self._browser_policy = browser_policy if isinstance(browser_policy, dict) else {}
        if self._browser_policy:
            self._session_manager = BrowserSessionManager.from_policy(
                headless=self._headless,
                policy=self._browser_policy,
                default_profile_mode="ephemeral",
            )
            self._stealth_provider = StealthProvider.from_policy(self._browser_policy)
        else:
            self._session_manager = BrowserSessionManager.from_env(
                headless=self._headless,
                default_profile_mode="ephemeral",
            )
            self._stealth_provider = StealthProvider.from_env()

        human_cfg = self._browser_policy.get("human_behavior") if isinstance(self._browser_policy.get("human_behavior"), dict) else {}
        if human_cfg:
            self._human_behavior_enabled = bool(human_cfg.get("enabled", False))
            self._human_behavior_level = str(human_cfg.get("level", "low")).strip() or "low"
        else:
            self._human_behavior_enabled = browser_human_behavior_enabled(default=False)
            self._human_behavior_level = browser_human_behavior_level(default="low")

    def _mock_artifacts(self) -> dict[str, str]:
        screenshot_path = self._artifacts_dir / "screenshot.png"
        source_path = self._artifacts_dir / "source.html"
        screenshot_path.write_bytes(b"mock")
        source_path.write_text("<html><body>mock</body></html>", encoding="utf-8")
        return {"screenshot": str(screenshot_path), "source": str(source_path)}

    def _allowlist(self) -> list[str]:
        raw = os.getenv("CORTEXPILOT_BROWSER_ALLOWLIST", "").strip()
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    @trace_span("browser.run_script")
    def run_script(self, script_content: str, url: str) -> dict[str, Any]:
        start = time.monotonic()
        allowlist = self._allowlist()
        policy_events: list[dict[str, Any]] = []

        if allowlist and not _url_allowed(url, allowlist):
            error_path = self._artifacts_dir / "error.txt"
            error_path.write_text(f"url not allowlisted: {url}", encoding="utf-8")
            return {
                "ok": False,
                "mode": "blocked",
                "url": url,
                "result": None,
                "error": "url not allowlisted",
                "artifacts": {"error": str(error_path)},
                "policy_events": policy_events,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }

        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            artifacts = self._mock_artifacts()
            return {
                "ok": True,
                "mode": "mock",
                "url": url,
                "result": None,
                "artifacts": artifacts,
                "policy_events": policy_events,
                "duration_ms": int((time.monotonic() - start) * 1000),
                "warning": f"playwright_unavailable: {exc}",
            }

        screenshot_path = self._artifacts_dir / "screenshot.png"
        source_path = self._artifacts_dir / "source.html"
        error_path = self._artifacts_dir / "error.txt"

        session: BrowserSessionHandle | None = None
        page = None
        session_meta: dict[str, Any] = {}
        stealth_meta: dict[str, Any] = {}
        behavior_meta: dict[str, Any] = {}

        try:
            with sync_playwright() as p:
                try:
                    session = self._session_manager.open_page(
                        p,
                        extra_launch_args=self._stealth_provider.launch_args(),
                    )
                    session_meta = session.metadata
                    policy_events.append(self._session_manager.profile_event(session_meta))
                    page = session.page
                    stealth_meta = self._stealth_provider.apply(page=page, context=session.context)
                    policy_events.extend(stealth_meta.get("events", []))

                    page.set_default_timeout(self._timeout_ms)
                    page.goto(url)

                    behavior_meta = apply_human_behavior(
                        page,
                        enabled=self._human_behavior_enabled,
                        level=self._human_behavior_level,
                    )

                    result = None
                    if script_content.strip():
                        result = page.evaluate(script_content)

                    _safe_screenshot(page, screenshot_path)
                    source_path.write_text(page.content(), encoding="utf-8")
                    session_to_close = session
                    session = None
                    _close_session_strict(session_to_close)
                    return {
                        "ok": True,
                        "mode": "playwright",
                        "url": url,
                        "result": result,
                        "artifacts": {
                            "screenshot": str(screenshot_path),
                            "source": str(source_path),
                        },
                        "meta": {
                            "session": session_meta,
                            "stealth": stealth_meta,
                            "human_behavior": behavior_meta,
                        },
                        "policy_events": policy_events,
                        "duration_ms": int((time.monotonic() - start) * 1000),
                    }
                finally:
                    if session is not None:
                        _close_session_strict(session)
                        session = None
        except Exception as exc:  # noqa: BLE001
            error_path.write_text(str(exc), encoding="utf-8")
            if page is not None:
                try:
                    _safe_screenshot(page, screenshot_path)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    source_path.write_text(page.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass
            return {
                "ok": False,
                "mode": "playwright",
                "url": url,
                "result": None,
                "error": str(exc),
                "artifacts": {
                    "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
                    "source": str(source_path) if source_path.exists() else None,
                    "error": str(error_path),
                },
                "meta": {
                    "session": session_meta,
                    "stealth": stealth_meta,
                    "human_behavior": behavior_meta,
                },
                "policy_events": policy_events,
                "duration_ms": int((time.monotonic() - start) * 1000),
            }
