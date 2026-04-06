from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read(rel: str) -> str:
    return (_repo_root() / rel).read_text(encoding="utf-8")


def test_ui_audit_logs_use_dedicated_runtime_subdir() -> None:
    text = _read("scripts/ui_audit_gate.sh")
    assert 'LOG_DIR="$ROOT_DIR/.runtime-cache/logs/runtime/ui_audit"' in text


def test_ui_audit_container_staging_prefers_runner_temp() -> None:
    text = _read("scripts/ui_audit_gate.sh")
    assert 'if [[ "${CORTEXPILOT_CI_CONTAINER:-0}" == "1" && -n "${RUNNER_TEMP:-}" ]]; then' in text
    assert 'workspace_parent="${RUNNER_TEMP}/ui-audit-dashboard-workspace"' in text
    assert 'frontend-api-client \\' in text
    assert 'frontend-api-contract \\' in text
    assert 'frontend-shared' in text
    assert 'ln -s "${ROOT_DIR}/packages" "${stage_root}/packages"' not in text
    assert 'desktop preview exited before ready; refreshing desktop deps before fallback' in text


def test_install_logs_use_dedicated_runtime_subdir() -> None:
    dash = _read("scripts/install_dashboard_deps.sh")
    desktop = _read("scripts/install_desktop_deps.sh")
    assert (
        'INSTALL_LOG="$ROOT_DIR/.runtime-cache/logs/runtime/deps_install/install_dashboard_deps.log"' in dash
        or 'INSTALL_LOG="${STATE_ROOT}/install_dashboard_deps.log"' in dash
    )
    assert 'INSTALL_LOG="$ROOT_DIR/.runtime-cache/logs/runtime/deps_install/install_desktop_deps.log"' in desktop


def test_ci_perf_log_uses_dedicated_runtime_subdir() -> None:
    text = _read("scripts/lib/ci_step9_helpers.sh")
    assert 'PERF_API_LOG=".runtime-cache/logs/runtime/ci_perf/ci_perf_api.log"' in text
