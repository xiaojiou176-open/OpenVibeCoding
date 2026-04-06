from __future__ import annotations

import importlib
import os
from typing import Any


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        stripped = str(value or "").strip()
        if stripped:
            return stripped
    return ""


def _to_bool(value: str, default: bool) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _normalize_mode(raw_mode: str) -> str:
    mode = (raw_mode or "none").strip().lower()
    if mode in {"none", "lite", "plugin"}:
        return mode
    return "none"


_LITE_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
""".strip()


class StealthProvider:
    def __init__(self, *, mode: str, plugin_optional: bool) -> None:
        self.mode = _normalize_mode(mode)
        self.plugin_optional = plugin_optional


    @classmethod
    def from_policy(cls, policy: dict[str, Any] | None) -> "StealthProvider":
        payload = policy if isinstance(policy, dict) else {}
        mode = payload.get("stealth_mode") if isinstance(payload.get("stealth_mode"), str) else ""
        plugin_optional = payload.get("plugin_optional")
        if not isinstance(plugin_optional, bool):
            plugin_optional = _to_bool(os.getenv("CORTEXPILOT_BROWSER_PLUGIN_OPTIONAL", ""), True)
        if not isinstance(mode, str) or not mode.strip():
            return cls.from_env()
        return cls(mode=mode, plugin_optional=bool(plugin_optional))

    @classmethod
    def from_env(
        cls,
    ) -> "StealthProvider":
        raw_mode = _first_non_empty(
            os.getenv("CORTEXPILOT_BROWSER_STEALTH_MODE"),
            os.getenv("CORTEXPILOT_WEB_STEALTH_MODE"),
        ) or "none"
        raw_optional = _first_non_empty(os.getenv("CORTEXPILOT_BROWSER_PLUGIN_OPTIONAL"))
        plugin_optional = _to_bool(raw_optional, True)
        return cls(mode=raw_mode, plugin_optional=plugin_optional)

    def launch_args(self) -> list[str]:
        if self.mode not in {"lite", "plugin"}:
            return []
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
        ]

    def _apply_lite(self, page: Any, context: Any | None) -> None:
        if context is not None and hasattr(context, "add_init_script"):
            try:
                context.add_init_script(_LITE_INIT_SCRIPT)
            except Exception:  # noqa: BLE001
                pass
        if hasattr(page, "add_init_script"):
            try:
                page.add_init_script(_LITE_INIT_SCRIPT)
            except Exception:  # noqa: BLE001
                pass

    def _apply_plugin(self, page: Any) -> None:
        module = importlib.import_module("playwright_stealth")
        plugin_fn = getattr(module, "stealth_sync", None)
        if callable(plugin_fn):
            plugin_fn(page)
            return
        fallback_fn = getattr(module, "stealth", None)
        if callable(fallback_fn):
            fallback_fn(page)
            return
        raise RuntimeError("playwright_stealth entrypoint not found")

    def apply(self, *, page: Any, context: Any | None = None) -> dict[str, Any]:
        requested_mode = self.mode
        applied_mode = requested_mode
        provider = "none"
        warnings: list[str] = []
        events: list[dict[str, Any]] = []

        if requested_mode == "plugin":
            try:
                self._apply_plugin(page)
                provider = "playwright_stealth"
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"plugin_unavailable: {exc}")
                if self.plugin_optional:
                    applied_mode = "lite"
                    events.append(
                        {
                            "event": "BROWSER_STEALTH_FALLBACK",
                            "level": "WARN",
                            "meta": {
                                "requested_mode": requested_mode,
                                "fallback_mode": applied_mode,
                                "reason": str(exc),
                            },
                        }
                    )
                else:
                    raise

        if applied_mode == "lite":
            self._apply_lite(page, context)
            provider = "builtin-lite"

        if applied_mode in {"lite", "plugin"}:
            events.append(
                {
                    "event": "BROWSER_STEALTH_APPLIED",
                    "level": "INFO",
                    "meta": {
                        "requested_mode": requested_mode,
                        "applied_mode": applied_mode,
                        "provider": provider,
                    },
                }
            )

        return {
            "requested_mode": requested_mode,
            "applied_mode": applied_mode,
            "provider": provider,
            "warnings": warnings,
            "events": events,
        }
