from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tooling.browser.repo_chrome_singleton import (
    DEFAULT_PROFILE_DISPLAY_NAME,
    default_cdp_host,
    default_cdp_port,
    default_repo_chrome_user_data_dir,
    ensure_repo_chrome_singleton,
    resolve_real_chrome_executable_path,
)


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        stripped = str(value or "").strip()
        if stripped:
            return stripped
    return ""


def _truthy_env(*names: str) -> bool:
    for name in names:
        raw = str(os.getenv(name, "")).strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
    return False


def _normalize_profile_mode(raw: str, default_mode: str) -> str:
    value = (raw or default_mode).strip().lower()
    mapping = {
        "none": "ephemeral",
        "default": "ephemeral",
        "ephemeral": "ephemeral",
        "allow_profile": "allow_profile",
        "profile": "allow_profile",
        "cookie_file": "cookie_file",
        "cookie": "cookie_file",
    }
    return mapping.get(value, "ephemeral")


def _local_profile_defaults_enabled() -> bool:
    if _truthy_env("CI", "GITHUB_ACTIONS", "CORTEXPILOT_CI_CONTAINER"):
        return False
    if _first_non_empty(
        os.getenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT"),
        os.getenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT"),
    ):
        return False
    return True


def _default_profile_mode(default_mode: str) -> str:
    normalized = _normalize_profile_mode(default_mode, "ephemeral")
    if normalized != "ephemeral":
        return normalized
    if _local_profile_defaults_enabled():
        return "allow_profile"
    return "ephemeral"


def _default_profile_name(profile_mode: str) -> str:
    if profile_mode == "allow_profile" and _local_profile_defaults_enabled():
        return DEFAULT_PROFILE_DISPLAY_NAME
    return "Default"


def _forced_ephemeral_reason() -> str:
    if _truthy_env("CI", "GITHUB_ACTIONS", "CORTEXPILOT_CI_CONTAINER"):
        return "ci_or_container"
    if _first_non_empty(
        os.getenv("CORTEXPILOT_CLEAN_ROOM_MACHINE_TMP_ROOT"),
        os.getenv("CORTEXPILOT_CLEAN_ROOM_PRESERVE_ROOT"),
    ):
        return "clean_room"
    return ""


def _runtime_root() -> Path:
    return Path(os.getenv("CORTEXPILOT_RUNTIME_ROOT", ".runtime-cache/cortexpilot")).resolve()


def _load_cookie_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cookies", [])
    if not isinstance(payload, list):
        raise ValueError("cookie file payload must be a list")
    cookies: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            cookies.append(item)
    return cookies


def _close_page_only(page: Any) -> None:
    try:
        page.close()
    except Exception:  # noqa: BLE001
        return


@dataclass
class BrowserSessionHandle:
    page: Any
    context: Any | None
    metadata: dict[str, Any]
    _close_fn: Callable[[], None]

    def close(self) -> None:
        self._close_fn()


class BrowserSessionManager:
    def __init__(
        self,
        *,
        headless: bool,
        profile_mode: str,
        profile_dir: Path | None,
        profile_name: str,
        cookie_file: Path | None,
        runtime_root: Path,
    ) -> None:
        self.headless = headless
        self.profile_mode = profile_mode
        self.profile_dir = profile_dir
        self.profile_name = profile_name
        self.cookie_file = cookie_file
        self.runtime_root = runtime_root

    @classmethod
    def from_policy(
        cls,
        *,
        headless: bool,
        policy: dict[str, Any] | None,
        default_profile_mode: str = "ephemeral",
    ) -> "BrowserSessionManager":
        payload = policy if isinstance(policy, dict) else {}
        resolved_default_mode = _default_profile_mode(default_profile_mode)
        profile_mode = _normalize_profile_mode(payload.get("profile_mode", resolved_default_mode), resolved_default_mode)
        if _forced_ephemeral_reason():
            profile_mode = "ephemeral"

        profile_ref = payload.get("profile_ref") if isinstance(payload.get("profile_ref"), dict) else {}
        profile_dir_raw = profile_ref.get("profile_dir") if isinstance(profile_ref.get("profile_dir"), str) else ""
        profile_dir = Path(profile_dir_raw).expanduser().resolve() if profile_dir_raw else None
        if profile_dir is None and profile_mode == "allow_profile":
            profile_dir = default_repo_chrome_user_data_dir().resolve()

        profile_name_raw = profile_ref.get("profile_name") if isinstance(profile_ref.get("profile_name"), str) else ""
        profile_name = profile_name_raw.strip() or _default_profile_name(profile_mode)

        cookie_ref = payload.get("cookie_ref") if isinstance(payload.get("cookie_ref"), dict) else {}
        cookie_file_raw = cookie_ref.get("cookie_path") if isinstance(cookie_ref.get("cookie_path"), str) else ""
        cookie_file = Path(cookie_file_raw).expanduser().resolve() if cookie_file_raw else None
        if profile_mode == "ephemeral":
            profile_dir = None
            cookie_file = None
            profile_name = "Default"

        return cls(
            headless=headless,
            profile_mode=profile_mode,
            profile_dir=profile_dir,
            profile_name=profile_name,
            cookie_file=cookie_file,
            runtime_root=_runtime_root(),
        )

    @classmethod
    def from_env(
        cls,
        *,
        headless: bool,
        default_profile_mode: str = "ephemeral",
    ) -> "BrowserSessionManager":
        resolved_default_mode = _default_profile_mode(default_profile_mode)
        raw_mode = _first_non_empty(
            os.getenv("CORTEXPILOT_BROWSER_PROFILE_MODE"),
            os.getenv("CORTEXPILOT_WEB_PROFILE_MODE"),
        )
        profile_mode = _normalize_profile_mode(raw_mode, resolved_default_mode)
        if _forced_ephemeral_reason():
            profile_mode = "ephemeral"

        raw_profile_dir = _first_non_empty(
            os.getenv("CORTEXPILOT_BROWSER_PROFILE_DIR"),
            os.getenv("CORTEXPILOT_WEB_PROFILE_DIR"),
        )
        profile_dir = Path(raw_profile_dir).expanduser().resolve() if raw_profile_dir else None
        if profile_dir is None and profile_mode == "allow_profile":
            profile_dir = default_repo_chrome_user_data_dir().resolve()

        raw_profile_name = _first_non_empty(
            os.getenv("CORTEXPILOT_BROWSER_PROFILE_NAME"),
            os.getenv("CORTEXPILOT_WEB_PROFILE_NAME"),
        )
        profile_name = raw_profile_name or _default_profile_name(profile_mode)

        raw_cookie_file = _first_non_empty(
            os.getenv("CORTEXPILOT_BROWSER_COOKIE_PATH"),
            os.getenv("CORTEXPILOT_WEB_COOKIE_PATH"),
        )
        cookie_file = Path(raw_cookie_file).expanduser().resolve() if raw_cookie_file else None
        if profile_mode == "ephemeral":
            profile_dir = None
            cookie_file = None
            profile_name = "Default"

        return cls(
            headless=headless,
            profile_mode=profile_mode,
            profile_dir=profile_dir,
            profile_name=profile_name,
            cookie_file=cookie_file,
            runtime_root=_runtime_root(),
        )

    def profile_event(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": "BROWSER_PROFILE_MODE_SELECTED",
            "level": "INFO",
            "meta": {
                "mode": metadata.get("mode", self.profile_mode),
                "profile_dir": metadata.get("profile_dir"),
                "profile_name": metadata.get("profile_name"),
                "profile_directory": metadata.get("profile_directory"),
                "cookie_path": metadata.get("cookie_path"),
                "chrome_executable_path": metadata.get("chrome_executable_path"),
                "connection_mode": metadata.get("connection_mode"),
                "cdp_endpoint": metadata.get("cdp_endpoint"),
                "requested_headless": metadata.get("requested_headless"),
                "actual_headless": metadata.get("actual_headless"),
            },
        }

    def open_page(self, playwright: Any, extra_launch_args: list[str] | None = None) -> BrowserSessionHandle:
        launch_args = [arg for arg in (extra_launch_args or []) if isinstance(arg, str) and arg.strip()]
        mode = self.profile_mode

        if mode == "allow_profile":
            if self.profile_dir is None:
                raise RuntimeError("repo Chrome root not configured")
            chrome_executable_path = resolve_real_chrome_executable_path()
            if not chrome_executable_path:
                raise RuntimeError("real Chrome executable not found for allow_profile mode")
            instance = ensure_repo_chrome_singleton(
                chrome_executable_path=chrome_executable_path,
                user_data_dir=self.profile_dir,
                profile_name=self.profile_name,
                cdp_host=default_cdp_host(),
                cdp_port=default_cdp_port(),
                extra_launch_args=launch_args,
                requested_headless=self.headless,
            )
            browser = playwright.chromium.connect_over_cdp(instance.cdp_endpoint)
            contexts = list(getattr(browser, "contexts", []))
            if not contexts:
                raise RuntimeError("repo Chrome CDP attach returned no browser contexts")
            context = contexts[0]
            page = context.new_page()
            metadata = {
                "mode": "allow_profile",
                "profile_dir": instance.user_data_dir,
                "profile_name": instance.profile_name,
                "profile_directory": instance.profile_directory,
                "chrome_executable_path": instance.chrome_executable_path,
                "connection_mode": instance.connection_mode,
                "cdp_endpoint": instance.cdp_endpoint,
                "requested_headless": instance.requested_headless,
                "actual_headless": instance.actual_headless,
            }
            return BrowserSessionHandle(page=page, context=context, metadata=metadata, _close_fn=lambda: _close_page_only(page))

        if mode == "cookie_file":
            if self.cookie_file is None or not self.cookie_file.exists():
                raise RuntimeError("cookie file not found")
            cookie_profile_dir = self.runtime_root / "browser-session" / "cookie-profile"
            cookie_profile_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(cookie_profile_dir),
                headless=self.headless,
                args=launch_args,
            )
            cookies = _load_cookie_file(self.cookie_file)
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            metadata = {
                "mode": "cookie_file",
                "cookie_path": str(self.cookie_file),
                "cookie_count": len(cookies),
                "headless": self.headless,
            }
            return BrowserSessionHandle(page=page, context=context, metadata=metadata, _close_fn=context.close)

        browser = playwright.chromium.launch(headless=self.headless, args=launch_args)
        page = browser.new_page()
        metadata = {
            "mode": "ephemeral",
            "headless": self.headless,
        }
        return BrowserSessionHandle(page=page, context=getattr(page, "context", None), metadata=metadata, _close_fn=browser.close)
