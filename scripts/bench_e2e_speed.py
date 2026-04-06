#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BENCH_ROOT = ROOT / ".runtime-cache" / "test_output" / "benchmarks"
UI_REPORT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_full_gemini_audit"
DASH_REPORT_ROOT = ROOT / ".runtime-cache" / "test_output" / "ui_regression"

SUITE_UI = "ui_full_gemini_strict"
SUITE_DASH = "dashboard_high_risk_e2e"


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _latest_report(pattern: str) -> Path | None:
    candidates = sorted(ROOT.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(float(v) for v in values)
    rank = (len(sorted_values) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _classify_ui_failure(report_payload: dict[str, Any], exit_code: int) -> str:
    errors = report_payload.get("errors") or []
    combined_error = " ".join(str(item) for item in errors).lower()
    summary = report_payload.get("summary") or {}
    if "timeout" in combined_error:
        return "timeout"
    if int(summary.get("interaction_click_failures", 0) or 0) > 0:
        return "interaction_click_failure"
    if int(summary.get("gemini_warn_or_fail", 0) or 0) > 0:
        return "gemini_warn_or_fail"
    if int(summary.get("click_inventory_blocking_failures", 0) or 0) > 0:
        return "click_inventory_blocking_failures"
    if int(summary.get("click_inventory_missing_target_refs", 0) or 0) > 0:
        return "click_inventory_missing_target_refs"
    if report_payload.get("errors"):
        return "runtime_error"
    if exit_code != 0:
        return "strict_gate_failed"
    return "unknown_failure"


def _classify_dash_failure(report_payload: dict[str, Any], exit_code: int) -> str:
    explicit = str(report_payload.get("failure_category", "")).strip()
    if explicit:
        return explicit
    failed_checks = report_payload.get("failed_checks") or []
    error_text = str(report_payload.get("error", "")).lower()
    if failed_checks:
        return "assertion_failure"
    if "timeout" in error_text:
        return "timeout"
    if exit_code != 0:
        return "command_failed"
    return "unknown_failure"


def _build_summary(results: list[dict[str, Any]], run_id: str, run_dir: Path) -> dict[str, Any]:
    suite_names = sorted({item["suite"] for item in results})
    suites: dict[str, Any] = {}
    all_durations = [float(item.get("duration_sec", 0.0) or 0.0) for item in results]
    total_failures = 0
    for suite in suite_names:
        suite_rows = [item for item in results if item["suite"] == suite]
        durations = [float(item.get("duration_sec", 0.0) or 0.0) for item in suite_rows]
        failures = [item for item in suite_rows if not bool(item.get("success", False))]
        total_failures += len(failures)
        category_counts: dict[str, int] = {}
        for row in failures:
            cat = str(row.get("failure_category", "") or "unknown_failure")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        suites[suite] = {
            "count": len(suite_rows),
            "success_count": len(suite_rows) - len(failures),
            "failure_count": len(failures),
            "fail_rate": round((len(failures) / len(suite_rows)) if suite_rows else 0.0, 6),
            "duration_sec": {
                "avg": round(statistics.mean(durations), 6) if durations else 0.0,
                "p50": round(_percentile(durations, 0.50), 6),
                "p95": round(_percentile(durations, 0.95), 6),
                "min": round(min(durations), 6) if durations else 0.0,
                "max": round(max(durations), 6) if durations else 0.0,
            },
            "failure_categories": category_counts,
        }
    return {
        "run_id": run_id,
        "generated_at": _now_utc(),
        "results_count": len(results),
        "run_dir": str(run_dir),
        "overall": {
            "count": len(results),
            "failure_count": total_failures,
            "fail_rate": round((total_failures / len(results)) if results else 0.0, 6),
            "duration_sec": {
                "avg": round(statistics.mean(all_durations), 6) if all_durations else 0.0,
                "p50": round(_percentile(all_durations, 0.50), 6),
                "p95": round(_percentile(all_durations, 0.95), 6),
                "min": round(min(all_durations), 6) if all_durations else 0.0,
                "max": round(max(all_durations), 6) if all_durations else 0.0,
            },
        },
        "suites": suites,
    }


def _render_markdown(summary: dict[str, Any], results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# E2E Speed Benchmark Summary")
    lines.append("")
    lines.append(f"- run_id: `{summary.get('run_id', '')}`")
    lines.append(f"- generated_at: `{summary.get('generated_at', '')}`")
    lines.append(f"- total_runs: `{summary.get('overall', {}).get('count', 0)}`")
    lines.append(f"- fail_rate: `{summary.get('overall', {}).get('fail_rate', 0)}`")
    lines.append("")
    lines.append("## Suite Metrics")
    lines.append("")
    lines.append("| suite | count | p50(s) | p95(s) | fail_rate | failures |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for suite_name, suite in (summary.get("suites") or {}).items():
        duration = suite.get("duration_sec") or {}
        lines.append(
            "| {suite} | {count} | {p50:.3f} | {p95:.3f} | {fail_rate:.4f} | {failures} |".format(
                suite=suite_name,
                count=int(suite.get("count", 0) or 0),
                p50=float(duration.get("p50", 0.0) or 0.0),
                p95=float(duration.get("p95", 0.0) or 0.0),
                fail_rate=float(suite.get("fail_rate", 0.0) or 0.0),
                failures=int(suite.get("failure_count", 0) or 0),
            )
        )
    lines.append("")
    lines.append("## Failure Categories")
    lines.append("")
    for suite_name, suite in (summary.get("suites") or {}).items():
        cats = suite.get("failure_categories") or {}
        if not cats:
            lines.append(f"- `{suite_name}`: none")
            continue
        rendered = ", ".join(f"`{name}`={count}" for name, count in sorted(cats.items()))
        lines.append(f"- `{suite_name}`: {rendered}")
    lines.append("")
    lines.append("## Round Details")
    lines.append("")
    lines.append("| round | suite | status | duration(s) | failure_category | report |")
    lines.append("|---:|---|---|---:|---|---|")
    for row in results:
        status = "PASS" if bool(row.get("success", False)) else "FAIL"
        report = str(row.get("report_path", "") or "-")
        lines.append(
            "| {round_idx} | {suite} | {status} | {duration:.3f} | {failure} | `{report}` |".format(
                round_idx=int(row.get("round", 0) or 0),
                suite=str(row.get("suite", "")),
                status=status,
                duration=float(row.get("duration_sec", 0.0) or 0.0),
                failure=str(row.get("failure_category", "") or "-"),
                report=report,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _run_once(
    *,
    suite: str,
    round_idx: int,
    run_id: str,
    dry_run: bool,
    ui_command: str,
    dash_command: str,
) -> dict[str, Any]:
    started = _now_utc()
    t0 = time.perf_counter()
    env = os.environ.copy()
    artifact_suffix = f"bench_{run_id}_{suite}_r{round_idx:03d}"
    env["CORTEXPILOT_E2E_ARTIFACT_SUFFIX"] = artifact_suffix

    command = ""
    report_path = ""
    exit_code = 0
    failure_category = ""
    success = True

    if suite == SUITE_UI:
        ui_run_id = f"bench_{run_id}_ui_r{round_idx:03d}"
        env["CORTEXPILOT_UI_FULL_E2E_RUN_ID"] = ui_run_id
        command = ui_command
        report_path_obj = UI_REPORT_ROOT / ui_run_id / "report.json"
    elif suite == SUITE_DASH:
        command = dash_command
        report_path_obj = DASH_REPORT_ROOT / f"dashboard_high_risk_actions_real.{artifact_suffix}.json"
    else:
        raise ValueError(f"unsupported suite: {suite}")

    if dry_run:
        success = True
        failure_category = ""
    else:
        run = subprocess.run(
            shlex.split(command),
            cwd=ROOT,
            env=env,
            shell=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        exit_code = int(run.returncode)
        success = exit_code == 0
        if report_path_obj.exists():
            report_path = str(report_path_obj.resolve())
            try:
                payload = json.loads(report_path_obj.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if not success:
                if suite == SUITE_UI:
                    failure_category = _classify_ui_failure(payload, exit_code)
                else:
                    failure_category = _classify_dash_failure(payload, exit_code)
        else:
            latest = None
            if suite == SUITE_UI:
                latest = _latest_report(".runtime-cache/test_output/ui_full_gemini_audit/*/report.json")
            elif suite == SUITE_DASH:
                latest = _latest_report(".runtime-cache/test_output/ui_regression/dashboard_high_risk_actions_real*.json")
            if latest is not None:
                report_path = str(latest.resolve())
            if not success:
                failure_category = "report_missing"

    duration = time.perf_counter() - t0
    finished = _now_utc()
    return {
        "suite": suite,
        "round": round_idx,
        "command": command,
        "dry_run": dry_run,
        "started_at": started,
        "finished_at": finished,
        "duration_sec": round(duration, 6),
        "success": success,
        "exit_code": exit_code,
        "failure_category": failure_category,
        "report_path": report_path,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run N-round E2E speed benchmark and aggregate p50/p95/fail-rate.")
    parser.add_argument("--rounds", type=int, default=3, help="Continuous rounds for each enabled suite.")
    parser.add_argument("--ui-full-gemini-strict", action="store_true", help="Enable ui full gemini strict benchmark.")
    parser.add_argument("--dashboard-high-risk", action="store_true", help="Enable dashboard high-risk e2e benchmark.")
    parser.add_argument("--dry-run", action="store_true", help="Only plan command execution without running suites.")
    parser.add_argument("--report-only", action="store_true", help="Skip execution and aggregate from existing raw results.")
    parser.add_argument("--run-id", default="", help="Run id for output directory.")
    parser.add_argument("--run-dir", default="", help="Existing benchmark run dir for report-only mode.")
    parser.add_argument("--raw-results", default="", help="Existing raw results json path for report-only mode.")
    parser.add_argument("--ui-command", default="npm run ui:e2e:full:gemini:strict")
    parser.add_argument("--dash-command", default="npm run dashboard:e2e:high-risk-actions:real")
    parser.add_argument("--stop-on-failure", action="store_true", help="Stop remaining rounds when a suite fails once.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.rounds < 1:
        print("❌ --rounds must be >= 1", file=sys.stderr)
        return 2

    BENCH_ROOT.mkdir(parents=True, exist_ok=True)
    run_id = str(args.run_id or dt.datetime.now(dt.timezone.utc).strftime("bench_%Y%m%d_%H%M%S"))
    run_dir = Path(args.run_dir).expanduser().resolve() if args.run_dir else (BENCH_ROOT / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_path = Path(args.raw_results).expanduser().resolve() if args.raw_results else (run_dir / "raw_results.json")
    summary_json_path = run_dir / "summary.json"
    summary_md_path = run_dir / "summary.md"

    if args.report_only:
        if not raw_path.exists():
            print(f"❌ report-only requires raw results file: {raw_path}", file=sys.stderr)
            return 2
        rows = json.loads(raw_path.read_text(encoding="utf-8"))
        summary = _build_summary(rows, run_id=run_id, run_dir=run_dir)
        summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary_md_path.write_text(_render_markdown(summary, rows), encoding="utf-8")
        print(f"✅ [bench] report-only aggregated from: {raw_path}")
        print(f"📄 summary_json={summary_json_path}")
        print(f"📄 summary_md={summary_md_path}")
        return 0

    suites: list[str] = []
    if args.ui_full_gemini_strict:
        suites.append(SUITE_UI)
    if args.dashboard_high_risk:
        suites.append(SUITE_DASH)
    if not suites:
        print("❌ enable at least one suite: --ui-full-gemini-strict and/or --dashboard-high-risk", file=sys.stderr)
        return 2

    print(f"🚀 [bench] run_id={run_id}")
    print(f"📁 [bench] run_dir={run_dir}")
    print(f"🔁 [bench] rounds={args.rounds} suites={','.join(suites)} dry_run={args.dry_run}")

    rows: list[dict[str, Any]] = []
    for round_idx in range(1, args.rounds + 1):
        for suite in suites:
            print(f"▶️  [bench] round={round_idx}/{args.rounds} suite={suite}")
            row = _run_once(
                suite=suite,
                round_idx=round_idx,
                run_id=run_id,
                dry_run=args.dry_run,
                ui_command=args.ui_command,
                dash_command=args.dash_command,
            )
            rows.append(row)
            status = "PASS" if row["success"] else "FAIL"
            print(
                f"   [{status}] duration={row['duration_sec']:.3f}s"
                f" failure_category={row.get('failure_category', '') or '-'} report={row.get('report_path', '') or '-'}"
            )
            if args.stop_on_failure and not row["success"]:
                print("⏹️  [bench] stop-on-failure triggered")
                break
        if args.stop_on_failure and rows and not rows[-1]["success"]:
            break

    raw_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = _build_summary(rows, run_id=run_id, run_dir=run_dir)
    summary_json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_md_path.write_text(_render_markdown(summary, rows), encoding="utf-8")

    print(f"✅ [bench] done: rows={len(rows)}")
    print(f"📄 raw_results={raw_path}")
    print(f"📄 summary_json={summary_json_path}")
    print(f"📄 summary_md={summary_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
