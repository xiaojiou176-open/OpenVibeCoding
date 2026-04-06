#!/usr/bin/env python3
"""Aggregate repo-level coverage from existing subproject coverage reports."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "repo_coverage_report.json"
DEFAULT_THRESHOLD = float(os.environ.get("CORTEXPILOT_REPO_COVERAGE_GATE_THRESHOLD", "95"))
MAX_RUN_ARTIFACT_AGE_SECONDS = int(os.environ.get("CORTEXPILOT_REPO_COVERAGE_MAX_RUN_ARTIFACT_AGE_SECONDS", "21600"))

SOURCE_SELECTION_LAYERS: dict[str, list[tuple[str, Any]]] = {
    "orchestrator": [
        ("glob", str(ROOT_DIR / ".runtime-cache" / "test_output" / "orchestrator_coverage_final_v*.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "orchestrator_coverage_final.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "orchestrator" / "orchestrator_coverage.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "orchestrator_coverage_recheck_v2.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "orchestrator_coverage_recheck.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "orchestrator_coverage.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "orchestrator_coverage_test_gate.json")),
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "ci" / "orchestrator_coverage_ci_gate.json")),
    ],
    "dashboard": [
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "dashboard" / "coverage-summary.json")),
        (
            "multi",
            [
                ("glob", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "run-*" / "coverage-summary.json")),
                ("path", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "coverage-summary.json")),
                ("glob", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "run-*" / "coverage-final.json")),
                ("path", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "coverage-final.json")),
                ("glob", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "run-*" / "index.html")),
                ("path", str(ROOT_DIR / "apps" / "dashboard" / "coverage" / "index.html")),
            ],
        ),
    ],
    "desktop": [
        ("path", str(ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / "desktop" / "coverage-summary.json")),
        (
            "multi",
            [
                ("glob", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "run-*" / "coverage-summary.json")),
                ("path", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "coverage-summary.json")),
                ("glob", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "run-*" / "coverage-final.json")),
                ("path", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "coverage-final.json")),
                ("glob", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "run-*" / "index.html")),
                ("path", str(ROOT_DIR / "apps" / "desktop" / "coverage" / "index.html")),
            ],
        ),
    ],
}


def _round2(value: float) -> float:
    return round(float(value), 2)


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


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        parsed = float(stripped)
        return parsed if math.isfinite(parsed) else default
    raise TypeError(f"unsupported numeric type: {type(value)}")


def _pct(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return _round2((float(covered) / float(total)) * 100.0)


def _derive_total_from_percent(covered: int, percent: float) -> int | None:
    if covered < 0:
        return None
    if percent <= 0.0 or percent > 100.0:
        return None
    return max(covered, int(round((float(covered) * 100.0) / percent)))


@dataclass(frozen=True)
class CoverageTotals:
    lines_total: int
    lines_covered: int
    statements_total: int
    statements_covered: int
    branches_total: int
    branches_covered: int
    functions_total: int = 0
    functions_covered: int = 0
    percent_covered_override: float | None = None

    @property
    def percent_covered(self) -> float:
        if self.percent_covered_override is not None:
            return _round2(self.percent_covered_override)
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
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"coverage report not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _iter_layer_candidates(layer: tuple[str, Any]) -> list[Path]:
    layer_type, layer_value = layer
    if layer_type == "path":
        return [Path(layer_value)]
    if layer_type == "glob":
        pattern_path = Path(layer_value)
        if pattern_path.is_absolute():
            try:
                relative_pattern = pattern_path.relative_to(ROOT_DIR)
            except ValueError:
                return []
            return sorted(
                ROOT_DIR.glob(relative_pattern.as_posix()),
                key=lambda path: (path.stat().st_mtime, str(path)),
                reverse=True,
            )
        return sorted(
            ROOT_DIR.glob(pattern_path.as_posix()),
            key=lambda path: (path.stat().st_mtime, str(path)),
            reverse=True,
        )
    if layer_type == "multi":
        candidates: list[Path] = []
        for nested_layer in layer_value:
            candidates.extend(_iter_layer_candidates(nested_layer))
        return candidates
    raise ValueError(f"unsupported source selection layer type: {layer_type}")


def _project_report_parser(project: str):
    if project == "orchestrator":
        return _parse_pytest_cov_report
    if project in {"dashboard", "desktop"}:
        return _parse_web_coverage_report
    raise ValueError(f"unsupported project for coverage parser: {project}")


def _canonical_repo_coverage_path(project: str) -> Path | None:
    if project in {"dashboard", "desktop"}:
        return ROOT_DIR / ".runtime-cache" / "test_output" / "repo_coverage" / project / "coverage-summary.json"
    return None


def _is_run_artifact(path: Path) -> bool:
    return "/coverage/run-" in path.as_posix()


def _reject_run_artifact_reason(project: str, path: Path) -> str | None:
    if not _is_run_artifact(path):
        return None

    run_dir = path.parent
    if (run_dir / ".tmp").exists():
        return "run directory still contains .tmp marker"

    canonical = _canonical_repo_coverage_path(project)
    if canonical is not None and canonical.exists():
        if path.stat().st_mtime < canonical.stat().st_mtime:
            return f"older than canonical repo_coverage artifact: {canonical}"

    age_seconds = datetime.now(tz=timezone.utc).timestamp() - path.stat().st_mtime
    if age_seconds > float(MAX_RUN_ARTIFACT_AGE_SECONDS):
        return (
            f"run artifact older than max age "
            f"({int(age_seconds)}s > {MAX_RUN_ARTIFACT_AGE_SECONDS}s)"
        )
    return None


def _resolve_source_report(project: str, explicit_path: Path | None) -> tuple[Path, CoverageTotals]:
    parser = _project_report_parser(project)
    rejection_reasons: list[str] = []

    if explicit_path is not None:
        if not explicit_path.exists():
            raise FileNotFoundError(f"{project} coverage report not found: {explicit_path}")
        totals = parser(explicit_path)
        return explicit_path, totals

    layers = SOURCE_SELECTION_LAYERS[project]
    for layer in layers:
        for candidate in _iter_layer_candidates(layer):
            if not candidate.exists():
                continue

            run_rejection = _reject_run_artifact_reason(project, candidate)
            if run_rejection is not None:
                rejection_reasons.append(f"{candidate} [{run_rejection}]")
                continue

            try:
                totals = parser(candidate)
            except Exception as exc:  # noqa: BLE001
                rejection_reasons.append(f"{candidate} [invalid: {exc}]")
                continue
            return candidate, totals

    searched_values: list[str] = []
    for layer_type, layer_value in layers:
        if layer_type == "multi":
            for nested_layer_type, nested_layer_value in layer_value:
                searched_values.append(f"{nested_layer_type}:{nested_layer_value}")
            continue
        searched_values.append(f"{layer_type}:{layer_value}")
    searched = ", ".join(searched_values)
    rejected = "; ".join(rejection_reasons)
    if rejected:
        raise FileNotFoundError(
            f"{project} coverage report not found; searched: {searched}; rejected candidates: {rejected}"
        )
    raise FileNotFoundError(f"{project} coverage report not found; searched: {searched}")


def _parse_pytest_cov_report(path: Path) -> CoverageTotals:
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
    percent_covered_override = _to_float(totals.get("percent_covered"), None)
    if percent_covered_override is not None:
        derived_lines_total = _derive_total_from_percent(lines_covered, percent_covered_override)
        if derived_lines_total is not None:
            lines_total = max(lines_total, derived_lines_total)
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
        percent_covered_override=percent_covered_override,
    )


def _parse_vitest_summary(path: Path) -> CoverageTotals:
    payload = _load_json(path)
    total = payload.get("total")
    if not isinstance(total, dict):
        raise ValueError(f"vitest summary missing total map: {path}")

    def metric_counts(metric_name: str) -> tuple[int, int]:
        metric = total.get(metric_name)
        if not isinstance(metric, dict):
            return (0, 0)
        return (_to_int(metric.get("total"), 0), _to_int(metric.get("covered"), 0))

    statements_total, statements_covered = metric_counts("statements")
    lines_total, lines_covered = metric_counts("lines")
    branches_total, branches_covered = metric_counts("branches")
    functions_total, functions_covered = metric_counts("functions")

    if lines_total <= 0 or statements_total <= 0:
        raise ValueError(f"vitest summary has empty totals: {path}")

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


def _parse_istanbul_final(path: Path) -> CoverageTotals:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"istanbul final report must be an object: {path}")

    statements_total = 0
    statements_covered = 0
    lines_total = 0
    lines_covered = 0
    branches_total = 0
    branches_covered = 0
    functions_total = 0
    functions_covered = 0

    for file_coverage in payload.values():
        if not isinstance(file_coverage, dict):
            continue
        statement_hits = file_coverage.get("s")
        if isinstance(statement_hits, dict):
            statement_values = [_to_int(value, 0) for value in statement_hits.values()]
            statements_total += len(statement_values)
            statements_covered += sum(1 for value in statement_values if value > 0)

        line_hits = file_coverage.get("l")
        if isinstance(line_hits, dict):
            line_values = [_to_int(value, 0) for value in line_hits.values()]
            lines_total += len(line_values)
            lines_covered += sum(1 for value in line_values if value > 0)

        function_hits = file_coverage.get("f")
        if isinstance(function_hits, dict):
            function_values = [_to_int(value, 0) for value in function_hits.values()]
            functions_total += len(function_values)
            functions_covered += sum(1 for value in function_values if value > 0)

        branch_hits = file_coverage.get("b")
        if isinstance(branch_hits, dict):
            for branch_arms in branch_hits.values():
                if isinstance(branch_arms, (list, tuple)):
                    arm_values = [_to_int(value, 0) for value in branch_arms]
                    branches_total += len(arm_values)
                    branches_covered += sum(1 for value in arm_values if value > 0)

    if lines_total <= 0:
        lines_total = statements_total
        lines_covered = statements_covered
    if lines_total <= 0 or statements_total <= 0:
        raise ValueError(f"istanbul final report has empty totals: {path}")

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


def _parse_istanbul_index_html(path: Path) -> CoverageTotals:
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"coverage report not found: {path}") from exc

    def fraction(metric: str) -> tuple[int, int]:
        pattern = (
            r"<span[^>]*class=[\"']quiet[\"'][^>]*>\s*"
            + re.escape(metric)
            + r"\s*</span>\s*"
            + r"<span[^>]*class=[\"']fraction[\"'][^>]*>\s*([0-9]+)\s*/\s*([0-9]+)\s*</span>"
        )
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match is None:
            raise ValueError(f"istanbul html index missing {metric} fraction: {path}")
        covered = _to_int(match.group(1), 0)
        total = _to_int(match.group(2), 0)
        return total, covered

    statements_total, statements_covered = fraction("Statements")
    branches_total, branches_covered = fraction("Branches")
    functions_total, functions_covered = fraction("Functions")
    lines_total, lines_covered = fraction("Lines")

    if lines_total <= 0 or statements_total <= 0:
        raise ValueError(f"istanbul html index has empty totals: {path}")

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


def _parse_web_coverage_report(path: Path) -> CoverageTotals:
    suffix = path.suffix.lower()
    if suffix == ".html":
        return _parse_istanbul_index_html(path)
    if suffix == ".json":
        payload = _load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"web coverage json payload must be an object: {path}")
        if isinstance(payload.get("total"), dict):
            return _parse_vitest_summary(path)
        return _parse_istanbul_final(path)
    raise ValueError(f"unsupported web coverage artifact format: {path}")


def _aggregate_repo_totals(subprojects: dict[str, CoverageTotals]) -> CoverageTotals:
    return CoverageTotals(
        lines_total=sum(item.lines_total for item in subprojects.values()),
        lines_covered=sum(item.lines_covered for item in subprojects.values()),
        statements_total=sum(item.statements_total for item in subprojects.values()),
        statements_covered=sum(item.statements_covered for item in subprojects.values()),
        branches_total=sum(item.branches_total for item in subprojects.values()),
        branches_covered=sum(item.branches_covered for item in subprojects.values()),
        functions_total=sum(item.functions_total for item in subprojects.values()),
        functions_covered=sum(item.functions_covered for item in subprojects.values()),
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate orchestrator/dashboard/desktop coverage facts into a single repo-level JSON report, "
            "and optionally enforce a fail-closed threshold gate."
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON report path.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD, help="Gate threshold percent (default: 95).")
    parser.add_argument("--enforce-gate", action="store_true", help="Exit non-zero when repo metrics are below threshold.")
    parser.add_argument("--orchestrator-report", type=Path, default=None, help="Optional explicit orchestrator pytest-cov JSON path.")
    parser.add_argument("--dashboard-report", type=Path, default=None, help="Optional explicit dashboard vitest summary JSON path.")
    parser.add_argument("--desktop-report", type=Path, default=None, help="Optional explicit desktop vitest summary JSON path.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        resolved = {
            "orchestrator": _resolve_source_report("orchestrator", args.orchestrator_report),
            "dashboard": _resolve_source_report("dashboard", args.dashboard_report),
            "desktop": _resolve_source_report("desktop", args.desktop_report),
        }
        source_reports = {project: source for project, (source, _totals) in resolved.items()}
        subprojects = {project: totals for project, (_source, totals) in resolved.items()}
        repo_totals = _aggregate_repo_totals(subprojects)
        repo_level = {
            "percent_covered": repo_totals.percent_covered,
            "percent_statements_covered": repo_totals.percent_statements_covered,
            "percent_branches_covered": repo_totals.percent_branches_covered,
            "totals": repo_totals.to_dict(),
        }

        gate_failures = [
            f"percent_covered={repo_level['percent_covered']:.2f}% < {args.threshold:.2f}%"
            for _ in [None]
            if repo_level["percent_covered"] < args.threshold
        ]
        if repo_level["percent_statements_covered"] < args.threshold:
            gate_failures.append(
                "percent_statements_covered="
                f"{repo_level['percent_statements_covered']:.2f}% < {args.threshold:.2f}%"
            )
        secondary_indicators: list[str] = []
        if repo_level["percent_branches_covered"] < args.threshold:
            secondary_indicators.append(
                "percent_branches_covered="
                f"{repo_level['percent_branches_covered']:.2f}% < {args.threshold:.2f}%"
            )

        gate_passed = len(gate_failures) == 0
        report = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "threshold_percent": _round2(args.threshold),
            "gate_mode": "enforced" if args.enforce_gate else "report-only",
            "gate_passed": gate_passed,
            "repo_level": repo_level,
            "subprojects": {
                project: {
                    "source_report": str(source_reports[project]),
                    "totals": totals.to_dict(),
                }
                for project, totals in subprojects.items()
            },
            "gate_failures": gate_failures,
            "secondary_indicators": secondary_indicators,
        }

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        print(f"✅ repo coverage report generated: {args.output}")
        print(
            "ℹ repo-level metrics: "
            f"percent_covered={repo_level['percent_covered']:.2f}% "
            f"percent_statements_covered={repo_level['percent_statements_covered']:.2f}% "
            f"percent_branches_covered={repo_level['percent_branches_covered']:.2f}%"
        )
        for indicator in secondary_indicators:
            print(f"ℹ secondary coverage indicator: {indicator}")

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
