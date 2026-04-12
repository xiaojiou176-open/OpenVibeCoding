from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _gate_script() -> Path:
    return _repo_root() / "scripts" / "check_bench_e2e_speed_gate.py"


def _write_summary(path: Path, *, overall_fail_rate: float, ui_p95: float, dash_p95: float) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": "bench_test",
                "overall": {"fail_rate": overall_fail_rate},
                "suites": {
                    "ui_full_gemini_strict": {"duration_sec": {"p95": ui_p95}},
                    "dashboard_high_risk_e2e": {"duration_sec": {"p95": dash_p95}},
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_bench_gate_passes_for_summary_within_thresholds(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    _write_summary(summary, overall_fail_rate=0.0, ui_p95=90.0, dash_p95=45.0)

    result = subprocess.run(
        [sys.executable, str(_gate_script()), "--summary", str(summary), "--ui-max-p95-sec", "120", "--dash-max-p95-sec", "60"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "benchmark gate passed" in result.stdout


def test_bench_gate_fails_when_overall_fail_rate_exceeds_threshold(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    _write_summary(summary, overall_fail_rate=0.2, ui_p95=90.0, dash_p95=45.0)

    result = subprocess.run(
        [sys.executable, str(_gate_script()), "--summary", str(summary), "--max-overall-fail-rate", "0.1"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "overall.fail_rate=0.2000 > max_overall_fail_rate=0.1000" in result.stderr


def test_bench_gate_fails_when_suite_p95_exceeds_threshold(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    _write_summary(summary, overall_fail_rate=0.0, ui_p95=181.0, dash_p95=91.0)

    result = subprocess.run(
        [
            sys.executable,
            str(_gate_script()),
            "--summary",
            str(summary),
            "--ui-max-p95-sec",
            "180",
            "--dash-max-p95-sec",
            "90",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "ui_full_gemini_strict.p95=181.000s > max_p95=180.000s" in result.stderr
    assert "dashboard_high_risk_e2e.p95=91.000s > max_p95=90.000s" in result.stderr


def test_bench_gate_fails_closed_when_summary_is_missing(tmp_path: Path) -> None:
    summary = tmp_path / "missing-summary.json"

    result = subprocess.run(
        [sys.executable, str(_gate_script()), "--summary", str(summary)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "benchmark summary not found" in result.stderr
