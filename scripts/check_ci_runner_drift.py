#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "configs" / "ci_runner_baseline.json"
DEFAULT_OUT_DIR = ROOT / ".runtime-cache" / "cortexpilot" / "reports" / "ci" / "runner_drift"
REPORT_ONLY_ROUTE_IDS = {"trusted_pr", "untrusted_pr", "push_main"}
HOST_ONLY_COMMANDS = {"docker", "sudo"}


def _run_command(name: str, args: list[str]) -> tuple[bool, str]:
    if shutil.which(name) is None:
        return False, ""
    try:
        proc = subprocess.run(
            [name, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return True, ""
    output = (proc.stdout or proc.stderr or "").strip().splitlines()
    return True, output[0].strip() if output else ""


def _current_ci_route_id() -> str:
    return str(os.environ.get("CORTEXPILOT_CI_ROUTE_ID") or "").strip()


def _is_report_only_host_check(name: str, *, route_id: str) -> bool:
    return route_id in REPORT_ONLY_ROUTE_IDS and name in HOST_ONLY_COMMANDS


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GitHub-hosted CI runner toolchain drift.")
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE), help="Baseline JSON path")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    parser.add_argument(
        "--mode",
        choices=("strict", "report"),
        default="strict",
        help="strict=fail on drift, report=emit report only",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    route_id = _current_ci_route_id()
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for item in baseline.get("commands", []):
        name = str(item.get("name") or "").strip()
        version_args = [str(x) for x in item.get("version_args") or []]
        required = bool(item.get("required", True))
        pattern = str(item.get("match_regex") or "").strip()
        report_only = _is_report_only_host_check(name, route_id=route_id)
        found, output = _run_command(name, version_args)
        row = {
            "name": name,
            "required": required,
            "report_only": report_only,
            "match_regex": pattern,
            "found": found,
            "output": output,
            "matched": False,
        }
        if not found:
            if required and not report_only:
                failures.append(f"{name}: command missing")
            rows.append(row)
            continue
        if pattern:
            matched = re.search(pattern, output) is not None
            row["matched"] = matched
            if required and not matched and not report_only:
                failures.append(f"{name}: output drift (`{output}`)")
        else:
            row["matched"] = True
        rows.append(row)

    payload = {
        "report_type": "cortexpilot_ci_runner_drift_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": str(baseline_path),
        "route_id": route_id or None,
        "mode": args.mode,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "checks": rows,
    }
    report_json = out_dir / "report.json"
    summary_md = out_dir / "summary.md"
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_md.write_text(
        "\n".join(
            [
                "## CI Runner Drift",
                "",
                f"- status: **{payload['status']}**",
                f"- baseline: `{baseline_path}`",
                f"- mode: `{args.mode}`",
                f"- failures: `{len(failures)}`",
                "",
            ]
            + [f"- {item}" for item in failures]
            + [""]
        ),
        encoding="utf-8",
    )
    print(str(report_json))
    print(str(summary_md))
    if failures and args.mode == "strict":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
