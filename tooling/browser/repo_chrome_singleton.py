from __future__ import annotations

import copy
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_DISPLAY_NAME = "cortexpilot"
DEFAULT_PROFILE_DIRECTORY = "Profile 1"
DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = 9341
SAFE_BROWSER_INSTANCE_THRESHOLD = 6
SINGLETON_FILENAMES = ("SingletonLock", "SingletonCookie", "SingletonSocket")
_CHROME_BROWSER_MARKER = "Google Chrome.app/Contents/MacOS/Google Chrome"
_USER_DATA_DIR_RE = re.compile(r"--user-data-dir=(.+?)(?=\s--[A-Za-z0-9-]+=|\s--[A-Za-z0-9-]+\b|$)")
_REMOTE_DEBUGGING_PORT_RE = re.compile(r"--remote-debugging-port=(\d+)")


@dataclass(frozen=True)
class ChromeProcessInfo:
    pid: int
    args: str
    user_data_dir: str | None
    remote_debugging_port: int | None
    uses_default_root: bool


@dataclass(frozen=True)
class RepoChromeInstance:
    connection_mode: str
    pid: int | None
    user_data_dir: str
    profile_directory: str
    profile_name: str
    cdp_host: str
    cdp_port: int
    cdp_endpoint: str
    chrome_executable_path: str
    browser_root: str
    actual_headless: bool
    requested_headless: bool

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


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


def _machine_cache_root() -> Path:
    explicit = _first_non_empty(os.getenv("CORTEXPILOT_MACHINE_CACHE_ROOT"))
    if explicit:
        return Path(explicit).expanduser()
    runner_temp = _first_non_empty(os.getenv("RUNNER_TEMP"))
    if runner_temp and _truthy_env("CI", "GITHUB_ACTIONS"):
        return Path(runner_temp) / "cortexpilot-machine-cache"
    xdg_cache_home = _first_non_empty(os.getenv("XDG_CACHE_HOME"))
    if xdg_cache_home:
        return Path(xdg_cache_home) / "cortexpilot"
    return Path.home() / ".cache" / "cortexpilot"


def default_repo_browser_root() -> Path:
    return _machine_cache_root() / "browser"


def default_repo_chrome_user_data_dir() -> Path:
    return default_repo_browser_root() / "chrome-user-data"


def default_source_chrome_root() -> Path:
    return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"


def default_cdp_host() -> str:
    return _first_non_empty(os.getenv("CORTEXPILOT_BROWSER_CDP_HOST"), DEFAULT_CDP_HOST)


def default_cdp_port() -> int:
    raw = _first_non_empty(os.getenv("CORTEXPILOT_BROWSER_CDP_PORT"), str(DEFAULT_CDP_PORT))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CDP_PORT
    return value if value > 0 else DEFAULT_CDP_PORT


def singleton_state_path(user_data_dir: Path | None = None) -> Path:
    browser_root = (user_data_dir or default_repo_chrome_user_data_dir()).resolve().parent
    return browser_root / "chrome-singleton.json"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def load_local_state(chrome_root: Path) -> dict[str, Any]:
    return _load_json(chrome_root / "Local State")


def resolve_profile_directory_name(chrome_root: Path, profile_name: str) -> str | None:
    requested = str(profile_name or "").strip() or "Default"
    direct_candidate = chrome_root / requested
    if direct_candidate.exists():
        return requested
    requested_folded = requested.casefold()
    info_cache = (((load_local_state(chrome_root) or {}).get("profile") or {}).get("info_cache") or {})
    if not isinstance(info_cache, dict):
        return None
    for directory_name, info in info_cache.items():
        if str(directory_name).casefold() == requested_folded:
            return str(directory_name)
        if isinstance(info, dict):
            display_name = str(info.get("name", "")).strip()
            if display_name and display_name.casefold() == requested_folded:
                return str(directory_name)
    return None


def build_repo_local_state(
    source_payload: dict[str, Any],
    *,
    source_profile_directory: str,
    target_profile_directory: str = DEFAULT_PROFILE_DIRECTORY,
    display_name: str = DEFAULT_PROFILE_DISPLAY_NAME,
) -> dict[str, Any]:
    payload = copy.deepcopy(source_payload) if isinstance(source_payload, dict) else {}
    profile_payload = payload.get("profile")
    if not isinstance(profile_payload, dict):
        profile_payload = {}
    info_cache = profile_payload.get("info_cache")
    if not isinstance(info_cache, dict):
        info_cache = {}
    source_info = info_cache.get(source_profile_directory)
    target_info = copy.deepcopy(source_info) if isinstance(source_info, dict) else {}
    target_info["name"] = display_name
    profile_payload["info_cache"] = {target_profile_directory: target_info}
    profile_payload["last_used"] = target_profile_directory
    profile_payload["last_active_profiles"] = [target_profile_directory]
    profile_payload["profiles_order"] = [target_profile_directory]
    payload["profile"] = profile_payload
    return payload


def is_bootstrapped_repo_chrome_root(
    user_data_dir: Path,
    *,
    profile_directory: str = DEFAULT_PROFILE_DIRECTORY,
) -> bool:
    return (user_data_dir / "Local State").exists() and (user_data_dir / profile_directory).is_dir()


def remove_singleton_files(user_data_dir: Path) -> list[str]:
    removed: list[str] = []
    for filename in SINGLETON_FILENAMES:
        candidate = user_data_dir / filename
        if candidate.exists():
            candidate.unlink(missing_ok=True)
            removed.append(str(candidate))
    return removed


def remove_singleton_state_file(user_data_dir: Path) -> bool:
    path = singleton_state_path(user_data_dir)
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True


def _clear_stale_singleton_files_if_repo_root_is_offline(user_data_dir: Path, *, cdp_port: int) -> list[str]:
    if find_chrome_process_by_user_data_dir(user_data_dir) is not None:
        return []
    if find_chrome_process_by_remote_debugging_port(cdp_port) is not None:
        return []
    removed = remove_singleton_files(user_data_dir)
    if removed:
        remove_singleton_state_file(user_data_dir)
    return removed


def _parse_chrome_process_line(line: str) -> ChromeProcessInfo | None:
    if _CHROME_BROWSER_MARKER not in line:
        return None
    pid_match = re.match(r"\s*(\d+)\s+(.*)", line)
    if not pid_match:
        return None
    pid = int(pid_match.group(1))
    args = pid_match.group(2)
    user_data_match = _USER_DATA_DIR_RE.search(args)
    port_match = _REMOTE_DEBUGGING_PORT_RE.search(args)
    user_data_dir = user_data_match.group(1) if user_data_match else None
    remote_debugging_port = int(port_match.group(1)) if port_match else None
    return ChromeProcessInfo(
        pid=pid,
        args=args,
        user_data_dir=user_data_dir,
        remote_debugging_port=remote_debugging_port,
        uses_default_root=user_data_dir is None,
    )


def list_chrome_processes() -> list[ChromeProcessInfo]:
    try:
        output = subprocess.check_output(["ps", "-axo", "pid=,args="], text=True)
    except Exception:  # noqa: BLE001
        return []
    processes: list[ChromeProcessInfo] = []
    for raw_line in output.splitlines():
        parsed = _parse_chrome_process_line(raw_line)
        if parsed is not None:
            processes.append(parsed)
    return processes


def chrome_processes_using_default_root() -> list[ChromeProcessInfo]:
    return [process for process in list_chrome_processes() if process.uses_default_root]


def _normalized_path_text(path: str | Path | None) -> str:
    if path is None:
        return ""
    return str(Path(path).expanduser().resolve(strict=False))


def find_chrome_process_by_user_data_dir(user_data_dir: Path) -> ChromeProcessInfo | None:
    expected = _normalized_path_text(user_data_dir)
    for process in list_chrome_processes():
        if _normalized_path_text(process.user_data_dir) == expected:
            return process
    return None


def find_chrome_process_by_remote_debugging_port(port: int) -> ChromeProcessInfo | None:
    for process in list_chrome_processes():
        if process.remote_debugging_port == port:
            return process
    return None


def _require_positive_pid(pid: int, *, context: str) -> int:
    if not isinstance(pid, int) or pid <= 0:
        raise RuntimeError(f"{context} requires a strictly positive PID, got: {pid!r}")
    return pid


def _find_live_chrome_process_by_pid(pid: int) -> ChromeProcessInfo | None:
    expected_pid = _require_positive_pid(pid, context="chrome process lookup")
    for process in list_chrome_processes():
        if process.pid == expected_pid:
            return process
    return None


def _chrome_process_matches(
    process: ChromeProcessInfo,
    *,
    expected_user_data_dir: str,
    expected_remote_debugging_port: int | None,
) -> bool:
    if _normalized_path_text(process.user_data_dir) != expected_user_data_dir:
        return False
    return process.remote_debugging_port == expected_remote_debugging_port


def read_cdp_version(host: str, port: int, *, timeout_sec: float = 0.5) -> dict[str, Any] | None:
    url = f"http://{host}:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def wait_for_cdp_version(host: str, port: int, *, timeout_sec: float = 15.0, poll_sec: float = 0.25) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = read_cdp_version(host, port, timeout_sec=min(poll_sec, 1.0))
        if payload is not None:
            return payload
        time.sleep(poll_sec)
    raise RuntimeError(f"Chrome CDP endpoint did not become ready at http://{host}:{port}/json/version")


def _is_executable_file(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    return candidate.is_file() and os.access(candidate, os.X_OK)


def resolve_real_chrome_executable_path() -> str:
    env_candidate = _first_non_empty(os.getenv("CHROME_PATH"))
    if env_candidate and _is_executable_file(env_candidate):
        return str(Path(env_candidate).expanduser())
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path.home() / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome",
    ]
    for candidate in candidates:
        if _is_executable_file(candidate):
            return str(candidate.expanduser())
    return ""


def _chrome_app_bundle_path(chrome_executable_path: str) -> str | None:
    candidate = Path(chrome_executable_path).expanduser().resolve(strict=False)
    for parent in (candidate, *candidate.parents):
        if parent.suffix == ".app":
            return str(parent)
    return None


def _launch_chrome_process(args: list[str]) -> subprocess.Popen[Any]:
    return subprocess.Popen(  # noqa: S603
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _launch_repo_chrome_via_mac_open(
    *,
    chrome_executable_path: str,
    launch_args: list[str],
) -> bool:
    if sys.platform != "darwin":
        return False
    bundle_path = _chrome_app_bundle_path(chrome_executable_path)
    if not bundle_path:
        return False
    _launch_chrome_process(["open", "-na", bundle_path, "--args", *launch_args])
    return True


def _verify_repo_chrome_launch_stability(
    *,
    user_data_dir: Path,
    cdp_host: str,
    cdp_port: int,
    settle_sec: float = 1.0,
    stable_samples: int = 3,
) -> ChromeProcessInfo:
    expected_root = _normalized_path_text(user_data_dir)
    required_samples = max(int(stable_samples), 1)
    sample_sleep_sec = max(settle_sec, 0.0)
    timeout_sec = min(max(settle_sec, 0.5), 1.0)
    stable_process: ChromeProcessInfo | None = None

    for sample_idx in range(required_samples):
        if sample_sleep_sec > 0:
            time.sleep(sample_sleep_sec)

        endpoint_payload = read_cdp_version(cdp_host, cdp_port, timeout_sec=timeout_sec)
        port_process = find_chrome_process_by_remote_debugging_port(cdp_port)
        root_process = find_chrome_process_by_user_data_dir(user_data_dir)

        port_process_matches_root = (
            port_process is not None and _normalized_path_text(port_process.user_data_dir) == expected_root
        )
        root_process_matches_root = (
            root_process is not None and _normalized_path_text(root_process.user_data_dir) == expected_root
        )

        if endpoint_payload is not None and port_process_matches_root and port_process is not None:
            if stable_process is None:
                stable_process = port_process
            elif stable_process.pid != port_process.pid:
                raise RuntimeError(
                    "repo Chrome launch changed owning PID before the repo-owned singleton stayed stably attached to the expected CDP endpoint"
                )
            continue
        if root_process_matches_root:
            raise RuntimeError(
                "repo Chrome launch became unstable: the repo-owned browser root is still running but CDP is no longer ready"
            )
        if sample_idx == 0:
            raise RuntimeError(
                "repo Chrome launch became stale before the repo-owned singleton stayed attached to the expected CDP endpoint"
            )
        raise RuntimeError(
            "repo Chrome launch became stale before the repo-owned singleton stayed stably attached to the expected CDP endpoint"
        )

    if stable_process is None:
        raise RuntimeError(
            "repo Chrome launch finished its stability window without a verified repo-owned CDP process"
        )
    return stable_process


def write_singleton_state(instance: RepoChromeInstance) -> Path:
    path = singleton_state_path(Path(instance.user_data_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = instance.to_metadata()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_singleton_state(user_data_dir: Path | None = None) -> dict[str, Any]:
    return _load_json(singleton_state_path(user_data_dir))


def _wait_for_process_exit(process: ChromeProcessInfo, *, timeout_sec: float = 10.0, poll_sec: float = 0.2) -> bool:
    expected_pid = _require_positive_pid(process.pid, context="Chrome exit wait")
    expected_root = _normalized_path_text(process.user_data_dir)
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        live_process = _find_live_chrome_process_by_pid(expected_pid)
        if live_process is None:
            return True
        if not _chrome_process_matches(
            live_process,
            expected_user_data_dir=expected_root,
            expected_remote_debugging_port=process.remote_debugging_port,
        ):
            return True
        time.sleep(poll_sec)
    return False


def _stop_repo_owned_root_process_for_relaunch(process: ChromeProcessInfo, *, timeout_sec: float = 10.0) -> None:
    expected_pid = _require_positive_pid(process.pid, context="repo Chrome relaunch stop")
    expected_root = _normalized_path_text(process.user_data_dir)
    if not expected_root:
        raise RuntimeError("refusing to stop repo Chrome process without a recorded repo-owned user-data-dir")
    live_process = _find_live_chrome_process_by_pid(expected_pid)
    if live_process is None:
        return
    if not _chrome_process_matches(
        live_process,
        expected_user_data_dir=expected_root,
        expected_remote_debugging_port=process.remote_debugging_port,
    ):
        raise RuntimeError(
            f"refusing to stop Chrome PID {expected_pid} because it no longer matches the repo-owned browser root"
        )
    try:
        os.kill(expected_pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise RuntimeError(
            f"failed to stop repo Chrome process {expected_pid} for relaunch after remote debugging port mismatch "
            f"(actual port: {process.remote_debugging_port})"
        ) from exc
    if not _wait_for_process_exit(live_process, timeout_sec=timeout_sec):
        raise RuntimeError(
            f"repo Chrome process {expected_pid} using remote debugging port {process.remote_debugging_port} "
            f"did not stop in time for relaunch after port mismatch; close it and relaunch via repo launcher"
        )


def migrate_default_chrome_profile(
    *,
    source_root: Path,
    source_profile_name: str,
    target_root: Path,
    target_profile_directory: str = DEFAULT_PROFILE_DIRECTORY,
    target_display_name: str = DEFAULT_PROFILE_DISPLAY_NAME,
    reseed: bool = False,
) -> dict[str, Any]:
    if not source_root.exists():
        raise RuntimeError(f"source Chrome root not found: {source_root}")
    if chrome_processes_using_default_root():
        blockers = ", ".join(str(process.pid) for process in chrome_processes_using_default_root())
        raise RuntimeError(f"default Chrome root is still active; close those Chrome processes first: {blockers}")
    if find_chrome_process_by_user_data_dir(target_root) is not None:
        raise RuntimeError("repo Chrome root is already active; stop that instance before migrating or reseeding")
    if is_bootstrapped_repo_chrome_root(target_root, profile_directory=target_profile_directory) and not reseed:
        resolved = resolve_profile_directory_name(target_root, target_display_name) or target_profile_directory
        return {
            "status": "already_bootstrapped",
            "source_root": str(source_root),
            "source_profile_name": source_profile_name,
            "target_root": str(target_root),
            "target_profile_directory": resolved,
            "removed_singleton_files": [],
        }

    source_local_state = load_local_state(source_root)
    if not source_local_state:
        raise RuntimeError(f"source Local State missing or unreadable: {source_root / 'Local State'}")
    source_profile_directory = resolve_profile_directory_name(source_root, source_profile_name)
    if not source_profile_directory:
        raise RuntimeError(f"source Chrome profile directory not found for display name `{source_profile_name}`")
    source_profile_root = source_root / source_profile_directory
    if not source_profile_root.is_dir():
        raise RuntimeError(f"source Chrome profile directory missing: {source_profile_root}")

    if target_root.exists() and reseed:
        shutil.rmtree(target_root)
    elif target_root.exists() and any(target_root.iterdir()):
        raise RuntimeError(
            "target repo Chrome root already exists but is incomplete; use --reseed to rebuild it explicitly"
        )

    target_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_profile_root, target_root / target_profile_directory, dirs_exist_ok=False)
    rewritten_local_state = build_repo_local_state(
        source_local_state,
        source_profile_directory=source_profile_directory,
        target_profile_directory=target_profile_directory,
        display_name=target_display_name,
    )
    (target_root / "Local State").write_text(
        json.dumps(rewritten_local_state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    removed_singletons = remove_singleton_files(target_root)
    return {
        "status": "migrated",
        "source_root": str(source_root),
        "source_profile_name": source_profile_name,
        "source_profile_directory": source_profile_directory,
        "target_root": str(target_root),
        "target_profile_directory": target_profile_directory,
        "target_display_name": target_display_name,
        "removed_singleton_files": removed_singletons,
    }


def ensure_repo_chrome_singleton(
    *,
    chrome_executable_path: str,
    user_data_dir: Path,
    profile_name: str,
    cdp_host: str,
    cdp_port: int,
    extra_launch_args: list[str] | None = None,
    requested_headless: bool = False,
    cdp_timeout_sec: float = 15.0,
) -> RepoChromeInstance:
    if not chrome_executable_path or not _is_executable_file(chrome_executable_path):
        raise RuntimeError("real Chrome executable not found")
    if not is_bootstrapped_repo_chrome_root(user_data_dir):
        raise RuntimeError("repo Chrome root is not bootstrapped; run the repo Chrome migrate command first")

    profile_directory = resolve_profile_directory_name(user_data_dir, profile_name)
    if not profile_directory:
        raise RuntimeError(f"repo Chrome profile directory not found for profile `{profile_name}`")

    expected_root = _normalized_path_text(user_data_dir)
    endpoint_payload = read_cdp_version(cdp_host, cdp_port)
    port_process = find_chrome_process_by_remote_debugging_port(cdp_port)

    if endpoint_payload is not None:
        if port_process is None:
            raise RuntimeError("repo Chrome CDP endpoint is live but the owning Chrome process could not be resolved")
        if _normalized_path_text(port_process.user_data_dir) != expected_root:
            raise RuntimeError("another Chrome instance already owns the configured CDP port")
        instance = RepoChromeInstance(
            connection_mode="attached",
            pid=port_process.pid,
            user_data_dir=expected_root,
            profile_directory=profile_directory,
            profile_name=profile_name,
            cdp_host=cdp_host,
            cdp_port=cdp_port,
            cdp_endpoint=f"http://{cdp_host}:{cdp_port}",
            chrome_executable_path=chrome_executable_path,
            browser_root=str(user_data_dir.parent),
            actual_headless=False,
            requested_headless=bool(requested_headless),
        )
        write_singleton_state(instance)
        return instance

    root_process = find_chrome_process_by_user_data_dir(user_data_dir)
    if root_process is not None:
        if root_process.remote_debugging_port != cdp_port:
            if root_process.remote_debugging_port == 9334 and cdp_port == 9341:
                if port_process is not None and _normalized_path_text(port_process.user_data_dir) != expected_root:
                    raise RuntimeError("another Chrome instance already owns the configured CDP port")
                _stop_repo_owned_root_process_for_relaunch(root_process)
            else:
                raise RuntimeError(
                    "this repo Chrome root is already occupied by a non-managed Chrome process; "
                    "close it or relaunch via repo launcher"
                )
        else:
            wait_for_cdp_version(cdp_host, cdp_port, timeout_sec=cdp_timeout_sec)
            instance = RepoChromeInstance(
                connection_mode="attached",
                pid=root_process.pid,
                user_data_dir=expected_root,
                profile_directory=profile_directory,
                profile_name=profile_name,
                cdp_host=cdp_host,
                cdp_port=cdp_port,
                cdp_endpoint=f"http://{cdp_host}:{cdp_port}",
                chrome_executable_path=chrome_executable_path,
                browser_root=str(user_data_dir.parent),
                actual_headless=False,
                requested_headless=bool(requested_headless),
            )
            write_singleton_state(instance)
            return instance

    if port_process is not None and _normalized_path_text(port_process.user_data_dir) != expected_root:
        raise RuntimeError("another Chrome instance already owns the configured CDP port")

    _clear_stale_singleton_files_if_repo_root_is_offline(user_data_dir, cdp_port=cdp_port)

    launch_args = [
        f"--user-data-dir={expected_root}",
        f"--profile-directory={profile_directory}",
        f"--remote-debugging-address={cdp_host}",
        f"--remote-debugging-port={cdp_port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "about:blank",
    ]
    for arg in extra_launch_args or []:
        if isinstance(arg, str) and arg.strip():
            launch_args.append(arg)
    launched_via_mac_open = False
    if sys.platform == "darwin":
        launched_via_mac_open = _launch_repo_chrome_via_mac_open(
            chrome_executable_path=chrome_executable_path,
            launch_args=launch_args,
        )
    proc = None if launched_via_mac_open else _launch_chrome_process([chrome_executable_path, *launch_args])
    try:
        wait_for_cdp_version(cdp_host, cdp_port, timeout_sec=cdp_timeout_sec)
    except RuntimeError:
        launch_retry_allowed = (
            sys.platform == "darwin"
            and find_chrome_process_by_user_data_dir(user_data_dir) is None
            and find_chrome_process_by_remote_debugging_port(cdp_port) is None
        )
        if not launch_retry_allowed or not _launch_repo_chrome_via_mac_open(
            chrome_executable_path=chrome_executable_path,
            launch_args=launch_args,
        ):
            raise
        wait_for_cdp_version(cdp_host, cdp_port, timeout_sec=cdp_timeout_sec)
    launched_process = find_chrome_process_by_remote_debugging_port(cdp_port)
    if launched_process is not None and _normalized_path_text(launched_process.user_data_dir) != expected_root:
        raise RuntimeError("launched Chrome did not bind to the expected repo browser root")
    try:
        stable_process = _verify_repo_chrome_launch_stability(
            user_data_dir=user_data_dir,
            cdp_host=cdp_host,
            cdp_port=cdp_port,
        )
    except RuntimeError:
        stability_retry_allowed = (
            sys.platform == "darwin"
            and find_chrome_process_by_user_data_dir(user_data_dir) is None
            and find_chrome_process_by_remote_debugging_port(cdp_port) is None
        )
        if stability_retry_allowed and _launch_repo_chrome_via_mac_open(
            chrome_executable_path=chrome_executable_path,
            launch_args=launch_args,
        ):
            wait_for_cdp_version(cdp_host, cdp_port, timeout_sec=cdp_timeout_sec)
            stable_process = _verify_repo_chrome_launch_stability(
                user_data_dir=user_data_dir,
                cdp_host=cdp_host,
                cdp_port=cdp_port,
            )
        else:
            _clear_stale_singleton_files_if_repo_root_is_offline(user_data_dir, cdp_port=cdp_port)
            raise
    instance = RepoChromeInstance(
        connection_mode="launched",
        pid=stable_process.pid if stable_process is not None else (launched_process.pid if launched_process is not None else proc.pid),
        user_data_dir=expected_root,
        profile_directory=profile_directory,
        profile_name=profile_name,
        cdp_host=cdp_host,
        cdp_port=cdp_port,
        cdp_endpoint=f"http://{cdp_host}:{cdp_port}",
        chrome_executable_path=chrome_executable_path,
        browser_root=str(user_data_dir.parent),
        actual_headless=False,
        requested_headless=bool(requested_headless),
    )
    write_singleton_state(instance)
    return instance


def repo_chrome_status(
    *,
    user_data_dir: Path,
    profile_name: str,
    cdp_host: str,
    cdp_port: int,
) -> dict[str, Any]:
    state = read_singleton_state(user_data_dir)
    profile_directory = resolve_profile_directory_name(user_data_dir, profile_name) if user_data_dir.exists() else None
    port_process = find_chrome_process_by_remote_debugging_port(cdp_port)
    root_process = find_chrome_process_by_user_data_dir(user_data_dir)
    endpoint_payload = read_cdp_version(cdp_host, cdp_port)
    expected_root = _normalized_path_text(user_data_dir)
    port_process_matches_root = (
        port_process is not None and _normalized_path_text(port_process.user_data_dir) == expected_root
    )
    root_process_matches_root = (
        root_process is not None and _normalized_path_text(root_process.user_data_dir) == expected_root
    )
    state_pid_raw = state.get("pid") if isinstance(state, dict) else None
    try:
        state_pid = int(state_pid_raw) if state_pid_raw is not None else None
    except (TypeError, ValueError):
        state_pid = None
    state_matches_port_process = state_pid is not None and port_process is not None and state_pid == port_process.pid
    state_matches_root_process = state_pid is not None and root_process is not None and state_pid == root_process.pid
    machine_browser_processes = list_chrome_processes()
    machine_browser_process_count = len(machine_browser_processes)
    new_launch_allowed = (
        machine_browser_process_count <= SAFE_BROWSER_INSTANCE_THRESHOLD
        or port_process_matches_root
        or root_process_matches_root
    )

    if not state:
        state_file_status = "absent"
    elif state_matches_port_process or state_matches_root_process:
        state_file_status = "live_match"
    elif port_process is None and root_process is None and endpoint_payload is None:
        state_file_status = "stale"
    else:
        state_file_status = "present_mismatch"

    if not is_bootstrapped_repo_chrome_root(user_data_dir):
        singleton_status = "not_bootstrapped"
    elif endpoint_payload is not None and port_process_matches_root:
        singleton_status = "cdp_live"
    elif endpoint_payload is not None and not port_process_matches_root:
        singleton_status = "foreign_port_owner"
    elif root_process_matches_root and root_process is not None and root_process.remote_debugging_port != cdp_port:
        singleton_status = "root_process_wrong_port"
    elif root_process_matches_root and endpoint_payload is None:
        singleton_status = "root_process_without_cdp"
    elif state_file_status == "stale":
        singleton_status = "offline_stale_state"
    else:
        singleton_status = "offline"

    return {
        "user_data_dir": str(user_data_dir),
        "browser_root": str(user_data_dir.parent),
        "bootstrapped": is_bootstrapped_repo_chrome_root(user_data_dir),
        "profile_name": profile_name,
        "profile_directory": profile_directory,
        "cdp_host": cdp_host,
        "cdp_port": cdp_port,
        "cdp_ready": endpoint_payload is not None,
        "cdp_endpoint": f"http://{cdp_host}:{cdp_port}",
        "singleton_status": singleton_status,
        "state_file_status": state_file_status,
        "machine_browser_process_count": machine_browser_process_count,
        "machine_browser_processes": [asdict(process) for process in machine_browser_processes],
        "launch_safe_threshold": SAFE_BROWSER_INSTANCE_THRESHOLD,
        "new_launch_allowed": new_launch_allowed,
        "port_process": asdict(port_process) if port_process else None,
        "root_process": asdict(root_process) if root_process else None,
        "state_file": state,
    }
