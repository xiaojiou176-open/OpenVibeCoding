from __future__ import annotations

from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


REPO_ROOT = Path(__file__).resolve().parents[3]

from scripts import ui_full_e2e_gemini_audit_runner as runner_module


class _FakePage:
    def __init__(self, *, fail_networkidle: bool = False) -> None:
        self.fail_networkidle = fail_networkidle
        self.load_state_calls: list[tuple[str, int]] = []
        self.function_calls: list[tuple[str, int]] = []

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_state_calls.append((state, timeout))
        if self.fail_networkidle and state == "networkidle":
            raise PlaywrightTimeoutError("network idle timeout")

    def wait_for_function(self, script: str, timeout: int) -> None:
        self.function_calls.append((script, timeout))


def test_wait_for_page_settle_prefers_networkidle() -> None:
    page = _FakePage()
    runner_module._wait_for_page_settle(page=page, settle_ms=800)
    assert [state for state, _ in page.load_state_calls] == ["domcontentloaded", "networkidle"]
    assert page.function_calls == []


def test_wait_for_page_settle_falls_back_to_ready_state_check() -> None:
    page = _FakePage(fail_networkidle=True)
    runner_module._wait_for_page_settle(page=page, settle_ms=800)
    assert [state for state, _ in page.load_state_calls][:2] == ["domcontentloaded", "networkidle"]
    assert len(page.function_calls) == 1
    assert "document.readyState" in page.function_calls[0][0]


def test_wait_for_post_action_settle_falls_back_when_networkidle_times_out() -> None:
    page = _FakePage(fail_networkidle=True)
    runner_module._wait_for_post_action_settle(page=page, settle_ms=500)
    assert [state for state, _ in page.load_state_calls] == ["networkidle"]
    assert len(page.function_calls) == 1
    assert "document.readyState" in page.function_calls[0][0]


def test_wait_helpers_skip_when_budget_is_non_positive() -> None:
    page = _FakePage()
    runner_module._wait_for_page_settle(page=page, settle_ms=0)
    runner_module._wait_for_post_action_settle(page=page, settle_ms=-1)
    assert page.load_state_calls == []
    assert page.function_calls == []


def test_target_scripts_no_longer_use_hard_wait_apis() -> None:
    target_files = [
        REPO_ROOT / "scripts/e2e_command_tower_controls_real.sh",
        REPO_ROOT / "scripts/ui_full_e2e_gemini_audit_runner.py",
    ]
    for file_path in target_files:
        content = file_path.read_text(encoding="utf-8")
        assert "wait_for_timeout(" not in content, file_path.as_posix()
        assert "time.sleep(" not in content, file_path.as_posix()
