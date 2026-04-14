#!/usr/bin/env python3
"""Repo-level coverage aggregation and optional fail-closed gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "repo_coverage_report.json"
DEFAULT_ORCH_REPORT = (
    ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "orchestrator" / "orchestrator_coverage.json"
)
DEFAULT_DASH_REPORT = (
    ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "dashboard" / "coverage-summary.json"
)
DEFAULT_DESKTOP_REPORT = (
    ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "desktop" / "coverage-summary.json"
)
DEFAULT_COVERAGE_DATA_DIR = ROOT_DIR / ".runtime-cache" / "cache" / "test" / "coverage" / "repo_coverage_gate"
DEFAULT_HYPOTHESIS_DATA_DIR = ROOT_DIR / ".runtime-cache" / "cache" / "hypothesis" / "repo_coverage_gate"
DEFAULT_THRESHOLD = float(os.environ.get("OPENVIBECODING_REPO_COVERAGE_GATE_THRESHOLD", "95"))


def _round2(value: float) -> float:
    return round(float(value), 2)


def _pct(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _round2((float(covered) / float(total)) * 100.0)


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        return int(float(stripped))
    raise TypeError(f"unsupported numeric type: {type(value)}")


@dataclass
class CoverageTotals:
    lines_total: int
    lines_covered: int
    statements_total: int
    statements_covered: int
    branches_total: int
    branches_covered: int
    functions_total: int = 0
    functions_covered: int = 0

    @property
    def percent_covered(self) -> float:
        return _pct(self.lines_covered, self.lines_total)

    @property
    def percent_statements_covered(self) -> float:
        return _pct(self.statements_covered, self.statements_total)

    @property
    def percent_branches_covered(self) -> float:
        return _pct(self.branches_covered, self.branches_total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines_total": self.lines_total,
            "lines_covered": self.lines_covered,
            "statements_total": self.statements_total,
            "statements_covered": self.statements_covered,
            "branches_total": self.branches_total,
            "branches_covered": self.branches_covered,
            "functions_total": self.functions_total,
            "functions_covered": self.functions_covered,
            "percent_covered": self.percent_covered,
            "percent_statements_covered": self.percent_statements_covered,
            "percent_branches_covered": self.percent_branches_covered,
        }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"coverage report not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def parse_pytest_cov_report(path: Path) -> CoverageTotals:
    payload = _load_json(path)
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        raise ValueError(f"pytest-cov report missing totals map: {path}")

    statements_total = _to_int(totals.get("num_statements"), 0)
    statements_covered = _to_int(
        totals.get("covered_lines"),
        statements_total - _to_int(totals.get("missing_lines"), 0),
    )

    lines_total = _to_int(totals.get("num_lines"), statements_total)
    lines_covered = _to_int(totals.get("covered_lines"), statements_covered)

    branches_total = _to_int(totals.get("num_branches"), 0)
    branches_covered = _to_int(
        totals.get("covered_branches"),
        branches_total - _to_int(totals.get("missing_branches"), 0),
    )

    if lines_total <= 0 or statements_total <= 0:
        raise ValueError(f"pytest-cov report has empty totals: {path}")

    return CoverageTotals(
        lines_total=lines_total,
        lines_covered=lines_covered,
        statements_total=statements_total,
        statements_covered=statements_covered,
        branches_total=branches_total,
        branches_covered=branches_covered,
    )


def parse_vitest_summary_report(path: Path) -> CoverageTotals:
    payload = _load_json(path)
    total = payload.get("total")
    if not isinstance(total, dict):
        raise ValueError(f"vitest coverage summary missing total map: {path}")

    def metric_counts(metric_name: str) -> tuple[int, int]:
        metric = total.get(metric_name)
        if not isinstance(metric, dict):
            return (0, 0)
        return (_to_int(metric.get("total"), 0), _to_int(metric.get("covered"), 0))

    statements_total, statements_covered = metric_counts("statements")
    lines_total, lines_covered = metric_counts("lines")
    branches_total, branches_covered = metric_counts("branches")
    functions_total, functions_covered = metric_counts("functions")

    if statements_total <= 0 or lines_total <= 0:
        raise ValueError(f"vitest coverage summary has empty totals: {path}")

    return CoverageTotals(
        lines_total=lines_total,
        lines_covered=lines_covered,
        statements_total=statements_total,
        statements_covered=statements_covered,
        branches_total=branches_total,
        branches_covered=branches_covered,
        functions_total=functions_total,
        functions_covered=functions_covered,
    )


def run_command(command: list[str], env_overrides: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    print(f"▶ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT_DIR, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed (exit={result.returncode}): {' '.join(command)}")


def _prepare_coverage_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    for stale_path in path.parent.glob(f"{path.name}.*"):
        stale_path.unlink(missing_ok=True)


def run_orchestrator_coverage(report_path: Path, pytest_target: str, pytest_mark: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_file = DEFAULT_COVERAGE_DATA_DIR / ".coverage"
    _prepare_coverage_file(coverage_file)
    override = os.getenv("OPENVIBECODING_PYTHON", "").strip()
    toolchain_python = ROOT_DIR / ".runtime-cache" / "cache" / "toolchains" / "python" / "current" / "bin" / "python"
    python_bin = Path(override) if override else toolchain_python
    if not python_bin.exists():
        repo_python = ROOT_DIR / ".venv" / "bin" / "python"
        python_bin = repo_python if repo_python.exists() else Path(sys.executable)
    python_exe = str(python_bin)
    command = [
        python_exe,
        "-m",
        "pytest",
        pytest_target,
        "-m",
        pytest_mark,
        "-n",
        "0",
        "--cov=openvibecoding_orch",
        "--cov-branch",
        f"--cov-report=json:{report_path}",
        "--cov-fail-under=0",
    ]
    try:
        run_command(
            command,
            env_overrides={
                "PYTHONPATH": "apps/orchestrator/src",
                "COVERAGE_FILE": str(coverage_file),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(DEFAULT_HYPOTHESIS_DATA_DIR),
            },
        )
    finally:
        _prepare_coverage_file(coverage_file)


def run_dashboard_coverage(report_path: Path, test_targets: list[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(["bash", "scripts/install_dashboard_deps.sh"])
    command = [
        "pnpm",
        "--dir",
        "apps/dashboard",
        "exec",
        "vitest",
        "run",
        "--config",
        "vitest.config.mts",
        "--coverage",
        "--coverage.thresholds.lines=0",
        "--coverage.thresholds.statements=0",
        "--coverage.thresholds.functions=0",
        "--coverage.thresholds.branches=0",
        "--coverage.reporter=json-summary",
        "--coverage.reporter=text",
        f"--coverage.reportsDirectory={report_path.parent}",
    ]
    command.extend(test_targets)
    run_command(
        command,
        env_overrides={
            "CI": "1",
            "OPENVIBECODING_COVERAGE_HTML": "0",
            "OPENVIBECODING_DASHBOARD_COVERAGE_DIR": str(report_path.parent),
        },
    )


def run_desktop_coverage(report_path: Path, test_targets: list[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_command(["bash", "scripts/install_desktop_deps.sh"])
    command = [
        "pnpm",
        "--dir",
        "apps/desktop",
        "exec",
        "vitest",
        "run",
        "--coverage",
        "--coverage.thresholds.lines=0",
        "--coverage.thresholds.statements=0",
        "--coverage.thresholds.functions=0",
        "--coverage.thresholds.branches=0",
        "--coverage.reporter=json-summary",
        "--coverage.reporter=text",
        f"--coverage.reportsDirectory={report_path.parent}",
    ]
    command.extend(test_targets)
    run_command(
        command,
        env_overrides={
            "CI": "1",
            "OPENVIBECODING_COVERAGE_HTML": "0",
            "OPENVIBECODING_DESKTOP_COVERAGE_DIR": str(report_path.parent),
            "OPENVIBECODING_DESKTOP_COVERAGE_RUN_ID": "repo-coverage-gate",
        },
    )


def aggregate_repo_totals(project_totals: dict[str, CoverageTotals]) -> CoverageTotals:
    return CoverageTotals(
        lines_total=sum(item.lines_total for item in project_totals.values()),
        lines_covered=sum(item.lines_covered for item in project_totals.values()),
        statements_total=sum(item.statements_total for item in project_totals.values()),
        statements_covered=sum(item.statements_covered for item in project_totals.values()),
        branches_total=sum(item.branches_total for item in project_totals.values()),
        branches_covered=sum(item.branches_covered for item in project_totals.values()),
        functions_total=sum(item.functions_total for item in project_totals.values()),
        functions_covered=sum(item.functions_covered for item in project_totals.values()),
    )


def build_report(
    *,
    threshold: float,
    enforce_gate: bool,
    output_path: Path,
    source_reports: dict[str, Path],
    project_totals: dict[str, CoverageTotals],
) -> tuple[dict[str, Any], bool, list[str]]:
    repo_totals = aggregate_repo_totals(project_totals)
    gate_failures: list[str] = []

    metrics = {
        "percent_covered": repo_totals.percent_covered,
        "percent_statements_covered": repo_totals.percent_statements_covered,
        "percent_branches_covered": repo_totals.percent_branches_covered,
    }
    for metric_name, value in metrics.items():
        if value < threshold:
            gate_failures.append(f"{metric_name}={value:.2f}% < {threshold:.2f}%")

    gate_passed = len(gate_failures) == 0
    report = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "threshold_percent": _round2(threshold),
        "gate_mode": "enforced" if enforce_gate else "report-only",
        "gate_passed": gate_passed,
        "repo_level": {
            "percent_covered": repo_totals.percent_covered,
            "percent_statements_covered": repo_totals.percent_statements_covered,
            "percent_branches_covered": repo_totals.percent_branches_covered,
            "totals": repo_totals.to_dict(),
        },
        "projects": {
            project_name: {
                "source_report": str(source_reports[project_name]),
                "totals": totals.to_dict(),
            }
            for project_name, totals in project_totals.items()
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return report, gate_passed, gate_failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate orchestrator/dashboard/desktop coverage into a single repo-level JSON report, "
            "and optionally enforce a fail-closed coverage gate."
        )
    )
    parser.add_argument("--skip-tests", action="store_true", help="Skip test execution and only parse existing reports.")
    parser.add_argument("--enforce-gate", action="store_true", help="Fail (non-zero exit) when repo-level metrics are below threshold.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Coverage threshold percent (default: 95).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON report path.")
    parser.add_argument("--orchestrator-report", type=Path, default=DEFAULT_ORCH_REPORT, help="Pytest-cov JSON report path.")
    parser.add_argument("--dashboard-report", type=Path, default=DEFAULT_DASH_REPORT, help="Dashboard vitest summary report path.")
    parser.add_argument("--desktop-report", type=Path, default=DEFAULT_DESKTOP_REPORT, help="Desktop vitest summary report path.")
    parser.add_argument(
        "--orchestrator-pytest-target",
        default="apps/orchestrator/tests",
        help="Pytest target for orchestrator coverage run.",
    )
    parser.add_argument(
        "--orchestrator-pytest-mark",
        default="not e2e and not serial",
        help='Pytest mark expression for orchestrator coverage run (default: "not e2e and not serial").',
    )
    parser.add_argument(
        "--dashboard-test-target",
        action="append",
        default=[],
        help="Optional dashboard test target(s) appended to vitest command (repeatable).",
    )
    parser.add_argument(
        "--desktop-test-target",
        action="append",
        default=[],
        help="Optional desktop test target(s) appended to vitest command (repeatable).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_reports = {
        "orchestrator": args.orchestrator_report,
        "dashboard": args.dashboard_report,
        "desktop": args.desktop_report,
    }
    try:
        if not args.skip_tests:
            run_orchestrator_coverage(
                report_path=source_reports["orchestrator"],
                pytest_target=args.orchestrator_pytest_target,
                pytest_mark=args.orchestrator_pytest_mark,
            )
            run_dashboard_coverage(source_reports["dashboard"], args.dashboard_test_target)
            run_desktop_coverage(source_reports["desktop"], args.desktop_test_target)

        project_totals = {
            "orchestrator": parse_pytest_cov_report(source_reports["orchestrator"]),
            "dashboard": parse_vitest_summary_report(source_reports["dashboard"]),
            "desktop": parse_vitest_summary_report(source_reports["desktop"]),
        }
        report, gate_passed, gate_failures = build_report(
            threshold=args.threshold,
            enforce_gate=args.enforce_gate,
            output_path=args.output,
            source_reports=source_reports,
            project_totals=project_totals,
        )
        print(f"✅ repo coverage report generated: {args.output}")
        print(
            "ℹ repo metrics: "
            f"percent_covered={report['repo_level']['percent_covered']:.2f}% "
            f"percent_statements_covered={report['repo_level']['percent_statements_covered']:.2f}% "
            f"percent_branches_covered={report['repo_level']['percent_branches_covered']:.2f}%"
        )
        if args.enforce_gate and not gate_passed:
            print("❌ repo coverage gate failed:", file=sys.stderr)
            for failure in gate_failures:
                print(f"  - {failure}", file=sys.stderr)
            return 1
        if args.enforce_gate:
            print(f"✅ repo coverage gate passed (threshold={args.threshold:.2f}%)")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"❌ repo coverage aggregation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
