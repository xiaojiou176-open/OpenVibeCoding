from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scripts.host_process_safety import terminate_tracked_child
try:
    import fcntl
except Exception:  # noqa: BLE001
    fcntl = None

from scripts.ui_full_e2e_gemini_audit_common import APP_DIR, ROOT, ensure_dir


def http_json(
    base: str,
    path: str,
    method: str = "GET",
    token: str = "",
    payload: dict[str, Any] | None = None,
    timeout_sec: int = 15,
) -> dict[str, Any] | list[Any]:
    data = None
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["x-openvibecoding-role"] = "OWNER"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{base}{path}",
        method=method,
        data=data,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8")
        if not body.strip():
            return {}
        parsed = json.loads(body)
        if isinstance(parsed, (dict, list)):
            return parsed
        return {"value": parsed}


def wait_http_ok(url: str, timeout_sec: int) -> None:
    started = time.time()
    while time.time() - started < timeout_sec:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=4) as resp:
                if 200 <= int(resp.status) < 500:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"timeout waiting: {url}")


def http_ok(url: str, timeout_sec: int = 3) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= int(resp.status) < 500
    except Exception:
        return False


def goto_with_retry(
    page: Any,
    url: str,
    *,
    wait_until: str,
    timeout_ms: int,
    max_attempts: int = 3,
    backoff_ms: int = 500,
) -> None:
    attempts = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts:
                page.wait_for_timeout(max(100, int(backoff_ms) * attempt))
                continue
            break
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"goto failed without exception: {url}")


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, int(port))) == 0


def resolve_free_port(host: str, preferred_port: int, *, avoid_port: int | None = None, max_shift: int = 200) -> int:
    port = int(preferred_port)
    end = port + int(max_shift)
    while port <= end:
        if avoid_port is not None and port == int(avoid_port):
            port += 1
            continue
        if not port_in_use(host, port):
            return port
        port += 1
    raise RuntimeError(
        f"unable to resolve free port for host={host}, preferred={preferred_port}, "
        f"avoid={avoid_port}, max_shift={max_shift}"
    )


def spawn_process(cmd: list[str], log_path: Path, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    ensure_dir(log_path.parent)
    fp = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=fp,
        stderr=subprocess.STDOUT,
        text=True,
    )


def kill_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    terminate_tracked_child(proc, term_timeout_sec=5, kill_timeout_sec=3)


def _probe_playwright_browser() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser.close()


def _ensure_playwright_tmpdir(scope: str = "ui-full-e2e") -> None:
    temp_root = str(os.environ.get("RUNNER_TEMP", "")).strip()
    if not temp_root:
        temp_root = str(ROOT / ".runtime-cache" / "openvibecoding" / "temp")
    target_dir = Path(temp_root) / "playwright-artifacts" / scope
    ensure_dir(target_dir)
    os.environ["TMPDIR"] = str(target_dir)
    os.environ["TMP"] = str(target_dir)
    os.environ["TEMP"] = str(target_dir)


@contextmanager
def _playwright_browser_bootstrap_lock() -> Any:
    if fcntl is None:
        yield
        return
    lock_path = Path(
            os.environ.get(
                "OPENVIBECODING_UI_PLAYWRIGHT_BOOTSTRAP_LOCK",
                str(ROOT / ".runtime-cache" / "openvibecoding" / "locks" / "ui_playwright_browser_bootstrap.lock"),
            )
    )
    ensure_dir(lock_path.parent)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)



def ensure_playwright_browser_ready(
    *,
    python_executable: str,
    probe_browser: Any | None = None,
    run_command: Any = subprocess.run,
    logger: Any | None = None,
) -> None:
    def _noop_logger(message: str) -> None:
        _ = message

    log = logger or _noop_logger
    probe = probe_browser or _probe_playwright_browser
    _ensure_playwright_tmpdir()

    with _playwright_browser_bootstrap_lock():
        try:
            probe()
            log("✅ [ui-full-e2e] Playwright browser already available")
            return
        except Exception as exc:
            if isinstance(exc, OSError) and exc.errno == getattr(os, "ENOSPC", 28):
                raise RuntimeError(f"Playwright browser probe hit ENOSPC: {exc}") from exc
            if "no space left on device" in str(exc).lower():
                raise RuntimeError(f"Playwright browser probe hit ENOSPC: {exc}") from exc
            log(f"⚠️ [ui-full-e2e] Playwright browser probe failed, installing browsers: {exc}")

        result = run_command(
            [python_executable, "-m", "playwright", "install"],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        if int(result.returncode) != 0:
            detail = str(result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"Playwright browser bootstrap failed: {detail or 'playwright install exited non-zero'}")

        try:
            probe()
        except Exception as exc:
            raise RuntimeError(f"Playwright browser remained unavailable after install: {exc}") from exc

        log("✅ [ui-full-e2e] Playwright browser install completed and probe passed")



def discover_page_routes() -> list[str]:
    routes: list[str] = []
    candidates = list(APP_DIR.rglob("page.tsx")) + list(APP_DIR.rglob("page.ts"))
    for file in sorted(set(candidates)):
        rel = file.relative_to(APP_DIR)
        folder = rel.parent.as_posix()
        if folder == ".":
            routes.append("/")
        else:
            routes.append("/" + folder)
    return sorted(set(routes))


def route_with_dynamic_ids(route: str, ids: dict[str, str]) -> str | None:
    matches = list(re.finditer(r"\[([^\]/]+)\]", route))
    if not matches:
        return route
    resolved = route
    for match in matches:
        key = str(match.group(1) or "").strip()
        value = str(ids.get(key) or "").strip()
        if not value and key == "id":
            # Backward-compatible aliases for existing dynamic routes that used [id].
            if route.startswith("/workflows/"):
                value = str(ids.get("workflow_id") or "").strip()
            elif route.startswith("/command-tower/sessions/"):
                value = str(ids.get("pm_session_id") or "").strip()
        if not value:
            value = str(ids.get("run_id") or "").strip()
        if not value:
            return None
        resolved = resolved.replace(match.group(0), urllib.parse.quote(value), 1)
    return resolved


def safe_screenshot(page: Any, path: Path, *, full_page: bool, timeout_ms: int = 0) -> None:
    try:
        page.screenshot(path=str(path), full_page=full_page, timeout=timeout_ms, animations="disabled")
        return
    except Exception:
        if full_page:
            page.screenshot(path=str(path), full_page=False, timeout=timeout_ms, animations="disabled")
            return
        raise


def safe_close_page(page: Any) -> None:
    if page is None:
        return
    try:
        if hasattr(page, "is_closed") and page.is_closed():
            return
    except Exception:
        pass
    try:
        page.close()
    except Exception:
        pass


def safe_close_context(context: Any) -> None:
    if context is None:
        return
    try:
        context.close()
    except Exception:
        pass


def safe_close_browser(browser: Any) -> None:
    if browser is None:
        return
    try:
        if hasattr(browser, "is_connected") and not browser.is_connected():
            return
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass


def _is_executable_file(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _iter_playwright_browser_roots() -> list[Path]:
    raw_roots = [str(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")).strip()]
    home = Path.home()
    raw_roots.extend(
        [
            str(home / "Library" / "Caches" / "ms-playwright"),
            str(home / ".cache" / "ms-playwright"),
        ]
    )
    roots: list[Path] = []
    seen: set[str] = set()
    for raw in raw_roots:
        if not raw or raw == "0":
            continue
        resolved = str(Path(raw).expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(Path(resolved))
    return roots


def _resolve_preferred_chrome_path() -> str:
    env_candidate = str(os.environ.get("CHROME_PATH", "")).strip()
    if env_candidate and _is_executable_file(env_candidate):
        return str(Path(env_candidate).expanduser())

    candidate_patterns = [
        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-linux*/chrome",
        "chromium-*/chrome-win*/chrome.exe",
        "chromium_headless_shell-*/chrome-headless-shell-mac-arm64/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-mac-x64/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
    ]
    for root in _iter_playwright_browser_roots():
        if not root.exists():
            continue
        for pattern in candidate_patterns:
            for candidate in sorted(root.glob(pattern)):
                if _is_executable_file(candidate):
                    return str(candidate)
    return ""


def _launch_chromium(playwright_runtime: Any, *, headless: bool) -> Any:
    launch_kwargs: dict[str, Any] = {"headless": headless}
    preferred_chrome_path = _resolve_preferred_chrome_path()
    if not preferred_chrome_path:
        runtime_candidate = str(getattr(playwright_runtime.chromium, "executable_path", "") or "").strip()
        if runtime_candidate and _is_executable_file(runtime_candidate):
            preferred_chrome_path = str(Path(runtime_candidate).expanduser())
    if preferred_chrome_path:
        launch_kwargs["executable_path"] = preferred_chrome_path
    return playwright_runtime.chromium.launch(**launch_kwargs)


def create_context_page(browser: Any, *, navigation_timeout_ms: int) -> tuple[Any, Any]:
    context = browser.new_context(viewport={"width": 1600, "height": 960})
    page = context.new_page()
    page.set_default_timeout(navigation_timeout_ms)
    return context, page


def _browser_needs_rebuild(browser: Any | None) -> bool:
    if browser is None:
        return True
    try:
        return not bool(browser.is_connected())
    except Exception:
        return True


def _context_needs_rebuild(context: Any | None) -> bool:
    if context is None:
        return True
    try:
        probe = context.new_page()
    except Exception:
        return True
    safe_close_page(probe)
    return False


def _page_is_unavailable(page: Any | None) -> bool:
    if page is None:
        return True
    try:
        return bool(page.is_closed())
    except Exception:
        return True


def ensure_route_runtime(
    *,
    playwright_runtime: Any,
    browser: Any | None,
    context: Any | None,
    page: Any | None,
    navigation_timeout_ms: int,
    headless: bool,
) -> tuple[Any, Any, Any, bool]:
    rebuilt = False
    active_browser = browser
    active_context = context
    active_page = page

    if _browser_needs_rebuild(active_browser):
        safe_close_page(active_page)
        safe_close_context(active_context)
        safe_close_browser(active_browser)
        active_browser = _launch_chromium(playwright_runtime, headless=headless)
        active_context, active_page = create_context_page(
            active_browser,
            navigation_timeout_ms=navigation_timeout_ms,
        )
        return active_browser, active_context, active_page, True

    if _context_needs_rebuild(active_context):
        safe_close_page(active_page)
        safe_close_context(active_context)
        active_context, active_page = create_context_page(
            active_browser,
            navigation_timeout_ms=navigation_timeout_ms,
        )
        rebuilt = True

    if _page_is_unavailable(active_page):
        safe_close_page(active_page)
        if active_context is None:
            raise RuntimeError("route runtime missing browser context after rebuild check")
        active_page = active_context.new_page()
        active_page.set_default_timeout(navigation_timeout_ms)
        rebuilt = True

    return active_browser, active_context, active_page, rebuilt


def rebuild_route_runtime(
    *,
    playwright_runtime: Any,
    browser: Any | None,
    context: Any | None,
    page: Any | None,
    navigation_timeout_ms: int,
    headless: bool,
) -> tuple[Any, Any, Any]:
    safe_close_page(page)
    safe_close_context(context)
    safe_close_browser(browser)
    new_browser = _launch_chromium(playwright_runtime, headless=headless)
    new_context, new_page = create_context_page(new_browser, navigation_timeout_ms=navigation_timeout_ms)
    return new_browser, new_context, new_page
