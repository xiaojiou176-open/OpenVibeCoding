from pathlib import Path
import sys
import types

from tooling.browser.playwright_runner import BrowserRunner


def test_browser_runner_captures_error_artifacts(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"

    class DummyPage:
        def __init__(self) -> None:
            self.timeout = None

        def set_default_timeout(self, ms: int) -> None:
            self.timeout = ms

        def add_init_script(self, script: str) -> None:  # noqa: ARG002
            return None

        def goto(self, url: str) -> None:
            raise RuntimeError("goto failed")

        def evaluate(self, script: str):
            return None

        def screenshot(self, path: str, _full_page: bool = True) -> None:
            Path(path).write_bytes(b"shot")

        def content(self) -> str:
            return "<html>fail</html>"

    class DummyBrowser:
        def new_page(self) -> DummyPage:
            return DummyPage()

        def close(self) -> None:
            return None

    class DummyChromium:
        def launch(self, headless: bool = True, args=None) -> DummyBrowser:  # noqa: ARG002
            return DummyBrowser()

    class DummyPlaywright:
        def __init__(self) -> None:
            self.chromium = DummyChromium()

    class DummyContext:
        def __enter__(self) -> DummyPlaywright:
            return DummyPlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    dummy_module = types.ModuleType("playwright.sync_api")
    setattr(dummy_module, "sync_playwright", lambda: DummyContext())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", dummy_module)

    runner = BrowserRunner(artifacts_dir, headless=True, browser_policy={"profile_mode": "ephemeral"})
    result = runner.run_script("", "https://example.com")
    assert result["ok"] is False
    artifacts = result.get("artifacts", {})
    assert artifacts.get("error") is not None
    assert artifacts.get("source") is not None
    assert artifacts.get("screenshot") is not None
    assert Path(artifacts["error"]).exists()
    assert Path(artifacts["source"]).exists()
    assert Path(artifacts["screenshot"]).exists()


def test_browser_runner_blocks_non_allowlisted_url(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"
    monkeypatch.setenv("OPENVIBECODING_BROWSER_ALLOWLIST", "https://chatgpt.com/")

    runner = BrowserRunner(artifacts_dir, headless=True, browser_policy={"profile_mode": "ephemeral"})
    result = runner.run_script("", "https://example.com")
    assert result["ok"] is False
    assert result["error"] == "url not allowlisted"
    artifacts = result.get("artifacts", {})
    assert Path(artifacts["error"]).exists()


def test_browser_runner_plugin_mode_fallback_to_lite(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"

    class DummyPage:
        def __init__(self) -> None:
            self._init_scripts: list[str] = []

        def set_default_timeout(self, ms: int) -> None:  # noqa: ARG002
            return None

        def add_init_script(self, script: str) -> None:
            self._init_scripts.append(script)

        def goto(self, url: str) -> None:  # noqa: ARG002
            return None

        def evaluate(self, script: str):  # noqa: ARG002
            return None

        def screenshot(self, path: str, _full_page: bool = True) -> None:  # noqa: ARG002
            Path(path).write_bytes(b"ok")

        def content(self) -> str:
            return "<html>ok</html>"

    class DummyBrowser:
        def __init__(self) -> None:
            self.page = DummyPage()

        def new_page(self) -> DummyPage:
            return self.page

        def close(self) -> None:
            return None

    class DummyChromium:
        def launch(self, headless: bool = True, args=None) -> DummyBrowser:  # noqa: ARG002
            return DummyBrowser()

    class DummyPlaywright:
        def __init__(self) -> None:
            self.chromium = DummyChromium()

    class DummyContext:
        def __enter__(self) -> DummyPlaywright:
            return DummyPlaywright()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    dummy_module = types.ModuleType("playwright.sync_api")
    setattr(dummy_module, "sync_playwright", lambda: DummyContext())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", dummy_module)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_ALLOWLIST", raising=False)
    monkeypatch.setenv("OPENVIBECODING_BROWSER_STEALTH_MODE", "plugin")
    monkeypatch.setenv("OPENVIBECODING_BROWSER_PLUGIN_OPTIONAL", "1")

    runner = BrowserRunner(artifacts_dir, headless=True, browser_policy={"profile_mode": "ephemeral"})
    result = runner.run_script("", "https://example.com")

    assert result["ok"] is True
    events = result.get("policy_events", [])
    assert any(event.get("event") == "BROWSER_PROFILE_MODE_SELECTED" for event in events)
    assert any(event.get("event") == "BROWSER_STEALTH_FALLBACK" for event in events)
    assert any(event.get("event") == "BROWSER_STEALTH_APPLIED" for event in events)


def test_browser_runner_closes_session_before_playwright_exit(tmp_path: Path, monkeypatch) -> None:
    artifacts_dir = tmp_path / "artifacts"
    order: list[str] = []

    class DummyPage:
        def set_default_timeout(self, ms: int) -> None:  # noqa: ARG002
            return None

        def goto(self, url: str) -> None:  # noqa: ARG002
            return None

        def evaluate(self, script: str):  # noqa: ARG002
            return None

        def screenshot(self, path: str, _full_page: bool = True) -> None:  # noqa: ARG002
            Path(path).write_bytes(b"ok")

        def content(self) -> str:
            return "<html>ok</html>"

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

    dummy_module = types.ModuleType("playwright.sync_api")
    setattr(dummy_module, "sync_playwright", lambda: DummyContextManager())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", dummy_module)

    runner = BrowserRunner(artifacts_dir, headless=True, browser_policy={"profile_mode": "ephemeral"})
    runner._session_manager = types.SimpleNamespace(  # type: ignore[attr-defined]
        open_page=lambda _p, extra_launch_args=None: DummySession(),
        profile_event=lambda _meta: {"event": "BROWSER_PROFILE_MODE_SELECTED"},
    )
    runner._stealth_provider = types.SimpleNamespace(  # type: ignore[attr-defined]
        launch_args=lambda: [],
        apply=lambda **_kwargs: {"events": []},
    )

    result = runner.run_script("", "https://example.com")

    assert result["ok"] is True
    assert order == ["session.close", "playwright.exit"]
