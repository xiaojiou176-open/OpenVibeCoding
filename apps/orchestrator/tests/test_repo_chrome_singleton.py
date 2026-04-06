from __future__ import annotations

import json
from pathlib import Path

import pytest

from tooling.browser import repo_chrome_singleton as singleton_module


def test_build_repo_local_state_rewrites_to_single_profile() -> None:
    source_payload = {
        "profile": {
            "last_used": "Profile 22",
            "last_active_profiles": ["Profile 22", "Profile 3"],
            "profiles_order": ["Profile 22", "Profile 3"],
            "info_cache": {
                "Profile 22": {"name": "cortexpilot", "gaia_name": "Example"},
                "Profile 3": {"name": "other"},
            },
        },
        "browser": {"theme": "keep-me"},
    }

    rewritten = singleton_module.build_repo_local_state(
        source_payload,
        source_profile_directory="Profile 22",
        target_profile_directory="Profile 1",
        display_name="cortexpilot",
    )

    profile_payload = rewritten["profile"]
    assert profile_payload["last_used"] == "Profile 1"
    assert profile_payload["last_active_profiles"] == ["Profile 1"]
    assert profile_payload["profiles_order"] == ["Profile 1"]
    assert profile_payload["info_cache"] == {
        "Profile 1": {"name": "cortexpilot", "gaia_name": "Example"}
    }
    assert rewritten["browser"] == {"theme": "keep-me"}


def test_migrate_default_chrome_profile_copies_only_local_state_and_target_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source-chrome"
    target_root = tmp_path / "repo-browser" / "chrome-user-data"
    source_profile = source_root / "Profile 22"
    source_profile.mkdir(parents=True, exist_ok=True)
    (source_profile / "Preferences").write_text("{}", encoding="utf-8")
    (source_root / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 22": {"name": "cortexpilot"}}, "last_used": "Profile 22"}}),
        encoding="utf-8",
    )
    (source_root / "SingletonLock").write_text("lock", encoding="utf-8")
    (source_root / "Other Root File").write_text("do-not-copy", encoding="utf-8")
    monkeypatch.setattr(singleton_module, "chrome_processes_using_default_root", lambda: [])
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda _path: None)

    result = singleton_module.migrate_default_chrome_profile(
        source_root=source_root,
        source_profile_name="cortexpilot",
        target_root=target_root,
    )

    assert result["status"] == "migrated"
    assert (target_root / "Local State").exists() is True
    assert (target_root / "Profile 1" / "Preferences").exists() is True
    assert (target_root / "Other Root File").exists() is False
    assert (target_root / "SingletonLock").exists() is False
    local_state = json.loads((target_root / "Local State").read_text(encoding="utf-8"))
    assert local_state["profile"]["last_used"] == "Profile 1"
    assert set(local_state["profile"]["info_cache"]) == {"Profile 1"}


def test_migrate_default_chrome_profile_returns_already_bootstrapped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source-chrome"
    target_root = tmp_path / "repo-browser" / "chrome-user-data"
    source_root.mkdir(parents=True, exist_ok=True)
    target_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 22": {"name": "cortexpilot"}}}}),
        encoding="utf-8",
    )
    (target_root / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    (target_root / "Profile 1").mkdir()
    monkeypatch.setattr(singleton_module, "chrome_processes_using_default_root", lambda: [])
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda _path: None)

    result = singleton_module.migrate_default_chrome_profile(
        source_root=source_root,
        source_profile_name="cortexpilot",
        target_root=target_root,
    )

    assert result["status"] == "already_bootstrapped"


def test_migrate_default_chrome_profile_fails_when_default_root_is_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source-chrome"
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 22": {"name": "cortexpilot"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        singleton_module,
        "chrome_processes_using_default_root",
        lambda: [
            singleton_module.ChromeProcessInfo(
                pid=999,
                args="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                user_data_dir=None,
                remote_debugging_port=None,
                uses_default_root=True,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="default Chrome root is still active"):
        singleton_module.migrate_default_chrome_profile(
            source_root=source_root,
            source_profile_name="cortexpilot",
            target_root=tmp_path / "target",
        )


def test_parse_chrome_process_line_preserves_user_data_dir_with_spaces() -> None:
    line = (
        "67422 "
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome "
        "--disable-blink-features=AutomationControlled "
        "--user-data-dir=/workspace/CortexPilot Repo/"
        ".runtime-cache/temp/batch-auth-chrome-user-data/Profile-1-abc "
        "--profile-directory=Profile 1 "
        "--remote-debugging-port=9221 "
        "--incognito about:blank"
    )

    parsed = singleton_module._parse_chrome_process_line(line)

    assert parsed is not None
    assert parsed.pid == 67422
    assert parsed.remote_debugging_port == 9221
    assert (
        parsed.user_data_dir
        == "/workspace/CortexPilot Repo/.runtime-cache/temp/batch-auth-chrome-user-data/Profile-1-abc"
    )


def test_ensure_repo_chrome_singleton_attaches_existing_matching_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: {"Browser": "Chrome", "webSocketDebuggerUrl": "ws://127.0.0.1/devtools/browser/1"},
    )
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: singleton_module.ChromeProcessInfo(
            pid=123,
            args="chrome --user-data-dir=/tmp/repo --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=port,
            uses_default_root=False,
        ),
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/preferred/chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
        requested_headless=True,
    )

    assert instance.connection_mode == "attached"
    assert instance.profile_directory == "Profile 1"
    assert instance.requested_headless is True
    assert instance.actual_headless is False


def test_ensure_repo_chrome_singleton_launches_when_no_instance_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    launches: list[list[str]] = []

    class _Proc:
        pid = 777

    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", lambda host, port, timeout_sec=15.0, poll_sec=0.25: {"ok": True})
    monkeypatch.setattr(
        singleton_module,
        "_verify_repo_chrome_launch_stability",
        lambda **kwargs: singleton_module.ChromeProcessInfo(
            pid=777,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9341,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module.subprocess,
        "Popen",
        lambda args, stdout, stderr, start_new_session=None: launches.append(args) or _Proc(),
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/preferred/chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
        extra_launch_args=["--disable-blink-features=AutomationControlled"],
    )

    assert instance.connection_mode == "launched"
    assert launches and f"--user-data-dir={user_data_dir.resolve()}" in launches[0]
    assert "--profile-directory=Profile 1" in launches[0]
    assert "--remote-debugging-port=9341" in launches[0]


def test_ensure_repo_chrome_singleton_launches_on_non_macos_without_unbound_flag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    launches: list[list[str]] = []

    class _Proc:
        pid = 778

    monkeypatch.setattr(singleton_module.sys, "platform", "linux")
    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", lambda host, port, timeout_sec=15.0, poll_sec=0.25: {"ok": True})
    monkeypatch.setattr(
        singleton_module,
        "_verify_repo_chrome_launch_stability",
        lambda **kwargs: singleton_module.ChromeProcessInfo(
            pid=778,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9341,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module.subprocess,
        "Popen",
        lambda args, stdout, stderr, start_new_session=None: launches.append(args) or _Proc(),
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/preferred/chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert instance.connection_mode == "launched"
    assert launches and launches[0][0] == "/preferred/chrome"
    assert "--remote-debugging-port=9341" in launches[0]


def test_ensure_repo_chrome_singleton_fails_closed_when_launch_does_not_stay_attached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    (user_data_dir / "SingletonLock").write_text("stale", encoding="utf-8")
    singleton_module.write_singleton_state(
        singleton_module.RepoChromeInstance(
            connection_mode="launched",
            pid=777,
            user_data_dir=str(user_data_dir),
            profile_directory="Profile 1",
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
            cdp_endpoint="http://127.0.0.1:9341",
            chrome_executable_path="/preferred/chrome",
            browser_root=str(user_data_dir.parent),
            actual_headless=False,
            requested_headless=False,
        )
    )
    launches: list[list[str]] = []
    state = {"phase": "launching"}

    class _Proc:
        pid = 777

    def _read_cdp_version(host: str, port: int, timeout_sec: float = 0.5) -> dict[str, object] | None:
        if state["phase"] == "stable_check":
            return None
        return None

    def _wait_for_cdp(host: str, port: int, timeout_sec: float = 15.0, poll_sec: float = 0.25) -> dict[str, bool]:
        state["phase"] = "stable_check"
        return {"ok": True}

    def _find_by_port(port: int) -> singleton_module.ChromeProcessInfo | None:
        if state["phase"] == "launching":
            return None
        return None

    monkeypatch.setattr(singleton_module, "read_cdp_version", _read_cdp_version)
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", _find_by_port)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", _wait_for_cdp)
    monkeypatch.setattr(singleton_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        singleton_module.subprocess,
        "Popen",
        lambda args, stdout, stderr, start_new_session=None: launches.append(args) or _Proc(),
    )

    with pytest.raises(RuntimeError, match="launch became stale"):
        singleton_module.ensure_repo_chrome_singleton(
            chrome_executable_path="/preferred/chrome",
            user_data_dir=user_data_dir,
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
        )

    assert launches and "--remote-debugging-port=9341" in launches[0]
    assert (user_data_dir / "SingletonLock").exists() is False
    assert singleton_module.singleton_state_path(user_data_dir).exists() is False


def test_ensure_repo_chrome_singleton_retries_via_mac_open_when_stability_check_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    launches: list[list[str]] = []
    state = {"phase": "launching"}

    class _Proc:
        pid = 888

    def _wait_for_cdp(host: str, port: int, timeout_sec: float = 15.0, poll_sec: float = 0.25) -> dict[str, bool]:
        if state["phase"] == "launching":
            state["phase"] = "stability_retry"
            return {"ok": True}
        state["phase"] = "ready"
        return {"ok": True}

    def _read_cdp(host: str, port: int, timeout_sec: float = 0.5) -> dict[str, object] | None:
        if state["phase"] == "stability_retry":
            return None
        if state["phase"] == "ready":
            return {"Browser": "Chrome"}
        return None

    def _find_by_port(port: int) -> singleton_module.ChromeProcessInfo | None:
        if state["phase"] == "ready":
            return singleton_module.ChromeProcessInfo(
                pid=999,
                args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
                user_data_dir=str(user_data_dir),
                remote_debugging_port=port,
                uses_default_root=False,
            )
        return None

    monkeypatch.setattr(singleton_module.sys, "platform", "darwin")
    monkeypatch.setattr(singleton_module, "read_cdp_version", _read_cdp)
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", _find_by_port)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", _wait_for_cdp)
    monkeypatch.setattr(singleton_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        singleton_module.subprocess,
        "Popen",
        lambda args, stdout, stderr, start_new_session=None: launches.append(args) or _Proc(),
    )
    monkeypatch.setattr(
        singleton_module,
        "_launch_repo_chrome_via_mac_open",
        lambda **kwargs: launches.append(
            ["open", "-na", "/Applications/Google Chrome.app", "--args", "--remote-debugging-port=9341"]
        )
        or True,
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/preferred/chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert instance.connection_mode == "launched"
    assert launches and launches[0][0] == "open"
    assert "--remote-debugging-port=9341" in launches[0]


def test_ensure_repo_chrome_singleton_retries_via_open_on_macos_when_initial_open_launch_never_binds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    launches: list[list[str]] = []
    state = {"phase": "before_retry"}

    class _Proc:
        pid = 888

    def _wait_for_cdp(host: str, port: int, timeout_sec: float = 15.0, poll_sec: float = 0.25) -> dict[str, bool]:
        if state["phase"] == "before_retry":
            state["phase"] = "after_first_fail"
            raise RuntimeError("Chrome CDP endpoint did not become ready")
        state["phase"] = "ready"
        return {"ok": True}

    def _find_by_port(port: int) -> singleton_module.ChromeProcessInfo | None:
        if state["phase"] != "ready":
            return None
        return singleton_module.ChromeProcessInfo(
            pid=999,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=port,
            uses_default_root=False,
        )

    monkeypatch.setattr(singleton_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        singleton_module,
        "_is_executable_file",
        lambda path: str(path) == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", _find_by_port)
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", _wait_for_cdp)
    monkeypatch.setattr(
        singleton_module,
        "_verify_repo_chrome_launch_stability",
        lambda **kwargs: singleton_module.ChromeProcessInfo(
            pid=999,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9341,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module,
        "_launch_chrome_process",
        lambda args: launches.append(args) or _Proc(),
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert instance.connection_mode == "launched"
    assert launches[0][:4] == ["open", "-na", "/Applications/Google Chrome.app", "--args"]
    assert launches[1][:4] == ["open", "-na", "/Applications/Google Chrome.app", "--args"]
    assert "--remote-debugging-port=9341" in launches[0]
    assert "--remote-debugging-port=9341" in launches[1]


def test_ensure_repo_chrome_singleton_fails_when_other_root_owns_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: {"Browser": "Chrome"},
    )
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: singleton_module.ChromeProcessInfo(
            pid=321,
            args="chrome --user-data-dir=/tmp/other --remote-debugging-port=9341",
            user_data_dir="/tmp/other",
            remote_debugging_port=port,
            uses_default_root=False,
        ),
    )

    with pytest.raises(RuntimeError, match="already owns the configured CDP port"):
        singleton_module.ensure_repo_chrome_singleton(
            chrome_executable_path="/preferred/chrome",
            user_data_dir=user_data_dir,
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
        )


def test_ensure_repo_chrome_singleton_relaunches_same_root_from_legacy_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    launches: list[list[str]] = []
    stopped: list[int] = []

    class _Proc:
        pid = 555

    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: singleton_module.ChromeProcessInfo(
            pid=444,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9334",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9334,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module,
        "_stop_repo_owned_root_process_for_relaunch",
        lambda process, timeout_sec=10.0: stopped.append(process.pid),
    )
    monkeypatch.setattr(singleton_module, "wait_for_cdp_version", lambda host, port, timeout_sec=15.0, poll_sec=0.25: {"ok": True})
    monkeypatch.setattr(
        singleton_module,
        "_verify_repo_chrome_launch_stability",
        lambda **kwargs: singleton_module.ChromeProcessInfo(
            pid=555,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9341,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module.subprocess,
        "Popen",
        lambda args, stdout, stderr, start_new_session=None: launches.append(args) or _Proc(),
    )

    instance = singleton_module.ensure_repo_chrome_singleton(
        chrome_executable_path="/preferred/chrome",
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert stopped == [444]
    assert launches and "--remote-debugging-port=9341" in launches[0]
    assert instance.connection_mode == "launched"
    assert instance.cdp_port == 9341


def test_ensure_repo_chrome_singleton_keeps_legacy_process_when_new_port_is_foreign(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    stopped: list[int] = []

    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: singleton_module.ChromeProcessInfo(
            pid=999,
            args="chrome --user-data-dir=/tmp/foreign --remote-debugging-port=9341",
            user_data_dir="/tmp/foreign",
            remote_debugging_port=9341,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: singleton_module.ChromeProcessInfo(
            pid=444,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9334",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9334,
            uses_default_root=False,
        ),
    )
    monkeypatch.setattr(
        singleton_module,
        "_stop_repo_owned_root_process_for_relaunch",
        lambda process, timeout_sec=10.0: stopped.append(process.pid),
    )

    with pytest.raises(RuntimeError, match="already owns the configured CDP port"):
        singleton_module.ensure_repo_chrome_singleton(
            chrome_executable_path="/preferred/chrome",
            user_data_dir=user_data_dir,
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
        )

    assert stopped == []


def test_ensure_repo_chrome_singleton_fails_closed_for_same_root_non_legacy_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(singleton_module, "_is_executable_file", lambda path: str(path) == "/preferred/chrome")
    monkeypatch.setattr(singleton_module, "read_cdp_version", lambda host, port, timeout_sec=0.5: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: singleton_module.ChromeProcessInfo(
            pid=777,
            args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9444",
            user_data_dir=str(user_data_dir),
            remote_debugging_port=9444,
            uses_default_root=False,
        ),
    )

    with pytest.raises(RuntimeError, match="non-managed Chrome process"):
        singleton_module.ensure_repo_chrome_singleton(
            chrome_executable_path="/preferred/chrome",
            user_data_dir=user_data_dir,
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
        )


def test_repo_chrome_singleton_cli_status_writes_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: None,
    )
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(singleton_module, "list_chrome_processes", lambda: [])

    payload = singleton_module.repo_chrome_status(
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert payload["user_data_dir"] == str(user_data_dir)
    assert payload["cdp_ready"] is False
    assert payload["singleton_status"] == "not_bootstrapped"
    assert payload["state_file_status"] == "absent"
    assert payload["machine_browser_process_count"] == 0
    assert payload["machine_browser_processes"] == []
    assert payload["new_launch_allowed"] is True


def test_repo_chrome_singleton_status_reports_stale_state_when_state_file_survives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    (user_data_dir / "Profile 1").mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text(
        json.dumps({"profile": {"info_cache": {"Profile 1": {"name": "cortexpilot"}}, "last_used": "Profile 1"}}),
        encoding="utf-8",
    )
    singleton_module.write_singleton_state(
        singleton_module.RepoChromeInstance(
            connection_mode="launched",
            pid=20105,
            user_data_dir=str(user_data_dir),
            profile_directory="Profile 1",
            profile_name="cortexpilot",
            cdp_host="127.0.0.1",
            cdp_port=9341,
            cdp_endpoint="http://127.0.0.1:9341",
            chrome_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            browser_root=str(user_data_dir.parent),
            actual_headless=False,
            requested_headless=False,
        )
    )
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: None,
    )
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_remote_debugging_port", lambda port: None)
    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda root: None)
    monkeypatch.setattr(
        singleton_module,
        "list_chrome_processes",
        lambda: [
            singleton_module.ChromeProcessInfo(
                pid=idx,
                args=f"chrome --remote-debugging-port={9300 + idx}",
                user_data_dir=f"/tmp/browser-{idx}",
                remote_debugging_port=9300 + idx,
                uses_default_root=False,
            )
            for idx in range(1, 8)
        ],
    )

    payload = singleton_module.repo_chrome_status(
        user_data_dir=user_data_dir,
        profile_name="cortexpilot",
        cdp_host="127.0.0.1",
        cdp_port=9341,
    )

    assert payload["cdp_ready"] is False
    assert payload["singleton_status"] == "offline_stale_state"
    assert payload["state_file_status"] == "stale"
    assert payload["machine_browser_process_count"] == 7
    assert len(payload["machine_browser_processes"]) == 7
    assert payload["machine_browser_processes"][0]["remote_debugging_port"] == 9301
    assert payload["new_launch_allowed"] is False


def test_clear_stale_singleton_files_uses_requested_cdp_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    stale_lock = user_data_dir / "SingletonLock"
    stale_lock.write_text("stale", encoding="utf-8")

    monkeypatch.setattr(singleton_module, "find_chrome_process_by_user_data_dir", lambda path: None)
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: (
            singleton_module.ChromeProcessInfo(
                pid=55,
                args="chrome --user-data-dir=/tmp/other --remote-debugging-port=9341",
                user_data_dir="/tmp/other",
                remote_debugging_port=9341,
                uses_default_root=False,
            )
            if port == 9341
            else None
        ),
    )

    removed = singleton_module._clear_stale_singleton_files_if_repo_root_is_offline(
        user_data_dir,
        cdp_port=9555,
    )

    assert removed == [str(stale_lock)]
    assert stale_lock.exists() is False


def test_verify_repo_chrome_launch_stability_requires_persistent_attachment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    matching_process = singleton_module.ChromeProcessInfo(
        pid=301,
        args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
        user_data_dir=str(user_data_dir),
        remote_debugging_port=9341,
        uses_default_root=False,
    )
    endpoint_states = iter([{"Browser": "Chrome"}, {"Browser": "Chrome"}, None])
    port_states = iter([matching_process, matching_process, None])
    root_states = iter([matching_process, matching_process, None])

    monkeypatch.setattr(singleton_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: next(endpoint_states),
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: next(port_states),
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: next(root_states),
    )

    with pytest.raises(RuntimeError, match="stayed stably attached"):
        singleton_module._verify_repo_chrome_launch_stability(
            user_data_dir=user_data_dir,
            cdp_host="127.0.0.1",
            cdp_port=9341,
            settle_sec=1.0,
            stable_samples=3,
        )


def test_verify_repo_chrome_launch_stability_accepts_three_stable_samples(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    matching_process = singleton_module.ChromeProcessInfo(
        pid=401,
        args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
        user_data_dir=str(user_data_dir),
        remote_debugging_port=9341,
        uses_default_root=False,
    )

    monkeypatch.setattr(singleton_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: {"Browser": "Chrome"},
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: matching_process,
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: matching_process,
    )

    stable_process = singleton_module._verify_repo_chrome_launch_stability(
        user_data_dir=user_data_dir,
        cdp_host="127.0.0.1",
        cdp_port=9341,
        settle_sec=1.0,
        stable_samples=3,
    )
    assert stable_process.pid == matching_process.pid


def test_verify_repo_chrome_launch_stability_fails_when_pid_changes_mid_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    user_data_dir = tmp_path / "browser" / "chrome-user-data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    first_process = singleton_module.ChromeProcessInfo(
        pid=501,
        args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
        user_data_dir=str(user_data_dir),
        remote_debugging_port=9341,
        uses_default_root=False,
    )
    second_process = singleton_module.ChromeProcessInfo(
        pid=777,
        args=f"chrome --user-data-dir={user_data_dir} --remote-debugging-port=9341",
        user_data_dir=str(user_data_dir),
        remote_debugging_port=9341,
        uses_default_root=False,
    )
    port_states = iter([first_process, second_process, second_process])

    monkeypatch.setattr(singleton_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        singleton_module,
        "read_cdp_version",
        lambda host, port, timeout_sec=0.5: {"Browser": "Chrome"},
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_remote_debugging_port",
        lambda port: next(port_states),
    )
    monkeypatch.setattr(
        singleton_module,
        "find_chrome_process_by_user_data_dir",
        lambda root: second_process,
    )

    with pytest.raises(RuntimeError, match="changed owning PID"):
        singleton_module._verify_repo_chrome_launch_stability(
            user_data_dir=user_data_dir,
            cdp_host="127.0.0.1",
            cdp_port=9341,
            settle_sec=1.0,
            stable_samples=3,
        )
