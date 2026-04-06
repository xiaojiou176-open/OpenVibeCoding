from __future__ import annotations

import os
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]

from scripts import ui_full_e2e_gemini_audit_gemini as gemini_module
from scripts import ui_full_e2e_gemini_audit_runtime as audit_runtime_module
from scripts import ui_full_e2e_gemini_parallel_strict as parallel_strict_module
from scripts import ui_full_e2e_gemini_strict_gate as strict_gate_module


def _http_error(code: int, msg: str, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.test",
        code=code,
        msg=msg,
        hdrs=headers or {},
        fp=None,
    )


def test_is_retryable_gemini_error_handles_503_service_unavailable() -> None:
    assert gemini_module._is_retryable_gemini_error(_http_error(503, "Service Unavailable")) is True
    assert gemini_module._is_retryable_gemini_error(_http_error(400, "Bad Request")) is False


def test_generate_with_retry_retries_http_503_then_succeeds(monkeypatch) -> None:
    analyzer = gemini_module.GeminiAnalyzer(
        api_key="fake-key",
        model="gemini-3.1-pro-preview",
        request_timeout_sec=1,
        max_attempts=3,
    )
    calls = {"count": 0}

    def _fake_generate_once(*, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise _http_error(503, "Service Unavailable")
        return '{"ok": true}'

    monkeypatch.setattr(analyzer, "_generate_once_with_timeout", _fake_generate_once)
    monkeypatch.setattr(gemini_module.time, "sleep", lambda _: None)

    output = analyzer._generate_with_retry(prompt="p", images=[], model="gemini-3.1-pro-preview")
    assert output == '{"ok": true}'
    assert calls["count"] == 2


def test_generate_with_retry_does_not_retry_http_400(monkeypatch) -> None:
    analyzer = gemini_module.GeminiAnalyzer(
        api_key="fake-key",
        model="gemini-3.1-pro-preview",
        request_timeout_sec=1,
        max_attempts=3,
    )
    calls = {"count": 0}

    def _fake_generate_once(*, prompt: str, images: list[tuple[bytes, str]], model: str) -> str:
        calls["count"] += 1
        raise _http_error(400, "Bad Request")

    monkeypatch.setattr(analyzer, "_generate_once_with_timeout", _fake_generate_once)
    monkeypatch.setattr(gemini_module.time, "sleep", lambda _: None)

    with pytest.raises(urllib.error.HTTPError):
        analyzer._generate_with_retry(prompt="p", images=[], model="gemini-3.1-pro-preview")
    assert calls["count"] == 1


def test_parallel_strict_main_primes_llm_keys_before_env_validation(monkeypatch, capsys) -> None:
    original_argv = sys.argv[:]
    sys.argv = ["ui_full_e2e_gemini_parallel_strict.py"]
    try:
        main_globals = parallel_strict_module.main.__globals__
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        observed = {"build_called": False}

        def fake_prime_llm_keys() -> None:
            monkeypatch.setenv("GEMINI_API_KEY", "dummy-from-prime")

        def stop_after_preflight(**_kwargs: object) -> dict[str, object]:
            observed["build_called"] = True
            raise RuntimeError("after-prime")

        monkeypatch.setitem(main_globals, "_prime_llm_keys", fake_prime_llm_keys)
        monkeypatch.setitem(main_globals, "_build_route_sampling_plan", stop_after_preflight)

        result = parallel_strict_module.main()
        captured = capsys.readouterr()
    finally:
        sys.argv = original_argv

    assert result == 2
    assert observed["build_called"] is True
    assert os.environ.get("GEMINI_API_KEY") == "dummy-from-prime"
    assert "missing Gemini API key env" not in captured.err
    assert "failed to build route sampling plan: after-prime" in captured.err


def test_analyze_page_marks_extreme_tall_screenshot_http_400(monkeypatch, tmp_path: Path) -> None:
    analyzer = gemini_module.GeminiAnalyzer(
        api_key="fake-key",
        model="gemini-3.1-pro-preview",
        request_timeout_sec=1,
        max_attempts=2,
    )
    screenshot_path = tmp_path / "page.png"
    screenshot_path.write_bytes(b"not-a-real-image")

    monkeypatch.setattr(gemini_module, "read_image_bytes", lambda _path: (b"fake", "image/png"))
    monkeypatch.setattr(
        analyzer,
        "_generate_for_model_candidates",
        lambda **_kwargs: (_ for _ in ()).throw(_http_error(400, "Bad Request")),
    )
    monkeypatch.setattr(
        gemini_module,
        "_diagnose_extreme_tall_images",
        lambda _paths: {
            "diagnosis": "extreme_tall_screenshot",
            "kind": "page_structure_issue",
            "findings": [
                {
                    "path": str(screenshot_path),
                    "width": 256,
                    "height": 12000,
                    "aspect_ratio_h_over_w": 46.875,
                }
            ],
        },
    )

    with pytest.raises(RuntimeError, match="gemini_http_400_extreme_tall_screenshot"):
        analyzer.analyze_page(route="/pm", screenshot_path=screenshot_path)


def test_analyze_page_plain_http_400_without_extreme_tall_diagnosis(monkeypatch, tmp_path: Path) -> None:
    analyzer = gemini_module.GeminiAnalyzer(
        api_key="fake-key",
        model="gemini-3.1-pro-preview",
        request_timeout_sec=1,
        max_attempts=2,
    )
    screenshot_path = tmp_path / "page.png"
    screenshot_path.write_bytes(b"not-a-real-image")

    monkeypatch.setattr(gemini_module, "read_image_bytes", lambda _path: (b"fake", "image/png"))
    monkeypatch.setattr(
        analyzer,
        "_generate_for_model_candidates",
        lambda **_kwargs: (_ for _ in ()).throw(_http_error(400, "Bad Request")),
    )
    monkeypatch.setattr(gemini_module, "_diagnose_extreme_tall_images", lambda _paths: None)

    with pytest.raises(RuntimeError, match="gemini_http_400_bad_request"):
        analyzer.analyze_page(route="/pm", screenshot_path=screenshot_path)


def test_normalize_interaction_analysis_never_downgrades_fail_to_pass() -> None:
    payload = {
        "verdict": "fail",
        "issues": [
            {
                "severity": "major",
                "title": "403 forbidden",
                "detail": "god-mode/pending optional access denied",
            }
        ],
    }
    normalized = gemini_module.normalize_interaction_analysis(payload)
    assert normalized["verdict"] == "fail"


def test_normalize_page_analysis_warn_without_explicit_non_blocking_stays_warn() -> None:
    payload = {
        "verdict": "warn",
        "issues": [
            {
                "severity": "minor",
                "title": "状态提示信息偏长",
                "detail": "当前提示长度较长但不影响主流程操作",
            }
        ],
    }
    normalized = gemini_module.normalize_page_analysis(payload)
    assert normalized["verdict"] == "warn"
    assert "normalization_note" not in normalized


def test_normalize_page_analysis_warn_with_explicit_non_blocking_can_downgrade() -> None:
    payload = {
        "verdict": "warn",
        "issues": [
            {
                "severity": "major",
                "title": "403 forbidden",
                "detail": "god-mode/pending optional path unauthorized",
            }
        ],
    }
    normalized = gemini_module.normalize_page_analysis(payload)
    assert normalized["verdict"] == "pass"
    assert normalized["issues"][0]["severity"] == "minor"


def test_parallel_collect_stats_blocks_on_click_inventory_inconsistency(tmp_path: Path) -> None:
    click_inventory_report = tmp_path / "click_inventory_report.json"
    click_inventory_report.write_text(
        '{"summary":{"total_entries":1,"blocking_failures":0,"missing_target_ref_count":0,"overall_passed":true}}',
        encoding="utf-8",
    )
    report_payload = {
        "routes": [
            {
                "route": "/pm",
                "errors": [],
                "page_analysis": {"verdict": "pass"},
                "interactions": [
                    {
                        "index": 1,
                        "click_ok": True,
                        "target": {"selector": "[data-testid=send]"},
                        "analysis": {"verdict": "pass"},
                    }
                ],
            }
        ],
        "summary": {
            "total_routes": 1,
            "total_interactions": 1,
            "interaction_click_failures": 0,
            "gemini_warn_or_fail": 0,
            "click_inventory_entries": 2,
            "click_inventory_blocking_failures": 0,
            "click_inventory_missing_target_refs": 0,
            "click_inventory_overall_passed": True,
        },
        "artifacts": {"click_inventory_report": str(click_inventory_report)},
    }
    stats = parallel_strict_module._collect_stats(report_payload, report_path=tmp_path / "report.json")
    assert stats["click_inventory_consistency_error_count"] > 0
    assert parallel_strict_module._shard_strict_ok(stats, require_gemini_clean=False) is False


def test_parallel_collect_stats_accepts_click_inventory_consistent_payload(tmp_path: Path) -> None:
    click_inventory_report = tmp_path / "click_inventory_report.json"
    click_inventory_report.write_text(
        '{"summary":{"total_entries":1,"blocking_failures":0,"missing_target_ref_count":0,"overall_passed":true}}',
        encoding="utf-8",
    )
    report_payload = {
        "routes": [
            {
                "route": "/pm",
                "errors": [],
                "page_analysis": {"verdict": "pass"},
                "interactions": [
                    {
                        "index": 1,
                        "click_ok": True,
                        "target": {"selector": "[data-testid=send]"},
                        "analysis": {"verdict": "pass"},
                    }
                ],
            }
        ],
        "summary": {
            "total_routes": 1,
            "total_interactions": 1,
            "interaction_click_failures": 0,
            "gemini_warn_or_fail": 0,
            "click_inventory_entries": 1,
            "click_inventory_blocking_failures": 0,
            "click_inventory_missing_target_refs": 0,
            "click_inventory_overall_passed": True,
        },
        "artifacts": {"click_inventory_report": str(click_inventory_report)},
    }
    stats = parallel_strict_module._collect_stats(report_payload, report_path=tmp_path / "report.json")
    assert stats["click_inventory_consistency_error_count"] == 0
    assert parallel_strict_module._shard_strict_ok(stats, require_gemini_clean=False) is True


def test_parallel_collect_stats_blocks_on_missing_target_ref_without_route_idx_fallback(tmp_path: Path) -> None:
    click_inventory_report = tmp_path / "click_inventory_report.json"
    click_inventory_report.write_text(
        '{"summary":{"total_entries":1,"blocking_failures":0,"missing_target_ref_count":1,"overall_passed":false}}',
        encoding="utf-8",
    )
    report_payload = {
        "routes": [
            {
                "route": "/pm",
                "errors": [],
                "page_analysis": {"verdict": "pass"},
                "interactions": [
                    {
                        "index": 1,
                        "click_ok": True,
                        "target": {"tag": "button"},
                        "analysis": {"verdict": "pass"},
                    }
                ],
            }
        ],
        "summary": {
            "total_routes": 1,
            "total_interactions": 1,
            "interaction_click_failures": 0,
            "gemini_warn_or_fail": 0,
            "click_inventory_entries": 1,
            "click_inventory_blocking_failures": 0,
            "click_inventory_missing_target_refs": 1,
            "click_inventory_overall_passed": False,
        },
        "artifacts": {"click_inventory_report": str(click_inventory_report)},
    }
    stats = parallel_strict_module._collect_stats(report_payload, report_path=tmp_path / "report.json")
    assert stats["derived_click_inventory_missing_target_refs"] == 1
    assert stats["reported_click_inventory_missing_target_refs"] == 1
    assert parallel_strict_module._shard_strict_ok(stats, require_gemini_clean=False) is False


def test_route_error_recovered_detection_prefers_structured_fields() -> None:
    recovered_error = {"message": "retrying once", "recovered": True}
    non_recovered_error = {"message": "retrying once", "recovered": False}
    keyword_only_message = "retrying once due transient timeout"
    still_not_recovered_message = "retry attempted but still not recovered"
    explicit_retry_false_message = "retry succeeded=false after fallback"
    explicit_recovered_false_message = "recovered: false after second retry"
    structured_recovered_overrides_text = {"status": "retry_recovered", "message": "still not recovered"}
    structured_failed_overrides_text = {"status": "retry_failed", "message": "retry recovered"}

    assert parallel_strict_module._is_recovered_route_error(recovered_error) is True
    assert strict_gate_module._is_recovered_route_error(recovered_error) is True

    assert parallel_strict_module._is_recovered_route_error(non_recovered_error) is False
    assert strict_gate_module._is_recovered_route_error(non_recovered_error) is False

    assert parallel_strict_module._is_recovered_route_error(keyword_only_message) is False
    assert strict_gate_module._is_recovered_route_error(keyword_only_message) is False

    assert parallel_strict_module._is_recovered_route_error(still_not_recovered_message) is False
    assert strict_gate_module._is_recovered_route_error(still_not_recovered_message) is False

    assert parallel_strict_module._is_recovered_route_error(explicit_retry_false_message) is False
    assert strict_gate_module._is_recovered_route_error(explicit_retry_false_message) is False

    assert parallel_strict_module._is_recovered_route_error(explicit_recovered_false_message) is False
    assert strict_gate_module._is_recovered_route_error(explicit_recovered_false_message) is False

    assert parallel_strict_module._is_recovered_route_error(structured_recovered_overrides_text) is True
    assert strict_gate_module._is_recovered_route_error(structured_recovered_overrides_text) is True

    assert parallel_strict_module._is_recovered_route_error(structured_failed_overrides_text) is False
    assert strict_gate_module._is_recovered_route_error(structured_failed_overrides_text) is False


class _FakePage:
    def __init__(self) -> None:
        self.default_timeout: int | None = None
        self.closed = False

    def set_default_timeout(self, timeout_ms: int) -> None:
        self.default_timeout = timeout_ms

    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.pages: list[_FakePage] = []

    def new_page(self) -> _FakePage:
        if self.closed:
            raise RuntimeError("context already closed")
        page = _FakePage()
        self.pages.append(page)
        return page

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.contexts: list[_FakeContext] = []

    def is_connected(self) -> bool:
        return not self.closed

    def new_context(self, **_kwargs: object) -> _FakeContext:
        if self.closed:
            raise RuntimeError("browser already closed")
        context = _FakeContext()
        self.contexts.append(context)
        return context

    def close(self) -> None:
        self.closed = True


def test_ensure_route_runtime_prefers_explicit_chrome_path(monkeypatch, tmp_path: Path) -> None:
    chrome_path = tmp_path / "chrome-for-testing"
    chrome_path.write_text("binary", encoding="utf-8")
    chrome_path.chmod(0o755)
    launch_calls: list[dict[str, object]] = []

    def _fake_launch(**kwargs: object) -> _FakeBrowser:
        launch_calls.append(kwargs)
        return _FakeBrowser()

    playwright_runtime = SimpleNamespace(chromium=SimpleNamespace(launch=_fake_launch))
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(audit_runtime_module, "_resolve_preferred_chrome_path", lambda: str(chrome_path))

    browser, context, page, rebuilt = audit_runtime_module.ensure_route_runtime(
        playwright_runtime=playwright_runtime,
        browser=None,
        context=None,
        page=None,
        navigation_timeout_ms=4321,
        headless=True,
    )

    assert rebuilt is True
    assert launch_calls == [{"headless": True, "executable_path": str(chrome_path)}]
    assert isinstance(browser, _FakeBrowser)
    assert isinstance(context, _FakeContext)
    assert isinstance(page, _FakePage)
    assert page.default_timeout == 4321


def test_rebuild_route_runtime_prefers_explicit_chrome_path(monkeypatch, tmp_path: Path) -> None:
    chrome_path = tmp_path / "chrome-for-testing"
    chrome_path.write_text("binary", encoding="utf-8")
    chrome_path.chmod(0o755)
    launch_calls: list[dict[str, object]] = []

    def _fake_launch(**kwargs: object) -> _FakeBrowser:
        launch_calls.append(kwargs)
        return _FakeBrowser()

    stale_browser = _FakeBrowser()
    stale_context = stale_browser.new_context()
    stale_page = stale_context.new_page()
    playwright_runtime = SimpleNamespace(chromium=SimpleNamespace(launch=_fake_launch))
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(audit_runtime_module, "_resolve_preferred_chrome_path", lambda: str(chrome_path))

    browser, context, page = audit_runtime_module.rebuild_route_runtime(
        playwright_runtime=playwright_runtime,
        browser=stale_browser,
        context=stale_context,
        page=stale_page,
        navigation_timeout_ms=9876,
        headless=True,
    )

    assert launch_calls == [{"headless": True, "executable_path": str(chrome_path)}]
    assert stale_browser.closed is True
    assert stale_context.closed is True
    assert stale_page.closed is True
    assert isinstance(browser, _FakeBrowser)
    assert isinstance(context, _FakeContext)
    assert isinstance(page, _FakePage)
    assert page.default_timeout == 9876
