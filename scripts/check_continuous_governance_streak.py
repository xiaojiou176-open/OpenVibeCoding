#!/usr/bin/env python3
"""Validate Continuous Governance recent streak and produce trend score outputs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse


def _parse_windows(args: argparse.Namespace) -> list[int]:
    windows: list[int] = []
    if args.windows.strip():
        for raw in args.windows.split(","):
            token = raw.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError as exc:
                raise ValueError(f"invalid window: {token}") from exc
            if value < 1:
                raise ValueError(f"window must be >= 1: {value}")
            if value not in windows:
                windows.append(value)
    if args.window is not None and args.window >= 1 and args.window not in windows:
        windows.append(args.window)
    if not windows:
        windows = [7, 14]
    return sorted(windows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check recent workflow runs with multi-window streak + trend score."
    )
    parser.add_argument(
        "--workflow-file",
        default=".github/workflows/continuous-governance.yml",
        help="Workflow file path or file name.",
    )
    parser.add_argument(
        "--windows",
        default="7,14",
        help="Comma-separated windows, e.g. 7,14.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=None,
        help="Legacy single window override (compatible mode).",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="GitHub repository in owner/repo format. Defaults to GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--current-run-id",
        default="",
        help="Current run id to exclude. Defaults to GITHUB_RUN_ID.",
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Branch name filter. Defaults to GITHUB_REF_NAME when present.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when available completed runs are fewer than any requested window.",
    )
    parser.add_argument(
        "--soft-fail",
        action="store_true",
        help="Always exit 0 while still reporting gate_passed=false when applicable.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional path to write machine-readable JSON report.",
    )
    parser.add_argument(
        "--summary-output",
        default="",
        help="Optional path to write human-readable markdown summary.",
    )
    parser.add_argument(
        "--write-step-summary",
        action="store_true",
        help="Append markdown summary to GITHUB_STEP_SUMMARY when available.",
    )
    return parser.parse_args()


def _fail(message: str) -> int:
    print(f"❌ [continuous-governance] {message}", file=sys.stderr)
    return 1


def _soft_or_fail(message: str, soft_fail: bool) -> int:
    if soft_fail:
        print(f"⚠️ [continuous-governance] {message}; soft-fail enabled")
        return 0
    return _fail(message)


def _detect_repo_from_git_remote() -> str:
    proc = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    raw = proc.stdout.strip()
    if not raw:
        return ""
    if raw.startswith("git@github.com:") and raw.endswith(".git"):
        return raw[len("git@github.com:") : -len(".git")]
    if raw.startswith("git@github.com:"):
        return raw[len("git@github.com:") :]
    parsed = urlparse(raw)
    if parsed.netloc == "github.com" and parsed.path:
        path = parsed.path.lstrip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        return path
    return ""


def _run_gh_api(path: str) -> dict[str, Any]:
    command = ["gh", "api", path]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh api failed")
    return json.loads(proc.stdout)


def _normalize_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run.get("id"),
        "run_number": run.get("run_number"),
        "event": run.get("event"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("created_at"),
        "html_url": run.get("html_url"),
    }


def _grade(score: float) -> str:
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


def _build_summary(report: dict[str, Any]) -> str:
    trend = report["trend"]
    lines = [
        "### Continuous Governance Trend Score",
        f"- Overall score: **{trend['score']:.2f}** (grade **{trend['grade']}**)",
        f"- Gate passed: **{'yes' if report['gate_passed'] else 'no'}**",
        f"- Workflow: `{report['workflow']}`",
        f"- Branch: `{report['branch'] or 'all'}`",
        "",
        "| Window | Checked | Success | Pass Rate | Coverage | Window Score | Passed |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["window_metrics"]:
        lines.append(
            "| {window} | {checked_count} | {success_count} | {pass_rate:.2%} | {coverage_ratio:.2%} | {score:.2f} | {passed} |".format(
                window=row["window"],
                checked_count=row["checked_count"],
                success_count=row["success_count"],
                pass_rate=row["pass_rate"],
                coverage_ratio=row["coverage_ratio"],
                score=row["score"],
                passed="yes" if row["passed"] else "no",
            )
        )
    lines.extend(
        [
            "",
            f"- Momentum (`W{trend['short_window']} - W{trend['long_window']}` pass rate): **{trend['momentum']:+.4f}**",
            f"- Weighted base score: **{trend['weighted_base_score']:.2f}**",
            f"- Momentum adjustment: **{trend['momentum_adjustment']:+.2f}**",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def main() -> int:
    args = _parse_args()

    try:
        windows = _parse_windows(args)
    except ValueError as exc:
        return _soft_or_fail(str(exc), args.soft_fail)

    if shutil.which("gh") is None:
        return _soft_or_fail("gh cli is required for streak check", args.soft_fail)

    repo = (
        args.repo.strip()
        or os.environ.get("GITHUB_REPOSITORY", "").strip()
        or _detect_repo_from_git_remote()
    )
    if not repo:
        return _soft_or_fail("missing repo; set --repo or GITHUB_REPOSITORY", args.soft_fail)

    current_run_id = args.current_run_id.strip() or os.environ.get("GITHUB_RUN_ID", "").strip()
    branch = args.branch.strip() or os.environ.get("GITHUB_REF_NAME", "").strip()

    workflow_name = Path(args.workflow_file).name
    max_window = max(windows)
    query = (
        f"/repos/{repo}/actions/workflows/{quote(workflow_name, safe='')}/runs"
        f"?status=completed&per_page={max(30, max_window + 10)}"
    )
    if branch:
        query = f"{query}&branch={quote(branch, safe='')}"

    try:
        payload = _run_gh_api(query)
    except Exception as exc:  # pragma: no cover - cli integration
        return _soft_or_fail(f"unable to load workflow runs: {exc}", args.soft_fail)

    runs = payload.get("workflow_runs", [])
    if not isinstance(runs, list):
        return _soft_or_fail("invalid workflow runs payload", args.soft_fail)

    selected: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("id", "")).strip()
        if current_run_id and run_id == current_run_id:
            continue
        if run.get("status") != "completed":
            continue
        if run.get("conclusion") is None:
            continue
        selected.append(run)
        if len(selected) >= max_window:
            break

    window_metrics: list[dict[str, Any]] = []
    gate_passed = True
    for window in windows:
        checked = selected[:window]
        checked_count = len(checked)
        success_count = sum(1 for run in checked if run.get("conclusion") == "success")
        failed_count = checked_count - success_count
        pass_rate = (success_count / checked_count) if checked_count else 0.0
        coverage_ratio = min(1.0, checked_count / window)
        window_score = max(0.0, min(100.0, pass_rate * 100.0 * coverage_ratio))
        insufficient_history = checked_count < window
        passed = failed_count == 0 and (not args.strict or not insufficient_history)
        if not passed:
            gate_passed = False
        window_metrics.append(
            {
                "window": window,
                "required_count": window,
                "checked_count": checked_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "pass_rate": round(pass_rate, 6),
                "coverage_ratio": round(coverage_ratio, 6),
                "score": round(window_score, 2),
                "insufficient_history": insufficient_history,
                "passed": passed,
            }
        )

    short_window = windows[0]
    long_window = windows[-1]
    short_metric = next(item for item in window_metrics if item["window"] == short_window)
    long_metric = next(item for item in window_metrics if item["window"] == long_window)

    short_pass_rate = float(short_metric["pass_rate"])
    long_pass_rate = float(long_metric["pass_rate"])
    momentum = short_pass_rate - long_pass_rate

    weighted_base_score = short_metric["score"] * 0.6 + long_metric["score"] * 0.4
    momentum_adjustment = max(-10.0, min(10.0, momentum * 20.0))
    trend_score = max(0.0, min(100.0, weighted_base_score + momentum_adjustment))

    report: dict[str, Any] = {
        "report_type": "continuous_governance_streak_trend",
        "schema_version": 2,
        "repo": repo,
        "workflow": workflow_name,
        "branch": branch or None,
        "windows": windows,
        "strict": args.strict,
        "soft_fail": args.soft_fail,
        "checked_runs_total": len(selected),
        "gate_passed": gate_passed,
        "window_metrics": window_metrics,
        "trend": {
            "short_window": short_window,
            "long_window": long_window,
            "short_pass_rate": round(short_pass_rate, 6),
            "long_pass_rate": round(long_pass_rate, 6),
            "momentum": round(momentum, 6),
            "weighted_base_score": round(weighted_base_score, 2),
            "momentum_adjustment": round(momentum_adjustment, 2),
            "score": round(trend_score, 2),
            "grade": _grade(trend_score),
        },
        "runs": [_normalize_run(run) for run in selected],
    }

    summary_md = _build_summary(report)

    if args.json_output.strip():
        _write_text(args.json_output.strip(), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if args.summary_output.strip():
        _write_text(args.summary_output.strip(), summary_md)

    if args.write_step_summary:
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
        if summary_path:
            with Path(summary_path).open("a", encoding="utf-8") as handle:
                handle.write(summary_md)

    print(json.dumps(report, ensure_ascii=False))
    print(summary_md)

    if gate_passed:
        return 0
    if args.soft_fail:
        print("⚠️ [continuous-governance] streak gate failed but soft-fail is enabled")
        return 0
    return _fail("recent streak gate failed under one or more configured windows")


if __name__ == "__main__":
    raise SystemExit(main())
