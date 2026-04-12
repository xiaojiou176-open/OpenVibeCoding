from __future__ import annotations

from pathlib import Path


def _read_script() -> str:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "repo_coverage_gate.py"
    return script_path.read_text(encoding="utf-8")


def test_dashboard_coverage_installs_deps_before_vitest() -> None:
    text = _read_script()
    install_idx = text.index('run_command(["bash", "scripts/install_dashboard_deps.sh"])')
    vitest_idx = text.index('"pnpm",\n        "--dir",\n        "apps/dashboard",\n        "exec",\n        "vitest"')
    assert install_idx < vitest_idx


def test_desktop_coverage_installs_deps_before_vitest() -> None:
    text = _read_script()
    install_idx = text.index('run_command(["bash", "scripts/install_desktop_deps.sh"])')
    vitest_idx = text.index('"pnpm",\n        "--dir",\n        "apps/desktop",\n        "exec",\n        "vitest"')
    assert install_idx < vitest_idx


def test_orchestrator_coverage_uses_managed_coverage_file() -> None:
    text = _read_script()
    assert 'DEFAULT_COVERAGE_DATA_DIR = ROOT_DIR / ".runtime-cache" / "cache" / "test" / "coverage" / "repo_coverage_gate"' in text
    assert '"COVERAGE_FILE": str(coverage_file)' in text


def test_dashboard_and_desktop_coverage_use_managed_report_dirs() -> None:
    text = _read_script()
    assert '"CORTEXPILOT_DASHBOARD_COVERAGE_DIR": str(report_path.parent)' in text
    assert '"CORTEXPILOT_DESKTOP_COVERAGE_DIR": str(report_path.parent)' in text


def test_orchestrator_coverage_uses_managed_hypothesis_storage() -> None:
    text = _read_script()
    assert 'DEFAULT_HYPOTHESIS_DATA_DIR = ROOT_DIR / ".runtime-cache" / "cache" / "hypothesis" / "repo_coverage_gate"' in text
    assert '"HYPOTHESIS_STORAGE_DIRECTORY": str(DEFAULT_HYPOTHESIS_DATA_DIR)' in text
