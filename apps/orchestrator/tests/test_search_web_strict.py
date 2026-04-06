import os
from pathlib import Path
from urllib.parse import urlparse

from tooling.search.search_engine import (
    _browser_search,
    _pick_chat_input_locator,
    _url_allowed,
    _web_allowlist,
    _write_web_error_artifacts,
    search_verify,
)


def test_web_allowlist_match() -> None:
    allowlist = ["https://chatgpt.com/", "https://*.openai.com/"]
    assert _url_allowed("https://chatgpt.com/", allowlist) is True
    assert _url_allowed("https://platform.openai.com/docs", allowlist) is True
    assert _url_allowed("https://example.com/", allowlist) is False


def test_default_web_allowlist_minimal(monkeypatch) -> None:
    monkeypatch.delenv("CORTEXPILOT_WEB_ALLOWLIST", raising=False)
    allowlist = _web_allowlist()
    assert len(allowlist) >= 3
    assert any(urlparse(item).hostname == "chatgpt.com" for item in allowlist)
    assert any(urlparse(item).hostname == "grok.com" for item in allowlist)


def test_web_search_strict_failure(monkeypatch) -> None:
    monkeypatch.setenv("CORTEXPILOT_WEB_SEARCH_FALLBACK_POLICY", "strict")
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_MODE", "allow_profile")
    monkeypatch.setenv("CORTEXPILOT_BROWSER_PROFILE_DIR", os.path.join(os.getcwd(), "missing_profile_dir"))
    result = search_verify("cortexpilot", provider="chatgpt_web")
    assert result["ok"] is False
    assert result["mode"] == "web"
    assert "error" in result
    meta = result.get("meta", {})
    artifacts = meta.get("artifacts", {})
    assert Path(artifacts["error"]).exists()


def test_web_error_artifacts_capture(tmp_path: Path) -> None:
    class DummyPage:
        def __init__(self, html: str) -> None:
            self._html = html

        def screenshot(self, path: str, _full_page: bool = True) -> None:  # noqa: ARG002
            Path(path).write_bytes(b"png")

        def content(self) -> str:
            return self._html

    artifacts = _write_web_error_artifacts(tmp_path, "boom", DummyPage("<html>fail</html>"))
    assert Path(artifacts["error"]).exists()
    assert Path(artifacts["screenshot"]).exists()
    assert Path(artifacts["html"]).exists()


def test_web_error_artifacts_screenshot_fallback_never_raises(tmp_path: Path) -> None:
    class DummyPage:
        def screenshot(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            raise TypeError("unsupported signature")

        def content(self) -> str:
            return "<html>fail</html>"

    artifacts = _write_web_error_artifacts(tmp_path, "boom", DummyPage())
    assert Path(artifacts["error"]).exists()
    assert artifacts["screenshot"] is None
    assert Path(artifacts["html"]).exists()


def test_pick_chat_input_locator_prefers_standard_inputs() -> None:
    class DummyLocator:
        def __init__(self, name: str, count: int) -> None:
            self.name = name
            self._count = count
            self.first = self

        def count(self) -> int:
            return self._count

    class DummyPage:
        def __init__(self) -> None:
            self.locators = {
                "textarea": DummyLocator("textarea", 1),
                "input[type='text']": DummyLocator("input", 1),
                "[role='textbox'][contenteditable='true']": DummyLocator("textbox", 1),
                "[contenteditable='true'][role='textbox']": DummyLocator("textbox-reversed", 1),
                "[aria-label='Enter a prompt for Gemini'][contenteditable='true']": DummyLocator("aria", 1),
                ".ql-editor[contenteditable='true']": DummyLocator("ql-editor", 1),
            }

        def locator(self, selector: str) -> DummyLocator:
            return self.locators[selector]

    locator = _pick_chat_input_locator(DummyPage())
    assert locator is not None
    assert locator.name == "textarea"


def test_pick_chat_input_locator_falls_back_to_contenteditable_textbox() -> None:
    class DummyLocator:
        def __init__(self, name: str, count: int) -> None:
            self.name = name
            self._count = count
            self.first = self

        def count(self) -> int:
            return self._count

    class DummyPage:
        def __init__(self) -> None:
            self.locators = {
                "textarea": DummyLocator("textarea", 0),
                "input[type='text']": DummyLocator("input", 0),
                "[role='textbox'][contenteditable='true']": DummyLocator("textbox", 1),
                "[contenteditable='true'][role='textbox']": DummyLocator("textbox-reversed", 0),
                "[aria-label='Enter a prompt for Gemini'][contenteditable='true']": DummyLocator("aria", 0),
                ".ql-editor[contenteditable='true']": DummyLocator("ql-editor", 0),
            }

        def locator(self, selector: str) -> DummyLocator:
            return self.locators[selector]

    locator = _pick_chat_input_locator(DummyPage())
    assert locator is not None
    assert locator.name == "textbox"


def test_pick_chat_input_locator_returns_none_when_no_supported_input_exists() -> None:
    class DummyLocator:
        def __init__(self) -> None:
            self.first = self

        def count(self) -> int:
            return 0

    class DummyPage:
        def locator(self, selector: str) -> DummyLocator:  # noqa: ARG002
            return DummyLocator()

    assert _pick_chat_input_locator(DummyPage()) is None


def test_browser_search_closes_session_before_playwright_exit(monkeypatch, tmp_path: Path) -> None:
    order: list[str] = []

    class DummyPage:
        def goto(self, url: str) -> None:  # noqa: ARG002
            return None

        def wait_for_timeout(self, ms: int) -> None:  # noqa: ARG002
            return None

        def evaluate(self, script: str):  # noqa: ARG002
            return [{"title": "ok", "href": "https://example.com"}]

    class DummySession:
        def __init__(self) -> None:
            self.page = DummyPage()
            self.context = object()
            self.metadata = {"mode": "allow_profile"}

        def close(self) -> None:
            order.append("session.close")

    class DummyPlaywright:
        chromium = object()

    class DummyContextManager:
        def __enter__(self) -> DummyPlaywright:
            return DummyPlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            order.append("playwright.exit")
            return None

    import sys
    import types

    dummy_module = types.ModuleType("playwright.sync_api")
    setattr(dummy_module, "sync_playwright", lambda: DummyContextManager())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", dummy_module)
    monkeypatch.setattr(
        "tooling.search.search_engine._web_session_manager",
        lambda browser_policy=None: types.SimpleNamespace(open_page=lambda _p, extra_launch_args=None: DummySession()),
    )
    monkeypatch.setattr(
        "tooling.search.search_engine._web_stealth_provider",
        lambda browser_policy=None: types.SimpleNamespace(launch_args=lambda: [], apply=lambda **_kwargs: {"events": []}),
    )
    monkeypatch.setenv("CORTEXPILOT_RUNTIME_ROOT", str(tmp_path / ".runtime-cache" / "cortexpilot"))

    results, error = _browser_search("cortexpilot")

    assert error is None
    assert results == [{"title": "ok", "href": "https://example.com"}]
    assert order == ["session.close", "playwright.exit"]


def test_browser_ddg_fail_closed_when_singleton_attach_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        "tooling.search.search_engine._browser_search",
        lambda query, browser_policy=None: ([], "browser_ddg_failed: singleton attach failed"),
    )

    result = search_verify("cortexpilot", provider="browser_ddg")

    assert result["ok"] is False
    assert result["mode"] == "browser"
    assert result["results"] == []
    assert result["error"] == "browser_ddg_failed: singleton attach failed"
