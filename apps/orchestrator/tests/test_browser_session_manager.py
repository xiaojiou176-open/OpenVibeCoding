from __future__ import annotations

from pathlib import Path

import pytest

from tooling.browser import session_manager as session_manager_module
from tooling.browser.repo_chrome_singleton import RepoChromeInstance
from tooling.browser.session_manager import BrowserSessionManager


def test_session_manager_from_env_defaults_to_repo_browser_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("OPENVIBECODING_CI_CONTAINER", raising=False)
    monkeypatch.delenv("OPENVIBECODING_CLEAN_ROOM_MACHINE_TMP_ROOT", raising=False)
    monkeypatch.delenv("OPENVIBECODING_CLEAN_ROOM_PRESERVE_ROOT", raising=False)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_MODE", raising=False)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_DIR", raising=False)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_NAME", raising=False)
    monkeypatch.setattr(session_manager_module, "default_repo_chrome_user_data_dir", lambda: browser_root)

    manager = BrowserSessionManager.from_env(headless=True)

    assert manager.profile_mode == "allow_profile"
    assert manager.profile_dir == browser_root.resolve()
    assert manager.profile_name == "openvibecoding"


def test_session_manager_from_env_defaults_to_ephemeral_in_ci(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_MODE", raising=False)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_DIR", raising=False)
    monkeypatch.delenv("OPENVIBECODING_BROWSER_PROFILE_NAME", raising=False)
    monkeypatch.setattr(session_manager_module, "default_repo_chrome_user_data_dir", lambda: browser_root)

    manager = BrowserSessionManager.from_env(headless=True)

    assert manager.profile_mode == "ephemeral"
    assert manager.profile_dir is None
    assert manager.profile_name == "Default"


def test_session_manager_from_env_forces_ephemeral_even_when_allow_profile_is_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"
    monkeypatch.setenv("OPENVIBECODING_CI_CONTAINER", "1")
    monkeypatch.setenv("OPENVIBECODING_BROWSER_PROFILE_MODE", "allow_profile")
    monkeypatch.setenv("OPENVIBECODING_BROWSER_PROFILE_DIR", str(browser_root))
    monkeypatch.setenv("OPENVIBECODING_BROWSER_PROFILE_NAME", "openvibecoding")

    manager = BrowserSessionManager.from_env(headless=True)

    assert manager.profile_mode == "ephemeral"
    assert manager.profile_dir is None
    assert manager.profile_name == "Default"


def test_open_page_allow_profile_attaches_to_repo_singleton(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"
    closed: list[str] = []

    class _Page:
        def close(self) -> None:
            closed.append("page")

    class _Context:
        def new_page(self) -> _Page:
            return _Page()

    class _Browser:
        contexts = [_Context()]

    class _Chromium:
        def connect_over_cdp(self, endpoint: str) -> _Browser:
            assert endpoint == "http://127.0.0.1:9341"
            return _Browser()

    class _Playwright:
        chromium = _Chromium()

    monkeypatch.setattr(session_manager_module, "resolve_real_chrome_executable_path", lambda: "/preferred/chrome")
    monkeypatch.setattr(
        session_manager_module,
        "ensure_repo_chrome_singleton",
        lambda **kwargs: RepoChromeInstance(
            connection_mode="attached",
            pid=4321,
            user_data_dir=str(browser_root),
            profile_directory="Profile 1",
            profile_name="openvibecoding",
            cdp_host="127.0.0.1",
            cdp_port=9341,
            cdp_endpoint="http://127.0.0.1:9341",
            chrome_executable_path="/preferred/chrome",
            browser_root=str(browser_root.parent),
            actual_headless=False,
            requested_headless=bool(kwargs["requested_headless"]),
        ),
    )

    manager = BrowserSessionManager(
        headless=True,
        profile_mode="allow_profile",
        profile_dir=browser_root,
        profile_name="openvibecoding",
        cookie_file=None,
        runtime_root=tmp_path / "runtime",
    )

    session = manager.open_page(_Playwright(), extra_launch_args=["--fake-flag"])

    assert session.metadata["profile_name"] == "openvibecoding"
    assert session.metadata["profile_directory"] == "Profile 1"
    assert session.metadata["chrome_executable_path"] == "/preferred/chrome"
    assert session.metadata["connection_mode"] == "attached"
    assert session.metadata["requested_headless"] is True
    assert session.metadata["actual_headless"] is False
    session.close()
    assert closed == ["page"]


def test_open_page_allow_profile_fails_closed_without_real_chrome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"

    class _Playwright:
        chromium = object()

    monkeypatch.setattr(session_manager_module, "resolve_real_chrome_executable_path", lambda: "")

    manager = BrowserSessionManager(
        headless=False,
        profile_mode="allow_profile",
        profile_dir=browser_root,
        profile_name="openvibecoding",
        cookie_file=None,
        runtime_root=tmp_path / "runtime",
    )

    with pytest.raises(RuntimeError, match="real Chrome executable not found"):
        manager.open_page(_Playwright())


def test_open_page_allow_profile_fails_closed_without_cdp_contexts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    browser_root = tmp_path / "browser" / "chrome-user-data"

    class _Browser:
        contexts: list[object] = []

    class _Chromium:
        def connect_over_cdp(self, endpoint: str) -> _Browser:
            assert endpoint == "http://127.0.0.1:9341"
            return _Browser()

    class _Playwright:
        chromium = _Chromium()

    monkeypatch.setattr(session_manager_module, "resolve_real_chrome_executable_path", lambda: "/preferred/chrome")
    monkeypatch.setattr(
        session_manager_module,
        "ensure_repo_chrome_singleton",
        lambda **_kwargs: RepoChromeInstance(
            connection_mode="attached",
            pid=4321,
            user_data_dir=str(browser_root),
            profile_directory="Profile 1",
            profile_name="openvibecoding",
            cdp_host="127.0.0.1",
            cdp_port=9341,
            cdp_endpoint="http://127.0.0.1:9341",
            chrome_executable_path="/preferred/chrome",
            browser_root=str(browser_root.parent),
            actual_headless=False,
            requested_headless=False,
        ),
    )

    manager = BrowserSessionManager(
        headless=True,
        profile_mode="allow_profile",
        profile_dir=browser_root,
        profile_name="openvibecoding",
        cookie_file=None,
        runtime_root=tmp_path / "runtime",
    )

    with pytest.raises(RuntimeError, match="returned no browser contexts"):
        manager.open_page(_Playwright())
