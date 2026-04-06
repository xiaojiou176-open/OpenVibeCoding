from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

audit_module = importlib.import_module("scripts.ui_full_e2e_gemini_audit")
runtime_module = importlib.import_module("scripts.ui_full_e2e_gemini_audit_runtime")


def _completed_process(
    cmd: list[str], *, returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)


def _build_args() -> argparse.Namespace:
    return argparse.Namespace(
        provider="gemini",
        provider_base_url="",
        provider_model="",
        gemini_model="gemini-3.0-flash",
        thinking_level="high",
    )


def _build_runtime_args() -> argparse.Namespace:
    return argparse.Namespace(
        host="127.0.0.1",
        api_port=19600,
        dashboard_port=19700,
        external_api_base="",
        external_dashboard_base="",
        api_token="cortexpilot-e2e-token",
        provider="gemini",
        provider_base_url="",
        provider_model="",
        gemini_model="gemini-3.0-flash",
        thinking_level="high",
        gemini_key_env="GEMINI_API_KEY",
        gemini_request_timeout_sec=75,
        gemini_max_attempts=5,
        max_pages=0,
        max_buttons_per_page=120,
        max_interactions=504,
        max_duplicate_targets=3,
        navigation_timeout_ms=30000,
        action_timeout_ms=10000,
        page_settle_ms=1500,
        interaction_settle_ms=1200,
        max_runtime_sec=0,
        heartbeat_interval_sec=20,
        run_id="test-run",
        route_shard_total=1,
        route_shard_index=0,
        headed=False,
    )


def test_repo_root_scripts_package_imports_resolve() -> None:
    audit = importlib.import_module("scripts.ui_full_e2e_gemini_audit")
    runtime = importlib.import_module("scripts.ui_full_e2e_gemini_audit_runtime")
    assert callable(audit.main)
    assert callable(runtime.ensure_route_runtime)


def test_ensure_playwright_browser_ready_uses_bootstrap_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class _Lock:
        def __enter__(self) -> None:
            events.append("enter")
            return None

        def __exit__(self, _exc_type, _exc, _tb) -> None:
            events.append("exit")
            return None

    monkeypatch.setattr(runtime_module, "_playwright_browser_bootstrap_lock", lambda: _Lock())

    runtime_module.ensure_playwright_browser_ready(
        python_executable="/tmp/python",
        probe_browser=lambda: None,
        run_command=lambda cmd, **kwargs: _completed_process(cmd),
        logger=lambda _unused: None,
    )

    assert events == ["enter", "exit"]



def test_ensure_playwright_browser_ready_skips_install_when_probe_succeeds() -> None:
    probe_calls: list[str] = []
    install_calls: list[tuple[list[str], dict[str, object]]] = []
    logs: list[str] = []

    def probe() -> None:
        probe_calls.append("probe")

    def run_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        install_calls.append((cmd, kwargs))
        return _completed_process(cmd)

    runtime_module.ensure_playwright_browser_ready(
        python_executable="/tmp/python",
        probe_browser=probe,
        run_command=run_command,
        logger=logs.append,
    )

    assert probe_calls == ["probe"]
    assert install_calls == []
    assert any("already available" in line for line in logs)



def test_ensure_playwright_browser_ready_installs_then_rechecks() -> None:
    probe_calls: list[str] = []
    install_calls: list[tuple[list[str], dict[str, object]]] = []

    def probe() -> None:
        probe_calls.append("probe")
        if len(probe_calls) == 1:
            raise RuntimeError("missing browser")

    def run_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        install_calls.append((cmd, kwargs))
        return _completed_process(cmd, stdout="installed")

    runtime_module.ensure_playwright_browser_ready(
        python_executable="/tmp/python",
        probe_browser=probe,
        run_command=run_command,
        logger=lambda _unused: None,
    )

    assert probe_calls == ["probe", "probe"]
    assert install_calls == [
        (
            ["/tmp/python", "-m", "playwright", "install"],
            {"cwd": str(REPO_ROOT), "check": False, "capture_output": True, "text": True},
        )
    ]



def test_ensure_playwright_browser_ready_raises_when_install_fails() -> None:
    def probe() -> None:
        raise RuntimeError("missing browser")

    def run_command(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed_process(cmd, returncode=1, stderr="network error")

    with pytest.raises(RuntimeError, match="Playwright browser bootstrap failed"):
        runtime_module.ensure_playwright_browser_ready(
            python_executable="/tmp/python",
            probe_browser=probe,
            run_command=run_command,
            logger=lambda _unused: None,
        )



def test_ensure_playwright_browser_ready_raises_when_browser_is_still_unavailable() -> None:
    probe_calls: list[str] = []

    def probe() -> None:
        probe_calls.append("probe")
        raise RuntimeError("missing browser")

    def run_command(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return _completed_process(cmd, stdout="installed")

    with pytest.raises(RuntimeError, match="Playwright browser remained unavailable after install"):
        runtime_module.ensure_playwright_browser_ready(
            python_executable="/tmp/python",
            probe_browser=probe,
            run_command=run_command,
            logger=lambda _unused: None,
        )

    assert probe_calls == ["probe", "probe"]



def test_ui_full_e2e_main_requires_playwright_browser_ready_before_runtime_boot() -> None:
    class _Sentinel(RuntimeError):
        pass

    original_argv = sys.argv[:]
    sys.argv = ["ui_full_e2e_gemini_audit.py"]
    try:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(audit_module, "_prime_llm_keys", lambda: None)
            monkeypatch.setattr(audit_module, "_parse_args", _build_args)
            monkeypatch.setattr(audit_module, "_resolve_git_sha", lambda: "")

            def validate_args(args: argparse.Namespace) -> int:
                assert args.provider == "gemini"
                return 0

            def resolve_server_mode(args: argparse.Namespace) -> tuple[bool, str, str, int, int, int]:
                assert args.provider == "gemini"
                return False, "", "", 19600, 19700, 0

            monkeypatch.setattr(audit_module, "_validate_args", validate_args)
            monkeypatch.setattr(audit_module, "_resolve_server_mode", resolve_server_mode)

            def fail_fast(**kwargs: object) -> None:
                raise _Sentinel(str(kwargs.get("python_executable") or "missing"))

            monkeypatch.setattr(audit_module, "ensure_playwright_browser_ready", fail_fast)
            with pytest.raises(_Sentinel, match=r"python"):
                audit_module.main()
    finally:
        sys.argv = original_argv



def test_ui_full_e2e_main_isolates_dashboard_next_dist_dir_per_port() -> None:
    spawn_calls: list[dict[str, object]] = []

    def spawn_process(cmd: list[str], log_path: Path, env: dict[str, str]) -> str:
        spawn_calls.append({"cmd": cmd, "log_path": log_path, "env": dict(env)})
        return f"proc-{len(spawn_calls)}"

    original_argv = sys.argv[:]
    sys.argv = ["ui_full_e2e_gemini_audit.py"]
    try:
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setenv("GEMINI_API_KEY", "test-key")
            monkeypatch.setattr(audit_module, "_prime_llm_keys", lambda: None)
            monkeypatch.setattr(audit_module, "_parse_args", _build_runtime_args)
            monkeypatch.setattr(audit_module, "_resolve_git_sha", lambda: "sha")
            monkeypatch.setattr(audit_module, "ensure_playwright_browser_ready", lambda **_kwargs: None)
            monkeypatch.setattr(audit_module, "_validate_args", lambda _args: 0)
            monkeypatch.setattr(
                audit_module,
                "_resolve_server_mode",
                lambda _args: (False, "", "", 19660, 19760, 0),
            )
            monkeypatch.setattr(audit_module, "spawn_process", spawn_process)
            monkeypatch.setattr(audit_module, "wait_http_ok", lambda *_args, **_kwargs: None)
            monkeypatch.setattr(
                audit_module,
                "_seed_ids",
                lambda *_args, **_kwargs: {"pm_session_id": "pm-1", "run_id": "run-1", "workflow_id": "wf-1"},
            )
            monkeypatch.setattr(audit_module, "discover_page_routes", lambda: [])
            monkeypatch.setattr(
                audit_module,
                "execute_playwright_audit",
                lambda **_kwargs: (0, 0, 0, 0),
            )
            monkeypatch.setattr(audit_module, "GeminiAnalyzer", lambda **_kwargs: object())
            monkeypatch.setattr(audit_module, "build_click_inventory_report", lambda *_args, **_kwargs: {"summary": {}})
            monkeypatch.setattr(audit_module, "build_markdown_report", lambda _payload: "report")
            kill_calls: list[object] = []
            monkeypatch.setattr(audit_module, "kill_process", lambda proc: kill_calls.append(proc))

            code = audit_module.main()

    finally:
        sys.argv = original_argv

    assert code == 0
    assert len(spawn_calls) == 2
    dashboard_env = spawn_calls[1]["env"]
    assert dashboard_env["PORT"] == "19760"
    assert dashboard_env["NEXT_DIST_DIR"] == ".next-e2e-19760"



def test_launch_chromium_prefers_explicit_chrome_path() -> None:
    launch_calls: list[dict[str, object]] = []

    class _Chromium:
        executable_path = "/runtime/chromium"

        def launch(self, **kwargs: object) -> str:
            launch_calls.append(kwargs)
            return "browser"

    class _Playwright:
        chromium = _Chromium()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CHROME_PATH", "/preferred/chrome")
        monkeypatch.setattr(runtime_module, "_is_executable_file", lambda path: str(path) in {"/preferred/chrome", "/runtime/chromium"})
        browser = runtime_module._launch_chromium(_Playwright(), headless=True)

    assert browser == "browser"
    assert launch_calls == [{"headless": True, "executable_path": "/preferred/chrome"}]



def test_launch_chromium_falls_back_to_runtime_executable_path() -> None:
    launch_calls: list[dict[str, object]] = []

    class _Chromium:
        executable_path = "/runtime/chromium"

        def launch(self, **kwargs: object) -> str:
            launch_calls.append(kwargs)
            return "browser"

    class _Playwright:
        chromium = _Chromium()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.delenv("CHROME_PATH", raising=False)
        monkeypatch.setattr(runtime_module, "_resolve_preferred_chrome_path", lambda: "")
        monkeypatch.setattr(runtime_module, "_is_executable_file", lambda path: str(path) == "/runtime/chromium")
        browser = runtime_module._launch_chromium(_Playwright(), headless=False)

    assert browser == "browser"
    assert launch_calls == [{"headless": False, "executable_path": "/runtime/chromium"}]
