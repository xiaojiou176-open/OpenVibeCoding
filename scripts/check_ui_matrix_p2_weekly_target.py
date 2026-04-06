#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = ROOT / "docs" / "governance" / "ui-button-coverage-matrix.md"


@dataclass(frozen=True)
class MatrixScope:
    tiers: set[str]
    surfaces: set[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute weekly P2 PARTIAL/COVERED statistics and weekly target convergence "
            "with configurable fail-closed mode."
        )
    )
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX), help="Matrix markdown path")
    parser.add_argument("--tiers", default="P2", help="Comma-separated tiers, e.g. P2")
    parser.add_argument("--surfaces", default="dashboard,desktop", help="Comma-separated surfaces")
    parser.add_argument("--partial-status", default="PARTIAL", help="Status label counted as PARTIAL")
    parser.add_argument("--covered-status", default="COVERED", help="Status label counted as COVERED")
    parser.add_argument("--target-partial-max", type=int, required=True, help="Weekly target upper bound for PARTIAL count")
    parser.add_argument("--target-covered-min", type=int, required=True, help="Weekly target lower bound for COVERED count")
    parser.add_argument(
        "--baseline-week-start",
        required=True,
        help="Baseline week start date in YYYY-MM-DD used for convergence speed.",
    )
    parser.add_argument("--baseline-partial", type=int, required=True, help="Baseline PARTIAL count")
    parser.add_argument("--baseline-covered", type=int, required=True, help="Baseline COVERED count")
    parser.add_argument(
        "--min-weekly-gap-reduction",
        type=float,
        default=0.0,
        help="Minimum average weekly reduction of target gap.",
    )
    parser.add_argument(
        "--as-of-date",
        default="",
        help="As-of date (YYYY-MM-DD). Defaults to current UTC date.",
    )
    parser.add_argument(
        "--fail-closed-mode",
        choices=("off", "warn", "strict"),
        default="warn",
        help="off=report only, warn=report+warn, strict=target miss exits non-zero.",
    )
    parser.add_argument(
        "--min-scoped",
        type=int,
        default=1,
        help="Fail when scoped rows are fewer than this value (default: 1). Use 0 to disable.",
    )
    parser.add_argument("--gate-name", default="ui-matrix-p2-weekly-target", help="Gate name in output")
    parser.add_argument("--report-out", default="", help="Optional output JSON report path")
    return parser.parse_args()


def _parse_scope(tiers: str, surfaces: str) -> MatrixScope:
    tier_set = {item.strip() for item in tiers.split(",") if item.strip()}
    surface_set = {item.strip() for item in surfaces.split(",") if item.strip()}
    if not tier_set:
        raise SystemExit("tiers must not be empty")
    if not surface_set:
        raise SystemExit("surfaces must not be empty")
    return MatrixScope(tiers=tier_set, surfaces=surface_set)


def _parse_as_of_date(raw: str) -> date:
    if raw.strip():
        return date.fromisoformat(raw.strip())
    return datetime.now(timezone.utc).date()


def _load_scoped_rows(matrix_path: Path, scope: MatrixScope) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in matrix_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| btn-"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        row = {
            "id": cols[0],
            "surface": cols[1],
            "tier": cols[2],
            "file": cols[3],
            "action": cols[4],
            "status": cols[5],
            "notes": cols[6],
        }
        if row["tier"] in scope.tiers and row["surface"] in scope.surfaces:
            rows.append(row)
    return rows


def _gap(partial_count: int, covered_count: int, partial_max: int, covered_min: int) -> int:
    return max(0, partial_count - partial_max) + max(0, covered_min - covered_count)


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix)
    if not matrix_path.exists():
        raise SystemExit(f"matrix not found: {matrix_path}")

    if args.target_partial_max < 0:
        raise SystemExit("target_partial_max must be >= 0")
    if args.target_covered_min < 0:
        raise SystemExit("target_covered_min must be >= 0")
    if args.baseline_partial < 0 or args.baseline_covered < 0:
        raise SystemExit("baseline counts must be >= 0")
    if args.min_scoped < 0:
        raise SystemExit("min_scoped must be >= 0")

    scope = _parse_scope(args.tiers, args.surfaces)
    as_of_date = _parse_as_of_date(args.as_of_date)
    baseline_date = date.fromisoformat(args.baseline_week_start.strip())
    if as_of_date < baseline_date:
        raise SystemExit("as_of_date must be >= baseline_week_start")

    scoped_rows = _load_scoped_rows(matrix_path, scope)
    if args.min_scoped > 0 and len(scoped_rows) < args.min_scoped:
        print(
            f"[{args.gate_name}] scoped rows below minimum: "
            f"scoped={len(scoped_rows)} < min_scoped={args.min_scoped}"
        )
        return 1

    status_counts: dict[str, int] = {}
    for row in scoped_rows:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    partial_count = status_counts.get(args.partial_status, 0)
    covered_count = status_counts.get(args.covered_status, 0)
    todo_count = status_counts.get("TODO", 0)

    current_gap = _gap(
        partial_count=partial_count,
        covered_count=covered_count,
        partial_max=args.target_partial_max,
        covered_min=args.target_covered_min,
    )
    baseline_gap = _gap(
        partial_count=args.baseline_partial,
        covered_count=args.baseline_covered,
        partial_max=args.target_partial_max,
        covered_min=args.target_covered_min,
    )

    days_elapsed = (as_of_date - baseline_date).days
    weeks_elapsed = max(1, (days_elapsed + 6) // 7)
    avg_weekly_gap_reduction = (baseline_gap - current_gap) / float(weeks_elapsed)

    partial_target_pass = partial_count <= args.target_partial_max
    covered_target_pass = covered_count >= args.target_covered_min
    convergence_target_pass = avg_weekly_gap_reduction >= args.min_weekly_gap_reduction
    targets_pass = partial_target_pass and covered_target_pass and convergence_target_pass

    iso_year, iso_week, _ = as_of_date.isocalendar()
    summary = (
        f"[{args.gate_name}] week={iso_year}-W{iso_week:02d} "
        f"scoped={len(scoped_rows)} partial={partial_count} covered={covered_count} todo={todo_count} "
        f"target_partial_max={args.target_partial_max} target_covered_min={args.target_covered_min} "
        f"gap={current_gap} baseline_gap={baseline_gap} weeks_elapsed={weeks_elapsed} "
        f"avg_weekly_gap_reduction={avg_weekly_gap_reduction:.3f} "
        f"target_min_weekly_gap_reduction={args.min_weekly_gap_reduction:.3f} "
        f"targets_pass={str(targets_pass).lower()} fail_closed_mode={args.fail_closed_mode}"
    )
    print(summary)

    fail_closed_options = {
        "off": "report-only; always exit 0 unless input/schema is invalid.",
        "warn": "target miss prints warning but exits 0.",
        "strict": "target miss exits 1 (fail-closed).",
    }

    report = {
        "report_type": "ui_matrix_p2_weekly_target",
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_name": args.gate_name,
        "scope": {
            "tiers": sorted(scope.tiers),
            "surfaces": sorted(scope.surfaces),
            "scoped_rows": len(scoped_rows),
            "min_scoped": args.min_scoped,
        },
        "as_of": {
            "date": as_of_date.isoformat(),
            "iso_year": iso_year,
            "iso_week": iso_week,
        },
        "status_counts": status_counts,
        "partial_status": args.partial_status,
        "covered_status": args.covered_status,
        "partial_count": partial_count,
        "covered_count": covered_count,
        "todo_count": todo_count,
        "weekly_target": {
            "partial_max": args.target_partial_max,
            "covered_min": args.target_covered_min,
            "min_weekly_gap_reduction": args.min_weekly_gap_reduction,
        },
        "baseline": {
            "week_start_date": baseline_date.isoformat(),
            "partial_count": args.baseline_partial,
            "covered_count": args.baseline_covered,
            "gap": baseline_gap,
        },
        "convergence": {
            "weeks_elapsed": weeks_elapsed,
            "current_gap": current_gap,
            "avg_weekly_gap_reduction": avg_weekly_gap_reduction,
        },
        "checks": {
            "partial_target_pass": partial_target_pass,
            "covered_target_pass": covered_target_pass,
            "convergence_target_pass": convergence_target_pass,
            "targets_pass": targets_pass,
        },
        "fail_closed_mode": args.fail_closed_mode,
        "fail_closed_options": fail_closed_options,
    }

    if args.report_out.strip():
        report_path = Path(args.report_out)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{args.gate_name}] report={report_path}")

    if not targets_pass:
        if args.fail_closed_mode == "warn":
            print(
                f"[{args.gate_name}] warning: weekly targets not met "
                "(mode=warn, exit=0; use mode=strict to fail-closed)"
            )
        if args.fail_closed_mode == "strict":
            print(f"[{args.gate_name}] fail-closed: weekly targets not met")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
